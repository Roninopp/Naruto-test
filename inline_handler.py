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

# Shadow Clone Training
CLONE_COST = 80
CLONE_TRAINING = {
    'beginner': {'success': 0.30, 'reward': 250, 'name': 'Beginner (30% success)'},
    'intermediate': {'success': 0.20, 'reward': 500, 'name': 'Intermediate (20% success)'},
    'advanced': {'success': 0.10, 'reward': 1000, 'name': 'Advanced (10% success)'},
    'forbidden': {'success': 0.05, 'reward': 2500, 'name': 'Forbidden Jutsu (5% success)'}
}

# Ninja Battle Royale (Rock-Paper-Scissors with characters)
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

# Akatsuki Encounter
AKATSUKI_COST = 150
AKATSUKI_MEMBERS = {
    'itachi': {'name': 'Itachi Uchiha', 'image': 'https://i.imgur.com/4Rq5xOE.jpg', 'difficulty': 0.25, 'reward': 600},
    'pain': {'name': 'Pain', 'image': 'https://i.imgur.com/nE6Bk2P.jpg', 'difficulty': 0.15, 'reward': 1000},
    'madara': {'name': 'Madara Uchiha', 'image': 'https://i.imgur.com/8sN3yHD.jpg', 'difficulty': 0.08, 'reward': 1800},
    'obito': {'name': 'Obito (Tobi)', 'image': 'https://i.imgur.com/9wK5xPm.jpg', 'difficulty': 0.20, 'reward': 750}
}

# Summoning Jutsu
SUMMON_COST = 120
SUMMON_CREATURES = {
    'gamabunta': {'name': 'Gamabunta (Giant Toad)', 'rarity': 0.20, 'power': 800, 'image': 'https://i.imgur.com/qK3xNvW.jpg'},
    'manda': {'name': 'Manda (Giant Snake)', 'rarity': 0.15, 'power': 1000, 'image': 'https://i.imgur.com/7dH3kRx.jpg'},
    'katsuyu': {'name': 'Katsuyu (Giant Slug)', 'rarity': 0.25, 'power': 600, 'image': 'https://i.imgur.com/5pN8yHm.jpg'},
    'kurama': {'name': 'Kurama (Nine-Tails)', 'rarity': 0.05, 'power': 3000, 'image': 'https://i.imgur.com/nB6Hk2R.jpg'},
    'failed': {'name': 'Summoning Failed!', 'rarity': 0.35, 'power': 0, 'image': None}
}

# Chunin Exam Challenge
CHUNIN_COST = 90
CHUNIN_STAGES = {
    'written_test': {'difficulty': 0.40, 'reward': 200, 'desc': '📝 Written Test'},
    'forest_survival': {'difficulty': 0.30, 'reward': 350, 'desc': '🌲 Forest of Death'},
    'tournament': {'difficulty': 0.20, 'reward': 550, 'desc': '⚔️ Tournament Finals'}
}

# Tailed Beast Encounter
TAILED_BEAST_COST = 200
TAILED_BEASTS = [
    {'name': 'Shukaku (One-Tail)', 'image': 'https://i.imgur.com/xK9nR3P.jpg', 'power': 1, 'reward': 300},
    {'name': 'Matatabi (Two-Tails)', 'image': 'https://i.imgur.com/yN8kR5Q.jpg', 'power': 2, 'reward': 400},
    {'name': 'Isobu (Three-Tails)', 'image': 'https://i.imgur.com/qL4nH7M.jpg', 'power': 3, 'reward': 500},
    {'name': 'Son Goku (Four-Tails)', 'image': 'https://i.imgur.com/rM9pK6N.jpg', 'power': 4, 'reward': 700},
    {'name': 'Kokuo (Five-Tails)', 'image': 'https://i.imgur.com/tP5nJ8L.jpg', 'power': 5, 'reward': 900},
    {'name': 'Saiken (Six-Tails)', 'image': 'https://i.imgur.com/wQ7kM4O.jpg', 'power': 6, 'reward': 1100},
    {'name': 'Chomei (Seven-Tails)', 'image': 'https://i.imgur.com/xR3nL6P.jpg', 'power': 7, 'reward': 1400},
    {'name': 'Gyuki (Eight-Tails)', 'image': 'https://i.imgur.com/yT8mN5Q.jpg', 'power': 8, 'reward': 1800},
    {'name': 'Kurama (Nine-Tails)', 'image': 'https://i.imgur.com/nB6Hk2R.jpg', 'power': 9, 'reward': 2500}
]

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
    
    updates = {'inline_pack_cooldown': datetime.datetime.now(timezone.utc)}
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

