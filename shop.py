import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Command Handler ---

async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the item shop."""
    user = update.effective_user
    player = db.get_player(user.id)

    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

    text = f"Welcome to the Shop, {player['username']}!\n"
    text += f"You have: {player['ryo']} Ryo 💰\n\n"
    text += "What would you like to buy?\n"

    keyboard = []
    for item_key, item_info in gl.SHOP_INVENTORY.items():
        button_text = f"{item_info['name']} ({item_info['price']} Ryo)"
        if item_info['type'] == 'weapon':
            button_text = f"⚔️ {button_text} (+{item_info['stats']['strength']} Str)"
        elif item_info['type'] == 'armor':
            button_text = f"🛡️ {button_text} (+{item_info['stats']['stamina']} Stam)"

        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"shop_buy_{item_key}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup)

# --- Callback Handler ---

async def shop_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user's purchase selection."""
    query = update.callback_query
    # --- THIS IS THE FIX ---
    # We will call query.answer() only ONCE, either with the alert or silently later.
    # REMOVED: await query.answer()

    item_key = query.data.split('_', 2)[-1]
    item_info = gl.SHOP_INVENTORY.get(item_key)

    if not item_info:
        # If item doesn't exist, answer silently and send message
        await query.answer()
        await query.message.reply_text("That item is no longer for sale.")
        return

    user = query.from_user
    player = db.get_player(user.id)

    # 1. Check if they have enough Ryo
    if player['ryo'] < item_info['price']:
        # --- FIX PART 2: Call answer() HERE with the alert ---
        await query.answer("You don't have enough Ryo!", show_alert=True)
        return # Stop processing

    # --- If code reaches here, the player HAS enough Ryo ---
    
    # --- FIX PART 3: Answer silently NOW before processing purchase ---
    await query.answer()

    updates_to_save = {}

    # 2. Subtract Ryo
    new_ryo = player['ryo'] - item_info['price']
    updates_to_save['ryo'] = new_ryo

    # 3. Add the item
    if item_info['type'] in ['weapon', 'armor', 'accessory']:
        equipment = json.loads(player['equipment'])
        equipment[item_info['type']] = item_key
        updates_to_save['equipment'] = json.dumps(equipment)
        await query.message.reply_text(f"You bought and equipped the {item_info['name']}!")

    else: # Consumable
        inventory = json.loads(player['inventory'])
        inventory.append(item_key)
        updates_to_save['inventory'] = json.dumps(inventory)
        await query.message.reply_text(f"You bought a {item_info['name']}! It has been added to your inventory.")

    # 4. Save changes to the database
    success = db.update_player(user.id, updates_to_save)

    if not success:
        await query.message.reply_text("An error occurred while saving your purchase.")
