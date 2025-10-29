import logging
import json
import random 
import asyncio # <-- NEW: For the job queue loop
from datetime import timedelta 

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
import protecc # <-- NEW: Import the protecc module

# --- Constants ---
BOT_TOKEN = "8400754472:AAFzBj_SsUh7BAuIcBO27kHPxQ9W3KnFZpQ" 
START_IMAGE_URL = "https://envs.sh/r6z.jpg" 

# --- REMOVED TARGET_CHAT_ID ---

# --- NEW: Protecc Auto-Post Function (Updated) ---
async def post_new_character(context: ContextTypes.DEFAULT_TYPE):
    """Fetches a random character and posts it to all enabled chats."""
    logger.info("PROTECC JOB: Running...")
    
    # 1. Get list of all enabled chat IDs from the DB
    enabled_chat_ids = db.get_all_protecc_chats()
    if not enabled_chat_ids:
        logger.info("PROTECC JOB: No enabled chats. Skipping post.")
        return

    # 2. Pick a random character from the full list in game_logic
    char_key, char_data = random.choice(list(gl.PROTECC_CHARACTERS.items()))
    
    # 3. Add the 'key' (the lowercase name to guess) to the dict
    spotlight_data = char_data.copy()
    spotlight_data['key'] = char_key
    
    # 4. Save this as the *new* current character in the DB
    db.update_current_spotlight(spotlight_data)
    logger.info(f"PROTECC JOB: New spotlight set to {spotlight_data['name']}")

    # 5. Prepare the message caption
    rarity_info = gl.PROTECC_RARITIES[spotlight_data['rarity']]
    caption = (
        f"🎴 <b>Character Spotlight!</b> 🎴\n\n"
        f"A new character has appeared! Guess their full name to collect them.\n\n"
        f"<b>Name:</b> {spotlight_data['name']}\n"
        f"<b>Rarity:</b> {rarity_info['emoji']} {spotlight_data['rarity'].title()}\n"
        f"<b>Series:</b> {spotlight_data['series']}\n\n"
        # --- THIS IS THE FIX ---
        f"Use: `/proteec [full name]`"
        # --- END OF FIX ---
    )

    # 6. Loop and send to all chats
    logger.info(f"PROTECC JOB: Sending to {len(enabled_chat_ids)} chats...")
    for chat_id in enabled_chat_ids:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=spotlight_data['image'],
                caption=caption,
                parse_mode="HTML"
            )
            # Wait 0.5 seconds between sends to avoid rate-limiting
            await asyncio.sleep(0.5) 
            
        except Exception as e:
            # If bot is kicked or blocked, it will fail. Log it and continue.
            logger.error(f"Failed to post spotlight to chat {chat_id}: {e}")
            # We could add logic here to remove the chat_id if the error is "Forbidden: bot was kicked"
    
    logger.info("PROTECC JOB: Finished sending all posts.")


# --- Command Handlers (Core) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command with photo and interactive help button."""
    user = update.effective_user
    player = db.get_player(user.id) 

    help_button = InlineKeyboardButton("❓ Help & Commands", callback_data="show_main_help")
    
    if player:
        # Returning Player
        welcome_text = (
            f"🔥 Welcome back, {player['rank']} {player['username']} of {player['village']}! 🔥\n\n"
            "The path of the ninja is long and challenging. Continue your training, undertake perilous missions, and prove your strength against rivals!\n\n"
            "<i>What destiny awaits you today?</i>"
        )
        reply_markup = InlineKeyboardMarkup([[help_button]]) 
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=START_IMAGE_URL,
                caption=welcome_text,
                parse_mode="HTML", 
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send start photo: {e}. Sending text only.")
            await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=reply_markup)

    else:
        # New Player Registration
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
        
        village_keyboard = [
            [InlineKeyboardButton(name, callback_data=f"village_{key}")]
            for key, name in gl.VILLAGES.items()
        ]
        village_keyboard.append([help_button]) 
        
        reply_markup = InlineKeyboardMarkup(village_keyboard)
        
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=START_IMAGE_URL,
                caption=welcome_text,
                parse_mode="HTML", 
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send start photo: {e}. Sending text only.")
            await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=reply_markup)

# --- Other Commands (profile, give_exp, etc. - no changes needed) ---
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (code is the same) ...
    user = update.effective_user
    player = db.get_player(user.id)

    if not player:
        await update.message.reply_text("You haven't started your journey yet! Use /start to begin.")
        return

    player_equipment = json.loads(player.get('equipment', '{}')) 
    total_stats = gl.get_total_stats(player) 
    
    equipment_text = ""
    for slot in ['weapon', 'armor', 'accessory']: 
        item_key = player_equipment.get(slot) 
        if item_key:
            item_info = gl.SHOP_INVENTORY.get(item_key)
            if item_info:
                item_stat_text = []
                for stat, value in item_info.get('stats', {}).items(): 
                    if value > 0 and stat in total_stats:
                        item_stat_text.append(f"+{value} {stat[:3].capitalize()}") 
                
                equipment_text += f"<b>{slot.title()}:</b> {item_info.get('name', 'Unknown Item')} ({', '.join(item_stat_text)})\n"
        else:
            equipment_text += f"<b>{slot.title()}:</b> None\n"

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

    if not player:
        await update.message.reply_text("Use /start first.")
        return

    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Please provide an amount, e.g., /giveexp 150")
        return

    temp_player_data = dict(player)
    temp_player_data['exp'] += amount
    temp_player_data['total_exp'] += amount
    final_player_data, leveled_up, messages = gl.check_for_level_up(temp_player_data)
    
    success = db.update_player(user.id, final_player_data)

    if success:
        await update.message.reply_text(f"Gained {amount} EXP!\n\n" + "\n".join(messages))
    else:
        await update.message.reply_text("An error occurred while adding EXP.")


