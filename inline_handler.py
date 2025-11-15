import logging
import uuid
import random
import datetime
from datetime import timezone
from html import escape
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, InlineQueryResultPhoto
from telegram.ext import ContextTypes

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Daily Pack Loot Table ---
PACK_LOOT_TABLE = [
    (100, 'ryo', 'ryo', 50, "Common Ryo Pouch"),
    (100, 'ryo', 'ryo', 75, "Common Ryo Pouch"),
    (50,  'ryo', 'ryo', 150, "Uncommon Ryo Pouch"),
    (25,  'item', 'health_potion', 1, "Health Potion"),
    (10,  'ryo', 'ryo', 500, "Rare Ryo Chest"),
    (5,   'item', 'soldier_pill', 1, "Soldier Pill"),
    (1,   'exp', 'exp', 100, "Legendary EXP Scroll")
]

PACK_COOLDOWN_HOURS = 4

# 🆕 EPIC NARUTO GAME CONSTANTS
CLONE_COST = 80
CLONE_TRAINING = {
    'beginner': {'success': 0.30, 'reward': 250, 'name': 'Beginner (30%)'},
    'intermediate': {'success': 0.20, 'reward': 500, 'name': 'Intermediate (20%)'},
    'advanced': {'success': 0.10, 'reward': 1000, 'name': 'Advanced (10%)'},
    'forbidden': {'success': 0.05, 'reward': 2500, 'name': 'Forbidden (5%)'}
}

BATTLE_COST = 100
BATTLE_CHARACTERS = {
    'naruto': {
        'name': 'Naruto Uzumaki',
        'image': 'https://i.imgur.com/YqN7xQs.jpg',
        'strength': 'Taijutsu',
        'weakness': 'Genjutsu',
        'special': 'Rasengan'
    },
    'sasuke': {
        'name': 'Sasuke Uchiha', 
        'image': 'https://i.imgur.com/8kFvZOh.jpg',
        'strength': 'Ninjutsu',
        'weakness': 'Taijutsu',
        'special': 'Chidori'
    },
    'sakura': {
        'name': 'Sakura Haruno',
        'image': 'https://i.imgur.com/nYvR7pQ.jpg',
        'strength': 'Genjutsu',
        'weakness': 'Ninjutsu',
        'special': 'Chakra Punch'
    }
}

AKATSUKI_COST = 150
AKATSUKI_MEMBERS = {
    'itachi': {'name': 'Itachi Uchiha', 'image': 'https://i.imgur.com/4Rq5xOE.jpg', 'difficulty': 0.25, 'reward': 600},
    'pain': {'name': 'Pain', 'image': 'https://i.imgur.com/nE6Bk2P.jpg', 'difficulty': 0.15, 'reward': 1000},
    'madara': {'name': 'Madara Uchiha', 'image': 'https://i.imgur.com/8sN3yHD.jpg', 'difficulty': 0.08, 'reward': 1800},
}

SUMMON_COST = 120
CHUNIN_COST = 90
TAILED_BEAST_COST = 200

def get_wallet_text(player):
    is_hosp, _ = gl.get_hospital_status(player)
    status_text = "🏥 Hospitalized" if is_hosp else "❤️ Alive"
    return (
        f"<b>--- 🥷 {escape(player['username'])}'s Wallet 🥷 ---</b>\n\n"
        f"<b>Rank:</b> {player['rank']}\n"
        f"<b>Level:</b> {player['level']}\n"
        f"<b>Ryo:</b> {player['ryo']:,} 💰\n"
        f"<b>Kills:</b> {player.get('kills', 0)} ☠️\n"
        f"<b>Status:</b> {status_text}"
    )

