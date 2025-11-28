"""
League Battle Callback Handler (Part 2)
Handles all button interactions for league battles
"""
import logging
import random
from html import escape
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database as db
import league_system as ls
import battle_enemies as be

logger = logging.getLogger(__name__)

# Import from part 1
from inline_handler_league import (
    ACTIVE_GAMES, PLAYER_JUTSUS, health_bar, chakra_bar
)


async def league_battle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles button clicks in league battle games."""
    query = update.callback_query
    
    # Try to answer query
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
    
    # START NEW BATTLE
    if action == 'start':
        game_id = parts[2]
        enemy_key = parts[3]
        
        # Check if already started
        if game_id in ACTIVE_GAMES:
            if ACTIVE_GAMES[game_id]['player_id'] != query.from_user.id:
                try:
                    await query.answer("🚫 Someone else started this battle!", show_alert=True)
                except:
                    pass
                return
        
        # Get league tier and check entry fee
        league_display = ls.get_league_display(player)
        tier_key = league_display['tier_key']
        tier_data = ls.LEAGUE_TIERS[tier_key]
        
        if player['ryo'] < tier_data['entry_fee']:
            try:
                await query.answer(f"❌ Need {tier_data['entry_fee']} Ryo!", show_alert=True)
            except:
                pass
            return
        
        # Check daily limit
        battle_check = ls.can_battle_today(player)
        if not battle_check['can_battle']:
            try:
                await query.answer("⚠️ Daily battle limit reached!", show_alert=True)
            except:
                pass
            return
        
        enemy_data = be.get_enemy_by_key(enemy_key)
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
            'log': [],
            'player_move_history': [],
            'used_heal': False,
            'tier_key': tier_key
        }
        
        # Deduct entry fee and increment battles today
        db.update_player(query.from_user.id, {
            'ryo': player['ryo'] - tier_data['entry_fee'],
            'battles_today': player.get('battles_today', 0) + 1,
            'total_battles': player.get('total_battles', 0) + 1
        })
        
        # Show jutsu selection
        await show_battle_screen(query, game_id, ACTIVE_GAMES[game_id], enemy_data, tier_data)
    
    # PLAYER MAKES A MOVE
    elif action == 'move':
        game_id = parts[2]
        jutsu_key = parts[3]
        
        game_state = ACTIVE_GAMES.get(game_id)
        if not game_state:
            try:
                await query.answer("⚠️ Game expired!", show_alert=True)
            except:
                pass
            return
        
        if game_state['player_id'] != query.from_user.id:
            try:
                await query.answer("🚫 Not your game!", show_alert=True)
            except:
                pass
            return
        
        enemy_data = be.get_enemy_by_key(game_state['enemy_key'])
        player_jutsu = PLAYER_JUTSUS.get(jutsu_key)
        tier_data = ls.LEAGUE_TIERS[game_state['tier_key']]
        
        if not player_jutsu or not enemy_data:
            return
        
        # Check chakra
        if game_state['player_chakra'] < player_jutsu['chakra']:
            try:
                await query.answer("❌ Not enough chakra!", show_alert=True)
            except:
                pass
            return
        
        # Track move for AI and heal usage
        game_state['player_move_history'].append(player_jutsu['type'])
        if player_jutsu['type'] == 'heal':
            game_state['used_heal'] = True
        
        # Player turn
        game_state['player_chakra'] -= player_jutsu['chakra']
        
        if player_jutsu.get('heal', 0) > 0:
            # Healing jutsu
            heal_amount = min(player_jutsu['heal'], 100 - game_state['player_hp'])
            game_state['player_hp'] = min(100, game_state['player_hp'] + heal_amount)
            game_state['log'].append(f"💚 You healed {heal_amount} HP!")
        else:
            # Attack jutsu
            damage = player_jutsu['power']
            
            # Type effectiveness
            if player_jutsu['type'] == enemy_data.get('weakness'):
                damage = int(damage * 1.5)
                game_state['log'].append(f"💥 SUPER EFFECTIVE! (+50% damage)")
            
            # Critical hit chance (15%)
            if random.random() < 0.15:
                damage = int(damage * 2)
                game_state['log'].append(f"⚡ CRITICAL HIT! (2x damage)")
            
            game_state['enemy_hp'] -= damage
            game_state['log'].append(f"⚔️ You used {player_jutsu['name']} - {damage} damage!")
        
        # Check if enemy defeated
        if game_state['enemy_hp'] <= 0:
            await end_game(query, game_id, game_state, enemy_data, tier_data, won=True)
            return
        
        # Enemy turn
        enemy_attack_key = be.get_enemy_ai_move(enemy_data, game_state)
        
        if enemy_attack_key and game_state['enemy_chakra'] >= enemy_data['attacks'][enemy_attack_key]['chakra']:
            enemy_attack = enemy_data['attacks'][enemy_attack_key]
            
            game_state['enemy_chakra'] -= enemy_attack['chakra']
            
            # Calculate enemy damage
            enemy_damage = enemy_attack['power']
            
            # Type effectiveness against player
            last_player_type = game_state['player_move_history'][-1] if game_state['player_move_history'] else None
            if last_player_type in enemy_attack.get('strong_vs', []):
                enemy_damage = int(enemy_damage * 1.3)
                game_state['log'].append(f"⚠️ Enemy countered your move!")
            
            game_state['player_hp'] -= enemy_damage
            game_state['log'].append(f"💢 {enemy_data['name']} used {enemy_attack['name']} - {enemy_damage} damage!")
        else:
            game_state['log'].append(f"💤 {enemy_data['name']} is out of chakra!")
        
        # Check if player defeated
        if game_state['player_hp'] <= 0:
            await end_game(query, game_id, game_state, enemy_data, tier_data, won=False)
            return
        
        # Continue battle
        game_state['turn'] += 1
        
        # Show updated battle screen
        await show_battle_screen(query, game_id, game_state, enemy_data, tier_data)
    
    # END GAME (Surrender)
    elif action == 'end':
        game_id = parts[2]
        reason = parts[3] if len(parts) > 3 else 'surrender'
        
        game_state = ACTIVE_GAMES.get(game_id)
        if not game_state:
            return
        
        if game_state['player_id'] != query.from_user.id:
            return
        
        enemy_data = be.get_enemy_by_key(game_state['enemy_key'])
        tier_data = ls.LEAGUE_TIERS[game_state['tier_key']]
        
        if reason == 'surrender':
            # Apply loss penalties
            player = db.get_player(query.from_user.id)
            league_display = ls.get_league_display(player)
            
            new_points = max(0, player.get('league_points', 0) - tier_data['point_loss'])
            
            db.update_player(query.from_user.id, {
                'league_points': new_points,
                'win_streak': 0
            })
            
            result_text = (
                f"🏳️ <b>SURRENDERED</b>\n\n"
                f"You gave up the fight against {enemy_data['name']}!\n\n"
                f"<b>Penalties:</b>\n"
                f"💸 Lost: {tier_data['entry_fee']} Ryo (entry fee)\n"
                f"📉 Lost: {tier_data['point_loss']} League Points\n"
                f"🔥 Win Streak Reset: 0\n\n"
                f"<b>New League Points:</b> {new_points}\n\n"
                f"<i>Don't give up! Train harder and come back stronger!</i>"
            )
        
            keyboard = [[InlineKeyboardButton("🎮 Battle Again", switch_inline_query_current_chat="")]]
            
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


async def show_battle_screen(query, game_id, game_state, enemy_data, tier_data):
    """Display the battle screen with jutsu options."""
    
    # Build battle log (last 3 actions)
    log_text = "\n".join(game_state['log'][-3:]) if game_state['log'] else "Battle started!"
    
    # Streak info
    player = db.get_player(game_state['player_id'])
    streak = player.get('win_streak', 0)
    streak_display = f"🔥 {streak}-Win Streak!" if streak > 0 else ""
    
    battle_text = (
        f"🎮 <b>BATTLE - Turn {game_state['turn']}</b> 🎮\n\n"
        f"👤 <b>You</b> {streak_display}\n"
        f"❤️ {health_bar(game_state['player_hp'], 100)}\n"
        f"💙 {chakra_bar(game_state['player_chakra'], 100)}\n\n"
        f"👹 <b>{enemy_data['name']}</b> {enemy_data['emoji']}\n"
        f"❤️ {health_bar(game_state['enemy_hp'], enemy_data['max_hp'])}\n"
        f"💙 {chakra_bar(game_state['enemy_chakra'], enemy_data['chakra'])}\n\n"
        f"<b>Battle Log:</b>\n{log_text}\n\n"
        f"<i>Choose your jutsu:</i>"
    )
    
    # Build jutsu keyboard
    keyboard = [
        [
            InlineKeyboardButton(f"🔥 Fire (15💙)", callback_data=f"lb_move_{game_id}_f"),
            InlineKeyboardButton(f"👊 Taijutsu (5💙)", callback_data=f"lb_move_{game_id}_t")
        ],
        [
            InlineKeyboardButton(f"🌊 Water (25💙)", callback_data=f"lb_move_{game_id}_wa"),
            InlineKeyboardButton(f"⚡ Lightning (30💙)", callback_data=f"lb_move_{game_id}_l")
        ],
        [
            InlineKeyboardButton(f"💫 Rasengan (35💙)", callback_data=f"lb_move_{game_id}_r"),
            InlineKeyboardButton(f"👁️ Genjutsu (20💙)", callback_data=f"lb_move_{game_id}_g")
        ],
        [
            InlineKeyboardButton(f"🌀 Clone (20💙)", callback_data=f"lb_move_{game_id}_sc"),
            InlineKeyboardButton(f"💚 Heal (25💙)", callback_data=f"lb_move_{game_id}_h")
        ],
        [
            InlineKeyboardButton(f"🏳️ Surrender", callback_data=f"lb_end_{game_id}_surrender")
        ]
    ]
    
    try:
        await query.edit_message_text(
            text=battle_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error updating battle screen: {e}")


async def end_game(query, game_id, game_state, enemy_data, tier_data, won):
    """End the game and show results."""
    player = db.get_player(game_state['player_id'])
    
    if won:
        # Calculate rewards
        reward_data = ls.calculate_battle_rewards(player, True, enemy_data['base_reward'])
        
        # Update player stats
        new_streak = player.get('win_streak', 0) + 1
        new_points = player.get('league_points', 0) + reward_data['points']
        
        updates = {
            'ryo': player['ryo'] + reward_data['ryo'],
            'exp': player['exp'] + reward_data['exp'],
            'total_exp': player['total_exp'] + reward_data['exp'],
            'league_points': new_points,
            'win_streak': new_streak
        }
        
        # Add bonus items to inventory
        if reward_data['bonus_items']:
            inventory = player.get('inventory') or []
            inventory.extend(reward_data['bonus_items'])
            updates['inventory'] = inventory
        
        db.update_player(game_state['player_id'], updates)
        
        # Check for mission completion
        mission_results = []
        
        # Win 3 battles mission
        missions_data = ls.get_daily_missions(player)
        win_mission = ls.update_mission_progress(player, 'win_3', 1)
        if win_mission['completed']:
            mission_results.append(f"✅ Mission Complete: {win_mission['mission']['description']}")
        
        # Win without heal mission
        if not game_state['used_heal']:
            no_heal_mission = ls.update_mission_progress(player, 'win_no_heal', 1)
            if no_heal_mission['completed']:
                mission_results.append(f"✅ Mission Complete: {no_heal_mission['mission']['description']}")
        
        # Perfect win mission (80+ HP)
        if game_state['player_hp'] >= 80:
            perfect_mission = ls.update_mission_progress(player, 'perfect_win', 1)
            if perfect_mission['completed']:
                mission_results.append(f"✅ Mission Complete: {perfect_mission['mission']['description']}")
        
        # Win streak mission
        if new_streak >= 3:
            streak_mission = ls.update_mission_progress(player, 'win_streak_3', 1)
            if streak_mission['completed']:
                mission_results.append(f"✅ Mission Complete: {streak_mission['mission']['description']}")
        
        # Build result text
        streak_info = ""
        if reward_data['streak_bonus']:
            bonus = reward_data['streak_bonus']
            streak_info = f"\n🔥 <b>{bonus['name']}</b> {bonus['emoji']}\n   Ryo Bonus: +{int((reward_data['streak_multiplier']-1)*100)}%"
        
        mission_text = "\n" + "\n".join(mission_results) if mission_results else ""
        
        bonus_items_text = ""
        if reward_data['bonus_items']:
            bonus_items_text = f"\n🎁 Bonus Items: {', '.join(reward_data['bonus_items'])}"
        
        # Check league promotion
        new_league = ls.get_league_display({'league_points': new_points})
        old_league = ls.get_league_display(player)
        promotion_text = ""
        if new_league['tier_key'] != old_league['tier_key']:
            promotion_text = f"\n\n🎊 <b>LEAGUE PROMOTION!</b> 🎊\n{old_league['emoji']} {old_league['tier_name']} → {new_league['emoji']} {new_league['tier_name']}"
        
        result_text = (
            f"🏆 <b>VICTORY!</b> 🏆\n\n"
            f"You defeated <b>{enemy_data['name']}</b>!\n\n"
            f"<b>Battle Summary:</b>\n"
            f"⚔️ Turns: {game_state['turn']}\n"
            f"❤️ HP Remaining: {game_state['player_hp']}/100\n"
            f"💙 Chakra Remaining: {game_state['player_chakra']}/100\n\n"
            f"<b>Rewards:</b>\n"
            f"💰 Ryo: +{reward_data['ryo']:,}"
            f" (Base: {reward_data['base_ryo']:,})\n"
            f"✨ EXP: +{reward_data['exp']}\n"
            f"⭐ League Points: +{reward_data['points']} ({new_points} total)\n"
            f"🔥 Win Streak: {new_streak}"
            f"{streak_info}"
            f"{bonus_items_text}"
            f"{mission_text}"
            f"{promotion_text}"
        )
    else:
        # Loss
        new_points = max(0, player.get('league_points', 0) - tier_data['point_loss'])
        
        db.update_player(game_state['player_id'], {
            'league_points': new_points,
            'win_streak': 0
        })
        
        result_text = (
            f"💔 <b>DEFEATED!</b> 💔\n\n"
            f"You were defeated by <b>{enemy_data['name']}</b>!\n\n"
            f"<b>Battle Summary:</b>\n"
            f"⚔️ Turns Survived: {game_state['turn']}\n"
            f"👹 Enemy HP Remaining: {game_state['enemy_hp']}/{enemy_data['max_hp']}\n\n"
            f"<b>Penalties:</b>\n"
            f"💸 Lost: {tier_data['entry_fee']} Ryo (entry fee)\n"
            f"📉 Lost: {tier_data['point_loss']} League Points\n"
            f"🔥 Win Streak Reset: 0\n\n"
            f"<b>New League Points:</b> {new_points}\n\n"
            f"<i>Train harder and try again!</i>"
        )
    
    keyboard = [[InlineKeyboardButton("🎮 Battle Again", switch_inline_query_current_chat="")]]
    
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
