import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.error import BadRequest
from telegram.ext import ContextTypes
import game_logic as gl 
from html import escape

logger = logging.getLogger(__name__)

HELP_IMAGE_URL = "https://envs.sh/r6f.jpg" 

# --- Main Help Menu ---

async def show_main_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the main help menu, ALWAYS sending a new photo message."""
    
    help_caption = "<b>--- ❓ Bot Help & Commands ❓ ---</b>\n\n"
    help_caption += "Select a topic below for detailed instructions:"
    
    keyboard = [
        [InlineKeyboardButton("👤 PROFILE INFO", callback_data="help_module_profile"), 
         InlineKeyboardButton("🗺️ Mission Guide", callback_data="help_module_missions")],
        [InlineKeyboardButton("💪 SPECIAL TRAINING", callback_data="help_module_training"), 
         InlineKeyboardButton("🌀 Jutsu & Discovery", callback_data="help_module_jutsu")],
        [InlineKeyboardButton("⚔️ BATTLE MODES", callback_data="help_module_battle"), 
         InlineKeyboardButton("🛒 Shop Guide", callback_data="help_module_shop")],
        [InlineKeyboardButton("👹 BOSS SPAWN", callback_data="help_module_boss"), 
         InlineKeyboardButton("🔥 Akatsuki Ambush", callback_data="help_module_akatsuki")],
        [InlineKeyboardButton("🎲 Mini-Games", callback_data="help_module_minigames"),
         InlineKeyboardButton("🎮 Advanced Games", callback_data="help_module_minigames_v2")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    query = update.callback_query
    chat_id = query.message.chat_id if query else update.message.chat_id
    
    if query: 
        # If called from a button, try to delete the old message first
        try: await query.answer(); await query.message.delete() 
        except Exception as e: logger.warning(f"Could not delete old help message: {e}")
        
    # Always send a fresh photo message for the main menu
    try:
        await context.bot.send_photo(
            chat_id=chat_id, photo=HELP_IMAGE_URL, caption=help_caption,
            reply_markup=reply_markup, parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send main help photo: {e}. Sending text only.")
        await context.bot.send_message( 
            chat_id=chat_id, text=help_caption, 
            reply_markup=reply_markup, parse_mode="HTML"
        )

# --- Module-Specific Help Callbacks ---

async def show_module_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes the photo message and sends the module help as a new TEXT message."""
    query = update.callback_query
    await query.answer()

    module = query.data.split('_')[-1] 
    chat_id = query.message.chat_id
    
    help_text = ""
    
    # Default Back Button
    keyboard = [[InlineKeyboardButton("⬅️ Back to Help Menu", callback_data="back_to_main_help")]]

    if module == "profile":
        help_text += "<b>--- 👤 Profile Help 👤 ---</b>\n\n"
        help_text += "Your profile is your ninja identity. It shows all your stats and progress.\n\n"
        help_text += "  •  <code>/profile</code>: Shows your stats, level, EXP, Ryo, and equipped items.\n"
        help_text += "  •  <code>/inventory</code>: Shows all consumable items you have bought, like Health Potions.\n"
        help_text += "  •  <code>/wallet</code> (or <code>/bal</code>): A quick way to show your Rank, Level, and Ryo to the group.\n\n"
        help_text += "  •  <b>Level</b>: Gain EXP from missions and battles to level up.\n"
        help_text += "  •  <b>Stats</b>: Stats increase automatically on level up.\n"
        help_text += "    - <b>Str (Strength)</b>: Increases Taijutsu damage.\n"
        help_text += "    - <b>Spd (Speed)</b>: Increases chance to go first in battle and critical hit chance.\n"
        help_text += "    - <b>Int (Intelligence)</b>: Increases Jutsu damage and Max Chakra.\n"
        help_text += "    - <b>Stam (Stamina)</b>: Increases your Max HP.\n"
        
    elif module == "missions":
        help_text += "<b>--- 🗺️ Mission Help 🗺️ ---</b>\n\n"
        help_text += "Missions are the main way to get EXP and Ryo (money).\n\n"
        help_text += "  •  Use <code>/missions</code> to open the mission board.\n"
        help_text += "  •  Select a mission you meet the level requirement for.\n"
        help_text += "  •  Higher-rank missions give much better rewards but require a higher level."

    elif module == "training":
        help_text += "<b>--- 💪 Training Help 💪 ---</b>\n\n"
        help_text += "Training permanently increases your base stats, but you can only do it a few times per day.\n\n"
        help_text += "  •  Use <code>/train</code> to see available training.\n"
        help_text += "  •  <b>Chakra Control</b>: Increases your Max Chakra.\n"
        help_text += "  •  <b>Taijutsu</b>: Increases your Strength.\n\n"
        help_text += "💡 <b>TIP:</b> Training also fully restores your HP and Chakra, so it's a great way to heal after a battle!"

    elif module == "jutsu":
        help_text += "<b>--- 🌀 Jutsu &amp; Discovery 🌀 ---</b>\n\n"
        help_text += "Jutsus are powerful attacks used in battle. You must discover them first!\n\n"
        help_text += "  •  <code>/jutsus</code>: Lists all the jutsus you have learned.\n"
        help_text += "  •  <code>/combine [signs]</code>: Try to discover a new jutsu by combining hand signs.\n\n"
        help_text += "<b>Example:</b>\n<code>/combine tiger snake bird</code>\n\n"
        help_text += "<b>--- Available Hand Signs ---</b>\n"
        help_text += "You must combine these in the correct order to learn a new jutsu:\n\n"
        signs_list = " • ".join([escape(sign.title()) for sign in gl.HAND_SIGNS])
        help_text += f"<code>{signs_list}</code>"

    elif module == "battle":
        help_text += "<b>--- ⚔️ Battle Help ⚔️ ---</b>\n\n"
        help_text += "Challenge other ninjas in the group to a 1v1 battle.\n\n"
        help_text += "  •  To challenge, reply to another user's message and type <code>/battle</code>.\n"
        help_text += "  •  The winner gains EXP and Ryo!\n"
        help_text += "  •  <b>Taijutsu</b>: A basic attack based on your Strength.\n"
        help_text += "  •  <b>Use Jutsu</b>: Use your learned jutsus. This costs Chakra.\n"
        help_text += "  •  <b>Use Item</b>: Use a consumable item from your inventory, like a Health Potion."

    elif module == "shop":
        help_text += "<b>--- 🛒 Shop Help 🛒 ---</b>\n\n"
        help_text += "Use your Ryo to buy new equipment and items.\n\n"
        help_text += "  •  Use <code>/shop</code> to open the item list.\n"
        help_text += "  •  <b>Equipment</b>: (Weapons, Armor) These are equipped automatically and boost your stats.\n"
        help_text += "  •  <b>Consumables</b>: (Health Potion) These are added to your <code>/inventory</code> to be used in battle."

    elif module == "boss":
        help_text += "<b>--- 👹 World Boss Spawn Guide 👹 ---</b>\n\n"
        help_text += "A World Boss is a massive enemy that everyone in the group can attack together!\n\n"
        help_text += "  •  A boss will spawn automatically every <b>1 hour</b>.\n"
        help_text += "  •  Use the buttons to attack (Taijutsu, Kunai, Jutsu).\n"
        help_text += "  •  Attacking costs a small amount of HP (recoil damage).\n"
        help_text += "  •  When the boss is defeated, the <b>Ryo Pool</b> is divided among all attackers based on how much damage they dealt."

    elif module == "akatsuki":
        help_text += "<b>--- 🔥 Akatsuki Ambush 🔥 ---</b>\n\n"
        help_text += "This is an automatic event where a rogue ninja ambushes the group!\n\n"
        help_text += "  •  An event will spawn automatically every <b>3 hours</b>.\n"
        help_text += "  •  Up to <b>3 players</b> can click the button to join the fight.\n"
        help_text += "  •  It is a turn-based battle. The 3 players take their turns, then the AI attacks.\n"
        help_text += "  •  If the event is not finished after 3 hours, it will expire and a new one will be sent.\n\n"
        help_text += "<b>Rewards:</b>\n"
        help_text += " • If your team wins, all 3 participants get <b>+110 EXP</b> and <b>+180 Ryo</b>!\n\n"
        help_text += "<b>Admin Command (Opt-Out):</b>\n"
        help_text += " • Group admins can use <code>/auto_fight_off</code> to stop these events."
    
    elif module == "minigames":
        help_text += "<b>--- 🎲 Mini-Games Help 🎲 ---</b>\n\n"
        help_text += "Fun commands to interact with other players and earn rewards.\n\n"
        
        help_text += "<b>/wallet</b> (or <code>/bal</code>)\n"
        help_text += "  •  Shows your Rank, Level, and Ryo. A quick way to show off!\n\n"

        help_text += "<b>/scout</b>\n"
        help_text += "  •  Scout the area for rewards. Can be used once per hour.\n"
        help_text += "  •  Has a 25% chance to find Ryo and a 5% chance to find EXP.\n\n"
        
        help_text += "<b>/rob</b> (or <code>/steal</code>)\n"
        help_text += "  •  Reply to a user with <code>/rob</code> to try and pickpocket them.\n"
        help_text += "  •  <b>Success Chance:</b> Starts at 60%, increases with your <b>Speed</b> stat!\n"
        help_text += "  •  <b>Cost:</b> 15 Chakra per attempt.\n\n"
        
        help_text += "<b>/assassinate</b>\n"
        help_text += "  •  A high-risk, high-reward mission. Reply to a user with <code>/assassinate</code>.\n"
        help_text += "  •  <b>Cost:</b> 200 Ryo just to attempt the mission.\n"
        help_text += "  •  <b>Success:</b> Steal 10% of their Ryo (max 1,000), gain 100 EXP, and <b>HOSPITALIZE</b> them for 3 hours!\n"
        help_text += "  •  <b>Fail:</b> You lose your 200 Ryo payment.\n"
        help_text += "  •  Cooldown: 24 hours.\n\n"

        help_text += "<b>/protect</b>\n"
        help_text += "  •  Hire Anbu guards to block ALL rob and assassinate attempts.\n"
        help_text += "  •  Cost: 500 Ryo for 1 day, or 1300 Ryo for 3 days (use <code>/protect 3d</code>).\n\n"
        
        help_text += "<b>/heal</b>\n"
        help_text += "  •  Pay 300 Ryo to instantly leave the hospital if you were assassinated."

    elif module == "v2":
        help_text += "<b>--- 🎮 Advanced Mini-Games 🎮 ---</b>\n\n"
        help_text += "Advanced gameplay features for experienced ninjas!\n\n"
        
        help_text += "<b>/bountyboard</b>\n"
        help_text += "  •  View active bounties on other players.\n\n"
        
        help_text += "<b>/contracts</b>\n"
        help_text += "  •  View available assassination contracts.\n\n"
        
        help_text += "<b>/contract [amount]</b>\n"
        help_text += "  •  Reply to a player to put a bounty on them.\n\n"
        
        help_text += "<b>/legendary</b>\n"
        help_text += "  •  View and use your legendary items.\n\n"
        
        help_text += "<b>/reputation</b>\n"
        help_text += "  •  Check your reputation status and titles.\n\n"
        
        help_text += "<b>/heat</b>\n"
        help_text += "  •  Check your current wanted level.\n\n"

        # BUTTON FOR FULL GUIDE
        help_text += "⬇️ <b>Click below for full mechanics guide!</b>"

        keyboard = [
            [InlineKeyboardButton("📖 Full Mechanics Guide", callback_data="help_module_v2full")],
            [InlineKeyboardButton("⬅️ Back to Help Menu", callback_data="back_to_main_help")]
        ]
    
    elif module == "v2full":
        help_text += "<b>--- 📖 Advanced Mechanics Guide 📖 ---</b>\n\n"
        
        help_text += "<b>1. 🔥 Heat System (/heat)</b>\n"
        help_text += "Every crime (rob/kill) increases your Heat Level.\n"
        help_text += " • <b>Risk:</b> High Heat reduces your success chance!\n"
        help_text += " • <b>Reward:</b> High Heat multiplies ALL stolen Ryo!\n"
        help_text += "    🟡 <b>Suspicious (25+):</b> 1.2x Ryo\n"
        help_text += "    🟠 <b>Wanted (50+):</b> 1.5x Ryo\n"
        help_text += "    🔴 <b>Most Wanted (80+):</b> 2.0x Ryo\n"
        help_text += " • <b>Decay:</b> Heat naturally drops by 5 points per hour.\n\n"

        help_text += "<b>2. 📜 Contracts & Bounties</b>\n"
        help_text += " • <b>/bountyboard:</b> View the Top 10 Most Wanted players.\n"
        help_text += " • <b>/contracts:</b> View hitman contracts set by players.\n"
        help_text += " • <b>/contract [amount]:</b> Reply to a user to place a bounty on them (Min 500 Ryo). Expires in 48h.\n"
        help_text += " • <b>To Claim:</b> Successfully kill the target to earn the reward!\n\n"

        help_text += "<b>3. 🏆 Reputation Titles (/reputation)</b>\n"
        help_text += "Unlock permanent passive bonuses by playing:\n"
        help_text += " • <b>Shadow Assassin</b> (50 Kills): +25% Kill Success\n"
        help_text += " • <b>Notorious Criminal</b> (100 Kills): +30% Rob Success\n"
        help_text += " • <b>Master Thief</b> (500 Steals): +50% Rob Amount, +20% Success\n"
        help_text += " • <b>Guardian Angel</b> (50 Heals): +20% Protection Time\n"
        help_text += " • <b>Scout Master</b> (200 Scouts): 2x Scout Rewards\n\n"

        help_text += "<b>4. 🎒 Legendary Items (/legendary)</b>\n"
        help_text += "Crimes have a small chance to drop powerful items:\n"
        help_text += " • <b>🔱 Gold Kunai:</b> Guaranteed 1-hit kill (1 use).\n"
        help_text += " • <b>🥷 Stealth Cloak:</b> +50% Rob success for 1 hour.\n"
        help_text += " • <b>📜 Legendary Scroll:</b> Instantly gives +200 EXP.\n"
        help_text += " • <b>💎 Chakra Crystal:</b> Fully restores 100 Chakra."

        # Back button goes to the v2 summary menu
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="help_module_minigames_v2")]]

    else:
        help_text = "Help information for this module is not available yet."

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
        # Try sending without parse_mode as fallback
        try:
            await context.bot.send_message(
                chat_id=chat_id, 
                text=help_text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "").replace("&amp;", "&"),
                reply_markup=reply_markup
            )
        except Exception as e2:
            logger.error(f"Failed to send plain text help for {module}: {e2}")

# --- Back Button Callback (unchanged) ---
async def back_to_main_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Just call the main menu function, it handles deleting the old text message.
    await show_main_help_menu(update, context)
