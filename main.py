import logging
import json
import asyncio 
from datetime import timedelta, datetime 

# Setup Logging FIRST
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    JobQueue 
)

# Import our code modules
import database as db
import game_logic as gl
import missions
import training
import jutsu
import battle
import cache
import shop
import help_handler
import world_boss 
import sudo       
import inventory  

# --- Constants ---
BOT_TOKEN = "8400754472:AAGqOme2MQq_Bim_FhO2Fr_DJGuUZrBDsBc" # Make sure this is your correct token
START_IMAGE_URL = "https://envs.sh/r6z.jpg"

# --- Command Handlers (Core, Profile, Help - unchanged) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (code is the same)
    user = update.effective_user; player = db.get_player(user.id)
    help_button = InlineKeyboardButton("❓ Help & Commands", callback_data="show_main_help")
    if player:
        welcome_text = (f"🔥 Welcome back, {player.get('rank', 'Ninja')} {player.get('username', 'User')} of {player.get('village', 'Unknown Village')}! 🔥\n\n" + "...")
        reply_markup = InlineKeyboardMarkup([[help_button]])
        try: await context.bot.send_photo(chat_id=update.effective_chat.id, photo=START_IMAGE_URL, caption=welcome_text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e: logger.error(f"Failed photo: {e}"); await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        username = user.username if user.username else user.first_name; logger.info(f"New user: {username} ({user.id})")
        welcome_text = (f"Greetings, {username}! A new legend begins...\n\n" + "✨ Welcome to the <b>Shinobi Chronicles RPG</b>! ✨\n\n" + "...")
        village_keyboard = [[InlineKeyboardButton(name, callback_data=f"village_{key}")] for key, name in gl.VILLAGES.items()]
        village_keyboard.append([help_button]); reply_markup = InlineKeyboardMarkup(village_keyboard)
        try: await context.bot.send_photo(chat_id=update.effective_chat.id, photo=START_IMAGE_URL, caption=welcome_text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e: logger.error(f"Failed photo: {e}"); await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=reply_markup)

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (code is the same)
    user = update.effective_user; player = db.get_player(user.id)
    if not player: await update.message.reply_text("Use /start first."); return
    # ... (rest of profile code) ...
    await update.message.reply_text(profile_text, parse_mode="HTML")


# --- Callbacks (village_selection - unchanged) ---
async def village_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
     # (code is the same)
    query = update.callback_query; await query.answer()
    user = query.from_user; village_key = query.data.split('_', 1)[1] 
    if db.get_player(user.id):
        try: await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❓ Help & Commands", callback_data="show_main_help")]]))
        except Exception as e: logger.warning(f"Error editing reply markup: {e}")
        return
    username = user.username if user.username else user.first_name; village_name = gl.VILLAGES[village_key]
    success = db.create_player(user.id, username, village_name)
    original_caption = query.message.caption or ""; welcome_part = original_caption.split('Your adventure starts now!')[0] if 'Your adventure starts now!' in original_caption else original_caption + "\n\n"
    new_caption = (f"{welcome_part}" f"<b>You have joined {village_name}!</b>\n\n" + "...")
    edit_func = query.edit_message_caption if query.message.photo else query.edit_message_text
    if success:
        logger.info(f"User {username} chose {village_name}")
        try: await edit_func(new_caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❓ Help & Commands", callback_data="show_main_help")]])) 
        except Exception as e: logger.error(f"Error editing message: {e}"); await query.message.reply_text(new_caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❓ Help & Commands", callback_data="show_main_help")]]))
    else:
        error_caption = (f"{original_caption}\n\n" + "Error saving choice.")
        try: await edit_func(error_caption, reply_markup=None)
        except Exception as e: logger.error(f"Error editing message: {e}")


# --- Main Bot Setup ---

def main():
    """Starts the bot."""
    logger.info("Starting bot...")

    db.create_tables()
    db.update_schema()

    application = Application.builder().token(BOT_TOKEN).build()

    # --- Add Handlers ---
    # Core
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("profile", profile_command))
    # application.add_handler(CommandHandler("giveexp", give_exp_command)) # REMOVED
    application.add_handler(CommandHandler("help", help_handler.show_main_help_menu)) 
    application.add_handler(CommandHandler("inventory", inventory.inventory_command))

    # Modules
    application.add_handler(CommandHandler("missions", missions.missions_command))
    application.add_handler(CallbackQueryHandler(missions.mission_callback, pattern="^mission_"))
    application.add_handler(CommandHandler("train", training.training_command))
    application.add_handler(CallbackQueryHandler(training.training_callback, pattern="^train_"))
    application.add_handler(CommandHandler("jutsus", jutsu.jutsus_command))
    application.add_handler(CommandHandler("combine", jutsu.combine_command))
    application.add_handler(CommandHandler("shop", shop.shop_command))
    application.add_handler(CallbackQueryHandler(shop.shop_buy_callback, pattern="^shop_buy_"))
    
    # Battle
    application.add_handler(CommandHandler("battle", battle.battle_command))
    application.add_handler(CallbackQueryHandler(battle.battle_invite_callback, pattern="^battle_invite_"))
    application.add_handler(CallbackQueryHandler(battle.battle_action_callback, pattern="^battle_action_")) # PvP Action
    application.add_handler(CallbackQueryHandler(battle.battle_jutsu_callback, pattern="^battle_jutsu_"))   # PvP Jutsu Select
    application.add_handler(CallbackQueryHandler(battle.battle_item_callback, pattern="^battle_item_"))     # PvP Item Select

    # World Boss 
    application.add_handler(CommandHandler("enable_world_boss", world_boss.enable_world_boss_command))
    application.add_handler(CommandHandler("boss_status", world_boss.boss_status_command))
    # --- FIX: Use correct prefix 'wb' for the handler pattern ---
    application.add_handler(CallbackQueryHandler(world_boss.boss_action_callback, pattern="^wb_action_")) 
    # --- END FIX ---
    application.add_handler(CallbackQueryHandler(world_boss.boss_jutsu_callback, pattern="^boss_usejutsu_")) # Boss Jutsu Select

    # Sudo 
    application.add_handler(CommandHandler("server_stats", sudo.server_stats_command))
    application.add_handler(CommandHandler("db_query", sudo.db_query_command))
    application.add_handler(CommandHandler("sudo_give", sudo.sudo_give_command))
    application.add_handler(CommandHandler("sudo_set", sudo.sudo_set_command))
    application.add_handler(CommandHandler("list_boss_chats", sudo.list_boss_chats_command))
    application.add_handler(CommandHandler("sudo_leave", sudo.sudo_leave_command))
    application.add_handler(CommandHandler("get_user", sudo.get_user_command))
    application.add_handler(CommandHandler("bot_stats", sudo.bot_stats_command))

    # Core Callbacks
    application.add_handler(CallbackQueryHandler(village_selection_callback, pattern="^village_"))
    # Help Handler Callbacks
    application.add_handler(CallbackQueryHandler(help_handler.show_main_help_menu, pattern="^show_main_help$")) 
    application.add_handler(CallbackQueryHandler(help_handler.show_module_help, pattern="^help_module_"))
    application.add_handler(CallbackQueryHandler(help_handler.back_to_main_help_callback, pattern="^back_to_main_help$"))

    # Start the Boss Spawn Job 
    try:
        if application.job_queue:
            application.job_queue.run_repeating(world_boss.spawn_world_boss, interval=3600, first=10) 
            logger.info("World Boss spawn job scheduled.")
        else: logger.error("JobQueue is None! Cannot schedule World Boss spawn.")
    except Exception as e: logger.error(f"Error scheduling World Boss job: {e}")

    logger.info("Bot is polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