# --- Callbacks (village_selection - simplified) ---

async def village_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    village_key = query.data.split('_', 1)[1] 
    
    if db.get_player(user.id):
         # Just ensure the help button is there if they click again
         await query.edit_message_reply_markup(
              reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❓ Help & Commands", callback_data="show_main_help")]])
         )
         return

    username = user.username if user.username else user.first_name
    village_name = gl.VILLAGES[village_key]
    
    success = db.create_player(user.id, username, village_name)
    
    original_caption = query.message.caption or ""
    welcome_part = original_caption.split('Your adventure starts now!')[0] if 'Your adventure starts now!' in original_caption else original_caption + "\n\n"

    new_caption = (
        f"{welcome_part}" 
        f"<b>You have joined {village_name}!</b>\n\n"
        "A new path is set. Your training begins now.\n"
        "Use /profile to check your new status."
    )
    
    if success:
        logger.info(f"User {username} chose {village_name}")
        try:
            # Edit original photo caption
            await query.edit_message_caption( 
                caption=new_caption,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❓ Help & Commands", callback_data="show_main_help")]]) 
            )
        except Exception as e:
            logger.error(f"Error editing caption after village selection: {e}")
            # Fallback if edit fails
            await query.message.reply_text(new_caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❓ Help & Commands", callback_data="show_main_help")]]))
            
    else:
        error_caption = (
             f"{original_caption}\n\n"
             "An error occurred while saving your choice. Please try /start again."
        )
        try:
             await query.edit_message_caption(caption=error_caption, reply_markup=None)
        except Exception as e:
             logger.error(f"Error editing caption after village selection error: {e}")


# --- Main Bot Setup ---

def main():
    """Starts the bot."""
    logger.info("Starting bot...")
    
    db.create_tables()
    db.update_schema()

    application = Application.builder().token(BOT_TOKEN).build()

    # --- Add Handlers ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("giveexp", give_exp_command))
    application.add_handler(CommandHandler("help", help_handler.show_main_help_menu)) 
    
    application.add_handler(CommandHandler("missions", missions.missions_command))
    application.add_handler(CallbackQueryHandler(missions.mission_callback, pattern="^mission_"))
    application.add_handler(CommandHandler("train", training.training_command))
    application.add_handler(CallbackQueryHandler(training.training_callback, pattern="^train_"))
    application.add_handler(CommandHandler("jutsus", jutsu.jutsus_command))
    application.add_handler(CommandHandler("combine", jutsu.combine_command))
    application.add_handler(CommandHandler("battle", battle.battle_command))
    application.add_handler(CallbackQueryHandler(battle.battle_invite_callback, pattern="^battle_invite_"))
    application.add_handler(CallbackQueryHandler(battle.battle_action_callback, pattern="^battle_action_"))
    application.add_handler(CallbackQueryHandler(battle.battle_jutsu_callback, pattern="^battle_jutsu_"))
    application.add_handler(CommandHandler("shop", shop.shop_command))
    application.add_handler(CallbackQueryHandler(shop.shop_buy_callback, pattern="^shop_buy_"))
    application.add_handler(CallbackQueryHandler(village_selection_callback, pattern="^village_"))
    
    # --- NEW: PROTECC HANDLERS ---
    application.add_handler(CommandHandler("enable_protecc", protecc.enable_protecc_command))
    application.add_handler(CommandHandler("proteec", protecc.proteec_command))
    application.add_handler(CommandHandler("collection", protecc.collection_command))
    application.add_handler(CommandHandler("proteecstats", protecc.proteec_stats_command))
    # --- END NEW ---

    # --- Help Handler Callbacks (Corrected Prefix) ---
    application.add_handler(CallbackQueryHandler(help_handler.show_main_help_menu, pattern="^show_main_help$")) 
    application.add_handler(CallbackQueryHandler(help_handler.show_module_help, pattern="^help_module_"))
    application.add_handler(CallbackQueryHandler(help_handler.back_to_main_help_callback, pattern="^back_to_main_help$"))

    # --- NEW: START THE JOB QUEUE ---
    job_queue = application.job_queue
    # Run 'post_new_character' every 2 minutes (120 seconds)
    # first=1 means it runs 1 second after startup for immediate testing
    job_queue.run_repeating(post_new_character, interval=120, first=1)
    logger.info("Character spotlight job scheduled for every 2 minutes.")
    # --- END NEW ---

    logger.info("Bot is polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
