import logging
import json
import sqlite3
import datetime
from telegram import Update
from telegram.ext import ContextTypes

# Import our database and game_logic functions
import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Command Handlers ---

async def proteec_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /proteec <name> guess from the user."""
    user = update.effective_user
    player = db.get_player(user.id)

    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

    if not context.args:
        await update.message.reply_text("You must provide a name to guess!\nExample: `/proteec Naruto Uzumaki`")
        return

    # Combine all args into a single string and convert to lowercase
    guess_name = " ".join(context.args).lower()

    # Get the current character from the DB
    spotlight_char = db.get_current_spotlight()

    if not spotlight_char:
        await update.message.reply_text("There is no character in the spotlight right now. Wait for the next announcement!")
        return
        
    # The key in the DB is the lowercase name, e.g., 'naruto uzumaki'
    correct_name_key = spotlight_char['key']

    if guess_name != correct_name_key:
        await update.message.reply_text(f"Sorry, '{guess_name}' is not the correct character. Try again!")
        return

    # --- GUESS IS CORRECT ---
    await _process_correct_guess(update, user.id, player, spotlight_char)


async def collection_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the user's character collection."""
    user = update.effective_user
    player = db.get_player(user.id)

    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return
        
    collection = db.get_player_collection(user.id)
    
    if not collection:
        await update.message.reply_text("Your collection is empty. Use /proteec <name> to guess characters!")
        return

    # Group characters by rarity
    collection_by_rarity = {
        'common': [],
        'rare': [],
        'epic': [],
        'legendary': []
    }
    
    for char in collection:
        rarity = char['rarity']
        if rarity in collection_by_rarity:
            collection_by_rarity[rarity].append(char)

    # Build the text response
    text = f"<b>--- {player['username']}'s Collection ---</b>\n\n"
    
    for rarity, chars in collection_by_rarity.items():
        rarity_info = gl.PROTECC_RARITIES[rarity]
        text += f"<b>{rarity_info['emoji']} {rarity.title()} Characters ({len(chars)}) {rarity_info['emoji']}</b>\n"
        if not chars:
            text += "  <i>(None collected)</i>\n"
        else:
            for char in chars:
                text += f"  • {char['character_name']} (x{char['times_collected']})\n"
        text += "\n"
        
    await update.message.reply_text(text, parse_mode="HTML")


async def proteec_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the user's collection stats."""
    user = update.effective_user
    player = db.get_player(user.id)

    if not player:
        await update.message.reply_text("You must /start your journey first.")
        return

    stats = db.get_protecc_stats(user.id)
    if not stats:
        # This should not happen if create_player() is working, but it's a good fallback.
        await update.message.reply_text("Could not find your stats. Try /start again.")
        return

    # Get total unique characters possible
    total_possible = len(gl.PROTECC_CHARACTERS)

    text = (
        f"<b>--- 🎴 Collection Stats ---</b>\n\n"
        f"<b>Player:</b> {player['username']}\n"
        f"<b>Unique Characters:</b> {stats['unique_collected']} / {total_possible}\n"
        f"<b>Total Characters Caught:</b> {stats['total_collected']}\n"
        f"<b>Total Ryo Earned:</b> {stats['total_ryo_earned']} 💰\n"
    )
    
    await update.message.reply_text(text, parse_mode="HTML")


# --- Helper Function ---

async def _process_correct_guess(update, user_id, player_data, character_info):
    """Handles all database updates for a correct guess."""
    
    char_name = character_info['name']
    char_rarity = character_info['rarity']
    
    # Get rarity info and base Ryo value
    rarity_data = gl.PROTECC_RARITIES[char_rarity]
    base_ryo_reward = rarity_data['ryo']
    
    conn = db.get_db_connection()
    if conn is None:
        await update.message.reply_text("Error: Could not connect to the database.")
        return

    try:
        cursor = conn.cursor()
        
        # --- 1. Check if player already has this character ---
        cursor.execute(
            "SELECT times_collected FROM protecc_collection WHERE user_id = ? AND character_name = ?",
            (user_id, char_name)
        )
        existing_entry = cursor.fetchone()
        
        is_new_catch = (existing_entry is None)
        
        if is_new_catch:
            # New catch! Full Ryo reward
            ryo_gain = base_ryo_reward
            times_collected = 1
            
            # Insert into collection
            cursor.execute(
                "INSERT INTO protecc_collection (user_id, character_name, rarity, times_collected) VALUES (?, ?, ?, ?)",
                (user_id, char_name, char_rarity, times_collected)
            )
            
            # Update stats
            cursor.execute(
                "UPDATE protecc_stats SET total_collected = total_collected + 1, unique_collected = unique_collected + 1, total_ryo_earned = total_ryo_earned + ? WHERE user_id = ?",
                (ryo_gain, user_id)
            )
            
            reply_text = (
                f"🎉 <b>NEW CATCH!</b> 🎉\n"
                f"You successfully protected and collected <b>{char_name} ({rarity_data['emoji']} {char_rarity.title()})</b>!\n"
                f"You earned {ryo_gain} Ryo! 💰"
            )
            
        else:
            # Duplicate catch! 20% Ryo reward
            ryo_gain = int(base_ryo_reward * 0.20)
            times_collected = existing_entry['times_collected'] + 1
            
            # Update collection
            cursor.execute(
                "UPDATE protecc_collection SET times_collected = ? WHERE user_id = ? AND character_name = ?",
                (times_collected, user_id, char_name)
            )
            
            # Update stats
            cursor.execute(
                "UPDATE protecc_stats SET total_collected = total_collected + 1, total_ryo_earned = total_ryo_earned + ? WHERE user_id = ?",
                (ryo_gain, user_id)
            )
            
            reply_text = (
                f"✅ <b>DUPLICATE!</b> ✅\n"
                f"You found <b>{char_name}</b> again! (Total: x{times_collected})\n"
                f"You earned a duplicate reward of {ryo_gain} Ryo. 💰"
            )

        # --- 2. Update Player's Ryo in 'players' table ---
        new_total_ryo = player_data['ryo'] + ryo_gain
        cursor.execute(
            "UPDATE players SET ryo = ? WHERE user_id = ?",
            (new_total_ryo, user_id)
        )

        # --- 3. Commit all changes ---
        conn.commit()
        
        # --- 4. Clear player cache ---
        db.cache.clear_player_cache(user_id)
        
        await update.message.reply_text(reply_text, parse_mode="HTML")

    except sqlite3.Error as e:
        logger.error(f"Error processing correct guess for {user_id}: {e}")
        await update.message.reply_text("A database error occurred while saving your catch.")
    finally:
        conn.close()
