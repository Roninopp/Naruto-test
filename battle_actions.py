"""
⚔️ BATTLE ACTIONS - Combat Mechanics
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All combat action logic: Taijutsu, Jutsu, Items, Stances, Prediction
"""

import asyncio
import json
import random
import logging
from collections import Counter

import game_logic as gl
import animations as anim
import battle_core as bc

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════
# TAIJUTSU ACTION
# ═══════════════════════════════════════

async def execute_taijutsu(context, battle_state, attacker_id, defender_id, message_id):
    """
    Execute taijutsu (basic attack) action.
    
    Flow:
    1. Check for stun
    2. Calculate damage with all modifiers
    3. Animate attack
    4. Apply damage and update combo
    5. Check for KO
    6. Switch turn if not KO
    """
    attacker = battle_state['players'][attacker_id]
    defender = battle_state['players'][defender_id]
    
    attacker_state = battle_state['player_states'][attacker_id]
    defender_state = battle_state['player_states'][defender_id]
    
    chat_id = battle_state['chat_id']
    
    # Check for stun
    if 'stun' in attacker_state['status_effects']:
        if random.random() < bc.STATUS_EFFECTS['stun']['skip_chance']:
            # Stunned! Skip turn
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"{battle_state['base_text']}\n\n<i>⚡ {attacker['username']} is STUNNED and can't move!</i>",
                parse_mode="HTML"
            )
            await asyncio.sleep(2)
            
            # Reset combo
            attacker_state['combo'] = 0
            
            # Switch turn
            return await switch_turn(context, battle_state, defender_id, message_id)
    
    # Calculate base damage
    base_damage, is_crit = gl.calculate_taijutsu_damage(attacker, defender)
    
    # Apply all modifiers
    final_damage = bc.calculate_battle_damage(
        attacker, defender,
        attacker_state, defender_state,
        base_damage, is_crit
    )
    
    # Show processing
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=f"{battle_state['base_text']}\n\n<i>👊 {attacker['username']} prepares to strike...</i>",
        parse_mode="HTML"
    )
    await asyncio.sleep(1)
    
    # Apply damage
    defender['current_hp'] -= final_damage
    defender_state['took_damage'] = True
    
    # Increment attacker combo
    attacker_state['combo'] += 1
    
    # Reset defender combo (took damage)
    defender_state['combo'] = 0
    
    # Build result text
    result_text = f"{battle_state['base_text']}\n\n"
    
    if is_crit:
        result_text += "<b>💥 CRITICAL HIT! 💥</b>\n"
    
    if attacker_state['combo'] > 1:
        combo_text = bc.get_combo_display(attacker_state['combo'])
        result_text += f"<b>{combo_text}</b>\n"
    
    result_text += f"<i>👊 {attacker['username']} strikes {defender['username']}!</i>\n"
    result_text += f"<b>💢 {final_damage} damage!</b>"
    
    # Show result
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=result_text,
        parse_mode="HTML"
    )
    await asyncio.sleep(2)
    
    # Check for KO
    if defender['current_hp'] <= 0:
        return 'ko'
    
    # Switch turn
    return await switch_turn(context, battle_state, defender_id, message_id)

# ═══════════════════════════════════════
# JUTSU ACTION
# ═══════════════════════════════════════