def get_top_killers_text():
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
    prize = random.choices(PACK_LOOT_TABLE, weights=[p[0] for p in PACK_LOOT_TABLE], k=1)[0]
    _, p_type, p_key, p_amount, p_name = prize
    
    updates = {'inline_pack_cooldown': datetime.datetime.now(timezone.utc)}
    result_text = ""

    if p_type == 'ryo':
        updates['ryo'] = player['ryo'] + p_amount
        result_text = f"🎁 **Daily Pack!** 🎁\n{escape(player['username'])} opened a pack!\n💰 **+{p_amount} Ryo!**"
    elif p_type == 'item':
        inventory = player.get('inventory') or []
        inventory.append(p_key)
        updates['inventory'] = inventory
        result_text = f"🎁 **Daily Pack!** 🎁\n{escape(player['username'])} got a **{p_name}**!\n📦 Added to /inventory."
    elif p_type == 'exp':
        updates['exp'] = player['exp'] + p_amount
        updates['total_exp'] = player['total_exp'] + p_amount
        result_text = f"🎁 **Daily Pack!** 🎁\n{escape(player['username'])} found a **{p_name}**!\n✨ **+{p_amount} EXP!**"

    return result_text, updates


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline queries (@BotName ...) - OPTIMIZED FOR SPEED."""
    query = update.inline_query
    if not query:
        return

    user_id = query.from_user.id
    player = db.get_player(user_id)
    results = []

    if player:
        is_hosp, _ = gl.get_hospital_status(player)
        
        # --- 1. Show My Wallet (Instant) ---
        wallet_text = get_wallet_text(player)
        results.append(
            InlineQueryResultArticle(
                id="wallet",
                title="🥷 Show My Wallet",
                description=f"Lvl {player['level']} | {player['ryo']:,} Ryo",
                input_message_content=InputTextMessageContent(wallet_text, parse_mode="HTML")
            )
        )
        
        # --- 2. Top Killers (Instant) ---
        killers_text = get_top_killers_text()
        results.append(
            InlineQueryResultArticle(
                id="top_killers",
                title="☠️ Top 5 Killers",
                description="Show leaderboard",
                input_message_content=InputTextMessageContent(killers_text, parse_mode="HTML")
            )
        )
        
        # --- 3. Top Richest (Instant) ---
        rich_text = get_top_rich_text()
        results.append(
            InlineQueryResultArticle(
                id="top_rich",
                title="💰 Top 5 Richest",
                description="Show leaderboard",
                input_message_content=InputTextMessageContent(rich_text, parse_mode="HTML")
            )
        )
        
        # --- 4. Daily Pack (Only if available) ---
        now = datetime.datetime.now(timezone.utc)
        last_claim_time = player.get('inline_pack_cooldown')
        
        if last_claim_time and not isinstance(last_claim_time, datetime.datetime):
            try:
                last_claim_time = datetime.datetime.fromisoformat(last_claim_time)
            except:
                last_claim_time = None
        
        if last_claim_time and last_claim_time.tzinfo is None:
            last_claim_time = last_claim_time.replace(tzinfo=timezone.utc)
        
        pack_available = not last_claim_time or (now - last_claim_time) >= datetime.timedelta(hours=PACK_COOLDOWN_HOURS)
        
        if pack_available:
            # ⚡ ONLY calculate when showing option
            result_text, updates_to_be_done = get_daily_pack_prize(player)
            db.update_player(user_id, updates_to_be_done)

            results.append(
                InlineQueryResultArticle(
                    id="daily_pack",
                    title="🎁 Daily Shinobi Pack!",
                    description=f"Free rewards!",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                )
            )
        
        # 🎮 GAMES - Show ONLY options, calculate on click
        if not is_hosp:
            # --- Shadow Clone Training (Show options only) ---
            if player['ryo'] >= CLONE_COST:
                for diff_key, diff_data in list(CLONE_TRAINING.items())[:2]:  # Show only 2 to save space
                    # ⚡ Calculate instantly for ONE game
                    training = diff_data
                    success = random.random() < training['success']
                    
                    if success:
                        result_text = f"🌀 **SHADOW CLONE** 🌀\n\n{diff_data['name']}\n\n✅ **SUCCESS!**\n💰 +{training['reward']} Ryo!"
                        updates = {'ryo': player['ryo'] - CLONE_COST + training['reward']}
                    else:
                        result_text = f"🌀 **SHADOW CLONE** 🌀\n\n{diff_data['name']}\n\n❌ **FAILED!**\n💸 -{CLONE_COST} Ryo"
                        updates = {'ryo': player['ryo'] - CLONE_COST}
                    
                    db.update_player(user_id, updates)
                    
                    results.append(
                        InlineQueryResultArticle(
                            id=f"clone_{diff_key}_{uuid.uuid4()}",
                            title=f"🌀 Shadow Clone: {diff_data['name']}",
                            description=f"Cost: {CLONE_COST} | Reward: {diff_data['reward']}",
                            input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                        )
                    )
            
            # --- Ninja Battle (1 character with image) ---
            if player['ryo'] >= BATTLE_COST:
                # ⚡ Show ONLY Naruto to save time
                char_key = 'naruto'
                char_data = BATTLE_CHARACTERS[char_key]
                
                opponent_choice = random.choice(list(BATTLE_CHARACTERS.keys()))
                opponent_char = BATTLE_CHARACTERS[opponent_choice]
                
                # Quick battle logic
                if char_key == opponent_choice:
                    result = "DRAW 🤝"
                    winnings = 0
                elif (
                    (char_data['strength'] == 'Taijutsu' and opponent_char['strength'] == 'Genjutsu') or
                    (char_data['strength'] == 'Ninjutsu' and opponent_char['strength'] == 'Taijutsu') or
                    (char_data['strength'] == 'Genjutsu' and opponent_char['strength'] == 'Ninjutsu')
                ):
                    result = "VICTORY 🏆"
                    winnings = BATTLE_COST * 2
                else:
                    result = "DEFEAT 💔"
                    winnings = 0
                
                result_text = (
                    f"⚔️ **NINJA BATTLE** ⚔️\n\n"
                    f"You: {char_data['name']}\n"
                    f"VS\n"
                    f"Opponent: {opponent_char['name']}\n\n"
                    f"**{result}**"
                )
                
                if winnings > 0:
                    updates = {'ryo': player['ryo'] - BATTLE_COST + winnings}
                    result_text += f"\n💰 Won {winnings} Ryo!"
                elif result == "DRAW 🤝":
                    updates = {}
                else:
                    updates = {'ryo': player['ryo'] - BATTLE_COST}
                    result_text += f"\n💸 Lost {BATTLE_COST} Ryo"
                
                db.update_player(user_id, updates)
                
                results.append(
                    InlineQueryResultPhoto(
                        id=f"battle_{uuid.uuid4()}",
                        photo_url=char_data['image'],
                        thumbnail_url=char_data['image'],
                        title=f"⚔️ Fight as {char_data['name']}",
                        description=f"Cost: {BATTLE_COST} | Win: {BATTLE_COST * 2}",
                        caption=result_text,
                        parse_mode="HTML"
                    )
                )
            
            # --- Akatsuki Fight (1 member with image) ---
            if player['ryo'] >= AKATSUKI_COST:
                # ⚡ Show ONLY Itachi to save time
                member_key = 'itachi'
                member = AKATSUKI_MEMBERS[member_key]
                player_power = player['level'] * 10 + gl.get_total_stats(player)['strength']
                
                base_chance = member['difficulty']
                power_bonus = min(0.15, player_power / 1000)
                success = random.random() < (base_chance + power_bonus)
                
                if success:
                    result_text = (
                        f"🔴 **AKATSUKI FIGHT** 🔴\n\n"
                        f"Enemy: {member['name']}\n\n"
                        f"🏆 **VICTORY!**\n"
                        f"💰 +{member['reward']} Ryo\n"
                        f"✨ +50 EXP!"
                    )
                    updates = {
                        'ryo': player['ryo'] - AKATSUKI_COST + member['reward'],
                        'exp': player['exp'] + 50,
                        'total_exp': player['total_exp'] + 50
                    }
                else:
                    result_text = (
                        f"🔴 **AKATSUKI FIGHT** 🔴\n\n"
                        f"Enemy: {member['name']}\n\n"
                        f"💔 **DEFEATED!**\n"
                        f"💸 -{AKATSUKI_COST} Ryo"
                    )
                    updates = {'ryo': player['ryo'] - AKATSUKI_COST}
                
                db.update_player(user_id, updates)
                
                results.append(
                    InlineQueryResultPhoto(
                        id=f"akatsuki_{uuid.uuid4()}",
                        photo_url=member['image'],
                        thumbnail_url=member['image'],
                        title=f"🔴 Fight {member['name']}",
                        description=f"Cost: {AKATSUKI_COST} | Reward: {member['reward']}",
                        caption=result_text,
                        parse_mode="HTML"
                    )
                )
            
    else:
        # --- Not registered ---
        results.append(
            InlineQueryResultArticle(
                id="register",
                title="❌ Not registered!",
                description="Click to ask how to join",
                input_message_content=InputTextMessageContent(
                    f"How do I /register for @{context.bot.username}?"
                )
            )
        )

    # ⚡ Answer FAST with cache_time=0
    try:
        await query.answer(results, cache_time=0)
    except Exception as e:
        logger.error(f"Error answering inline query: {e}")
