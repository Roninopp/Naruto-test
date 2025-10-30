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
import animations as anim 

logger = logging.getLogger(__name__)

# --- Constants ---
TAIJUTSU_COOLDOWN_SECONDS = 30
# --- NEW: Kunai Cooldown ---
KUNAI_COOLDOWN_SECONDS = 45 
JUTSU_COOLDOWN_SECONDS = 180 
FAINT_LOCKOUT_HOURS = 1
ACTIVE_BOSS_MESSAGES = {}

# --- Helper: Get Boss Battle Text (unchanged) ---
def get_boss_battle_text(boss_status, boss_info, chat_id):
    # (code is the same)
    top_damage = _get_top_damage_dealers(chat_id, limit=3) 
    text = (
        f"👹 **{boss_info['name']}** Attacks! 👹\n\n"
        f"<b>HP:</b> {gl.health_bar(boss_status['current_hp'], boss_status['max_hp'])}\n"
        f"<b>Ryo Pool:</b> {boss_status['ryo_pool']:,} 💰\n\n"
        f"<b>⚔️ Top Attackers ⚔️</b>\n"
    )
    if not top_damage: text += "<i>No damage dealt yet.</i>\n"
    else:
        for i, entry in enumerate(top_damage):
            rank_emoji = ["🥇", "🥈", "🥉"][i]
            text += f"{rank_emoji} {entry['username']}: {entry['total_damage']:,}\n"
    text += "\nChoose your attack:"
    return text

# --- Helper: Send/Edit Boss Battle Message ---
async def send_or_edit_boss_message(context: ContextTypes.DEFAULT_TYPE, chat_id, boss_status, boss_info):
    """Sends/Edits the interactive boss message with ALL buttons."""
    text = get_boss_battle_text(boss_status, boss_info, chat_id)
    
    # --- NEW: Added Throw Kunai Button ---
    keyboard = [
        [
            InlineKeyboardButton("⚔️ Taijutsu", callback_data="wb_action_taijutsu"), 
            InlineKeyboardButton("<0xF0><0x9F><0xAA><0x9A> Throw Kunai", callback_data="wb_action_throw_kunai"), # New Button
        ],
        [ 
            InlineKeyboardButton("🌀 Use Jutsu", callback_data="wb_action_jutsu"),   
            InlineKeyboardButton("📊 Status Update", callback_data="wb_action_status") 
        ]
        # We can add Use Item button here later if desired for boss fights
    ]
    # --- END NEW ---
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_id = ACTIVE_BOSS_MESSAGES.get(chat_id)

    try:
        if message_id:
            await context.bot.edit_message_caption( 
                chat_id=chat_id, message_id=message_id, caption=text,
                reply_markup=reply_markup, parse_mode="HTML"
            )
        else:
            # Check if boss_info['image'] exists and is accessible
            image_path = boss_info.get('image', 'images/default_boss.png') # Add a default?
            try:
                # Try opening the file to ensure it exists before sending
                with open(image_path, 'rb') as f:
                    pass # Just check if it opens
                photo_input = open(image_path, 'rb')
            except FileNotFoundError:
                 logger.error(f"Boss image not found at {image_path}. Sending text only.")
                 photo_input = None # Indicate photo failed

            if photo_input:
                message = await context.bot.send_photo(
                    chat_id=chat_id, photo=photo_input, 
                    caption=text, reply_markup=reply_markup, parse_mode="HTML"
                )
                ACTIVE_BOSS_MESSAGES[chat_id] = message.message_id 
                logger.info(f"Sent new boss message for chat {chat_id}, msg_id: {message.message_id}")
            else: # Send text if photo failed
                 message = await context.bot.send_message(
                      chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML"
                 )
                 # Don't store message ID if it's text only? Or handle editing text later?
                 # For now, let's not store it if photo fails, status cmd will resend.
                 logger.warning(f"Sent boss message as text due to missing image for chat {chat_id}")


    except Exception as e:
        logger.error(f"Error sending/editing boss message for chat {chat_id}: {e}")
        if "Message is not modified" not in str(e): # Don't clear ID if it's just not modified
            if chat_id in ACTIVE_BOSS_MESSAGES: del ACTIVE_BOSS_MESSAGES[chat_id]


