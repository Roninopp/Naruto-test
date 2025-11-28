import random
import math
import json 
import datetime 
from datetime import timezone 

# --- Constants ---
SHOP_INVENTORY = {
    'kunai': {'name': 'Kunai', 'type': 'weapon', 'price': 250, 'stats': {'strength': 5, 'speed': 0, 'intelligence': 0, 'stamina': 0}},
    'shuriken_pack': {'name': 'Shuriken Pack', 'type': 'weapon', 'price': 600, 'stats': {'strength': 8, 'speed': 2, 'intelligence': 0, 'stamina': 0}},
    'flak_jacket': {'name': 'Flak Jacket', 'type': 'armor', 'price': 400, 'stats': {'strength': 0, 'speed': 0, 'intelligence': 0, 'stamina': 10}},
    'health_potion': {'name': 'Health Potion', 'type': 'consumable', 'price': 100, 'stats': {'heal': 50}},
    'soldier_pill': {'name': '💊 Soldier Pill', 'type': 'consumable', 'price': 50, 'desc': 'Restores energy for a quick duel.'},
    'chakra_pill': {'name': '🔵 Chakra Pill', 'type': 'consumable', 'price': 100, 'desc': 'Restores 50 Chakra.'}
}

VILLAGES = {
    'konoha': 'Konoha (Fire 🔥)',
    'suna': 'Suna (Wind 💨)',
    'kiri': 'Kiri (Water 💧)',
    'kumo': 'Kumo (Lightning ⚡)',
    'iwa': 'Iwa (Earth ⛰️)'
}

VILLAGE_TO_ELEMENT = {
    'Konoha (Fire 🔥)': 'fire',
    'Suna (Wind 💨)': 'wind',
    'Kiri (Water 💧)': 'water',
    'Kumo (Lightning ⚡)': 'lightning',
    'Iwa (Earth ⛰️)': 'earth',
    # Also support without emoji for auto_register
    'Konohagakure (Leaf)': 'fire',
    'Kirigakure (Mist)': 'water',
    'Kumogakure (Cloud)': 'lightning',
    'Sunagakure (Sand)': 'wind',
    'Iwagakure (Rock)': 'earth'
}

MISSIONS = {
    'd_rank': {'name': 'D-Rank: Weeding Garden', 'exp': 50, 'ryo': 100, 'level_req': 1, 'animation': "🪴 Weeding garden...\n✅ Mission completed! +50 EXP"},
    'c_rank': {'name': 'C-Rank: Escort Client', 'exp': 150, 'ryo': 300, 'level_req': 10, 'animation': "🛡️ Escorting client...\n⚔️ Bandits defeated!\n✅ Mission success! +150 EXP"},
    'b_rank': {'name': 'B-Rank: Capture Target', 'exp': 400, 'ryo': 800, 'level_req': 20, 'animation': "🔍 Investigating...\n💥 Enemy ninja battle!\n🎯 Target captured!\n✅ Mission accomplished! +400 EXP"}
}

TRAINING_ANIMATIONS = {
    'chakra_control': {'frames': ["🧘 Meditating...", "💫 Chakra flowing...", "✨ Control improving!"], 'stat': 'max_chakra', 'amount': 5, 'reward_text': "🎯 Max Chakra +5!"},
    'taijutsu': {'frames': ["🥋 Practicing forms...", "💥 Sparring session!", "⚡ Speed increasing!"], 'stat': 'strength', 'amount': 3, 'reward_text': "🎯 Strength +3!"}
}

HAND_SIGNS = ['tiger', 'snake', 'dog', 'bird', 'ram', 'boar', 'hare', 'rat', 'monkey', 'dragon']

JUTSU_LIBRARY = {
    'fireball': {'name': 'Fireball', 'signs': ['tiger', 'snake', 'bird'], 'power': 45, 'chakra_cost': 25, 'element': 'fire', 'level_required': 5},
    'great_fireball': {'name': 'Great Fireball', 'signs': ['tiger', 'snake', 'ram', 'bird'], 'power': 70, 'chakra_cost': 40, 'element': 'fire', 'level_required': 12},
    'water_dragon': {'name': 'Water Dragon', 'signs': ['tiger', 'dog', 'snake', 'bird'], 'power': 65, 'chakra_cost': 35, 'element': 'water', 'level_required': 15},
    'fire_phoenix': {'name': 'Fire Phoenix', 'signs': ['tiger', 'snake', 'boar', 'bird', 'dragon'], 'power': 95, 'chakra_cost': 60, 'element': 'fire', 'level_required': 25, 'discovered': False}
}

