import logging
import asyncio
import datetime # FIX: NEW IMPORT
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Import our database and game_logic functions
import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Command Handler ---

async def training_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the training options."""
    user = update.effective_user
    player = db.get_player(user.id)

    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

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
    await query.answer()

    training_key = query.data.split('_', 1)[1] # "chakra_control" or "taijutsu"
    training_info = gl.TRAINING_ANIMATIONS.get(training_key)

    if not training_info:
        await query.edit_message_text("Error: Invalid training type.")
        return

    user = query.from_user
    player = db.get_player(user.id)
    player_data = dict(player) # Convert to mutable dict for state tracking
    
    # --- FIX: Daily Limit Check & Reset ---
    today_date = datetime.date.today().isoformat()
    TRAINING_LIMIT = 2

    # 1. Reset check: If it's a new day, reset count and update date in the local player_data
    if player_data.get('last_train_reset_date') != today_date:
        player_data['daily_train_count'] = 0
        player_data['last_train_reset_date'] = today_date
    
    # 2. Limit check: If limit is reached, inform user and exit
    if player_data.get('daily_train_count', 0) >= TRAINING_LIMIT:
        await query.edit_message_text(
            f"🧘 You have reached your daily training limit of {TRAINING_LIMIT} per day. Come back tomorrow!", 
            parse_mode="HTML", 
            reply_markup=None 
        )
        return
    # --- END FIX: Daily Limit Check & Reset ---
    
    # --- Play Animation ---
    try:
        # Use query.message.edit_text to keep the animation on the same message
        for frame in training_info['frames']:
            await query.edit_message_text(f"<i>{frame}</i>", parse_mode="HTML")
            await asyncio.sleep(1.5)
    except Exception as e:
        logger.warning(f"Training animation error: {e}")
    
    # --- Grant Reward ---
    # player_data is already a dict from the start of the function
    
    stat_to_update = training_info['stat']
    amount = training_info['amount']
    
    player_data[stat_to_update] += amount

    # Only recalculate (call distribute_stats) if a *base stat* changed.
    # If we just added to 'max_chakra', we must NOT recalculate.
    if stat_to_update in ['strength', 'speed', 'intelligence', 'stamina']:
        player_data = gl.distribute_stats(player_data, 0) 
    
    # Refill HP/Chakra to new max
    player_data['current_hp'] = player_data['max_hp']
    player_data['current_chakra'] = player_data['max_chakra']

    # --- FIX: Increment daily training count ---
    player_data['daily_train_count'] += 1
    # The last_train_reset_date is already set to today_date (either by reset or by being up-to-date)
    # --- END FIX ---

    success = db.update_player(user.id, player_data)
    
    if success:
        await query.message.reply_text(f"<b>Training Complete!</b>\n{training_info['reward_text']}", parse_mode="HTML")
    else:
        await query.message.reply_text("An error occurred while saving your training gains.")
