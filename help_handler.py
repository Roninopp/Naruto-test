import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

HELP_IMAGE_URL = "https://envs.sh/r6f.jpg" 

# --- Main Help Menu ---

async def show_main_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the main help menu, deleting the old message if called from a button."""
    
    help_caption = "<b>--- ❓ Bot Help & Commands ❓ ---</b>\n\n"
    help_caption += "Select a topic below for detailed instructions:"
    
    keyboard = [
        [InlineKeyboardButton("👤 Profile Info", callback_data="help_module_profile"), InlineKeyboardButton("🗺️ Mission Guide", callback_data="help_module_missions")],
        [InlineKeyboardButton("💪 How to Train", callback_data="help_module_training"), InlineKeyboardButton("🌀 Jutsu & Discovery", callback_data="help_module_jutsu")],
        [InlineKeyboardButton("⚔️ Battle Guide", callback_data="help_module_battle"), InlineKeyboardButton("🛒 Shop Guide", callback_data="help_module_shop")],
        [InlineKeyboardButton("👹 Boss Spawn Guide", callback_data="help_module_boss")],
        # --- NEW: Akatsuki Event Button ---
        [InlineKeyboardButton("🔥 Akatsuki Ambush", callback_data="help_module_akatsuki")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    query = update.callback_query
    chat_id = query.message.chat_id if query else update.message.chat_id
    
    if query: 
        try: await query.answer(); await query.message.delete() 
        except Exception as e: logger.warning(f"Could not delete old help message: {e}")
        try:
            await context.bot.send_photo(
                chat_id=chat_id, photo=HELP_IMAGE_URL, caption=help_caption,
                reply_markup=reply_markup, parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send help photo: {e}. Sending text only.")
            await context.bot.send_message( 
                chat_id=chat_id, text=help_caption, 
                reply_markup=reply_markup, parse_mode="HTML"
            )
            
    elif update.message: # Called via /help command
        try:
            await update.message.reply_photo( 
                photo=HELP_IMAGE_URL, caption=help_caption,
                reply_markup=reply_markup, parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send help photo via command: {e}. Sending text only.")
            await update.message.reply_text( 
                help_caption, reply_markup=reply_markup, parse_mode="HTML"
            )

# --- Module-Specific Help Callbacks ---

async def show_module_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes the photo message and sends the module help as a new TEXT message."""
    query = update.callback_query
    await query.answer()

    module = query.data.split('_')[-1] 
    chat_id = query.message.chat_id
    
    help_text = f"<b>--- {module.capitalize()} Help ---</b>\n\n"
    
    # (All existing help text (profile, missions, etc.) is the same)
    if module == "profile":
        help_text += "Your Ninja Profile shows your complete status.\n\n" # ...
    elif module == "missions":
        help_text += "Missions are your primary way to gain Experience (EXP) and Ryo.\n\n" # ...
    elif module == "training":
        help_text += "Training allows you to permanently increase your base stats.\n\n" # ...
    elif module == "jutsu":
        help_text += "<b>🌀 Jutsu & Discovery 🌀</b>\n\n" # ...
    elif module == "battle":
        help_text += "<b>⚔️ Player vs Player Battle ⚔️</b>\n\n" # ...
    elif module == "shop":
        help_text += "The Shop is where you spend Ryo to get stronger.\n\n" # ...
    elif module == "boss":
        help_text += "👹 --- **World Boss Spawn Guide** --- 👹\n\n" # ...
    
    # --- NEW: Akatsuki Event Help Text ---
    elif module == "akatsuki":
        help_text += "<b>🔥 --- Akatsuki Ambush --- 🔥</b>\n\n"
        help_text += "This is an automatic event to attract new players!\n\n"
        help_text += "<b>How it Works:</b>\n"
        help_text += " • Every **5 minutes** (for testing), an Akatsuki member will ambush the group.\n"
        help_text += " • A message appears: `[⚔️ Protect Village!]`\n"
        help_text += " • Up to **3 players** can click the button to join the fight.\n"
        help_text += " • If you are the 4th, a pop-up will say the fight is full.\n\n"
        help_text += "<b>Battle Gameplay:</b>\n"
        help_text += " • This is a turn-based, animated battle (no spam!).\n"
        help_text += " • You have new attacks just for this event:\n"
        help_text += "    - `[🔰 Throw Kunai]`: Fast, low damage, short cooldown.\n"
        help_text += "    - `[💥 Paper Bomb]`: Stronger, medium damage, longer cooldown.\n"
        help_text += "    - `[🌀 Use Jutsu]`: Your strongest attack! Requires Level 5+ and Chakra.\n"
        help_text += " • The 3 players take their turns, then the AI (e.g., Sasuke) attacks one player randomly.\n\n"
        help_text += "<b>Rewards:</b>\n"
        help_text += " • If your team wins, all 3 participants get **+110 EXP** and **+180 Ryo**!\n\n"
        help_text += "<b>Admin Command (Opt-Out):</b>\n"
        help_text += " • If you are a group admin, you can use /auto_fight_off to stop these events in your group."
    # --- END NEW ---
    
    else:
        help_text = "Help information for this module is not available yet."

    keyboard = [[InlineKeyboardButton("⬅️ Back to Help Menu", callback_data="back_to_main_help")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try: await query.message.delete()
    except Exception as e: logger.warning(f"Could not delete help photo message: {e}")
        
    try:
        await context.bot.send_message( 
            chat_id=chat_id, text=help_text, 
            reply_markup=reply_markup, parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send help text message for {module}: {e}")

# --- Back Button Callback (unchanged) ---
async def back_to_main_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (code is the same)
    query = update.callback_query
    try: await query.answer(); await query.message.delete()
    except Exception as e: logger.warning(f"Could not delete text help message on back: {e}")
    await show_main_help_menu(update, context)
