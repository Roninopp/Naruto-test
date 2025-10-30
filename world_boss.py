import logging
import json
import sqlite3
import datetime
import asyncio
import random
import time # For cooldown calculations

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatType

# Import our database, game logic, and ANIMATIONS
import database as db
import game_logic as gl
import animations as anim # <-- NEW IMPORT

logger = logging.getLogger(__name__)

# --- Constants ---
TAIJUTSU_COOLDOWN_SECONDS = 30
JUTSU_COOLDOWN_SECONDS = 180 # 3 minutes
FAINT_LOCKOUT_HOURS = 1
# Store active boss interaction messages {chat_id: message_id}
# We might need a more robust way later (like Redis or DB) if the bot restarts often
ACTIVE_BOSS_MESSAGES = {}

# --- Helper: Get Boss Battle Text ---
def get_boss_battle_text(boss_status, boss_info, chat_id):
    """Generates the text for the interactive boss battle message."""
    top_damage = _get_top_damage_dealers(chat_id, limit=3) # Get Top 3

    text = (
        f"👹 **{boss_info['name']}** Attacks! 👹\n\n"
        f"<b>HP:</b> {gl.health_bar(boss_status['current_hp'], boss_status['max_hp'])}\n"
        f"<b>Ryo Pool:</b> {boss_status['ryo_pool']:,} 💰\n\n"
        f"<b>⚔️ Top Attackers ⚔️</b>\n"
    )
    if not top_damage:
        text += "<i>No damage dealt yet.</i>\n"
    else:
        for i, entry in enumerate(top_damage):
            rank_emoji = ["🥇", "🥈", "🥉"][i]
            text += f"{rank_emoji} {entry['username']}: {entry['total_damage']:,}\n"

    text += "\nChoose your attack:"
    return text

