import logging
import json
import sqlite3
import datetime
import asyncio
import random
import time 

# --- FIX: IMPORT TIMEZONE ---
from datetime import timezone
# --- END FIX ---

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatType
from collections import Counter 

import database as db
import game_logic as gl
import animations as anim 

logger = logging.getLogger(__name__)

# --- Constants ---
KUNAI_EMOJI = "\U0001FA9A"
BOMB_EMOJI = "💥"
KUNAI_COOLDOWN_SECONDS = 30 # Reduced cooldown for more action
BOMB_COOLDOWN_SECONDS = 120 # 2 minutes
JUTSU_COOLDOWN_SECONDS = 300 # 5 minutes
FLEE_COOLDOWN_SECONDS = 60
AKATSUKI_REWARDS = {'exp': 110, 'ryo': 180}
PLAYER_SLOTS = ['player_1_id', 'player_2_id', 'player_3_id']

# --- THIS IS THE FIX (3 hours) ---
# 180 minutes = 3 hours
EVENT_TIMEOUT_MINUTES = 180
# --- END OF FIX ---

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
    
    # Get fresh player data for all joined players
    joined_players_data = {}
    for slot in PLAYER_SLOTS:
        player_id = battle_state[slot]
        if player_id:
            player_data = db.get_player(player_id) # Get fresh data
            if player_data:
                joined_players_data[player_id] = player_data

    # Display player info
    for i, slot in enumerate(PLAYER_SLOTS):
        player_id = battle_state[slot]
        if player_id and player_id in joined_players_data:
            player_data = joined_players_data[player_id]
            player_total_stats = gl.get_total_stats(player_data)
            # Check if fainted
            hp_display = f"(HP: {player_data['current_hp']}/{player_total_stats['max_hp']})"
            if player_data['current_hp'] <= 1:
                hp_display = "<b>(Fainted)</b>"
                
            text += f" {i+1}. {player_data['username']} [Lvl {player_data['level']}] {hp_display}\n"
            if str(player_id) == str(turn_player_id): # Compare as strings
                turn_player_name = player_data['username']
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
            # We will always edit the caption
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
            if "Message to edit not found" in str(e) or "message to edit not found" in str(e):
                 db.clear_akatsuki_fight(chat_id) # Clean up DB if message is gone
            elif "message must have media" in str(e):
                 # Fallback: Original message was text? Try editing text
                 try:
                     await context.bot.edit_message_text(
                         chat_id=chat_id, message_id=message_id,
                         text=text, reply_markup=reply_markup, parse_mode="HTML"
                     )
                 except Exception as e2:
                     logger.error(f"Fallback edit_message_text also failed: {e2}")
                     # if chat_id in ACTIVE_BOSS_MESSAGES: del ACTIVE_BOSS_MESSAGES[chat_id] # This var isn't in this file
                     db.clear_akatsuki_fight(chat_id) # Clean up DB


