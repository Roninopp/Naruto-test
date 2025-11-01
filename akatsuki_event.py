import logging
import json
import sqlite3
import datetime
import asyncio
import random
import time 

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatType
from collections import Counter 

import database as db
import game_logic as gl
import animations as anim # We will reuse our animations

logger = logging.getLogger(__name__)

# --- Constants ---
KUNAI_EMOJI = "\U0001FA9A"
BOMB_EMOJI = "💥"
KUNAI_COOLDOWN_SECONDS = 30
BOMB_COOLDOWN_SECONDS = 120 # 2 minutes
JUTSU_COOLDOWN_SECONDS = 300 # 5 minutes
FLEE_COOLDOWN_SECONDS = 60
AKATSUKI_REWARDS = {'exp': 110, 'ryo': 180}
PLAYER_SLOTS = ['player_1_id', 'player_2_id', 'player_3_id']

# --- Helper: Get Battle Text ---
def get_akatsuki_battle_text(battle_state, enemy_info, players_list):
    """Generates the text for the interactive battle message."""
    
    text = (
        f"👹 **{enemy_info['name']}** Attacks! 👹\n"
        f"<i>{enemy_info['desc']}</i>\n\n"
        f"<b>HP:</b> {gl.health_bar(battle_state['enemy_hp'], enemy_info['max_hp'])}\n\n"
        f"<b>⚔️ Joined Players (Up to 3) ⚔️</b>\n"
    )
    
    turn_player_id = battle_state.get('turn_player_id')
    turn_player_name = "AI" # Default to AI
    
    for i, slot in enumerate(PLAYER_SLOTS):
        player_id = battle_state[slot]
        if player_id:
            player_data = db.get_player(player_id) # Get fresh data
            if player_data:
                player_total_stats = gl.get_total_stats(player_data)
                text += f" {i+1}. {player_data['username']} [Lvl {player_data['level']}] (HP: {player_data['current_hp']}/{player_total_stats['max_hp']})\n"
                if player_id == turn_player_id:
                    turn_player_name = player_data['username']
            else:
                 text += f" {i+1}. <i>Unknown Player</i>\n"
        else:
             text += f" {i+1}. <i>(Waiting...)</i>\n"
             
    if not turn_player_id: # If turn_player_id is None, it's still in the "joining" phase
         text += "\nWaiting for 3 players to join..."
    elif turn_player_id == 'ai_turn':
         text += f"\n<b>Turn: {enemy_info['name']}</b>\n<i>The enemy is preparing an attack...</i>"
    else:
         text += f"\n<b>Turn: {turn_player_name}</b>\nChoose your action:"
         
    return text

# --- Helper: Send/Edit Battle Message ---
async def send_or_edit_akatsuki_message(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id=None, text=None, photo_url=None, reply_markup=None):
    """A dedicated helper to send or edit the Akatsuki event message."""
    try:
        if message_id: # Edit existing message
            if photo_url: # Edit media (change photo + caption)
                await context.bot.edit_message_media(
                    chat_id=chat_id, message_id=message_id,
                    media=InputMediaPhoto(media=photo_url, caption=text, parse_mode="HTML"),
                    reply_markup=reply_markup
                )
            else: # Edit caption only
                await context.bot.edit_message_caption(
                    chat_id=chat_id, message_id=message_id,
                    caption=text, reply_markup=reply_markup, parse_mode="HTML"
                )
        else: # Send new message
            await context.bot.send_photo(
                chat_id=chat_id, photo=photo_url,
                caption=text, reply_markup=reply_markup, parse_mode="HTML"
            )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error sending/editing Akatsuki message for chat {chat_id}: {e}")
            # If message was deleted, we lose it, but job will spawn a new one later
            if "Message to edit not found" in str(e):
                 db.clear_akatsuki_fight(chat_id) # Clean up DB if message is gone


