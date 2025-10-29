import logging
import asyncio
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
    
    # --- Play Animation ---
    try:
        for frame in training_info['frames']:
            await query.edit_message_text(f"<i>{frame}</i>", parse_mode="HTML")
            await asyncio.sleep(1.5)
    except Exception as e:
        logger.warning(f"Training animation error: {e}")
    
    # --- Grant Reward ---
    player_data = dict(player)
    stat_to_update = training_info['stat']
    amount = training_info['amount']
    
    player_data[stat_to_update] += amount

    # --- THIS IS THE FIX ---
    # Only recalculate (call distribute_stats) if a *base stat* changed.
    # If we just added to 'max_chakra', we must NOT recalculate.
    if stat_to_update in ['strength', 'speed', 'intelligence', 'stamina']:
        player_data = gl.distribute_stats(player_data, 0) 
    # --- END OF FIX ---
    
    # Refill HP/Chakra to new max
    player_data['current_hp'] = player_data['max_hp']
    player_data['current_chakra'] = player_data['max_chakra']

    success = db.update_player(user.id, player_data)
    
    if success:
        await query.message.reply_text(f"<b>Training Complete!</b>\n{training_info['reward_text']}", parse_mode="HTML")
    else:
        await query.message.reply_text("An error occurred while saving your training gains.")
