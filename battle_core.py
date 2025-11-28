"""
🔥 BATTLE CORE - Constants & Helper Functions
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All battle constants, calculations, and display logic.
No async functions here - pure logic only!
"""

import random
import game_logic as gl

# ═══════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════

# Betting limits by level
BETTING_LIMITS = {
    'low': {'min': 50, 'max': 500, 'level_max': 10},
    'mid': {'min': 100, 'max': 1000, 'level_max': 25},
    'high': {'min': 200, 'max': 2000, 'level_max': 40},
    'elite': {'min': 500, 'max': 5000, 'level_max': 60}
}

HOUSE_FEE_PERCENT = 0.10  # 10% house fee
BATTLE_COOLDOWN_MINUTES = 5
TURN_TIMEOUT_SECONDS = 30
MAX_TURNS = 15  # Auto-draw after 15 turns (faster battles!)
INVITE_TIMEOUT_MINUTES = 2  # Battle invites expire after 2 minutes
BATTLE_TIMEOUT_MINUTES = 20  # Battles auto-forfeit after 20 minutes

# Stance modifiers
STANCES = {
    'aggressive': {
        'emoji': '⚔️',
        'name': 'Aggressive',
        'damage_mult': 1.3,
        'defense_mult': 0.8,
        'chakra_regen': 5,
        'desc': '+30% DMG, -20% DEF'
    },
    'defensive': {
        'emoji': '🛡️',
        'name': 'Defensive',
        'damage_mult': 0.7,
        'defense_mult': 1.4,
        'chakra_regen': 10,
        'desc': '-30% DMG, +40% DEF'
    },
    'balanced': {
        'emoji': '⚖️',
        'name': 'Balanced',
        'damage_mult': 1.0,
        'defense_mult': 1.0,
        'chakra_regen': 15,
        'desc': 'Normal, +15 chakra/turn'
    }
}

# Status effects
STATUS_EFFECTS = {
    'burn': {
        'emoji': '🔥',
        'name': 'Burning',
        'damage_per_turn': 10,
        'duration': 3,
        'element': 'fire'
    },
    'stun': {
        'emoji': '⚡',
        'name': 'Stunned',
        'skip_chance': 0.5,
        'duration': 2,
        'element': 'lightning'
    },
    'slow': {
        'emoji': '💧',
        'name': 'Slowed',
        'damage_reduction': 0.2,
        'duration': 3,
        'element': 'water'
    },
    'bleed': {
        'emoji': '🩸',
        'name': 'Bleeding',
        'base_damage': 5,
        'duration': 4,
        'element': 'wind'
    }
}

# Achievement bonuses
ACHIEVEMENTS = {
    'flawless': {
        'emoji': '✨',
        'name': 'FLAWLESS VICTORY',
        'bonus_ryo': 500,
        'desc': 'Win without taking damage'
    },
    'underdog': {
        'emoji': '🎯',
        'name': 'UNDERDOG TRIUMPH',
        'bonus_ryo': 1000,
        'desc': 'Win with 10+ level difference'
    },
    'speedrun': {
        'emoji': '⚡',
        'name': 'SPEEDRUN',
        'bonus_ryo': 300,
        'desc': 'Win in 5 turns or less'
    },
    'comeback': {
        'emoji': '🔥',
        'name': 'COMEBACK KING',
        'bonus_ryo': 700,
        'desc': 'Win from <20% HP'
    }
}

# Rare drop rates
DROP_RATES = {
    'health_potion': 0.20,  # 20%
    'chakra_pill': 0.15,    # 15%
    'legendary': 0.05       # 5%
}

# ═══════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════

def get_betting_limit(level):
    """Get min/max bet based on player level"""
    for tier, limits in BETTING_LIMITS.items():
        if level <= limits['level_max']:
            return limits['min'], limits['max']
    return BETTING_LIMITS['elite']['min'], BETTING_LIMITS['elite']['max']