async def execute_jutsu(context, battle_state, attacker_id, defender_id, jutsu_key, message_id):
    """
    Execute jutsu action.
    
    Flow:
    1. Validate jutsu and chakra
    2. Calculate damage with modifiers
    3. Animate jutsu (element-based)
    4. Try to apply status effect
    5. Apply damage and update combo
    6. Check for KO
    7. Switch turn
    """
    attacker = battle_state['players'][attacker_id]
    defender = battle_state['players'][defender_id]
    
    attacker_state = battle_state['player_states'][attacker_id]
    defender_state = battle_state['player_states'][defender_id]
    
    chat_id = battle_state['chat_id']
    
    # Get jutsu info
    jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_key)
    if not jutsu_info:
        return 'error'
    
    # Check chakra
    if attacker['current_chakra'] < jutsu_info['chakra_cost']:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"{battle_state['base_text']}\n\n<i>❌ Not enough chakra!</i>",
            parse_mode="HTML"
        )
        await asyncio.sleep(1.5)
        return 'continue'
    
    # Deduct chakra
    attacker['current_chakra'] -= jutsu_info['chakra_cost']
    
    # Calculate damage
    base_damage, is_crit, is_super_eff = gl.calculate_damage(attacker, defender, jutsu_info)
    
    # Apply battle modifiers
    final_damage = bc.calculate_battle_damage(
        attacker, defender,
        attacker_state, defender_state,
        base_damage, is_crit
    )
    
    # Show jutsu activation
    jutsu_name = jutsu_info['name']
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=f"{battle_state['base_text']}\n\n<i>🌀 {attacker['username']} uses <b>{jutsu_name}</b>!</i>",
        parse_mode="HTML"
    )
    await asyncio.sleep(1.5)
    
    # Apply damage
    defender['current_hp'] -= final_damage
    defender_state['took_damage'] = True
    
    # Increment combo
    attacker_state['combo'] += 1
    defender_state['combo'] = 0
    
    # Try to apply status effect
    status_applied, effect_key = bc.try_apply_status_effect(
        attacker, defender_state, jutsu_info['element']
    )
    
    # Build result text
    result_text = f"{battle_state['base_text']}\n\n"
    
    # Element animation
    element_emoji = {
        'fire': '🔥',
        'water': '💧',
        'lightning': '⚡',
        'wind': '💨',
        'earth': '🪨'
    }.get(jutsu_info['element'], '💥')
    
    result_text += f"<b>{element_emoji} {jutsu_name.upper()}! {element_emoji}</b>\n\n"
    
    if is_crit:
        result_text += "<b>💥 CRITICAL HIT!</b>\n"
    
    if is_super_eff:
        result_text += "<i>✨ It's super effective!</i>\n"
    
    if attacker_state['combo'] > 1:
        combo_text = bc.get_combo_display(attacker_state['combo'])
        result_text += f"<b>{combo_text}</b>\n"
    
    result_text += f"<b>💢 {final_damage} damage!</b>\n"
    
    if status_applied:
        effect = bc.STATUS_EFFECTS[effect_key]
        result_text += f"\n{effect['emoji']} <b>{defender['username']} is {effect['name']}!</b>"
    
    # Show result
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=result_text,
        parse_mode="HTML"
    )
    await asyncio.sleep(2.5)
    
    # Check for KO
    if defender['current_hp'] <= 0:
        return 'ko'
    
    # Switch turn
    return await switch_turn(context, battle_state, defender_id, message_id)

# ═══════════════════════════════════════
# ITEM ACTION
# ═══════════════════════════════════════

async def execute_item(context, battle_state, player_id, item_key, message_id):
    """
    Execute item usage.
    
    Supported items:
    - health_potion: Restores 50 HP
    - chakra_pill: Restores 50 Chakra
    """
    player = battle_state['players'][player_id]
    player_state = battle_state['player_states'][player_id]
    
    chat_id = battle_state['chat_id']
    
    # Get item info
    item_info = gl.SHOP_INVENTORY.get(item_key)
    if not item_info or item_info['type'] != 'consumable':
        return 'error'
    
    # Check inventory
    inventory = player.get('inventory', [])
    if item_key not in inventory:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"{battle_state['base_text']}\n\n<i>❌ Item not found in inventory!</i>",
            parse_mode="HTML"
        )
        await asyncio.sleep(1.5)
        return 'continue'
    
    # Show usage
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=f"{battle_state['base_text']}\n\n<i>🧪 {player['username']} uses {item_info['name']}...</i>",
        parse_mode="HTML"
    )
    await asyncio.sleep(1.5)
    
    # Remove from inventory
    inventory.remove(item_key)
    player['inventory'] = inventory
    
    # Apply effect
    result_text = f"{battle_state['base_text']}\n\n"
    
    if item_key == 'health_potion':
        heal_amount = item_info['stats']['heal']
        player_stats = gl.get_total_stats(player)
        max_hp = player_stats['max_hp']
        
        actual_heal = min(heal_amount, max_hp - player['current_hp'])
        
        if actual_heal <= 0:
            result_text += "<i>💊 HP is already full!</i>"
        else:
            player['current_hp'] += actual_heal
            result_text += f"<b>💚 Restored {actual_heal} HP!</b>"
    
    elif item_key == 'chakra_pill':
        restore_amount = 50
        player_stats = gl.get_total_stats(player)
        max_chakra = player_stats['max_chakra']
        
        actual_restore = min(restore_amount, max_chakra - player['current_chakra'])
        
        if actual_restore <= 0:
            result_text += "<i>🔵 Chakra is already full!</i>"
        else:
            player['current_chakra'] += actual_restore
            result_text += f"<b>💙 Restored {actual_restore} Chakra!</b>"
    
    # Show result
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=result_text,
        parse_mode="HTML"
    )
    await asyncio.sleep(2)
    
    # Using item doesn't break combo, but ends turn
    other_player_id = [pid for pid in battle_state['players'].keys() if pid != player_id][0]
    return await switch_turn(context, battle_state, other_player_id, message_id)

