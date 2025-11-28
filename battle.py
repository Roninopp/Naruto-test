"""
🔥 BATTLE.PY - Main Battle System (ALL BUGS FIXED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIXES:
1. ✅ Turn validation - Only current player can press buttons
2. ✅ Fixed battle_stance_callback error (removed item_key)
3. ✅ Added missing battle_predict_callback
"""

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
import battle_core as bc
import battle_actions as ba
import auto_register

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════
# GLOBAL STATE
# ═══════════════════════════════════════

ACTIVE_BATTLES = {}
BATTLE_INVITES = {}

# ═══════════════════════════════════════
# MENU FUNCTIONS
# ═══════════════════════════════════════

async def send_battle_menu(context: ContextTypes.DEFAULT_TYPE, battle_state, message_id=None):
    """Send battle action menu"""
    turn_player_id = battle_state['turn']
    text = bc.get_enhanced_battle_display(battle_state)
    
    battle_state['base_text'] = text
    
    keyboard = [
        [
            InlineKeyboardButton("👊 Taijutsu", callback_data=f"battle_action_taijutsu_{turn_player_id}"),
            InlineKeyboardButton("🌀 Jutsu", callback_data=f"battle_action_jutsu_{turn_player_id}")
        ],
        [
            InlineKeyboardButton("🎯 Predict", callback_data=f"battle_action_predict_{turn_player_id}"),
            InlineKeyboardButton("🧪 Item", callback_data=f"battle_action_item_{turn_player_id}")
        ],
        [
            InlineKeyboardButton("⚔️ Aggressive", callback_data=f"battle_stance_aggressive_{turn_player_id}"),
            InlineKeyboardButton("🛡️ Defensive", callback_data=f"battle_stance_defensive_{turn_player_id}")
        ],
        [
            InlineKeyboardButton("⚖️ Balanced", callback_data=f"battle_stance_balanced_{turn_player_id}"),
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

# ═══════════════════════════════════════
# BATTLE END
# ═══════════════════════════════════════

async def end_battle(context: ContextTypes.DEFAULT_TYPE, battle_id, winner_id, loser_id, chat_id, message_id, fled=False):
    """End battle with full rewards"""
    battle_state = ACTIVE_BATTLES.pop(battle_id, None)
    if not battle_state:
        return
    
    winner = battle_state['players'][winner_id]
    loser = battle_state['players'][loser_id]
    
    if fled:
        result_text = f"🏃 <b>{loser['username']}</b> fled!\n<b>{winner['username']}</b> wins by forfeit!"
    else:
        result_text = f"🏆 <b>{winner['username']}</b> is VICTORIOUS!\n💀 {loser['username']} has been defeated!"
    
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=result_text,
        reply_markup=None,
        parse_mode="HTML"
    )
    
    cooldown_time = datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=bc.BATTLE_COOLDOWN_MINUTES)
    
    winner_exp_gain = loser['level'] * 10
    winner_ryo_gain = battle_state.get('winner_payout', loser['level'] * 20)
    
    achievements, bonus_ryo = bc.check_achievements(battle_state, winner_id, loser_id)
    winner_ryo_gain += bonus_ryo
    
    dropped, drop_key = bc.check_rare_drop()
    
    winner['wins'] += 1
    winner['battle_cooldown'] = cooldown_time
    winner['exp'] += winner_exp_gain
    winner['total_exp'] += winner_exp_gain
    winner['ryo'] += winner_ryo_gain
    
    if dropped:
        winner_inv = winner.get('inventory', [])
        winner_inv.append(drop_key)
        winner['inventory'] = winner_inv
    
    final_winner_data, leveled_up, level_messages = gl.check_for_level_up(winner)
    db.update_player(winner_id, final_winner_data)
    
    loser['losses'] += 1
    loser['battle_cooldown'] = cooldown_time
    loser_stats = gl.get_total_stats(loser)
    loser['max_hp'] = loser_stats['max_hp']
    loser['current_hp'] = 1
    
    loser_ryo_loss = battle_state.get('bet_amount', 0)
    loser['ryo'] = max(0, loser['ryo'] - loser_ryo_loss)
    
    db.update_player(loser_id, {
        'losses': loser['losses'],
        'battle_cooldown': loser['battle_cooldown'].isoformat(),
        'current_hp': loser['current_hp'],
        'max_hp': loser['max_hp'],
        'ryo': loser['ryo']
    })
    
    reward_text = "\n\n<b>🎁 BATTLE REWARDS</b>\n"
    reward_text += "━━━━━━━━━━━━━━━━\n"
    reward_text += f"💰 <b>{winner_ryo_gain:,} Ryo</b>\n"
    reward_text += f"⭐ <b>+{winner_exp_gain} EXP</b>\n"
    
    if achievements:
        reward_text += "\n<b>🏆 ACHIEVEMENTS UNLOCKED:</b>\n"
        for ach in achievements:
            reward_text += f"{ach['emoji']} <b>{ach['name']}</b> (+{ach['bonus_ryo']:,} Ryo)\n"
    
    if dropped:
        item_name = gl.SHOP_INVENTORY.get(drop_key, {}).get('name', 'Mystery Item')
        reward_text += f"\n✨ <b>RARE DROP:</b> {item_name}!"
    
    if leveled_up:
        reward_text += "\n\n" + "\n".join(level_messages)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=reward_text,
        parse_mode="HTML"
    )