# --- Admin Command (Enable Boss - unchanged) ---
async def enable_world_boss_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (code is the same)
    chat = update.effective_chat; user = update.effective_user
    # ... (admin checks) ...
    success = db.enable_boss_chat(chat.id, user.id)
    # ... (reply messages) ...

# --- Player Command (Boss Status - unchanged) ---
async def boss_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (code is the same)
    chat_id = update.effective_chat.id; boss_status = db.get_boss_status(chat_id)
    # ... (checks) ...
    old_message_id = ACTIVE_BOSS_MESSAGES.pop(chat_id, None)
    # ... (delete old message) ...
    await send_or_edit_boss_message(context, chat_id, boss_status, boss_info)

# --- Callback Handlers for Buttons ---

async def boss_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles main boss action buttons: Taijutsu, Throw Kunai, Jutsu, Status."""
    query = update.callback_query
    
    # --- FIX: Move answer() calls AFTER checks ---

    action = query.data.split('_')[-1] # taijutsu, throw_kunai, jutsu, status
    user = query.from_user
    chat_id = query.message.chat_id
    player_data = db.get_player(user.id)
    
    if not player_data: await query.answer("You need to /start your journey first!", show_alert=True); return

    boss_status = db.get_boss_status(chat_id)
    if not boss_status or not boss_status['is_active']:
        await query.answer("The World Boss is no longer active.", show_alert=True)
        try: await query.edit_message_reply_markup(reply_markup=None)
        except: pass
        return
        
    boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
    if not boss_info: await query.answer("Error finding boss info.", show_alert=True); return
         
    if action == "status":
        # --- FIX: Add feedback for status button ---
        await query.answer("Status refreshed!", show_alert=False) 
        # --- END FIX ---
        await send_or_edit_boss_message(context, chat_id, boss_status, boss_info)
        return
        
    # --- Action is Attack - Perform Checks FIRST ---
    if player_data['current_hp'] <= 1:
         await query.answer(f"😵 You are fainted and locked out! Recover first.", show_alert=True); return
         
    # Determine cooldown based on action
    cooldown_seconds = 0
    if action == "taijutsu": cooldown_seconds = TAIJUTSU_COOLDOWN_SECONDS
    elif action == "throw_kunai": cooldown_seconds = KUNAI_COOLDOWN_SECONDS # New cooldown
    elif action == "jutsu": cooldown_seconds = JUTSU_COOLDOWN_SECONDS
    else: await query.answer("Unknown action!", show_alert=True); return # Should not happen
    
    cooldown_check, remaining_seconds = _check_cooldown(player_data, cooldown_seconds)
    if not cooldown_check:
        time_unit = "seconds"; time_val = remaining_seconds
        if cooldown_seconds == JUTSU_COOLDOWN_SECONDS: time_unit = "minutes"; time_val = remaining_seconds / 60
        await query.answer(f"⏳ On cooldown! Wait {time_val:.1f} {time_unit}.", show_alert=True); return

    # --- Process Attack Actions ---
    await query.answer() # Answer silently now that checks passed
    
    battle_state_for_anim = {
        'chat_id': chat_id, 'message_id': query.message.message_id,
        'base_text': get_boss_battle_text(boss_status, boss_info, chat_id).split("\n\nChoose your attack:")[0],
        'players': {user.id: player_data}, 'turn': user.id
    }
    await anim.edit_battle_message(context, battle_state_for_anim, f"{battle_state_for_anim['base_text']}\n\n<i>Processing attack...</i>", reply_markup=None)

    player_total_stats = gl.get_total_stats(player_data)
    new_boss_hp = boss_status['current_hp']; boss_defeated = False
    final_damage = 0; recoil_damage = 0; new_cooldown_time_iso = ""

    if action == "taijutsu":
        base_damage = player_total_stats['strength'] * 2
        damage_dealt = random.randint(int(base_damage * 0.8), int(base_damage * 1.2))
        is_crit = random.random() < 0.1
        final_damage = int(damage_dealt * (2.0 if is_crit else 1.0))
        recoil_damage = int(player_total_stats['max_hp'] * boss_info['taijutsu_recoil'])
        player_data['current_hp'] -= recoil_damage
        boss_defender_sim = {'username': boss_info['name']} # Simplified for anim
        await anim.animate_taijutsu(context, battle_state_for_anim, player_data, boss_defender_sim, final_damage, is_crit)
        new_cooldown_time_iso = (datetime.datetime.now() + datetime.timedelta(seconds=TAIJUTSU_COOLDOWN_SECONDS)).isoformat()
        
    # --- NEW: Throw Kunai Action ---
    elif action == "throw_kunai":
        # Simple fixed damage range + crit chance
        damage_dealt = random.randint(8, 12) + player_data['level'] # Scale slightly with level
        is_crit = random.random() < 0.08 # 8% crit chance
        final_damage = int(damage_dealt * (1.8 if is_crit else 1.0))
        # Use same recoil as Taijutsu for simplicity
        recoil_damage = int(player_total_stats['max_hp'] * boss_info['taijutsu_recoil']) 
        player_data['current_hp'] -= recoil_damage
        # Play Kunai Animation
        boss_defender_sim = {'username': boss_info['name']}
        await anim.animate_throw_kunai(context, battle_state_for_anim, player_data, boss_defender_sim, final_damage, is_crit) # New animation func
        new_cooldown_time_iso = (datetime.datetime.now() + datetime.timedelta(seconds=KUNAI_COOLDOWN_SECONDS)).isoformat()
    # --- END NEW ---
        
    elif action == "jutsu":
        # --- FIX: Check level BEFORE answering ---
        if player_data['level'] < 5: 
             await query.answer("You need Level 5+ to use Jutsus!", show_alert=True)
             await send_or_edit_boss_message(context, chat_id, boss_status, boss_info); return # Reshow menu

        try: known_jutsus_list = json.loads(player_data['known_jutsus'])
        except: known_jutsus_list = []
        if not known_jutsus_list:
            # --- FIX: Use alert ---
            await query.answer("You don't know any Jutsus!", show_alert=True)
            await send_or_edit_boss_message(context, chat_id, boss_status, boss_info); return # Reshow menu

        # Checks passed, now show menu (answer was done above)
        keyboard = []; available_jutsus = 0
        for jutsu_key in known_jutsus_list:
            jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_key)
            if jutsu_info:
                if player_data['current_chakra'] >= jutsu_info['chakra_cost']:
                    button_text = f"{jutsu_info['name']} ({jutsu_info['chakra_cost']} Chakra)"
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=f"boss_usejutsu_{jutsu_key}")])
                    available_jutsus += 1
                else:
                    button_text = f"🚫 {jutsu_info['name']} ({jutsu_info['chakra_cost']} Chakra)"
                    keyboard.append([InlineKeyboardButton(button_text, callback_data="boss_nochakra")])
        
        if available_jutsus == 0:
             # --- FIX: Use alert ---
             await query.answer("Not enough Chakra for any Jutsu!", show_alert=True)
             await send_or_edit_boss_message(context, chat_id, boss_status, boss_info); return # Reshow menu

        keyboard.append([InlineKeyboardButton("Cancel", callback_data="boss_usejutsu_cancel")])
        await anim.edit_battle_message(context, battle_state_for_anim, f"{battle_state_for_anim['base_text']}\n\nSelect a Jutsu:", reply_markup=InlineKeyboardMarkup(keyboard))
        return # Jutsu selection happens in boss_jutsu_callback

    # --- Update DB after Taijutsu or Throw Kunai ---
    if action in ["taijutsu", "throw_kunai"]:
        boss_defeated, new_boss_hp = _update_boss_and_player_damage(chat_id, user.id, player_data['username'], final_damage, boss_status)
        player_updates = {'current_hp': max(1, player_data['current_hp']), 'boss_attack_cooldown': new_cooldown_time_iso}
        db.update_player(user.id, player_updates)
        
        # Post-animation message update
        action_name = "Taijutsu" if action == "taijutsu" else "Kunai"
        final_text = (f"{battle_state_for_anim['base_text']}\n\n"
                      f"<i>{action_name} dealt {final_damage:,} damage!</i>\n"
                      f"<i>🩸 Recoil: Took {recoil_damage} damage.</i>")
        if player_data['current_hp'] <= 1: final_text += "\n😵 **You fainted!**"
        await anim.edit_battle_message(context, battle_state_for_anim, final_text, reply_markup=None)
        await asyncio.sleep(2.5) 

    # --- Update message after action (unless Jutsu selection) ---
    if not boss_defeated and action != "jutsu":
         updated_boss_status = db.get_boss_status(chat_id)
         if updated_boss_status and updated_boss_status['is_active']:
              await send_or_edit_boss_message(context, chat_id, updated_boss_status, boss_info)
         else: boss_defeated = True 

    if boss_defeated:
         final_boss_status = db.get_boss_status(chat_id)
         await _process_boss_defeat(context, chat_id, final_boss_status if final_boss_status else boss_status, boss_info)
         if chat_id in ACTIVE_BOSS_MESSAGES: del ACTIVE_BOSS_MESSAGES[chat_id]


async def boss_jutsu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the selection of a specific Jutsu to use against the boss."""
    query = update.callback_query
    
    user = query.from_user
    chat_id = query.message.chat_id
    player_data = db.get_player(user.id)

    if not player_data: await query.answer("Error: Player data not found.", show_alert=True); return

    parts = query.data.split('_'); jutsu_key = "_".join(parts[2:]) 

    if jutsu_key == "cancel":
        await query.answer() # Answer silently
        boss_status = db.get_boss_status(chat_id)
        if boss_status and boss_status['is_active']:
             boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
             if boss_info: await send_or_edit_boss_message(context, chat_id, boss_status, boss_info)
        else: await query.edit_message_caption(caption="Boss fight ended.", reply_markup=None) 
        return
        
    if jutsu_key == "nochakra":
        await query.answer("You don't have enough Chakra for that Jutsu!", show_alert=True); return 

    jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_key)
    if not jutsu_info: await query.answer("Error: Invalid Jutsu selected.", show_alert=True); return

    # Re-check chakra, cooldown, faint status BEFORE answering
    if player_data['current_chakra'] < jutsu_info['chakra_cost']: await query.answer("Not enough Chakra!", show_alert=True); return
    cooldown_check, remaining_seconds = _check_cooldown(player_data, JUTSU_COOLDOWN_SECONDS)
    if not cooldown_check: await query.answer(f"⏳ On Jutsu cooldown! Wait {remaining_seconds / 60:.1f} minutes.", show_alert=True); return
    if player_data['current_hp'] <= 1: await query.answer(f"😵 You are fainted! Cannot use Jutsu.", show_alert=True); return

    boss_status = db.get_boss_status(chat_id)
    if not boss_status or not boss_status['is_active']:
        await query.answer("The World Boss was defeated before you could attack!", show_alert=True)
        await query.edit_message_caption(caption="Boss fight ended.", reply_markup=None); return
        
    boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
    if not boss_info: await query.answer("Error finding boss info.", show_alert=True); return

    # --- Perform Jutsu Attack ---
    await query.answer() # Answer silently now
    
    battle_state_for_anim = {
        'chat_id': chat_id, 'message_id': query.message.message_id,
        'base_text': get_boss_battle_text(boss_status, boss_info, chat_id).split("\n\nChoose your attack:")[0],
        'players': {user.id: player_data}, 'turn': user.id
    }
    await anim.edit_battle_message(context, battle_state_for_anim, f"{battle_state_for_anim['base_text']}\n\n<i>Processing Jutsu...</i>", reply_markup=None)

    player_total_stats = gl.get_total_stats(player_data)

    base_damage = jutsu_info['power'] + (player_total_stats['intelligence'] * 2.5)
    damage_dealt = random.randint(int(base_damage * 0.9), int(base_damage * 1.1))
    is_crit = random.random() < 0.15
    final_damage = int(damage_dealt * (2.5 if is_crit else 1.0))
    damage_data = (final_damage, is_crit, False) 
    recoil_damage = int(player_total_stats['max_hp'] * boss_info['jutsu_recoil'])
    player_data['current_hp'] -= recoil_damage
    player_data['current_chakra'] -= jutsu_info['chakra_cost']

    boss_defender_sim = {'username': boss_info['name'], 'village': 'none'} # Added village for calc
    jutsu_info_for_anim = {'name': jutsu_info['name'], 'signs': jutsu_info['signs'], 'element': jutsu_info['element']}
    await anim.battle_animation_flow(context, battle_state_for_anim, player_data, boss_defender_sim, jutsu_info_for_anim, damage_data)

    boss_defeated, new_boss_hp = _update_boss_and_player_damage(chat_id, user.id, player_data['username'], final_damage, boss_status)
    new_cooldown_time_iso = (datetime.datetime.now() + datetime.timedelta(seconds=JUTSU_COOLDOWN_SECONDS)).isoformat()
    player_updates = {
        'current_hp': max(1, player_data['current_hp']),
        'current_chakra': player_data['current_chakra'],
        'boss_attack_cooldown': new_cooldown_time_iso
    }
    db.update_player(user.id, player_updates)

    final_text = (f"{battle_state_for_anim['base_text']}\n\n"
                  f"<i>🌀 You dealt {final_damage:,} Jutsu damage!</i>\n"
                  f"<i>🩸 Recoil: Took {recoil_damage} damage.</i>")
    if player_data['current_hp'] <= 1: final_text += "\n😵 **You fainted!**"
    await anim.edit_battle_message(context, battle_state_for_anim, final_text, reply_markup=None)
    await asyncio.sleep(2.5) 

    if not boss_defeated:
         updated_boss_status = db.get_boss_status(chat_id)
         if updated_boss_status and updated_boss_status['is_active']:
              await send_or_edit_boss_message(context, chat_id, updated_boss_status, boss_info)
         else: boss_defeated = True 
    if boss_defeated:
         final_boss_status = db.get_boss_status(chat_id)
         await _process_boss_defeat(context, chat_id, final_boss_status if final_boss_status else boss_status, boss_info)
         if chat_id in ACTIVE_BOSS_MESSAGES: del ACTIVE_BOSS_MESSAGES[chat_id]


