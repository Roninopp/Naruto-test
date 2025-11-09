import logging
import json
import datetime
import asyncio
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from collections import Counter 
from datetime import timezone

import database as db
import game_logic as gl
import animations as anim 

logger = logging.getLogger(__name__)

ACTIVE_BATTLES = {}
BATTLE_INVITES = {}
BATTLE_COOLDOWN_MINUTES = 5

# --- NEW: Quick Fight Constants ---
FIGHT_INVITES = {} 
FIGHT_HOSPITAL_MINUTES = 30
FIGHT_WIN_RYO_PERCENT = 0.05

# --- Helper Functions ---
def get_battle_text(players, turn_player_id):
    player_ids = list(players.keys())
    if player_ids[0] < player_ids[1]: p1 = players[player_ids[0]]; p2 = players[player_ids[1]]
    else: p1 = players[player_ids[1]]; p2 = players[player_ids[0]]
    p1_total_stats = gl.get_total_stats(p1); p2_total_stats = gl.get_total_stats(p2)
    attacker = p1 if turn_player_id == p1['user_id'] else p2
    return (f"⚔️ <b>BATTLE!</b> ⚔️\n\n" f"<b>{p1['username']}</b> [Lvl {p1['level']}]\n" f"HP: {gl.health_bar(p1['current_hp'], p1_total_stats['max_hp'])}\n\n" f"<b>{p2['username']}</b> [Lvl {p2['level']}]\n" f"HP: {gl.health_bar(p2['current_hp'], p2_total_stats['max_hp'])}\n\n" f"<b>Turn: {attacker['username']}</b>\n" "Choose your action:")