# ═══════════════════════════════════════
# /BATTLE COMMAND
# ═══════════════════════════════════════

async def battle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main battle command with mandatory betting"""
    challenger_user = update.effective_user
    
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚔️ <b>BATTLE CHALLENGE</b>\n\n"
            "Reply to a user and type:\n"
            "<code>/battle [amount]</code>\n\n"
            "<b>Example:</b> <code>/battle 500</code>",
            parse_mode="HTML"
        )
        return
    
    challenged_user = update.message.reply_to_message.from_user
    
    if challenged_user.is_bot or challenged_user.id == challenger_user.id:
        await update.message.reply_text("❌ Invalid opponent.")
        return
    
    p1 = auto_register.ensure_player_exists(challenger_user.id, challenger_user.username or challenger_user.first_name)
    p2 = auto_register.ensure_player_exists(challenged_user.id, challenged_user.username or challenged_user.first_name)
    
    if not p1 or not p2:
        await update.message.reply_text("❌ Registration failed. Try again.")
        return
    
    hosp1, rem1 = gl.get_hospital_status(p1)
    hosp2, _ = gl.get_hospital_status(p2)
    
    if hosp1:
        await update.message.reply_text(f"🏥 You are in the hospital! Wait {int(rem1/60)}m.")
        return
    
    if hosp2:
        await update.message.reply_text(f"🏥 {p2['username']} is in the hospital.")
        return
    
    if any(str(p1['user_id']) in bid for bid in ACTIVE_BATTLES) or \
       any(str(p2['user_id']) in bid for bid in ACTIVE_BATTLES):
        await update.message.reply_text("⚔️ One of you is already in a battle.")
        return
    
    args = context.args
    if not args:
        min_bet, max_bet = bc.get_betting_limit(min(p1['level'], p2['level']))
        await update.message.reply_text(
            f"💰 <b>BET AMOUNT REQUIRED!</b>\n\n"
            f"Usage: <code>/battle [amount]</code>\n\n"
            f"<b>Your limits:</b>\n"
            f"Min: {min_bet:,} Ryo\n"
            f"Max: {max_bet:,} Ryo",
            parse_mode="HTML"
        )
        return
    
    try:
        bet_amount = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid bet amount.")
        return
    
    min_bet, max_bet = bc.get_betting_limit(min(p1['level'], p2['level']))
    
    if bet_amount < min_bet:
        await update.message.reply_text(f"❌ Minimum bet: {min_bet:,} Ryo")
        return
    
    if bet_amount > max_bet:
        await update.message.reply_text(f"❌ Maximum bet: {max_bet:,} Ryo")
        return
    
    if p1['ryo'] < bet_amount:
        await update.message.reply_text(f"💸 You need {bet_amount:,} Ryo! (You have: {p1['ryo']:,})")
        return
    
    if p2['ryo'] < bet_amount:
        await update.message.reply_text(f"💸 {p2['username']} can't afford this bet!")
        return
    
    total_pot, house_fee, winner_payout = bc.calculate_pot(bet_amount)
    
    BATTLE_INVITES[p2['user_id']] = {
        'challenger_id': p1['user_id'],
        'bet_amount': bet_amount,
        'total_pot': total_pot,
        'house_fee': house_fee,
        'winner_payout': winner_payout,
        'timestamp': datetime.datetime.now(timezone.utc)
    }
    
    text = (
        f"⚔️ <b>BATTLE CHALLENGE!</b> ⚔️\n\n"
        f"<b>{p1['username']}</b> challenges <b>{p2['username']}</b>!\n\n"
        f"💰 <b>Bet:</b> {bet_amount:,} Ryo each\n"
        f"🏆 <b>Pot:</b> {total_pot:,} Ryo\n"
        f"💵 <b>Winner gets:</b> {winner_payout:,} Ryo\n"
        f"<i>(10% house fee: {house_fee:,} Ryo)</i>\n\n"
        f"⚠️ <b>WARNING:</b> Loser loses their bet!"
    )
    
    keyboard = [[
        InlineKeyboardButton("✅ Accept", callback_data=f"battle_invite_accept_{p1['user_id']}"),
        InlineKeyboardButton("❌ Decline", callback_data=f"battle_invite_decline_{p1['user_id']}")
    ]]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

# ═══════════════════════════════════════
# BATTLE INVITE CALLBACK
# ═══════════════════════════════════════

async def battle_invite_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle invite accept/decline"""
    query = update.callback_query
    
    parts = query.data.split('_')
    action = parts[2]
    challenger_id = int(parts[3])
    challenged_id = query.from_user.id
    
    invite_data = BATTLE_INVITES.get(challenged_id)
    if not invite_data or invite_data['challenger_id'] != challenger_id:
        await query.answer("⏳ Invite expired!", show_alert=True)
        await query.edit_message_text("⏳ Invite expired.", reply_markup=None)
        return
    
    invite_time = invite_data.get('timestamp')
    if invite_time:
        now = datetime.datetime.now(timezone.utc)
        elapsed_minutes = (now - invite_time).total_seconds() / 60
        if elapsed_minutes > bc.INVITE_TIMEOUT_MINUTES:
            BATTLE_INVITES.pop(challenged_id, None)
            await query.answer("⏰ Invite expired!", show_alert=True)
            await query.edit_message_text(
                f"⏰ <b>INVITE EXPIRED!</b>\n\nThis challenge timed out after {bc.INVITE_TIMEOUT_MINUTES} minutes.",
                reply_markup=None,
                parse_mode="HTML"
            )
            return
    
    await query.answer()
    BATTLE_INVITES.pop(challenged_id)
    
    if action == "decline":
        await query.edit_message_text("❌ Battle declined.", reply_markup=None)
        return
    
    challenger = db.get_player(challenger_id)
    challenged = db.get_player(challenged_id)
    
    if not challenger or not challenged:
        await query.edit_message_text("❌ Player not found.", reply_markup=None)
        return
    
    p1 = dict(challenger)
    p2 = dict(challenged)
    
    p1['total_stats'] = gl.get_total_stats(p1)
    p2['total_stats'] = gl.get_total_stats(p2)
    
    if p1['total_stats']['speed'] > p2['total_stats']['speed']:
        turn_player_id = p1['user_id']
    elif p2['total_stats']['speed'] > p1['total_stats']['speed']:
        turn_player_id = p2['user_id']
    else:
        turn_player_id = random.choice([p1['user_id'], p2['user_id']])
    
    player_states = {
        p1['user_id']: {
            'stance': 'balanced',
            'combo': 0,
            'status_effects': {},
            'took_damage': False
        },
        p2['user_id']: {
            'stance': 'balanced',
            'combo': 0,
            'status_effects': {},
            'took_damage': False
        }
    }
    
    battle_id = f"{p1['user_id']}_vs_{p2['user_id']}"
    battle_state = {
        'players': {p1['user_id']: p1, p2['user_id']: p2},
        'player_states': player_states,
        'turn': turn_player_id,
        'turn_number': 1,
        'message_id': None,
        'chat_id': query.message.chat_id,
        'base_text': '',
        'bet_amount': invite_data['bet_amount'],
        'pot_amount': invite_data['total_pot'],
        'house_fee': invite_data['house_fee'],
        'winner_payout': invite_data['winner_payout'],
        'start_time': datetime.datetime.now(timezone.utc)
    }
    
    ACTIVE_BATTLES[battle_id] = battle_state
    
    ACTIVE_BATTLES[battle_id]['message_id'] = await send_battle_menu(
        context, battle_state, message_id=query.message.message_id
    )

