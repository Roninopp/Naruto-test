import logging
import uuid
import random
import datetime # <-- NEW IMPORT
from html import escape
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- NEW: Daily Pack Constants ---
PACK_COMMON_CHANCE = 0.70 # 70%
PACK_UNCOMMON_CHANCE = 0.20 # 20%
PACK_RARE_CHANCE = 0.08 # 8%
# Legendary is the remaining 2%
# ------------------------------

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

# --- NEW HELPER FUNCTION ---
def get_daily_pack_prize(player):
    """
    Calculates a random prize for the daily pack.
    Returns (prize_text, updates_dict)
    """
    roll = random.random()
    
    if roll < PACK_COMMON_CHANCE:
        # Common: 50-100 Ryo
        prize_ryo = random.randint(50, 100)
        prize_text = f"💰 **{prize_ryo} Ryo**"
        updates = {'ryo': player['ryo'] + prize_ryo}
        return prize_text, updates
        
    elif roll < PACK_COMMON_CHANCE + PACK_UNCOMMON_CHANCE:
        # Uncommon: 150-250 Ryo
        prize_ryo = random.randint(150, 250)
        prize_text = f"💰💰 **{prize_ryo} Ryo**"
        updates = {'ryo': player['ryo'] + prize_ryo}
        return prize_text, updates
        
    elif roll < PACK_COMMON_CHANCE + PACK_UNCOMMON_CHANCE + PACK_RARE_CHANCE:
        # Rare: A random pill
        pill = random.choice(['health_potion', 'chakra_pill'])
        prize_text = f"🧪 **1x {gl.SHOP_INVENTORY[pill]['name']}**"
        
        inventory = player.get('inventory') or []
        # Handle if inventory is string (old data) or list
        if isinstance(inventory, str):
            try:
                inventory = json.loads(inventory)
                if not isinstance(inventory, list): inventory = []
            except:
                inventory = []
                
        inventory.append(pill)
        updates = {'inventory': inventory}
        return prize_text, updates
        
    else:
        # Legendary: 500 Ryo + 100 EXP
        prize_ryo = 500
        prize_exp = 100
        prize_text = f"🎉 **LEGENDARY!** {prize_ryo} Ryo and {prize_exp} EXP!"
        updates = {
            'ryo': player['ryo'] + prize_ryo,
            'exp': player['exp'] + prize_exp,
            'total_exp': player['total_exp'] + prize_exp
        }
        # We can even check for level up here if we want, but let's keep it simple
        return prize_text, updates
# --- END NEW HELPER ---


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
        
        # --- 4. REPLACED: Daily Shinobi Pack ---
        today = datetime.date.today()
        last_claim = player.get('last_inline_game_date')
        
        # Convert from DB string if needed
        if isinstance(last_claim, str):
            try:
                last_claim = datetime.date.fromisoformat(last_claim)
            except ValueError:
                last_claim = None # Handle bad data

        if last_claim == today:
            # --- Already claimed ---
            results.append(
                InlineQueryResultArticle(
                    id="daily_pack_claimed",
                    title="❌ Daily Pack Already Claimed",
                    description="Come back tomorrow for your next free pack!",
                    input_message_content=InputTextMessageContent(
                        f"{escape(player['username'])} is patiently waiting for their next daily pack."
                    )
                )
            )
        else:
            # --- Not claimed yet! ---
            
            # 1. Determine the prize
            prize_text, prize_updates = get_daily_pack_prize(player)
            
            # 2. Add the "claimed" timestamp to the updates
            prize_updates['last_inline_game_date'] = today
            
            # 3. Save to database
            db.update_player(user_id, prize_updates)
            
            # 4. Create the result
            results.append(
                InlineQueryResultArticle(
                    id="daily_pack_claim",
                    title="🎒 Open your Daily Shinobi Pack!",
                    description="Click to see what you got!",
                    input_message_content=InputTextMessageContent(
                        f"🎉 **{escape(player['username'])} opened their Daily Shinobi Pack and found...**\n\n{prize_text}!",
                        parse_mode="HTML"
                    )
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
