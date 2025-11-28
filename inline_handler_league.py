"""
Enhanced Inline Handler with Battle League System (Part 1)
Handles inline queries - showing battles, profile, missions
"""
import logging
import uuid
import datetime
from datetime import timezone
from html import escape
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database as db
import game_logic as gl
import league_system as ls
import battle_enemies as be

logger = logging.getLogger(__name__)

# 🎮 GAME STATE STORAGE (in-memory for active games)
ACTIVE_GAMES = {}

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
    current = max(0, current)
    filled = int((current / max_hp) * length)
    bar = '█' * filled + '░' * (length - filled)
    return f"{bar} {current}/{max_hp}"


def chakra_bar(current, max_chakra, length=10):
    """Generate chakra bar visual."""
    current = max(0, current)
    filled = int((current / max_chakra) * length)
    bar = '▰' * filled + '▱' * (length - filled)
    return f"{bar} {current}/{max_chakra}"


def get_wallet_text(player):
    """Get wallet display with league info."""
    is_hosp, _ = gl.get_hospital_status(player)
    status_text = "🏥 Hospitalized" if is_hosp else "❤️ Alive"
    
    # League info
    league_display = ls.get_league_display(player)
    
    streak = player.get('win_streak', 0)
    streak_display = '🔥' * min(streak, 10) if streak > 0 else '❌'
    
    # Fix for the problematic line - avoid nested f-strings
    next_tier_text = f" / {league_display['next_tier_points']}" if league_display['next_tier_points'] else " (MAX)"
    
    return (
        f"<b>--- 🥷 {escape(player['username'])}'s Profile 🥷 ---</b>\n\n"
        f"<b>League:</b> {league_display['emoji']} {league_display['tier_name']} {league_display['stars']}\n"
        f"<b>Points:</b> {league_display['points']}{next_tier_text}\n"
        f"<b>Win Streak:</b> {streak_display} {streak}\n\n"
        f"<b>Level:</b> {player['level']} | <b>Rank:</b> {player['rank']}\n"
        f"<b>Ryo:</b> {player['ryo']:,} 💰\n"
        f"<b>Total Battles:</b> {player.get('total_battles', 0)}\n"
        f"<b>Kills:</b> {player.get('kills', 0)} ☠️\n"
        f"<b>Status:</b> {status_text}"
    )


def get_top_league_text():
    """Get top players by league points."""
    text = "🏆 <b>Top 5 League Champions</b> 🏆\n\n"
    top_players = db.get_top_players_by_league(limit=5)
    
    if not top_players:
        text += "No league battles yet...\n"
        text += "Be the first to climb the ranks!"
    else:
        for i, p in enumerate(top_players):
            rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
            league_display = ls.get_league_display(p)
            mention = f'<a href="tg://user?id={p["user_id"]}">{escape(p["username"])}</a>'
            text += f"{rank_emoji} {mention}\n"
            text += f"   {league_display['emoji']} {league_display['tier_name']} - {league_display['points']} pts | Streak: {p.get('win_streak', 0)}\n\n"
    
    return text


