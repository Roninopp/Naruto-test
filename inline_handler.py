import logging
import uuid
from html import escape
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

def get_wallet_text(player):
    """Generates the HTML text for a player's wallet card."""
    is_hosp, _ = gl.get_hospital_status(player)
    status_text = "🏥 Hospitalized" if is_hosp else "❤️ Alive"
    wallet_text = (
        f"<b>--- 🥷 {escape(player['username'])}'s Wallet 🥷 ---</b>\n\n"
        f"<b>Rank:</b> {player['rank']}\n"
        f"<b>Level:</b> {player['level']}\n"
        f"<b>Ryo:</b> {player['ryo']:,} 💰\n"
        f"<b>Kills:</b> {player.get('kills', 0)} ☠️\n"
        f"<b>Status:</b> {status_text}"
    )
    return wallet_text

def get_top_killers_text():
    """Generates the HTML text for the Top 5 Killers."""
    text = "☠️ **Top 5 Deadliest Ninja** ☠️\n*(By Kills)*\n\n"
    top_players = db.get_top_players_by_kills(limit=5)
    if not top_players:
        text += "No successful kills yet..."
    else:
        for i, p in enumerate(top_players):
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"<b>{i+1}.</b>"
            # Use escape to be safe, but a "mention" is better for flexing
            mention = f'<a href="tg://user?id={p["user_id"]}">{escape(p["username"])}</a>'
            text += f"{rank} {mention} - {p['kills']} Kills\n"
    return text

def get_top_rich_text():
    """Generates the HTML text for the Top 5 Richest."""
    text = "💰 **Top 5 Richest Ninja** 💰\n*(By Total Ryo)*\n\n"
    top_players = db.get_top_players_by_ryo(limit=5)
    if not top_players:
        text += "No one has any Ryo..."
    else:
        for i, p in enumerate(top_players):
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"<b>{i+1}.</b>"
            mention = f'<a href="tg://user?id={p["user_id"]}">{escape(p["username"])}</a>'
            text += f"{rank} {mention} - {p['ryo']:,} Ryo\n"
    return text

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline queries (@BotName ...)."""
    query = update.inline_query
    if not query:
        return

    user_id = query.from_user.id
    player = db.get_player(user_id)
    results = []

    if player:
        # --- 1. Show My Wallet ---
        wallet_text = get_wallet_text(player)
        results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="🥷 Show My Wallet (Flex!)",
                description=f"Post your Lvl {player['level']} | {player['ryo']} Ryo | {player.get('kills', 0)} Kills card",
                input_message_content=InputTextMessageContent(wallet_text, parse_mode="HTML")
            )
        )
        
        # --- 2. Show Top Killers ---
        killers_text = get_top_killers_text()
        results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="☠️ Show Top 5 Killers",
                description="Post the 'Top Killers' leaderboard here.",
                input_message_content=InputTextMessageContent(killers_text, parse_mode="HTML")
            )
        )
        
        # --- 3. Show Top Richest ---
        rich_text = get_top_rich_text()
        results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="💰 Show Top 5 Richest",
                description="Post the 'Top Richest' leaderboard here.",
                input_message_content=InputTextMessageContent(rich_text, parse_mode="HTML")
            )
        )
    else:
        # --- Not registered ---
        results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="❌ You are not registered!",
                description="Click here to ask how to join.",
                input_message_content=InputTextMessageContent(f"Hey everyone, how do I /register for @{context.bot.username}?")
            )
        )

    # Answer the query with the list of results
    await query.answer(results, cache_time=10) # 10 second cache