def calculate_pot(bet_amount):
    """Calculate total pot and house fee"""
    total_pot = bet_amount * 2
    house_fee = int(total_pot * HOUSE_FEE_PERCENT)
    winner_payout = total_pot - house_fee
    return total_pot, house_fee, winner_payout

def calculate_combo_multiplier(combo_count):
    """Calculate damage multiplier based on combo"""
    if combo_count <= 1:
        return 1.0
    elif combo_count == 2:
        return 1.15  # +15%
    elif combo_count == 3:
        return 1.30  # +30%
    else:  # 4+
        return 1.50  # +50%

def get_critical_hp_bonus(current_hp, max_hp):
    """Get damage bonus for low HP (Desperate Mode)"""
    hp_percent = (current_hp / max_hp) * 100
    
    if hp_percent < 15:
        return 1.50  # +50% damage (Last Stand)
    elif hp_percent < 30:
        return 1.25  # +25% damage (Desperate Mode)
    else:
        return 1.0   # Normal

def calculate_status_effect_chance(attacker_element, jutsu_element):
    """Calculate chance to apply status effect"""
    if attacker_element == jutsu_element:
        return 0.30  # 30% if village matches jutsu element
    else:
        return 0.15  # 15% base chance

def get_status_effect_from_element(element):
    """Get status effect key from jutsu element"""
    element_to_status = {
        'fire': 'burn',
        'lightning': 'stun',
        'water': 'slow',
        'wind': 'bleed'
    }
    return element_to_status.get(element)

def calculate_battle_damage(attacker, defender, attacker_state, defender_state, base_damage, is_crit=False):
    """
    Calculate final battle damage with all modifiers.
    
    Modifiers applied:
    - Stance (attack/defense)
    - Combo multiplier
    - Critical HP bonus
    - Status effects (slow reduces damage dealt)
    - Critical hit multiplier
    """
    # Get stance modifiers
    attack_stance_mult = STANCES[attacker_state['stance']]['damage_mult']
    defense_stance_mult = STANCES[defender_state['stance']]['defense_mult']
    
    # Get combo multiplier
    combo_mult = calculate_combo_multiplier(attacker_state['combo'])
    
    # Get critical HP bonus
    attacker_stats = gl.get_total_stats(attacker)
    critical_hp_mult = get_critical_hp_bonus(attacker['current_hp'], attacker_stats['max_hp'])
    
    # Check for slow debuff on attacker
    slow_mult = 1.0
    if 'slow' in attacker_state['status_effects']:
        slow_mult = 0.8  # -20% damage when slowed
    
    # Critical hit
    crit_mult = 1.8 if is_crit else 1.0
    
    # Calculate final damage
    final_damage = base_damage * attack_stance_mult * (1 / defense_stance_mult)
    final_damage *= combo_mult * critical_hp_mult * slow_mult * crit_mult
    
    return int(final_damage)

def create_hp_bar(current, maximum, length=10):
    """Create visual HP bar with percentage"""
    if maximum <= 0:
        return "░" * length + " 0%"
    
    current = max(0, current)
    percentage = (current / maximum) * 100
    filled = int((current / maximum) * length)
    empty = length - filled
    
    bar = '█' * filled + '░' * empty
    return f"{bar} {int(percentage)}%"

def get_hp_status_emoji(hp_percent):
    """Get emoji based on HP percentage"""
    if hp_percent < 15:
        return '⚠️ DESPERATE MODE'
    elif hp_percent < 30:
        return '⚠️ LOW HP'
    else:
        return ''

def get_combo_display(combo_count):
    """Get combo display text"""
    if combo_count <= 1:
        return ""
    elif combo_count == 2:
        return "⚡ 2-HIT COMBO!"
    elif combo_count == 3:
        return "⚡⚡ 3-HIT COMBO!"
    else:
        return "⚡⚡⚡ UNSTOPPABLE!"

# ═══════════════════════════════════════
# BATTLE DISPLAY
# ═══════════════════════════════════════

