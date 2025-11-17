"""
🎮 MINIGAMES.PY - Core Criminal Activities
Handles: Steal, Scout, Kill, Heal, Gift, Protect, Wallet

Features:
- Heat system integration
- Reputation tracking
- Bounty rewards
- Escape mechanics
"""

import logging
import random
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatType
from telegram.error import BadRequest
from html import escape

import database as db
import game_logic as gl
import minigames_v2 as mgv2  # Import advanced systems

logger = logging.getLogger(__name__)

# --- CONSTANTS ---
STEAL_CHAKRA_COST = 15
STEAL_BASE_SUCCESS_CHANCE = 0.60
STEAL_BASE_FAIL_CHANCE = 0.10
STEAL_MAX_ROB_AMOUNT = 100
STEAL_FAIL_PENALTY = 20

SCOUT_COOLDOWN_MINUTES = 60
SCOUT_EXP_CHANCE = 0.05
SCOUT_RYO_CHANCE = 0.25
SCOUT_EXP_REWARD = 50
SCOUT_RYO_REWARD = 25

GIFT_TAX_PERCENT = 0.05

PROTECT_1D_COST = 500
PROTECT_3D_COST = 1300

KILL_CHAKRA_COST = 30
KILL_BASE_SUCCESS = 0.50
HOSPITAL_DURATION_HOURS = 24

HEAL_COST = 300

# Heat constants
HEAT_PER_ROB = 10
HEAT_PER_KILL = 25