# ═══════════════════════════════════════
# BATTLE ACTION CALLBACK
# ═══════════════════════════════════════

async def battle_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main action router"""
    query = update.callback_query
    parts = query.data.split('_')
    action = parts[2]
    player_id = int(parts[3])
    
    if query.from_user.id != player_id:
        await query.answer("⏳ Not your turn!", show_alert=True)
        return
    
    battle_id = next((bid for bid, bstate in ACTIVE_BATTLES.items() 
                      if player_id in bstate['players']), None)
    
    if not battle_id:
        await query.answer("Battle ended!", show_alert=True)
        await query.edit_message_text("⏳ Battle ended.", reply_markup=None)
        return
    
    battle_state = ACTIVE_BATTLES[battle_id]
    
    if battle_state['turn'] != player_id:
        await query.answer("⏳ Wait for your turn!", show_alert=True)
        return
    
    start_time = battle_state.get('start_time')
    if start_time:
        now = datetime.datetime.now(timezone.utc)
        elapsed_minutes = (now - start_time).total_seconds() / 60
        if elapsed_minutes > bc.BATTLE_TIMEOUT_MINUTES:
            ACTIVE_BATTLES.pop(battle_id)
            other_player_id = [pid for pid in battle_state['players'] if pid != player_id][0]
            await query.answer("Battle timed out!", show_alert=True)
            await query.edit_message_text(
                f"⏰ <b>BATTLE TIMEOUT!</b>\n\n"
                f"Battle exceeded {bc.BATTLE_TIMEOUT_MINUTES} minutes.\n"
                f"{battle_state['players'][player_id]['username']} forfeits due to inactivity!",
                reply_markup=None,
                parse_mode="HTML"
            )
            await end_battle(context, battle_id, other_player_id, player_id, 
                           battle_state['chat_id'], battle_state['message_id'], fled=True)
            return
    
    await query.answer()
    
    message_id = battle_state['message_id']
    chat_id = battle_state['chat_id']
    defender_id = [pid for pid in battle_state['players'] if pid != player_id][0]
    
    if action == "taijutsu":
        result = await ba.execute_taijutsu(context, battle_state, player_id, defender_id, message_id)
    
    elif action == "flee":
        result = await ba.attempt_flee(context, battle_state, player_id, message_id)
    
    elif action == "jutsu":
        attacker = battle_state['players'][player_id]
        known_jutsus = attacker.get('known_jutsus', [])
        
        if not known_jutsus:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"{battle_state['base_text']}\n\n<i>❌ You don't know any jutsus!</i>",
                parse_mode="HTML"
            )
            await asyncio.sleep(1.5)
            await send_battle_menu(context, battle_state, message_id)
            return
        
        keyboard = []
        for jutsu_key in known_jutsus:
            jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_key)
            if jutsu_info:
                button_text = f"{jutsu_info['name']} ({jutsu_info['chakra_cost']} ⚡)"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"battle_jutsu_{player_id}_{jutsu_key}")])
        
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"battle_jutsu_{player_id}_cancel")])
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"{battle_state['base_text']}\n\n<b>Select a Jutsu:</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return
    
    elif action == "item":
        attacker = battle_state['players'][player_id]
        inventory = attacker.get('inventory', [])
        
        if not inventory:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"{battle_state['base_text']}\n\n<i>❌ Inventory empty!</i>",
                parse_mode="HTML"
            )
            await asyncio.sleep(1.5)
            await send_battle_menu(context, battle_state, message_id)
            return
        
        item_counts = Counter(inventory)
        
        keyboard = []
        for item_key, count in item_counts.items():
            item_info = gl.SHOP_INVENTORY.get(item_key)
            if item_info and item_info['type'] == 'consumable':
                button_text = f"{item_info['name']} (x{count})"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"battle_item_{player_id}_{item_key}")])
        
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"battle_item_{player_id}_cancel")])
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"{battle_state['base_text']}\n\n<b>Select an Item:</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return
    
    elif action == "predict":
        result = await ba.initiate_prediction(context, battle_state, player_id, message_id)
        return
    
    else:
        result = 'continue'
    
    if result == 'ko':
        await end_battle(context, battle_id, player_id, defender_id, chat_id, message_id)
    elif result == 'fled':
        await end_battle(context, battle_id, defender_id, player_id, chat_id, message_id, fled=True)
    elif result == 'draw':
        ACTIVE_BATTLES.pop(battle_id)
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="⏱️ <b>DRAW!</b> Battle reached max turns. Both fighters walk away.",
            parse_mode="HTML",
            reply_markup=None
        )
    elif result == 'continue':
        await send_battle_menu(context, battle_state, message_id)

# ═══════════════════════════════════════
# STANCE CALLBACK - FIXED
# ═══════════════════════════════════════

async def battle_stance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle stance switching"""
    query = update.callback_query
    parts = query.data.split('_')
    stance = parts[2]
    player_id = int(parts[3])
    
    if query.from_user.id != player_id:
        await query.answer("⏳ Not your turn!", show_alert=True)
        return
    
    battle_id = next((bid for bid, bstate in ACTIVE_BATTLES.items() 
                      if player_id in bstate['players']), None)
    
    if not battle_id:
        await query.answer("Battle ended!", show_alert=True)
        return
    
    battle_state = ACTIVE_BATTLES[battle_id]
    
    if battle_state['turn'] != player_id:
        await query.answer("⏳ Wait for your turn!", show_alert=True)
        return
    
    await query.answer()
    
    result = await ba.switch_stance(context, battle_state, player_id, stance, battle_state['message_id'])
    
    if result == 'continue':
        await send_battle_menu(context, battle_state, battle_state['message_id'])

