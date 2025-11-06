import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Command Handler ---
async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (No changes here, this function is fine)
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

    item_key = query.data.split('_', 2)[-1]
    item_info = gl.SHOP_INVENTORY.get(item_key)

    if not item_info:
        await query.answer()
        await query.message.reply_text("That item is no longer for sale.")
        return

    user = query.from_user
    player = db.get_player(user.id)
    
    if not player:
        await query.answer("Player not found, please /start", show_alert=True)
        return

    if player['ryo'] < item_info['price']:
        await query.answer("You don't have enough Ryo!", show_alert=True)
        return 
    
    await query.answer() 
    updates_to_save = {}
    updates_to_save['ryo'] = player['ryo'] - item_info['price']

    if item_info['type'] in ['weapon', 'armor', 'accessory']:
        # --- THIS IS THE FIX ---
        # player.get('equipment') is already a dict
        equipment = player.get('equipment') or {}
        # --- END OF FIX ---
        
        equipment[item_info['type']] = item_key
        updates_to_save['equipment'] = equipment # db.update_player handles the json conversion
        await query.message.reply_text(f"You bought and equipped the {item_info['name']}!")

    else: # Consumable
        # --- THIS IS THE FIX ---
        # player.get('inventory') is already a list
        inventory = player.get('inventory') or []
        # --- END OF FIX ---
        
        inventory.append(item_key)
        updates_to_save['inventory'] = inventory # db.update_player handles the json conversion
        await query.message.reply_text(f"You bought a {item_info['name']}! It has been added to your inventory.")

    success = db.update_player(user.id, updates_to_save)

    if not success:
        await query.message.reply_text("An error occurred while saving your purchase.")
