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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, filters # Import filters
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    JobQueue,
    MessageHandler # Import MessageHandler
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
import animations 
import akatsuki_event # <-- NEW: Import Akatsuki event

# --- Constants ---
BOT_TOKEN = "8400754472:AAGqOme2MQq_Bim_FhO2Fr_DJGuUZrBDsBc" # Your Test Bot Token
START_IMAGE_URL = "https://envs.sh/r6z.jpg" 

# --- (All core commands: start, profile - are unchanged) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (code is the same)
    pass
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (code is the same)
    pass

# --- (village_selection callback is unchanged) ---
async def village_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (code is the same)
    pass

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
    application.add_handler(CallbackQueryHandler(battle.battle_action_callback, pattern="^battle_action_")) 
    application.add_handler(CallbackQueryHandler(battle.battle_jutsu_callback, pattern="^battle_jutsu_"))   
    application.add_handler(CallbackQueryHandler(battle.battle_item_callback, pattern="^battle_item_"))     

    # World Boss 
    application.add_handler(CommandHandler("enable_world_boss", world_boss.enable_world_boss_command))
    application.add_handler(CommandHandler("boss_status", world_boss.boss_status_command))
    application.add_handler(CallbackQueryHandler(world_boss.boss_action_callback, pattern="^wb_action_")) 
    application.add_handler(CallbackQueryHandler(world_boss.boss_jutsu_callback, pattern="^boss_usejutsu_")) 

    # Sudo 
    application.add_handler(CommandHandler("server_stats", sudo.server_stats_command))
    application.add_handler(CommandHandler("db_query", sudo.db_query_command))
    application.add_handler(CommandHandler("sudo_give", sudo.sudo_give_command))
    application.add_handler(CommandHandler("sudo_set", sudo.sudo_set_command))
    application.add_handler(CommandHandler("list_boss_chats", sudo.list_boss_chats_command))
    application.add_handler(CommandHandler("sudo_leave", sudo.sudo_leave_command))
    application.add_handler(CommandHandler("get_user", sudo.get_user_command))
    application.add_handler(CommandHandler("bot_stats", sudo.bot_stats_command))
    
    # --- NEW: Akatsuki Event Handlers ---
    application.add_handler(CommandHandler(("auto_fight_off", "auto_fight_on"), akatsuki_event.toggle_auto_fight_command))
    application.add_handler(CallbackQueryHandler(akatsuki_event.akatsuki_join_callback, pattern="^akatsuki_join$"))
    application.add_handler(CallbackQueryHandler(akatsuki_event.akatsuki_action_callback, pattern="^akatsuki_action_"))
    application.add_handler(CallbackQueryHandler(akatsuki_event.akatsuki_jutsu_callback, pattern="^akatsuki_jutsu_"))
    
    # This handler passively registers groups. It must be last or have block=False
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & (~filters.COMMAND), akatsuki_event.passive_group_register), group=-1) # Run in a lower group
    # --- END NEW ---

    # Core Callbacks
    application.add_handler(CallbackQueryHandler(village_selection_callback, pattern="^village_"))
    # Help Handler Callbacks
    application.add_handler(CallbackQueryHandler(help_handler.show_main_help_menu, pattern="^show_main_help$"))
    application.add_handler(CallbackQueryHandler(help_handler.show_module_help, pattern="^help_module_"))
    application.add_handler(CallbackQueryHandler(help_handler.back_to_main_help_callback, pattern="^back_to_main_help$"))

    # Start the Job Queues
    try:
        if application.job_queue:
            # Boss Spawn Job (every 1 hour)
            application.job_queue.run_repeating(world_boss.spawn_world_boss, interval=3600, first=10)
            logger.info("World Boss spawn job scheduled (1 hour).")
            
            # --- NEW: Akatsuki Event Job (every 5 minutes for testing) ---
            application.job_queue.run_repeating(akatsuki_event.spawn_akatsuki_event, interval=300, first=20) # 300 seconds = 5 minutes
            logger.info("Akatsuki Ambush job scheduled (5 minutes).")
            # --- END NEW ---
            
        else:
            logger.error("JobQueue is None! Cannot schedule jobs. Run: pip install \"python-telegram-bot[job-queue]\"")
    except Exception as e:
        logger.error(f"Error scheduling jobs: {e}")

    logger.info("Bot is polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