# ═══════════════════════════════════════
# STANCE SWITCHING
# ═══════════════════════════════════════

async def switch_stance(context, battle_state, player_id, new_stance, message_id):
    """
    Switch player stance.
    
    Stance switching is instant and doesn't end turn!
    This allows strategic play.
    """
    player = battle_state['players'][player_id]
    player_state = battle_state['player_states'][player_id]
    
    chat_id = battle_state['chat_id']
    
    # Validate stance
    if new_stance not in bc.STANCES:
        return 'error'
    
    # Update stance
    old_stance = player_state['stance']
    player_state['stance'] = new_stance
    
    stance_info = bc.STANCES[new_stance]
    
    # Show stance change
    text = f"{battle_state['base_text']}\n\n"
    text += f"<i>{stance_info['emoji']} {player['username']} switches to <b>{stance_info['name']}</b> stance!</i>\n"
    text += f"<i>{stance_info['desc']}</i>"
    
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode="HTML"
    )
    await asyncio.sleep(1.5)
    
    # Stance change doesn't end turn - return to menu
    return 'continue'

# ═══════════════════════════════════════
# PREDICTION SYSTEM
# ═══════════════════════════════════════

async def initiate_prediction(context, battle_state, predictor_id, message_id):
    """
    Start prediction mini-game.
    
    Player tries to predict opponent's next move.
    - Correct guess: Interrupt attack + 50% counter damage
    - Wrong guess: Take full damage from opponent
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    predictor = battle_state['players'][predictor_id]
    opponent_id = [pid for pid in battle_state['players'].keys() if pid != predictor_id][0]
    
    chat_id = battle_state['chat_id']
    
    # Store prediction state
    battle_state['prediction_active'] = True
    battle_state['predictor_id'] = predictor_id
    
    # Show prediction menu
    text = f"{battle_state['base_text']}\n\n"
    text += f"<b>🎯 {predictor['username']} is reading the opponent's moves!</b>\n\n"
    text += "<i>Guess their next action:</i>\n"
    text += "• Correct: Interrupt + Counter!\n"
    text += "• Wrong: Take full damage!"
    
    keyboard = [
        [
            InlineKeyboardButton("👊 Predict Taijutsu", callback_data=f"predict_taijutsu_{predictor_id}"),
            InlineKeyboardButton("🌀 Predict Jutsu", callback_data=f"predict_jutsu_{predictor_id}")
        ],
        [
            InlineKeyboardButton("🧪 Predict Item", callback_data=f"predict_item_{predictor_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"predict_cancel_{predictor_id}")
        ]
    ]
    
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
    return 'prediction_wait'

async def resolve_prediction(context, battle_state, predicted_action, actual_action, message_id):
    """
    Resolve prediction outcome.
    
    Args:
        predicted_action: What predictor guessed
        actual_action: What opponent actually did
    """
    predictor_id = battle_state['predictor_id']
    opponent_id = [pid for pid in battle_state['players'].keys() if pid != predictor_id][0]
    
    predictor = battle_state['players'][predictor_id]
    opponent = battle_state['players'][opponent_id]
    
    predictor_state = battle_state['player_states'][predictor_id]
    opponent_state = battle_state['player_states'][opponent_id]
    
    chat_id = battle_state['chat_id']
    
    # Clear prediction state
    battle_state['prediction_active'] = False
    del battle_state['predictor_id']
    
    # Check if prediction was correct
    if predicted_action == actual_action:
        # CORRECT PREDICTION!
        # Calculate counter damage (50% of predictor's taijutsu)
        base_damage, is_crit = gl.calculate_taijutsu_damage(predictor, opponent)
        counter_damage = int(base_damage * 0.5)
        
        # Apply damage to opponent
        opponent['current_hp'] -= counter_damage
        opponent_state['took_damage'] = True
        
        # Predictor gets combo
        predictor_state['combo'] += 1
        opponent_state['combo'] = 0
        
        # Show result
        result_text = f"{battle_state['base_text']}\n\n"
        result_text += "<b>🎯 PREDICTION SUCCESS! 🎯</b>\n\n"
        result_text += f"<i>{predictor['username']} read {opponent['username']}'s move!</i>\n"
        result_text += f"<b>⚡ COUNTER ATTACK! {counter_damage} damage!</b>"
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=result_text,
            parse_mode="HTML"
        )
        await asyncio.sleep(2.5)
        
        # Check for KO
        if opponent['current_hp'] <= 0:
            return 'ko'
        
        # Predictor keeps turn advantage
        return await switch_turn(context, battle_state, opponent_id, message_id)
    
    else:
        # WRONG PREDICTION
        # Opponent gets free hit with bonus damage
        result_text = f"{battle_state['base_text']}\n\n"
        result_text += "<b>❌ PREDICTION FAILED!</b>\n\n"
        result_text += f"<i>{predictor['username']} guessed wrong!</i>\n"
        result_text += f"<i>{opponent['username']} punishes the mistake!</i>"
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=result_text,
            parse_mode="HTML"
        )
        await asyncio.sleep(2)
        
        # Opponent gets turn with damage bonus stored
        battle_state['prediction_failed'] = True
        battle_state['failed_predictor_id'] = predictor_id
        
        # Switch to opponent's turn
        battle_state['turn'] = opponent_id
        return 'continue'

# ═══════════════════════════════════════
# TURN MANAGEMENT
# ═══════════════════════════════════════

async def switch_turn(context, battle_state, next_player_id, message_id):
    """
    Switch to next player's turn.
    
    Handles:
    - Status effect processing
    - Chakra regeneration
    - Turn counter
    - Max turn check (draw)
    """
    next_player = battle_state['players'][next_player_id]
    next_state = battle_state['player_states'][next_player_id]
    
    chat_id = battle_state['chat_id']
    
    # Process status effects
    effect_messages = bc.process_status_effects(next_player, next_state)
    
    if effect_messages:
        status_text = f"{battle_state['base_text']}\n\n"
        status_text += "\n".join(effect_messages)
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=status_text,
            parse_mode="HTML"
        )
        await asyncio.sleep(2)
        
        # Check if status effect killed player
        if next_player['current_hp'] <= 0:
            return 'ko'
    
    # Regenerate chakra based on stance
    stance = next_state['stance']
    chakra_regen = bc.STANCES[stance]['chakra_regen']
    
    next_stats = gl.get_total_stats(next_player)
    max_chakra = next_stats['max_chakra']
    
    next_player['current_chakra'] = min(
        next_player['current_chakra'] + chakra_regen,
        max_chakra
    )
    
    # Increment turn
    battle_state['turn'] = next_player_id
    battle_state['turn_number'] += 1
    
    # Check for max turns (draw)
    if battle_state['turn_number'] > bc.MAX_TURNS:
        return 'draw'
    
    return 'continue'

# ═══════════════════════════════════════
# FLEE ATTEMPT
# ═══════════════════════════════════════

async def attempt_flee(context, battle_state, fleeing_player_id, message_id):
    """
    Attempt to flee from battle.
    
    50% base chance to escape.
    Resets combo on attempt (success or fail).
    """
    fleeing_player = battle_state['players'][fleeing_player_id]
    fleeing_state = battle_state['player_states'][fleeing_player_id]
    
    other_player_id = [pid for pid in battle_state['players'].keys() if pid != fleeing_player_id][0]
    
    chat_id = battle_state['chat_id']
    
    # Show attempt
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=f"{battle_state['base_text']}\n\n<i>🏃 {fleeing_player['username']} attempts to flee...</i>",
        parse_mode="HTML"
    )
    await asyncio.sleep(1.5)
    
    # Reset combo
    fleeing_state['combo'] = 0
    
    # 50% chance
    if random.random() < 0.5:
        # Success!
        return 'fled'
    else:
        # Failed
        result_text = f"{battle_state['base_text']}\n\n"
        result_text += f"<i>❌ {fleeing_player['username']} couldn't escape!</i>"
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=result_text,
            parse_mode="HTML"
        )
        await asyncio.sleep(2)
        
        # Switch turn
        return await switch_turn(context, battle_state, other_player_id, message_id)
