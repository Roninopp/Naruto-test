import logging
import random
import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatType
from telegram.error import BadRequest

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Constants ---
STEAL_CHAKRA_COST = 15 
STEAL_BASE_SUCCESS_CHANCE = 0.60; STEAL_BASE_FAIL_CHANCE = 0.10; STEAL_BASE_AMOUNT = 30; STEAL_MAX_AMOUNT = 100; STEAL_FAIL_PENALTY = 20
SCOUT_COOLDOWN_MINUTES = 60; SCOUT_EXP_CHANCE = 0.05; SCOUT_RYO_CHANCE = 0.25; SCOUT_EXP_REWARD = 50; SCOUT_RYO_REWARD = 25
ASSASSINATE_COOLDOWN_HOURS = 24; ASSASSINATE_COST = 200; ASSASSINATE_BASE_SUCCESS_CHANCE = 0.15; ASSASSINATE_STEAL_PERCENT = 0.10; ASSASSINATE_MAX_STEAL = 1000; ASSASSINATE_EXP_REWARD = 100
GIFT_TAX_PERCENT = 0.05; PROTECT_1D_COST = 500; PROTECT_3D_COST = 1300
HOSPITAL_DURATION_HOURS = 3; HEAL_COST = 300

async def safe_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text, parse_mode=None):
    try: await update.message.reply_text(text, parse_mode=parse_mode)
    except BadRequest:
        try: await context.bot.send_message(update.effective_chat.id, text, parse_mode=parse_mode)
        except Exception as e: logger.error(f"Failed to send safe_reply: {e}")

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; player = db.get_player(user.id)
    if not player: await safe_reply(update, context, f"{user.mention_html()}, please /register first to start your journey!", parse_mode="HTML"); return
    wallet_text = (f"<b>--- 🥷 {user.mention_html()}'s Wallet 🥷 ---</b>\n\n" f"<b>Rank:</b> {player['rank']}\n" f"<b>Level:</b> {player['level']}\n" f"<b>Ryo:</b> {player['ryo']:,} 💰")
    await safe_reply(update, context, wallet_text, parse_mode="HTML")

async def steal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; chat = update.effective_chat
    if chat.type == ChatType.PRIVATE: await safe_reply(update, context, "You can only rob in group chats."); return
    if not update.message.reply_to_message: await safe_reply(update, context, "Reply to the user you want to rob."); return
    victim_user = update.message.reply_to_message.from_user
    if victim_user.id == user.id or victim_user.is_bot: await safe_reply(update, context, "Invalid target."); return
    stealer = db.get_player(user.id); victim = db.get_player(victim_user.id)
    if not stealer: await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML"); return
    if not victim: await safe_reply(update, context, f"{victim_user.mention_html()} is not a registered ninja.", parse_mode="HTML"); return
    is_hospitalized, remaining = gl.get_hospital_status(stealer)
    if is_hospitalized: await safe_reply(update, context, f"🏥 You are in the hospital! Wait {remaining/60:.0f}m or use /heal."); return
    now = datetime.datetime.now(datetime.timezone.utc)
    if victim.get('protection_until'):
        pt = victim['protection_until']
        if pt.tzinfo is None: pt = pt.replace(tzinfo=datetime.timezone.utc)
        if now < pt: await safe_reply(update, context, f"🛡️ **FAILED!** {victim_user.mention_html()} is protected!", parse_mode="HTML"); return
    if stealer['current_chakra'] < STEAL_CHAKRA_COST: await safe_reply(update, context, f"🥵 You are too tired! You need **{STEAL_CHAKRA_COST} Chakra** to rob someone.\nUse `/train` to recover!", parse_mode="HTML"); return
    stealer_updates = {'current_chakra': stealer['current_chakra'] - STEAL_CHAKRA_COST}
    stats = gl.get_total_stats(stealer)
    fail = max(0.05, STEAL_BASE_FAIL_CHANCE - min(0.10, stats['speed'] * 0.005))
    success = STEAL_BASE_SUCCESS_CHANCE + min(0.20, stats['speed'] * 0.01)
    steal = random.randint(STEAL_BASE_AMOUNT, min(STEAL_MAX_AMOUNT, STEAL_BASE_AMOUNT + int(stealer['level'] * 1.5)))
    roll = random.random()
    if roll < success:
        final = min(victim['ryo'], steal)
        if final <= 0: db.update_player(user.id, stealer_updates); await safe_reply(update, context, f"You pickpocketed {victim['username']}, but they are broke!"); return
        db.update_player(user.id, {**stealer_updates, 'ryo': stealer['ryo'] + final}); db.update_player(victim_user.id, {'ryo': victim['ryo'] - final})
        await safe_reply(update, context, f"✅ **Success!** Stole **{final} Ryo** from {victim['username']}!", parse_mode="HTML")
    elif roll < (success + fail):
        lose = min(stealer['ryo'], STEAL_FAIL_PENALTY)
        db.update_player(user.id, {**stealer_updates, 'ryo': stealer['ryo'] - lose})
        await safe_reply(update, context, f"❌ **Caught!** You paid a **{lose} Ryo** fine.", parse_mode="HTML")
    else: db.update_player(user.id, stealer_updates); await safe_reply(update, context, "You failed to find anything.")

