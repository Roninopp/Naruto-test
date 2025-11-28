"""
Battle Enemies - All enemy definitions organized by league tier
"""

# 🎮 ENEMY DATABASE - Organized by League Tier

ENEMIES_BY_LEAGUE = {
    'genin': {
        'bandit': {
            'name': 'Bandit Leader',
            'image': 'https://envs.sh/VuB.jpg',
            'emoji': '🗡️',
            'max_hp': 100,
            'attacks': {
                'slash': {'name': 'Rusty Blade', 'power': 15, 'chakra': 10, 'weak_to': [], 'strong_vs': []},
                'throw': {'name': 'Kunai Throw', 'power': 18, 'chakra': 12, 'weak_to': [], 'strong_vs': []},
                'dirty': {'name': 'Dirty Tactics', 'power': 12, 'chakra': 8, 'weak_to': [], 'strong_vs': []}
            },
            'weakness': 't',
            'base_reward': 200,
            'chakra': 60,
            'ai_pattern': 'random',
            'difficulty': 'easy'
        },
        'rogue': {
            'name': 'Rogue Genin',
            'image': 'https://envs.sh/VuC.jpg',
            'emoji': '🥷',
            'max_hp': 110,
            'attacks': {
                'clone': {'name': 'Clone Jutsu', 'power': 16, 'chakra': 15, 'weak_to': [], 'strong_vs': []},
                'wire': {'name': 'Wire Trap', 'power': 14, 'chakra': 10, 'weak_to': [], 'strong_vs': []},
                'shuriken': {'name': 'Shuriken Storm', 'power': 20, 'chakra': 18, 'weak_to': [], 'strong_vs': []}
            },
            'weakness': 'f',
            'base_reward': 250,
            'chakra': 70,
            'ai_pattern': 'random',
            'difficulty': 'easy'
        },
        'academy': {
            'name': 'Failed Academy Student',
            'image': 'https://envs.sh/VuD.jpg',
            'emoji': '📚',
            'max_hp': 90,
            'attacks': {
                'basic': {'name': 'Basic Punch', 'power': 12, 'chakra': 5, 'weak_to': [], 'strong_vs': []},
                'novice': {'name': 'Novice Jutsu', 'power': 15, 'chakra': 12, 'weak_to': [], 'strong_vs': []},
                'desperate': {'name': 'Desperate Strike', 'power': 18, 'chakra': 15, 'weak_to': [], 'strong_vs': []}
            },
            'weakness': 'sc',
            'base_reward': 180,
            'chakra': 50,
            'ai_pattern': 'random',
            'difficulty': 'easy'
        }
    },
    
    'chunin': {
        'zabuza': {
            'name': 'Zabuza Momochi',
            'image': 'https://envs.sh/Vux.jpg',
            'emoji': '⚔️',
            'max_hp': 150,
            'attacks': {
                'wd': {'name': 'Water Dragon Jutsu', 'power': 28, 'chakra': 20, 'weak_to': ['l'], 'strong_vs': ['f']},
                'hm': {'name': 'Hidden Mist', 'power': 22, 'chakra': 15, 'weak_to': ['w'], 'strong_vs': []},
                'sw': {'name': 'Silent Killing', 'power': 32, 'chakra': 25, 'weak_to': [], 'strong_vs': []}
            },
            'weakness': 'l',
            'base_reward': 600,
            'chakra': 100,
            'ai_pattern': 'aggressive',
            'difficulty': 'medium'
        },
        'sound': {
            'name': 'Sound Ninja Quartet',
            'image': 'https://envs.sh/VFE.jpg',
            'emoji': '🎵',
            'max_hp': 130,
            'attacks': {
                'sw': {'name': 'Sound Wave Blast', 'power': 24, 'chakra': 15, 'weak_to': [], 'strong_vs': []},
                'cm': {'name': 'Curse Mark Power', 'power': 30, 'chakra': 20, 'weak_to': ['m'], 'strong_vs': ['t']},
                'kb': {'name': 'Kunai Barrage', 'power': 18, 'chakra': 10, 'weak_to': [], 'strong_vs': []}
            },
            'weakness': 'g',
            'base_reward': 550,
            'chakra': 90,
            'ai_pattern': 'balanced',
            'difficulty': 'medium'
        },
        'haku': {
            'name': 'Haku',
            'image': 'https://envs.sh/VuE.jpg',
            'emoji': '❄️',
            'max_hp': 140,
            'attacks': {
                'ice': {'name': 'Ice Needles', 'power': 26, 'chakra': 18, 'weak_to': ['f'], 'strong_vs': ['wa']},
                'mirror': {'name': 'Crystal Ice Mirrors', 'power': 30, 'chakra': 25, 'weak_to': ['f'], 'strong_vs': []},
                'speed': {'name': 'Lightning Speed', 'power': 22, 'chakra': 15, 'weak_to': [], 'strong_vs': []}
            },
            'weakness': 'f',
            'base_reward': 580,
            'chakra': 95,
            'ai_pattern': 'defensive',
            'difficulty': 'medium'
        }
    },
    
    'jonin': {
        'itachi': {
            'name': 'Itachi Uchiha',
            'image': 'https://envs.sh/VFD.jpg',
            'emoji': '🔴',
            'max_hp': 180,
            'attacks': {
                'am': {'name': 'Amaterasu', 'power': 42, 'chakra': 35, 'weak_to': ['w'], 'strong_vs': ['wa']},
                'ts': {'name': 'Tsukuyomi', 'power': 38, 'chakra': 30, 'weak_to': [], 'strong_vs': ['g']},
                'fb': {'name': 'Fireball Jutsu', 'power': 28, 'chakra': 20, 'weak_to': ['wa'], 'strong_vs': []}
            },
            'weakness': '',
            'base_reward': 1500,
            'chakra': 120,
            'ai_pattern': 'smart',
            'difficulty': 'hard'
        },
        'kisame': {
            'name': 'Kisame Hoshigaki',
            'image': 'https://envs.sh/VuF.jpg',
            'emoji': '🦈',
            'max_hp': 200,
            'attacks': {
                'shark': {'name': 'Shark Bomb', 'power': 40, 'chakra': 30, 'weak_to': ['l'], 'strong_vs': ['f']},
                'samehada': {'name': 'Samehada Slash', 'power': 35, 'chakra': 25, 'weak_to': [], 'strong_vs': []},
                'water': {'name': 'Water Prison', 'power': 32, 'chakra': 28, 'weak_to': ['l'], 'strong_vs': []}
            },
            'weakness': 'l',
            'base_reward': 1600,
            'chakra': 140,
            'ai_pattern': 'aggressive',
            'difficulty': 'hard'
        },
        'oro': {
            'name': 'Orochimaru',
            'image': 'https://envs.sh/VuG.jpg',
            'emoji': '🐍',
            'max_hp': 190,
            'attacks': {
                'snake': {'name': 'Hidden Shadow Snakes', 'power': 36, 'chakra': 28, 'weak_to': ['f'], 'strong_vs': []},
                'curse': {'name': 'Curse Mark Seal', 'power': 38, 'chakra': 30, 'weak_to': [], 'strong_vs': ['g']},
                'sword': {'name': 'Kusanagi Sword', 'power': 34, 'chakra': 25, 'weak_to': [], 'strong_vs': []}
            },
            'weakness': 'f',
            'base_reward': 1550,
            'chakra': 130,
            'ai_pattern': 'tricky',
            'difficulty': 'hard'
        }
    },
    
    'anbu': {
        'pain': {
            'name': 'Pain (Deva Path)',
            'image': 'https://envs.sh/VuH.jpg',
            'emoji': '👁️',
            'max_hp': 250,
            'attacks': {
                'shinra': {'name': 'Shinra Tensei', 'power': 50, 'chakra': 40, 'weak_to': [], 'strong_vs': []},
                'bansho': {'name': 'Bansho Tenin', 'power': 45, 'chakra': 35, 'weak_to': [], 'strong_vs': []},
                'chibaku': {'name': 'Chibaku Tensei', 'power': 55, 'chakra': 45, 'weak_to': [], 'strong_vs': []}
            },
            'weakness': '',
            'base_reward': 3200,
            'chakra': 160,
            'ai_pattern': 'genius',
            'difficulty': 'very_hard'
        },
        'minato': {
            'name': 'Minato Namikaze',
            'image': 'https://envs.sh/VuI.jpg',
            'emoji': '⚡',
            'max_hp': 230,
            'attacks': {
                'ftg': {'name': 'Flying Thunder God', 'power': 48, 'chakra': 38, 'weak_to': [], 'strong_vs': []},
                'rasengan': {'name': 'Rasengan', 'power': 46, 'chakra': 35, 'weak_to': [], 'strong_vs': []},
                'kunai': {'name': 'Hiraishin Kunai', 'power': 42, 'chakra': 32, 'weak_to': [], 'strong_vs': []}
            },
            'weakness': '',
            'base_reward': 3000,
            'chakra': 150,
            'ai_pattern': 'genius',
            'difficulty': 'very_hard'
        },
        'jiraiya': {
            'name': 'Jiraiya (Sage Mode)',
            'image': 'https://envs.sh/VuJ.jpg',
            'emoji': '🐸',
            'max_hp': 240,
            'attacks': {
                'sage': {'name': 'Sage Art: Rasengan', 'power': 52, 'chakra': 42, 'weak_to': [], 'strong_vs': []},
                'fire': {'name': 'Fire Style: Flame Bomb', 'power': 44, 'chakra': 34, 'weak_to': ['wa'], 'strong_vs': []},
                'toad': {'name': 'Toad Oil Bomb', 'power': 46, 'chakra': 36, 'weak_to': [], 'strong_vs': ['f']}
            },
            'weakness': 'wa',
            'base_reward': 3100,
            'chakra': 155,
            'ai_pattern': 'genius',
            'difficulty': 'very_hard'
        }
    },
    
    'kage': {
        'madara': {
            'name': 'Madara Uchiha',
            'image': 'https://envs.sh/VuK.jpg',
            'emoji': '👹',
            'max_hp': 320,
            'attacks': {
                'susanoo': {'name': 'Perfect Susanoo', 'power': 65, 'chakra': 50, 'weak_to': [], 'strong_vs': []},
                'meteor': {'name': 'Tengai Shinsei', 'power': 70, 'chakra': 55, 'weak_to': [], 'strong_vs': []},
                'fire': {'name': 'Majestic Destroyer Flame', 'power': 60, 'chakra': 45, 'weak_to': ['wa'], 'strong_vs': []}
            },
            'weakness': '',
            'base_reward': 6500,
            'chakra': 200,
            'ai_pattern': 'legendary',
            'difficulty': 'legendary'
        },
        'hashirama': {
            'name': 'Hashirama Senju',
            'image': 'https://envs.sh/VuL.jpg',
            'emoji': '🌳',
            'max_hp': 310,
            'attacks': {
                'wood': {'name': 'Wood Dragon', 'power': 62, 'chakra': 48, 'weak_to': ['f'], 'strong_vs': ['wa']},
                'sage': {'name': 'Sage Art: Wood Golem', 'power': 68, 'chakra': 52, 'weak_to': ['f'], 'strong_vs': []},
                'deep': {'name': 'Deep Forest Emergence', 'power': 58, 'chakra': 44, 'weak_to': ['f'], 'strong_vs': []}
            },
            'weakness': 'f',
            'base_reward': 6200,
            'chakra': 190,
            'ai_pattern': 'legendary',
            'difficulty': 'legendary'
        },
        'sixpaths': {
            'name': 'Six Paths Naruto',
            'image': 'https://envs.sh/VuM.jpg',
            'emoji': '☀️',
            'max_hp': 350,
            'attacks': {
                'tbb': {'name': 'Tailed Beast Bomb', 'power': 75, 'chakra': 60, 'weak_to': [], 'strong_vs': []},
                'rasenshuriken': {'name': 'Rasenshuriken', 'power': 70, 'chakra': 55, 'weak_to': [], 'strong_vs': []},
                'truthseeker': {'name': 'Truth-Seeking Orbs', 'power': 65, 'chakra': 50, 'weak_to': [], 'strong_vs': []}
            },
            'weakness': '',
            'base_reward': 7000,
            'chakra': 220,
            'ai_pattern': 'legendary',
            'difficulty': 'legendary'
        }
    }
}