# --- Admin Command (On/Off) ---
async def toggle_auto_fight_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin Only) Toggles auto-fights on or off for this chat."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("This command only works in groups.")
        return

    # Check if user is admin
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

    # Get current status and toggle
    command = update.message.text.split(' ')[0].split('@')[0].lower() # /auto_fight_off or /auto_ryo_off
    if command in ["/auto_fight_off", "/auto_ryo_off"]:
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

    # --- (Get all chats - this logic is correct from last time) ---
    boss_chats = set(db.get_all_boss_chats())
    event_settings = db.get_event_settings_dict()
    all_known_chats = boss_chats.union(set(event_settings.keys()))
    
    enabled_chat_ids = []
    for chat_id in all_known_chats:
        status = event_settings.get(chat_id)
        if status == 0:
            logger.info(f"AKATSUKI JOB: Chat {chat_id} has events disabled. Skipping.")
            continue
        else:
            enabled_chat_ids.append(chat_id)
    
    if not enabled_chat_ids:
        logger.info("AKATSUKI JOB: No chats found for auto-events. Skipping.")
        return

    # --- (Get enemy info - this is also correct) ---
    enemy_key = 'sasuke_clone' 
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

    # --- MODIFIED LOOP WITH TIMEZONE FIX ---
    now = datetime.datetime.now(timezone.utc) # Get current time in UTC
    timeout_duration = datetime.timedelta(minutes=EVENT_TIMEOUT_MINUTES)

    for chat_id in enabled_chat_ids:
        battle_state = db.get_akatsuki_fight(chat_id) # Check if fight active in this chat

        if battle_state:
            # --- NEW TIMEOUT LOGIC ---
            try:
                # DB stores as 'YYYY-MM-DD HH:MM:SS' which is UTC
                created_at_str = battle_state['created_at']
                # Parse the string into a naive datetime object
                created_at_time_naive = datetime.datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
                
                # Make the naive datetime object "aware" that it is in UTC
                created_at_time_aware = created_at_time_naive.replace(tzinfo=timezone.utc) 
                
                # --- THIS IS THE FIX: Changed > to >= ---
                if (now - created_at_time_aware) >= timeout_duration:
                # --- END OF FIX ---
                    logger.warning(f"AKATSUKI JOB: Fight in chat {chat_id} timed out. Clearing.")
                    try:
                        # Try to send a message
                        await context.bot.send_message(chat_id, "The Akatsuki member got bored of waiting and left...")
                    except Exception as e:
                        logger.error(f"AKATSUKI JOB: Failed to send timeout message to chat {chat_id}: {e}")
                    
                    db.clear_akatsuki_fight(chat_id) # Clear the old fight
                    battle_state = None # Set to None so a new fight can be spawned
                
                else:
                    # Fight is active but not timed out
                    logger.info(f"AKATSUKI JOB: Fight active in chat {chat_id} (not timed out). Skipping.")
                    continue # Skip to the next chat_id

            except Exception as e:
                logger.error(f"AKATSUKI JOB: Error checking timestamp for chat {chat_id}: {e}. Clearing fight.")
                db.clear_akatsuki_fight(chat_id) # Clear broken fight
                battle_state = None
            # --- END NEW TIMEOUT LOGIC ---

        if not battle_state:
            # Spawn a new fight
            try:
                message = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=enemy_info['image'],
                    caption=message_text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
                db.create_akatsuki_fight(message.message_id, chat_id, enemy_key)
                logger.info(f"AKATSUKI JOB: Sent ambush {message.message_id} to chat {chat_id}")
                await asyncio.sleep(1) 
                
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
        await query.answer("You must be a registered ninja to join this fight! Use /start first.", show_alert=True)
        return

    # Try to join the fight
    join_result = db.add_player_to_fight(message_id, chat_id, user.id)
    battle_state = db.get_akatsuki_fight(chat_id, message_id) # Get state *after* joining
    
    if not battle_state: # Fight was already cleared or failed
        await query.answer("This fight is no longer active.", show_alert=True)
        try: await query.edit_message_reply_markup(reply_markup=None)
        except: pass
        return

    if join_result['status'] == 'full':
        await query.answer("This fight is already full! (Max 3 players).", show_alert=True)
        return
        
    if join_result['status'] == 'already_joined':
        await query.answer("You are already in this fight!", show_alert=True)
        return
        
    # --- Status is 'joined' or 'ready' ---
    await query.answer("You have joined the fight!")
    
    enemy_info = gl.AKATSUKI_ENEMIES.get(battle_state['enemy_name'])
    
    if join_result['status'] == 'ready':
        # This was the 3rd player! Start the battle
        db.set_akatsuki_turn(message_id, battle_state['player_1_id']) # Set turn to player 1
        battle_state['turn_player_id'] = str(battle_state['player_1_id']) # Update local state (as string)
        
        text = get_akatsuki_battle_text(battle_state, enemy_info, []) 
        
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
        
    # --- THIS IS THE FIX ---
    if battle_state['turn_player_id'] != str(user.id):
    # --- END OF FIX ---
        await query.answer("It's not your turn!", show_alert=True)
        return
        
    player_data = db.get_player(user.id)
    if not player_data: await query.answer("Cannot find your player data!", show_alert=True); return
    
    if player_data['current_hp'] <= 1:
        await query.answer("You are fainted and cannot move! Waiting for AI...", show_alert=True)
        # Auto-skip turn to AI
        enemy_info = gl.AKATSUKI_ENEMIES.get(battle_state['enemy_name'])
        await _next_turn(context, chat_id, message_id, battle_state, enemy_info)
        return
        
    enemy_info = gl.AKATSUKI_ENEMIES.get(battle_state['enemy_name'])
    
    # --- Handle Flee ---
    if action == "flee":
        await query.answer() # Answer silently
        await query.edit_message_caption(caption=f"🏃 {player_data['username']} fled the battle! You gain no rewards.")
        # We need to remove the player from the fight and pass the turn
        db.remove_player_from_fight(message_id, user.id) # Need this DB func
        # Check if all players fled
        remaining_players = db.get_akatsuki_fight(chat_id, message_id)
        if not remaining_players['player_1_id'] and not remaining_players['player_2_id'] and not remaining_players['player_3_id']:
             await end_akatsuki_fight(context, chat_id, message_id, battle_state, enemy_info, success=False, flee=True)
        else:
             await _next_turn(context, chat_id, message_id, battle_state, enemy_info) # Pass turn
        return

    # --- Check Cooldowns for Attacks ---
    cooldown_seconds = 0
    # if action == "taijutsu": cooldown_seconds = TAIJUTSU_COOLDOWN_SECONDS # This was removed from your file
    if action == "throw_kunai": cooldown_seconds = KUNAI_COOLDOWN_SECONDS 
    elif action == "paper_bomb": cooldown_seconds = BOMB_COOLDOWN_SECONDS # New cooldown
    elif action == "jutsu": cooldown_seconds = JUTSU_COOLDOWN_SECONDS
    else: 
        await query.answer(f"Unknown action: {action}", show_alert=True) 
        return 

    # We need a *per-action* cooldown, not a generic one
    # Let's add 'akatsuki_cooldown' as a JSON dict in players table
    cooldown_check, remaining_seconds = _check_akatsuki_cooldown(player_data, action, cooldown_seconds)
    if not cooldown_check:
        time_unit = "seconds"; time_val = remaining_seconds
        if cooldown_seconds >= 60: time_unit = "minutes"; time_val = remaining_seconds / 60
        await query.answer(f"⏳ {action.replace('_', ' ').title()} is on cooldown! Wait {time_val:.0f} {time_unit}.", show_alert=True)
        return
    # --- End Cooldown Check ---
        
    player_total_stats = gl.get_total_stats(player_data)
    
    # --- THIS IS THE JUTSU BUTTON FIX (part 1) ---
    if action == "jutsu":
        if player_data['level'] < gl.JUTSU_LIBRARY['fireball']['level_required']: 
             await query.answer("You need Level 5+ to use Jutsus!", show_alert=True)
             return
        try: known_jutsus_list = json.loads(player_data['known_jutsus'])
        except: known_jutsus_list = []
        if not known_jutsus_list:
            await query.answer("You don't know any Jutsus! Use /combine.", show_alert=True)
            return
        
        await query.answer() # Answer silently *after* checks pass
        
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
             # We already answered query, so edit message to show error
             base_text = get_akatsuki_battle_text(battle_state, enemy_info, []).split("\n\nTurn:")[0]
             await send_or_edit_akatsuki_message(context, chat_id, message_id, f"{base_text}\n\n<i>Not enough Chakra for any Jutsu!</i>", None, query.message.reply_markup)
             return
        
        keyboard.append([InlineKeyboardButton("Cancel", callback_data="akatsuki_jutsu_cancel")])
        base_text = get_akatsuki_battle_text(battle_state, enemy_info, []).split("\n\nTurn:")[0]
        await send_or_edit_akatsuki_message(context, chat_id, message_id, f"{base_text}\n\nSelect a Jutsu:", None, InlineKeyboardMarkup(keyboard))
        return # Jutsu selection happens in akatsuki_jutsu_callback
    # --- END OF JUTSU BUTTON FIX ---

    # --- Handle Kunai and Bomb ---
    await query.answer() # Answer silently now
    
    battle_state_for_anim = {
        'chat_id': chat_id, 'message_id': message_id,
        'base_text': get_akatsuki_battle_text(battle_state, enemy_info, []).split("\n\nTurn:")[0],
        'players': {user.id: player_data}, 'turn': user.id
    }
    await send_or_edit_akatsuki_message(context, chat_id, message_id, f"{battle_state_for_anim['base_text']}\n\n<i>Turn: {player_data['username']}</i>\nProcessing attack...", None, None)
    
    final_damage = 0
    
    if action == "throw_kunai":
        boss_defender_sim = {'username': enemy_info['name']}
        damage_dealt = random.randint(8, 12) + player_data['level'] 
        is_crit = random.random() < 0.08 
        final_damage = int(damage_dealt * (1.8 if is_crit else 1.0))
        await anim.animate_throw_kunai(context, battle_state_for_anim, player_data, boss_defender_sim, final_damage, is_crit) 
        
    elif action == "paper_bomb":
        damage_dealt = (random.randint(15, 25) + player_data['level'] * 2)
        is_crit = random.random() < 0.12 
        final_damage = int(damage_dealt * (2.0 if is_crit else 1.0))
        boss_defender_sim = {'name': enemy_info['name']} # Paper Bomb anim uses 'name'
        await anim.animate_paper_bomb(context, battle_state_for_anim, player_data, boss_defender_sim, final_damage, is_crit)
        
    # --- Update DB after non-Jutsu Attacks ---
    new_enemy_hp = max(0, battle_state['enemy_hp'] - final_damage)
    db.update_akatsuki_fight_hp(message_id, new_enemy_hp)
    db.add_player_damage_to_fight(message_id, user.id, final_damage)
    # Set the cooldown for this specific action
    db.set_akatsuki_cooldown(user.id, action, cooldown_seconds)
    
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
    # --- THIS IS THE FIX ---
    if not battle_state or battle_state['turn_player_id'] != str(user.id):
    # --- END OF FIX ---
        await query.answer("It's not your turn!", show_alert=True); return
        
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
    
    # Check Jutsu cooldown
    cooldown_check, remaining_seconds = _check_akatsuki_cooldown(player_data, "jutsu", JUTSU_COOLDOWN_SECONDS)
    if not cooldown_check:
        await query.answer(f"⏳ Jutsu is on cooldown! Wait {remaining_seconds / 60:.1f} minutes.", show_alert=True); return
        
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
    damage_data = (final_damage, is_crit, False) 
    
    # Apply cost
    player_data['current_chakra'] -= jutsu_info['chakra_cost']
    
    # Play animation
    enemy_sim = {'username': enemy_info['name'], 'village': 'none'} 
    jutsu_info_for_anim = {'name': jutsu_info['name'], 'signs': jutsu_info['signs'], 'element': jutsu_info['element']}
    await anim.battle_animation_flow(context, battle_state_for_anim, player_data, enemy_sim, jutsu_info_for_anim, damage_data)

    # Apply damage
    new_enemy_hp = max(0, battle_state['enemy_hp'] - final_damage)
    db.update_akatsuki_fight_hp(message_id, new_enemy_hp)
    db.add_player_damage_to_fight(message_id, user.id, final_damage)
    
    # Set cooldowns and save chakra
    db.set_akatsuki_cooldown(user.id, "jutsu", JUTSU_COOLDOWN_SECONDS)
    db.update_player(user.id, {'current_chakra': player_data['current_chakra']}) # Save chakra change
    
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
        
    target_player = random.choice(living_players)
    target_player_total_stats = gl.get_total_stats(target_player)
    
    # AI Logic (Simple: 100% Taijutsu for now)
    ai_strength = enemy_info.get('strength', 20)
    ai_damage = int((ai_strength * 0.8) + (enemy_info['level'] * 0.5)) 
    ai_damage = random.randint(int(ai_damage * 0.8), int(ai_damage * 1.2))
    is_crit = random.random() < 0.1 
    if is_crit: ai_damage = int(ai_damage * 1.8)
    
    # Apply damage to player
    new_player_hp = max(0, target_player['current_hp'] - ai_damage)
    
    battle_state_for_anim = {
        'chat_id': chat_id, 'message_id': message_id,
        'base_text': get_akatsuki_battle_text(battle_state, enemy_info, []).split("\n\nTurn:")[0],
    }
    enemy_attacker_sim = {'username': enemy_info['name']}
    # Pass target_player as defender (it's a full player dict, so it's fine)
    await anim.animate_taijutsu(context, battle_state_for_anim, enemy_attacker_sim, target_player, ai_damage, is_crit)
    
    if new_player_hp == 0: new_player_hp = 1 # Fainted
    db.update_player(target_player['user_id'], {'current_hp': new_player_hp})
    
    # Check if all players are now fainted
    all_fainted = True
    # Re-fetch data to check
    for p_id in [battle_state[s] for s in PLAYER_SLOTS if battle_state[s]]:
        p_data = db.get_player(p_id)
        if p_data and p_data['current_hp'] > 1:
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
    
    current_player_id_str = str(battle_state['turn_player_id'])
    player_ids_list_str = [str(battle_state[s]) if battle_state[s] else None for s in PLAYER_SLOTS]

    if next_turn_id: # Used by AI to force turn back to Player 1
        pass # Will be handled below
    else:
        # Find current player's index
        try:
            current_index = player_ids_list_str.index(current_player_id_str)
        except ValueError:
            current_index = -1 

        if current_index == 0: # Was Player 1's turn
            next_turn_id = battle_state['player_2_id']
        elif current_index == 1: # Was Player 2's turn
            next_turn_id = battle_state['player_3_id']
        else: # Was Player 3's turn (or index -1)
            next_turn_id = 'ai_turn'
            
    # --- Check if next player is valid (not None or fainted) ---
    if next_turn_id and next_turn_id != 'ai_turn':
        player_data = db.get_player(next_turn_id)
        if not player_data or player_data['current_hp'] <= 1:
            # Player is fainted or gone, skip them
            logger.info(f"AKATSUKI EVENT: Skipping fainted player {next_turn_id}")
            # Recursively call _next_turn, passing the fainted player's ID as the *current* turn
            # This will make the logic advance to the *next* player after them
            temp_state = battle_state.copy()
            temp_state['turn_player_id'] = str(next_turn_id) # Pass as string
            await _next_turn(context, chat_id, message_id, temp_state, enemy_info)
            return # Stop this instance

    # --- Turn is valid ---
    db.set_akatsuki_turn(message_id, str(next_turn_id)) # Store as string
    battle_state['turn_player_id'] = str(next_turn_id) # Update local state
    
    # Get updated text (shows new player HPs)
    text = get_akatsuki_battle_text(battle_state, enemy_info, [])
    
    if next_turn_id == 'ai_turn':
        # Show AI thinking message (no buttons)
        await send_or_edit_akatsuki_message(context, chat_id, message_id, text, None, None)
        await asyncio.sleep(2) # Pause
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
async def end_akatsuki_fight(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id, battle_state, enemy_info, success=True, flee=False):
    """Ends the fight, gives rewards, and cleans up."""
    
    logger.info(f"AKATSUKI EVENT: Fight ended in chat {chat_id}. Success: {success}")
    
    if flee:
         final_text = (f"🏃 **Battle Ended!** 🏃\n\n" f"All players fled the fight.")
    elif success:
        final_text = (
            f"🏆 **YOU PROTECTED THE VILLAGE!** 🏆\n\n"
            f"The {enemy_info['name']} has been defeated!\n\n"
            f"Rewards: **+{AKATSUKI_REWARDS['exp']} EXP** and **+{AKATSUKI_REWARDS['ryo']} Ryo** have been given to all participants!"
        )
    else: # Players lost (all fainted)
        final_text = (
            f"💔 **MISSION FAILED!** 💔\n\n"
            f"The {enemy_info['name']} has defeated your team. The village is in peril..."
        )
    
    try:
        await send_or_edit_akatsuki_message(context, chat_id, message_id, final_text, None, None)
    except Exception as e:
        logger.error(f"Error sending final battle message: {e}")
        # Send as new message if edit fails
        await context.bot.send_message(chat_id=chat_id, text=final_text, parse_mode="HTML")


    # Give rewards (if success)
    if success:
        player_ids = [battle_state[s] for s in PLAYER_SLOTS if battle_state[s]]
        all_messages = []
        for user_id in player_ids:
            player = db.get_player(user_id)
            if player:
                temp_player_data = dict(player)
                temp_player_data['ryo'] += AKATSUKI_REWARDS['ryo']
                temp_player_data['exp'] += AKATSUKI_REWARDS['exp']
                temp_player_data['total_exp'] += AKATSUKI_REWARDS['exp']
                
                final_player_data, leveled_up, messages = gl.check_for_level_up(temp_player_data)
                db.update_player(user_id, final_player_data)
                
                if leveled_up:
                    all_messages.append(f"@{player['username']}\n" + "\n".join(messages))
        
        # Send level up messages
        if all_messages:
            await context.bot.send_message(chat_id=chat_id, text="\n\n".join(all_messages))

    # Clean up database
    db.clear_akatsuki_fight(chat_id)
    # Clear cooldowns for participants
    player_ids = [battle_state[s] for s in PLAYER_SLOTS if battle_state[s]]
    for user_id in player_ids:
        # db.set_akatsuki_cooldown(user_id, "taijutsu", 1) # Reset all cooldowns
        db.set_akatsuki_cooldown(user_id, "throw_kunai", 1)
        db.set_akatsuki_cooldown(user_id, "paper_bomb", 1)
        db.set_akatsuki_cooldown(user_id, "jutsu", 1)


