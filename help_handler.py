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
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    query = update.callback_query
    chat_id = query.message.chat_id if query else update.message.chat_id
    
    if query: 
        try:
            await query.answer() 
            await query.message.delete() 
        except Exception as e:
            logger.warning(f"Could not delete original message before showing help: {e}")
            
        try:
            # Send NEW message with the help image
            await context.bot.send_photo(
                chat_id=chat_id, 
                photo=HELP_IMAGE_URL,
                caption=help_caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send help photo: {e}. Sending text only.")
            await context.bot.send_message( 
                chat_id=chat_id,
                text=help_caption, 
                reply_markup=reply_markup, 
                parse_mode="HTML"
            )
            
    elif update.message: # Called via /help command
        try:
            await update.message.reply_photo( 
                photo=HELP_IMAGE_URL,
                caption=help_caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send help photo via command: {e}. Sending text only.")
            await update.message.reply_text( 
                help_caption, 
                reply_markup=reply_markup, 
                parse_mode="HTML"
            )

# --- Module-Specific Help Callbacks ---

async def show_module_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes the photo message and sends the module help as a new TEXT message."""
    query = update.callback_query
    await query.answer()

    module = query.data.split('_')[-1] 
    chat_id = query.message.chat_id
    
    help_text = f"<b>--- {module.capitalize()} Help ---</b>\n\n"
    
    # (Detailed help texts are correct and complete here)
    if module == "profile":
        help_text += "Your Ninja Profile shows your complete status.\n\n"
        help_text += "<b>Command:</b> /profile\n\n"
        help_text += "<b>Displays:</b>\n"
        help_text += " • <b>Name, Village, Rank:</b> Your identity.\n"
        help_text += " • <b>Level & EXP:</b> Your progress. EXP needed for next level is shown (Level * 150).\n"
        help_text += " • <b>Ryo:</b> Your currency, earned from missions and battles.\n"
        help_text += " • <b>HP & Chakra Bars:</b> Your current health and energy.\n"
        help_text += " • <b>Total Stats:</b> Strength (Str), Speed (Spd), Intelligence (Int), Stamina (Stam). Includes bonuses from equipment.\n"
        help_text += " • <b>Base Stats:</b> Your stats without item bonuses.\n"
        help_text += " • <b>Equipment:</b> Items currently equipped (Weapon, Armor).\n"
        help_text += " • <b>Wins/Losses:</b> Your PvP battle record."
        
    elif module == "missions":
        help_text += "Missions are your primary way to gain Experience (EXP) and Ryo.\n\n"
        help_text += "<b>Command:</b> /missions\n\n"
        help_text += "<b>How it Works:</b>\n"
        help_text += " • The command lists available missions.\n"
        help_text += " • Missions have a <b>Level Requirement</b> (e.g., Lvl 10+). Locked missions show 🔒.\n"
        help_text += " • Click the button for an unlocked mission to start it.\n"
        help_text += " • An animation plays, showing the mission progress.\n"
        help_text += " • Upon completion, you receive EXP and Ryo automatically.\n"
        help_text += " • Gaining EXP can lead to a <b>Level Up</b>!\n\n"
        help_text += "<i>(Future Update: Higher rank missions will involve challenging PvE battles!)</i>"
        
    elif module == "training":
        help_text += "Training allows you to permanently increase your base stats.\n\n"
        help_text += "<b>Command:</b> /train\n\n"
        help_text += "<b>How it Works:</b>\n"
        help_text += " • The command shows available training options.\n"
        help_text += " • Click a button (e.g., <b>Chakra Control</b> or <b>Taijutsu</b>).\n"
        help_text += " • An animation plays.\n"
        help_text += " • Your corresponding base stat is increased (e.g., Max Chakra or Strength).\n\n"
        help_text += "<i>(Note: Training takes time in some games, but here it's instant for now.)</i>"
        
    elif module == "jutsu":
        help_text += "<b>🌀 Jutsu & Discovery 🌀</b>\n\n"
        help_text += "Master powerful Ninja Techniques!\n\n"
        help_text += "<b>Listing Your Jutsus:</b>\n"
        help_text += " • Command: /jutsus\n"
        help_text += " • Shows all jutsus you have learned, including their element, power, chakra cost, and required hand signs.\n\n"
        help_text += "<b>Discovering New Jutsus:</b>\n"
        help_text += " • Command: /combine [sign1] [sign2] ...\n"
        help_text += " • Example: `/combine tiger snake bird`\n"
        help_text += " • Experiment with different combinations of the 10 hand signs:\n   <i>tiger, snake, dog, bird, ram, boar, hare, rat, monkey, dragon</i>\n"
        help_text += " • If the combination is correct AND you meet the jutsu's <b>Level Requirement</b> (e.g., Level 5 for Fireball), you will learn the jutsu!\n"
        help_text += " • If the combination is wrong, nothing happens.\n"
        help_text += " • If you don't meet the level requirement, you'll feel the chakra but fail to learn it."
        
    elif module == "battle":
        help_text += "<b>⚔️ Player vs Player Battle ⚔️</b>\n\n"
        help_text += "Challenge other ninjas in the group to test your skills!\n\n"
        help_text += "<b>How to Challenge:</b>\n"
        help_text += " • <b>Reply</b> to a message written by the player you want to fight.\n"
        help_text += " • Type the command: /battle\n\n"
        help_text += "<b>Accepting/Declining:</b>\n"
        help_text += " • The challenged player will see buttons to ✅ Accept or ❌ Decline.\n\n"
        help_text += "<b>Gameplay:</b>\n"
        help_text += " • Battles are turn-based. Higher Speed (including item bonuses) increases the chance to go first.\n"
        help_text += " • The battle menu shows both players' HP.\n"
        help_text += " • On your turn, choose an action:\n"
        help_text += "    - <b>⚔️ Taijutsu:</b> A basic physical attack. Damage scales with your total Strength. Costs no Chakra.\n"
        help_text += "    - <b>🌀 Use Jutsu:</b> Opens a list of your known jutsus. Select one to use. Costs Chakra. Requires Level 5+ to access.\n"
        help_text += "    - <b>🏃 Flee:</b> Attempt to escape. Success chance is 50%.\n"
        help_text += " • Attacks and Jutsus play animations directly in the battle message (no spam!).\n"
        help_text += " • Watch for <b>Critical Hits</b> (extra damage!) and <b>Elemental Effects</b> (Jutsus can be stronger or weaker depending on your opponent's village element).\n\n"
        help_text += "<b>Winning & Cooldown:</b>\n"
        help_text += " • Defeat your opponent (reduce HP to 0) to win.\n"
        help_text += " • Winners gain EXP and Ryo based on the loser's level.\n"
        help_text += " • Both players receive a 5-minute battle cooldown."

    elif module == "shop":
        help_text += "The Shop is where you spend Ryo to get stronger.\n\n"
        help_text += "<b>Command:</b> /shop\n\n"
        help_text += "<b>How it Works:</b>\n"
        help_text += " • The command lists items for sale with their price and effects.\n"
        help_text += " • Click an item's button to buy it.\n"
        help_text += " • You must have enough Ryo. If not, you'll get an alert.\n"
        help_text += " • <b>Equipment</b> (⚔️ Weapons, 🛡️ Armor) is automatically equipped when bought, replacing any previous item in that slot.\n"
        help_text += " • Equipment provides stat bonuses (e.g., +Strength, +Stamina) which are added to your base stats.\n"
        help_text += " • Your <b>Total Stats</b> (Base + Items) are shown in /profile and used in battle calculations.\n"
        help_text += " • <b>Consumables</b> (like Health Potions) are added to your inventory (use /inventory - command coming soon!)."
        
    else:
        help_text = "Help information for this module is not available yet."
    # --- END OF DETAILED TEXTS ---

    keyboard = [[InlineKeyboardButton("⬅️ Back to Help Menu", callback_data="back_to_main_help")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # --- NEW: Always delete photo and send text ---
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete help photo message: {e}")
        
    try:
        await context.bot.send_message( # Send as NEW message
            chat_id=chat_id,
            text=help_text, 
            reply_markup=reply_markup, 
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send help text message for {module}: {e}")
    # --- END OF NEW LOGIC ---


# --- Back Button Callback ---

async def back_to_main_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Back' button press. Deletes old text message and resends photo menu."""
    query = update.callback_query
    
    # Delete the text message
    try:
        await query.answer()
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete text help message on back button: {e}")
        
    # Resend the main help menu (which includes the photo)
    # We pass 'update' which contains the necessary chat_id info inside query.message
    await show_main_help_menu(update, context)