# ═══════════════════════════════════════
# JUTSU CALLBACK
# ═══════════════════════════════════════

async def battle_jutsu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle jutsu selection"""
    query = update.callback_query
    parts = query.data.split('_')
    player_id = int(parts[2])
    jutsu_key = "_".join(parts[3:])
    
    if query.from_user.id != player_id:
        await query.answer("⏳ Not your turn!", show_alert=True)
        return
    
    battle_id = next((bid for bid, bstate in ACTIVE_BATTLES.items() 
                      if player_id in bstate['players']), None)
    
    if not battle_id:
        await query.answer("Battle ended!", show_alert=True)
        return
    
    battle_state = ACTIVE_BATTLES[battle_id]
    
    if battle_state['turn'] != player_id:
        await query.answer("⏳ Wait for your turn!", show_alert=True)
        return
    
    await query.answer()
    
    if jutsu_key == "cancel":
        await send_battle_menu(context, battle_state, battle_state['message_id'])
        return
    
    defender_id = [pid for pid in battle_state['players'] if pid != player_id][0]
    
    result = await ba.execute_jutsu(context, battle_state, player_id, defender_id, jutsu_key, battle_state['message_id'])
    
    if result == 'ko':
        await end_battle(context, battle_id, player_id, defender_id, battle_state['chat_id'], battle_state['message_id'])
    elif result == 'continue':
        await send_battle_menu(context, battle_state, battle_state['message_id'])

# ═══════════════════════════════════════
# ITEM CALLBACK
# ═══════════════════════════════════════

async def battle_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle item usage"""
    query = update.callback_query
    parts = query.data.split('_')
    player_id = int(parts[2])
    item_key = "_".join(parts[3:])
    
    if query.from_user.id != player_id:
        await query.answer("⏳ Not your turn!", show_alert=True)
        return
    
    battle_id = next((bid for bid, bstate in ACTIVE_BATTLES.items() 
                      if player_id in bstate['players']), None)
    
    if not battle_id:
        await query.answer("Battle ended!", show_alert=True)
        return
    
    battle_state = ACTIVE_BATTLES[battle_id]
    
    if battle_state['turn'] != player_id:
        await query.answer("⏳ Wait for your turn!", show_alert=True)
        return
    
    await query.answer()
    
    if item_key == "cancel":
        await send_battle_menu(context, battle_state, battle_state['message_id'])
        return
    
    result = await ba.execute_item(context, battle_state, player_id, item_key, battle_state['message_id'])
    
    if result == 'continue':
        await send_battle_menu(context, battle_state, battle_state['message_id'])