# 🆕 EPIC NARUTO GAME FUNCTIONS

def play_shadow_clone_training(player, difficulty):
    """Train with shadow clones at different difficulty levels."""
    training = CLONE_TRAINING[difficulty]
    
    if random.random() < training['success']:
        result_text = (
            f"🌀 **SHADOW CLONE TRAINING** 🌀\n\n"
            f"Difficulty: {training['name']}\n\n"
            f"✅ **SUCCESS!**\n"
            f"Your clones completed the training!\n"
            f"💰 Reward: +{training['reward']} Ryo\n"
            f"✨ Experience gained!"
        )
        updates = {'ryo': player['ryo'] - CLONE_COST + training['reward']}
    else:
        result_text = (
            f"🌀 **SHADOW CLONE TRAINING** 🌀\n\n"
            f"Difficulty: {training['name']}\n\n"
            f"❌ **FAILED!**\n"
            f"Your clones disappeared before completing training!\n"
            f"💸 Lost: {CLONE_COST} Ryo"
        )
        updates = {'ryo': player['ryo'] - CLONE_COST}
    
    return result_text, updates

def play_ninja_battle(player, choice):
    """Battle using character selection (rock-paper-scissors style)."""
    player_char = BATTLE_CHARACTERS[choice]
    opponent_choice = random.choice(list(BATTLE_CHARACTERS.keys()))
    opponent_char = BATTLE_CHARACTERS[opponent_choice]
    
    if choice == opponent_choice:
        result = "DRAW"
        winnings = 0
        result_emoji = "🤝"
    elif (
        (player_char['strength'] == 'Taijutsu' and opponent_char['strength'] == 'Genjutsu') or
        (player_char['strength'] == 'Ninjutsu' and opponent_char['strength'] == 'Taijutsu') or
        (player_char['strength'] == 'Genjutsu' and opponent_char['strength'] == 'Ninjutsu')
    ):
        result = "VICTORY"
        winnings = BATTLE_COST * 2
        result_emoji = "🏆"
    else:
        result = "DEFEAT"
        winnings = 0
        result_emoji = "💔"
    
    result_text = (
        f"⚔️ **NINJA BATTLE ROYALE** ⚔️\n\n"
        f"Your Fighter: {player_char['name']}\n"
        f"Special Move: {player_char['special']}\n\n"
        f"VS\n\n"
        f"Opponent: {opponent_char['name']}\n"
        f"Special Move: {opponent_char['special']}\n\n"
        f"{result_emoji} **{result}!** {result_emoji}\n"
    )
    
    if result == "VICTORY":
        result_text += f"💰 You won {winnings} Ryo!"
        updates = {'ryo': player['ryo'] - BATTLE_COST + winnings}
    elif result == "DRAW":
        result_text += f"🤝 No one wins! Ryo returned."
        updates = {}
    else:
        result_text += f"💸 You lost {BATTLE_COST} Ryo!"
        updates = {'ryo': player['ryo'] - BATTLE_COST}
    
    return result_text, updates, player_char['image']

def play_akatsuki_encounter(player, member_key):
    """Fight an Akatsuki member."""
    member = AKATSUKI_MEMBERS[member_key]
    player_power = player['level'] * 10 + gl.get_total_stats(player)['strength']
    
    base_chance = member['difficulty']
    power_bonus = min(0.15, player_power / 1000)
    success_chance = base_chance + power_bonus
    
    if random.random() < success_chance:
        result_text = (
            f"🔴 **AKATSUKI ENCOUNTER** 🔴\n\n"
            f"Enemy: {member['name']}\n\n"
            f"⚔️ An intense battle unfolds!\n"
            f"Your determination and skill prevail!\n\n"
            f"🏆 **VICTORY!**\n"
            f"💰 Bounty: +{member['reward']} Ryo\n"
            f"✨ +50 EXP gained!"
        )
        updates = {
            'ryo': player['ryo'] - AKATSUKI_COST + member['reward'],
            'exp': player['exp'] + 50,
            'total_exp': player['total_exp'] + 50
        }
    else:
        result_text = (
            f"🔴 **AKATSUKI ENCOUNTER** 🔴\n\n"
            f"Enemy: {member['name']}\n\n"
            f"⚔️ You fought bravely but...\n"
            f"The Akatsuki member was too powerful!\n\n"
            f"💔 **DEFEATED!**\n"
            f"💸 Lost: {AKATSUKI_COST} Ryo"
        )
        updates = {'ryo': player['ryo'] - AKATSUKI_COST}
    
    return result_text, updates, member['image']

