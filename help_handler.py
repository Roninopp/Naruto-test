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
    
    # --- FIX: Match the buttons in your screenshot ---
    keyboard = [
        [InlineKeyboardButton("👤 PROFILE INFO", callback_data="help_module_profile"), 
         InlineKeyboardButton("🗺️ Mission Guide", callback_data="help_module_missions")],
        [InlineKeyboardButton("💪 SPECIAL TRAINING", callback_data="help_module_training"), 
         InlineKeyboardButton("🌀 Jutsu & Discovery", callback_data="help_module_jutsu")],
        [InlineKeyboardButton("⚔️ BATTLE MODES", callback_data="help_module_battle"), 
         InlineKeyboardButton("🛒 Shop Guide", callback_data="help_module_shop")],
        [InlineKeyboardButton("👹 BOSS SPWAN", callback_data="help_module_boss"), 
         InlineKeyboardButton("🔥 Akatsuki Ambush", callback_data="help_module_akatsuki")]
    ]
    # --- END FIX ---
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
    
    # --- FIX: Added complete help text ---
    help_text = ""
    
    if module == "profile":
        help_text += "<b>--- 👤 Profile Help 👤 ---</b>\n\n"
        help_text += "Your profile is your ninja identity. It shows all your stats and progress.\n\n"
        help_text += "  •  `/profile`: Shows your stats, level, EXP, Ryo, and equipped items.\n"
        help_text += "  •  `/inventory`: Shows all consumable items you have bought, like Health Potions.\n"
        help_text += "  •  **Level**: Gain EXP from missions and battles to level up.\n"
        help_text += "  •  **Stats**: Stats increase automatically on level up.\n"
        help_text += "    - **Str (Strength)**: Increases Taijutsu damage.\n"
        help_text += "    - **Spd (Speed)**: Increases chance to go first in battle and critical hit chance.\n"
        help_text += "    - **Int (Intelligence)**: Increases Jutsu damage and Max Chakra.\n"
        help_text += "    - **Stam (Stamina)**: Increases your Max HP.\n"
        
    elif module == "missions":
        help_text += "<b>--- 🗺️ Mission Help 🗺️ ---</b>\n\n"
        help_text += "Missions are the main way to get EXP and Ryo (money).\n\n"
        help_text += "  •  Use `/missions` to open the mission board.\n"
        help_text += "  •  Select a mission you meet the level requirement for.\n"
        help_text += "  •  Higher-rank missions give much better rewards but require a higher level."

    elif module == "training":
        help_text += "<b>--- 💪 Training Help 💪 ---</b>\n\n"
        help_text += "Training permanently increases your base stats, but you can only do it a few times per day.\n\n"
        help_text += "  •  Use `/train` to see available training.\n"
        help_text += "  •  **Chakra Control**: Increases your Max Chakra.\n"
        help_text += "  •  **Taijutsu**: Increases your Strength."

    elif module == "jutsu":
        help_text += "<b>--- 🌀 Jutsu & Discovery 🌀 ---</b>\n\n"
        help_text += "Jutsus are powerful attacks used in battle. You must discover them first!\n\n"
        help_text += "  •  `/jutsus`: Lists all the jutsus you have learned.\n"
        help_text += "  •  `/combine [signs]`: Try to discover a new jutsu by combining hand signs.\n\n"
        help_text += "<b>Example:</b>\n`/combine tiger snake bird`\n\n"
        help_text += "If the combination is correct, you will learn a new jutsu!"

    elif module == "battle":
        help_text += "<b>--- ⚔️ Battle Help ⚔️ ---</b>\n\n"
        help_text += "Challenge other ninjas in the group to a 1v1 battle.\n\n"
        help_text += "  •  To challenge, reply to another user's message and type `/battle`.\n"
        help_text += "  •  The winner gains EXP and Ryo!\n"
        help_text += "  •  **Taijutsu**: A basic attack based on your Strength.\n"
        help_text += "  •  **Use Jutsu**: Use your learned jutsus. This costs Chakra.\n"
        help_text += "  •  **Use Item**: Use a consumable item from your inventory, like a Health Potion."

    elif module == "shop":
        help_text += "<b>--- 🛒 Shop Help 🛒 ---</b>\n\n"
        help_text += "Use your Ryo to buy new equipment and items.\n\n"
        help_text += "  •  Use `/shop` to open the item list.\n"
        help_text += "  •  **Equipment**: (Weapons, Armor) These are equipped automatically and boost your stats.\n"
        help_text += "  •  **Consumables**: (Health Potion) These are added to your `/inventory` to be used in battle."

    elif module == "boss":
        help_text += "👹 --- **World Boss Spawn Guide** --- 👹\n\n"
        help_text += "A World Boss is a massive enemy that everyone in the group can attack together!\n\n"
        help_text += "  •  A boss will spawn automatically every **1 hour**.\n"
        help_text += "  •  Use the buttons to attack (Taijutsu, Kunai, Jutsu).\n"
        help_text += "  •  Attacking costs a small amount of HP (recoil damage).\n"
        help_text += "  •  When the boss is defeated, the **Ryo Pool** is divided among all attackers based on how much damage they dealt."

    elif module == "akatsuki":
        help_text += "<b>--- 🔥 Akatsuki Ambush --- 🔥</b>\n\n"
        help_text += "This is an automatic event where a rogue ninja ambushes the group!\n\n"
        help_text += "  •  An event will spawn automatically every **3 hours**.\n"
        help_text += "  •  Up to **3 players** can click the button to join the fight.\n"
        help_text += "  •  It is a turn-based battle. The 3 players take their turns, then the AI attacks.\n"
        help_text += "  •  If the event is not finished after 3 hours, it will expire and a new one will be sent.\n\n"
        help_text += "<b>Rewards:</b>\n"
        help_text += " • If your team wins, all 3 participants get **+110 EXP** and **+180 Ryo**!\n\n"
        help_text += "<b>Admin Command (Opt-Out):</b>\n"
        help_text += " • Group admins can use /auto_fight_off to stop these events."
    
    else:
        help_text = "Help information for this module is not available yet."
    # --- END FIX ---

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
