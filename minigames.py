import logging
import random
import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatType
from telegram.error import BadRequest
from html import escape

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Constants ---
STEAL_CHAKRA_COST = 15 
STEAL_BASE_SUCCESS_CHANCE = 0.60
STEAL_BASE_FAIL_CHANCE = 0.10
STEAL_BASE_AMOUNT = 30
STEAL_MAX_ROB_AMOUNT = 100  # ✅ FIXED: Renamed from STEAL_MAX_AMOUNT
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
KILL_RYO_REWARD = 100
KILL_EXP_REWARD = 140
KILL_BASE_SUCCESS = 0.50
HOSPITAL_DURATION_HOURS = 24
HEAL_COST = 300

async def safe_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text, parse_mode=None):
    try:
        await update.message.reply_text(text, parse_mode=parse_mode)
    except BadRequest:
        try:
            await context.bot.send_message(update.effective_chat.id, text, parse_mode=parse_mode)
        except Exception as e:
            logger.error(f"Failed to send safe_reply: {e}")

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows your wallet, or the wallet of the user you reply to."""
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
    
    wallet_text = (
        f"<b>--- 🥷 {escape(target_user.first_name)}'s Wallet 🥷 ---</b>\n\n"
        f"<b>Rank:</b> {player['rank']}\n"
        f"<b>Level:</b> {player['level']}\n"
        f"<b>Ryo:</b> {player['ryo']:,} 💰\n"
        f"<b>Kills:</b> {player.get('kills', 0)} ☠️\n"
        f"<b>Status:</b> {status_text}" 
    )
    
    await safe_reply(update, context, wallet_text, parse_mode="HTML")

async def steal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Attempts to steal a specific amount of Ryo from a replied-to user."""
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
         
    stealer_updates = {'current_chakra': stealer['current_chakra'] - STEAL_CHAKRA_COST}
    stealer_stats = gl.get_total_stats(stealer)
    
    fail_chance = max(0.05, STEAL_BASE_FAIL_CHANCE - min(0.10, stealer_stats['speed'] * 0.005))
    success_chance = STEAL_BASE_SUCCESS_CHANCE + min(0.20, stealer_stats['speed'] * 0.01)
    
    roll = random.random()
    
    if roll < success_chance:
        # ✅ SUCCESS: Use atomic operations to prevent race conditions
        db.update_player(user.id, stealer_updates)
        
        # Atomic Ryo transfer
        db.atomic_add_ryo(user.id, amount_to_steal)
        db.atomic_add_ryo(victim_user.id, -amount_to_steal)
        
        victim_name = escape(victim_user.first_name)
        success_messages = [
            f"✅ **Success!** You used a classic substitution jutsu and swiped **{amount_to_steal} Ryo** from **{victim_name}**!",
            f"✅ **Perfect Stealth!** You slipped past **{victim_name}**'s defenses and took **{amount_to_steal} Ryo**!",
            f"✅ **Gotcha!** You pickpocketed **{victim_name}** while they weren't looking. You got **{amount_to_steal} Ryo**!",
            f"✅ **Too Easy!** You stole **{amount_to_steal} Ryo** from **{victim_name}**. They'll never see it coming!"
        ]
        await safe_reply(update, context, random.choice(success_messages), parse_mode="HTML")
        
    elif roll < (success_chance + fail_chance):
        # CAUGHT: Pay penalty
        lose = min(stealer['ryo'], STEAL_FAIL_PENALTY)
        stealer_updates['ryo'] = stealer['ryo'] - lose
        db.update_player(user.id, stealer_updates)
        await safe_reply(update, context, f"❌ **Caught!** You paid a **{lose} Ryo** fine.", parse_mode="HTML")
    else:
        # NEUTRAL: Just lose chakra
        db.update_player(user.id, stealer_updates)
        await safe_reply(update, context, "You failed to find anything.")

async def scout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    player_updates = {'scout_cooldown': now + datetime.timedelta(minutes=SCOUT_COOLDOWN_MINUTES)}
    roll = random.random()
    
    if roll < SCOUT_EXP_CHANCE:
        player_updates.update({
            'exp': player['exp'] + SCOUT_EXP_REWARD, 
            'total_exp': player['total_exp'] + SCOUT_EXP_REWARD
        })
        db.update_player(user.id, player_updates)
        await safe_reply(update, context, f"You found a hidden training ground! **+{SCOUT_EXP_REWARD} EXP**!", parse_mode="HTML")
    elif roll < (SCOUT_EXP_CHANCE + SCOUT_RYO_CHANCE):
        player_updates['ryo'] = player['ryo'] + SCOUT_RYO_REWARD
        db.update_player(user.id, player_updates)
        await safe_reply(update, context, f"You found a lost wallet! **+{SCOUT_RYO_REWARD} Ryo**.", parse_mode="HTML")
    else:
        db.update_player(user.id, player_updates)
        await safe_reply(update, context, "You scouted but found nothing.")

