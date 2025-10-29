import logging
import sqlite3
import json
import psutil # For server stats
import os
import functools # For the decorator

from telegram import Update
from telegram.ext import ContextTypes

# Import our database and game_logic functions
import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- !!! YOUR OWNER ID !!! ---
OWNER_ID = 6837532865
# -----------------------------

# --- Decorator for Owner Check ---
def owner_only(func):
    """Decorator to restrict command access to the OWNER_ID."""
    @functools.wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if user.id != OWNER_ID:
            logger.warning(f"Unauthorized sudo attempt by user {user.id} ({user.username}) for command /{func.__name__.replace('_command', '')}")
            await update.message.reply_text("⛔️ You are not authorized to use this command.")
            return
        logger.info(f"Sudo command /{func.__name__.replace('_command', '')} initiated by owner.")
        return await func(update, context, *args, **kwargs)
    return wrapped
# --- End Decorator ---

# --- Sudo Commands ---

@owner_only
async def server_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows server resource usage."""
    try:
        cpu_usage = psutil.cpu_percent(interval=1)
        memory_info = psutil.virtual_memory()
        disk_info = psutil.disk_usage('/')

        stats_text = (
            f"🖥️ **Server Status** 🖥️\n\n"
            f"**CPU Usage:** {cpu_usage}%\n"
            f"**RAM Usage:** {memory_info.percent}% ({memory_info.used / (1024**3):.2f} GB / {memory_info.total / (1024**3):.2f} GB)\n"
            f"**Disk Usage:** {disk_info.percent}% ({disk_info.used / (1024**3):.2f} GB / {disk_info.total / (1024**3):.2f} GB)"
        )
        await update.message.reply_text(stats_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error getting server stats: {e}")
        await update.message.reply_text(f"Error getting server stats: {e}")

@owner_only
async def db_query_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes a read-only SQL query."""
    if not context.args:
        await update.message.reply_text("Please provide a SQL query. Example: `/db_query SELECT * FROM players WHERE user_id = 123`")
        return

    query = " ".join(context.args)

    # --- Basic Security: Only allow SELECT ---
    if not query.strip().upper().startswith("SELECT"):
        await update.message.reply_text("⚠️ **Error:** Only SELECT queries are allowed for safety.")
        return
    # --- End Security ---

    conn = None
    try:
        conn = db.get_db_connection()
        if conn is None:
            await update.message.reply_text("Failed to connect to the database.")
            return

        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("Query executed successfully, but no results found.")
            return

        # Format results (limited to avoid huge messages)
        results_text = f"📊 **Query Results** (Limit 10 rows):\n\n```\n"
        headers = [description[0] for description in cursor.description]
        results_text += " | ".join(headers) + "\n"
        results_text += "-" * (len(" | ".join(headers))) + "\n" # Separator line

        for i, row in enumerate(rows[:10]): # Limit to first 10 rows
            row_dict = dict(row)
            results_text += " | ".join(map(str, row_dict.values())) + "\n"

        if len(rows) > 10:
            results_text += f"\n... (truncated, {len(rows) - 10} more rows)\n"

        results_text += "```"
        await update.message.reply_text(results_text, parse_mode="HTML")

    except sqlite3.Error as e:
        logger.error(f"Error executing DB query '{query}': {e}")
        await update.message.reply_text(f"❌ **Database Error:**\n`{e}`", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Unexpected error during DB query '{query}': {e}")
        await update.message.reply_text(f"❌ **Error:**\n`{e}`", parse_mode="HTML")
    finally:
        if conn:
            conn.close()

@owner_only
async def sudo_give_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gives Ryo or EXP to a specific user."""
    args = context.args
    if len(args) != 3:
        await update.message.reply_text("Usage: `/sudo_give <user_id> <ryo|exp> <amount>`\nExample: `/sudo_give 12345 ryo 5000`")
        return

    try:
        target_user_id = int(args[0])
        give_type = args[1].lower()
        amount = int(args[2])
    except ValueError:
        await update.message.reply_text("Invalid arguments. User ID and amount must be numbers.")
        return

    if give_type not in ['ryo', 'exp']:
        await update.message.reply_text("Invalid type. Must be 'ryo' or 'exp'.")
        return

    target_player = db.get_player(target_user_id)
    if not target_player:
        await update.message.reply_text(f"Player with ID {target_user_id} not found.")
        return

    updates = {}
    if give_type == 'ryo':
        updates['ryo'] = target_player['ryo'] + amount
        success = db.update_player(target_user_id, updates)
        if success:
            await update.message.reply_text(f"✅ Successfully gave {amount} Ryo to user {target_user_id}. New balance: {updates['ryo']}.")
        else:
            await update.message.reply_text("❌ Failed to update player Ryo.")
    elif give_type == 'exp':
        # Use existing logic to handle level ups correctly
        temp_player_data = dict(target_player)
        temp_player_data['exp'] += amount
        temp_player_data['total_exp'] += amount
        final_player_data, leveled_up, messages = gl.check_for_level_up(temp_player_data)
        success = db.update_player(target_user_id, final_player_data)
        if success:
            await update.message.reply_text(f"✅ Successfully gave {amount} EXP to user {target_user_id}.\n" + "\n".join(messages))
        else:
            await update.message.reply_text("❌ Failed to update player EXP.")

@owner_only
async def sudo_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets a specific stat for a player."""
    args = context.args
    valid_stats = ['level', 'exp', 'ryo', 'strength', 'speed', 'intelligence', 'stamina', 'current_hp', 'current_chakra', 'max_hp', 'max_chakra', 'wins', 'losses']

    if len(args) != 3:
        await update.message.reply_text(f"Usage: `/sudo_set <user_id> <stat> <value>`\nValid stats: {', '.join(valid_stats)}")
        return

    try:
        target_user_id = int(args[0])
        stat_to_set = args[1].lower()
        new_value = int(args[2]) # Most stats are integers
    except ValueError:
        await update.message.reply_text("Invalid arguments. User ID and value must be numbers.")
        return

    if stat_to_set not in valid_stats:
        await update.message.reply_text(f"Invalid stat. Choose from: {', '.join(valid_stats)}")
        return

    target_player = db.get_player(target_user_id)
    if not target_player:
        await update.message.reply_text(f"Player with ID {target_user_id} not found.")
        return

    updates = {stat_to_set: new_value}
    success = db.update_player(target_user_id, updates)

    if success:
        await update.message.reply_text(f"✅ Successfully set **{stat_to_set}** to **{new_value}** for user {target_user_id}.")
        # Inform user if setting HP/Chakra might require recalc or cause issues
        if stat_to_set in ['stamina', 'intelligence']:
             await update.message.reply_text(f"ℹ️ Note: Changing base stats like {stat_to_set} doesn't automatically recalculate Max HP/Chakra shown in profile until next level up or training.")
        if stat_to_set in ['max_hp', 'max_chakra']:
             await update.message.reply_text(f"ℹ️ Note: Current HP/Chakra may need manual adjustment if you changed the max value.")
    else:
        await update.message.reply_text("❌ Failed to update player stat.")


@owner_only
async def list_boss_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all chat IDs where the World Boss is enabled."""
    enabled_chat_ids = db.get_all_boss_chats()

    if not enabled_chat_ids:
        await update.message.reply_text("World Boss is not enabled in any chats yet.")
        return

    chat_list = "\n".join(map(str, enabled_chat_ids))
    await update.message.reply_text(f"📜 **World Boss Enabled Chats:**\n```\n{chat_list}\n```", parse_mode="HTML")

@owner_only
async def sudo_leave_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forces the bot to leave a specific chat."""
    if not context.args:
        await update.message.reply_text("Usage: `/sudo_leave <chat_id>`")
        return

    try:
        chat_id_to_leave = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid Chat ID. Must be a number.")
        return

    try:
        await context.bot.leave_chat(chat_id=chat_id_to_leave)
        logger.info(f"Sudo command: Left chat {chat_id_to_leave}")
        await update.message.reply_text(f"✅ Successfully left chat {chat_id_to_leave}.")
    except Exception as e:
        logger.error(f"Error leaving chat {chat_id_to_leave}: {e}")
        await update.message.reply_text(f"❌ Failed to leave chat {chat_id_to_leave}.\nError: `{e}`", parse_mode="HTML")


@owner_only
async def get_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches and displays all DB info for a user ID."""
    if not context.args:
        await update.message.reply_text("Usage: `/get_user <user_id>`")
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid User ID. Must be a number.")
        return

    player_data = db.get_player(target_user_id)

    if not player_data:
        await update.message.reply_text(f"Player with ID {target_user_id} not found in the database.")
        return

    # Format the data nicely
    user_info_text = f"👤 **User Data for ID: {target_user_id}** 👤\n\n```json\n"
    user_info_text += json.dumps(player_data, indent=2) # Pretty print JSON
    user_info_text += "\n```"

    # Send in chunks if too long
    MAX_MSG_LENGTH = 4096
    if len(user_info_text) <= MAX_MSG_LENGTH:
        await update.message.reply_text(user_info_text, parse_mode="HTML")
    else:
        await update.message.reply_text(f"👤 **User Data for ID: {target_user_id}** 👤\nData too long, sending as chunks...")
        for i in range(0, len(user_info_text), MAX_MSG_LENGTH - 10): # -10 for safety margin + code block markers
             chunk = user_info_text[i:i + MAX_MSG_LENGTH - 10]
             # Ensure code blocks are properly closed in chunks
             if i == 0:
                 await update.message.reply_text(f"{chunk}\n```", parse_mode="HTML")
             elif i + MAX_MSG_LENGTH - 10 < len(user_info_text):
                 await update.message.reply_text(f"```json\n{chunk}\n```", parse_mode="HTML")
             else: # Last chunk
                 await update.message.reply_text(f"```json\n{chunk}", parse_mode="HTML")