def get_daily_missions_text(player):
    """Get daily missions display."""
    missions_data = ls.get_daily_missions(player)
    
    text = "📋 <b>Daily Missions</b> 📋\n\n"
    
    completed_count = len(missions_data['completed'])
    text += f"<b>Progress:</b> {completed_count}/3 Complete\n\n"
    
    for mission in missions_data['missions']:
        progress = missions_data['progress'].get(mission['id'], 0)
        is_complete = mission['id'] in missions_data['completed']
        
        if is_complete:
            status = "✅"
            text += f"{status} <s>{mission['description']}</s>\n"
            text += f"   <i>Claimed: {mission['reward_ryo']} Ryo + {mission['reward_exp']} EXP</i>\n\n"
        else:
            status = f"⬜ ({progress}/{mission['target']})"
            text += f"{status} <b>{mission['description']}</b>\n"
            text += f"   Reward: {mission['reward_ryo']} Ryo + {mission['reward_exp']} EXP\n\n"
    
    if completed_count == 3:
        text += "🎊 <b>ALL MISSIONS COMPLETE!</b> 🎊\n"
        text += "Great work, ninja! Come back tomorrow for new missions.\n"
    
    # Time until reset
    reset_time = missions_data.get('reset_time')
    if reset_time:
        now = datetime.datetime.now(timezone.utc)
        if isinstance(reset_time, str):
            reset_time = datetime.datetime.fromisoformat(reset_time)
        if reset_time.tzinfo is None:
            reset_time = reset_time.replace(tzinfo=timezone.utc)
        
        time_until_reset = reset_time + datetime.timedelta(hours=24) - now
        hours_left = int(time_until_reset.total_seconds() / 3600)
        text += f"\n⏰ Resets in: {hours_left}h"
    
    return text


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced inline query handler with league system."""
    query = update.inline_query
    if not query:
        return

    user_id = query.from_user.id
    player = db.get_player(user_id)
    results = []

    if player:
        is_hosp, _ = gl.get_hospital_status(player)
        league_display = ls.get_league_display(player)
        tier_key = league_display['tier_key']
        tier_data = ls.LEAGUE_TIERS[tier_key]
        
        # --- 1. Show Profile/Wallet ---
        wallet_text = get_wallet_text(player)
        results.append(
            InlineQueryResultArticle(
                id="wallet",
                title=f"{league_display['emoji']} My Ninja Profile",
                description=f"{league_display['tier_name']} League | {league_display['points']} pts | Streak: {player.get('win_streak', 0)}",
                input_message_content=InputTextMessageContent(wallet_text, parse_mode="HTML")
            )
        )
        
        # --- 2. League Leaderboard ---
        results.append(
            InlineQueryResultArticle(
                id="league_top",
                title="🏆 League Champions",
                description="View top 5 league leaders",
                input_message_content=InputTextMessageContent(get_top_league_text(), parse_mode="HTML")
            )
        )
        
        # --- 3. Daily Missions ---
        missions_data = ls.get_daily_missions(player)
        completed = len(missions_data['completed'])
        results.append(
            InlineQueryResultArticle(
                id="missions",
                title=f"📋 Daily Missions ({completed}/3)",
                description="View your daily challenges",
                input_message_content=InputTextMessageContent(get_daily_missions_text(player), parse_mode="HTML")
            )
        )
        
        # --- 4. LEAGUE BATTLES ---
        if not is_hosp:
            battle_check = ls.can_battle_today(player)
            
            if battle_check['can_battle'] and player['ryo'] >= tier_data['entry_fee']:
                # Get enemies for player's league
                available_enemies = be.get_enemies_for_league(tier_key)
                
                for enemy_key, enemy_data in available_enemies.items():
                    game_id = uuid.uuid4().hex[:6]
                    
                    entry_fee = tier_data['entry_fee']
                    potential_reward = f"{tier_data['reward_min']}-{tier_data['reward_max']}"
                    
                    # Show streak bonus if active
                    streak = player.get('win_streak', 0)
                    streak_status = ls.get_streak_status(streak)
                    streak_text = ""
                    if streak_status and streak > 0:
                        multiplier_percent = int((streak_status['multiplier'] - 1) * 100)
                        if multiplier_percent > 0:
                            streak_text = f"\n🔥 <b>Streak Bonus:</b> {streak_status['name']} (+{multiplier_percent}% Ryo!)"
                    
                    start_text = (
                        f"🎮 <b>{league_display['emoji']} {league_display['tier_name'].upper()} LEAGUE BATTLE!</b> 🎮\n\n"
                        f"<b>Enemy:</b> {enemy_data['name']} {enemy_data['emoji']}\n"
                        f"<b>Difficulty:</b> {enemy_data['difficulty'].title()}\n"
                        f"<b>HP:</b> {health_bar(enemy_data['max_hp'], enemy_data['max_hp'])}\n"
                        f"<b>Chakra:</b> {chakra_bar(enemy_data['chakra'], enemy_data['chakra'])}\n\n"
                        f"<b>Your HP:</b> {health_bar(100, 100)}\n"
                        f"<b>Your Chakra:</b> {chakra_bar(100, 100)}\n\n"
                        f"💰 <b>Entry Fee:</b> {entry_fee} Ryo\n"
                        f"🏆 <b>Reward:</b> {potential_reward} Ryo\n"
                        f"⭐ <b>Points:</b> +{tier_data['point_gain']} (win) / -{tier_data['point_loss']} (lose)\n"
                        f"📊 <b>Battles Today:</b> {player.get('battles_today', 0)}/{tier_data['daily_battle_limit']}"
                        f"{streak_text}\n\n"
                        f"<i>Ready to fight?</i>"
                    )
                    
                    keyboard = [[InlineKeyboardButton("⚔️ START BATTLE!", callback_data=f"lb_start_{game_id}_{enemy_key}")]]
                    
                    results.append(
                        InlineQueryResultArticle(
                            id=f"battle_{tier_key}_{enemy_key}_{game_id}",
                            title=f"⚔️ Battle: {enemy_data['name']} ({enemy_data['difficulty'].title()})",
                            description=f"Fee: {entry_fee} Ryo | Reward: {potential_reward} Ryo | +{tier_data['point_gain']} pts",
                            input_message_content=InputTextMessageContent(start_text, parse_mode="HTML"),
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            thumbnail_url=enemy_data.get('image', '')
                        )
                    )
            
            elif not battle_check['can_battle']:
                # Daily limit reached
                results.append(
                    InlineQueryResultArticle(
                        id="limit_reached",
                        title="⚠️ Daily Battle Limit Reached",
                        description=f"Come back tomorrow! ({tier_data['daily_battle_limit']} battles/day)",
                        input_message_content=InputTextMessageContent(
                            f"⚠️ <b>Daily Battle Limit Reached!</b>\n\n"
                            f"You've completed <b>{tier_data['daily_battle_limit']}</b> battles today.\n"
                            f"Come back tomorrow for more league battles!\n\n"
                            f"<i>Tip: Complete daily missions for extra Ryo!</i>",
                            parse_mode="HTML"
                        )
                    )
                )
            
            elif player['ryo'] < tier_data['entry_fee']:
                # Not enough Ryo
                results.append(
                    InlineQueryResultArticle(
                        id="low_ryo",
                        title="❌ Not Enough Ryo",
                        description=f"Need {tier_data['entry_fee']} Ryo to battle in {league_display['tier_name']}",
                        input_message_content=InputTextMessageContent(
                            f"❌ <b>Insufficient Ryo</b>\n\n"
                            f"You need <b>{tier_data['entry_fee']} Ryo</b> to battle in the {league_display['emoji']} {league_display['tier_name']} League.\n\n"
                            f"<b>Your Balance:</b> {player['ryo']:,} Ryo\n"
                            f"<b>Need:</b> {tier_data['entry_fee'] - player['ryo']:,} more Ryo\n\n"
                            f"💡 <b>How to earn Ryo:</b>\n"
                            f"• Complete daily missions\n"
                            f"• Fight in main game (/fight)\n"
                            f"• Rob other players (/rob)",
                            parse_mode="HTML"
                        )
                    )
                )
        else:
            # Hospitalized
            results.append(
                InlineQueryResultArticle(
                    id="hospitalized",
                    title="🏥 You're Hospitalized!",
                    description="Can't battle while recovering",
                    input_message_content=InputTextMessageContent(
                        f"🏥 <b>You're Hospitalized!</b>\n\n"
                        f"You can't participate in league battles while recovering.\n"
                        f"Wait for your recovery time to expire, or use /hospital to check status.",
                        parse_mode="HTML"
                    )
                )
            )
    
    else:
        # Not registered
        results.append(
            InlineQueryResultArticle(
                id="register",
                title="❌ Not Registered!",
                description="Join the ninja world!",
                input_message_content=InputTextMessageContent(
                    f"⚠️ <b>You're Not Registered!</b>\n\n"
                    f"Start your ninja journey with @{context.bot.username}\n\n"
                    f"Use /start to register and join the Battle League!",
                    parse_mode="HTML"
                )
            )
        )

    try:
        await query.answer(results, cache_time=0)
    except Exception as e:
        logger.error(f"Inline query error: {e}")