# --- Helper: Send/Edit Boss Battle Message ---
async def send_or_edit_boss_message(context: ContextTypes.DEFAULT_TYPE, chat_id, boss_status, boss_info):
    """Sends a new interactive boss message or edits the existing one."""
    text = get_boss_battle_text(boss_status, boss_info, chat_id)
    
    # Buttons always enabled, cooldown check happens in callback
    keyboard = [
        [
            InlineKeyboardButton("⚔️ Taijutsu", callback_data="boss_action_taijutsu"),
            InlineKeyboardButton("🌀 Use Jutsu", callback_data="boss_action_jutsu"),
        ],
        [ InlineKeyboardButton("📊 Status Update", callback_data="boss_action_status") ] # Button to refresh
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_id = ACTIVE_BOSS_MESSAGES.get(chat_id)

    try:
        if message_id:
            await context.bot.edit_message_caption( # Edit caption of existing photo message
                chat_id=chat_id,
                message_id=message_id,
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        else:
            # If no message_id stored, or editing failed, send a new one
            message = await context.bot.send_photo(
                chat_id=chat_id,
                photo=open(boss_info['image'], 'rb'), # Resend photo
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            ACTIVE_BOSS_MESSAGES[chat_id] = message.message_id # Store new message ID
            logger.info(f"Sent new boss message for chat {chat_id}, msg_id: {message.message_id}")

    except Exception as e:
        logger.error(f"Error sending/editing boss message for chat {chat_id}: {e}")
        # If sending/editing fails, clear the stored message ID
        if chat_id in ACTIVE_BOSS_MESSAGES:
            del ACTIVE_BOSS_MESSAGES[chat_id]


# --- Admin Command (Enable Boss) --- unchanged ---
async def enable_world_boss_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (code is the same)
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

# --- Player Command (Boss Status - might be less needed now) ---
async def boss_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refreshes the interactive boss message."""
    chat_id = update.effective_chat.id
    boss_status = db.get_boss_status(chat_id)

    if not boss_status or not boss_status['is_active']:
        await update.message.reply_text("There is no active World Boss in this chat right now.")
        return

    boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
    if not boss_info:
        await update.message.reply_text("Error: Could not retrieve boss information.")
        return
        
    # --- NEW: Delete old message and resend ---
    # This ensures the message is always fresh and avoids editing issues
    old_message_id = ACTIVE_BOSS_MESSAGES.pop(chat_id, None)
    if old_message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=old_message_id)
        except Exception as e:
            logger.warning(f"Could not delete old boss message {old_message_id} in chat {chat_id}: {e}")
            
    await send_or_edit_boss_message(context, chat_id, boss_status, boss_info)
    # --- END NEW ---

# --- REMOVED /boss_taijutsu and /boss_jutsu COMMANDS ---
# We now use buttons

# --- Callback Handlers for Buttons ---

async def boss_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles main boss action buttons: Taijutsu, Jutsu, Status."""
    query = update.callback_query
    await query.answer() # Acknowledge tap immediately

    action = query.data.split('_')[-1] # taijutsu, jutsu, status
    user = query.from_user
    chat_id = query.message.chat_id
    player_data = db.get_player(user.id)
    
    # --- Basic Checks ---
    if not player_data:
        await query.answer("You need to /start your journey first!", show_alert=True)
        return

    boss_status = db.get_boss_status(chat_id)
    if not boss_status or not boss_status['is_active']:
        await query.answer("The World Boss is no longer active.", show_alert=True)
        # Try to clean up the message if possible
        try: await query.edit_message_reply_markup(reply_markup=None)
        except: pass
        return
        
    boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
    if not boss_info:
         await query.answer("Error finding boss info.", show_alert=True)
         return
         
    # --- Handle Status Update Button ---
    if action == "status":
        # Just refresh the message content without performing an attack
        await send_or_edit_boss_message(context, chat_id, boss_status, boss_info)
        return
        
    # --- Action is Taijutsu or Jutsu - Perform Checks ---
    
    # Faint Check
    if player_data['current_hp'] <= 1:
         await query.answer(f"😵 You are fainted and locked out! Recover first.", show_alert=True)
         return
         
    # Cooldown Check
    cooldown_seconds = TAIJUTSU_COOLDOWN_SECONDS if action == "taijutsu" else JUTSU_COOLDOWN_SECONDS
    cooldown_check, remaining_seconds = _check_cooldown(player_data, cooldown_seconds)
    if not cooldown_check:
        time_unit = "seconds"
        time_val = remaining_seconds
        if cooldown_seconds == JUTSU_COOLDOWN_SECONDS:
             time_unit = "minutes"
             time_val = remaining_seconds / 60
        await query.answer(f"⏳ On cooldown! Wait {time_val:.1f} {time_unit}.", show_alert=True)
        return

    # --- Process Attack Actions ---
    
    # Store necessary info for animations/updates
    battle_state_for_anim = {
        'chat_id': chat_id,
        'message_id': query.message.message_id,
        'base_text': get_boss_battle_text(boss_status, boss_info, chat_id).split("\n\nChoose your attack:")[0],
        'players': {user.id: player_data}, # Simplified structure for anim funcs
        'turn': user.id # Attacker is always the user
    }
    
    # Disable buttons during animation by editing caption
    await anim.edit_battle_message(context, battle_state_for_anim, f"{battle_state_for_anim['base_text']}\n\n<i>Processing attack...</i>", reply_markup=None)

    player_total_stats = gl.get_total_stats(player_data)
    new_boss_hp = boss_status['current_hp'] # Start with current HP
    boss_defeated = False

    if action == "taijutsu":
        # Damage Calculation
        base_damage = player_total_stats['strength'] * 2
        damage_dealt = random.randint(int(base_damage * 0.8), int(base_damage * 1.2))
        is_crit = random.random() < 0.1
        final_damage = int(damage_dealt * (2.0 if is_crit else 1.0))
        
        # Recoil Calculation
        recoil_damage = int(player_total_stats['max_hp'] * boss_info['taijutsu_recoil'])
        player_data['current_hp'] -= recoil_damage
        
        # --- Play Animation ---
        # Simulate defender for animation function (boss doesn't need full stats here)
        boss_defender_sim = {'username': boss_info['name'], 'current_hp': boss_status['current_hp'], 'max_hp': boss_status['max_hp']}
        await anim.animate_taijutsu(context, battle_state_for_anim, player_data, boss_defender_sim, final_damage, is_crit)
        
        # Update Database
        boss_defeated, new_boss_hp = _update_boss_and_player_damage(chat_id, user.id, player_data['username'], final_damage, boss_status)
        new_cooldown_time = (datetime.datetime.now() + datetime.timedelta(seconds=TAIJUTSU_COOLDOWN_SECONDS)).isoformat()
        player_updates = {'current_hp': max(1, player_data['current_hp']), 'boss_attack_cooldown': new_cooldown_time}
        db.update_player(user.id, player_updates)
        
        # Post-animation message update
        final_text = (f"{battle_state_for_anim['base_text']}\n\n"
                      f"<i>⚔️ You dealt {final_damage:,} Taijutsu damage!</i>\n"
                      f"<i>🩸 Recoil: Took {recoil_damage} damage.</i>")
        if player_data['current_hp'] <= 1: final_text += "\n😵 **You fainted!**"
        await anim.edit_battle_message(context, battle_state_for_anim, final_text, reply_markup=None)
        await asyncio.sleep(2.5) # Pause to read

    elif action == "jutsu":
        # Check level first (as per PvP logic)
        if player_data['level'] < 5: # Assuming level 5 for first jutsu
             await query.answer("You need Level 5+ to use Jutsus!", show_alert=True)
             # Reshow menu
             await send_or_edit_boss_message(context, chat_id, boss_status, boss_info)
             return

        # Show Jutsu selection menu
        try: known_jutsus_list = json.loads(player_data['known_jutsus'])
        except: known_jutsus_list = []
        if not known_jutsus_list:
            await query.answer("You don't know any Jutsus!", show_alert=True)
            await send_or_edit_boss_message(context, chat_id, boss_status, boss_info) # Reshow menu
            return

        keyboard = []
        available_jutsus = 0
        for jutsu_key in known_jutsus_list:
            jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_key)
            if jutsu_info:
                if player_data['current_chakra'] >= jutsu_info['chakra_cost']:
                    button_text = f"{jutsu_info['name']} ({jutsu_info['chakra_cost']} Chakra)"
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=f"boss_usejutsu_{jutsu_key}")])
                    available_jutsus += 1
                else:
                    button_text = f"🚫 {jutsu_info['name']} ({jutsu_info['chakra_cost']} Chakra)"
                    keyboard.append([InlineKeyboardButton(button_text, callback_data="boss_nochakra")]) # Specific callback for no chakra
        
        if available_jutsus == 0:
             await query.answer("Not enough Chakra for any Jutsu!", show_alert=True)
             await send_or_edit_boss_message(context, chat_id, boss_status, boss_info) # Reshow menu
             return

        keyboard.append([InlineKeyboardButton("Cancel", callback_data="boss_usejutsu_cancel")])
        await anim.edit_battle_message(context, battle_state_for_anim, f"{battle_state_for_anim['base_text']}\n\nSelect a Jutsu:", reply_markup=InlineKeyboardMarkup(keyboard))
        return # Jutsu selection happens in boss_jutsu_callback

    # --- Update message after action (unless Jutsu selection) ---
    if not boss_defeated and action != "jutsu":
         # Fetch updated boss status AFTER damage/updates
         updated_boss_status = db.get_boss_status(chat_id)
         if updated_boss_status and updated_boss_status['is_active']:
              await send_or_edit_boss_message(context, chat_id, updated_boss_status, boss_info)
         else: # Boss might have been defeated by someone else during animation
              boss_defeated = True # Trigger defeat processing

    if boss_defeated:
         # Fetch final status one last time before processing defeat
         final_boss_status = db.get_boss_status(chat_id)
         await _process_boss_defeat(context, chat_id, final_boss_status if final_boss_status else boss_status, boss_info)
         # Clear message ID cache after defeat
         if chat_id in ACTIVE_BOSS_MESSAGES: del ACTIVE_BOSS_MESSAGES[chat_id]