def get_enhanced_battle_display(battle_state):
    """
    Create epic visual battle display.
    Returns formatted HTML text for battle status.
    """
    players = battle_state['players']
    player_ids = list(players.keys())
    
    # Sort by ID for consistency
    if player_ids[0] < player_ids[1]:
        p1, p2 = players[player_ids[0]], players[player_ids[1]]
    else:
        p1, p2 = players[player_ids[1]], players[player_ids[0]]
    
    # Get stats
    p1_stats = gl.get_total_stats(p1)
    p2_stats = gl.get_total_stats(p2)
    
    # Get battle states
    p1_state = battle_state['player_states'][p1['user_id']]
    p2_state = battle_state['player_states'][p2['user_id']]
    
    # HP percentages and bars
    p1_hp_pct = (p1['current_hp'] / p1_stats['max_hp']) * 100
    p2_hp_pct = (p2['current_hp'] / p2_stats['max_hp']) * 100
    
    p1_hp_bar = create_hp_bar(p1['current_hp'], p1_stats['max_hp'])
    p2_hp_bar = create_hp_bar(p2['current_hp'], p2_stats['max_hp'])
    
    # Status icons
    p1_hp_status = get_hp_status_emoji(p1_hp_pct)
    p2_hp_status = get_hp_status_emoji(p2_hp_pct)
    
    # Stance display
    p1_stance = STANCES[p1_state['stance']]
    p2_stance = STANCES[p2_state['stance']]
    
    # Combo display
    p1_combo = get_combo_display(p1_state['combo'])
    p2_combo = get_combo_display(p2_state['combo'])
    
    # Status effects
    p1_effects = " ".join([STATUS_EFFECTS[e]['emoji'] for e in p1_state['status_effects'].keys()])
    p2_effects = " ".join([STATUS_EFFECTS[e]['emoji'] for e in p2_state['status_effects'].keys()])
    
    # Build display
    text = "╔══════════════════════════╗\n"
    text += f"║  <b>{p1['username'][:20]}</b>\n"
    text += f"║  Lvl {p1['level']} | {p1_stance['emoji']} {p1_stance['name']}\n"
    text += f"║  HP: {p1_hp_bar}\n"
    text += f"║  {p1_hp_status}\n" if p1_hp_status else ""
    text += f"║  ⚡ Chakra: {p1['current_chakra']}/{p1_stats['max_chakra']}\n"
    text += f"║  {p1_effects}\n" if p1_effects else ""
    text += f"║  {p1_combo}\n" if p1_combo else ""
    text += "╚══════════════════════════╝\n"
    text += "        ⚔️ VS ⚔️\n"
    text += "╔══════════════════════════╗\n"
    text += f"║  <b>{p2['username'][:20]}</b>\n"
    text += f"║  Lvl {p2['level']} | {p2_stance['emoji']} {p2_stance['name']}\n"
    text += f"║  HP: {p2_hp_bar}\n"
    text += f"║  {p2_hp_status}\n" if p2_hp_status else ""
    text += f"║  ⚡ Chakra: {p2['current_chakra']}/{p2_stats['max_chakra']}\n"
    text += f"║  {p2_effects}\n" if p2_effects else ""
    text += f"║  {p2_combo}\n" if p2_combo else ""
    text += "╚══════════════════════════╝\n\n"
    
    # Pot display
    if 'bet_amount' in battle_state:
        text += f"💰 <b>POT: {battle_state['pot_amount']:,} Ryo</b>\n"
        text += f"<i>Winner takes: {battle_state['winner_payout']:,} Ryo</i>\n\n"
    
    # Turn indicator
    turn_player = battle_state['players'][battle_state['turn']]
    text += f"🎯 <b>{turn_player['username']}'s Turn</b>\n"
    text += f"<i>Turn {battle_state.get('turn_number', 1)}/{MAX_TURNS}</i>"
    
    return text

# ═══════════════════════════════════════
# STATUS EFFECT LOGIC
# ═══════════════════════════════════════