# --- Helper: Cooldown Check ---
def _check_akatsuki_cooldown(player_data, action, cooldown_seconds):
    """Checks a specific action's cooldown."""
    cooldown_str = player_data.get('akatsuki_cooldown')
    now = datetime.datetime.now() # This check uses local time, which is fine
    
    # Faint check
    if player_data.get('current_hp', 100) <= 1:
        # Find when they fainted (last cooldown time)
        if cooldown_str:
            try:
                cooldowns = json.loads(cooldown_str)
                faint_time_iso = max(cooldowns.values()) if cooldowns else None
                if faint_time_iso:
                    faint_time = datetime.datetime.fromisoformat(faint_time_iso)
                    # You don't have FAINT_LOCKOUT_HOURS defined, let's assume 1 hour
                    lockout_duration = datetime.timedelta(hours=1) 
                    if now < (faint_time + lockout_duration):
                        remaining = (faint_time + lockout_duration) - now
                        return False, remaining.total_seconds()
            except:
                pass # Ignore errors in cooldown json
        else: # Fainted but no cooldowns? Lock for 1 hour from now.
            return False, 3600
            
    # Not fainted, check action cooldown
    if not cooldown_str:
        return True, 0 # No cooldowns set
        
    try:
        cooldowns = json.loads(cooldown_str)
    except:
        cooldowns = {}
        
    action_cooldown_time_iso = cooldowns.get(action)
    if not action_cooldown_time_iso:
        return True, 0 # This specific action is not on cooldown
        
    try:
        cooldown_time = datetime.datetime.fromisoformat(action_cooldown_time_iso)
    except ValueError: # Handle invalid ISO format string
        return True, 0
        
    if now < cooldown_time:
        return False, (cooldown_time - now).total_seconds()
    else:
        return True, 0

# --- Helper: Cooldown Set ---
# This function is in database.py now, but your akatsuki_event file had it.
# I will leave it here as db.set_akatsuki_cooldown() will work.
# def db_set_akatsuki_cooldown(user_id, action, cooldown_seconds):
#     ...

# --- Helper: Remove Player (Flee) ---
# This function is in database.py now.
# def db_remove_player_from_fight(message_id, user_id):
#     ...
