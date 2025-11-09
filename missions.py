import logging
import asyncio
import datetime 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Import our database and game_logic functions
import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- SET THE DAILY MISSION LIMIT ---
DAILY_MISSION_LIMIT = 3
# -----------------------------------

# --- Command Handler ---

async def missions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays available missions to the player."""
    user = update.effective_user
    player = db.get_player(user.id)

    if not player:
        # --- TEXT UPDATE ---
        await update.message.reply_text(f"{user.mention_html()}, you must /register first to start your journey!", parse_mode="HTML")
        return
        # -------------------

    today_date = datetime.date.today()
    if player.get('last_mission_reset_date') != today_date:
        player['daily_mission_count'] = 0
        player['last_mission_reset_date'] = today_date
        db.update_player(user.id, {'daily_mission_count': 0, 'last_mission_reset_date': today_date})
    
    missions_done = player.get('daily_mission_count', 0)
    
    text = (f"📜 --- **MISSION BOARD** --- 📜\nYou have completed **{missions_done} / {DAILY_MISSION_LIMIT}** missions today.\n\nSelect a mission to begin:\n")
    
    keyboard = []
    for key, mission in gl.MISSIONS.items():
        if player['level'] >= mission['level_req']:
            button_text = f"{mission['name']} (Lvl {mission['level_req']}+)"
            callback_data = f"mission_{key}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        else:
            button_text = f"🚫 {mission['name']} (Lvl {mission['level_req']}+)"
            callback_data = "mission_locked"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

# --- Callback Handler ---

async def mission_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user's mission selection."""
    query = update.callback_query
    user = query.from_user
    player = db.get_player(user.id)
    
    if not player:
        # --- TEXT UPDATE ---
        await query.answer("Please /register first to perform missions!", show_alert=True)
        return
        # -------------------
        
    # --- Hospital Check ---
    is_hospitalized, remaining = gl.get_hospital_status(player)
    if is_hospitalized:
         await query.answer(f"🏥 You are in the hospital! Wait {remaining/60:.0f} minutes or use /heal.", show_alert=True)
         return

    await query.answer()
    mission_key = query.data.split('_', 1)[1] 

    if mission_key == "locked":
        await query.answer("You are not high enough level for this mission.", show_alert=True)
        return

    mission = gl.MISSIONS[mission_key]
    
    today_date = datetime.date.today()
    if player.get('last_mission_reset_date') != today_date:
        player['daily_mission_count'] = 0
        player['last_mission_reset_date'] = today_date
        
    missions_done = player.get('daily_mission_count', 0)
    if missions_done >= DAILY_MISSION_LIMIT:
        await query.edit_message_text(f"You have already completed your **{DAILY_MISSION_LIMIT}** missions for the day.\nRest up, ninja! New missions will be available tomorrow.")
        return

    await animate_mission(query.message, mission['animation'])
    
    temp_player_data = dict(player)
    temp_player_data['exp'] += mission['exp']
    temp_player_data['total_exp'] += mission['exp']
    temp_player_data['ryo'] += mission['ryo']
    temp_player_data['daily_mission_count'] += 1
    temp_player_data['last_mission_reset_date'] = today_date

    final_player_data, leveled_up, messages = gl.check_for_level_up(temp_player_data)
    success = db.update_player(user.id, final_player_data)

    if success:
        result_text = (f"<b>--- MISSION COMPLETE ---</b>\nRewards: +{mission['exp']} EXP | +{mission['ryo']} Ryo 💰\n\n<i>Missions completed today: {temp_player_data['daily_mission_count']} / {DAILY_MISSION_LIMIT}</i>")
        if leveled_up: result_text += "\n\n" + "\n".join(messages)
        await query.message.reply_text(result_text, parse_mode="HTML")
    else:
        await query.message.reply_text("An error occurred while saving your mission rewards.")

async def animate_mission(message, animation_text, delay=1.5):
    frames = animation_text.split('\n'); current_text = "<i>"
    try:
        await message.edit_text(current_text + frames[0] + "\n</i>", parse_mode="HTML", reply_markup=None); await asyncio.sleep(delay)
        for frame in frames[1:]: current_text += frame + "\n"; await message.edit_text(current_text + "</i>", parse_mode="HTML"); await asyncio.sleep(delay)
    except Exception as e: logger.warning(f"Mission animation error: {e}")
    return True
