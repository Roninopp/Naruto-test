import logging
import uuid
import random # <-- NEW IMPORT
from html import escape
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- NEW: Gamble Constants ---
BET_AMOUNT = 50
BET_WIN_CHANCE = 0.40 # 40% chance to win
BET_WIN_MULTIPLIER = 2.5 # Win 125 Ryo (50 bet + 75 profit)

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
        
        # --- 4. NEW: Gamble 50 Ryo ---
        gamble_title = f"🎲 Gamble {BET_AMOUNT} Ryo!"
        gamble_desc = "40% chance to win 125 Ryo!"
        
        is_hosp, _ = gl.get_hospital_status(player)
        if is_hosp:
            gamble_title = "❌ Cannot gamble while hospitalized"
            gamble_desc = "Use /heal in a group to recover."
        elif player['ryo'] < BET_AMOUNT:
            gamble_title = f"❌ Not enough Ryo (Need {BET_AMOUNT})"
            gamble_desc = "Go rob someone or do missions!"

        # --- This is the game logic. It runs BEFORE they click! ---
        if player['ryo'] >= BET_AMOUNT and not is_hosp:
            win_amount = int(BET_AMOUNT * BET_WIN_MULTIPLIER)
            
            if random.random() < BET_WIN_CHANCE:
                # --- WIN ---
                new_ryo = player['ryo'] + (win_amount - BET_AMOUNT)
                db.update_player(user_id, {'ryo': new_ryo})
                gamble_result_text = f"🎲 **JACKPOT!** 🎲\n{escape(player['username'])} just gambled {BET_AMOUNT} Ryo and **won {win_amount} Ryo**!"
            else:
                # --- LOSE ---
                new_ryo = player['ryo'] - BET_AMOUNT
                db.update_player(user_id, {'ryo': new_ryo})
                gamble_result_text = f"🎲 **Better luck next time...**\n{escape(player['username'])} gambled {BET_AMOUNT} Ryo and **lost it all**."
                
            results.append(
                InlineQueryResultArticle(
                    id="gamble",
                    title=gamble_title,
                    description=gamble_desc,
                    input_message_content=InputTextMessageContent(gamble_result_text, parse_mode="HTML")
                )
            )
        else:
            # Show a greyed-out, unclickable result
            results.append(
                InlineQueryResultArticle(
                    id="gamble_fail",
                    title=gamble_title,
                    description=gamble_desc,
                    input_message_content=InputTextMessageContent(f"I can't gamble right now. (Need {BET_AMOUNT} Ryo and must be healthy)")
                )
            )
        # --- END NEW ---
            
    else:
        # --- Not registered ---
        results.append(
            InlineQueryResultArticle(
                id="register",
                title="❌ You are not registered!",
                description="Click here to ask how to join.",
                input_message_content=InputTextMessageContent(f"Hey everyone, how do I /register for @{context.bot.username}?")
            )
        )

    await query.answer(results, cache_time=5) # 5 second cache so game is fresh