async def send_battle_menu(context: ContextTypes.DEFAULT_TYPE, battle_state, message_id=None):
    players = battle_state['players']; turn_player_id = battle_state['turn']
    text = get_battle_text(players, turn_player_id)
    battle_state['base_text'] = text.split("\n\n<b>Turn:")[0] 
    keyboard = [[InlineKeyboardButton("⚔️ Taijutsu", callback_data=f"battle_action_taijutsu_{turn_player_id}"), InlineKeyboardButton("🌀 Use Jutsu", callback_data=f"battle_action_jutsu_{turn_player_id}")], [InlineKeyboardButton("🧪 Use Item", callback_data=f"battle_action_item_{turn_player_id}"), InlineKeyboardButton("🏃 Flee", callback_data=f"battle_action_flee_{turn_player_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        if message_id: await context.bot.edit_message_text(chat_id=battle_state['chat_id'], message_id=message_id, text=text, reply_markup=reply_markup, parse_mode="HTML"); return message_id
        else: message = await context.bot.send_message(chat_id=battle_state['chat_id'], text=text, reply_markup=reply_markup, parse_mode="HTML"); return message.message_id
    except Exception as e: logger.error(f"Error sending battle menu: {e}"); return message_id

async def end_battle(context: ContextTypes.DEFAULT_TYPE, battle_id, winner_id, loser_id, chat_id, message_id, fled=False):
    battle_state = ACTIVE_BATTLES.pop(battle_id, None)
    if not battle_state: return
    winner = battle_state['players'][winner_id]; loser = battle_state['players'][loser_id]
    text = f"🏃 <b>{loser['username']}</b> fled the battle! <b>{winner['username']}</b> wins by default!" if fled else f"🏆 <b>{winner['username']}</b> is victorious! 🏆\n{loser['username']} has been defeated."
    await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=None, parse_mode="HTML")
    cooldown_time = (datetime.datetime.now() + datetime.timedelta(minutes=BATTLE_COOLDOWN_MINUTES)).isoformat()
    winner_exp_gain = loser['level'] * 10; winner_ryo_gain = loser['level'] * 20
    winner['wins'] += 1; winner['battle_cooldown'] = cooldown_time; winner['exp'] += winner_exp_gain; winner['total_exp'] += winner_exp_gain; winner['ryo'] += winner_ryo_gain
    final_winner_data, leveled_up, messages = gl.check_for_level_up(winner)
    db.update_player(winner_id, final_winner_data)
    loser['losses'] += 1; loser['battle_cooldown'] = cooldown_time; loser_total_stats = gl.get_total_stats(loser); loser['max_hp'] = loser_total_stats['max_hp']; loser['current_hp'] = 1 
    db.update_player(loser_id, {'losses': loser['losses'], 'battle_cooldown': loser['battle_cooldown'], 'current_hp': loser['current_hp'], 'max_hp': loser['max_hp']})
    reward_text = f"<b>{winner['username']}</b> gained +{winner_exp_gain} EXP and +{winner_ryo_gain} Ryo!"
    if leveled_up: reward_text += "\n\n" + "\n".join(messages)
    await context.bot.send_message(chat_id=chat_id, text=reward_text, parse_mode="HTML")

# --- NEW: /fight (Quick RPS Duel) ---
async def fight_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick Rock-Paper-Scissors duel with stat tie-breakers."""
    challenger = update.effective_user
    if not update.message.reply_to_message: await update.message.reply_text("Reply to the user you want to fight."); return
    opponent = update.message.reply_to_message.from_user
    if opponent.is_bot or opponent.id == challenger.id: await update.message.reply_text("Invalid opponent."); return
    p1 = db.get_player(challenger.id); p2 = db.get_player(opponent.id)
    if not p1: await update.message.reply_text(f"{challenger.mention_html()}, please /register first!", parse_mode="HTML"); return
    if not p2: await update.message.reply_text(f"{opponent.mention_html()} is not registered.", parse_mode="HTML"); return

    h1, r1 = gl.get_hospital_status(p1); h2, r2 = gl.get_hospital_status(p2)
    if h1: await update.message.reply_text(f"🏥 You are in the hospital! Wait {r1/60:.0f}m."); return
    if h2: await update.message.reply_text(f"🏥 {opponent.mention_html()} is in the hospital."); return

    inv = p1.get('inventory') or []
    # Handle both string (old cache) and list (new db) formats for safety
    if isinstance(inv, str): inv = json.loads(inv)
    
    if 'soldier_pill' not in inv:
        await update.message.reply_text("🚫 You need a **💊 Soldier Pill** to start a fight! Buy one in the /shop.", parse_mode="HTML")
        return

    FIGHT_INVITES[opponent.id] = challenger.id
    keyboard = [[InlineKeyboardButton("⚔️ ACCEPT DUEL", callback_data=f"fight_accept_{challenger.id}")]]
    await update.message.reply_text(
        f"⚔️ **QUICK DUEL CHALLENGE!** ⚔️\n\n{challenger.mention_html()} has challenged {opponent.mention_html()} to a fight!\nLoser goes to the hospital for 30 minutes.",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )

async def fight_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; user = query.from_user
    challenger_id = int(query.data.split('_')[2])
    if FIGHT_INVITES.get(user.id) != challenger_id: await query.answer("Invite expired or not for you.", show_alert=True); return
    del FIGHT_INVITES[user.id]
    
    p1 = db.get_player(challenger_id)
    inv = p1.get('inventory') or []
    if isinstance(inv, str): inv = json.loads(inv)
    
    if 'soldier_pill' in inv:
        inv.remove('soldier_pill')
        db.update_player(challenger_id, {'inventory': json.dumps(inv)})
    
    keyboard = [
        [InlineKeyboardButton("👊 Taijutsu", callback_data=f"fight_pick_{challenger_id}_{user.id}_taijutsu")],
        [InlineKeyboardButton("🖐️ Genjutsu", callback_data=f"fight_pick_{challenger_id}_{user.id}_genjutsu")],
        [InlineKeyboardButton("✌️ Ninjutsu", callback_data=f"fight_pick_{challenger_id}_{user.id}_ninjutsu")]
    ]
    await query.edit_message_text(
        f"⚔️ **DUEL STARTED!** ⚔️\n\n{p1['username']} VS {user.first_name}\n\nChoose your tactic secretly:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.bot_data[f"duel_{challenger_id}_{user.id}"] = {}

async def fight_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split('_')
    p1_id = int(parts[2]); p2_id = int(parts[3]); choice = parts[4]
    duel_key = f"duel_{p1_id}_{p2_id}"
    
    if query.from_user.id not in [p1_id, p2_id]: await query.answer("Not your fight!", show_alert=True); return
    duel_data = context.bot_data.get(duel_key)
    if duel_data is None: await query.answer("Duel expired."); return
    if query.from_user.id in duel_data: await query.answer("You already chose!", show_alert=True); return
        
    duel_data[query.from_user.id] = choice
    await query.answer("Tactic chosen!")
    
    if len(duel_data) == 2:
        await resolve_fight(update, context, p1_id, p2_id, duel_data)
        del context.bot_data[duel_key]

async def resolve_fight(update: Update, context: ContextTypes.DEFAULT_TYPE, p1_id, p2_id, choices):
    p1 = db.get_player(p1_id); p2 = db.get_player(p2_id)
    c1 = choices[p1_id]; c2 = choices[p2_id]
    s1 = gl.get_total_stats(p1); s2 = gl.get_total_stats(p2)
    winner_id = None; reason = ""
    
    if c1 == c2:
        if c1 == 'taijutsu':
            winner_id = p1_id if s1['strength'] >= s2['strength'] else p2_id
            reason = f"Both chose Taijutsu, but <b>{db.get_player(winner_id)['username']}</b> was stronger!"
        elif c1 == 'ninjutsu':
            winner_id = p1_id if s1['intelligence'] >= s2['intelligence'] else p2_id
            reason = f"Both chose Ninjutsu, but <b>{db.get_player(winner_id)['username']}</b> had more chakra control!"
        else:
            winner_id = p1_id if s1['speed'] >= s2['speed'] else p2_id
            reason = f"Both chose Genjutsu, but <b>{db.get_player(winner_id)['username']}</b> was faster!"
    elif (c1 == 'taijutsu' and c2 == 'genjutsu') or (c1 == 'genjutsu' and c2 == 'ninjutsu') or (c1 == 'ninjutsu' and c2 == 'taijutsu'):
        winner_id = p1_id; reason = f"{c1.title()} beats {c2.title()}!"
    else:
        winner_id = p2_id; reason = f"{c2.title()} beats {c1.title()}!"
        
    loser_id = p1_id if winner_id == p2_id else p2_id
    winner = p1 if winner_id == p1_id else p2
    loser = p2 if winner_id == p1_id else p1
    
    ryo_steal = int(loser['ryo'] * FIGHT_WIN_RYO_PERCENT)
    hospital_until = datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=FIGHT_HOSPITAL_MINUTES)
    
    db.update_player(winner_id, {'ryo': winner['ryo'] + ryo_steal, 'wins': winner['wins'] + 1})
    db.update_player(loser_id, {'ryo': loser['ryo'] - ryo_steal, 'losses': loser['losses'] + 1, 'hospitalized_until': hospital_until.isoformat()})

    res_text = (f"⚔️ **DUEL FINISHED!** ⚔️\n\n<b>{p1['username']}:</b> {c1.title()}\n<b>{p2['username']}:</b> {c2.title()}\n\n🏆 <b>WINNER: {winner['username']}!</b>\n<i>{reason}</i>\n\n💰 Stole: **{ryo_steal} Ryo**\n🏥 {loser['username']} is hospitalized for 30m!")
    await update.callback_query.edit_message_text(res_text, parse_mode="HTML")

# --- OLD BATTLE COMMANDS ---
async def battle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    challenger_user = update.effective_user
    if not update.message.reply_to_message: await update.message.reply_text("To challenge someone, you must reply to one of their messages and type /battle."); return
    challenged_user = update.message.reply_to_message.from_user
    if challenged_user.is_bot or challenged_user.id == challenger_user.id: await update.message.reply_text("Invalid opponent."); return
    p1 = db.get_player(challenger_user.id); p2 = db.get_player(challenged_user.id)
    if not p1: await update.message.reply_text(f"{challenger_user.mention_html()}, please /register first!", parse_mode="HTML"); return
    if not p2: await update.message.reply_text(f"{challenged_user.mention_html()} is not registered.", parse_mode="HTML"); return
    hosp1, rem1 = gl.get_hospital_status(p1); hosp2, _ = gl.get_hospital_status(p2)
    if hosp1: await update.message.reply_text(f"🏥 You are in the hospital! Wait {rem1/60:.0f}m."); return
    if hosp2: await update.message.reply_text(f"🏥 {p2['username']} is in the hospital."); return
    if any(str(p1['user_id']) in bid for bid in ACTIVE_BATTLES) or any(str(p2['user_id']) in bid for bid in ACTIVE_BATTLES): await update.message.reply_text("One of the players is already in a battle."); return
    if p1['user_id'] in BATTLE_INVITES.values() or p2['user_id'] in BATTLE_INVITES: await update.message.reply_text("One of the players already has a pending battle invite."); return
    now = datetime.datetime.now(timezone.utc)
    for player in [p1, p2]:
        if player['battle_cooldown']:
            cooldown_time = player['battle_cooldown']
            if cooldown_time.tzinfo is None: cooldown_time = cooldown_time.replace(tzinfo=timezone.utc)
            if now < cooldown_time: await update.message.reply_text(f"{player['username']} is on battle cooldown for {(cooldown_time - now).seconds // 60 + 1} more minute(s)."); return
    BATTLE_INVITES[p2['user_id']] = p1['user_id']
    text = f"<b>{p2['username']}!</b>\n{p1['username']} has challenged you to a battle!"
    keyboard = [[InlineKeyboardButton("✅ Accept", callback_data=f"battle_invite_accept_{p1['user_id']}"), InlineKeyboardButton("❌ Decline", callback_data=f"battle_invite_decline_{p1['user_id']}")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def battle_invite_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    parts = query.data.split('_'); action = parts[2]; challenger_id = int(parts[3]); challenged_id = query.from_user.id
    if BATTLE_INVITES.get(challenged_id) != challenger_id: await query.edit_message_text("This battle invite has expired.", reply_markup=None); return
    BATTLE_INVITES.pop(challenged_id)
    if action == "decline": await query.edit_message_text("Battle declined.", reply_markup=None); return
    challenger = db.get_player(challenger_id); challenged = db.get_player(challenged_id)
    if not challenger or not challenged: await query.edit_message_text("Error: Player not found.", reply_markup=None); return
    hosp1, _ = gl.get_hospital_status(challenger); hosp2, _ = gl.get_hospital_status(challenged)
    if hosp1 or hosp2: await query.edit_message_text("🏥 Battle cancelled: One of the players is hospitalized.", reply_markup=None); return
    p1 = dict(challenger); p2 = dict(challenged)
    p1['total_stats'] = gl.get_total_stats(p1); p2['total_stats'] = gl.get_total_stats(p2)
    turn_player_id = p1['user_id'] if p1['total_stats']['speed'] > p2['total_stats']['speed'] else p2['user_id'] if p2['total_stats']['speed'] > p1['total_stats']['speed'] else random.choice([p1['user_id'], p2['user_id']])
    battle_id = f"{p1['user_id']}_vs_{p2['user_id']}"; battle_state = {'players': {p1['user_id']: p1, p2['user_id']: p2}, 'turn': turn_player_id, 'message_id': None, 'chat_id': query.message.chat_id, 'base_text': '' }
    ACTIVE_BATTLES[battle_id] = battle_state
    ACTIVE_BATTLES[battle_id]['message_id'] = await send_battle_menu(context, battle_state, message_id=query.message.message_id)

async def battle_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split('_'); action = parts[2]; player_id = int(parts[3])
    battle_id = next((bid for bid, bstate in ACTIVE_BATTLES.items() if player_id in bstate['players']), None)
    if not battle_id: await query.answer(); await query.edit_message_text("Battle ended.", reply_markup=None); return
    battle_state = ACTIVE_BATTLES[battle_id]
    if battle_state['turn'] != player_id: await query.answer("Not your turn!", show_alert=True); return
    attacker = battle_state['players'][player_id]; defender_id = [pid for pid in battle_state['players'] if pid != player_id][0]; defender = battle_state['players'][defender_id]
    chat_id = battle_state['chat_id']; message_id = battle_state['message_id']
    
    if action == "flee":
        await query.answer(); await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\n<i>Processing turn...</i>", reply_markup=None)
        if random.random() < 0.5: await end_battle(context, battle_id, defender_id, player_id, chat_id, message_id, fled=True)
        else: await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\n<i>{attacker['username']} tried to flee but failed!</i>"); await asyncio.sleep(2); battle_state['turn'] = defender_id; await send_battle_menu(context, battle_state, message_id)
        return
    if action == "taijutsu":
        await query.answer(); await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\n<i>Processing turn...</i>", reply_markup=None)
        damage, is_crit = gl.calculate_taijutsu_damage(attacker, defender); defender['current_hp'] -= damage
        await anim.animate_taijutsu(context, battle_state, attacker, defender, damage, is_crit)
        if defender['current_hp'] <= 0: await end_battle(context, battle_id, player_id, defender_id, chat_id, message_id)
        else: battle_state['turn'] = defender_id; await send_battle_menu(context, battle_state, message_id)
        return
    if action == "jutsu":
        if attacker['level'] < gl.JUTSU_LIBRARY['fireball']['level_required']: await query.answer("Level 5+ required for jutsus!", show_alert=True); return
        known_jutsus = json.loads(attacker['known_jutsus']) if isinstance(attacker['known_jutsus'], str) else attacker.get('known_jutsus', [])
        if not known_jutsus: await query.answer("You don't know any jutsus!", show_alert=True); return
        await query.answer(); await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\n<i>Processing turn...</i>", reply_markup=None)
        keyboard = [[InlineKeyboardButton(f"{gl.JUTSU_LIBRARY.get(k)['name']} ({gl.JUTSU_LIBRARY.get(k)['chakra_cost']})", callback_data=f"battle_jutsu_{player_id}_{k}")] for k in known_jutsus if gl.JUTSU_LIBRARY.get(k)]
        keyboard.append([InlineKeyboardButton("Cancel", callback_data=f"battle_jutsu_{player_id}_cancel")])
        await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\nSelect a Jutsu:", reply_markup=InlineKeyboardMarkup(keyboard)); return
    if action == "item":
        inventory_list = json.loads(attacker['inventory']) if isinstance(attacker['inventory'], str) else attacker.get('inventory', [])
        if not inventory_list: await query.answer("Inventory empty!", show_alert=True); return
        usable_items = {k: gl.SHOP_INVENTORY.get(k) for k, count in Counter(inventory_list).items() if gl.SHOP_INVENTORY.get(k) and gl.SHOP_INVENTORY.get(k)['type'] == 'consumable'}
        if not usable_items: await query.answer("No usable items!", show_alert=True); return
        await query.answer(); await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\n<i>Processing turn...</i>", reply_markup=None)
        keyboard = [[InlineKeyboardButton(f"{info['name']} (x{Counter(inventory_list)[k]})", callback_data=f"battle_item_{player_id}_{k}")] for k, info in usable_items.items()]
        keyboard.append([InlineKeyboardButton("Cancel", callback_data=f"battle_item_{player_id}_cancel")])
        await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\nSelect an item:", reply_markup=InlineKeyboardMarkup(keyboard)); return

async def battle_jutsu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; parts = query.data.split('_'); player_id = int(parts[2]); jutsu_key = "_".join(parts[3:])
    battle_id = next((bid for bid, bstate in ACTIVE_BATTLES.items() if player_id in bstate['players']), None)
    if not battle_id: await query.answer(); await query.edit_message_text("Battle ended.", reply_markup=None); return
    battle_state = ACTIVE_BATTLES[battle_id]
    if battle_state['turn'] != player_id: await query.answer("Not your turn!", show_alert=True); return
    chat_id = battle_state['chat_id']; message_id = battle_state['message_id']
    if jutsu_key == "cancel": await query.answer(); await send_battle_menu(context, battle_state, message_id); return
    attacker = battle_state['players'][player_id]; defender_id = [pid for pid in battle_state['players'] if pid != player_id][0]; defender = battle_state['players'][defender_id]
    jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_key)
    if not jutsu_info: await query.answer(); return
    if attacker['current_chakra'] < jutsu_info['chakra_cost']: await query.answer("Not enough chakra!", show_alert=True); return
    await query.answer(); await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\n<i>Processing turn...</i>", reply_markup=None)
    attacker['current_chakra'] -= jutsu_info['chakra_cost']; damage_data = gl.calculate_damage(attacker, defender, jutsu_info); defender['current_hp'] -= damage_data[0]
    await anim.battle_animation_flow(context, battle_state, attacker, defender, jutsu_info, damage_data)
    if defender['current_hp'] <= 0: await end_battle(context, battle_id, player_id, defender_id, chat_id, message_id)
    else: battle_state['turn'] = defender_id; await send_battle_menu(context, battle_state, message_id)

async def battle_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; parts = query.data.split('_'); player_id = int(parts[2]); item_key = "_".join(parts[3:])
    battle_id = next((bid for bid, bstate in ACTIVE_BATTLES.items() if player_id in bstate['players']), None)
    if not battle_id: await query.answer(); await query.edit_message_text("Battle ended.", reply_markup=None); return
    battle_state = ACTIVE_BATTLES[battle_id]
    if battle_state['turn'] != player_id: await query.answer("Not your turn!", show_alert=True); return
    chat_id = battle_state['chat_id']; message_id = battle_state['message_id']
    if item_key == "cancel": await query.answer(); await send_battle_menu(context, battle_state, message_id); return
    attacker = battle_state['players'][player_id]; defender_id = [pid for pid in battle_state['players'] if pid != player_id][0]
    item_info = gl.SHOP_INVENTORY.get(item_key)
    if not item_info or item_info['type'] != 'consumable': await query.answer(); return
    inventory_list = json.loads(attacker['inventory']) if isinstance(attacker['inventory'], str) else attacker.get('inventory', [])
    if item_key not in inventory_list: await query.answer("Item not found!", show_alert=True); await send_battle_menu(context, battle_state, message_id); return
    await query.answer(); await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\n<i>Using {item_info['name']}...</i>", reply_markup=None)
    inventory_list.remove(item_key); updates_to_save = {'inventory': json.dumps(inventory_list)}
    if item_key == 'health_potion':
        heal_amount = item_info['stats']['heal']; max_hp = gl.get_total_stats(attacker)['max_hp']
        actual_heal = min(heal_amount, max_hp - attacker['current_hp'])
        if actual_heal <= 0: await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\n<i>HP already full!</i>"); await asyncio.sleep(2); await send_battle_menu(context, battle_state, message_id); return
        attacker['current_hp'] += actual_heal; updates_to_save['current_hp'] = attacker['current_hp']
        await anim.edit_battle_message(context, battle_state, f"{battle_state['base_text']}\n\n<i>🧪 Recovered {actual_heal} HP.</i>"); await asyncio.sleep(2.5)
    db.update_player(player_id, updates_to_save); battle_state['turn'] = defender_id; await send_battle_menu(context, battle_state, message_id)
