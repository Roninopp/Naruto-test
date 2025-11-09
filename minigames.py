import logging
import random
import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatType
from telegram.error import BadRequest
from datetime import timezone

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Constants ---
STEAL_CHAKRA_COST = 15 
STEAL_BASE_SUCCESS_CHANCE = 0.60; STEAL_BASE_FAIL_CHANCE = 0.10; STEAL_BASE_AMOUNT = 30; STEAL_MAX_AMOUNT = 100; STEAL_FAIL_PENALTY = 20
SCOUT_COOLDOWN_MINUTES = 60; SCOUT_EXP_CHANCE = 0.05; SCOUT_RYO_CHANCE = 0.25; SCOUT_EXP_REWARD = 50; SCOUT_RYO_REWARD = 25
GIFT_TAX_PERCENT = 0.05; PROTECT_1D_COST = 500; PROTECT_3D_COST = 1300

# --- KILL CONSTANTS ---
KILL_CHAKRA_COST = 50
KILL_RYO_REWARD = 140
KILL_EXP_REWARD = 100
KILL_BASE_SUCCESS = 1.00 # 100% Success Rate if not protected
KILL_COOLDOWN_HOURS = 24 # How long they stay "dead"
# ----------------------

async def safe_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text, parse_mode=None):
    try: await update.message.reply_text(text, parse_mode=parse_mode)
    except BadRequest:
        try: await context.bot.send_message(update.effective_chat.id, text, parse_mode=parse_mode)
        except Exception as e: logger.error(f"Failed to send safe_reply: {e}")

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; player = db.get_player(user.id)
    if not player: await safe_reply(update, context, f"Hey {user.mention_html()}! Please /start me in a private chat.", parse_mode="HTML"); return
    
    # Check if they are currently "dead"
    is_dead, rem = gl.get_hospital_status(player)
    status_text = f"\n💀 **Status:** Killed (Revives in {rem/3600:.1f}h)" if is_dead else "\n❤️ **Status:** Alive"
    
    wallet_text = (
        f"<b>--- 🥷 {user.mention_html()}'s Wallet 🥷 ---</b>\n\n"
        f"<b>Rank:</b> {player['rank']}\n"
        f"<b>Level:</b> {player['level']}\n"
        f"<b>Ryo:</b> {player['ryo']:,} 💰\n"
        f"<b>Kills:</b> {player.get('kills', 0)} ☠️"
        f"{status_text}"
    )
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
    
    # We removed hospital check for attacker here, they can rob even if "dead" based on your new rules?
    # If you want "dead" players to NOT rob, uncomment lines below:
    # is_dead, remaining = gl.get_hospital_status(stealer)
    # if is_dead: await safe_reply(update, context, f"💀 You are dead! Wait {remaining/3600:.1f}h or use /heal."); return

    now = datetime.datetime.now(timezone.utc)
    if victim.get('protection_until'):
        pt = victim['protection_until']
        if pt.tzinfo is None: pt = pt.replace(tzinfo=timezone.utc)
        if now < pt: await safe_reply(update, context, f"🛡️ **FAILED!** {victim_user.mention_html()} is Protected By Black Anbu Guards!", parse_mode="HTML"); return

    if stealer['current_chakra'] < STEAL_CHAKRA_COST: await safe_reply(update, context, f"🥵 You are too tired! You need **{STEAL_CHAKRA_COST} Chakra**.", parse_mode="HTML"); return
         
    stealer_updates = {'current_chakra': stealer['current_chakra'] - STEAL_CHAKRA_COST}
    stealer_stats = gl.get_total_stats(stealer)
    fail_chance = max(0.05, STEAL_BASE_FAIL_CHANCE - min(0.10, stealer_stats['speed'] * 0.005))
    success_chance = STEAL_BASE_SUCCESS_CHANCE + min(0.20, stealer_stats['speed'] * 0.01)
    steal_amount = random.randint(STEAL_BASE_AMOUNT, min(STEAL_MAX_AMOUNT, STEAL_BASE_AMOUNT + int(stealer['level'] * 1.5)))
    roll = random.random()
    
    if roll < success_chance:
        final_steal = min(victim['ryo'], steal_amount)
        if final_steal <= 0: 
            db.update_player(user.id, stealer_updates)
            await safe_reply(update, context, f"You pickpocketed {victim_user.mention_html()}, but they are broke!", parse_mode="HTML"); return
        stealer_updates['ryo'] = stealer['ryo'] + final_steal
        db.update_player(user.id, stealer_updates)
        db.update_player(victim_user.id, {'ryo': victim['ryo'] - final_steal})
        await safe_reply(update, context, f"✅ **Success!** Stole **{final_steal} Ryo** from {victim_user.mention_html()}!", parse_mode="HTML")
    elif roll < (success_chance + fail_chance):
        lose = min(stealer['ryo'], STEAL_FAIL_PENALTY)
        stealer_updates['ryo'] = stealer['ryo'] - lose
        db.update_player(user.id, stealer_updates)
        await safe_reply(update, context, f"❌ **Caught!** You paid a **{lose} Ryo** fine.", parse_mode="HTML")
    else:
        db.update_player(user.id, stealer_updates)
        await safe_reply(update, context, "You failed to find anything.")

