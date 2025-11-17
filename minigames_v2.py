"""
🎮 MINIGAMES_V2.PY - Advanced Criminal Systems
Handles: Heat Management, Reputation, Bounty Board, Contracts, Loot System

Features:
- Heat decay system
- Reputation titles with bonuses
- Contract board
- Loot drop mechanics
- Bounty calculations
"""

import logging
import random
import datetime
from datetime import timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from html import escape

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- HEAT SYSTEM ---
HEAT_DECAY_RATE = 5  # Decay 5 points per hour
MAX_HEAT = 100

# --- BOUNTY SYSTEM ---
BOUNTY_MULTIPLIER = 0.15  # 15% of victim's Ryo
KILL_BOUNTY_BONUS = 50  # +50 per kill
MIN_BOUNTY = 100
MAX_BOUNTY = 2000

# --- REPUTATION TITLES ---
REPUTATION_TITLES = {
    'notorious_criminal': {
        'name': '🔴 Notorious Criminal',
        'kills_req': 100,
        'bonus': {'rob_success': 0.30}
    },
    'master_thief': {
        'name': '💰 Master Thief',
        'steals_req': 500,
        'bonus': {'rob_amount': 1.50, 'rob_success': 0.20}
    },
    'guardian_angel': {
        'name': '💚 Guardian Angel',
        'heals_req': 50,
        'bonus': {'protection_time': 1.20}
    },
    'shadow_assassin': {
        'name': '☠️ Shadow Assassin',
        'kills_req': 50,
        'bonus': {'kill_success': 0.25}
    },
    'scout_master': {
        'name': '🔍 Scout Master',
        'scouts_req': 200,
        'bonus': {'scout_rewards': 2.0}
    }
}

# --- LEGENDARY LOOT ---
LEGENDARY_ITEMS = {
    'gold_kunai': {
        'name': '🔱 Gold Kunai',
        'effect': 'guaranteed_kill',
        'desc': '1-time guaranteed kill'
    },
    'legendary_scroll': {
        'name': '📜 Legendary Scroll',
        'effect': 'exp_boost',
        'value': 200,
        'desc': '+200 EXP'
    },
    'chakra_crystal': {
        'name': '💎 Chakra Crystal',
        'effect': 'chakra_restore',
        'value': 100,
        'desc': 'Restore 100 Chakra'
    },
    'stealth_cloak': {
        'name': '🥷 Stealth Cloak',
        'effect': 'rob_boost',
        'value': 0.50,
        'desc': '+50% rob success (1 hour)'
    }
}

LOOT_DROP_CHANCES = {
    'common': 0.60,
    'rare': 0.30,
    'legendary': 0.10
}

# --- HEAT FUNCTIONS ---
def update_heat(player, heat_change):
    """Updates player's heat level with automatic decay."""
    now = datetime.datetime.now(timezone.utc)
    last_decay = player.get('last_heat_decay')
    
    if last_decay:
        if isinstance(last_decay, str):
            last_decay = datetime.datetime.fromisoformat(last_decay)
        if last_decay.tzinfo is None:
            last_decay = last_decay.replace(tzinfo=timezone.utc)
        
        # Calculate decay
        hours_passed = (now - last_decay).total_seconds() / 3600
        decay_amount = int(hours_passed * HEAT_DECAY_RATE)
        current_heat = max(0, player.get('heat_level', 0) - decay_amount)
    else:
        current_heat = player.get('heat_level', 0)
    
    # Apply change
    new_heat = max(0, min(MAX_HEAT, current_heat + heat_change))
    
    return {
        'heat_level': new_heat,
        'last_heat_decay': now.isoformat()
    }

def get_heat_multiplier(heat_level):
    """Returns reward multiplier based on heat level."""
    if heat_level >= 80:
        return 2.0
    elif heat_level >= 50:
        return 1.5
    elif heat_level >= 25:
        return 1.2
    return 1.0

def get_heat_status(heat_level):
    """Returns heat status emoji and text."""
    if heat_level >= 80:
        return "🔴🔴🔴", "EXTREMELY WANTED"
    elif heat_level >= 50:
        return "🟠🟠", "WANTED"
    elif heat_level >= 25:
        return "🟡", "SUSPICIOUS"
    return "🟢", "CLEAR"