# --- Admin Command (On/Off) ---
async def toggle_auto_fight_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin Only) Toggles auto-fights on or off for this chat."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("This command only works in groups.")
        return

    # 1. Check if user is admin
    try:
        chat_admins = await context.bot.get_chat_administrators(chat.id)
        user_ids = [admin.user.id for admin in chat_admins]
        if user.id not in user_ids:
            await update.message.reply_text("Only group admins can use this command.")
            return
    except Exception as e:
        logger.error(f"Error checking admin status in chat {chat.id}: {e}")
        await update.message.reply_text("An error occurred. I might not have permission to see group admins.")
        return

    # 2. Get current status and toggle
    # Determine the new status based on the command used
    command = update.message.text.split(' ')[0].split('@')[0] # /auto_fight_off
    if command == "/auto_fight_off":
        new_status = 0 # Off
    else: # /auto_fight_on
        new_status = 1 # On
    
    db.toggle_auto_events(chat.id, new_status)
    
    if new_status == 1:
        await update.message.reply_text("✅ Akatsuki Ambushes have been **ENABLED** for this group.")
    else:
        await update.message.reply_text("❌ Akatsuki Ambushes have been **DISABLED** for this group.")

# --- Passive Group Registration ---
async def passive_group_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passively registers any group the bot is in for events."""
    if update.effective_chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        chat_id = update.effective_chat.id
        db.register_event_chat(chat_id) 


# --- Event Spawning ---
async def spawn_akatsuki_event(context: ContextTypes.DEFAULT_TYPE):
    """Job function to send an Akatsuki ambush to all enabled chats."""
    logger.info("AKATSUKI JOB: Running spawn check...")
    
    enabled_chat_ids = db.get_all_event_chats()
    if not enabled_chat_ids:
        logger.info("AKATSUKI JOB: No chats found for auto-events. Skipping.")
        return

    enemy_key = 'sasuke_clone' # We'll start with this one
    enemy_info = gl.AKATSUKI_ENEMIES.get(enemy_key)
    if not enemy_info:
        logger.error("AKATSUKI JOB: Cannot find enemy 'sasuke_clone' in game_logic.py"); return
        
    funny_text = "<i>Psst... If I'm coming to attack too often, an admin can use /auto_fight_off to give you a break!</i>"
    message_text = (
        f"**The Akatsuki Organization Is Coming To Destroy Your Village!**\n\n"
        f"A rogue ninja, {enemy_info['name']}, blocks the path! Work together to protect your village!\n\n"
        f"**Up to 3 ninjas** can join this fight.\n"
        f"{funny_text}"
    )
    
    button = InlineKeyboardButton("⚔️ Protect Village!", callback_data="akatsuki_join")
    reply_markup = InlineKeyboardMarkup([[button]])

    for chat_id in enabled_chat_ids:
        # Check if a fight is already active in this chat
        if db.get_akatsuki_fight(chat_id):
            logger.info(f"AKATSUKI JOB: Fight already active in chat {chat_id}. Skipping.")
            continue
            
        try:
            message = await context.bot.send_photo(
                chat_id=chat_id,
                photo=enemy_info['image'],
                caption=message_text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            # Create the fight in the DB
            db.create_akatsuki_fight(message.message_id, chat_id, enemy_key)
            logger.info(f"AKATSUKI JOB: Sent ambush {message.message_id} to chat {chat_id}")
            await asyncio.sleep(1) # Sleep 1 sec to avoid hitting rate limits
            
        except Exception as e:
            logger.error(f"AKATSUKI JOB: Failed to send ambush to chat {chat_id}: {e}")
            if "forbidden" in str(e).lower() or "bot was kicked" in str(e).lower():
                logger.warning(f"AKATSUKI JOB: Bot forbidden in chat {chat_id}. Disabling events.")
                db.toggle_auto_events(chat_id, 0)

    logger.info("AKATSUKI JOB: Finished spawn check.")

# --- Battle Callbacks ---

async def akatsuki_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles when a player clicks the 'Protect Village!' button."""
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    player = db.get_player(user.id)
    if not player:
        await query.answer("You must /start your journey first to join the fight!", show_alert=True)
        return

    # Try to join the fight
    join_result = db.add_player_to_fight(message_id, chat_id, user.id)
    
    if join_result['status'] == 'failed':
        await query.answer("This fight is no longer active.", show_alert=True)
        return
        
    if join_result['status'] == 'full':
        await query.answer("This fight is already full! (Max 3 players).", show_alert=True)
        return
        
    if join_result['status'] == 'already_joined':
        await query.answer("You are already in this fight!", show_alert=True)
        return
        
    # --- Status is 'joined' or 'ready' ---
    await query.answer("You have joined the fight!")
    
    battle_state = db.get_akatsuki_fight(chat_id, message_id)
    enemy_info = gl.AKATSUKI_ENEMIES.get(battle_state['enemy_name'])
    
    if join_result['status'] == 'ready':
        # This was the 3rd player! Start the battle
        db.set_akatsuki_turn(message_id, battle_state['player_1_id']) # Set turn to player 1
        battle_state['turn_player_id'] = battle_state['player_1_id'] # Update local state
        
        text = get_akatsuki_battle_text(battle_state, enemy_info, []) # Pass empty player list for now
        
        # New battle buttons
        keyboard = [
            [InlineKeyboardButton(f"{KUNAI_EMOJI} Throw Kunai", callback_data=f"akatsuki_action_throw_kunai"),
             InlineKeyboardButton(f"{BOMB_EMOJI} Paper Bomb", callback_data=f"akatsuki_action_paper_bomb")],
            [InlineKeyboardButton("🌀 Use Jutsu", callback_data="akatsuki_action_jutsu"),
             InlineKeyboardButton("🏃 Flee", callback_data="akatsuki_action_flee")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await send_or_edit_akatsuki_message(context, chat_id, message_id, text, None, reply_markup)
        
    else:
        # Just update the player count
        text = get_akatsuki_battle_text(battle_state, enemy_info, [])
        reply_markup = query.message.reply_markup # Keep the same "Protect Village" button
        await send_or_edit_akatsuki_message(context, chat_id, message_id, text, None, reply_markup)


async def akatsuki_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the custom attack buttons: Kunai, Bomb, Jutsu, Flee"""
    query = update.callback_query
    
    action = "_".join(query.data.split('_')[2:]) # throw_kunai, paper_bomb, jutsu, flee
    user = query.from_user
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    
    battle_state = db.get_akatsuki_fight(chat_id, message_id)
    if not battle_state:
        await query.answer("This fight is no longer active.", show_alert=True)
        try: await query.edit_message_reply_markup(reply_markup=None)
        except: pass
        return
        
    # Check if it's the player's turn
    if battle_state['turn_player_id'] != user.id:
        await query.answer("It's not your turn!", show_alert=True)
        return
        
    player_data = db.get_player(user.id)
    if not player_data: await query.answer("Cannot find your player data!", show_alert=True); return
    
    # Check if fainted
    if player_data['current_hp'] <= 1:
        await query.answer("You are fainted and cannot move!", show_alert=True)
        # TODO: Auto-skip turn?
        return
        
    # (We will add cooldown checks here in the future)
    
    enemy_info = gl.AKATSUKI_ENEMIES.get(battle_state['enemy_name'])
    
    # --- Handle Flee ---
    if action == "flee":
        await query.answer() # Answer silently
        await query.edit_message_caption(caption=f"🏃 {player_data['username']} fled the battle!")
        # TODO: Handle player leaving the fight, maybe replace them?
        # For now, just end the fight if all players flee?
        # This is complex, let's skip flee logic for Step 14
        return

    # --- Handle Attacks ---
    
    # Setup animation state
    battle_state_for_anim = {
        'chat_id': chat_id, 'message_id': message_id,
        'base_text': get_akatsuki_battle_text(battle_state, enemy_info, []).split("\n\nTurn:")[0],
        'players': {user.id: player_data}, 'turn': user.id
    }
    
    # Disable buttons
    await send_or_edit_akatsuki_message(context, chat_id, message_id, f"{battle_state_for_anim['base_text']}\n\n<i>Turn: {player_data['username']}</i>\nProcessing attack...", None, None)
    
    player_total_stats = gl.get_total_stats(player_data)
    final_damage = 0
    is_crit = False
    
    if action == "throw_kunai":
        damage_dealt = random.randint(8, 12) + player_data['level'] 
        is_crit = random.random() < 0.08 
        final_damage = int(damage_dealt * (1.8 if is_crit else 1.0))
        await anim.animate_throw_kunai(context, battle_state_for_anim, player_data, enemy_info, final_damage, is_crit)
        
    elif action == "paper_bomb":
        damage_dealt = (random.randint(15, 25) + player_data['level'] * 2)
        is_crit = random.random() < 0.12 # 12% crit
        final_damage = int(damage_dealt * (2.0 if is_crit else 1.0))
        await anim.animate_paper_bomb(context, battle_state_for_anim, player_data, enemy_info, final_damage, is_crit)
        
    elif action == "jutsu":
        # --- Pop-up Logic ---
        if player_data['level'] < gl.JUTSU_LIBRARY['fireball']['level_required']: 
             await query.answer("You need Level 5+ to use Jutsus!", show_alert=True)
             await send_or_edit_akatsuki_message(context, chat_id, message_id, get_akatsuki_battle_text(battle_state, enemy_info, []), None, query.message.reply_markup) # Reshow menu
             return
        try: known_jutsus_list = json.loads(player_data['known_jutsus'])
        except: known_jutsus_list = []
        if not known_jutsus_list:
            await query.answer("You don't know any Jutsus! Use /combine.", show_alert=True)
            await send_or_edit_akatsuki_message(context, chat_id, message_id, get_akatsuki_battle_text(battle_state, enemy_info, []), None, query.message.reply_markup) # Reshow menu
            return
        # --- End Pop-up Logic ---

        # Show Jutsu selection menu
        keyboard = []; available_jutsus = 0
        for jutsu_key in known_jutsus_list:
             jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_key)
             if jutsu_info:
                 if player_data['current_chakra'] >= jutsu_info['chakra_cost']:
                     button_text = f"{jutsu_info['name']} ({jutsu_info['chakra_cost']} Chakra)"
                     keyboard.append([InlineKeyboardButton(button_text, callback_data=f"akatsuki_jutsu_{jutsu_key}")])
                     available_jutsus += 1
                 else:
                     button_text = f"🚫 {jutsu_info['name']} ({jutsu_info['chakra_cost']} Chakra)"
                     keyboard.append([InlineKeyboardButton(button_text, callback_data="akatsuki_nochakra")])
        if available_jutsus == 0:
             await query.answer("Not enough Chakra for any Jutsu!", show_alert=True)
             await send_or_edit_akatsuki_message(context, chat_id, message_id, get_akatsuki_battle_text(battle_state, enemy_info, []), None, query.message.reply_markup) # Reshow menu
             return
        
        keyboard.append([InlineKeyboardButton("Cancel", callback_data="akatsuki_jutsu_cancel")])
        await send_or_edit_akatsuki_message(context, chat_id, message_id, f"{battle_state_for_anim['base_text']}\n\nSelect a Jutsu:", None, InlineKeyboardMarkup(keyboard))
        return # Jutsu selection happens in akatsuki_jutsu_callback
        
    # --- Update DB after Kunai or Bomb ---
    new_enemy_hp = max(0, battle_state['enemy_hp'] - final_damage)
    db.update_akatsuki_fight_hp(message_id, new_enemy_hp)
    db.add_player_damage_to_fight(message_id, user.id, final_damage) # Need this DB func
    
    if new_enemy_hp == 0:
        await end_akatsuki_fight(context, chat_id, message_id, battle_state, enemy_info, success=True)
    else:
        # Move to next player's turn
        await _next_turn(context, chat_id, message_id, battle_state, enemy_info)


async def akatsuki_jutsu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the selection of a specific Jutsu to use against the Akatsuki AI."""
    query = update.callback_query
    
    user = query.from_user
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    
    battle_state = db.get_akatsuki_fight(chat_id, message_id)
    if not battle_state or battle_state['turn_player_id'] != user.id:
        await query.answer("It's not your turn!", show_alert=True)
        return
        
    player_data = db.get_player(user.id)
    if not player_data: await query.answer("Cannot find your player data!", show_alert=True); return
    
    parts = query.data.split('_'); jutsu_key = "_".join(parts[2:]) 

    if jutsu_key == "cancel":
        await query.answer() 
        enemy_info = gl.AKATSUKI_ENEMIES.get(battle_state['enemy_name'])
        # Re-show the main battle menu
        text = get_akatsuki_battle_text(battle_state, enemy_info, [])
        keyboard = [
            [InlineKeyboardButton(f"{KUNAI_EMOJI} Throw Kunai", callback_data=f"akatsuki_action_throw_kunai"),
             InlineKeyboardButton(f"{BOMB_EMOJI} Paper Bomb", callback_data=f"akatsuki_action_paper_bomb")],
            [InlineKeyboardButton("🌀 Use Jutsu", callback_data="akatsuki_action_jutsu"),
             InlineKeyboardButton("🏃 Flee", callback_data="akatsuki_action_flee")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_or_edit_akatsuki_message(context, chat_id, message_id, text, None, reply_markup)
        return
        
    if jutsu_key == "nochakra":
        await query.answer("You don't have enough Chakra for that Jutsu!", show_alert=True); return 

    jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_key)
    if not jutsu_info: await query.answer("Error: Invalid Jutsu selected.", show_alert=True); return

    if player_data['current_chakra'] < jutsu_info['chakra_cost']: await query.answer("Not enough Chakra!", show_alert=True); return
    
    # --- Perform Jutsu Attack ---
    await query.answer() # Answer silently
    
    enemy_info = gl.AKATSUKI_ENEMIES.get(battle_state['enemy_name'])
    battle_state_for_anim = {
        'chat_id': chat_id, 'message_id': message_id,
        'base_text': get_akatsuki_battle_text(battle_state, enemy_info, []).split("\n\nTurn:")[0],
        'players': {user.id: player_data}, 'turn': user.id
    }
    await send_or_edit_akatsuki_message(context, chat_id, message_id, f"{battle_state_for_anim['base_text']}\n\n<i>Processing Jutsu...</i>", None, None)
    
    player_total_stats = gl.get_total_stats(player_data) 
    base_damage = jutsu_info['power'] + (player_total_stats['intelligence'] * 2.5)
    damage_dealt = random.randint(int(base_damage * 0.9), int(base_damage * 1.1))
    is_crit = random.random() < 0.15
    final_damage = int(damage_dealt * (2.5 if is_crit else 1.0))
    damage_data = (final_damage, is_crit, False) # (damage, is_crit, is_super_eff)
    
    # Apply cost
    player_data['current_chakra'] -= jutsu_info['chakra_cost']
    db.update_player(user.id, {'current_chakra': player_data['current_chakra']}) # Save chakra change
    
    # Play animation
    enemy_sim = {'username': enemy_info['name'], 'village': 'none'} 
    jutsu_info_for_anim = {'name': jutsu_info['name'], 'signs': jutsu_info['signs'], 'element': jutsu_info['element']}
    await anim.battle_animation_flow(context, battle_state_for_anim, player_data, enemy_sim, jutsu_info_for_anim, damage_data)

    # Apply damage
    new_enemy_hp = max(0, battle_state['enemy_hp'] - final_damage)
    db.update_akatsuki_fight_hp(message_id, new_enemy_hp)
    db.add_player_damage_to_fight(message_id, user.id, final_damage)
    
    if new_enemy_hp == 0:
        await end_akatsuki_fight(context, chat_id, message_id, battle_state, enemy_info, success=True)
    else:
        # Move to next player's turn
        await _next_turn(context, chat_id, message_id, battle_state, enemy_info)


# --- Helper: AI Turn Logic ---
async def _run_ai_turn(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id, battle_state, enemy_info):
    """The AI (Sasuke) takes its turn."""
    
    logger.info(f"AKATSUKI EVENT: AI Turn in chat {chat_id}")
    
    # Find living players to target
    living_players = []
    for slot in PLAYER_SLOTS:
        player_id = battle_state[slot]
        if player_id:
            player_data = db.get_player(player_id)
            if player_data and player_data['current_hp'] > 1:
                living_players.append(player_data)
                
    if not living_players:
        logger.info(f"AKATSUKI EVENT: All players fainted in chat {chat_id}. AI wins.")
        await end_akatsuki_fight(context, chat_id, message_id, battle_state, enemy_info, success=False)
        return
        
    # Choose a random target
    target_player = random.choice(living_players)
    target_player_total_stats = gl.get_total_stats(target_player)
    
    # AI Logic (Simple: 100% Taijutsu for now)
    # We can add AI jutsus later
    ai_strength = enemy_info.get('strength', 20)
    ai_damage = int((ai_strength * 0.8) + (enemy_info['level'] * 0.5)) # Simple AI damage calc
    ai_damage = random.randint(int(ai_damage * 0.8), int(ai_damage * 1.2)) # +/- 20%
    is_crit = random.random() < 0.1 # 10% crit
    if is_crit: ai_damage = int(ai_damage * 1.8)
    
    # Apply damage to player
    new_player_hp = max(0, target_player['current_hp'] - ai_damage)
    
    # Animate the AI attack
    battle_state_for_anim = {
        'chat_id': chat_id, 'message_id': message_id,
        'base_text': get_akatsuki_battle_text(battle_state, enemy_info, []).split("\n\nTurn:")[0],
    }
    enemy_attacker_sim = {'username': enemy_info['name']}
    await anim.animate_taijutsu(context, battle_state_for_anim, enemy_attacker_sim, target_player, ai_damage, is_crit)
    
    # Save player's new HP
    if new_player_hp == 0: new_player_hp = 1 # Fainted
    db.update_player(target_player['user_id'], {'current_hp': new_player_hp})
    
    # Check if all players are now fainted
    all_fainted = True
    for p_id in [battle_state[s] for s in PLAYER_SLOTS if battle_state[s]]:
        p_data = db.get_player(p_id)
        if p_data['current_hp'] > 1:
            all_fainted = False
            break
            
    if all_fainted:
        logger.info(f"AKATSUKI EVENT: All players fainted after AI turn in chat {chat_id}.")
        await end_akatsuki_fight(context, chat_id, message_id, battle_state, enemy_info, success=False)
    else:
        # Move to Player 1's turn
        await _next_turn(context, chat_id, message_id, battle_state, enemy_info, next_turn_id=battle_state['player_1_id'])


# --- Helper: Turn Management ---
async def _next_turn(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id, battle_state, enemy_info, next_turn_id=None):
    """Passes the turn to the next player or the AI."""
    
    if next_turn_id: # Used by AI to force turn back to Player 1
        db.set_akatsuki_turn(message_id, next_turn_id)
        battle_state['turn_player_id'] = next_turn_id
        text = get_akatsuki_battle_text(battle_state, enemy_info, [])
        keyboard = [
            [InlineKeyboardButton(f"{KUNAI_EMOJI} Throw Kunai", callback_data=f"akatsuki_action_throw_kunai"),
             InlineKeyboardButton(f"{BOMB_EMOJI} Paper Bomb", callback_data=f"akatsuki_action_paper_bomb")],
            [InlineKeyboardButton("🌀 Use Jutsu", callback_data="akatsuki_action_jutsu"),
             InlineKeyboardButton("🏃 Flee", callback_data="akatsuki_action_flee")]
        ]
        await send_or_edit_akatsuki_message(context, chat_id, message_id, text, None, InlineKeyboardMarkup(keyboard))
        return

    # Find current player's index
    current_turn_id = battle_state['turn_player_id']
    try:
        current_index = [battle_state[s] for s in PLAYER_SLOTS].index(current_turn_id)
    except ValueError:
        current_index = -1 # Should not happen

    if current_index == 0: # Was Player 1's turn
        next_turn_id = battle_state['player_2_id']
    elif current_index == 1: # Was Player 2's turn
        next_turn_id = battle_state['player_3_id']
    else: # Was Player 3's turn
        next_turn_id = 'ai_turn'
        
    # Update DB
    db.set_akatsuki_turn(message_id, next_turn_id)
    battle_state['turn_player_id'] = next_turn_id # Update local state
    
    # Show message
    text = get_akatsuki_battle_text(battle_state, enemy_info, [])
    
    if next_turn_id == 'ai_turn':
        # Show AI thinking message (no buttons)
        await send_or_edit_akatsuki_message(context, chat_id, message_id, text, None, None)
        await asyncio.sleep(2) # Pause
        # Run AI turn logic
        await _run_ai_turn(context, chat_id, message_id, battle_state, enemy_info)
    else:
        # It's a player's turn, show buttons
        keyboard = [
            [InlineKeyboardButton(f"{KUNAI_EMOJI} Throw Kunai", callback_data=f"akatsuki_action_throw_kunai"),
             InlineKeyboardButton(f"{BOMB_EMOJI} Paper Bomb", callback_data=f"akatsuki_action_paper_bomb")],
            [InlineKeyboardButton("🌀 Use Jutsu", callback_data="akatsuki_action_jutsu"),
             InlineKeyboardButton("🏃 Flee", callback_data="akatsuki_action_flee")]
        ]
        await send_or_edit_akatsuki_message(context, chat_id, message_id, text, None, InlineKeyboardMarkup(keyboard))


# --- Helper: End Fight ---
async def end_akatsuki_fight(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id, battle_state, enemy_info, success=True):
    """Ends the fight, gives rewards, and cleans up."""
    
    logger.info(f"AKATSUKI EVENT: Fight ended in chat {chat_id}. Success: {success}")
    
    # 1. Edit message to final state
    if success:
        final_text = (
            f"🏆 **YOU PROTECTED THE VILLAGE!** 🏆\n\n"
            f"The {enemy_info['name']} has been defeated!\n\n"
            f"Rewards: **+{AKATSUKI_REWARDS['exp']} EXP** and **+{AKATSUKI_REWARDS['ryo']} Ryo** have been given to all participants!"
        )
    else: # Players lost
        final_text = (
            f"💔 **MISSION FAILED!** 💔\n\n"
            f"The {enemy_info['name']} has defeated your team. The village is in peril..."
        )
    await send_or_edit_akatsuki_message(context, chat_id, message_id, final_text, None, None)

    # 2. Give rewards (if success)
    if success:
        player_ids = [battle_state[s] for s in PLAYER_SLOTS if battle_state[s]]
        for user_id in player_ids:
            player = db.get_player(user_id)
            if player:
                temp_player_data = dict(player)
                temp_player_data['ryo'] += AKATSUKI_REWARDS['ryo']
                temp_player_data['exp'] += AKATSUKI_REWARDS['exp']
                temp_player_data['total_exp'] += AKATSUKI_REWARDS['exp']
                
                final_player_data, leveled_up, messages = gl.check_for_level_up(temp_player_data)
                db.update_player(user_id, final_player_data)
                
                # Send level up message if it happened
                if leveled_up:
                    await context.bot.send_message(chat_id=chat_id, text=f"@{player['username']}\n" + "\n".join(messages))

    # 3. Clean up database
    db.clear_akatsuki_fight(chat_id)
    # (We also need to clear player cooldowns, but we haven't added them yet)