# --- Helper Functions (unchanged) ---
def _check_cooldown(player_data, cooldown_duration_seconds):
    # (code is the same)
    cooldown_str = player_data.get('boss_attack_cooldown'); now = datetime.datetime.now()
    if player_data.get('current_hp', 100) <= 1:
        lockout_duration = datetime.timedelta(hours=FAINT_LOCKOUT_HOURS)
        if cooldown_str: 
             cooldown_time = datetime.datetime.fromisoformat(cooldown_str)
             faint_time = cooldown_time - datetime.timedelta(seconds=cooldown_duration_seconds) 
             if now < (faint_time + lockout_duration):
                  remaining_lockout = (faint_time + lockout_duration) - now
                  return False, remaining_lockout.total_seconds()
        else: return False, lockout_duration.total_seconds() 
    if not cooldown_str: return True, 0 
    cooldown_time = datetime.datetime.fromisoformat(cooldown_str)
    if now < cooldown_time: return False, (cooldown_time - now).total_seconds()
    else: return True, 0

def _update_boss_and_player_damage(chat_id, user_id, username, damage_dealt, current_boss_status):
     # (code is the same)
    conn = db.get_db_connection(); # ... rest of function ...
    if conn is None: logger.error("DB connection failed..."); return False, current_boss_status['current_hp']
    new_boss_hp = 0; boss_defeated = False
    try:
        cursor = conn.cursor()
        new_boss_hp = max(0, current_boss_status['current_hp'] - damage_dealt)
        cursor.execute("UPDATE world_boss_status SET current_hp = ? WHERE chat_id = ? AND is_active = 1", (new_boss_hp, chat_id))
        cursor.execute(
            """INSERT INTO world_boss_damage (chat_id, user_id, username, total_damage) VALUES (?, ?, ?, ?)
               ON CONFLICT(chat_id, user_id) DO UPDATE SET total_damage = total_damage + excluded.total_damage, username = excluded.username;""",
            (chat_id, user_id, username, damage_dealt)
        )
        conn.commit()
        if new_boss_hp == 0: boss_defeated = True
    except sqlite3.Error as e: logger.error(f"Error updating boss damage: {e}"); conn.rollback(); return False, current_boss_status['current_hp']
    finally: conn.close()
    return boss_defeated, new_boss_hp


