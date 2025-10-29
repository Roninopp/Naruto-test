import logging
import json
import asyncio # Keep asyncio import if needed elsewhere, although not directly used here now
from datetime import timedelta, datetime # Keep datetime for potential future use

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
    JobQueue # Make sure JobQueue is imported if we need to explicitly create it later
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
import world_boss # Keep your world_boss import
import sudo       # Keep your sudo import
import inventory  # Import inventory module

# --- Constants ---
# --- !!! IMPORTANT: Use YOUR NEW Bot Token Here !!! ---
BOT_TOKEN = "7473579334:AAHXaUdj_5U-TjpGbEU-9xuqH1K3mNQeu2g" # Your Bot Token
# --- Make sure the correct token is above ---

START_IMAGE_URL = "https://envs.sh/r6z.jpg"

# --- Command Handlers (Core, Profile, Help, GiveEXP - unchanged) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (code is the same) ...
    user = update.effective_user
    player = db.get_player(user.id)
    help_button = InlineKeyboardButton("❓ Help & Commands", callback_data="show_main_help")
    if player:
        welcome_text = (
            f"🔥 Welcome back, {player['rank']} {player['username']} of {player['village']}! 🔥\n\n"
            "The path of the ninja is long and challenging. Continue your training, undertake perilous missions, and prove your strength against rivals!\n\n"
            "<i>What destiny awaits you today?</i>"
        )
        reply_markup = InlineKeyboardMarkup([[help_button]])
        try: await context.bot.send_photo(chat_id=update.effective_chat.id, photo=START_IMAGE_URL, caption=welcome_text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e: logger.error(f"Failed to send start photo: {e}. Sending text only."); await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        logger.info(f"New user registration started: {user.username} (ID: {user.id})")
        welcome_text = (
            f"Greetings, {user.username}! A new legend begins...\n\n"
            "✨ Welcome to the <b>Shinobi Chronicles RPG</b>! ✨\n\n"
            "Step into a world inspired by Naruto, where you'll forge your own ninja path. Here you can:\n"
            "  💪 Train to master powerful techniques\n"
            "  📜 Embark on challenging missions for glory and reward\n"
            "  🌀 Discover secret Jutsu combinations\n"
            "  ⚔️ Test your skills in thrilling PvP battles\n"
            "  🏆 Rise through the ninja ranks, from humble Academy Student to the legendary Kage!\n\n"
            "Your adventure starts now! Choose your home village wisely, as it grants unique bonuses:"
        )
        village_keyboard = [[InlineKeyboardButton(name, callback_data=f"village_{key}")] for key, name in gl.VILLAGES.items()]
        village_keyboard.append([help_button])
        reply_markup = InlineKeyboardMarkup(village_keyboard)
        try: await context.bot.send_photo(chat_id=update.effective_chat.id, photo=START_IMAGE_URL, caption=welcome_text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e: logger.error(f"Failed to send start photo: {e}. Sending text only."); await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=reply_markup)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (code is the same) ...
    user = update.effective_user
    player = db.get_player(user.id)
    if not player: await update.message.reply_text("You haven't started your journey yet! Use /start to begin."); return
    player_equipment = json.loads(player.get('equipment', '{}'))
    total_stats = gl.get_total_stats(player)
    equipment_text = ""
    for slot in ['weapon', 'armor', 'accessory']:
        item_key = player_equipment.get(slot)
        if item_key:
            item_info = gl.SHOP_INVENTORY.get(item_key)
            if item_info:
                item_stat_text = [f"+{value} {stat[:3].capitalize()}" for stat, value in item_info.get('stats', {}).items() if value > 0 and stat in total_stats]
                equipment_text += f"<b>{slot.title()}:</b> {item_info.get('name', 'Unknown Item')} ({', '.join(item_stat_text)})\n"
        else: equipment_text += f"<b>{slot.title()}:</b> None\n"
    total_max_hp = total_stats.get('max_hp', gl.BASE_HP)
    total_max_chakra = total_stats.get('max_chakra', gl.BASE_CHAKRA)
    hp_bar = gl.health_bar(player.get('current_hp', total_max_hp), total_max_hp)
    chakra_bar = gl.chakra_bar(player.get('current_chakra', total_max_chakra), total_max_chakra)
    exp_needed = gl.get_exp_for_next_level(player.get('level', 1))
    profile_text = (
        f"--- 👤 NINJA PROFILE 👤 ---\n\n"
        f"<b>Name:</b> {player.get('username', 'N/A')}\n"
        f"<b>Village:</b> {player.get('village', 'N/A')}\n"
        f"<b>Rank:</b> {player.get('rank', 'N/A')}\n"
        f"<b>Level:</b> {player.get('level', 1)}\n"
        f"<b>EXP:</b> {player.get('exp', 0)} / {exp_needed}\n"
        f"<b>Ryo:</b> {player.get('ryo', 0)} 💰\n\n"
        f"<b>HP:</b>     {hp_bar}\n"
        f"<b>Chakra:</b> {chakra_bar}\n\n"
        f"--- TOTAL STATS (with items) ---\n"
        f"<b>Str:</b> {total_stats.get('strength', 0)} (Base: {player.get('strength', 0)})\n"
        f"<b>Spd:</b> {total_stats.get('speed', 0)} (Base: {player.get('speed', 0)})\n"
        f"<b>Int:</b> {total_stats.get('intelligence', 0)} (Base: {player.get('intelligence', 0)})\n"
        f"<b>Stam:</b> {total_stats.get('stamina', 0)} (Base: {player.get('stamina', 0)})\n\n"
        f"--- EQUIPMENT ---\n{equipment_text}\n"
        f"<b>Wins:</b> {player.get('wins', 0)} | <b>Losses:</b> {player.get('losses', 0)}"
    )
    await update.message.reply_text(profile_text, parse_mode="HTML")


async def give_exp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (code is the same) ...
    user = update.effective_user
    player = db.get_player(user.id)
    if not player: await update.message.reply_text("Use /start first."); return
    try: amount = int(context.args[0])
    except (IndexError, ValueError): await update.message.reply_text("Please provide an amount, e.g., /giveexp 150"); return
    temp_player_data = dict(player); temp_player_data['exp'] += amount; temp_player_data['total_exp'] += amount
    final_player_data, leveled_up, messages = gl.check_for_level_up(temp_player_data)
    success = db.update_player(user.id, final_player_data)
    if success: await update.message.reply_text(f"Gained {amount} EXP!\n\n" + "\n".join(messages))
    else: await update.message.reply_text("An error occurred while adding EXP.")


# --- Callbacks ---
async def village_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (code is the same) ...
    query = update.callback_query; await query.answer()
    user = query.from_user; village_key = query.data.split('_', 1)[1]
    if db.get_player(user.id):
        try: await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❓ Help & Commands", callback_data="show_main_help")]]))
        except Exception as e: logger.warning(f"Error editing reply markup on village select for existing user: {e}")
        return
    username = user.username if user.username else user.first_name; village_name = gl.VILLAGES[village_key]
    success = db.create_player(user.id, username, village_name)
    original_caption = query.message.caption or ""; welcome_part = original_caption.split('Your adventure starts now!')[0] if 'Your adventure starts now!' in original_caption else original_caption + "\n\n"
    new_caption = (f"{welcome_part}" f"<b>You have joined {village_name}!</b>\n\n" "A new path is set. Your training begins now.\n" "Use /profile to check your new status.")
    edit_func = query.edit_message_caption if query.message.photo else query.edit_message_text
    if success:
        logger.info(f"User {username} chose {village_name}")
        try: await edit_func(new_caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❓ Help & Commands", callback_data="show_main_help")]]))
        except Exception as e: logger.error(f"Error editing message after village selection: {e}"); await query.message.reply_text(new_caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❓ Help & Commands", callback_data="show_main_help")]]))
    else:
        error_caption = (f"{original_caption}\n\n" "An error occurred while saving your choice. Please try /start again.")
        try: await edit_func(error_caption, reply_markup=None)
        except Exception as e: logger.error(f"Error editing message after village selection error: {e}")


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
    application.add_handler(CommandHandler("giveexp", give_exp_command))
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
    application.add_handler(CommandHandler("boss_taijutsu", world_boss.boss_taijutsu_command))
    application.add_handler(CommandHandler("boss_jutsu", world_boss.boss_jutsu_command))
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

    # Core Callbacks
    application.add_handler(CallbackQueryHandler(village_selection_callback, pattern="^village_"))
    # Help Handler Callbacks
    application.add_handler(CallbackQueryHandler(help_handler.show_main_help_menu, pattern="^show_main_help$"))
    application.add_handler(CallbackQueryHandler(help_handler.show_module_help, pattern="^help_module_"))
    application.add_handler(CallbackQueryHandler(help_handler.back_to_main_help_callback, pattern="^back_to_main_help$"))

    # --- Start the Boss Spawn Job ---
    # --- THIS IS THE FIX ---
    # Access application.job_queue directly
    try:
        if application.job_queue:
            application.job_queue.run_repeating(world_boss.spawn_world_boss, interval=3600, first=10) # Run every hour, start after 10 sec
            logger.info("World Boss spawn job scheduled.")
        else:
            logger.error("JobQueue is None! Cannot schedule World Boss spawn.")
    except Exception as e:
        logger.error(f"Error scheduling World Boss job: {e}")
    # --- END OF FIX ---


    logger.info("Bot is polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