async def scout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; player = db.get_player(user.id)
    if not player: await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML"); return
    hosp, rem = gl.get_hospital_status(player)
    if hosp: await safe_reply(update, context, f"🏥 You are in the hospital! Wait {rem/60:.0f}m or use /heal."); return
    now = datetime.datetime.now(datetime.timezone.utc)
    if player.get('scout_cooldown'):
        cd = player['scout_cooldown']; 
        if cd.tzinfo is None: cd = cd.replace(tzinfo=datetime.timezone.utc)
        if now < cd: await safe_reply(update, context, f"Scout again in {(cd - now).total_seconds()/60:.0f}m."); return
    upd = {'scout_cooldown': now + datetime.timedelta(minutes=SCOUT_COOLDOWN_MINUTES)}; roll = random.random()
    if roll < SCOUT_EXP_CHANCE:
        upd.update({'exp': player['exp'] + SCOUT_EXP_REWARD, 'total_exp': player['total_exp'] + SCOUT_EXP_REWARD}); db.update_player(user.id, upd)
        await safe_reply(update, context, f"You found a hidden training ground! **+{SCOUT_EXP_REWARD} EXP**!", parse_mode="HTML")
    elif roll < (SCOUT_EXP_CHANCE + SCOUT_RYO_CHANCE):
        upd['ryo'] = player['ryo'] + SCOUT_RYO_REWARD; db.update_player(user.id, upd)
        await safe_reply(update, context, f"You found a lost wallet! **+{SCOUT_RYO_REWARD} Ryo**.", parse_mode="HTML")
    else: db.update_player(user.id, upd); await safe_reply(update, context, "You scouted but found nothing.")

async def assassinate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; chat = update.effective_chat
    if chat.type == ChatType.PRIVATE or not update.message.reply_to_message: await safe_reply(update, context, "Reply to target in a group."); return
    victim_user = update.message.reply_to_message.from_user
    if victim_user.id == user.id or victim_user.is_bot: await safe_reply(update, context, "Invalid target."); return
    attacker = db.get_player(user.id); victim = db.get_player(victim_user.id)
    if not attacker: await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML"); return
    if not victim: await safe_reply(update, context, f"{victim_user.mention_html()} is not a registered ninja.", parse_mode="HTML"); return
    hosp, rem = gl.get_hospital_status(attacker)
    if hosp: await safe_reply(update, context, f"🏥 You are in the hospital! Wait {rem/3600:.1f}h or use /heal."); return
    now = datetime.datetime.now(datetime.timezone.utc)
    if victim.get('protection_until'):
        pt = victim['protection_until']
        if pt.tzinfo is None: pt = pt.replace(tzinfo=datetime.timezone.utc)
        if now < pt: await safe_reply(update, context, f"🛡️ **FAILED!** {victim_user.mention_html()} is protected!", parse_mode="HTML"); return
    if attacker.get('assassinate_cooldown'):
        cd = attacker['assassinate_cooldown']
        if cd.tzinfo is None: cd = cd.replace(tzinfo=datetime.timezone.utc)
        if now < cd: await safe_reply(update, context, f"Next contract in {(cd - now).total_seconds()/3600:.1f}h."); return
    if attacker['ryo'] < ASSASSINATE_COST: await safe_reply(update, context, f"Need {ASSASSINATE_COST} Ryo."); return
    new_cd = now + datetime.timedelta(hours=ASSASSINATE_COOLDOWN_HOURS); upd = {'assassinate_cooldown': new_cd, 'ryo': attacker['ryo'] - ASSASSINATE_COST}
    stats = gl.get_total_stats(attacker)
    chance = ASSASSINATE_BASE_SUCCESS_CHANCE + min(0.075, stats['strength'] * 0.003) + min(0.075, attacker['level'] * 0.001)
    if random.random() < chance:
        steal = min(int(victim['ryo'] * ASSASSINATE_STEAL_PERCENT), ASSASSINATE_MAX_STEAL)
        hosp_until = now + datetime.timedelta(hours=HOSPITAL_DURATION_HOURS)
        upd.update({'ryo': upd['ryo'] + steal, 'exp': attacker['exp'] + ASSASSINATE_EXP_REWARD, 'total_exp': attacker['total_exp'] + ASSASSINATE_EXP_REWARD, 'kills': attacker.get('kills', 0) + 1})
        db.update_player(user.id, upd); db.update_player(victim_user.id, {'ryo': victim['ryo'] - steal, 'hospitalized_until': hosp_until.isoformat()})
        await safe_reply(update, context, f"🎯 **ELIMINATED!**\nStole **{steal} Ryo**, gained **{ASSASSINATE_EXP_REWARD} EXP**.\n{victim_user.mention_html()} is 🏥 **HOSPITALIZED** for 3 hours!", parse_mode="HTML")
    else:
        db.update_player(user.id, upd)
        await safe_reply(update, context, f"❌ **FAILED!** You were spotted and lost **{ASSASSINATE_COST} Ryo**.", parse_mode="HTML")

