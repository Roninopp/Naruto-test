import logging
import json
import datetime
import asyncio
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
import game_logic as gl
import animations as anim 

logger = logging.getLogger(__name__)

# --- In-Memory Battle Management ---
ACTIVE_BATTLES = {}
BATTLE_INVITES = {}
BATTLE_COOLDOWN_MINUTES = 5

# --- Helper Functions ---

def get_battle_text(players, turn_player_id):
    """Generates the base text for the battle menu (HP bars)."""
    player_ids = list(players.keys())
    if player_ids[0] < player_ids[1]:
        p1 = players[player_ids[0]]
        p2 = players[player_ids[1]]
    else:
        p1 = players[player_ids[1]]
        p2 = players[player_ids[0]]

    # Recalculate max HP/Chakra based on TOTAL stats for display
    p1_total_stats = gl.get_total_stats(p1)
    p2_total_stats = gl.get_total_stats(p2)
    
    if turn_player_id == p1['user_id']:
        attacker = p1
    else:
        attacker = p2

    text = (
        f"⚔️ <b>BATTLE!</b> ⚔️\n\n"
        f"<b>{p1['username']}</b> [Lvl {p1['level']}]\n"
        # Display HP bar using total max HP
        f"HP: {gl.health_bar(p1['current_hp'], p1_total_stats['max_hp'])}\n\n" 
        f"<b>{p2['username']}</b> [Lvl {p2['level']}]\n"
        # Display HP bar using total max HP
        f"HP: {gl.health_bar(p2['current_hp'], p2_total_stats['max_hp'])}\n\n" 
        f"<b>Turn: {attacker['username']}</b>\n"
        "Choose your action:"
    )
    return text