def play_summoning_jutsu(player):
    """Summon a creature with random rarity."""
    weights = [c['rarity'] for c in SUMMON_CREATURES.values()]
    summoned = random.choices(list(SUMMON_CREATURES.values()), weights=weights, k=1)[0]
    
    if summoned['power'] == 0:
        result_text = (
            f"🐸 **SUMMONING JUTSU** 🐸\n\n"
            f"You perform the hand signs...\n"
            f"血 Blood offering made!\n\n"
            f"💨 *POOF*\n\n"
            f"❌ **SUMMONING FAILED!**\n"
            f"Not enough chakra control!\n"
            f"💸 Lost: {SUMMON_COST} Ryo"
        )
        updates = {'ryo': player['ryo'] - SUMMON_COST}
        image = None
    else:
        result_text = (
            f"🐸 **SUMMONING JUTSU** 🐸\n\n"
            f"You perform the hand signs...\n"
            f"血 Blood offering made!\n\n"
            f"💨 *POOF*\n\n"
            f"✨ **{summoned['name']} APPEARS!**\n"
            f"Power Level: {summoned['power']:,}\n"
            f"💰 Reward: +{summoned['power']} Ryo"
        )
        net_gain = summoned['power'] - SUMMON_COST
        result_text += f"\nNet: {'+' if net_gain >= 0 else ''}{net_gain} Ryo"
        updates = {'ryo': player['ryo'] - SUMMON_COST + summoned['power']}
        image = summoned['image']
    
    return result_text, updates, image

def play_chunin_exam(player, stage_key):
    """Take the Chunin Exam stages."""
    stage = CHUNIN_STAGES[stage_key]
    
    player_stats = gl.get_total_stats(player)
    base_chance = stage['difficulty']
    level_bonus = min(0.20, player['level'] / 100)
    stat_bonus = min(0.10, player_stats['intelligence'] / 200)
    
    success_chance = base_chance + level_bonus + stat_bonus
    
    if random.random() < success_chance:
        result_text = (
            f"📜 **CHUNIN EXAM** 📜\n\n"
            f"Stage: {stage['desc']}\n\n"
            f"You demonstrate exceptional skill!\n\n"
            f"✅ **PASSED!**\n"
            f"💰 Reward: +{stage['reward']} Ryo\n"
            f"✨ +30 EXP gained!"
        )
        updates = {
            'ryo': player['ryo'] - CHUNIN_COST + stage['reward'],
            'exp': player['exp'] + 30,
            'total_exp': player['total_exp'] + 30
        }
    else:
        result_text = (
            f"📜 **CHUNIN EXAM** 📜\n\n"
            f"Stage: {stage['desc']}\n\n"
            f"Despite your efforts...\n\n"
            f"❌ **FAILED!**\n"
            f"Better luck next time!\n"
            f"💸 Lost: {CHUNIN_COST} Ryo"
        )
        updates = {'ryo': player['ryo'] - CHUNIN_COST}
    
    return result_text, updates

