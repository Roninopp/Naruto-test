import logging
import asyncio
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Import our database and game_logic functions
import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Command Handlers ---

async def jutsus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists the jutsus the player has learned."""
    user = update.effective_user
    player = db.get_player(user.id)

    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

    known_jutsus = json.loads(player['known_jutsus']) # Convert JSON string from DB to list

    if not known_jutsus:
        await update.message.reply_text("You have not learned any jutsus yet. Use /combine to discover them!")
        return
        
    text = "<b>--- Your Known Jutsus---</b>\n\n"
    for jutsu_name in known_jutsus:
        jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_name)
        if jutsu_info:
            text += (
                f"<b>{jutsu_name.replace('_', ' ').title()}</b> ({jutsu_info['element'].title()})\n"
                f"  • Power: {jutsu_info['power']} | Cost: {jutsu_info['chakra_cost']}\n"
                f"  • Signs: {' → '.join(jutsu_info['signs'])}\n\n"
            )
            
    await update.message.reply_text(text, parse_mode="HTML")

async def combine_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows the player to try and discover a new jutsu."""
    user = update.effective_user
    player = db.get_player(user.id)

    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

    if not context.args:
        await update.message.reply_text(
            "You must provide a hand sign combination.\n"
            "Example: /combine tiger snake bird"
        )
        return

    # User input: ['tiger', 'snake', 'bird']
    combination = [sign.lower() for sign in context.args]
    
    # Check against the JUTSU_LIBRARY
    discovered_jutsu_name = None
    for jutsu_name, jutsu_info in gl.JUTSU_LIBRARY.items():
        if jutsu_info['signs'] == combination:
            discovered_jutsu_name = jutsu_name
            break

    if not discovered_jutsu_name:
        await update.message.reply_text(
            f"You perform the signs: {' → '.join(combination)}\n"
            "But... nothing happens. This combination seems to be incorrect."
        )
        return
        
    # --- Player Found a Jutsu! ---
    jutsu_info = gl.JUTSU_LIBRARY[discovered_jutsu_name]
    
    # Check if they already know it
    known_jutsus = json.loads(player['known_jutsus'])
    if discovered_jutsu_name in known_jutsus:
        await update.message.reply_text(f"You already know {discovered_jutsu_name.replace('_', ' ').title()}.")
        return
        
    # Check level requirement
    if player['level'] < jutsu_info['level_required']:
        await update.message.reply_text(
            f"You perform the signs: {' → '.join(combination)}\n"
            f"You feel a powerful chakra, but you are not high enough level to control it. "
            f"(Requires Level {jutsu_info['level_required']})"
        )
        return

    # --- SUCCESS! Add Jutsu to Player ---
    known_jutsus.append(discovered_jutsu_name)
    
    # Save the new list back to the DB as a JSON string
    player_data = {'known_jutsus': json.dumps(known_jutsus)}
    db.update_player(user.id, player_data)
    
    # Play the discovery animation
    discovery_message = await update.message.reply_text("You try unusual hand signs...")
    await animate_jutsu_discovery(discovery_message, player, discovered_jutsu_name, jutsu_info)


# --- Animation Function ---

async def animate_jutsu_discovery(message, player, jutsu_name, new_jutsu):
    """Plays the jutsu discovery animation from your prompt."""
    player_name = player['username']
    jutsu_name_formatted = jutsu_name.replace('_', ' ').upper()
    
    discovery_frames = [
        f"{player_name} tries unusual hand signs...",
        f"Signs: {' → '.join(new_jutsu['signs'])}",
        "💫 Chakra reacts strangely!",
        "✨ Something new is forming!",
        "🌟 NEW JUTSU DISCOVERED!",
        f"🎉 {jutsu_name_formatted}!",
        f"💥 Power: {new_jutsu['power']} | Cost: {new_jutsu['chakra_cost']}",
        "📚 This technique is now recorded in your scroll!"
    ]
    
    current_text = ""
    for frame in discovery_frames:
        current_text = frame # We replace the text each time for this animation
        try:
            await message.edit_text(f"<i>{current_text}</i>", parse_mode="HTML")
            await asyncio.sleep(1.5)
        except Exception as e:
            logger.warning(f"Jutsu discovery animation error: {e}")