async def scout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; player = db.get_player(user.id)
    if not player: await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML"); return
    
    # Optional: Uncomment if you want dead players unable to scout
    # is_dead, remaining = gl.get_hospital_status(player)
    # if is_dead: await safe_reply(update, context, f"💀 You are dead! Wait {remaining/3600:.1f}h."); return

    now = datetime.datetime.now(timezone.utc)
    if player.get('scout_cooldown'):
        cd = player['scout_cooldown']; 
        if cd.tzinfo is None: cd = cd.replace(tzinfo=timezone.utc)
        if now < cd: await safe_reply(update, context, f"Scout again in {(cd - now).total_seconds()/60:.0f}m."); return
    player_updates = {'scout_cooldown': now + datetime.timedelta(minutes=SCOUT_COOLDOWN_MINUTES)}; roll = random.random()
    if roll < SCOUT_EXP_CHANCE:
        player_updates.update({'exp': player['exp'] + SCOUT_EXP_REWARD, 'total_exp': player['total_exp'] + SCOUT_EXP_REWARD}); db.update_player(user.id, player_updates)
        await safe_reply(update, context, f"You found a hidden training ground! **+{SCOUT_EXP_REWARD} EXP**!", parse_mode="HTML")
    elif roll < (SCOUT_EXP_CHANCE + SCOUT_RYO_CHANCE):
        player_updates['ryo'] = player['ryo'] + SCOUT_RYO_REWARD; db.update_player(user.id, player_updates)
        await safe_reply(update, context, f"You found a lost wallet! **+{SCOUT_RYO_REWARD} Ryo**.", parse_mode="HTML")
    else:
        db.update_player(user.id, player_updates)
        await safe_reply(update, context, "You scouted but found nothing.")