def play_tailed_beast_encounter(player):
    """Encounter a random Tailed Beast."""
    weights = [10 - beast['power'] for beast in TAILED_BEASTS]
    beast = random.choices(TAILED_BEASTS, weights=weights, k=1)[0]
    
    player_power = player['level'] * 10 + gl.get_total_stats(player)['strength']
    base_chance = 0.50 - (beast['power'] * 0.03)
    power_bonus = min(0.25, player_power / 1000)
    success_chance = max(0.10, base_chance + power_bonus)
    
    if random.random() < success_chance:
        result_text = (
            f"🦊 **TAILED BEAST ENCOUNTER** 🦊\n\n"
            f"You encountered: {beast['name']}\n"
            f"Tails: {beast['power']} 🔥\n\n"
            f"⚔️ Epic battle ensues!\n"
            f"Your chakra clashes with the beast's!\n\n"
            f"🏆 **VICTORY!**\n"
            f"You sealed the beast temporarily!\n"
            f"💰 Massive Reward: +{beast['reward']} Ryo\n"
            f"✨ +100 EXP gained!"
        )
        updates = {
            'ryo': player['ryo'] - TAILED_BEAST_COST + beast['reward'],
            'exp': player['exp'] + 100,
            'total_exp': player['total_exp'] + 100
        }
    else:
        result_text = (
            f"🦊 **TAILED BEAST ENCOUNTER** 🦊\n\n"
            f"You encountered: {beast['name']}\n"
            f"Tails: {beast['power']} 🔥\n\n"
            f"⚔️ The beast's power is overwhelming!\n"
            f"You barely escape with your life!\n\n"
            f"💔 **DEFEATED!**\n"
            f"💸 Lost: {TAILED_BEAST_COST} Ryo"
        )
        updates = {'ryo': player['ryo'] - TAILED_BEAST_COST}
    
    return result_text, updates, beast['image']


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
                description=f"Post your Lvl {player['level']} | {player['ryo']} Ryo card",
                input_message_content=InputTextMessageContent(wallet_text, parse_mode="HTML")
            )
        )
        
        # --- 2. Show Top Killers ---
        killers_text = get_top_killers_text()
        results.append(
            InlineQueryResultArticle(
                id="top_killers",
                title="☠️ Show Top 5 Killers",
                description="Post the 'Top Killers' leaderboard",
                input_message_content=InputTextMessageContent(killers_text, parse_mode="HTML")
            )
        )
        
        # --- 3. Show Top Richest ---
        rich_text = get_top_rich_text()
        results.append(
            InlineQueryResultArticle(
                id="top_rich",
                title="💰 Show Top 5 Richest",
                description="Post the 'Top Richest' leaderboard",
                input_message_content=InputTextMessageContent(rich_text, parse_mode="HTML")
            )
        )
        
        # --- 4. Daily Shinobi Pack ---
        now = datetime.datetime.now(timezone.utc)
        last_claim_time = player.get('inline_pack_cooldown')
        
        if last_claim_time and not isinstance(last_claim_time, datetime.datetime):
            try:
                last_claim_time = datetime.datetime.fromisoformat(last_claim_time)
            except:
                last_claim_time = None
        
        if last_claim_time and last_claim_time.tzinfo is None:
            last_claim_time = last_claim_time.replace(tzinfo=timezone.utc)
        
        if last_claim_time and (now - last_claim_time) < datetime.timedelta(hours=PACK_COOLDOWN_HOURS):
            remaining = (last_claim_time + datetime.timedelta(hours=PACK_COOLDOWN_HOURS)) - now
            remaining_hours = int(remaining.total_seconds() // 3600)
            remaining_minutes = int((remaining.total_seconds() % 3600) // 60)
            
            results.append(
                InlineQueryResultArticle(
                    id="daily_pack_claimed",
                    title="❌ Daily Pack on Cooldown",
                    description=f"Come back in {remaining_hours}h {remaining_minutes}m",
                    input_message_content=InputTextMessageContent(
                        f"I've already claimed my daily pack. Come back in {remaining_hours}h {remaining_minutes}m!"
                    )
                )
            )
        else:
            result_text, updates_to_be_done = get_daily_pack_prize(player)
            db.update_player(user_id, updates_to_be_done)

            results.append(
                InlineQueryResultArticle(
                    id="daily_pack_open",
                    title="🎁 Open Daily Shinobi Pack!",
                    description=f"Free rewards every {PACK_COOLDOWN_HOURS} hours!",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                )
            )
        
        # 🆕 EPIC NARUTO GAMES START HERE
        
        if is_hosp:
            results.append(
                InlineQueryResultArticle(
                    id="games_locked",
                    title="❌ Cannot play while hospitalized!",
                    description="Use /heal to recover first",
                    input_message_content=InputTextMessageContent("I can't play games right now, I'm in the hospital! 🏥")
                )
            )
        else:
            # --- 5. Shadow Clone Training (4 difficulties) ---
            if player['ryo'] >= CLONE_COST:
                for diff_key, diff_data in CLONE_TRAINING.items():
                    result_text, updates = play_shadow_clone_training(player, diff_key)
                    db.update_player(user_id, updates)
                    results.append(
                        InlineQueryResultArticle(
                            id=f"clone_{diff_key}_{uuid.uuid4()}",
                            title=f"🌀 Shadow Clone: {diff_data['name']}",
                            description=f"Cost: {CLONE_COST} Ryo | Reward: {diff_data['reward']} Ryo",
                            input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                        )
                    )
            
            # --- 6. Ninja Battle (3 characters) ---
            if player['ryo'] >= BATTLE_COST:
                for char_key, char_data in BATTLE_CHARACTERS.items():
                    result_text, updates, image = play_ninja_battle(player, char_key)
                    db.update_player(user_id, updates)
                    results.append(
                        InlineQueryResultPhoto(
                            id=f"battle_{char_key}_{uuid.uuid4()}",
                            photo_url=image,
                            thumbnail_url=image,
                            title=f"⚔️ Fight as {char_data['name']}",
                            description=f"Cost: {BATTLE_COST} Ryo | Win: {BATTLE_COST * 2} Ryo",
                            caption=result_text,
                            parse_mode="HTML"
                        )
                    )
            
            # --- 7. Akatsuki Encounters (4 members) ---
            if player['ryo'] >= AKATSUKI_COST:
                for member_key, member_data in AKATSUKI_MEMBERS.items():
                    result_text, updates, image = play_akatsuki_encounter(player, member_key)
                    db.update_player(user_id, updates)
                    results.append(
                        InlineQueryResultPhoto(
                            id=f"akatsuki_{member_key}_{uuid.uuid4()}",
                            photo_url=image,
                            thumbnail_url=image,
                            title=f"🔴 Fight {member_data['name']}",
                            description=f"Cost: {AKATSUKI_COST} Ryo | Reward: {member_data['reward']} Ryo",
                            caption=result_text,
                            parse_mode="HTML"
                        )
                    )
            
            # --- 8. Summoning Jutsu ---
            if player['ryo'] >= SUMMON_COST:
                result_text, updates, image = play_summoning_jutsu(player)
                db.update_player(user_id, updates)
                
                if image:
                    results.append(
                        InlineQueryResultPhoto(
                            id=f"summon_{uuid.uuid4()}",
                            photo_url=image,
                            thumbnail_url=image,
                            title=f"🐸 Summoning Jutsu!",
                            description=f"Cost: {SUMMON_COST} Ryo | Summon powerful allies!",
                            caption=result_text,
                            parse_mode="HTML"
                        )
                    )
                else:
                    results.append(
                        InlineQueryResultArticle(
                            id=f"summon_{uuid.uuid4()}",
                            title=f"🐸 Summoning Jutsu!",
                            description=f"Cost: {SUMMON_COST} Ryo | Summon powerful allies!",
                            input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                        )
                    )
            
            # --- 9. Chunin Exam (3 stages) ---
            if player['ryo'] >= CHUNIN_COST:
                for stage_key, stage_data in CHUNIN_STAGES.items():
                    result_text, updates = play_chunin_exam(player, stage_key)
                    db.update_player(user_id, updates)
                    results.append(
                        InlineQueryResultArticle(
                            id=f"chunin_{stage_key}_{uuid.uuid4()}",
                            title=f"📜 Chunin Exam: {stage_data['desc']}",
                            description=f"Cost: {CHUNIN_COST} Ryo | Reward: {stage_data['reward']} Ryo",
                            input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                        )
                    )
            
            # --- 10. Tailed Beast Encounter ---
            if player['ryo'] >= TAILED_BEAST_COST:
                result_text, updates, image = play_tailed_beast_encounter(player)
                db.update_player(user_id, updates)
                results.append(
                    InlineQueryResultPhoto(
                        id=f"beast_{uuid.uuid4()}",
                        photo_url=image,
                        thumbnail_url=image,
                        title=f"🦊 Tailed Beast Encounter!",
                        description=f"Cost: {TAILED_BEAST_COST} Ryo | Epic battle!",
                        caption=result_text,
                        parse_mode="HTML"
                    )
                )
            
    else:
        # --- Not registered ---
        results.append(
            InlineQueryResultArticle(
                id="register",
                title="❌ You are not registered!",
                description="Click to ask how to join",
                input_message_content=InputTextMessageContent(
                    f"Hey everyone, how do I /register for @{context.bot.username}?"
                )
            )
        )

    # cache_time=0 is important for games
    await query.answer(results, cache_time=0)