async def kill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await safe_reply(update, context, f"🏥 You are too injured to fight! Wait {remaining/3600:.1f}h.", parse_mode="HTML")
        return

    victim_is_hosp, _ = gl.get_hospital_status(victim)
    if victim_is_hosp:
        killer_id = victim.get('hospitalized_by')
        killer_name = "someone"
        if killer_id:
            killer = db.get_player(killer_id)
            if killer:
                killer_name = killer['username']
        await safe_reply(update, context, f"⚠️ <b>{escape(victim_user.first_name)}</b> was already killed by <b>{escape(killer_name)}</b>!", parse_mode="HTML")
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    if victim.get('protection_until'):
        pt = victim['protection_until']
        if pt.tzinfo is None:
            pt = pt.replace(tzinfo=datetime.timezone.utc)
        if now < pt:
            await safe_reply(update, context, f"🛡️ **ATTEMPT FAILED!**\n<b>{escape(victim_user.first_name)}</b> is protected by Anbu Black Ops!", parse_mode="HTML")
            return

    if attacker['current_chakra'] < KILL_CHAKRA_COST:
        await safe_reply(update, context, f"🥵 Need {KILL_CHAKRA_COST} Chakra! Use /train.", parse_mode="HTML")
        return
    
    attacker_updates = {'current_chakra': attacker['current_chakra'] - KILL_CHAKRA_COST}
    
    if random.random() < KILL_BASE_SUCCESS:
        hospital_until = now + datetime.timedelta(hours=HOSPITAL_DURATION_HOURS)
        attacker_updates.update({
            'ryo': attacker['ryo'] + KILL_RYO_REWARD, 
            'exp': attacker['exp'] + KILL_EXP_REWARD, 
            'total_exp': attacker['total_exp'] + KILL_EXP_REWARD, 
            'kills': attacker.get('kills', 0) + 1
        })
        db.update_player(user.id, attacker_updates)
        db.update_player(victim_user.id, {
            'hospitalized_until': hospital_until.isoformat(), 
            'hospitalized_by': user.id
        })
        
        msg = (
            f"☠️ **SHINOBI EXECUTED** 🩸\n\n"
            f"💤 **Killer:** {escape(user.first_name)}\n"
            f"💀 **Victim:** {escape(victim_user.first_name)}\n\n"
            f"💸 **Bounty:** {KILL_RYO_REWARD} Ryo\n"
            f"✨ **Exp Gained:** +{KILL_EXP_REWARD}\n"
            f"🏥 **Status:** Victim hospitalized for 24h!"
        )
        await safe_reply(update, context, msg, parse_mode="HTML")
    else:
        db.update_player(user.id, attacker_updates)
        await safe_reply(update, context, f"💨 **MISSED!**\n<b>{escape(victim_user.first_name)}</b> spotted you and escaped! You wasted your Chakra.", parse_mode="HTML")

async def gift_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    # ✅ Use atomic operations
    db.atomic_add_ryo(user.id, -amount)
    db.atomic_add_ryo(victim.id, final)
    
    await safe_reply(update, context, f"🎁 **GIFT SENT!**\n<b>{escape(user.first_name)}</b> gifted **{amount:,} Ryo** to <b>{escape(victim.first_name)}</b>!\n<i>(Tax deducted: {amount - final} Ryo)</i>", parse_mode="HTML")

async def protect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    now = datetime.datetime.now(datetime.timezone.utc)
    current = player.get('protection_until')
    
    if current and current.tzinfo is None:
        current = current.replace(tzinfo=datetime.timezone.utc)
    
    new_time = (current + datetime.timedelta(days=days)) if (current and current > now) else (now + datetime.timedelta(days=days))
    
    db.update_player(user.id, {
        'ryo': player['ryo'] - cost, 
        'protection_until': new_time.isoformat()
    })
    
    await safe_reply(update, context, f"🛡️ **ANBU GUARD HIRED!** Protected for **{days} day(s)**!", parse_mode="HTML")

async def heal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    await safe_reply(update, context, f"💚 **MEDICAL NINJUTSU!** 💚\n{target_name} fully healed and released from the hospital!", parse_mode="HTML")