def process_status_effects(player, player_state):
    """
    Process status effects for a player at start of their turn.
    Returns list of message strings and updates player HP.
    """
    messages = []
    effects_to_remove = []
    
    for effect_key, remaining_turns in list(player_state['status_effects'].items()):
        effect = STATUS_EFFECTS[effect_key]
        
        # Apply damage effects
        if 'damage_per_turn' in effect:
            damage = effect['damage_per_turn']
            player['current_hp'] -= damage
            messages.append(f"{effect['emoji']} {effect['name']}: -{damage} HP")
        
        # Bleed increases each turn
        if effect_key == 'bleed':
            turn_number = effect['duration'] - remaining_turns + 1
            damage = effect['base_damage'] * turn_number
            player['current_hp'] -= damage
            messages.append(f"{effect['emoji']} {effect['name']}: -{damage} HP (increasing!)")
        
        # Decrease duration
        player_state['status_effects'][effect_key] -= 1
        
        # Mark for removal if expired
        if player_state['status_effects'][effect_key] <= 0:
            effects_to_remove.append(effect_key)
            messages.append(f"{effect['emoji']} {effect['name']} wore off!")
    
    # Remove expired effects
    for effect_key in effects_to_remove:
        del player_state['status_effects'][effect_key]
    
    return messages

def try_apply_status_effect(attacker, defender_state, jutsu_element):
    """
    Try to apply status effect from jutsu element.
    Returns (success: bool, effect_key: str or None)
    """
    # Get attacker's village element
    attacker_element = gl.VILLAGE_TO_ELEMENT.get(attacker.get('village', ''), 'none')
    
    # Calculate chance
    chance = calculate_status_effect_chance(attacker_element, jutsu_element)
    
    # Roll
    if random.random() < chance:
        effect_key = get_status_effect_from_element(jutsu_element)
        if effect_key and effect_key not in defender_state['status_effects']:
            # Apply effect
            defender_state['status_effects'][effect_key] = STATUS_EFFECTS[effect_key]['duration']
            return True, effect_key
    
    return False, None

# ═══════════════════════════════════════
# ACHIEVEMENT CHECKING
# ═══════════════════════════════════════

def check_achievements(battle_state, winner_id, loser_id):
    """
    Check for achievement bonuses.
    Returns (achievements_earned: list, total_bonus_ryo: int)
    """
    winner = battle_state['players'][winner_id]
    loser = battle_state['players'][loser_id]
    winner_state = battle_state['player_states'][winner_id]
    
    achievements_earned = []
    total_bonus = 0
    
    # Flawless Victory
    if not winner_state['took_damage']:
        achievements_earned.append(ACHIEVEMENTS['flawless'])
        total_bonus += ACHIEVEMENTS['flawless']['bonus_ryo']
    
    # Underdog Win
    level_diff = loser['level'] - winner['level']
    if level_diff >= 10:
        achievements_earned.append(ACHIEVEMENTS['underdog'])
        total_bonus += ACHIEVEMENTS['underdog']['bonus_ryo']
    
    # Speedrun
    if battle_state.get('turn_number', 999) <= 5:
        achievements_earned.append(ACHIEVEMENTS['speedrun'])
        total_bonus += ACHIEVEMENTS['speedrun']['bonus_ryo']
    
    # Comeback King
    winner_stats = gl.get_total_stats(winner)
    hp_pct = (winner['current_hp'] / winner_stats['max_hp']) * 100
    if hp_pct < 20:
        achievements_earned.append(ACHIEVEMENTS['comeback'])
        total_bonus += ACHIEVEMENTS['comeback']['bonus_ryo']
    
    return achievements_earned, total_bonus

def check_rare_drop():
    """
    Check for rare item drops.
    Returns (dropped: bool, item_key: str or None)
    """
    roll = random.random()
    
    if roll < DROP_RATES['legendary']:
        return True, 'legendary_token'  # Special item
    elif roll < (DROP_RATES['legendary'] + DROP_RATES['health_potion']):
        return True, 'health_potion'
    elif roll < (DROP_RATES['legendary'] + DROP_RATES['health_potion'] + DROP_RATES['chakra_pill']):
        return True, 'chakra_pill'
    
    return False, None