async def gift_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.reply_to_message: await safe_reply(update, context, "Reply to user to gift."); return
    victim = update.message.reply_to_message.from_user
    if victim.id == user.id or victim.is_bot: await safe_reply(update, context, "Invalid target."); return
    try: amount = int(context.args[0])
    except: await safe_reply(update, context, "Usage: `/gift <amount>`"); return
    if amount <= 0: await safe_reply(update, context, "Positive amounts only."); return
    sender = db.get_player(user.id); receiver = db.get_player(victim.id)
    if not sender: await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML"); return
    if not receiver: await safe_reply(update, context, f"{victim.mention_html()} is not registered.", parse_mode="HTML"); return
    if sender['ryo'] < amount: await safe_reply(update, context, "Not enough Ryo!"); return
    final = amount - int(amount * GIFT_TAX_PERCENT)
    db.update_player(user.id, {'ryo': sender['ryo'] - amount}); db.update_player(victim.id, {'ryo': receiver['ryo'] + final})
    await safe_reply(update, context, f"🎁 **GIFT SENT!**\n{user.mention_html()} gifted **{amount:,} Ryo** to {victim.mention_html()}! (Tax deducted)", parse_mode="HTML")

async def protect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; player = db.get_player(user.id)
    if not player: await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML"); return
    days = 3 if (context.args and context.args[0].lower() == '3d') else 1
    cost = PROTECT_3D_COST if days == 3 else PROTECT_1D_COST
    if player['ryo'] < cost: await safe_reply(update, context, f"Need **{cost} Ryo** for {days}d protection.", parse_mode="HTML"); return
    now = datetime.datetime.now(datetime.timezone.utc); current = player.get('protection_until')
    if current and current.tzinfo is None: current = current.replace(tzinfo=datetime.timezone.utc)
    new_time = (current + datetime.timedelta(days=days)) if (current and current > now) else (now + datetime.timedelta(days=days))
    db.update_player(user.id, {'ryo': player['ryo'] - cost, 'protection_until': new_time.isoformat()})
    await safe_reply(update, context, f"🛡️ **ANBU GUARD HIRED!** Protected for **{days} day(s)**!", parse_mode="HTML")

async def heal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; payer = db.get_player(user.id)
    if not payer: await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML"); return
    target_id = user.id; target_name = "You are"
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if not target_user.is_bot: target_id = target_user.id; target_name = f"{target_user.mention_html()} is"
    target = db.get_player(target_id)
    if not target: await safe_reply(update, context, "Target not registered."); return
    hosp, _ = gl.get_hospital_status(target)
    if not hosp: await safe_reply(update, context, f"{target_name} not in the hospital."); return
    if payer['ryo'] < HEAL_COST: await safe_reply(update, context, f"Need **{HEAL_COST} Ryo** for medical ninjutsu.", parse_mode="HTML"); return
    db.update_player(user.id, {'ryo': payer['ryo'] - HEAL_COST})
    db.update_player(target_id, {'hospitalized_until': None})
    await safe_reply(update, context, f"💚 **MEDICAL NINJUTSU!** 💚\n{target_name} fully healed and released from the hospital!", parse_mode="HTML")
