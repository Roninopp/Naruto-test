"""
League System - Battle League Rankings & Rewards
Handles all league tier calculations, rewards, and progression
"""
import logging

logger = logging.getLogger(__name__)

# 🏆 LEAGUE TIER DEFINITIONS
LEAGUE_TIERS = {
    'genin': {
        'name': 'Genin',
        'emoji': '🥉',
        'min_points': 0,
        'max_points': 499,
        'entry_fee': 50,
        'reward_min': 150,
        'reward_max': 300,
        'point_gain': 30,
        'point_loss': 20,
        'weekly_reward': {
            'ryo': 500,
            'exp': 50,
            'items': 0
        },
        'daily_battle_limit': 15,
        'win_rate_target': 0.75
    },
    'chunin': {
        'name': 'Chunin',
        'emoji': '🥈',
        'min_points': 500,
        'max_points': 1499,
        'entry_fee': 150,
        'reward_min': 500,
        'reward_max': 800,
        'point_gain': 40,
        'point_loss': 30,
        'weekly_reward': {
            'ryo': 1500,
            'exp': 150,
            'items': 1
        },
        'daily_battle_limit': 15,
        'win_rate_target': 0.65
    },
    'jonin': {
        'name': 'Jonin',
        'emoji': '🥇',
        'min_points': 1500,
        'max_points': 2999,
        'entry_fee': 300,
        'reward_min': 1200,
        'reward_max': 2000,
        'point_gain': 50,
        'point_loss': 40,
        'weekly_reward': {
            'ryo': 3500,
            'exp': 300,
            'items': 2
        },
        'daily_battle_limit': 15,
        'win_rate_target': 0.55
    },
    'anbu': {
        'name': 'ANBU',
        'emoji': '💎',
        'min_points': 3000,
        'max_points': 4999,
        'entry_fee': 500,
        'reward_min': 2500,
        'reward_max': 4000,
        'point_gain': 60,
        'point_loss': 50,
        'weekly_reward': {
            'ryo': 7000,
            'exp': 500,
            'items': 3
        },
        'daily_battle_limit': 15,
        'win_rate_target': 0.45
    },
    'kage': {
        'name': 'Kage',
        'emoji': '👑',
        'min_points': 5000,
        'max_points': 999999,
        'entry_fee': 800,
        'reward_min': 5000,
        'reward_max': 8000,
        'point_gain': 75,
        'point_loss': 75,
        'weekly_reward': {
            'ryo': 15000,
            'exp': 1000,
            'items': 5
        },
        'daily_battle_limit': 15,
        'win_rate_target': 0.35
    }
}

# 🔥 WIN STREAK BONUSES
STREAK_BONUSES = {
    3: {'ryo_multiplier': 1.2, 'name': '3-Win Streak!', 'emoji': '🔥'},
    5: {'ryo_multiplier': 1.5, 'name': '5-Win Streak!', 'emoji': '🔥🔥', 'item_chance': 0.3},
    7: {'ryo_multiplier': 2.0, 'name': '7-Win Streak!', 'emoji': '🔥🔥🔥', 'guaranteed_item': True},
    10: {'ryo_multiplier': 3.0, 'name': 'LEGENDARY 10-STREAK!', 'emoji': '⚡🔥⚡', 'legendary_chance': 0.15}
}

# 📋 DAILY MISSIONS POOL
DAILY_MISSIONS = [
    {
        'id': 'win_3',
        'description': 'Win 3 battles',
        'target': 3,
        'reward_ryo': 300,
        'reward_exp': 50
    },
    {
        'id': 'win_no_heal',
        'description': 'Win without using heal jutsu',
        'target': 1,
        'reward_ryo': 200,
        'reward_exp': 30
    },
    {
        'id': 'win_streak_3',
        'description': 'Achieve a 3-win streak',
        'target': 3,
        'reward_ryo': 400,
        'reward_exp': 60
    },
    {
        'id': 'use_ultimate',
        'description': 'Win using Rasengan or Lightning Blade',
        'target': 1,
        'reward_ryo': 250,
        'reward_exp': 40
    },
    {
        'id': 'perfect_win',
        'description': 'Win with 80+ HP remaining',
        'target': 1,
        'reward_ryo': 350,
        'reward_exp': 50
    }
]


def get_league_tier(points):
    """Get league tier based on points."""
    for tier_key, tier_data in LEAGUE_TIERS.items():
        if tier_data['min_points'] <= points <= tier_data['max_points']:
            return tier_key, tier_data
    return 'genin', LEAGUE_TIERS['genin']


def get_league_display(player):
    """Get formatted league display for player."""
    points = player.get('league_points', 0)
    tier_key, tier_data = get_league_tier(points)
    
    # Calculate stars (1-5 based on progress in tier)
    tier_range = tier_data['max_points'] - tier_data['min_points']
    progress = points - tier_data['min_points']
    stars = min(5, max(1, int((progress / tier_range) * 5) + 1)) if tier_range > 0 else 1
    
    star_display = '⭐' * stars
    
    return {
        'tier_key': tier_key,
        'tier_name': tier_data['name'],
        'emoji': tier_data['emoji'],
        'points': points,
        'stars': star_display,
        'next_tier_points': tier_data['max_points'] + 1 if tier_key != 'kage' else None
    }