ELEMENT_MATRIX = {
    'fire': {'wind': 1.5, 'earth': 0.75, 'water': 0.5, 'lightning': 1.0, 'fire': 1.0, 'none': 1.0},
    'water': {'fire': 1.5, 'earth': 1.0, 'lightning': 0.5, 'wind': 0.75, 'water': 1.0, 'none': 1.0},
    'wind': {'lightning': 1.5, 'earth': 0.5, 'fire': 0.75, 'water': 1.0, 'wind': 1.0, 'none': 1.0},
    'earth': {'lightning': 1.5, 'water': 0.75, 'fire': 1.0, 'wind': 1.5, 'earth': 1.0, 'none': 1.0},
    'lightning': {'water': 1.5, 'earth': 0.5, 'wind': 0.75, 'fire': 1.0, 'lightning': 1.0, 'none': 1.0},
    'none': {'fire': 1.0, 'water': 1.0, 'wind': 1.0, 'earth': 1.0, 'lightning': 1.0, 'none': 1.0}
}

ELEMENT_ANIMATIONS = {
    'fire': ["🔥 FIRE STYLE! 🔥", "🔥🔥 Igniting! 🔥🔥", "🔥🔥🔥 INFERNO! 🔥🔥🔥", "💥 BURNING DAMAGE! ❤️‍🔥"],
    'water': ["💧 WATER STYLE! 💧", "🌊 Waves forming! 🌊", "🌊💦 TSUNAMI! 💦🌊", "💦 SOAKING HIT! 🌊"],
    'lightning': ["⚡ LIGHTNING STYLE! ⚡", "⚡⚡ Charging! ⚡⚡", "⚡⚡⚡ THUNDER STRIKE! ⚡⚡⚡", "💢 SHOCK DAMAGE! 🌀"],
    'wind': ["💨 WIND STYLE! 💨", "💨💨 Gusts building! 💨💨", "💨💨💨 TYPHOON! 💨💨💨", "🌪 SLASHING WIND! 🎯"],
    'earth': ["⛰ EARTH STYLE! ⛰", "⛰⛰ Ground shaking! ⛰⛰", "⛰⛰⛰ QUAKE! ⛰⛰⛰", "💢 CRUSHING DAMAGE! 🪨"]
}

CRITICAL_HIT_FRAMES = ["✨ ✨ ✨", "💥 CRITICAL HIT! 💥", "⭐ DEVASTATING BLOW! ⭐", "🎯 WEAK POINT HIT!", "✨ ✨ ✨"]

RANKS = ['Academy Student', 'Genin', 'Chunin', 'Jonin', 'Kage']
RANK_REQUIREMENTS = {1: 'Academy Student', 10: 'Genin', 25: 'Chunin', 40: 'Jonin', 60: 'Kage'}

def get_exp_for_next_level(level): 
    return level * 150

STAT_POINTS_PER_LEVEL = 6
BASE_HP = 100
BASE_CHAKRA = 100

def health_bar(current, maximum, length=10):
    if maximum <= 0: return f"[🖤🖤🖤🖤🖤🖤🖤🖤🖤🖤] 0/0"
    current = max(0, current)
    filled = int((current / maximum) * length)
    empty = length - filled
    return f"[{'❤️' * filled}{'🖤' * empty}] {current}/{maximum}"

def chakra_bar(current, maximum, length=8):
    if maximum <= 0: return f"[⚪⚪⚪⚪⚪⚪⚪⚪] 0/0"
    current = max(0, current)
    filled = int((current / maximum) * length)
    empty = length - filled
    return f"[{'🔵' * filled}{'⚪' * empty}] {current}/{maximum}"

def get_rank(level):
    current_rank = 'Academy Student'
    for level_req, rank_name in RANK_REQUIREMENTS.items():
        if level >= level_req: 
            current_rank = rank_name
    return current_rank

def distribute_stats(player_stats, points_to_add):
    stats_to_upgrade = ['strength', 'speed', 'intelligence', 'stamina']
    for _ in range(points_to_add):
        stat_to_boost = random.choice(stats_to_upgrade)
        player_stats[stat_to_boost] += 1
    player_stats['max_hp'] = BASE_HP + (player_stats['stamina'] * 10)
    player_stats['max_chakra'] = BASE_CHAKRA + (player_stats['intelligence'] * 5)
    return player_stats

def get_total_stats(player_data):
    """
    Calculate total stats including equipment bonuses.
    Compatible with both old and new battle systems.
    """
    total_stats = {
        'strength': player_data.get('strength', 10),
        'speed': player_data.get('speed', 10),
        'intelligence': player_data.get('intelligence', 10),
        'stamina': player_data.get('stamina', 10)
    }
    
    player_equipment = player_data.get('equipment') or {}
    
    for slot, item_key in player_equipment.items():
        if item_key:
            item_info = SHOP_INVENTORY.get(item_key)
            if item_info and 'stats' in item_info:
                for stat, value in item_info['stats'].items():
                    if value > 0 and stat in total_stats:
                        total_stats[stat] += value
    
    total_stats['max_hp'] = BASE_HP + (total_stats['stamina'] * 10)
    total_stats['max_chakra'] = BASE_CHAKRA + (total_stats['intelligence'] * 5)
    
    return total_stats

