import logging
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
UPDATE_CHANNEL_USERNAME = "@SN_Telegram_bots_Stores" # <-- CHANGE THIS TO YOUR CHANNEL
DAILY_REWARD_RYO = 100
DAILY_REWARD_EXP = 150
# ---------------------

async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /daily reward command with channel check."""
    user = update.effective_user
    player = db.get_player(user.id)

    if not player:
        await update.message.reply_text(
            f"Hey {user.mention_html()}! Please /start me in a private chat to begin your journey.",
            parse_mode="HTML"
        )
        return

    # --- 1. Check Channel Membership ---
    try:
        member = await context.bot.get_chat_member(chat_id=UPDATE_CHANNEL_USERNAME, user_id=user.id)
        if member.status in ['left', 'kicked']:
            # Not a member, send buttons
            keyboard = [
                [InlineKeyboardButton("📢 Join Update Channel", url=f"https://t.me/{UPDATE_CHANNEL_USERNAME.replace('@', '')}")],
                [InlineKeyboardButton("✅ Claim Reward", callback_data="daily_claim_check")]
            ]
            await update.message.reply_text(
                f"Hey {user.mention_html()}! You must join our update channel to claim your daily reward.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
            return
    except BadRequest as e:
        logger.error(f"Could not check channel membership for {user.id}: {e}")
        # If bot can't check (e.g. not admin, or channel invalid), just let them claim to avoid getting stuck.
        pass 

    # --- 2. Check Daily Cooldown ---
    today = datetime.date.today()
    last_claim = player.get('last_daily_claim')
    
    if last_claim == today:
        await update.message.reply_text("⏳ You have already claimed your daily reward today. Come back tomorrow!")
        return

    # --- 3. Give Reward ---
    player['ryo'] += DAILY_REWARD_RYO
    player['exp'] += DAILY_REWARD_EXP
    player['total_exp'] += DAILY_REWARD_EXP
    player['last_daily_claim'] = today
    
    final_player_data, leveled_up, messages = gl.check_for_level_up(player)
    db.update_player(user.id, final_player_data)
    
    text = (
        f"🎁 **DAILY REWARD CLAIMED!** 🎁\n\n"
        f"You received:\n"
        f"💰 **+{DAILY_REWARD_RYO} Ryo**\n"
        f"✨ **+{DAILY_REWARD_EXP} EXP**\n"
        f"Come back tomorrow for more!"
    )
    if leveled_up:
        text += "\n\n" + "\n".join(messages)
        
    await update.message.reply_text(text, parse_mode="HTML")


async def daily_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Claim Reward' button press."""
    query = update.callback_query
    user = query.from_user
    
    # Re-check membership
    try:
        member = await context.bot.get_chat_member(chat_id=UPDATE_CHANNEL_USERNAME, user_id=user.id)
        if member.status in ['left', 'kicked']:
            await query.answer("❌ You haven't joined the channel yet!", show_alert=True)
            return
    except BadRequest:
        pass # Skip check if it fails

    # If joined, delete the button message and run the main command logic
    await query.message.delete()
    # We can't easily call the command handler directly because 'update' is different.
    # So we just run the logic here (simplified for callback).
    
    player = db.get_player(user.id)
    today = datetime.date.today()
    if player.get('last_daily_claim') == today:
         await context.bot.send_message(query.message.chat_id, "⏳ You have already claimed your daily reward today.")
         return

    player['ryo'] += DAILY_REWARD_RYO
    player['exp'] += DAILY_REWARD_EXP
    player['total_exp'] += DAILY_REWARD_EXP
    player['last_daily_claim'] = today
    final_player_data, leveled_up, messages = gl.check_for_level_up(player)
    db.update_player(user.id, final_player_data)
    
    text = f"🎁 **DAILY REWARD CLAIMED!** 🎁\n\nYou received 💰 **+{DAILY_REWARD_RYO} Ryo** and ✨ **+{DAILY_REWARD_EXP} EXP**!"
    if leveled_up: text += "\n\n" + "\n".join(messages)
    await context.bot.send_message(query.message.chat_id, text, parse_mode="HTML")
