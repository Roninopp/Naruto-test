import logging
import uuid
import random
import datetime
from datetime import timezone
from html import escape
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Daily Pack ---
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

# 🎮 INTERACTIVE GAME ENEMIES
GAME_ENEMIES = {
    'zabuza': {
        'name': 'Zabuza Momochi',
        'image': '⚔️',
        'hp': 100,
        'attacks': {
            'water_dragon': {'name': 'Water Dragon', 'power': 40, 'weak_to': ['lightning'], 'strong_vs': ['fire']},
            'hidden_mist': {'name': 'Hidden Mist', 'power': 30, 'weak_to': ['wind'], 'strong_vs': ['none']}
        },
        'weakness': 'lightning',
        'reward': 200
    },
    'sound_ninja': {
        'name': 'Sound Ninja Quartet',
        'image': '🎵',
        'hp': 80,
        'attacks': {
            'sound_wave': {'name': 'Sound Wave', 'power': 25, 'weak_to': ['none'], 'strong_vs': ['none']},
            'curse_mark': {'name': 'Curse Mark', 'power': 35, 'weak_to': ['medical'], 'strong_vs': ['taijutsu']}
        },
        'weakness': 'genjutsu',
        'reward': 150
    },
    'itachi': {
        'name': 'Itachi Uchiha',
        'image': '🔴',
        'hp': 150,
        'attacks': {
            'amaterasu': {'name': 'Amaterasu', 'power': 60, 'weak_to': ['wind'], 'strong_vs': ['water']},
            'tsukuyomi': {'name': 'Tsukuyomi', 'power': 50, 'weak_to': ['sharingan'], 'strong_vs': ['genjutsu']}
        },
        'weakness': 'none',
        'reward': 500
    },
    'orochimaru': {
        'name': 'Orochimaru',
        'image': '🐍',
        'hp': 120,
        'attacks': {
            'snake_summon': {'name': 'Giant Snakes', 'power': 45, 'weak_to': ['fire'], 'strong_vs': ['earth']},
            'curse_seal': {'name': 'Curse Seal', 'power': 40, 'weak_to': ['medical'], 'strong_vs': ['none']}
        },
        'weakness': 'medical',
        'reward': 300
    },
    'akatsuki_grunt': {
        'name': 'Akatsuki Member',
        'image': '☁️',
        'hp': 90,
        'attacks': {
            'kunai_barrage': {'name': 'Kunai Barrage', 'power': 30, 'weak_to': ['none'], 'strong_vs': ['none']},
            'explosive_tags': {'name': 'Explosive Tags', 'power': 35, 'weak_to': ['substitution'], 'strong_vs': ['taijutsu']}
        },
        'weakness': 'ninjutsu',
        'reward': 180
    }
}

# Player Jutsu Options
PLAYER_JUTSUS = {
    'fireball': {'name': '🔥 Fireball Jutsu', 'type': 'fire', 'power': 35},
    'shadow_clone': {'name': '🌀 Shadow Clone', 'type': 'ninjutsu', 'power': 30},
    'substitution': {'name': '🍃 Substitution', 'type': 'escape', 'power': 0},  # Defensive
    'water_dragon': {'name': '🌊 Water Dragon', 'type': 'water', 'power': 40},
    'lightning_blade': {'name': '⚡ Lightning Blade', 'type': 'lightning', 'power': 45},
    'rasengan': {'name': '💫 Rasengan', 'type': 'ninjutsu', 'power': 50},
    'medical_ninjutsu': {'name': '💚 Medical Ninjutsu', 'type': 'medical', 'power': 0},  # Heal
    'genjutsu': {'name': '👁️ Genjutsu', 'type': 'genjutsu', 'power': 35}
}

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
    text = "☠️ **Top 5 Deadliest Ninja** ☠️\n\n"
    top_players = db.get_top_players_by_kills(limit=5)
    if not top_players:
        text += "No successful kills yet..."
    else:
        for i, p in enumerate(top_players):
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
            mention = f'<a href="tg://user?id={p["user_id"]}">{escape(p["username"])}</a>'
            text += f"{rank} {mention} - {p['kills']} Kills\n"
    return text

