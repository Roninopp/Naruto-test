import logging
import uuid
import random
import datetime # <-- We need this for the daily pack
from html import escape
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Daily Pack Loot Table ---
# (Rarity, Type, Key, Amount, Name)
PACK_LOOT_TABLE = [
    (100, 'ryo', 'ryo', 50, "Common Ryo Pouch"),       # Common
    (100, 'ryo', 'ryo', 75, "Common Ryo Pouch"),       # Common
    (50,  'ryo', 'ryo', 150, "Uncommon Ryo Pouch"),    # Uncommon
    (25,  'item', 'health_potion', 1, "Health Potion"), # Uncommon
    (10,  'ryo', 'ryo', 500, "Rare Ryo Chest"),        # Rare
    (5,   'item', 'soldier_pill', 1, "Soldier Pill"),  # Rare
    (1,   'exp', 'exp', 100, "Legendary EXP Scroll")   # Legendary
]

# --- NEW: Hand Sign Game ---
GAME_COST = 25
GAME_WIN_MULTIPLIER = 3 # 1-in-3 chance, so 3x reward
GAME_WIN_AMOUNT = GAME_COST * GAME_WIN_MULTIPLIER
HAND_SIGNS = [
    ("tiger", "🐅"),
    ("snake", "🐍"),
    ("bird", "🐦")
]
# ---------------------------

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