async def boss_jutsu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the selection of a specific Jutsu to use against the boss."""
    query = update.callback_query
    
    user = query.from_user
    chat_id = query.message.chat_id
    player_data = db.get_player(user.id)

    if not player_data: await query.answer("Error: Player data not found.", show_alert=True); return

    parts = query.data.split('_'); jutsu_key = parts[-1]

    if jutsu_key == "cancel":
        await query.answer() # Answer silently
        # Edit back to the main action menu
        boss_status = db.get_boss_status(chat_id)
        if boss_status and boss_status['is_active']:
             boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
             if boss_info: await send_or_edit_boss_message(context, chat_id, boss_status, boss_info)
        else: await query.edit_message_caption(caption="Boss fight ended.", reply_markup=None) # Clean up if boss gone
        return
        
    if jutsu_key == "nochakra":
        await query.answer("You don't have enough Chakra for that Jutsu!", show_alert=True)
        return # Do nothing, let user choose again or cancel

    jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_key)
    if not jutsu_info:
        await query.answer("Error: Invalid Jutsu selected.", show_alert=True)
        return

    # Re-check chakra, cooldown, faint status
    if player_data['current_chakra'] < jutsu_info['chakra_cost']:
        await query.answer("Not enough Chakra!", show_alert=True); return
        
    cooldown_check, remaining_seconds = _check_cooldown(player_data, JUTSU_COOLDOWN_SECONDS)
    if not cooldown_check:
        await query.answer(f"⏳ On Jutsu cooldown! Wait {remaining_seconds / 60:.1f} minutes.", show_alert=True); return
        
    if player_data['current_hp'] <= 1:
         await query.answer(f"😵 You are fainted! Cannot use Jutsu.", show_alert=True); return

    boss_status = db.get_boss_status(chat_id)
    if not boss_status or not boss_status['is_active']:
        await query.answer("The World Boss was defeated before you could attack!", show_alert=True)
        await query.edit_message_caption(caption="Boss fight ended.", reply_markup=None)
        return
        
    boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
    if not boss_info: await query.answer("Error finding boss info.", show_alert=True); return

    # --- Perform Jutsu Attack ---
    await query.answer() # Answer silently
    
    battle_state_for_anim = {
        'chat_id': chat_id, 'message_id': query.message.message_id,
        'base_text': get_boss_battle_text(boss_status, boss_info, chat_id).split("\n\nChoose your attack:")[0],
        'players': {user.id: player_data}, 'turn': user.id
    }
    await anim.edit_battle_message(context, battle_state_for_anim, f"{battle_state_for_anim['base_text']}\n\n<i>Processing Jutsu...</i>", reply_markup=None)

    player_total_stats = gl.get_total_stats(player_data)

    # Damage Calculation (Jutsu vs Boss - simple version)
    base_damage = jutsu_info['power'] + (player_total_stats['intelligence'] * 2.5)
    damage_dealt = random.randint(int(base_damage * 0.9), int(base_damage * 1.1))
    is_crit = random.random() < 0.15
    final_damage = int(damage_dealt * (2.5 if is_crit else 1.0))
    damage_data = (final_damage, is_crit, False) # Last bool is is_super_eff (False for boss)

    # Recoil Calculation
    recoil_damage = int(player_total_stats['max_hp'] * boss_info['jutsu_recoil'])
    player_data['current_hp'] -= recoil_damage
    player_data['current_chakra'] -= jutsu_info['chakra_cost']

    # --- Play Animation ---
    boss_defender_sim = {'username': boss_info['name'], 'current_hp': boss_status['current_hp'], 'max_hp': boss_status['max_hp'], 'village': 'none'}
    # Pass a simplified jutsu_info dict for animation
    jutsu_info_for_anim = {'name': jutsu_info['name'], 'signs': jutsu_info['signs'], 'element': jutsu_info['element']}
    await anim.battle_animation_flow(context, battle_state_for_anim, player_data, boss_defender_sim, jutsu_info_for_anim, damage_data)

    # Update Database
    boss_defeated, new_boss_hp = _update_boss_and_player_damage(chat_id, user.id, player_data['username'], final_damage, boss_status)
    new_cooldown_time = (datetime.datetime.now() + datetime.timedelta(seconds=JUTSU_COOLDOWN_SECONDS)).isoformat()
    player_updates = {
        'current_hp': max(1, player_data['current_hp']),
        'current_chakra': player_data['current_chakra'],
        'boss_attack_cooldown': new_cooldown_time
    }
    db.update_player(user.id, player_updates)

    # Post-animation message update
    final_text = (f"{battle_state_for_anim['base_text']}\n\n"
                  f"<i>🌀 You dealt {final_damage:,} Jutsu damage!</i>\n"
                  f"<i>🩸 Recoil: Took {recoil_damage} damage.</i>")
    if player_data['current_hp'] <= 1: final_text += "\n😵 **You fainted!**"
    await anim.edit_battle_message(context, battle_state_for_anim, final_text, reply_markup=None)
    await asyncio.sleep(2.5) # Pause to read

    # --- Update message after action ---
    if not boss_defeated:
         updated_boss_status = db.get_boss_status(chat_id)
         if updated_boss_status and updated_boss_status['is_active']:
              await send_or_edit_boss_message(context, chat_id, updated_boss_status, boss_info)
         else: boss_defeated = True # Boss might have been defeated

    if boss_defeated:
         final_boss_status = db.get_boss_status(chat_id)
         await _process_boss_defeat(context, chat_id, final_boss_status if final_boss_status else boss_status, boss_info)
         if chat_id in ACTIVE_BOSS_MESSAGES: del ACTIVE_BOSS_MESSAGES[chat_id]


# --- Helper Functions (unchanged) ---

def _check_cooldown(player_data, cooldown_duration_seconds):
    # (code is the same)
    cooldown_str = player_data.get('boss_attack_cooldown')
    if not cooldown_str: return True, 0
    cooldown_time = datetime.datetime.fromisoformat(cooldown_str); now = datetime.datetime.now()
    if player_data.get('current_hp', 100) <= 1:
        lockout_duration = datetime.timedelta(hours=FAINT_LOCKOUT_HOURS)
        faint_time = cooldown_time - datetime.timedelta(seconds=cooldown_duration_seconds) # Approx faint time
        if now < (faint_time + lockout_duration):
             remaining_lockout = (faint_time + lockout_duration) - now
             return False, remaining_lockout.total_seconds()
    if now < cooldown_time: return False, (cooldown_time - now).total_seconds()
    else: return True, 0

def _update_boss_and_player_damage(chat_id, user_id, username, damage_dealt, current_boss_status):
    # (code is the same)
    conn = db.get_db_connection();
    if conn is None: logger.error("DB connection failed during boss update."); return False, current_boss_status['current_hp']
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
    except sqlite3.Error as e: logger.error(f"Error updating boss/player damage for chat {chat_id}, user {user_id}: {e}"); conn.rollback(); return False, current_boss_status['current_hp']
    finally: conn.close()
    return boss_defeated, new_boss_hp

def _get_top_damage_dealers(chat_id, limit=5):
    # (code is the same)
    conn = db.get_db_connection();
    if conn is None: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT username, total_damage FROM world_boss_damage WHERE chat_id = ? ORDER BY total_damage DESC LIMIT ?", (chat_id, limit))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e: logger.error(f"Error fetching top damage for chat {chat_id}: {e}"); return []
    finally: conn.close()

async def _process_boss_defeat(context: ContextTypes.DEFAULT_TYPE, chat_id, boss_status, boss_info):
    # (code is the same)
    logger.info(f"World Boss {boss_info['name']} defeated in chat {chat_id}!")
    await context.bot.send_message(chat_id=chat_id, text=f"🏆👹 **The {boss_info['name']} has been defeated!** 👹🏆", parse_mode="HTML")
    conn = db.get_db_connection()
    if conn is None: await context.bot.send_message(chat_id, "DB error during reward calculation."); return
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, total_damage FROM world_boss_damage WHERE chat_id = ? ORDER BY total_damage DESC", (chat_id,))
        all_damage = [dict(row) for row in cursor.fetchall()]
        if not all_damage:
            await context.bot.send_message(chat_id, "No one damaged the boss? No rewards given.")
            cursor.execute("UPDATE world_boss_status SET is_active = 0, current_hp = 0 WHERE chat_id = ?", (chat_id,))
            cursor.execute("DELETE FROM world_boss_damage WHERE chat_id = ?", (chat_id,))
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
        elif remaining_pool > 0 and len(all_damage) < 3:
            share = int(remaining_pool / len(all_damage))
            reward_text_parts.append(f"\n🤝 Extra Reward: +{share:,} Ryo each!")
            for player in all_damage: rewards[player['user_id']] += share
        player_ids_to_update = list(rewards.keys())
        for user_id, ryo_gain in rewards.items():
            cursor.execute("UPDATE players SET ryo = ryo + ?, boss_attack_cooldown = NULL WHERE user_id = ?", (ryo_gain, user_id))
        cursor.execute("UPDATE world_boss_status SET is_active = 0, current_hp = 0 WHERE chat_id = ?", (chat_id,))
        cursor.execute("DELETE FROM world_boss_damage WHERE chat_id = ?", (chat_id,))
        conn.commit()
        for user_id in player_ids_to_update: db.cache.clear_player_cache(user_id)
        await context.bot.send_message(chat_id, "\n".join(reward_text_parts), parse_mode="HTML")
    except sqlite3.Error as e: logger.error(f"Error processing boss defeat for chat {chat_id}: {e}"); await context.bot.send_message(chat_id, "A database error occurred during reward distribution."); conn.rollback()
    finally: conn.close()

# --- NEW: Spawn World Boss Function (from main.py) ---
# Moved here to keep boss logic together
async def spawn_world_boss(context: ContextTypes.DEFAULT_TYPE):
    logger.info("BOSS JOB: Running spawn check...")
    enabled_chat_ids = db.get_all_boss_chats() # Assuming this is correct in db.py
    if not enabled_chat_ids:
        logger.info("BOSS JOB: No enabled chats. Skipping spawn.")
        return

    for chat_id in enabled_chat_ids:
        # Check if boss already active for this chat
        boss_status = db.get_boss_status(chat_id)
        if boss_status and boss_status.get('is_active'):
            logger.info(f"BOSS JOB: Boss already active in chat {chat_id}. Skipping.")
            # Maybe refresh the message if needed?
            boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
            if boss_info:
                 await send_or_edit_boss_message(context, chat_id, boss_status, boss_info)
            continue # Skip spawning

        logger.info(f"BOSS JOB: Spawning new boss in chat {chat_id}...")
        boss_key = random.choice(list(gl.WORLD_BOSSES.keys()))
        boss_info = gl.WORLD_BOSSES[boss_key]
        spawn_time_iso = datetime.datetime.now().isoformat()
        
        # Update boss status in DB
        conn = db.get_db_connection()
        try:
            cursor = conn.cursor()
            # Use INSERT OR REPLACE to handle new chats added to status table
            cursor.execute(
                """
                INSERT OR REPLACE INTO world_boss_status 
                (chat_id, is_active, boss_key, current_hp, max_hp, ryo_pool, spawn_time)
                VALUES (?, 1, ?, ?, ?, ?, ?)
                """,
                (chat_id, boss_key, boss_info['hp'], boss_info['hp'], boss_info['ryo_pool'], spawn_time_iso)
            )
            # Clear old damage data for this chat
            cursor.execute("DELETE FROM world_boss_damage WHERE chat_id = ?", (chat_id,))
            conn.commit()
            logger.info(f"BOSS JOB: Spawn successful for {boss_info['name']} in chat {chat_id}")
        except sqlite3.Error as e:
            logger.error(f"BOSS JOB: DB error spawning boss in chat {chat_id}: {e}")
            if conn: conn.rollback()
            continue # Skip this chat if DB error
        finally:
            if conn: conn.close()

        # Get the newly saved status to pass to the message function
        new_boss_status = db.get_boss_status(chat_id)
        if new_boss_status and new_boss_status['is_active']:
            # Send the initial interactive message
            await send_or_edit_boss_message(context, chat_id, new_boss_status, boss_info)
            await asyncio.sleep(0.5) # Small delay between chats
        else:
             logger.error(f"BOSS JOB: Failed to get status immediately after spawning boss in chat {chat_id}")

    logger.info("BOSS JOB: Finished spawn check for all chats.")
