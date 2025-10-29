import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Import our database and game_logic functions
import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Command Handler (Moved from main.py) ---

async def missions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays available missions to the player."""
    user = update.effective_user
    player = db.get_player(user.id)

    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

    text = "📜 --- MISSION BOARD --- 📜\nSelect a mission to begin:\n"
    keyboard = []
    
    for key, mission in gl.MISSIONS.items():
        if player['level'] >= mission['level_req']:
            # Player is high enough level
            button_text = f"{mission['name']} (Lvl {mission['level_req']}+)"
            callback_data = f"mission_{key}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        else:
            # Player is too low level
            button_text = f"🔒 {mission['name']} (Lvl {mission['level_req']}+)"
            callback_data = "mission_locked"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup)


# --- Callback Handler (Moved from main.py) ---

async def mission_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user's mission selection."""
    query = update.callback_query
    await query.answer()

    # --- THIS IS THE 'KeyError: d' FIX ---
    # We split only at the *first* underscore
    # "mission_d_rank".split('_', 1) -> ['mission', 'd_rank']
    mission_key = query.data.split('_', 1)[1] 
    # --- END OF FIX ---

    if mission_key == "locked":
        await query.message.reply_text("You are not high enough level for this mission.")
        return

    mission = gl.MISSIONS[mission_key]
    user = query.from_user
    player = db.get_player(user.id)

    # --- Start the Mission Animation ---
    await animate_mission(query.message, mission['animation'])
    
    # --- Grant Rewards & Check for Level Up ---
    temp_player_data = dict(player)
    
    temp_player_data['exp'] += mission['exp']
    temp_player_data['total_exp'] += mission['exp']
    temp_player_data['ryo'] += mission['ryo']

    final_player_data, leveled_up, messages = gl.check_for_level_up(temp_player_data)
    
    success = db.update_player(user.id, final_player_data)

    if success:
        result_text = f"<b>--- MISSION COMPLETE ---</b>\n"
        result_text += f"Rewards: +{mission['exp']} EXP | +{mission['ryo']} Ryo 💰"
        
        if leveled_up:
            result_text += "\n\n" + "\n".join(messages)
            
        await query.message.reply_text(result_text, parse_mode="HTML")
    else:
        await query.message.reply_text("An error occurred while saving your mission rewards.")


# --- Animation Helper (Moved from main.py) ---

async def animate_mission(message, animation_text, delay=1.5):
    """Animates a mission by editing the message for each line."""
    frames = animation_text.split('\n')
    current_text = "<i>"
    try:
        for frame in frames:
            current_text += frame + "\n"
            await message.edit_text(current_text + "</i>", parse_mode="HTML")
            await asyncio.sleep(delay)
    except Exception as e:
        # If animation is interrupted or fails, log it
        logger.warning(f"Mission animation error: {e}")
    return True