def get_daily_pack_prize(player):
    """Runs the loot table, returns the text and the db update dict."""
    prize = random.choices(PACK_LOOT_TABLE, weights=[p[0] for p in PACK_LOOT_TABLE], k=1)[0]
    _, p_type, p_key, p_amount, p_name = prize
    
    updates = {'last_inline_game_date': datetime.date.today()}
    result_text = ""

    if p_type == 'ryo':
        updates['ryo'] = player['ryo'] + p_amount
        result_text = f"🎁 **Daily Pack!** 🎁\n{escape(player['username'])} opened a pack and found a **{p_name}**!\n💰 **You gain {p_amount} Ryo!**"
    
    elif p_type == 'item':
        inventory = player.get('inventory') or []
        inventory.append(p_key)
        updates['inventory'] = inventory
        result_text = f"🎁 **Daily Pack!** 🎁\n{escape(player['username'])} opened a pack and found a **{p_name}**!\n📦 It was added to your /inventory."

    elif p_type == 'exp':
        updates['exp'] = player['exp'] + p_amount
        updates['total_exp'] = player['total_exp'] + p_amount
        result_text = f"🎁 **Daily Pack!** 🎁\n{escape(player['username'])} opened a pack and found a **{p_name}**!\n✨ **You gain {p_amount} EXP!**"

    return result_text, updates


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline queries (@BotName ...)."""
    query = update.inline_query
    if not query:
        return

    user_id = query.from_user.id
    player = db.get_player(user_id)
    results = []

    if player:
        is_hosp, _ = gl.get_hospital_status(player)
        
        # --- 1. Show My Wallet ---
        wallet_text = get_wallet_text(player)
        results.append(
            InlineQueryResultArticle(
                id="wallet",
                title="🥷 Show My Wallet (Flex!)",
                description=f"Post your Lvl {player['level']} | {player['ryo']} Ryo | {player.get('kills', 0)} Kills card",
                input_message_content=InputTextMessageContent(wallet_text, parse_mode="HTML")
            )
        )
        
        # --- 2. Show Top Killers ---
        killers_text = get_top_killers_text()
        results.append(
            InlineQueryResultArticle(
                id="top_killers",
                title="☠️ Show Top 5 Killers",
                description="Post the 'Top Killers' leaderboard here.",
                input_message_content=InputTextMessageContent(killers_text, parse_mode="HTML")
            )
        )
        
        # --- 3. Show Top Richest ---
        rich_text = get_top_rich_text()
        results.append(
            InlineQueryResultArticle(
                id="top_rich",
                title="💰 Show Top 5 Richest",
                description="Post the 'Top Richest' leaderboard here.",
                input_message_content=InputTextMessageContent(rich_text, parse_mode="HTML")
            )
        )
        
        # --- 4. Daily Shinobi Pack (The one we already added) ---
        today = datetime.date.today()
        last_claim_str = player.get('last_inline_game_date')
        last_claim = None
        
        if last_claim_str:
            try: last_claim = datetime.date.fromisoformat(last_claim_str)
            except: pass

        if last_claim == today:
            # Already claimed
            results.append(
                InlineQueryResultArticle(
                    id="daily_pack_claimed",
                    title="❌ Daily Pack Already Claimed",
                    description="Come back tomorrow for your next free pack!",
                    input_message_content=InputTextMessageContent(f"I've already claimed my daily pack. Come back tomorrow!")
                )
            )
        else:
            # Not claimed yet
            # --- IMPORTANT: We only update the DB when they *click* ---
            # We create the text and updates here
            result_text, updates = get_daily_pack_prize(player)
            
            # Now we update the player in the database
            db.update_player(user_id, updates)
            
            results.append(
                InlineQueryResultArticle(
                    id="daily_pack_open",
                    title="🎁 Open your Daily Shinobi Pack!",
                    description="Get a free random reward once per day!",
                    # The text that will be sent is the result_text
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                )
            )
            
        # --- 5. NEW: Hand Sign Game ---
        if is_hosp:
            results.append(
                InlineQueryResultArticle(
                    id="game_fail_hosp",
                    title=f"❌ Cannot play games while hospitalized",
                    description="Use /heal in a group to recover.",
                    input_message_content=InputTextMessageContent("I can't play right now, I'm in the hospital!")
                )
            )
        elif player['ryo'] < GAME_COST:
            results.append(
                InlineQueryResultArticle(
                    id="game_fail_ryo",
                    title=f"❌ Not enough Ryo (Need {GAME_COST})",
                    description="Go rob someone or do missions!",
                    input_message_content=InputTextMessageContent(f"I'm too poor to play, I need {GAME_COST} Ryo.")
                )
            )
        else:
            # Player can play!
            # We must pre-calculate all 3 results
            bot_sign_name, bot_sign_emoji = random.choice(HAND_SIGNS)
            
            for sign_name, sign_emoji in HAND_SIGNS:
                
                # We calculate the result for *this* button
                if sign_name == bot_sign_name:
                    # This is the WINNING button
                    new_ryo = player['ryo'] + (GAME_WIN_AMOUNT - GAME_COST)
                    db.update_player(user_id, {'ryo': new_ryo}) # Update DB
                    result_text = (
                        f"🎲 **Hand Sign Guess!** 🎲\n\n"
                        f"You Chose: {sign_emoji}\n"
                        f"Bot Chose: {bot_sign_emoji}\n\n"
                        f"🎉 **IT'S A MATCH!** 🎉\n{escape(player['username'])} wins **{GAME_WIN_AMOUNT} Ryo**!"
                    )
                else:
                    # This is a LOSING button
                    new_ryo = player['ryo'] - GAME_COST
                    db.update_player(user_id, {'ryo': new_ryo}) # Update DB
                    result_text = (
                        f"🎲 **Hand Sign Guess!** 🎲\n\n"
                        f"You Chose: {sign_emoji}\n"
                        f"Bot Chose: {bot_sign_emoji}\n\n"
                        f"💔 **You lose!** {escape(player['username'])} lost {GAME_COST} Ryo."
                    )
                
                # Add a result for this button
                results.append(
                    InlineQueryResultArticle(
                        id=f"game_bet_{sign_name}_{uuid.uuid4()}", # Add UUID to make ID unique every time
                        title=f"🎲 Bet on {sign_emoji} {sign_name.title()}",
                        description=f"Cost: {GAME_COST} Ryo | Win: {GAME_WIN_AMOUNT} Ryo",
                        input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                    )
                )
        # --- END NEW GAME ---
            
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

    # cache_time=0 is VERY important for a game, so it's a new game every time
    await query.answer(results, cache_time=0)