# ═══════════════════════════════════════
# PREDICT CALLBACK - NEW!
# ═══════════════════════════════════════

async def battle_predict_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle prediction selection"""
    query = update.callback_query
    parts = query.data.split('_')
    predicted_action = parts[1]  # taijutsu, jutsu, item
    player_id = int(parts[2])
    
    if query.from_user.id != player_id:
        await query.answer("⏳ Not your turn!", show_alert=True)
        return
    
    battle_id = next((bid for bid, bstate in ACTIVE_BATTLES.items() 
                      if player_id in bstate['players']), None)
    
    if not battle_id:
        await query.answer("Battle ended!", show_alert=True)
        return
    
    battle_state = ACTIVE_BATTLES[battle_id]
    
    if battle_state['turn'] != player_id:
        await query.answer("⏳ Wait for your turn!", show_alert=True)
        return
    
    await query.answer()
    
    if predicted_action == "cancel":
        await send_battle_menu(context, battle_state, battle_state['message_id'])
        return
    
    # Store the prediction
    battle_state['prediction_guess'] = predicted_action
    battle_state['predictor_id'] = player_id
    
    # Get opponent ID
    opponent_id = [pid for pid in battle_state['players'] if pid != player_id][0]
    
    # Show waiting message
    text = f"{battle_state['base_text']}\n\n"
    text += f"<b>🎯 {battle_state['players'][player_id]['username']} is reading opponent's moves...</b>\n\n"
    text += f"<i>Waiting for {battle_state['players'][opponent_id]['username']}'s action...</i>"
    
    await context.bot.edit_message_text(
        chat_id=battle_state['chat_id'],
        message_id=battle_state['message_id'],
        text=text,
        parse_mode="HTML"
    )
    await asyncio.sleep(1.5)
    
    # Switch turn to opponent - they must now act
    battle_state['turn'] = opponent_id
    await send_battle_menu(context, battle_state, battle_state['message_id'])
