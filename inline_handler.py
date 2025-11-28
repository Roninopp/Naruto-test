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

# 🎮 GAME STATE STORAGE (in-memory for active games)
ACTIVE_GAMES = {}

# 🎮 INTERACTIVE GAME ENEMIES with images
GAME_ENEMIES = {
    'z': {
        'name': 'Zabuza Momochi',
        'image': 'https://envs.sh/Vux.jpg',
        'emoji': '⚔️',
        'max_hp': 120,
        'attacks': {
            'wd': {'name': 'Water Dragon Jutsu', 'power': 25, 'chakra': 20, 'weak_to': ['l'], 'strong_vs': ['f']},
            'hm': {'name': 'Hidden Mist Technique', 'power': 18, 'chakra': 15, 'weak_to': ['w'], 'strong_vs': []},
            'sw': {'name': 'Silent Killing', 'power': 30, 'chakra': 25, 'weak_to': [], 'strong_vs': []}
        },
        'weakness': 'l',
        'reward': 250,
        'chakra': 100
    },
    's': {
        'name': 'Sound Ninja Quartet',
        'image': 'https://envs.sh/VFE.jpg',
        'emoji': '🎵',
        'max_hp': 100,
        'attacks': {
            'sw': {'name': 'Sound Wave Blast', 'power': 20, 'chakra': 15, 'weak_to': [], 'strong_vs': []},
            'cm': {'name': 'Curse Mark Power', 'power': 28, 'chakra': 20, 'weak_to': ['m'], 'strong_vs': ['t']},
            'kb': {'name': 'Kunai Barrage', 'power': 15, 'chakra': 10, 'weak_to': [], 'strong_vs': []}
        },
        'weakness': 'g',
        'reward': 180,
        'chakra': 80
    },
    'i': {
        'name': 'Itachi Uchiha',
        'image': 'https://envs.sh/VFD.jpg',
        'emoji': '🔴',
        'max_hp': 150,
        'attacks': {
            'am': {'name': 'Amaterasu', 'power': 40, 'chakra': 35, 'weak_to': ['w'], 'strong_vs': ['wa']},
            'ts': {'name': 'Tsukuyomi', 'power': 35, 'chakra': 30, 'weak_to': [], 'strong_vs': ['g']},
            'fb': {'name': 'Fireball Jutsu', 'power': 25, 'chakra': 20, 'weak_to': ['wa'], 'strong_vs': []}
        },
        'weakness': '',
        'reward': 500,
        'chakra': 120
    }
}

# Player Jutsu Options
PLAYER_JUTSUS = {
    'f': {'name': '🔥 Fireball', 'type': 'f', 'power': 25, 'chakra': 15, 'heal': 0},
    'sc': {'name': '🌀 Shadow Clone', 'type': 'n', 'power': 20, 'chakra': 20, 'heal': 0},
    'wa': {'name': '🌊 Water Dragon', 'type': 'wa', 'power': 30, 'chakra': 25, 'heal': 0},
    'l': {'name': '⚡ Lightning Blade', 'type': 'l', 'power': 35, 'chakra': 30, 'heal': 0},
    'r': {'name': '💫 Rasengan', 'type': 'n', 'power': 40, 'chakra': 35, 'heal': 0},
    'g': {'name': '👁️ Genjutsu', 'type': 'g', 'power': 28, 'chakra': 20, 'heal': 0},
    'h': {'name': '💚 Heal', 'type': 'heal', 'power': 0, 'chakra': 25, 'heal': 30},
    't': {'name': '👊 Taijutsu', 'type': 't', 'power': 15, 'chakra': 5, 'heal': 0}
}

def health_bar(current, max_hp, length=10):
    """Generate health bar visual."""
    filled = int((current / max_hp) * length)
    bar = '█' * filled + '░' * (length - filled)
    return f"{bar} {current}/{max_hp}"

