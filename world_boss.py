import logging
import json
# import sqlite3 <-- REMOVED
import psycopg2 # <-- ADDED
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
KUNAI_EMOJI = "\U0001FA9A" 
KUNAI_COOLDOWN_SECONDS = 45 
JUTSU_COOLDOWN_SECONDS = 180 
FAINT_LOCKOUT_HOURS = 1
ACTIVE_BOSS_MESSAGES = {} 

# --- (Helper functions: get_boss_battle_text, send_or_edit_boss_message, enable_world_boss, boss_status_command are unchanged) ---
def get_boss_battle_text(boss_status, boss_info, chat_id):
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

async def send_or_edit_boss_message(context: ContextTypes.DEFAULT_TYPE, chat_id, boss_status, boss_info):
    text = get_boss_battle_text(boss_status, boss_info, chat_id)
    keyboard = [
        [
            InlineKeyboardButton("⚔️ Taijutsu", callback_data="wb_action_taijutsu"), 
            InlineKeyboardButton(f"{KUNAI_EMOJI} Throw Kunai", callback_data="wb_action_throw_kunai"), 
        ],
        [ 
            InlineKeyboardButton("🌀 Use Jutsu", callback_data="wb_action_jutsu"),   
            InlineKeyboardButton("📊 Status Update", callback_data="wb_action_status") 
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_id = ACTIVE_BOSS_MESSAGES.get(chat_id)
    try:
        if message_id:
            await context.bot.edit_message_caption( 
                chat_id=chat_id, message_id=message_id, caption=text,
                reply_markup=reply_markup, parse_mode="HTML"
            )
        else:
            image_path = boss_info.get('image', 'images/default_boss.png') 
            try:
                # This check might fail on ephemeral systems, but we'll try
                with open(image_path, 'rb') as f: pass 
                photo_input = open(image_path, 'rb')
            except FileNotFoundError:
                 logger.error(f"Boss image not found at {image_path}. Sending text only.")
                 photo_input = None 
            if photo_input:
                message = await context.bot.send_photo(
                    chat_id=chat_id, photo=photo_input, 
                    caption=text, reply_markup=reply_markup, parse_mode="HTML"
                )
                ACTIVE_BOSS_MESSAGES[chat_id] = message.message_id 
                logger.info(f"Sent new boss message for chat {chat_id}, msg_id: {message.message_id}")
                photo_input.close() # Close the file handle
            else: 
                 message = await context.bot.send_message(
                      chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML"
                 )
                 logger.warning(f"Sent boss message as text due to missing image for chat {chat_id}")
                 ACTIVE_BOSS_MESSAGES[chat_id] = message.message_id # Save message_id even for text
    except Exception as e:
        if "Message is not modified" not in str(e): 
            logger.error(f"Error sending/editing boss message for chat {chat_id}: {e}")
            if chat_id in ACTIVE_BOSS_MESSAGES: del ACTIVE_BOSS_MESSAGES[chat_id]

async def enable_world_boss_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat; user = update.effective_user
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]: await update.message.reply_text("This command can only be used in a group chat."); return
    try:
        chat_admins = await context.bot.get_chat_administrators(chat.id)
        user_ids = [admin.user.id for admin in chat_admins]
        if user.id not in user_ids: await update.message.reply_text("You must be a group admin to use this command."); return
    except Exception as e: logger.error(f"Error checking admin status in chat {chat.id}: {e}"); await update.message.reply_text("An error occurred. I might not have permission to see group admins."); return
    success = db.enable_boss_chat(chat.id, user.id)
    if success:
        logger.info(f"World Boss game enabled for chat {chat.id} by user {user.id}")
        await update.message.reply_text(
            "✅ 👹 **World Boss Enabled!** 👹 ✅\n\n"
            "This group will now be included in World Boss spawns.\n"
            "The next boss will appear on the next scheduled spawn (every **1 hour**).",
            parse_mode="HTML"
        )
    else: await update.message.reply_text("A database error occurred. Please try again.")

async def boss_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id; boss_status = db.get_boss_status(chat_id)
    if not boss_status or not boss_status['is_active']: await update.message.reply_text("There is no active World Boss in this chat right now."); return
    boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
    if not boss_info: await update.message.reply_text("Error: Could not retrieve boss information."); return
    old_message_id = ACTIVE_BOSS_MESSAGES.pop(chat_id, None)
    if old_message_id:
        try: await context.bot.delete_message(chat_id=chat_id, message_id=old_message_id)
        except Exception as e: logger.warning(f"Could not delete old boss message {old_message_id} in chat {chat_id}: {e}")
    await send_or_edit_boss_message(context, chat_id, boss_status, boss_info)

# --- Callback Handlers for Buttons ---

async def boss_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles main boss action buttons: Taijutsu, Throw Kunai, Jutsu, Status."""
    query = update.callback_query
    
    action = "_".join(query.data.split('_')[2:])
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
        await query.answer("Status refreshed!", show_alert=False) 
        await send_or_edit_boss_message(context, chat_id, boss_status, boss_info)
        return
        
    # --- Action is Attack - Perform Checks FIRST ---
    if player_data['current_hp'] <= 1:
         await query.answer(f"😵 You are fainted and locked out! Recover first.", show_alert=True); return
         
    cooldown_seconds = 0
    if action == "taijutsu": cooldown_seconds = TAIJUTSU_COOLDOWN_SECONDS
    elif action == "throw_kunai": cooldown_seconds = KUNAI_COOLDOWN_SECONDS 
    elif action == "jutsu": cooldown_seconds = JUTSU_COOLDOWN_SECONDS
    else: 
        await query.answer(f"Unknown action: {action}", show_alert=True); return 
    
    cooldown_check, remaining_seconds = _check_cooldown(player_data, cooldown_seconds)
    if not cooldown_check:
        time_unit = "seconds"; time_val = remaining_seconds
        if cooldown_seconds == JUTSU_COOLDOWN_SECONDS: time_unit = "minutes"; time_val = remaining_seconds / 60
        await query.answer(f"⏳ On cooldown! Wait {time_val:.1f} {time_unit}.", show_alert=True); return
    
    player_total_stats = gl.get_total_stats(player_data)
    
    battle_state_for_anim = {
        'chat_id': chat_id, 'message_id': query.message.message_id,
        'base_text': get_boss_battle_text(boss_status, boss_info, chat_id).split("\n\nChoose your attack:")[0],
        'players': {user.id: player_data}, 'turn': user.id
    }
    
    new_boss_hp = boss_status['current_hp']; boss_defeated = False
    final_damage = 0; recoil_damage = 0; new_cooldown_time_iso = ""

    if action == "taijutsu":
        await query.answer() # Answer silently now
        await anim.edit_battle_message(context, battle_state_for_anim, f"{battle_state_for_anim['base_text']}\n\n<i>Processing attack...</i>", reply_markup=None)
        
        base_damage = player_total_stats['strength'] * 2
        damage_dealt = random.randint(int(base_damage * 0.8), int(base_damage * 1.2))
        is_crit = random.random() < 0.1
        final_damage = int(damage_dealt * (2.0 if is_crit else 1.0))
        recoil_damage = int(player_total_stats['max_hp'] * boss_info['taijutsu_recoil'])
        player_data['current_hp'] -= recoil_damage
        boss_defender_sim = {'username': boss_info['name']} 
        await anim.animate_taijutsu(context, battle_state_for_anim, player_data, boss_defender_sim, final_damage, is_crit)
        new_cooldown_time_iso = (datetime.datetime.now() + datetime.timedelta(seconds=TAIJUTSU_COOLDOWN_SECONDS)).isoformat()
        
    elif action == "throw_kunai":
        await query.answer() # Answer silently now
        await anim.edit_battle_message(context, battle_state_for_anim, f"{battle_state_for_anim['base_text']}\n\n<i>Processing attack...</i>", reply_markup=None)
        
        damage_dealt = random.randint(8, 12) + player_data['level'] 
        is_crit = random.random() < 0.08 
        final_damage = int(damage_dealt * (1.8 if is_crit else 1.0))
        recoil_damage = int(player_total_stats['max_hp'] * boss_info['taijutsu_recoil']) 
        player_data['current_hp'] -= recoil_damage
        boss_defender_sim = {'username': boss_info['name']}
        await anim.animate_throw_kunai(context, battle_state_for_anim, player_data, boss_defender_sim, final_damage, is_crit) 
        new_cooldown_time_iso = (datetime.datetime.now() + datetime.timedelta(seconds=KUNAI_COOLDOWN_SECONDS)).isoformat()
        
    elif action == "jutsu":
        if player_data['level'] < gl.JUTSU_LIBRARY['fireball']['level_required']: 
             await query.answer("You need Level 5+ to use Jutsus!", show_alert=True); 
             return
        
        # --- THIS IS THE FIX ---
        known_jutsus_list = player_data.get('known_jutsus') or []
        # --- END OF FIX ---
        
        if not known_jutsus_list:
            await query.answer("You don't know any Jutsus! Use /combine.", show_alert=True); 
            return
        
        await query.answer() 
        await anim.edit_battle_message(context, battle_state_for_anim, f"{battle_state_for_anim['base_text']}\n\n<i>Processing attack...</i>", reply_markup=None) 
        
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
             await anim.edit_battle_message(context, battle_state_for_anim, f"{battle_state_for_anim['base_text']}\n\n<i>Not enough Chakra for any Jutsu!</i>")
             await asyncio.sleep(2) 
             await send_or_edit_boss_message(context, chat_id, boss_status, boss_info); return 
        
        keyboard.append([InlineKeyboardButton("Cancel", callback_data="boss_usejutsu_cancel")])
        await anim.edit_battle_message(context, battle_state_for_anim, f"{battle_state_for_anim['base_text']}\n\nSelect a Jutsu:", reply_markup=InlineKeyboardMarkup(keyboard))
        return 

    # --- Update DB after Taijutsu or Throw Kunai ---
    if action in ["taijutsu", "throw_kunai"]:
        boss_defeated, new_boss_hp = _update_boss_and_player_damage(chat_id, user.id, player_data['username'], final_damage, boss_status)
        player_updates = {'current_hp': max(1, player_data['current_hp']), 'boss_attack_cooldown': new_cooldown_time_iso}
        db.update_player(user.id, player_updates)
        
        action_name = "Taijutsu" if action == "taijutsu" else "Throw Kunai"
        final_text = (f"{battle_state_for_anim['base_text']}\n\n"
                      f"<i>{KUNAI_EMOJI if action == 'throw_kunai' else '⚔️'} You dealt {final_damage:,} {action_name} damage!</i>\n"
                      f"<i>🩸 Recoil: Took {recoil_damage} damage.</i>")
        if player_data['current_hp'] <= 1: final_text += "\n😵 **You fainted!**"
        await anim.edit_battle_message(context, battle_state_for_anim, final_text, reply_markup=None)
        await asyncio.sleep(2.5) 

    if not boss_defeated and action != "jutsu":
         updated_boss_status = db.get_boss_status(chat_id)
         if updated_boss_status and updated_boss_status['is_active']:
              await send_or_edit_boss_message(context, chat_id, updated_boss_status, boss_info)
         else: boss_defeated = True 

    if boss_defeated:
         final_boss_status = db.get_boss_status(chat_id)
         await _process_boss_defeat(context, chat_id, final_boss_status if final_boss_status else boss_status, boss_info)
         if chat_id in ACTIVE_BOSS_MESSAGES: del ACTIVE_BOSS_MESSAGES[chat_id]

# --- (boss_jutsu_callback is also fixed now) ---
async def boss_jutsu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user; chat_id = query.message.chat_id; player_data = db.get_player(user.id)
    if not player_data: await query.answer("Error: Player data not found.", show_alert=True); return
    parts = query.data.split('_'); jutsu_key = "_".join(parts[2:]) 
    if jutsu_key == "cancel":
        await query.answer(); boss_status = db.get_boss_status(chat_id)
        if boss_status and boss_status['is_active']:
             boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
             if boss_info: await send_or_edit_boss_message(context, chat_id, boss_status, boss_info)
        else: await query.edit_message_caption(caption="Boss fight ended.", reply_markup=None) 
        return
    if jutsu_key == "nochakra": await query.answer("You don't have enough Chakra for that Jutsu!", show_alert=True); return 
    jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_key)
    if not jutsu_info: await query.answer("Error: Invalid Jutsu selected.", show_alert=True); return
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
    await query.answer() 
    battle_state_for_anim = {
        'chat_id': chat_id, 'message_id': query.message.message_id,
        'base_text': get_boss_battle_text(boss_status, boss_info, chat_id).split("\n\nChoose your attack:")[0],
        'players': {user.id: player_data}, 'turn': user.id
    }
    await anim.edit_battle_message(context, battle_state_for_anim, f"{battle_state_for_anim['base_text']}\n\n<i>Processing Jutsu...</i>", reply_markup=None)
    player_total_stats = gl.get_total_stats(player_data) 
    base_damage = jutsu_info['power'] + (player_total_stats['intelligence'] * 2.5); damage_dealt = random.randint(int(base_damage * 0.9), int(base_damage * 1.1))
    is_crit = random.random() < 0.15; final_damage = int(damage_dealt * (2.5 if is_crit else 1.0)); damage_data = (final_damage, is_crit, False) 
    recoil_damage = int(player_total_stats['max_hp'] * boss_info['jutsu_recoil'])
    player_data['current_hp'] -= recoil_damage; player_data['current_chakra'] -= jutsu_info['chakra_cost']
    boss_defender_sim = {'username': boss_info['name'], 'village': 'none'} 
    jutsu_info_for_anim = {'name': jutsu_info['name'], 'signs': jutsu_info['signs'], 'element': jutsu_info['element']}
    await anim.battle_animation_flow(context, battle_state_for_anim, player_data, boss_defender_sim, jutsu_info_for_anim, damage_data)
    boss_defeated, new_boss_hp = _update_boss_and_player_damage(chat_id, user.id, player_data['username'], final_damage, boss_status)
    new_cooldown_time_iso = (datetime.datetime.now() + datetime.timedelta(seconds=JUTSU_COOLDOWN_SECONDS)).isoformat()
    player_updates = {'current_hp': max(1, player_data['current_hp']), 'current_chakra': player_data['current_chakra'], 'boss_attack_cooldown': new_cooldown_time_iso}
    db.update_player(user.id, player_updates)
    final_text = (f"{battle_state_for_anim['base_text']}\n\n" f"<i>🌀 You dealt {final_damage:,} Jutsu damage!</i>\n" f"<i>🩸 Recoil: Took {recoil_damage} damage.</i>")
    if player_data['current_hp'] <= 1: final_text += "\n😵 **You fainted!**"
    await anim.edit_battle_message(context, battle_state_for_anim, final_text, reply_markup=None); await asyncio.sleep(2.5) 
    if not boss_defeated:
         updated_boss_status = db.get_boss_status(chat_id)
         if updated_boss_status and updated_boss_status['is_active']: await send_or_edit_boss_message(context, chat_id, updated_boss_status, boss_info)
         else: boss_defeated = True 
    if boss_defeated:
         final_boss_status = db.get_boss_status(chat_id)
         await _process_boss_defeat(context, chat_id, final_boss_status if final_boss_status else boss_status, boss_info)
         if chat_id in ACTIVE_BOSS_MESSAGES: del ACTIVE_BOSS_MESSAGES[chat_id]

def _check_cooldown(player_data, cooldown_duration_seconds):
    # --- THIS IS THE FIX ---
    # The DB gives a datetime object or None, not a string
    cooldown_time = player_data.get('boss_attack_cooldown')
    # --- END OF FIX ---
    
    now = datetime.datetime.now(datetime.timezone.utc) # Use timezone-aware now
    
    if player_data.get('current_hp', 100) <= 1:
        lockout_duration = datetime.timedelta(hours=FAINT_LOCKOUT_HOURS)
        if cooldown_time: 
             # cooldown_time is the time the cooldown *ends*. The faint happened *before* this.
             faint_time = cooldown_time - datetime.timedelta(seconds=cooldown_duration_seconds) 
             # Make sure faint_time is timezone-aware for comparison
             if faint_time.tzinfo is None:
                 faint_time = faint_time.replace(tzinfo=datetime.timezone.utc)

             if now < (faint_time + lockout_duration):
                  remaining_lockout = (faint_time + lockout_duration) - now
                  return False, remaining_lockout.total_seconds()
        else: return False, lockout_duration.total_seconds() 
        
    if not cooldown_time: return True, 0 
    
    # Make sure cooldown_time is timezone-aware
    if cooldown_time.tzinfo is None:
        cooldown_time = cooldown_time.replace(tzinfo=datetime.timezone.utc)
    
    if now < cooldown_time: return False, (cooldown_time - now).total_seconds()
    else: return True, 0

def _update_boss_and_player_damage(chat_id, user_id, username, damage_dealt, current_boss_status):
    # --- THIS FUNCTION IS REWRITTEN FOR POSTGRESQL ---
    conn = db.get_db_connection(); 
    if conn is None: logger.error("DB connection failed..."); return False, current_boss_status['current_hp']
    
    new_boss_hp = 0; boss_defeated = False
    try:
        with conn.cursor() as cursor:
            # Lock the row for update to prevent race conditions
            cursor.execute("SELECT current_hp FROM world_boss_status WHERE chat_id = %s AND is_active = 1 FOR UPDATE", (chat_id,))
            current_hp_row = cursor.fetchone()
            
            if not current_hp_row: 
                 logger.warning(f"Boss in chat {chat_id} already defeated, damage from {user_id} not counted.")
                 conn.rollback() # Release the lock
                 return True, 0 
                 
            current_hp = current_hp_row[0]
            new_boss_hp = max(0, current_hp - damage_dealt)
            
            cursor.execute("UPDATE world_boss_status SET current_hp = %s WHERE chat_id = %s AND is_active = 1", (new_boss_hp, chat_id))
            
            cursor.execute(
                """INSERT INTO world_boss_damage (chat_id, user_id, username, total_damage) VALUES (%s, %s, %s, %s)
                   ON CONFLICT(chat_id, user_id) DO UPDATE SET total_damage = world_boss_damage.total_damage + %s, username = %s;""",
                (chat_id, user_id, username, damage_dealt, damage_dealt, username)
            )
            
        conn.commit()
        if new_boss_hp == 0: boss_defeated = True
    except (Exception, psycopg2.DatabaseError) as e: 
        logger.error(f"Error updating boss damage: {e}"); 
        conn.rollback(); 
        return False, current_boss_status['current_hp']
    finally: 
        db.put_db_connection(conn)
    return boss_defeated, new_boss_hp
    # --- END OF FIX ---

def _get_top_damage_dealers(chat_id, limit=5):
    # --- THIS FUNCTION IS REWRITTEN FOR POSTGRESQL ---
    conn = db.get_db_connection();
    if conn is None: return []
    try:
        with conn.cursor() as cursor: 
            cursor.execute("SELECT username, total_damage FROM world_boss_damage WHERE chat_id = %s ORDER BY total_damage DESC LIMIT %s", (chat_id, limit))
            rows = cursor.fetchall()
            # Use dict_factory logic manually
            fields = [column[0] for column in cursor.description]
            return [dict(zip(fields, row)) for row in rows]
    except (Exception, psycopg2.DatabaseError) as e: 
        logger.error(f"Error fetching top damage: {e}"); 
        return []
    finally: 
        db.put_db_connection(conn)
    # --- END OF FIX ---

async def _process_boss_defeat(context: ContextTypes.DEFAULT_TYPE, chat_id, boss_status, boss_info):
    # --- THIS FUNCTION IS REWRITTEN FOR POSTGRESQL ---
    logger.info(f"Boss defeated in chat {chat_id}!")
    await context.bot.send_message(chat_id=chat_id, text=f"🏆👹 **The {boss_info['name']} has been defeated!** 👹🏆", parse_mode="HTML")
    
    conn = db.get_db_connection(); 
    if conn is None: await context.bot.send_message(chat_id, "DB error during reward calculation."); return
    
    try:
         with conn.cursor() as cursor:
             cursor.execute("SELECT user_id, username, total_damage FROM world_boss_damage WHERE chat_id = %s ORDER BY total_damage DESC", (chat_id,))
             
             # Use dict_factory logic manually
             fields = [column[0] for column in cursor.description]
             all_damage = [dict(zip(fields, row)) for row in cursor.fetchall()]

             if not all_damage:
                await context.bot.send_message(chat_id, "No one damaged the boss? No rewards given.")
                cursor.execute("UPDATE world_boss_status SET is_active = 0, current_hp = 0 WHERE chat_id = %s", (chat_id,))
                cursor.execute("DELETE FROM world_boss_damage WHERE chat_id = %s", (chat_id,))
                conn.commit(); return
                
             total_ryo_pool = boss_status['ryo_pool']; rewards = {}; remaining_pool = total_ryo_pool
             reward_text_parts = ["<b>--- 💰 Reward Distribution 💰 ---</b>"]
             
             if len(all_damage) >= 1: amount = int(total_ryo_pool * 0.30); rewards[all_damage[0]['user_id']] = amount; remaining_pool -= amount; reward_text_parts.append(f"🥇 1st: {all_damage[0]['username']} (+{amount:,} Ryo)")
             if len(all_damage) >= 2: amount = int(total_ryo_pool * 0.20); rewards[all_damage[1]['user_id']] = rewards.get(all_damage[1]['user_id'], 0) + amount; remaining_pool -= amount; reward_text_parts.append(f"🥈 2nd: {all_damage[1]['username']} (+{amount:,} Ryo)")
             if len(all_damage) >= 3: amount = int(total_ryo_pool * 0.10); rewards[all_damage[2]['user_id']] = rewards.get(all_damage[2]['user_id'], 0) + amount; remaining_pool -= amount; reward_text_parts.append(f"🥉 3rd: {all_damage[2]['username']} (+{amount:,} Ryo)")
             
             participants = all_damage[3:]
             if participants and remaining_pool > 0:
                share = int(remaining_pool / len(participants))
                if share > 0:
                     reward_text_parts.append(f"\n🤝 Participation Reward: +{share:,} Ryo each!")
                     for participant in participants: rewards[participant['user_id']] = rewards.get(participant['user_id'], 0) + share
             elif remaining_pool > 0 and len(all_damage) < 3: # <3 players
                share = int(remaining_pool / len(all_damage))
                reward_text_parts.append(f"\n🤝 Extra Reward: +{share:,} Ryo each!")
                for player in all_damage: rewards[player['user_id']] = rewards.get(player['user_id'], 0) + share
             
             player_ids_to_update = list(rewards.keys())
             for user_id, ryo_gain in rewards.items():
                  cursor.execute("UPDATE players SET ryo = ryo + %s, boss_attack_cooldown = NULL WHERE user_id = %s", (ryo_gain, user_id))
             
             cursor.execute("UPDATE world_boss_status SET is_active = 0, current_hp = 0 WHERE chat_id = %s", (chat_id,))
             cursor.execute("DELETE FROM world_boss_damage WHERE chat_id = %s", (chat_id,))
             
         conn.commit()
         for user_id in player_ids_to_update: db.cache.clear_player_cache(user_id)
         await context.bot.send_message(chat_id, "\n".join(reward_text_parts), parse_mode="HTML")
         
    except (Exception, psycopg2.DatabaseError) as e: 
        logger.error(f"Error processing boss defeat: {e}"); 
        await context.bot.send_message(chat_id, "A database error occurred during reward distribution."); 
        conn.rollback()
    finally: 
        db.put_db_connection(conn)
    # --- END OF FIX ---

async def spawn_world_boss(context: ContextTypes.DEFAULT_TYPE):
    """Job function to check for and spawn world bosses."""
    # --- THIS FUNCTION IS REWRITTEN FOR POSTGRESQL ---
    logger.info("BOSS JOB: Running spawn check...")
    enabled_chat_ids = db.get_all_boss_chats() 
    if not enabled_chat_ids: 
        logger.info("BOSS JOB: No enabled chats."); 
        return
        
    for chat_id in enabled_chat_ids:
        boss_status = db.get_boss_status(chat_id)
        if boss_status and boss_status.get('is_active'):
            logger.info(f"BOSS JOB: Boss active in chat {chat_id}.") 
            boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
            if boss_info: 
                await send_or_edit_boss_message(context, chat_id, boss_status, boss_info) 
            continue 
            
        logger.info(f"BOSS JOB: Spawning new boss in chat {chat_id}...")
        boss_key = random.choice(list(gl.WORLD_BOSSES.keys()))
        boss_info = gl.WORLD_BOSSES[boss_key]
        spawn_time_utc = datetime.datetime.now(datetime.timezone.utc)
        
        conn = db.get_db_connection()
        if conn is None:
            logger.error(f"BOSS JOB: DB connection failed, skipping spawn for chat {chat_id}")
            continue
            
        try:
            with conn.cursor() as cursor:
                # Use INSERT ON CONFLICT DO UPDATE
                cursor.execute("""
                    INSERT INTO world_boss_status (chat_id, is_active, boss_key, current_hp, max_hp, ryo_pool, spawn_time) 
                    VALUES (%s, 1, %s, %s, %s, %s, %s)
                    ON CONFLICT (chat_id) DO UPDATE SET
                        is_active = 1,
                        boss_key = %s,
                        current_hp = %s,
                        max_hp = %s,
                        ryo_pool = %s,
                        spawn_time = %s
                """, 
                (chat_id, boss_key, boss_info['hp'], boss_info['hp'], boss_info['ryo_pool'], spawn_time_utc,
                 boss_key, boss_info['hp'], boss_info['hp'], boss_info['ryo_pool'], spawn_time_utc))
                
                cursor.execute("DELETE FROM world_boss_damage WHERE chat_id = %s", (chat_id,))
            conn.commit()
            logger.info(f"BOSS JOB: Spawn successful for {boss_info['name']} in chat {chat_id}")
        except (Exception, psycopg2.DatabaseError) as e: 
            logger.error(f"BOSS JOB: DB error spawning boss: {e}");
            conn.rollback()
        finally:
            db.put_db_connection(conn)
            
        new_boss_status = db.get_boss_status(chat_id)
        if new_boss_status and new_boss_status['is_active']:
            await send_or_edit_boss_message(context, chat_id, new_boss_status, boss_info)
            await asyncio.sleep(0.5) 
        else: 
             logger.error(f"BOSS JOB: Failed get status after spawn {chat_id}")
    logger.info("BOSS JOB: Finished spawn check.")
    # --- END OF FIX ---