def get_top_rich_text():
    text = "💰 **Top 5 Richest Ninja** 💰\n\n"
    top_players = db.get_top_players_by_ryo(limit=5)
    if not top_players:
        text += "No one has any Ryo..."
    else:
        for i, p in enumerate(top_players):
            rank = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
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
        result_text = f"🎁 **Daily Pack!**\n{escape(player['username'])} got **{p_name}**!\n💰 +{p_amount} Ryo!"
    elif p_type == 'item':
        inventory = player.get('inventory') or []
        inventory.append(p_key)
        updates['inventory'] = inventory
        result_text = f"🎁 **Daily Pack!**\n{escape(player['username'])} got **{p_name}**!\n📦 Added to inventory."
    elif p_type == 'exp':
        updates['exp'] = player['exp'] + p_amount
        updates['total_exp'] = player['total_exp'] + p_amount
        result_text = f"🎁 **Daily Pack!**\n{escape(player['username'])} got **{p_name}**!\n✨ +{p_amount} EXP!"

    return result_text, updates


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline queries - shows game options."""
    query = update.inline_query
    if not query:
        return

    user_id = query.from_user.id
    player = db.get_player(user_id)
    results = []

    if player:
        is_hosp, _ = gl.get_hospital_status(player)
        
        # --- 1. Show Wallet ---
        wallet_text = get_wallet_text(player)
        results.append(
            InlineQueryResultArticle(
                id="wallet",
                title="🥷 Show My Wallet",
                description=f"Lvl {player['level']} | {player['ryo']:,} Ryo",
                input_message_content=InputTextMessageContent(wallet_text, parse_mode="HTML")
            )
        )
        
        # --- 2. Top Killers ---
        results.append(
            InlineQueryResultArticle(
                id="top_killers",
                title="☠️ Top 5 Killers",
                description="Show leaderboard",
                input_message_content=InputTextMessageContent(get_top_killers_text(), parse_mode="HTML")
            )
        )
        
        # --- 3. Top Richest ---
        results.append(
            InlineQueryResultArticle(
                id="top_rich",
                title="💰 Top 5 Richest",
                description="Show leaderboard",
                input_message_content=InputTextMessageContent(get_top_rich_text(), parse_mode="HTML")
            )
        )
        
        # --- 4. Daily Pack ---
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
            result_text, updates = get_daily_pack_prize(player)
            db.update_player(user_id, updates)
            results.append(
                InlineQueryResultArticle(
                    id="daily_pack",
                    title="🎁 Daily Shinobi Pack!",
                    description="Free rewards!",
                    input_message_content=InputTextMessageContent(result_text, parse_mode="HTML")
                )
            )
        
        # 🎮 INTERACTIVE JUTSU BATTLE GAMES
        if not is_hosp and player['ryo'] >= 50:
            # Show different enemy options
            for enemy_key, enemy_data in list(GAME_ENEMIES.items())[:3]:  # Show 3 enemies
                # Create game start message with buttons
                game_id = f"{user_id}_{enemy_key}_{uuid.uuid4().hex[:8]}"
                
                start_text = (
                    f"🎮 **NINJA BATTLE!** 🎮\n\n"
                    f"You encounter: **{enemy_data['name']}** {enemy_data['image']}\n"
                    f"Enemy HP: {enemy_data['hp']}\n"
                    f"Your HP: 100\n\n"
                    f"Choose your jutsu wisely!"
                )
                
                # Create jutsu selection buttons
                keyboard = [
                    [
                        InlineKeyboardButton(
                            PLAYER_JUTSUS['fireball']['name'],
                            callback_data=f"jutsu_game_{game_id}_fireball_{enemy_key}"
                        ),
                        InlineKeyboardButton(
                            PLAYER_JUTSUS['shadow_clone']['name'],
                            callback_data=f"jutsu_game_{game_id}_shadow_clone_{enemy_key}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            PLAYER_JUTSUS['water_dragon']['name'],
                            callback_data=f"jutsu_game_{game_id}_water_dragon_{enemy_key}"
                        ),
                        InlineKeyboardButton(
                            PLAYER_JUTSUS['lightning_blade']['name'],
                            callback_data=f"jutsu_game_{game_id}_lightning_blade_{enemy_key}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            PLAYER_JUTSUS['rasengan']['name'],
                            callback_data=f"jutsu_game_{game_id}_rasengan_{enemy_key}"
                        ),
                        InlineKeyboardButton(
                            PLAYER_JUTSUS['genjutsu']['name'],
                            callback_data=f"jutsu_game_{game_id}_genjutsu_{enemy_key}"
                        )
                    ]
                ]
                
                results.append(
                    InlineQueryResultArticle(
                        id=f"game_{enemy_key}_{uuid.uuid4().hex[:8]}",
                        title=f"🎮 Battle {enemy_data['name']}!",
                        description=f"Cost: 50 Ryo | Reward: {enemy_data['reward']} Ryo",
                        input_message_content=InputTextMessageContent(start_text, parse_mode="HTML"),
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                )
        
    else:
        # Not registered
        results.append(
            InlineQueryResultArticle(
                id="register",
                title="❌ Not registered!",
                description="Click to join",
                input_message_content=InputTextMessageContent(f"How do I /register for @{context.bot.username}?")
            )
        )

    try:
        await query.answer(results, cache_time=0)
    except Exception as e:
        logger.error(f"Inline query error: {e}")


# 🎮 CALLBACK HANDLER FOR JUTSU GAME BUTTONS
async def jutsu_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles button clicks in jutsu battle games."""
    query = update.callback_query
    await query.answer()
    
    # Parse callback data: jutsu_game_{user_id}_{enemy_key}_{uuid}_{jutsu}_{enemy}
    parts = query.data.split('_')
    if len(parts) < 6:
        return
    
    user_id_from_game = int(parts[2])
    jutsu_choice = parts[4]
    enemy_key = parts[5]
    
    # Verify it's the right player
    if query.from_user.id != user_id_from_game:
        await query.answer("This is not your game!", show_alert=True)
        return
    
    player = db.get_player(query.from_user.id)
    if not player or player['ryo'] < 50:
        await query.answer("Not enough Ryo!", show_alert=True)
        return
    
    # Get enemy and player jutsu
    enemy_data = GAME_ENEMIES[enemy_key]
    player_jutsu = PLAYER_JUTSUS[jutsu_choice]
    
    # Enemy chooses random attack
    enemy_attack_key = random.choice(list(enemy_data['attacks'].keys()))
    enemy_attack = enemy_data['attacks'][enemy_attack_key]
    
    # Calculate damage
    player_damage = player_jutsu['power']
    enemy_damage = enemy_attack['power']
    
    # Type effectiveness
    if player_jutsu['type'] == enemy_data['weakness']:
        player_damage = int(player_damage * 1.5)
        effectiveness_text = "💥 Super effective!"
    elif player_jutsu['type'] in enemy_attack.get('weak_to', []):
        player_damage = int(player_damage * 0.5)
        effectiveness_text = "😔 Not very effective..."
    else:
        effectiveness_text = ""
    
    # Determine winner
    player_hp = 100 - enemy_damage
    enemy_hp = enemy_data['hp'] - player_damage
    
    if enemy_hp <= 0:
        # Player wins!
        result_text = (
            f"🎮 **BATTLE RESULT!** 🎮\n\n"
            f"You used: {player_jutsu['name']}\n"
            f"Damage dealt: {player_damage}\n"
            f"{effectiveness_text}\n\n"
            f"{enemy_data['name']} used: {enemy_attack['name']}\n"
            f"Damage taken: {enemy_damage}\n\n"
            f"🏆 **VICTORY!** 🏆\n"
            f"You defeated {enemy_data['name']}!\n"
            f"💰 Reward: +{enemy_data['reward']} Ryo\n"
            f"✨ +30 EXP!"
        )
        
        updates = {
            'ryo': player['ryo'] - 50 + enemy_data['reward'],
            'exp': player['exp'] + 30,
            'total_exp': player['total_exp'] + 30
        }
    elif player_hp <= 0:
        # Player loses
        result_text = (
            f"🎮 **BATTLE RESULT!** 🎮\n\n"
            f"You used: {player_jutsu['name']}\n"
            f"Damage dealt: {player_damage}\n"
            f"{effectiveness_text}\n\n"
            f"{enemy_data['name']} used: {enemy_attack['name']}\n"
            f"Damage taken: {enemy_damage}\n\n"
            f"💔 **DEFEAT!** 💔\n"
            f"You were defeated by {enemy_data['name']}!\n"
            f"💸 Lost: 50 Ryo"
        )
        
        updates = {'ryo': player['ryo'] - 50}
    else:
        # Close battle - decided by luck
        if random.random() < 0.5:
            result_text = (
                f"🎮 **BATTLE RESULT!** 🎮\n\n"
                f"You used: {player_jutsu['name']}\n"
                f"Damage dealt: {player_damage}\n"
                f"{effectiveness_text}\n\n"
                f"{enemy_data['name']} used: {enemy_attack['name']}\n"
                f"Damage taken: {enemy_damage}\n\n"
                f"⚔️ **CLOSE FIGHT!** ⚔️\n"
                f"You narrowly win!\n"
                f"💰 Reward: +{int(enemy_data['reward'] * 0.7)} Ryo"
            )
            updates = {'ryo': player['ryo'] - 50 + int(enemy_data['reward'] * 0.7)}
        else:
            result_text = (
                f"🎮 **BATTLE RESULT!** 🎮\n\n"
                f"You used: {player_jutsu['name']}\n"
                f"Damage dealt: {player_damage}\n"
                f"{effectiveness_text}\n\n"
                f"{enemy_data['name']} used: {enemy_attack['name']}\n"
                f"Damage taken: {enemy_damage}\n\n"
                f"⚔️ **CLOSE FIGHT!** ⚔️\n"
                f"You narrowly lose!\n"
                f"💸 Lost: 40 Ryo"
            )
            updates = {'ryo': player['ryo'] - 40}
    
    # Update database
    db.update_player(query.from_user.id, updates)
    
    # Add "Play Again" button
    keyboard = [[InlineKeyboardButton("🎮 Play Again?", switch_inline_query_current_chat="")]]
    
    # Edit the message with result
    try:
        await query.edit_message_text(
            text=result_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error editing game message: {e}")