async def kill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; chat = update.effective_chat
    if chat.type == ChatType.PRIVATE or not update.message.reply_to_message: await safe_reply(update, context, "Reply to target in a group."); return
    victim_user = update.message.reply_to_message.from_user
    if victim_user.id == user.id or victim_user.is_bot: await safe_reply(update, context, "Invalid target."); return
    attacker = db.get_player(user.id); victim = db.get_player(victim_user.id)
    if not attacker: await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML"); return
    if not victim: await safe_reply(update, context, f"{victim_user.mention_html()} is not a registered ninja.", parse_mode="HTML"); return
    
    # --- VITAL: Check if victim is ALREADY DEAD ---
    # We use 'hospitalized_until' as the 'death timer'
    is_dead, _ = gl.get_hospital_status(victim)
    if is_dead:
        killer_id = victim.get('hospitalized_by')
        killer_name = "someone"
        if killer_id:
             # Try to get killer name from DB if possible
             killer = db.get_player(killer_id)
             if killer: killer_name = killer['username']
        await safe_reply(update, context, f"⚠️ This Ninja Is Already Killed☠️ By **{killer_name}**!", parse_mode="HTML")
        return
    # ----------------------------------------------

    now = datetime.datetime.now(timezone.utc)
    if victim.get('protection_until'):
        pt = victim['protection_until']
        if pt.tzinfo is None: pt = pt.replace(tzinfo=timezone.utc)
        if now < pt: await safe_reply(update, context, f"🛡️ **FAILED!** {victim_user.mention_html()} is Protected By Black Anbu Guards!", parse_mode="HTML"); return

    if attacker['current_chakra'] < KILL_CHAKRA_COST: await safe_reply(update, context, f"🥵 You need **{KILL_CHAKRA_COST} Chakra** to kill! Use /train.", parse_mode="HTML"); return
    
    # --- 100% SUCCESS ---
    death_timer = now + datetime.timedelta(hours=KILL_COOLDOWN_HOURS)
    
    attacker_updates = {
        'current_chakra': attacker['current_chakra'] - KILL_CHAKRA_COST,
        'ryo': attacker['ryo'] + KILL_RYO_REWARD,
        'exp': attacker['exp'] + KILL_EXP_REWARD,
        'total_exp': attacker['total_exp'] + KILL_EXP_REWARD,
        'kills': attacker.get('kills', 0) + 1
    }
    
    # Apply updates
    db.update_player(user.id, attacker_updates)
    # Mark victim as dead (hospitalized) and record who did it
    db.update_player(victim_user.id, {'hospitalized_until': death_timer.isoformat(), 'hospitalized_by': user.id})
    
    await safe_reply(update, context, f"🎯 **TARGET ELIMINATED!**\n{user.mention_html()} killed {victim_user.mention_html()}!\nReward: **+{KILL_RYO_REWARD} Ryo**, **+{KILL_EXP_REWARD} EXP**.", parse_mode="HTML")

# Alias
async def assassinate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await kill_command(update, context)

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
    now = datetime.datetime.now(timezone.utc); current = player.get('protection_until')
    if current and current.tzinfo is None: current = current.replace(tzinfo=timezone.utc)
    new_time = (current + datetime.timedelta(days=days)) if (current and current > now) else (now + datetime.timedelta(days=days))
    db.update_player(user.id, {'ryo': player['ryo'] - cost, 'protection_until': new_time.isoformat()})
    await safe_reply(update, context, f"🛡️ **ANBU GUARD HIRED!** Protected for **{days} day(s)**!", parse_mode="HTML")

# --- UPDATED /heal Command ---
# Uses specific "Revive" text now since it's for "Killed" players
async def heal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; payer = db.get_player(user.id)
    if not payer: await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML"); return
    target_id = user.id; target_name = "You are"
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if not target_user.is_bot: target_id = target_user.id; target_name = f"{target_user.mention_html()} is"
    target = db.get_player(target_id)
    if not target: await safe_reply(update, context, "Target not registered."); return
    is_dead, _ = gl.get_hospital_status(target)
    if not is_dead: await safe_reply(update, context, f"{target_name} alive and well."); return
    # We'll use a higher cost for reviving from death? Or keep it 300?
    # Let's keep it 300 for now as requested.
    RE VIVE_COST = 300 
    if payer['ryo'] < RE VIVE_COST: await safe_reply(update, context, f"Need **{RE VIVE_COST} Ryo** for revival jutsu.", parse_mode="HTML"); return
    db.update_player(user.id, {'ryo': payer['ryo'] - RE VIVE_COST})
    db.update_player(target_id, {'hospitalized_until': None, 'hospitalized_by': None})
    await safe_reply(update, context, f"💚 **EDO TENSEI!** (Just kidding, it was medical ninjutsu)\n{target_name} revived and ready for action!", parse_mode="HTML")