# --- REPUTATION FUNCTIONS ---
def check_reputation_title(player):
    """Checks if player earned a new title."""
    kills = player.get('kills', 0)
    steals = player.get('total_steals', 0)
    heals = player.get('total_heals_given', 0)
    scouts = player.get('total_scouts', 0)
    
    new_title = None
    
    if kills >= 100:
        new_title = 'notorious_criminal'
    elif steals >= 500:
        new_title = 'master_thief'
    elif heals >= 50:
        new_title = 'guardian_angel'
    elif kills >= 50:
        new_title = 'shadow_assassin'
    elif scouts >= 200:
        new_title = 'scout_master'
    
    if new_title and player.get('reputation_title') != new_title:
        return new_title, REPUTATION_TITLES[new_title]
    
    return None, None

def get_reputation_bonuses(player):
    """Returns active bonuses from reputation title."""
    title_key = player.get('reputation_title')
    if not title_key or title_key not in REPUTATION_TITLES:
        return {}
    
    return REPUTATION_TITLES[title_key].get('bonus', {})

# --- BOUNTY FUNCTIONS ---
def calculate_bounty(victim):
    """Calculates bounty based on victim's wealth and kills."""
    base_bounty = int(victim['ryo'] * BOUNTY_MULTIPLIER)
    kill_bonus = victim.get('kills', 0) * KILL_BOUNTY_BONUS
    total = base_bounty + kill_bonus
    return max(MIN_BOUNTY, min(MAX_BOUNTY, total))

# --- LOOT FUNCTIONS ---
def roll_for_loot(player):
    """Rolls for loot drops."""
    roll = random.random()
    
    if roll < LOOT_DROP_CHANCES['legendary']:
        # Legendary!
        item_key = random.choice(list(LEGENDARY_ITEMS.keys()))
        return 'legendary', item_key, LEGENDARY_ITEMS[item_key]
    elif roll < (LOOT_DROP_CHANCES['legendary'] + LOOT_DROP_CHANCES['rare']):
        # Rare
        return 'rare', None, {'type': 'ryo', 'amount': random.randint(200, 500)}
    else:
        # Common
        return 'common', None, {'type': 'ryo', 'amount': random.randint(50, 100)}

# --- COMMAND FUNCTIONS ---
async def safe_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text, parse_mode=None, reply_markup=None):
    try:
        await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except BadRequest:
        try:
            await context.bot.send_message(update.effective_chat.id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

async def bounty_board_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows top 10 players with bounties."""
    conn = db.get_db_connection()
    if not conn:
        await safe_reply(update, context, "Database error!")
        return
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT user_id, username, bounty, heat_level, kills
                FROM players
                WHERE bounty > 0
                ORDER BY bounty DESC
                LIMIT 10
            """)
            results = cursor.fetchall()
        
        if not results:
            await safe_reply(update, context, "📜 <b>BOUNTY BOARD</b> 📜\n\nNo active bounties!", parse_mode="HTML")
            return
        
        text = "📜 <b>BOUNTY BOARD - MOST WANTED</b> 📜\n\n"
        
        for i, row in enumerate(results, 1):
            user_id, username, bounty, heat, kills = row
            heat_emoji, _ = get_heat_status(heat or 0)
            
            rank_emoji = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
            
            text += (
                f"{rank_emoji} <b>{escape(username)}</b>\n"
                f"├ Bounty: {bounty:,} Ryo 💰\n"
                f"├ Heat: {heat_emoji} {heat or 0}/100\n"
                f"└ Kills: {kills or 0} ☠️\n\n"
            )
        
        await safe_reply(update, context, text, parse_mode="HTML")
    
    except Exception as e:
        logger.error(f"Bounty board error: {e}")
        await safe_reply(update, context, "Error loading bounty board!")
    finally:
        db.put_db_connection(conn)