def chakra_bar(current, max_chakra, length=10):
    """Generate chakra bar visual."""
    filled = int((current / max_chakra) * length)
    bar = '▰' * filled + '▱' * (length - filled)
    return f"{bar} {current}/{max_chakra}"

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
            for enemy_key, enemy_data in GAME_ENEMIES.items():
                game_id = uuid.uuid4().hex[:6]
                
                start_text = (
                    f"🎮 <b>NINJA BATTLE!</b> 🎮\n\n"
                    f"<b>Enemy:</b> {enemy_data['name']} {enemy_data['emoji']}\n"
                    f"<b>HP:</b> {health_bar(enemy_data['max_hp'], enemy_data['max_hp'])}\n"
                    f"<b>Chakra:</b> {chakra_bar(enemy_data['chakra'], enemy_data['chakra'])}\n\n"
                    f"<b>Your HP:</b> {health_bar(100, 100)}\n"
                    f"<b>Your Chakra:</b> {chakra_bar(100, 100)}\n\n"
                    f"💰 <b>Entry Fee:</b> 50 Ryo\n"
                    f"🏆 <b>Reward:</b> {enemy_data['reward']} Ryo\n\n"
                    f"<i>Choose your first jutsu!</i>"
                )
                
                # Create start button
                keyboard = [[InlineKeyboardButton("⚔️ START BATTLE!", callback_data=f"jg_start_{game_id}_{enemy_key}")]]
                
                results.append(
                    InlineQueryResultArticle(
                        id=f"game_{enemy_key}_{game_id}",
                        title=f"🎮 Battle {enemy_data['name']}!",
                        description=f"Cost: 50 Ryo | Reward: {enemy_data['reward']} Ryo",
                        input_message_content=InputTextMessageContent(start_text, parse_mode="HTML"),
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        thumbnail_url=enemy_data['image']
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
    
    # Try to answer query, but don't fail if it's too old
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Could not answer callback query: {e}")
    
    parts = query.data.split('_')
    if len(parts) < 3:
        return
    
    action = parts[1]  # 'start', 'move', 'end'
    
    player = db.get_player(query.from_user.id)
    if not player:
        try:
            await query.answer("You need to register first!", show_alert=True)
        except:
            pass
        return
    
    # START NEW GAME
    if action == 'start':
        game_id = parts[2]
        enemy_key = parts[3]
        
        # Check if this game already started by someone else
        if game_id in ACTIVE_GAMES:
            if ACTIVE_GAMES[game_id]['player_id'] != query.from_user.id:
                try:
                    await query.answer("🚫 Someone else already started this battle! Start your own via inline mode.", show_alert=True)
                except:
                    pass
                return
        
        if player['ryo'] < 50:
            try:
                await query.answer("❌ Not enough Ryo! Need 50 Ryo to play.", show_alert=True)
            except:
                pass
            return
        
        enemy_data = GAME_ENEMIES.get(enemy_key)
        
        if not enemy_data:
            return
        
        # Initialize game state
        ACTIVE_GAMES[game_id] = {
            'player_id': query.from_user.id,
            'enemy_key': enemy_key,
            'player_hp': 100,
            'player_chakra': 100,
            'enemy_hp': enemy_data['max_hp'],
            'enemy_chakra': enemy_data['chakra'],
            'turn': 1,
            'log': []
        }
        
        # Deduct entry fee
        db.update_player(query.from_user.id, {'ryo': player['ryo'] - 50})
        
        # Show jutsu selection
        battle_text = (
            f"🎮 <b>BATTLE STARTED!</b> 🎮\n\n"
            f"<b>Turn 1</b>\n\n"
            f"👤 <b>You</b>\n"
            f"❤️ {health_bar(100, 100)}\n"
            f"💙 {chakra_bar(100, 100)}\n\n"
            f"👹 <b>{enemy_data['name']}</b> {enemy_data['emoji']}\n"
            f"❤️ {health_bar(enemy_data['max_hp'], enemy_data['max_hp'])}\n"
            f"💙 {chakra_bar(enemy_data['chakra'], enemy_data['chakra'])}\n\n"
            f"<i>Select your jutsu:</i>"
        )
        
        keyboard = [
            [
                InlineKeyboardButton(f"🔥 Fireball (15💙)", callback_data=f"jg_move_{game_id}_f"),
                InlineKeyboardButton(f"👊 Taijutsu (5💙)", callback_data=f"jg_move_{game_id}_t")
            ],
            [
                InlineKeyboardButton(f"🌊 Water (25💙)", callback_data=f"jg_move_{game_id}_wa"),
                InlineKeyboardButton(f"⚡ Lightning (30💙)", callback_data=f"jg_move_{game_id}_l")
            ],
            [
                InlineKeyboardButton(f"💫 Rasengan (35💙)", callback_data=f"jg_move_{game_id}_r"),
                InlineKeyboardButton(f"👁️ Genjutsu (20💙)", callback_data=f"jg_move_{game_id}_g")
            ],
            [
                InlineKeyboardButton(f"💚 Heal (25💙)", callback_data=f"jg_move_{game_id}_h"),
                InlineKeyboardButton(f"🏳️ Surrender", callback_data=f"jg_end_{game_id}_surrender")
            ]
        ]
        
        try:
            await query.edit_message_text(
                text=battle_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Error starting game: {e}")
    
    # PLAYER MAKES A MOVE
    elif action == 'move':
        game_id = parts[2]
        jutsu_key = parts[3]
        
        game_state = ACTIVE_GAMES.get(game_id)
        if not game_state:
            try:
                await query.answer("⚠️ Game expired! Start a new game.", show_alert=True)
            except:
                pass
            return
        
        if game_state['player_id'] != query.from_user.id:
            try:
                await query.answer("🚫 This is not your game! Start your own battle via inline mode.", show_alert=True)
            except:
                pass
            return
        
        enemy_data = GAME_ENEMIES[game_state['enemy_key']]
        player_jutsu = PLAYER_JUTSUS.get(jutsu_key)
        
        if not player_jutsu:
            try:
                await query.answer("⚠️ Invalid jutsu!", show_alert=True)
            except:
                pass
            return
        
        # Check chakra
        if game_state['player_chakra'] < player_jutsu['chakra']:
            try:
                await query.answer("❌ Not enough chakra!", show_alert=True)
            except:
                pass
            return
        
        # Player turn
        game_state['player_chakra'] -= player_jutsu['chakra']
        
        if player_jutsu.get('heal', 0) > 0:
            # Healing jutsu
            heal_amount = min(player_jutsu['heal'], 100 - game_state['player_hp'])
            game_state['player_hp'] = min(100, game_state['player_hp'] + heal_amount)
            game_state['log'].append(f"💚 You healed {heal_amount} HP!")
        else:
            # Attack jutsu
            # Calculate damage
            damage = player_jutsu['power']
            
            # Type effectiveness
            if player_jutsu['type'] == enemy_data['weakness']:
                damage = int(damage * 1.5)
                game_state['log'].append(f"💥 SUPER EFFECTIVE!")
            
            game_state['enemy_hp'] -= damage
            game_state['log'].append(f"⚔️ You used {player_jutsu['name']} - {damage} damage!")
        
        # Check if enemy defeated
        if game_state['enemy_hp'] <= 0:
            await end_game(query, game_id, game_state, enemy_data, won=True)
            return
        
        # Enemy turn
        if game_state['enemy_chakra'] >= 10:
            # Choose random attack
            available_attacks = [a for a, d in enemy_data['attacks'].items() if d['chakra'] <= game_state['enemy_chakra']]
            if available_attacks:
                enemy_attack_key = random.choice(available_attacks)
                enemy_attack = enemy_data['attacks'][enemy_attack_key]
                
                game_state['enemy_chakra'] -= enemy_attack['chakra']
                game_state['player_hp'] -= enemy_attack['power']
                game_state['log'].append(f"💢 {enemy_data['name']} used {enemy_attack['name']} - {enemy_attack['power']} damage!")
        
        # Check if player defeated
        if game_state['player_hp'] <= 0:
            await end_game(query, game_id, game_state, enemy_data, won=False)
            return
        
        # Continue battle
        game_state['turn'] += 1
        
        # Build battle log
        log_text = "\n".join(game_state['log'][-3:])  # Show last 3 actions
        
        battle_text = (
            f"🎮 <b>BATTLE - Turn {game_state['turn']}</b> 🎮\n\n"
            f"👤 <b>You</b>\n"
            f"❤️ {health_bar(game_state['player_hp'], 100)}\n"
            f"💙 {chakra_bar(game_state['player_chakra'], 100)}\n\n"
            f"👹 <b>{enemy_data['name']}</b> {enemy_data['emoji']}\n"
            f"❤️ {health_bar(game_state['enemy_hp'], enemy_data['max_hp'])}\n"
            f"💙 {chakra_bar(game_state['enemy_chakra'], enemy_data['chakra'])}\n\n"
            f"<b>Battle Log:</b>\n{log_text}\n\n"
            f"<i>Choose your next move:</i>"
        )
        
        keyboard = [
            [
                InlineKeyboardButton(f"🔥 Fireball (15💙)", callback_data=f"jg_move_{game_id}_f"),
                InlineKeyboardButton(f"👊 Taijutsu (5💙)", callback_data=f"jg_move_{game_id}_t")
            ],
            [
                InlineKeyboardButton(f"🌊 Water (25💙)", callback_data=f"jg_move_{game_id}_wa"),
                InlineKeyboardButton(f"⚡ Lightning (30💙)", callback_data=f"jg_move_{game_id}_l")
            ],
            [
                InlineKeyboardButton(f"💫 Rasengan (35💙)", callback_data=f"jg_move_{game_id}_r"),
                InlineKeyboardButton(f"👁️ Genjutsu (20💙)", callback_data=f"jg_move_{game_id}_g")
            ],
            [
                InlineKeyboardButton(f"💚 Heal (25💙)", callback_data=f"jg_move_{game_id}_h"),
                InlineKeyboardButton(f"🏳️ Surrender", callback_data=f"jg_end_{game_id}_surrender")
            ]
        ]
        
        try:
            await query.edit_message_text(
                text=battle_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Error updating battle: {e}")
    
    # END GAME
    elif action == 'end':
        game_id = parts[2]
        reason = parts[3] if len(parts) > 3 else 'surrender'
        
        game_state = ACTIVE_GAMES.get(game_id)
        if not game_state:
            return
        
        enemy_data = GAME_ENEMIES[game_state['enemy_key']]
        
        if reason == 'surrender':
            result_text = (
                f"🏳️ <b>SURRENDERED</b>\n\n"
                f"You gave up the fight!\n"
                f"💸 Lost: 50 Ryo"
            )
        
        keyboard = [[InlineKeyboardButton("🎮 Play Again?", switch_inline_query_current_chat="")]]
        
        try:
            await query.edit_message_text(
                text=result_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass
        
        # Clean up
        if game_id in ACTIVE_GAMES:
            del ACTIVE_GAMES[game_id]


async def end_game(query, game_id, game_state, enemy_data, won):
    """End the game and show results."""
    player = db.get_player(game_state['player_id'])
    
    if won:
        result_text = (
            f"🏆 <b>VICTORY!</b> 🏆\n\n"
            f"You defeated <b>{enemy_data['name']}</b>!\n\n"
            f"<b>Battle Summary:</b>\n"
            f"Turns: {game_state['turn']}\n"
            f"Your HP: {game_state['player_hp']}/100\n"
            f"Your Chakra: {game_state['player_chakra']}/100\n\n"
            f"💰 Reward: +{enemy_data['reward']} Ryo\n"
            f"✨ +50 EXP!"
        )
        
        updates = {
            'ryo': player['ryo'] + enemy_data['reward'],
            'exp': player['exp'] + 50,
            'total_exp': player['total_exp'] + 50
        }
        db.update_player(game_state['player_id'], updates)
    else:
        result_text = (
            f"💔 <b>DEFEATED!</b> 💔\n\n"
            f"You were defeated by <b>{enemy_data['name']}</b>!\n\n"
            f"<b>Battle Summary:</b>\n"
            f"Turns: {game_state['turn']}\n"
            f"Enemy HP: {game_state['enemy_hp']}/{enemy_data['max_hp']}\n\n"
            f"💸 Lost: 50 Ryo\n"
            f"<i>Train harder and try again!</i>"
        )
    
    keyboard = [[InlineKeyboardButton("🎮 Play Again?", switch_inline_query_current_chat="")]]
    
    try:
        await query.edit_message_text(
            text=result_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error ending game: {e}")
    
    # Clean up
    if game_id in ACTIVE_GAMES:
        del ACTIVE_GAMES[game_id]
