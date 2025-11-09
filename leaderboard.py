import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
# --- NEW: Import to escape HTML ---
from html import escape
# --- END NEW ---

import database as db

logger = logging.getLogger(__name__)

# --- Main Command ---

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the main leaderboard menu."""
    
    text = "🏆 **Shinobi Leaderboards** 🏆\n\nSelect a category to view the Top 10 ninja:"
    
    keyboard = [
        [InlineKeyboardButton("💰 Top Richest (Ryo)", callback_data="leaderboard_ryo")],
        [InlineKeyboardButton("🔥 Top Strongest (Level)", callback_data="leaderboard_exp")],
        [InlineKeyboardButton("⚔️ Top Fighters (Wins)", callback_data="leaderboard_wins")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query = update.callback_query
    if query:
        try:
            await query.answer()
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Error editing message to show main leaderboard: {e}")
            await update.effective_chat.send_message(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")


# --- Callback Handler ---

async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the button clicks for leaderboard categories."""
    query = update.callback_query
    await query.answer()

    category = query.data.split('_', 1)[1] # "ryo", "exp", or "wins"

    text = ""
    top_players = []
    
    # --- Helper function for mentions ---
    def get_mention(user_id, username):
        # Escape username to prevent HTML injection
        safe_username = escape(username)
        return f'<a href="tg://user?id={user_id}">{safe_username}</a>'

    if category == "ryo":
        text = "💰 **Top 10 Richest Ninja** 💰\n*(By Total Ryo)*\n\n"
        top_players = db.get_top_players_by_ryo(limit=10)
        
        if not top_players:
            text += "No ninja have earned any Ryo yet."
        else:
            for i, player in enumerate(top_players):
                rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"<b>{i+1}.</b>"
                mention = get_mention(player['user_id'], player['username'])
                text += f"{rank_emoji} {mention} - {player['ryo']:,} Ryo\n"

    elif category == "exp":
        text = "🔥 **Top 10 Strongest Ninja** 🔥\n*(By Total EXP / Level)*\n\n"
        top_players = db.get_top_players_by_exp(limit=10)
        
        if not top_players:
            text += "No ninja have earned any EXP yet."
        else:
            for i, player in enumerate(top_players):
                rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"<b>{i+1}.</b>"
                mention = get_mention(player['user_id'], player['username'])
                text += f"{rank_emoji} {mention} - Level {player['level']} ({player['total_exp']:,} EXP)\n"

    elif category == "wins":
        text = "⚔️ **Top 10 Fighters** ⚔️\n*(By PvP Wins)*\n\n"
        top_players = db.get_top_players_by_wins(limit=10)
        
        if not top_players:
            text += "No ninja have won any battles yet."
        else:
            for i, player in enumerate(top_players):
                rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"<b>{i+1}.</b>"
                mention = get_mention(player['user_id'], player['username'])
                text += f"{rank_emoji} {mention} - {player['wins']} Wins\n"

    else:
        # This was the bug! The "back" button was caught here.
        # But now the 'back' handler in main.py is registered first.
        # We will keep this as a safety net.
        await query.edit_message_text("Error: Unknown leaderboard category.")
        return

    keyboard = [[InlineKeyboardButton("⬅️ Back to Leaderboards", callback_data="leaderboard_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")


async def leaderboard_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Back' button press, showing the main menu."""
    # This function just calls the main command function, which is correct.
    await leaderboard_command(update, context)
