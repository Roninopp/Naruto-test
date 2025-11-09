import logging
import asyncio
import datetime 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Command Handler ---

async def training_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the training options."""
    user = update.effective_user
    player = db.get_player(user.id)

    if not player:
        # --- TEXT UPDATE ---
        await update.message.reply_text(f"{user.mention_html()}, you must /register first to start training!", parse_mode="HTML")
        return
        # -------------------

    text = "Select a training regimen:"
    keyboard = [
        [InlineKeyboardButton("🧘 Chakra Control (+5 Max Chakra)", callback_data="train_chakra_control")],
        [InlineKeyboardButton("🥋 Taijutsu (+3 Strength)", callback_data="train_taijutsu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup)

# --- Callback Handler ---

async def training_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user's training selection."""
    query = update.callback_query
    
    user = query.from_user
    player = db.get_player(user.id)
    
    if not player:
         # --- TEXT UPDATE ---
         await query.answer("Please /register first!", show_alert=True)
         return
         # -------------------
         
    # --- Hospital Check ---
    is_hospitalized, remaining = gl.get_hospital_status(player)
    if is_hospitalized:
            await query.answer(f"🏥 You are too injured to train! Wait {remaining/60:.0f} minutes or use /heal.", show_alert=True)
            return

    await query.answer()
    training_key = query.data.split('_', 1)[1] 
    training_info = gl.TRAINING_ANIMATIONS.get(training_key)

    if not training_info:
        await query.edit_message_text("Error: Invalid training type.")
        return

    player_data = dict(player) 
    
    today_date = datetime.date.today() # Use date object directly for comparison if DB returns date object
    TRAINING_LIMIT = 2

    if player_data.get('last_train_reset_date') != today_date:
        player_data['daily_train_count'] = 0
        player_data['last_train_reset_date'] = today_date
    
    if player_data.get('daily_train_count', 0) >= TRAINING_LIMIT:
        await query.edit_message_text(f"🧘 You have reached your daily training limit of {TRAINING_LIMIT} per day. Come back tomorrow!", parse_mode="HTML", reply_markup=None); return
    
    try:
        for frame in training_info['frames']: await query.edit_message_text(f"<i>{frame}</i>", parse_mode="HTML"); await asyncio.sleep(1.5)
    except Exception as e: logger.warning(f"Training animation error: {e}")
    
    stat_to_update = training_info['stat']; amount = training_info['amount']
    player_data[stat_to_update] += amount

    if stat_to_update in ['strength', 'speed', 'intelligence', 'stamina']: player_data = gl.distribute_stats(player_data, 0) 
    
    player_data['current_hp'] = player_data['max_hp']
    player_data['current_chakra'] = player_data['max_chakra']
    player_data['daily_train_count'] += 1

    success = db.update_player(user.id, player_data)
    if success: await query.message.reply_text(f"<b>Training Complete!</b>\n{training_info['reward_text']}", parse_mode="HTML")
    else: await query.message.reply_text("An error occurred while saving your training gains.")