async def send_battle_menu(context: ContextTypes.DEFAULT_TYPE, battle_state, message_id=None):
    """Sends or edits the main battle menu."""
    
    players = battle_state['players']
    turn_player_id = battle_state['turn']
    
    text = get_battle_text(players, turn_player_id)
    
    # Store the base text without the 'Turn' line
    battle_state['base_text'] = text.split("\n\n<b>Turn:")[0] 
    
    keyboard = [
        [
            InlineKeyboardButton("⚔️ Taijutsu", callback_data=f"battle_action_taijutsu_{turn_player_id}"),
            InlineKeyboardButton("🌀 Use Jutsu", callback_data=f"battle_action_jutsu_{turn_player_id}"),
            InlineKeyboardButton("🏃 Flee", callback_data=f"battle_action_flee_{turn_player_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if message_id:
            await context.bot.edit_message_text(
                chat_id=battle_state['chat_id'],
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            return message_id
        else:
            message = await context.bot.send_message(
                chat_id=battle_state['chat_id'],
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            return message.message_id
    except Exception as e:
        logger.error(f"Error sending battle menu: {e}")
        return message_id


async def end_battle(context: ContextTypes.DEFAULT_TYPE, battle_id, winner_id, loser_id, chat_id, message_id, fled=False):
    """Cleans up the battle, updates DB, and announces winner."""
    
    battle_state = ACTIVE_BATTLES.pop(battle_id, None)
    if not battle_state:
        return

    winner = battle_state['players'][winner_id]
    loser = battle_state['players'][loser_id]
    
    if fled:
        text = f"🏃 <b>{loser['username']}</b> fled the battle! <b>{winner['username']}</b> wins by default!"
    else:
        text = f"🏆 <b>{winner['username']}</b> is victorious! 🏆\n{loser['username']} has been defeated."

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=None,
        parse_mode="HTML"
    )

    cooldown_time = (datetime.datetime.now() + datetime.timedelta(minutes=BATTLE_COOLDOWN_MINUTES)).isoformat()
    
    winner_exp_gain = loser['level'] * 10
    winner_ryo_gain = loser['level'] * 20
    
    winner['wins'] += 1
    winner['battle_cooldown'] = cooldown_time
    winner['exp'] += winner_exp_gain
    winner['total_exp'] += winner_exp_gain
    winner['ryo'] += winner_ryo_gain
    
    # Update winner: check_for_level_up needs the full dict
    final_winner_data, leveled_up, messages = gl.check_for_level_up(winner)
    db.update_player(winner_id, final_winner_data)
    
    loser['losses'] += 1
    loser['battle_cooldown'] = cooldown_time
    # Recalculate max HP for loser based on their total stats before setting HP to 1
    loser_total_stats = gl.get_total_stats(loser) 
    loser['max_hp'] = loser_total_stats['max_hp'] # Update max HP in case it changed
    loser['current_hp'] = 1 
    
    # Update loser: only need specific fields
    loser_updates = {
        'losses': loser['losses'],
        'battle_cooldown': loser['battle_cooldown'],
        'current_hp': loser['current_hp'],
        'max_hp': loser['max_hp'] # Save updated max HP
    }
    db.update_player(loser_id, loser_updates)
    
    reward_text = f"<b>{winner['username']}</b> gained +{winner_exp_gain} EXP and +{winner_ryo_gain} Ryo!"
    if leveled_up:
        reward_text += "\n\n" + "\n".join(messages)
    await context.bot.send_message(chat_id=chat_id, text=reward_text, parse_mode="HTML")


# --- Command Handlers ---

async def battle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    challenger = update.effective_user
    
    if not update.message.reply_to_message:
        await update.message.reply_text("To challenge someone, you must reply to one of their messages and type /battle.")
        return

    challenged = update.message.reply_to_message.from_user
    
    if challenged.is_bot:
        await update.message.reply_text("You cannot battle a bot.")
        return
    if challenged.id == challenger.id:
        await update.message.reply_text("You cannot battle yourself.")
        return

    p1 = db.get_player(challenger.id)
    p2 = db.get_player(challenged.id)

    if not p1 or not p2:
        await update.message.reply_text("One of the players is not registered. (Use /start).")
        return
        
    # Check if either player is currently in a battle by checking their ID in ACTIVE_BATTLES keys
    p1_in_battle = any(str(p1['user_id']) in battle_id_key for battle_id_key in ACTIVE_BATTLES)
    p2_in_battle = any(str(p2['user_id']) in battle_id_key for battle_id_key in ACTIVE_BATTLES)

    if p1_in_battle or p2_in_battle:
        await update.message.reply_text("One of the players is already in a battle.")
        return
        
    if p1['user_id'] in BATTLE_INVITES.values() or p2['user_id'] in BATTLE_INVITES:
        await update.message.reply_text("One of the players already has a pending battle invite.")
        return

    now = datetime.datetime.now()
    for player in [p1, p2]:
        if player['battle_cooldown']:
            cooldown_time = datetime.datetime.fromisoformat(player['battle_cooldown'])
            if now < cooldown_time:
                remaining = (cooldown_time - now).seconds // 60 + 1
                await update.message.reply_text(f"{player['username']} is on battle cooldown for {remaining} more minute(s).")
                return

    BATTLE_INVITES[p2['user_id']] = p1['user_id']
    
    text = f"<b>{p2['username']}!</b>\n{p1['username']} has challenged you to a battle!"
    keyboard = [
        [
            InlineKeyboardButton("✅ Accept", callback_data=f"battle_invite_accept_{p1['user_id']}"),
            InlineKeyboardButton("❌ Decline", callback_data=f"battle_invite_decline_{p1['user_id']}")
        ]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# --- Callback Handlers ---

async def battle_invite_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split('_')
    action = parts[2]
    challenger_id_str = parts[3]

    challenger_id = int(challenger_id_str)
    challenged_id = query.from_user.id
    
    if BATTLE_INVITES.get(challenged_id) != challenger_id:
        await query.edit_message_text("This battle invite has expired.", reply_markup=None)
        return
        
    BATTLE_INVITES.pop(challenged_id)
    
    challenger = db.get_player(challenger_id)
    challenged = db.get_player(challenged_id)

    if action == "decline":
        await query.edit_message_text(f"{challenged['username']} has declined the battle challenge from {challenger['username']}.", reply_markup=None)
        return

    if not challenger or not challenged:
        await query.edit_message_text("Error: One of the players could not be found.", reply_markup=None)
        return
        
    p1 = dict(challenger)
    p2 = dict(challenged)
    
    # Calculate total stats ONCE at the start
    p1['total_stats'] = gl.get_total_stats(p1)
    p2['total_stats'] = gl.get_total_stats(p2)
    
    # Use total speed for turn order
    if p1['total_stats']['speed'] > p2['total_stats']['speed']:
        turn_player_id = p1['user_id']
    elif p2['total_stats']['speed'] > p1['total_stats']['speed']:
        turn_player_id = p2['user_id']
    else: 
        turn_player_id = random.choice([p1['user_id'], p2['user_id']])

    battle_id = f"{p1['user_id']}_vs_{p2['user_id']}"
    battle_state = {
        'players': {p1['user_id']: p1, p2['user_id']: p2},
        'turn': turn_player_id,
        'message_id': None,
        'chat_id': query.message.chat_id,
        'base_text': '' 
    }
    
    ACTIVE_BATTLES[battle_id] = battle_state
    
    message_id = await send_battle_menu(
        context, 
        battle_state,
        message_id=query.message.message_id
    )
    
    ACTIVE_BATTLES[battle_id]['message_id'] = message_id


async def battle_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    action = parts[2]
    player_id_str = parts[3]
    
    player_id = int(player_id_str)

    battle_id = None
    for bid, bstate in ACTIVE_BATTLES.items():
        if player_id in bstate['players']:
            battle_id = bid
            break
            
    if not battle_id:
        await query.edit_message_text("This battle is no longer active.", reply_markup=None)
        return

    battle_state = ACTIVE_BATTLES[battle_id]

    if battle_state['turn'] != player_id:
        await query.answer("It's not your turn!", show_alert=True)
        return
        
    attacker = battle_state['players'][player_id]
    defender_id = [pid for pid in battle_state['players'] if pid != player_id][0]
    defender = battle_state['players'][defender_id]

    chat_id = battle_state['chat_id']
    message_id = battle_state['message_id']
    
    await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\n<i>Processing turn...</i>", reply_markup=None)
    
    if action == "flee":
        if random.random() < 0.5: 
            await end_battle(context, battle_id, defender_id, player_id, chat_id, message_id, fled=True)
        else:
            await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\n<i>{attacker['username']} tried to flee but failed!</i>")
            await asyncio.sleep(2)
            battle_state['turn'] = defender_id
            await send_battle_menu(context, battle_state, message_id)
        return

    if action == "taijutsu":
        # --- CHANGE: Pass full player dicts to damage func ---
        damage, is_crit = gl.calculate_taijutsu_damage(attacker, defender)
        
        defender['current_hp'] -= damage
        
        await anim.animate_taijutsu(context, battle_state, attacker, defender, damage, is_crit)
        
        if defender['current_hp'] <= 0:
            await end_battle(context, battle_id, player_id, defender_id, chat_id, message_id)
        else:
            battle_state['turn'] = defender_id
            await send_battle_menu(context, battle_state, message_id)
        return

    if action == "jutsu":
        if attacker['level'] < gl.JUTSU_LIBRARY['fireball']['level_required']:
            await query.answer("You must be at least Level 5 to use jutsus!", show_alert=True)
            await send_battle_menu(context, battle_state, message_id)
            return
            
        known_jutsus = json.loads(attacker['known_jutsus'])
        
        if not known_jutsus:
            await query.answer("You don't know any jutsus! Use /combine to learn some.", show_alert=True)
            await send_battle_menu(context, battle_state, message_id)
            return

        keyboard = []
        for jutsu_name_key in known_jutsus:
            jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_name_key)
            if jutsu_info:
                button_text = f"{jutsu_info['name']} (Cost: {jutsu_info['chakra_cost']})"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"battle_jutsu_{player_id}_{jutsu_name_key}")])
        
        keyboard.append([InlineKeyboardButton("Cancel", callback_data=f"battle_jutsu_{player_id}_cancel")])
        
        await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\nSelect a Jutsu:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

async def battle_jutsu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split('_')
    player_id = int(parts[2])
    jutsu_key = "_".join(parts[3:]) 

    battle_id = None
    for bid, bstate in ACTIVE_BATTLES.items():
        if player_id in bstate['players']:
            battle_id = bid
            break
            
    if not battle_id:
        await query.edit_message_text("This battle is no longer active.", reply_markup=None)
        return

    battle_state = ACTIVE_BATTLES[battle_id]
    
    if battle_state['turn'] != player_id:
        await query.answer("It's not your turn!", show_alert=True)
        return

    chat_id = battle_state['chat_id']
    message_id = battle_state['message_id']
    
    if jutsu_key == "cancel":
        await send_battle_menu(context, battle_state, message_id)
        return

    attacker = battle_state['players'][player_id]
    defender_id = [pid for pid in battle_state['players'] if pid != player_id][0]
    defender = battle_state['players'][defender_id]

    jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_key)
    if not jutsu_info:
        await query.message.reply_text("Error: Unknown jutsu selected.")
        return

    if attacker['current_chakra'] < jutsu_info['chakra_cost']:
        await query.answer("Not enough chakra!", show_alert=True)
        await send_battle_menu(context, battle_state, message_id)
        return
        
    await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\n<i>Processing turn...</i>", reply_markup=None)
        
    attacker['current_chakra'] -= jutsu_info['chakra_cost']
    
    # --- CHANGE: Pass full player dicts to damage func ---
    damage_data = gl.calculate_damage(attacker, defender, jutsu_info)
    damage, is_crit, is_super_eff = damage_data
    
    defender['current_hp'] -= damage
    
    await anim.battle_animation_flow(context, battle_state, attacker, defender, jutsu_info, damage_data)
    
    if defender['current_hp'] <= 0:
        await end_battle(context, battle_id, player_id, defender_id, chat_id, message_id)
    else:
        battle_state['turn'] = defender_id
        await send_battle_menu(context, battle_state, message_id)
    return