async def contracts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows active contracts."""
    conn = db.get_db_connection()
    if not conn:
        await safe_reply(update, context, "Database error!")
        return
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT c.id, c.target_user_id, p.username, c.reward, c.placed_by_username
                FROM player_contracts c
                JOIN players p ON c.target_user_id = p.user_id
                WHERE c.is_active = 1 AND c.expires_at > NOW()
                ORDER BY c.reward DESC
                LIMIT 10
            """)
            results = cursor.fetchall()
        
        if not results:
            await safe_reply(update, context, "💼 <b>CONTRACT BOARD</b> 💼\n\nNo active contracts!", parse_mode="HTML")
            return
        
        text = "💼 <b>ACTIVE CONTRACTS</b> 💼\n\n"
        
        for i, row in enumerate(results, 1):
            contract_id, target_id, target_name, reward, placer = row
            
            text += (
                f"{i}. <b>{escape(target_name)}</b>\n"
                f"├ Reward: {reward:,} Ryo 💰\n"
                f"└ Placed by: {escape(placer)}\n\n"
            )
        
        text += "\n<i>Kill the target to claim the contract!</i>"
        
        await safe_reply(update, context, text, parse_mode="HTML")
    
    except Exception as e:
        logger.error(f"Contracts error: {e}")
        await safe_reply(update, context, "Error loading contracts!")
    finally:
        db.put_db_connection(conn)