async def safe_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text, parse_mode=None, reply_markup=None):
    try:
        await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except BadRequest:
        try:
            await context.bot.send_message(update.effective_chat.id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to send safe_reply: {e}")

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced wallet showing heat, bounty, and reputation."""
    user = update.effective_user
    target_user = user
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if target_user.is_bot:
            await safe_reply(update, context, "Bots don't have wallets!")
            return

    player = db.get_player(target_user.id)
    
    if not player:
        if target_user.id == user.id:
            await safe_reply(update, context, f"Hey {user.mention_html()}! Please /register first.", parse_mode="HTML")
        else:
            await safe_reply(update, context, f"<b>{escape(target_user.first_name)}</b> is not registered.", parse_mode="HTML")
        return

    is_hosp, _ = gl.get_hospital_status(player)
    status_text = "🏥 Hospitalized" if is_hosp else "❤️ Alive"
    
    # Get heat status
    heat_emoji, heat_text = mgv2.get_heat_status(player.get('heat_level', 0))
    
    # Get reputation
    rep_title = player.get('reputation_title')
    title_text = mgv2.REPUTATION_TITLES[rep_title]['name'] if rep_title in mgv2.REPUTATION_TITLES else "None"
    
    # Get bounty
    bounty = player.get('bounty', 0)
    
    wallet_text = (
        f"<b>--- 🥷 {escape(target_user.first_name)}'s Profile 🥷 ---</b>\n\n"
        f"<b>Rank:</b> {player['rank']}\n"
        f"<b>Level:</b> {player['level']}\n"
        f"<b>Ryo:</b> {player['ryo']:,} 💰\n\n"
        f"<b>⚔️ Combat Stats:</b>\n"
        f"├ Kills: {player.get('kills', 0)} ☠️\n"
        f"├ Wins: {player['wins']}\n"
        f"└ Losses: {player['losses']}\n\n"
        f"<b>🎯 Criminal Record:</b>\n"
        f"├ Bounty: {bounty:,} Ryo 💰\n"
        f"├ Heat: {heat_emoji} {player.get('heat_level', 0)}/100 ({heat_text})\n"
        f"└ Successful Robs: {player.get('total_steals', 0)}\n\n"
        f"<b>🏆 Reputation:</b>\n"
        f"├ Title: {title_text}\n"
        f"├ Points: {player.get('reputation_points', 0)}\n"
        f"└ Contracts Done: {player.get('contracts_completed', 0)}\n\n"
        f"<b>Status:</b> {status_text}"
    )
    
    await safe_reply(update, context, wallet_text, parse_mode="HTML")

async def steal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rob with heat system and escape mechanics."""
    user = update.effective_user
    chat = update.effective_chat
    
    if chat.type == ChatType.PRIVATE:
        await safe_reply(update, context, "You can only rob in group chats.")
        return
    
    if not update.message.reply_to_message:
        await safe_reply(update, context, "Reply to the user you want to rob and specify an amount. (e.g. /rob 70)")
        return
    
    victim_user = update.message.reply_to_message.from_user
    
    if victim_user.id == user.id or victim_user.is_bot:
        await safe_reply(update, context, "Invalid target.")
        return

    try:
        amount_to_steal = int(context.args[0])
    except (IndexError, ValueError):
        await safe_reply(update, context, "You must specify how much to rob! Usage: `/rob <amount>`")
        return
        
    if amount_to_steal > STEAL_MAX_ROB_AMOUNT:
        await safe_reply(update, context, f"You can only rob a maximum of **{STEAL_MAX_ROB_AMOUNT} Ryo** at a time.", parse_mode="HTML")
        return
    
    if amount_to_steal <= 0:
        await safe_reply(update, context, "You must rob a positive amount.")
        return

    stealer = db.get_player(user.id)
    victim = db.get_player(victim_user.id)
    
    if not stealer:
        await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML")
        return
    
    if not victim:
        await safe_reply(update, context, f"{victim_user.mention_html()} is not a registered ninja.", parse_mode="HTML")
        return
    
    is_hospitalized, remaining = gl.get_hospital_status(stealer)
    if is_hospitalized:
        await safe_reply(update, context, f"🏥 You are in the hospital! Wait {remaining/60:.0f}m or use /heal.")
        return

    if victim['ryo'] < amount_to_steal:
        await safe_reply(update, context, f"<b>{escape(victim_user.first_name)}</b> doesn't have that much Ryo! (They have {victim['ryo']} Ryo).", parse_mode="HTML")
        return
        
    now = datetime.datetime.now(datetime.timezone.utc)
    if victim.get('protection_until'):
        protect_time = victim['protection_until']
        if protect_time.tzinfo is None:
            protect_time = protect_time.replace(tzinfo=datetime.timezone.utc)
        if now < protect_time:
            await safe_reply(update, context, f"🛡️ **ATTEMPT FAILED!**\n{victim_user.mention_html()} is Protected By Black Anbu Guards!", parse_mode="HTML")
            return

    if stealer['current_chakra'] < STEAL_CHAKRA_COST:
        await safe_reply(update, context, f"🥵 You are too tired! You need **{STEAL_CHAKRA_COST} Chakra**.", parse_mode="HTML")
        return
    
    # Get reputation bonuses
    rep_bonuses = mgv2.get_reputation_bonuses(stealer)
    rob_success_bonus = rep_bonuses.get('rob_success', 0)
    rob_amount_bonus = rep_bonuses.get('rob_amount', 1.0)
    
    # Heat affects success
    heat_level = stealer.get('heat_level', 0)
    heat_penalty = heat_level * 0.003
    
    stealer_stats = gl.get_total_stats(stealer)
    
    fail_chance = max(0.05, STEAL_BASE_FAIL_CHANCE + heat_penalty - min(0.10, stealer_stats['speed'] * 0.005))
    success_chance = STEAL_BASE_SUCCESS_CHANCE + rob_success_bonus + min(0.20, stealer_stats['speed'] * 0.01) - heat_penalty
    
    roll = random.random()
    
    stealer_updates = {'current_chakra': stealer['current_chakra'] - STEAL_CHAKRA_COST}
    
    if roll < success_chance:
        # SUCCESS
        final_amount = int(amount_to_steal * rob_amount_bonus)
        
        # Heat multiplier
        heat_multiplier = mgv2.get_heat_multiplier(heat_level)
        final_amount = int(final_amount * heat_multiplier)
        
        # Update heat
        heat_updates = mgv2.update_heat(stealer, HEAT_PER_ROB)
        stealer_updates.update(heat_updates)
        stealer_updates['total_steals'] = stealer.get('total_steals', 0) + 1
        stealer_updates['reputation_points'] = stealer.get('reputation_points', 0) + 10
        
        db.update_player(user.id, stealer_updates)
        db.atomic_add_ryo(user.id, final_amount)
        db.atomic_add_ryo(victim_user.id, -final_amount)
        
        # Check for title
        new_title, title_info = mgv2.check_reputation_title({**stealer, **stealer_updates})
        title_text = f"\n\n🏆 <b>NEW TITLE!</b> {title_info['name']}" if new_title else ""
        if new_title:
            db.update_player(user.id, {'reputation_title': new_title})
        
        # Roll for loot
        loot_type, loot_key, loot_data = mgv2.roll_for_loot(stealer)
        loot_text = ""
        if loot_type == 'legendary':
            loot_text = f"\n✨ <b>LEGENDARY DROP!</b> {loot_data['name']}"
            items = stealer.get('legendary_items', [])
            items.append(loot_key)
            db.update_player(user.id, {'legendary_items': items})
        elif loot_type == 'rare':
            loot_text = f"\n🎁 Bonus: +{loot_data['amount']} Ryo"
            db.atomic_add_ryo(user.id, loot_data['amount'])
        
        heat_emoji, _ = mgv2.get_heat_status(heat_updates['heat_level'])
        
        success_msg = (
            f"✅ <b>ROB SUCCESS!</b> ✅\n\n"
            f"💰 Stolen: <b>{final_amount} Ryo</b>\n"
            f"🔥 Heat Bonus: x{heat_multiplier}\n"
            f"🚨 Heat: {heat_emoji} {heat_updates['heat_level']}/100\n"
            f"⭐ +10 Rep{title_text}{loot_text}"
        )
        await safe_reply(update, context, success_msg, parse_mode="HTML")
        
    elif roll < (success_chance + fail_chance):
        # CAUGHT - Escape options
        keyboard = [
            [InlineKeyboardButton("🏃 Run (Speed)", callback_data=f"escape_run_{user.id}")],
            [InlineKeyboardButton("⚔️ Fight (Risk)", callback_data=f"escape_fight_{user.id}")],
            [InlineKeyboardButton(f"💰 Bribe ({STEAL_FAIL_PENALTY * 2} Ryo)", callback_data=f"escape_bribe_{user.id}")]
        ]
        
        stealer_updates['total_steals_caught'] = stealer.get('total_steals_caught', 0) + 1
        heat_updates = mgv2.update_heat(stealer, HEAT_PER_ROB // 2)
        stealer_updates.update(heat_updates)
        db.update_player(user.id, stealer_updates)
        
        caught_msg = (
            f"🚨 <b>CAUGHT!</b> 🚨\n\n"
            f"Spotted by {escape(victim_user.first_name)}!\n\n"
            f"Choose wisely:\n"
            f"🏃 <b>Run</b> - 50%+ escape chance\n"
            f"⚔️ <b>Fight</b> - Win = 2x reward, Lose = 2x fine\n"
            f"💰 <b>Bribe</b> - Guaranteed escape"
        )
        
        await safe_reply(update, context, caught_msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        # NEUTRAL
        db.update_player(user.id, stealer_updates)
        await safe_reply(update, context, "Failed to find anything.")

async def scout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scout with reputation bonuses."""
    user = update.effective_user
    player = db.get_player(user.id)
    
    if not player:
        await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML")
        return
    
    hosp, rem = gl.get_hospital_status(player)
    if hosp:
        await safe_reply(update, context, f"🏥 You are in the hospital! Wait {rem/60:.0f}m or use /heal.")
        return
    
    now = datetime.datetime.now(datetime.timezone.utc)
    if player.get('scout_cooldown'):
        cd = player['scout_cooldown']
        if cd.tzinfo is None:
            cd = cd.replace(tzinfo=datetime.timezone.utc)
        if now < cd:
            await safe_reply(update, context, f"Scout again in {(cd - now).total_seconds()/60:.0f}m.")
            return
    
    # Reputation bonus
    rep_bonuses = mgv2.get_reputation_bonuses(player)
    scout_multiplier = rep_bonuses.get('scout_rewards', 1.0)
    
    player_updates = {'scout_cooldown': now + datetime.timedelta(minutes=SCOUT_COOLDOWN_MINUTES)}
    player_updates['total_scouts'] = player.get('total_scouts', 0) + 1
    player_updates['reputation_points'] = player.get('reputation_points', 0) + 5
    
    roll = random.random()
    
    if roll < SCOUT_EXP_CHANCE:
        exp_reward = int(SCOUT_EXP_REWARD * scout_multiplier)
        player_updates.update({
            'exp': player['exp'] + exp_reward,
            'total_exp': player['total_exp'] + exp_reward
        })
        db.update_player(user.id, player_updates)
        
        # Check title
        new_title, title_info = mgv2.check_reputation_title({**player, **player_updates})
        title_text = f"\n🏆 <b>NEW TITLE!</b> {title_info['name']}" if new_title else ""
        if new_title:
            db.update_player(user.id, {'reputation_title': new_title})
        
        await safe_reply(update, context, f"Found a hidden training ground! **+{exp_reward} EXP**! ⭐ +5 Rep{title_text}", parse_mode="HTML")
        
    elif roll < (SCOUT_EXP_CHANCE + SCOUT_RYO_CHANCE):
        ryo_reward = int(SCOUT_RYO_REWARD * scout_multiplier)
        player_updates['ryo'] = player['ryo'] + ryo_reward
        db.update_player(user.id, player_updates)
        await safe_reply(update, context, f"Found a lost wallet! **+{ryo_reward} Ryo**. ⭐ +5 Rep", parse_mode="HTML")
    else:
        db.update_player(user.id, player_updates)
        await safe_reply(update, context, "You scouted but found nothing. ⭐ +5 Rep")

async def kill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kill with bounty rewards and loot drops."""
    user = update.effective_user
    chat = update.effective_chat
    
    if chat.type == ChatType.PRIVATE or not update.message.reply_to_message:
        await safe_reply(update, context, "Reply to target in a group.")
        return
    
    victim_user = update.message.reply_to_message.from_user
    
    if victim_user.id == user.id or victim_user.is_bot:
        await safe_reply(update, context, "Invalid target.")
        return
    
    attacker = db.get_player(user.id)
    victim = db.get_player(victim_user.id)
    
    if not attacker:
        await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML")
        return
    
    if not victim:
        await safe_reply(update, context, f"<b>{escape(victim_user.first_name)}</b> is not registered.", parse_mode="HTML")
        return
    
    is_hospitalized, remaining = gl.get_hospital_status(attacker)
    if is_hospitalized:
        await safe_reply(update, context, f"🏥 You are too injured! Wait {remaining/3600:.1f}h.", parse_mode="HTML")
        return

    victim_is_hosp, _ = gl.get_hospital_status(victim)
    if victim_is_hosp:
        await safe_reply(update, context, f"⚠️ <b>{escape(victim_user.first_name)}</b> is already hospitalized!", parse_mode="HTML")
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    if victim.get('protection_until'):
        pt = victim['protection_until']
        if pt.tzinfo is None:
            pt = pt.replace(tzinfo=datetime.timezone.utc)
        if now < pt:
            await safe_reply(update, context, f"🛡️ <b>{escape(victim_user.first_name)}</b> is protected!", parse_mode="HTML")
            return

    if attacker['current_chakra'] < KILL_CHAKRA_COST:
        await safe_reply(update, context, f"🥵 Need {KILL_CHAKRA_COST} Chakra!", parse_mode="HTML")
        return
    
    # Reputation bonus
    rep_bonuses = mgv2.get_reputation_bonuses(attacker)
    kill_bonus = rep_bonuses.get('kill_success', 0)
    
    success_chance = KILL_BASE_SUCCESS + kill_bonus
    
    attacker_updates = {'current_chakra': attacker['current_chakra'] - KILL_CHAKRA_COST}
    
    if random.random() < success_chance:
        # Calculate bounty
        bounty = mgv2.calculate_bounty(victim)
        
        # Heat multiplier
        heat_level = attacker.get('heat_level', 0)
        heat_multiplier = mgv2.get_heat_multiplier(heat_level)
        final_bounty = int(bounty * heat_multiplier)
        
        hospital_until = now + datetime.timedelta(hours=HOSPITAL_DURATION_HOURS)
        
        # Update heat
        heat_updates = mgv2.update_heat(attacker, HEAT_PER_KILL)
        
        attacker_updates.update({
            'ryo': attacker['ryo'] + final_bounty,
            'exp': attacker['exp'] + 140,
            'total_exp': attacker['total_exp'] + 140,
            'kills': attacker.get('kills', 0) + 1,
            'reputation_points': attacker.get('reputation_points', 0) + 50
        })
        attacker_updates.update(heat_updates)
        
        db.update_player(user.id, attacker_updates)
        db.update_player(victim_user.id, {
            'hospitalized_until': hospital_until.isoformat(),
            'hospitalized_by': user.id,
            'bounty': 0  # Clear victim's bounty
        })
        
        # Roll for loot
        loot_type, loot_key, loot_data = mgv2.roll_for_loot(attacker)
        loot_text = ""
        if loot_type == 'legendary':
            loot_text = f"\n✨ <b>LEGENDARY DROP!</b> {loot_data['name']}"
            items = attacker.get('legendary_items', [])
            items.append(loot_key)
            db.update_player(user.id, {'legendary_items': items})
        
        # Check title
        new_title, title_info = mgv2.check_reputation_title({**attacker, **attacker_updates})
        title_text = f"\n🏆 <b>NEW TITLE!</b> {title_info['name']}" if new_title else ""
        if new_title:
            db.update_player(user.id, {'reputation_title': new_title})
        
        heat_emoji, _ = mgv2.get_heat_status(heat_updates['heat_level'])
        
        msg = (
            f"☠️ <b>EXECUTION!</b> 🩸\n\n"
            f"💀 <b>Killer:</b> {escape(user.first_name)}\n"
            f"💔 <b>Victim:</b> {escape(victim_user.first_name)}\n\n"
            f"💰 <b>Bounty:</b> {final_bounty:,} Ryo\n"
            f"✨ <b>EXP:</b> +140\n"
            f"⭐ <b>Rep:</b> +50\n"
            f"🚨 <b>Heat:</b> {heat_emoji} {heat_updates['heat_level']}/100\n"
            f"🏥 <b>Victim hospitalized 24h!{title_text}{loot_text}</b>"
        )
        await safe_reply(update, context, msg, parse_mode="HTML")
    else:
        db.update_player(user.id, attacker_updates)
        await safe_reply(update, context, f"💨 <b>MISSED!</b>\n{escape(victim_user.first_name)} escaped!", parse_mode="HTML")

async def gift_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gift with reputation tracking."""
    user = update.effective_user
    
    if not update.message.reply_to_message:
        await safe_reply(update, context, "Reply to user to gift.")
        return
    
    victim = update.message.reply_to_message.from_user
    
    if victim.id == user.id or victim.is_bot:
        await safe_reply(update, context, "Invalid target.")
        return
    
    try:
        amount = int(context.args[0])
    except:
        await safe_reply(update, context, "Usage: `/gift <amount>`")
        return
    
    if amount <= 0:
        await safe_reply(update, context, "Positive only.")
        return
    
    sender = db.get_player(user.id)
    receiver = db.get_player(victim.id)
    
    if not sender:
        await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML")
        return
    
    if not receiver:
        await safe_reply(update, context, f"{victim.mention_html()} is not registered.", parse_mode="HTML")
        return
    
    if sender['ryo'] < amount:
        await safe_reply(update, context, "Not enough Ryo!")
        return
    
    final = amount - int(amount * GIFT_TAX_PERCENT)
    
    db.atomic_add_ryo(user.id, -amount)
    db.atomic_add_ryo(victim.id, final)
    
    # Track reputation
    db.update_player(user.id, {
        'total_gifts_given': sender.get('total_gifts_given', 0) + 1,
        'reputation_points': sender.get('reputation_points', 0) + 5
    })
    
    await safe_reply(update, context, f"🎁 **GIFT SENT!**\n<b>{escape(user.first_name)}</b> gifted **{amount:,} Ryo** to <b>{escape(victim.first_name)}</b>!\n<i>(Tax: {amount - final} Ryo)</i>\n⭐ +5 Rep", parse_mode="HTML")

async def protect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Protection with reputation bonuses."""
    user = update.effective_user
    player = db.get_player(user.id)
    
    if not player:
        await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML")
        return
    
    days = 3 if (context.args and context.args[0].lower() == '3d') else 1
    cost = PROTECT_3D_COST if days == 3 else PROTECT_1D_COST
    
    if player['ryo'] < cost:
        await safe_reply(update, context, f"Need **{cost} Ryo** for {days}d protection.", parse_mode="HTML")
        return
    
    # Reputation bonus
    rep_bonuses = mgv2.get_reputation_bonuses(player)
    protection_bonus = rep_bonuses.get('protection_time', 1.0)
    actual_days = int(days * protection_bonus)
    
    now = datetime.datetime.now(datetime.timezone.utc)
    current = player.get('protection_until')
    
    if current and current.tzinfo is None:
        current = current.replace(tzinfo=datetime.timezone.utc)
    
    new_time = (current + datetime.timedelta(days=actual_days)) if (current and current > now) else (now + datetime.timedelta(days=actual_days))
    
    db.update_player(user.id, {
        'ryo': player['ryo'] - cost,
        'protection_until': new_time.isoformat(),
        'total_protections_bought': player.get('total_protections_bought', 0) + 1
    })
    
    bonus_text = f" (+{actual_days - days} bonus days!)" if actual_days > days else ""
    await safe_reply(update, context, f"🛡️ <b>ANBU GUARD HIRED!</b>\nProtected for **{actual_days} day(s)**!{bonus_text}", parse_mode="HTML")

async def heal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Heal with reputation tracking."""
    user = update.effective_user
    payer = db.get_player(user.id)
    
    if not payer:
        await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML")
        return
    
    target_id = user.id
    target_name = "You are"
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if not target_user.is_bot:
            target_id = target_user.id
            target_name = f"<b>{escape(target_user.first_name)}</b> is"
    
    target = db.get_player(target_id)
    
    if not target:
        await safe_reply(update, context, "Target not registered.")
        return
    
    hosp, _ = gl.get_hospital_status(target)
    if not hosp:
        await safe_reply(update, context, f"{target_name} not in the hospital.", parse_mode="HTML")
        return
    
    if payer['ryo'] < HEAL_COST:
        await safe_reply(update, context, f"Need **{HEAL_COST} Ryo** for medical ninjutsu.", parse_mode="HTML")
        return
    
    db.update_player(user.id, {'ryo': payer['ryo'] - HEAL_COST})
    db.update_player(target_id, {
        'hospitalized_until': None,
        'hospitalized_by': None
    })
    
    # Track reputation if healing others
    if target_id != user.id:
        db.update_player(user.id, {
            'total_heals_given': payer.get('total_heals_given', 0) + 1,
            'reputation_points': payer.get('reputation_points', 0) + 25
        })
        
        # Check for Guardian Angel title
        new_title, title_info = mgv2.check_reputation_title({**payer, 'total_heals_given': payer.get('total_heals_given', 0) + 1})
        title_text = f"\n🏆 <b>NEW TITLE!</b> {title_info['name']}" if new_title else ""
        if new_title:
            db.update_player(user.id, {'reputation_title': new_title})
        
        await safe_reply(update, context, f"💚 <b>MEDICAL NINJUTSU!</b> 💚\n{target_name} fully healed!\n⭐ +25 Rep{title_text}", parse_mode="HTML")
    else:
        await safe_reply(update, context, f"💚 <b>MEDICAL NINJUTSU!</b> 💚\n{target_name} fully healed!", parse_mode="HTML")

# 🆕 ESCAPE CALLBACK HANDLER
async def escape_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles escape mini-game when caught robbing."""
    query = update.callback_query
    
    try:
        await query.answer()
    except:
        pass
    
    data = query.data.split('_')
    action = data[1]  # run, fight, bribe
    user_id = int(data[2])
    
    if query.from_user.id != user_id:
        try:
            await query.answer("This is not your escape!", show_alert=True)
        except:
            pass
        return
    
    player = db.get_player(user_id)
    if not player:
        return
    
    stats = gl.get_total_stats(player)
    
    if action == 'run':
        # Speed check
        escape_chance = 0.5 + (stats['speed'] * 0.01)
        if random.random() < escape_chance:
            result = (
                f"🏃💨 <b>ESCAPED!</b>\n\n"
                f"You used your speed to get away!\n"
                f"⭐ +5 Reputation"
            )
            db.update_player(user_id, {
                'reputation_points': player.get('reputation_points', 0) + 5,
                'total_escapes': player.get('total_escapes', 0) + 1
            })
        else:
            lose = min(player['ryo'], STEAL_FAIL_PENALTY)
            result = (
                f"❌ <b>CAPTURED!</b>\n\n"
                f"You couldn't escape!\n"
                f"💸 Fine: {lose} Ryo"
            )
            db.atomic_add_ryo(user_id, -lose)
    
    elif action == 'fight':
        # Strength check
        win_chance = 0.3 + (stats['strength'] * 0.01)
        if random.random() < win_chance:
            reward = STEAL_FAIL_PENALTY * 2
            result = (
                f"⚔️ <b>VICTORY!</b>\n\n"
                f"You defeated the guard!\n"
                f"💰 Looted: {reward} Ryo\n"
                f"⭐ +15 Reputation"
            )
            db.atomic_add_ryo(user_id, reward)
            db.update_player(user_id, {'reputation_points': player.get('reputation_points', 0) + 15})
        else:
            lose = min(player['ryo'], STEAL_FAIL_PENALTY * 2)
            result = (
                f"💔 <b>DEFEATED!</b>\n\n"
                f"The guard overpowered you!\n"
                f"💸 Fine: {lose} Ryo"
            )
            db.atomic_add_ryo(user_id, -lose)
    
    elif action == 'bribe':
        cost = STEAL_FAIL_PENALTY * 2
        if player['ryo'] >= cost:
            result = (
                f"💰 <b>BRIBE ACCEPTED!</b>\n\n"
                f"You paid off the guard.\n"
                f"💸 Cost: {cost} Ryo"
            )
            db.atomic_add_ryo(user_id, -cost)
        else:
            lose = min(player['ryo'], STEAL_FAIL_PENALTY)
            result = (
                f"❌ <b>NOT ENOUGH RYO!</b>\n\n"
                f"Guard took what you had.\n"
                f"💸 Lost: {lose} Ryo"
            )
            db.atomic_add_ryo(user_id, -lose)
    else:
        result = "Invalid escape option!"
    
    try:
        await query.edit_message_text(result, parse_mode="HTML")
    except:
        pass