def check_for_level_up(player_data):
    leveled_up = False
    messages = []
    exp_needed = get_exp_for_next_level(player_data['level'])
    
    while player_data['exp'] >= exp_needed:
        if player_data['level'] >= 60:
            player_data['exp'] = 0
            break
        
        leveled_up = True
        player_data['level'] += 1
        player_data['exp'] -= exp_needed
        messages.append(f"🎉 LEVEL UP! You are now Level {player_data['level']}! 🎉")
        
        player_data = distribute_stats(player_data, STAT_POINTS_PER_LEVEL)
        messages.append(f"💪 Your stats have increased! (+{STAT_POINTS_PER_LEVEL} points)")
        
        new_rank = get_rank(player_data['level'])
        if new_rank != player_data['rank']:
            player_data['rank'] = new_rank
            messages.append(f"🏆 RANK UP! You are now a {new_rank}! 🏆")
        
        # Update HP/Chakra to new max
        total_stats = get_total_stats(player_data)
        player_data['current_hp'] = total_stats['max_hp']
        player_data['current_chakra'] = total_stats['max_chakra']
        player_data['max_hp'] = total_stats['max_hp']
        player_data['max_chakra'] = total_stats['max_chakra']
        
        exp_needed = get_exp_for_next_level(player_data['level'])
    
    return player_data, leveled_up, messages

def calculate_damage(attacker, defender, jutsu_info):
    """
    Calculate jutsu damage with element bonuses.
    Returns: (damage, is_critical, is_super_effective)
    """
    attacker_stats = get_total_stats(attacker)
    defender_stats = get_total_stats(defender)
    
    attacker_level = attacker.get('level', 1)
    attacker_speed = attacker_stats['speed']
    
    # Get defender's element
    defender_village = defender.get('village', 'none')
    defender_element = VILLAGE_TO_ELEMENT.get(defender_village, 'none')
    
    jutsu_power = jutsu_info['power']
    jutsu_element = jutsu_info['element']
    
    # Base damage
    base_damage = jutsu_power + (attacker_level * 2)
    
    # Element bonus
    element_bonus = ELEMENT_MATRIX[jutsu_element].get(defender_element, 1.0)
    
    # Critical hit chance (based on speed)
    critical_chance = (attacker_speed / 200) + 0.05
    is_critical = random.random() < critical_chance
    critical_multiplier = 1.8 if is_critical else 1.0
    
    # Final damage
    final_damage = int(base_damage * element_bonus * critical_multiplier)
    
    # Is super effective?
    is_super_eff = element_bonus > 1.0
    
    return final_damage, is_critical, is_super_eff

def calculate_taijutsu_damage(attacker, defender):
    """
    Calculate basic taijutsu damage.
    Returns: (damage, is_critical)
    """
    attacker_stats = get_total_stats(attacker)
    
    # Base damage from strength
    base_damage = attacker_stats['strength'] * 0.8
    
    # Critical hit chance
    critical_chance = (attacker_stats['speed'] / 200) + 0.05
    is_critical = random.random() < critical_chance
    critical_multiplier = 1.8 if is_critical else 1.0
    
    final_damage = int(base_damage * critical_multiplier)
    
    return final_damage, is_critical

# World Boss data (for other modules)
WORLD_BOSSES = {
    'gedo_mazo': {'name': 'Gedo Mazo Statue', 'hp': 10000, 'ryo_pool': 25000, 'image': 'images/gedo_mazo.png', 'taijutsu_recoil': 0.05, 'jutsu_recoil': 0.15},
    'ten_tails': {'name': 'Ten-Tails (Incomplete)', 'hp': 50000, 'ryo_pool': 100000, 'image': 'images/ten_tails.png', 'taijutsu_recoil': 0.08, 'jutsu_recoil': 0.20}
}

# Akatsuki enemies (for event system)
AKATSUKI_ENEMIES = {
    'sasuke_clone': {'name': 'Sasuke (Clone)', 'desc': "A fast and skilled clone, it strikes with deadly precision!", 'level': 10, 'strength': 20, 'speed': 25, 'stamina': 10, 'intelligence': 15, 'max_hp': 200, 'image': 'https://envs.sh/NMW.jpg'}
}

# Hospital check helper
def get_hospital_status(player_data):
    """
    Checks if a player is hospitalized.
    Returns: (is_hospitalized, remaining_seconds)
    """
    hospital_time = player_data.get('hospitalized_until')
    
    if not hospital_time:
        return False, 0
    
    now = datetime.datetime.now(timezone.utc)
    
    # Ensure it's a datetime object
    if isinstance(hospital_time, str):
        try:
            hospital_time = datetime.datetime.fromisoformat(hospital_time)
        except ValueError:
            return False, 0
    
    # Ensure timezone-aware
    if hospital_time.tzinfo is None:
        hospital_time = hospital_time.replace(tzinfo=timezone.utc)
    
    # Check if still hospitalized
    if now < hospital_time:
        remaining_seconds = (hospital_time - now).total_seconds()
        return True, remaining_seconds
    
    return False, 0