async def place_contract_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Place a contract on someone."""
    user = update.effective_user
    
    if not update.message.reply_to_message:
        await safe_reply(update, context, "Reply to the target and specify reward. Usage: `/contract <amount>`")
        return
    
    target_user = update.message.reply_to_message.from_user
    
    if target_user.id == user.id or target_user.is_bot:
        await safe_reply(update, context, "Invalid target!")
        return
    
    try:
        reward = int(context.args[0])
    except:
        await safe_reply(update, context, "Specify reward amount! Usage: `/contract <amount>`")
        return
    
    if reward < 500:
        await safe_reply(update, context, "Minimum contract is 500 Ryo!")
        return
    
    player = db.get_player(user.id)
    target = db.get_player(target_user.id)
    
    if not player:
        await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML")
        return
    
    if not target:
        await safe_reply(update, context, "Target is not registered!")
        return
    
    if player['ryo'] < reward:
        await safe_reply(update, context, "Not enough Ryo!")
        return
    
    # Place contract
    conn = db.get_db_connection()
    if not conn:
        return
    
    try:
        expires_at = datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=48)
        
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO player_contracts 
                (target_user_id, placed_by_user_id, placed_by_username, reward, expires_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (target_user.id, user.id, user.first_name, reward, expires_at))
        
        conn.commit()
        
        # Deduct Ryo
        db.atomic_add_ryo(user.id, -reward)
        
        # Add bounty to target
        db.update_player(target_user.id, {
            'bounty': target.get('bounty', 0) + reward
        })
        
        msg = (
            f"💼 <b>CONTRACT PLACED!</b> 💼\n\n"
            f"Target: <b>{escape(target_user.first_name)}</b>\n"
            f"Reward: {reward:,} Ryo 💰\n"
            f"Expires: 48 hours\n\n"
            f"<i>Anyone can claim by killing the target!</i>"
        )
        
        await safe_reply(update, context, msg, parse_mode="HTML")
    
    except Exception as e:
        logger.error(f"Place contract error: {e}")
        conn.rollback()
        await safe_reply(update, context, "Failed to place contract!")
    finally:
        db.put_db_connection(conn)

async def inventory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows legendary items inventory."""
    user = update.effective_user
    player = db.get_player(user.id)
    
    if not player:
        await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML")
        return
    
    legendary_items = player.get('legendary_items', [])
    
    if not legendary_items:
        await safe_reply(update, context, "🎒 <b>LEGENDARY INVENTORY</b> 🎒\n\nYou don't have any legendary items yet!\n\n<i>Get them from kills and robberies!</i>", parse_mode="HTML")
        return
    
    text = "🎒 <b>LEGENDARY INVENTORY</b> 🎒\n\n"
    
    for item_key in legendary_items:
        item = LEGENDARY_ITEMS.get(item_key)
        if item:
            text += f"{item['name']}\n└ {item['desc']}\n\n"
    
    keyboard = [[InlineKeyboardButton("🎁 Use Item", callback_data="use_legendary_item")]]
    
    await safe_reply(update, context, text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def use_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle using legendary items."""
    query = update.callback_query
    await query.answer()
    
    player = db.get_player(query.from_user.id)
    if not player:
        return
    
    items = player.get('legendary_items', [])
    
    if not items:
        await query.edit_message_text("You don't have any items!")
        return
    
    # Show item selection
    keyboard = []
    for item_key in items:
        item = LEGENDARY_ITEMS.get(item_key)
        if item:
            keyboard.append([InlineKeyboardButton(item['name'], callback_data=f"use_item_{item_key}")])
    
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_item_use")])
    
    await query.edit_message_text(
        "Select an item to use:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def reputation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows reputation status and progress to titles."""
    user = update.effective_user
    player = db.get_player(user.id)
    
    if not player:
        await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML")
        return
    
    current_title = player.get('reputation_title')
    rep_points = player.get('reputation_points', 0)
    
    text = "⭐ <b>REPUTATION STATUS</b> ⭐\n\n"
    text += f"<b>Points:</b> {rep_points}\n"
    text += f"<b>Current Title:</b> {REPUTATION_TITLES[current_title]['name'] if current_title in REPUTATION_TITLES else 'None'}\n\n"
    
    text += "<b>📊 PROGRESS TO TITLES:</b>\n\n"
    
    # Show progress
    text += f"🔴 <b>Notorious Criminal</b>\n"
    text += f"├ Kills: {player.get('kills', 0)}/100\n"
    text += f"└ Bonus: +30% rob success\n\n"
    
    text += f"💰 <b>Master Thief</b>\n"
    text += f"├ Successful Robs: {player.get('total_steals', 0)}/500\n"
    text += f"└ Bonus: +50% rob amount, +20% success\n\n"
    
    text += f"💚 <b>Guardian Angel</b>\n"
    text += f"├ Players Healed: {player.get('total_heals_given', 0)}/50\n"
    text += f"└ Bonus: +20% protection time\n\n"
    
    text += f"☠️ <b>Shadow Assassin</b>\n"
    text += f"├ Kills: {player.get('kills', 0)}/50\n"
    text += f"└ Bonus: +25% kill success\n\n"
    
    text += f"🔍 <b>Scout Master</b>\n"
    text += f"├ Scouts Done: {player.get('total_scouts', 0)}/200\n"
    text += f"└ Bonus: 2x scout rewards\n"
    
    await safe_reply(update, context, text, parse_mode="HTML")

async def heat_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows heat level and cooldown info."""
    user = update.effective_user
    player = db.get_player(user.id)
    
    if not player:
        await safe_reply(update, context, f"{user.mention_html()}, please /register first!", parse_mode="HTML")
        return
    
    heat_level = player.get('heat_level', 0)
    heat_emoji, heat_text = get_heat_status(heat_level)
    heat_mult = get_heat_multiplier(heat_level)
    
    # Calculate time to cool down
    last_decay = player.get('last_heat_decay')
    now = datetime.datetime.now(timezone.utc)
    
    if last_decay:
        if isinstance(last_decay, str):
            last_decay = datetime.datetime.fromisoformat(last_decay)
        if last_decay.tzinfo is None:
            last_decay = last_decay.replace(tzinfo=timezone.utc)
        
        hours_since = (now - last_decay).total_seconds() / 3600
        pending_decay = int(hours_since * HEAT_DECAY_RATE)
    else:
        pending_decay = 0
    
    hours_to_clear = heat_level / HEAT_DECAY_RATE if heat_level > 0 else 0
    
    text = (
        f"🚨 <b>HEAT STATUS</b> 🚨\n\n"
        f"<b>Heat Level:</b> {heat_emoji} {heat_level}/100\n"
        f"<b>Status:</b> {heat_text}\n"
        f"<b>Reward Multiplier:</b> x{heat_mult}\n\n"
        f"<b>Decay Rate:</b> -{HEAT_DECAY_RATE}/hour\n"
        f"<b>Pending Decay:</b> -{pending_decay}\n"
        f"<b>Time to Clear:</b> {hours_to_clear:.1f} hours\n\n"
        f"<i>💡 High heat = higher rewards but lower success rates!</i>\n"
        f"<i>💡 Lay low to reduce heat naturally.</i>"
    )
    
    await safe_reply(update, context, text, parse_mode="HTML")