def get_enemies_for_league(league_tier):
    """Get all enemies available for a league tier."""
    return ENEMIES_BY_LEAGUE.get(league_tier, {})


def get_enemy_by_key(enemy_key):
    """Get a specific enemy by its key across all leagues."""
    for league, enemies in ENEMIES_BY_LEAGUE.items():
        if enemy_key in enemies:
            return enemies[enemy_key]
    return None


def get_enemy_ai_move(enemy_data, game_state):
    """Determine enemy's next move based on AI pattern."""
    import random
    
    ai_pattern = enemy_data.get('ai_pattern', 'random')
    available_attacks = [
        key for key, attack in enemy_data['attacks'].items()
        if attack['chakra'] <= game_state['enemy_chakra']
    ]
    
    if not available_attacks:
        return None
    
    if ai_pattern == 'random':
        return random.choice(available_attacks)
    
    elif ai_pattern == 'aggressive':
        best_attack = max(available_attacks, 
                         key=lambda k: enemy_data['attacks'][k]['power'])
        return best_attack
    
    elif ai_pattern == 'defensive':
        if game_state['enemy_hp'] < enemy_data['max_hp'] * 0.3:
            return max(available_attacks, 
                      key=lambda k: enemy_data['attacks'][k]['power'])
        else:
            return min(available_attacks,
                      key=lambda k: enemy_data['attacks'][k]['chakra'])
    
    elif ai_pattern in ['smart', 'genius', 'legendary']:
        last_player_moves = game_state.get('player_move_history', [])
        
        if len(last_player_moves) >= 2 and last_player_moves[-1] == last_player_moves[-2]:
            for attack_key in available_attacks:
                attack = enemy_data['attacks'][attack_key]
                if last_player_moves[-1] in attack.get('strong_vs', []):
                    return attack_key
        
        return max(available_attacks,
                  key=lambda k: enemy_data['attacks'][k]['power'])
    
    else:
        return random.choice(available_attacks)
