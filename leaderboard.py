import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from html import escape

import database as db

logger = logging.getLogger(__name__)

# --- Main Command ---
async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the main leaderboard menu."""
    text = "🏆 **Shinobi Leaderboards** 🏆\n\nSelect a category to view the Top 10 ninja:"
    keyboard = [
        [InlineKeyboardButton("💰 Top Richest (Ryo)", callback_data="leaderboard_ryo")],
        [InlineKeyboardButton("🔥 Top Strongest (Level)", callback_data="leaderboard_exp")],
        [InlineKeyboardButton("⚔️ Top Fighters (Wins)", callback_data="leaderboard_wins")],
        [InlineKeyboardButton("☠️ Top Killers (Kills)", callback_data="leaderboard_kills")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query = update.callback_query
    if query:
        try: await query.answer(); await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except: await update.effective_chat.send_message(text, reply_markup=reply_markup, parse_mode="HTML")
    else: await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

# --- Callback Handler ---
async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the button clicks for leaderboard categories."""
    query = update.callback_query; await query.answer(); category = query.data.split('_', 1)[1]; text = ""; top_players = []
    def get_mention(uid, uname): return f'<a href="tg://user?id={uid}">{escape(uname)}</a>'

    if category == "ryo":
        text = "💰 **Top 10 Richest Ninja** 💰\n*(By Total Ryo)*\n\n"; top_players = db.get_top_players_by_ryo(limit=10)
        if not top_players: text += "No ninja have earned any Ryo yet."
        else:
            for i, p in enumerate(top_players): text += f"{['🥇','🥈','🥉'][i] if i<3 else f'<b>{i+1}.</b>'} {get_mention(p['user_id'], p['username'])} - {p['ryo']:,} Ryo\n"
    elif category == "exp":
        text = "🔥 **Top 10 Strongest Ninja** 🔥\n*(By Total EXP)*\n\n"; top_players = db.get_top_players_by_exp(limit=10)
        if not top_players: text += "No ninja have earned any EXP yet."
        else:
            for i, p in enumerate(top_players): text += f"{['🥇','🥈','🥉'][i] if i<3 else f'<b>{i+1}.</b>'} {get_mention(p['user_id'], p['username'])} - Lvl {p['level']} ({p['total_exp']:,} EXP)\n"
    elif category == "wins":
        text = "⚔️ **Top 10 Fighters** ⚔️\n*(By PvP Wins)*\n\n"; top_players = db.get_top_players_by_wins(limit=10)
        if not top_players: text += "No ninja have won any battles yet."
        else:
            for i, p in enumerate(top_players): text += f"{['🥇','🥈','🥉'][i] if i<3 else f'<b>{i+1}.</b>'} {get_mention(p['user_id'], p['username'])} - {p['wins']} Wins\n"
    elif category == "kills":
        text = "☠️ **Top 10 Deadliest Ninja** ☠️\n*(By Assassination Kills)*\n\n"; top_players = db.get_top_players_by_kills(limit=10)
        if not top_players: text += "No successful assassinations yet. The village is peaceful... for now."
        else:
            for i, p in enumerate(top_players): text += f"{['🥇','🥈','🥉'][i] if i<3 else f'<b>{i+1}.</b>'} {get_mention(p['user_id'], p['username'])} - {p['kills']} Kills\n"
    else: await query.edit_message_text("Error: Unknown category."); return

    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="leaderboard_main")]]; await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def leaderboard_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await leaderboard_command(update, context)

# --- NEW: /topkillers COMMAND ---
async def topkillers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct command to show top killers."""
    text = "☠️ **Top 10 Deadliest Ninja** ☠️\n*(By Assassination Kills)*\n\n"
    top_players = db.get_top_players_by_kills(limit=10)
    if not top_players:
        text += "No successful assassinations yet."
    else:
        for i, p in enumerate(top_players):
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"<b>{i+1}.</b>"
            # Recreating get_mention locally for this function
            mention = f'<a href="tg://user?id={p["user_id"]}">{escape(p["username"])}</a>'
            text += f"{rank} {mention} - {p['kills']} Kills\n"
            
    await update.message.reply_text(text, parse_mode="HTML")
