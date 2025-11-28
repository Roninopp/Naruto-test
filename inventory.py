import logging
import json
from collections import Counter # Helps count items easily
from telegram import Update
from telegram.ext import ContextTypes

# Import our database and game_logic functions
import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Command Handler ---

async def inventory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the player's consumable items."""
    user = update.effective_user
    player = db.get_player(user.id)

    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

    # --- THIS IS THE FIX ---
    # The database (JSONB) and cache (json.loads) already return a Python LIST, not a string.
    # We must remove json.loads() to prevent the TypeError.
    # We just get the list directly, or an empty list if it's None.
    inventory_list = player.get('inventory') or []
    # --- END OF FIX ---

    if not inventory_list:
        await update.message.reply_text("🎒 Your inventory is empty.")
        return

    # Count the items
    item_counts = Counter(inventory_list) # {'health_potion': 2}

    inventory_text = "<b>--- 🎒 Your Inventory 🎒 ---</b>\n\n"
    inventory_text += "<b>Consumables:</b>\n"

    found_consumables = False
    for item_key, count in item_counts.items():
        item_info = gl.SHOP_INVENTORY.get(item_key)
        if item_info and item_info['type'] == 'consumable':
            inventory_text += f" • {item_info['name']} x{count}\n"
            found_consumables = True

    if not found_consumables:
        inventory_text += "<i>No consumable items.</i>\n"

    # (We can add sections for other item types later if needed)

    await update.message.reply_text(inventory_text, parse_mode="HTML")