def _get_top_damage_dealers(chat_id, limit=5):
    # (code is the same)
    conn = db.get_db_connection(); # ... rest of function ...
    if conn is None: return []
    try:
        cursor = conn.cursor(); cursor.execute("SELECT username, total_damage FROM world_boss_damage WHERE chat_id = ? ORDER BY total_damage DESC LIMIT ?", (chat_id, limit))
        rows = cursor.fetchall(); return [dict(row) for row in rows]
    except sqlite3.Error as e: logger.error(f"Error fetching top damage: {e}"); return []
    finally: conn.close()

async def _process_boss_defeat(context: ContextTypes.DEFAULT_TYPE, chat_id, boss_status, boss_info):
    # (code is the same)
    logger.info(f"Boss defeated in chat {chat_id}!"); # ... rest of function ...
    await context.bot.send_message(chat_id=chat_id, text=f"🏆👹 **The {boss_info['name']} has been defeated!** 👹🏆", parse_mode="HTML")
    conn = db.get_db_connection(); # ... rest of reward logic ...
    if conn is None: await context.bot.send_message(chat_id, "DB error."); return
    try:
         cursor = conn.cursor() # ... get damage dealers ...
         all_damage = [dict(row) for row in cursor.fetchall()]
         if not all_damage: # ... handle no damage ...
             conn.commit(); return
         # ... calculate rewards ...
         rewards = {} # ... fill rewards dict ...
         reward_text_parts = ["<b>--- 💰 Reward Distribution 💰 ---</b>"] # ... build text ...
         player_ids_to_update = list(rewards.keys())
         for user_id, ryo_gain in rewards.items():
              cursor.execute("UPDATE players SET ryo = ryo + ?, boss_attack_cooldown = NULL WHERE user_id = ?", (ryo_gain, user_id))
         cursor.execute("UPDATE world_boss_status SET is_active = 0, current_hp = 0 WHERE chat_id = ?", (chat_id,))
         cursor.execute("DELETE FROM world_boss_damage WHERE chat_id = ?", (chat_id,))
         conn.commit()
         for user_id in player_ids_to_update: db.cache.clear_player_cache(user_id)
         await context.bot.send_message(chat_id, "\n".join(reward_text_parts), parse_mode="HTML")
    except sqlite3.Error as e: logger.error(f"Error processing boss defeat: {e}"); await context.bot.send_message(chat_id, "DB error during distribution."); conn.rollback()
    finally: conn.close()