def calculate_battle_rewards(player, won, enemy_reward_base):
    """Calculate battle rewards including streak bonuses."""
    tier_key, tier_data = get_league_tier(player.get('league_points', 0))
    streak = player.get('win_streak', 0)
    
    if won:
        # Base reward from league tier
        base_ryo = enemy_reward_base
        
        # Apply streak multiplier
        multiplier = 1.0
        streak_bonus = None
        bonus_items = []
        
        if streak >= 3:
            for streak_level in sorted(STREAK_BONUSES.keys(), reverse=True):
                if streak >= streak_level:
                    bonus_data = STREAK_BONUSES[streak_level]
                    multiplier = bonus_data['ryo_multiplier']
                    streak_bonus = bonus_data
                    break
        
        final_ryo = int(base_ryo * multiplier)
        base_exp = 50 + (tier_data['point_gain'] * 2)
        
        # Bonus items from streaks
        if streak_bonus:
            if streak_bonus.get('guaranteed_item'):
                bonus_items.append('health_potion')
            if streak_bonus.get('legendary_chance', 0) > 0:
                import random
                if random.random() < streak_bonus['legendary_chance']:
                    bonus_items.append('legendary_scroll')
        
        return {
            'won': True,
            'ryo': final_ryo,
            'base_ryo': base_ryo,
            'exp': base_exp,
            'points': tier_data['point_gain'],
            'streak_multiplier': multiplier,
            'streak_bonus': streak_bonus,
            'bonus_items': bonus_items
        }
    else:
        # Loss penalties
        return {
            'won': False,
            'ryo': -tier_data['entry_fee'],
            'exp': 0,
            'points': -tier_data['point_loss'],
            'streak_multiplier': 0,
            'streak_bonus': None,
            'bonus_items': []
        }


def get_daily_missions(player):
    """Get player's daily missions."""
    import random
    from datetime import datetime, timezone
    
    # Check if missions need reset
    last_reset = player.get('daily_missions_reset')
    now = datetime.now(timezone.utc)
    
    # Reset if last reset was more than 24 hours ago or doesn't exist
    needs_reset = True
    if last_reset:
        if isinstance(last_reset, str):
            try:
                last_reset = datetime.fromisoformat(last_reset)
            except:
                last_reset = None
        
        if last_reset and last_reset.tzinfo is None:
            last_reset = last_reset.replace(tzinfo=timezone.utc)
        
        if last_reset:
            hours_diff = (now - last_reset).total_seconds() / 3600
            needs_reset = hours_diff >= 24
    
    if needs_reset:
        # Generate 3 random missions
        missions = random.sample(DAILY_MISSIONS, 3)
        return {
            'missions': missions,
            'progress': {m['id']: 0 for m in missions},
            'completed': [],
            'reset_time': now
        }
    else:
        # Return existing missions
        return player.get('daily_missions_data', {
            'missions': [],
            'progress': {},
            'completed': [],
            'reset_time': last_reset
        })


def update_mission_progress(player, mission_type, amount=1):
    """Update progress on daily missions."""
    missions_data = get_daily_missions(player)
    
    for mission in missions_data['missions']:
        if mission['id'] == mission_type and mission['id'] not in missions_data['completed']:
            missions_data['progress'][mission['id']] = missions_data['progress'].get(mission['id'], 0) + amount
            
            # Check if completed
            if missions_data['progress'][mission['id']] >= mission['target']:
                missions_data['completed'].append(mission['id'])
                return {
                    'completed': True,
                    'mission': mission,
                    'all_complete': len(missions_data['completed']) == 3
                }
    
    return {'completed': False}


def can_battle_today(player):
    """Check if player can battle today (hasn't hit daily limit)."""
    tier_key, tier_data = get_league_tier(player.get('league_points', 0))
    battles_today = player.get('battles_today', 0)
    
    return {
        'can_battle': battles_today < tier_data['daily_battle_limit'],
        'battles_remaining': tier_data['daily_battle_limit'] - battles_today,
        'daily_limit': tier_data['daily_battle_limit']
    }


def get_streak_status(streak):
    """Get streak status display."""
    if streak == 0:
        return None
    
    # Find the highest achieved streak bonus
    for streak_level in sorted(STREAK_BONUSES.keys(), reverse=True):
        if streak >= streak_level:
            bonus = STREAK_BONUSES[streak_level]
            return {
                'streak': streak,
                'name': bonus['name'],
                'emoji': bonus['emoji'],
                'multiplier': bonus['ryo_multiplier']
            }
    
    # Below minimum streak for bonuses
    return {
        'streak': streak,
        'name': f'{streak}-Win Streak',
        'emoji': '🔥' if streak >= 2 else '✨',
        'multiplier': 1.0
    }


def apply_weekly_rewards(player):
    """Calculate and return weekly rewards for player's tier."""
    tier_key, tier_data = get_league_tier(player.get('league_points', 0))
    rewards = tier_data['weekly_reward'].copy()
    
    # Bonus for top 3 in tier (would need leaderboard data)
    # For now just return base rewards
    
    return {
        'tier': tier_key,
        'tier_name': tier_data['name'],
        'emoji': tier_data['emoji'],
        'rewards': rewards
    }