async def spawn_world_boss(context: ContextTypes.DEFAULT_TYPE):
    # (code is the same)
    logger.info("BOSS JOB: Running spawn check..."); # ... rest of function ...
    enabled_chat_ids = db.get_all_boss_chats() 
    if not enabled_chat_ids: logger.info("BOSS JOB: No enabled chats."); return
    for chat_id in enabled_chat_ids:
        boss_status = db.get_boss_status(chat_id)
        if boss_status and boss_status.get('is_active'):
            logger.info(f"BOSS JOB: Boss active in chat {chat_id}."); boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
            if boss_info: await send_or_edit_boss_message(context, chat_id, boss_status, boss_info) 
            continue 
        logger.info(f"BOSS JOB: Spawning new boss in chat {chat_id}...")
        boss_key = random.choice(list(gl.WORLD_BOSSES.keys())); boss_info = gl.WORLD_BOSSES[boss_key]
        spawn_time_iso = datetime.datetime.now().isoformat()
        conn = db.get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""INSERT OR REPLACE INTO world_boss_status (chat_id, is_active, boss_key, current_hp, max_hp, ryo_pool, spawn_time) VALUES (?, 1, ?, ?, ?, ?, ?)""", (chat_id, boss_key, boss_info['hp'], boss_info['hp'], boss_info['ryo_pool'], spawn_time_iso))
            cursor.execute("DELETE FROM world_boss_damage WHERE chat_id = ?", (chat_id,))
            conn.commit(); logger.info(f"BOSS JOB: Spawn successful for {boss_info['name']} in chat {chat_id}")
        except sqlite3.Error as e: logger.error(f"BOSS JOB: DB error spawning boss: {e}");
        finally:
            if conn: conn.close()
        new_boss_status = db.get_boss_status(chat_id)
        if new_boss_status and new_boss_status['is_active']:
            await send_or_edit_boss_message(context, chat_id, new_boss_status, boss_info)
            await asyncio.sleep(0.5) 
        else: logger.error(f"BOSS JOB: Failed get status after spawn {chat_id}")
    logger.info("BOSS JOB: Finished spawn check.")
