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

# Import our database and game_logic functions
import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Constants for Cooldowns ---
TAIJUTSU_COOLDOWN_SECONDS = 30
JUTSU_COOLDOWN_SECONDS = 180 # 3 minutes
FAINT_LOCKOUT_HOURS = 1

# --- Admin Command ---

async def enable_world_boss_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enables the world boss spawns for this group."""
    chat = update.effective_chat
    user = update.effective_user

    # 1. Check if the command is used in a group or supergroup
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.message.reply_text("This command can only be used in a group chat.")
        return

    # 2. Check if the user is an admin or the group creator
    try:
        chat_admins = await context.bot.get_chat_administrators(chat.id)
        user_ids = [admin.user.id for admin in chat_admins]

        if user.id not in user_ids:
            await update.message.reply_text("You must be a group admin to use this command.")
            return

    except Exception as e:
        logger.error(f"Error checking admin status in chat {chat.id}: {e}")
        await update.message.reply_text("An error occurred. I might not have permission to see group admins.")
        return

    # 3. If admin, add the chat to the database
    success = db.enable_boss_chat(chat.id, user.id)

    if success:
        logger.info(f"World Boss game enabled for chat {chat.id} by user {user.id}")
        await update.message.reply_text(
            "✅ 👹 **World Boss Enabled!** 👹 ✅\n\n"
            "This group will now be included in World Boss spawns.\n"
            "The next boss will appear on the next scheduled spawn (every 6 hours).",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("A database error occurred. Please try again.")


# --- Player Commands ---

async def boss_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the current status of the world boss in this chat."""
    chat_id = update.effective_chat.id
    boss_status = db.get_boss_status(chat_id)

    if not boss_status or not boss_status['is_active']:
        await update.message.reply_text("There is no active World Boss in this chat right now.")
        return

    boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
    if not boss_info:
        await update.message.reply_text("Error: Could not retrieve boss information.")
        logger.error(f"Boss key mismatch in status for chat {chat_id}: {boss_status['boss_key']}")
        return

    # Get Top 5 Damage Dealers
    top_damage = _get_top_damage_dealers(chat_id, limit=5)

    status_text = (
        f"👹 --- **World Boss Status** --- 👹\n\n"
        f"<b>Boss:</b> {boss_info['name']}\n"
        f"<b>HP:</b> {gl.health_bar(boss_status['current_hp'], boss_status['max_hp'])}\n\n"
        f"<b>⚔️ Top Damage Dealers ⚔️</b>\n"
    )

    if not top_damage:
        status_text += "<i>No damage dealt yet. Be the first!</i>"
    else:
        for i, entry in enumerate(top_damage):
            status_text += f"{i+1}. {entry['username']}: {entry['total_damage']:,} damage\n" # Format with commas

    await update.message.reply_text(status_text, parse_mode="HTML")


async def boss_taijutsu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the player's Taijutsu attack against the boss."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    player_data = db.get_player(user.id)

    if not player_data:
        await update.message.reply_text("You must /start your journey first.")
        return

    # Check for active boss
    boss_status = db.get_boss_status(chat_id)
    if not boss_status or not boss_status['is_active']:
        await update.message.reply_text("There is no active World Boss to attack.")
        return

    # --- Cooldown Check ---
    cooldown_check, remaining_seconds = _check_cooldown(player_data, TAIJUTSU_COOLDOWN_SECONDS)
    if not cooldown_check:
        await update.message.reply_text(f"⏳ You are recovering. You can use Taijutsu again in **{remaining_seconds:.0f}** seconds.", parse_mode="HTML")
        return
    # --- End Cooldown Check ---

    # --- Faint Check ---
    if player_data['current_hp'] <= 1:
         await update.message.reply_text(f"😵 You are too injured to fight! You need to recover.")
         return
    # --- End Faint Check ---

    boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
    player_total_stats = gl.get_total_stats(player_data)

    # --- Damage Calculation ---
    base_damage = player_total_stats['strength'] * 2
    # Add randomness (+/- 20%)
    damage_dealt = random.randint(int(base_damage * 0.8), int(base_damage * 1.2))
    is_crit = random.random() < 0.1 # 10% critical chance for Taijutsu
    crit_multiplier = 2.0 if is_crit else 1.0
    final_damage = int(damage_dealt * crit_multiplier)
    # --- End Damage Calculation ---

    # --- Recoil Calculation ---
    recoil_percent = boss_info['taijutsu_recoil']
    recoil_damage = int(player_total_stats['max_hp'] * recoil_percent)
    player_data['current_hp'] -= recoil_damage
    # --- End Recoil Calculation ---

    # --- Update Database & Check for Defeat ---
    boss_defeated, new_boss_hp = _update_boss_and_player_damage(
        chat_id, user.id, player_data['username'], final_damage, boss_status
    )

    # --- Set Cooldown ---
    new_cooldown_time = (datetime.datetime.now() + datetime.timedelta(seconds=TAIJUTSU_COOLDOWN_SECONDS)).isoformat()
    player_updates = {
        'current_hp': max(1, player_data['current_hp']), # HP cannot go below 1 (Fainted)
        'boss_attack_cooldown': new_cooldown_time
    }
    db.update_player(user.id, player_updates)
    # --- End Set Cooldown ---

    # --- Send Reply ---
    reply_text = (
        f"🥋 **{player_data['username']}** attacks the **{boss_info['name']}**! 🥋\n\n"
    )
    if is_crit:
        reply_text += f"💥 **CRITICAL HIT!** 💥\n"
    reply_text += (
        f"You dealt **{final_damage:,}** Taijutsu damage!\n"
        f"<i>The {boss_info['name']} counters! You take **{recoil_damage}** damage.</i>\n\n"
        f"**Boss HP:** {gl.health_bar(new_boss_hp, boss_status['max_hp'])}\n"
        f"Your HP: {gl.health_bar(player_data['current_hp'], player_total_stats['max_hp'])}"
    )
    if player_data['current_hp'] <= 1:
        reply_text += f"\n\n😵 **You fainted!** You are locked out of the fight for {FAINT_LOCKOUT_HOURS} hour."

    await update.message.reply_text(reply_text, parse_mode="HTML")
    # --- End Send Reply ---

    # --- Handle Boss Defeat ---
    if boss_defeated:
        await _process_boss_defeat(context, chat_id, boss_status, boss_info)
    # --- End Handle Boss Defeat ---


async def boss_jutsu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the player's known jutsus to use against the boss."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    player_data = db.get_player(user.id)

    if not player_data:
        await update.message.reply_text("You must /start your journey first.")
        return

    # Check for active boss
    boss_status = db.get_boss_status(chat_id)
    if not boss_status or not boss_status['is_active']:
        await update.message.reply_text("There is no active World Boss to attack.")
        return

    # --- Cooldown Check ---
    cooldown_check, remaining_seconds = _check_cooldown(player_data, JUTSU_COOLDOWN_SECONDS)
    if not cooldown_check:
        await update.message.reply_text(f"⏳ Your chakra needs to recharge. You can use Jutsu again in **{remaining_seconds / 60:.1f}** minutes.", parse_mode="HTML")
        return
    # --- End Cooldown Check ---

    # --- Faint Check ---
    if player_data['current_hp'] <= 1:
         await update.message.reply_text(f"😵 You are too injured to use Jutsu!")
         return
    # --- End Faint Check ---

    # --- Get Known Jutsus ---
    try:
        known_jutsus_list = json.loads(player_data['known_jutsus'])
    except json.JSONDecodeError:
        known_jutsus_list = []

    if not known_jutsus_list:
        await update.message.reply_text("You don't know any Jutsus! Use `/combine` to learn some.")
        return
    # --- End Get Known Jutsus ---

    # --- Build Buttons ---
    keyboard = []
    available_jutsus = 0
    for jutsu_key in known_jutsus_list:
        jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_key)
        if jutsu_info:
            # Check if player has enough chakra
            if player_data['current_chakra'] >= jutsu_info['chakra_cost']:
                button_text = f"{jutsu_info['name']} ({jutsu_info['chakra_cost']} Chakra)"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"boss_usejutsu_{jutsu_key}")])
                available_jutsus += 1
            else:
                # Show disabled button if not enough chakra
                button_text = f"🚫 {jutsu_info['name']} ({jutsu_info['chakra_cost']} Chakra)"
                keyboard.append([InlineKeyboardButton(button_text, callback_data="boss_nochakra")])

    if available_jutsus == 0:
         await update.message.reply_text("You don't have enough Chakra to use any of your Jutsus!")
         return

    keyboard.append([InlineKeyboardButton("Cancel", callback_data="boss_usejutsu_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select a Jutsu to use against the boss:", reply_markup=reply_markup)
    # --- End Build Buttons ---


# --- Callback Handlers ---

async def boss_jutsu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the button press for using a specific jutsu."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    chat_id = query.message.chat_id
    player_data = db.get_player(user.id)

    if not player_data:
        await query.edit_message_text("Error: Could not find your player data.")
        return

    parts = query.data.split('_')
    jutsu_key = parts[-1] # e.g., "fireball" or "cancel" or "nochakra"

    if jutsu_key == "cancel":
        await query.edit_message_text("Attack cancelled.")
        return
    if jutsu_key == "nochakra":
        await query.answer("Not enough Chakra for this Jutsu!", show_alert=True)
        # Re-show the menu in case chakra regenerated slightly
        await query.delete_message()
        await boss_jutsu_command(update, context) # Resend original command
        return

    jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_key)
    if not jutsu_info:
        await query.edit_message_text("Error: Invalid Jutsu selected.")
        return

    # Double-check chakra (in case it changed since buttons were shown)
    if player_data['current_chakra'] < jutsu_info['chakra_cost']:
        await query.answer("Not enough Chakra!", show_alert=True)
        await query.edit_message_text("Your chakra depleted before you could attack!")
        return

    # --- Perform the Attack ---
    await query.edit_message_text(f"🌀 Preparing {jutsu_info['name']}...") # Placeholder before actual attack

    # Check for active boss (again, in case it was defeated)
    boss_status = db.get_boss_status(chat_id)
    if not boss_status or not boss_status['is_active']:
        await query.edit_message_text("The World Boss was defeated before you could attack!")
        return

    # Check Cooldown (Important!)
    cooldown_check, remaining_seconds = _check_cooldown(player_data, JUTSU_COOLDOWN_SECONDS)
    if not cooldown_check:
        await query.edit_message_text(f"⏳ Your chakra needs to recharge. You can use Jutsu again in **{remaining_seconds / 60:.1f}** minutes.", parse_mode="HTML")
        return

    # Check Faint
    if player_data['current_hp'] <= 1:
         await query.edit_message_text(f"😵 You are too injured to use Jutsu!")
         return

    boss_info = gl.WORLD_BOSSES.get(boss_status['boss_key'])
    player_total_stats = gl.get_total_stats(player_data)

    # --- Damage Calculation ---
    # We use a simplified version here, focusing on Intelligence
    base_damage = jutsu_info['power'] + (player_total_stats['intelligence'] * 2.5)
    damage_dealt = random.randint(int(base_damage * 0.9), int(base_damage * 1.1)) # +/- 10%
    is_crit = random.random() < 0.15 # 15% critical chance for Jutsu
    crit_multiplier = 2.5 if is_crit else 1.0
    final_damage = int(damage_dealt * crit_multiplier)
    # --- End Damage Calculation ---

    # --- Recoil Calculation ---
    recoil_percent = boss_info['jutsu_recoil']
    recoil_damage = int(player_total_stats['max_hp'] * recoil_percent)
    player_data['current_hp'] -= recoil_damage
    player_data['current_chakra'] -= jutsu_info['chakra_cost']
    # --- End Recoil Calculation ---

    # --- Update Database & Check for Defeat ---
    boss_defeated, new_boss_hp = _update_boss_and_player_damage(
        chat_id, user.id, player_data['username'], final_damage, boss_status
    )

    # --- Set Cooldown ---
    new_cooldown_time = (datetime.datetime.now() + datetime.timedelta(seconds=JUTSU_COOLDOWN_SECONDS)).isoformat()
    player_updates = {
        'current_hp': max(1, player_data['current_hp']),
        'current_chakra': player_data['current_chakra'],
        'boss_attack_cooldown': new_cooldown_time
    }
    db.update_player(user.id, player_updates)
    # --- End Set Cooldown ---

    # --- Send Reply ---
    reply_text = (
        f"🌀 **{player_data['username']}** uses **{jutsu_info['name']}** against the **{boss_info['name']}**! 🌀\n\n"
    )
    # Add simple element animation emoji
    element_emoji = {'fire':'🔥', 'water':'💧', 'wind':'💨', 'earth':'⛰️', 'lightning':'⚡'}.get(jutsu_info['element'], '💥')
    reply_text += f"{element_emoji} {jutsu_info['element'].title()} Style! {element_emoji}\n"
    if is_crit:
        reply_text += f"💥 **CRITICAL HIT!** 💥\n"
    reply_text += (
        f"The boss takes **{final_damage:,}** Jutsu damage!\n"
        f"<i>The {boss_info['name']} counters fiercely! You take **{recoil_damage}** damage.</i>\n\n"
        f"**Boss HP:** {gl.health_bar(new_boss_hp, boss_status['max_hp'])}\n"
        f"Your HP: {gl.health_bar(player_data['current_hp'], player_total_stats['max_hp'])}\n"
        f"Your Chakra: {gl.chakra_bar(player_data['current_chakra'], player_total_stats['max_chakra'])}"
    )
    if player_data['current_hp'] <= 1:
        reply_text += f"\n\n😵 **You fainted!** You are locked out of the fight for {FAINT_LOCKOUT_HOURS} hour."

    # Use reply_text on the original message context
    await query.message.reply_text(reply_text, parse_mode="HTML")
    # --- End Send Reply ---

    # --- Handle Boss Defeat ---
    if boss_defeated:
        await _process_boss_defeat(context, chat_id, boss_status, boss_info)
    # --- End Handle Boss Defeat ---


# --- Helper Functions ---

def _check_cooldown(player_data, cooldown_duration_seconds):
    """Checks if the player's boss attack cooldown has passed."""
    cooldown_str = player_data.get('boss_attack_cooldown')
    if not cooldown_str:
        return True, 0 # No cooldown set, can attack

    cooldown_time = datetime.datetime.fromisoformat(cooldown_str)
    now = datetime.datetime.now()

    # --- Faint Lockout Check ---
    # If HP is 1, check if the FAINT_LOCKOUT_HOURS has passed since the cooldown was set
    if player_data.get('current_hp', 100) <= 1:
        lockout_duration = datetime.timedelta(hours=FAINT_LOCKOUT_HOURS)
        if now < (cooldown_time + lockout_duration - datetime.timedelta(seconds=cooldown_duration_seconds)): # Compare faint time to original cooldown time
             remaining_lockout = (cooldown_time + lockout_duration) - now
             return False, remaining_lockout.total_seconds()
        else:
             # Lockout is over, but cooldown might still be active
             pass # Continue to normal cooldown check
    # --- End Faint Lockout Check ---


    if now < cooldown_time:
        remaining = cooldown_time - now
        return False, remaining.total_seconds()
    else:
        return True, 0


def _update_boss_and_player_damage(chat_id, user_id, username, damage_dealt, current_boss_status):
    """
    Updates boss HP and player damage in the database transactionally.
    Returns (boss_defeated, new_boss_hp).
    """
    conn = db.get_db_connection()
    if conn is None:
        logger.error("Database connection failed during boss update.")
        return False, current_boss_status['current_hp'] # Return old HP

    new_boss_hp = 0
    boss_defeated = False
    try:
        cursor = conn.cursor()

        # Update Boss HP
        new_boss_hp = max(0, current_boss_status['current_hp'] - damage_dealt)
        cursor.execute(
            "UPDATE world_boss_status SET current_hp = ? WHERE chat_id = ? AND is_active = 1",
            (new_boss_hp, chat_id)
        )

        # Update Player Damage (Insert or Update)
        cursor.execute(
            """
            INSERT INTO world_boss_damage (chat_id, user_id, username, total_damage)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
            total_damage = total_damage + excluded.total_damage,
            username = excluded.username;
            """,
            (chat_id, user_id, username, damage_dealt)
        )

        conn.commit()

        if new_boss_hp == 0:
            boss_defeated = True

    except sqlite3.Error as e:
        logger.error(f"Error updating boss/player damage for chat {chat_id}, user {user_id}: {e}")
        conn.rollback() # Important: undo changes on error
        return False, current_boss_status['current_hp'] # Return old HP on error
    finally:
        conn.close()

    return boss_defeated, new_boss_hp


def _get_top_damage_dealers(chat_id, limit=5):
    """Gets the top damage dealers for the current boss in a chat."""
    conn = db.get_db_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT username, total_damage FROM world_boss_damage WHERE chat_id = ? ORDER BY total_damage DESC LIMIT ?",
            (chat_id, limit)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.error(f"Error fetching top damage for chat {chat_id}: {e}")
        return []
    finally:
        conn.close()


async def _process_boss_defeat(context: ContextTypes.DEFAULT_TYPE, chat_id, boss_status, boss_info):
    """Handles boss defeat, reward calculation, and database cleanup."""
    logger.info(f"World Boss {boss_info['name']} defeated in chat {chat_id}!")

    # Announce defeat
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🏆👹 **The {boss_info['name']} has been defeated!** 👹🏆",
        parse_mode="HTML"
    )

    conn = db.get_db_connection()
    if conn is None:
        await context.bot.send_message(chat_id, "Database error during reward calculation.")
        return

    try:
        cursor = conn.cursor()

        # Get all damage dealers for reward calculation
        cursor.execute(
            "SELECT user_id, username, total_damage FROM world_boss_damage WHERE chat_id = ? ORDER BY total_damage DESC",
            (chat_id,)
        )
        all_damage = [dict(row) for row in cursor.fetchall()]

        if not all_damage:
            await context.bot.send_message(chat_id, "No one damaged the boss? No rewards given.")
            # Still need to clean up
            cursor.execute("UPDATE world_boss_status SET is_active = 0, current_hp = 0 WHERE chat_id = ?", (chat_id,))
            cursor.execute("DELETE FROM world_boss_damage WHERE chat_id = ?", (chat_id,))
            conn.commit()
            return

        # Calculate Rewards
        total_ryo_pool = boss_status['ryo_pool']
        rewards = {} # user_id: ryo_amount
        remaining_pool = total_ryo_pool
        reward_text_parts = ["<b>--- 💰 Reward Distribution 💰 ---</b>"]

        # Top 3 Prizes
        if len(all_damage) >= 1:
            amount = int(total_ryo_pool * 0.30)
            rewards[all_damage[0]['user_id']] = amount
            remaining_pool -= amount
            reward_text_parts.append(f"🥇 1st: {all_damage[0]['username']} (+{amount:,} Ryo)")
        if len(all_damage) >= 2:
            amount = int(total_ryo_pool * 0.20)
            rewards[all_damage[1]['user_id']] = rewards.get(all_damage[1]['user_id'], 0) + amount # Add if somehow same user
            remaining_pool -= amount
            reward_text_parts.append(f"🥈 2nd: {all_damage[1]['username']} (+{amount:,} Ryo)")
        if len(all_damage) >= 3:
            amount = int(total_ryo_pool * 0.10)
            rewards[all_damage[2]['user_id']] = rewards.get(all_damage[2]['user_id'], 0) + amount
            remaining_pool -= amount
            reward_text_parts.append(f"🥉 3rd: {all_damage[2]['username']} (+{amount:,} Ryo)")

        # Participation Rewards (Split remaining 40%)
        participants = all_damage[3:] # Everyone else
        if participants:
            share = int(remaining_pool / len(participants)) if remaining_pool > 0 else 0
            if share > 0:
                 reward_text_parts.append(f"\n🤝 Participation Reward: +{share:,} Ryo each!")
                 for participant in participants:
                     rewards[participant['user_id']] = rewards.get(participant['user_id'], 0) + share
        elif remaining_pool > 0 and len(all_damage) < 3: # If <3 players, give remaining pool to them
            share = int(remaining_pool / len(all_damage))
            reward_text_parts.append(f"\n🤝 Extra Reward: +{share:,} Ryo each!")
            for player in all_damage:
                rewards[player['user_id']] += share


        # Update Player Ryo in DB and clear player cooldowns
        player_ids_to_update = list(rewards.keys())
        for user_id, ryo_gain in rewards.items():
            cursor.execute(
                "UPDATE players SET ryo = ryo + ?, boss_attack_cooldown = NULL WHERE user_id = ?",
                (ryo_gain, user_id)
            )

        # Clean up boss tables
        cursor.execute("UPDATE world_boss_status SET is_active = 0, current_hp = 0 WHERE chat_id = ?", (chat_id,))
        cursor.execute("DELETE FROM world_boss_damage WHERE chat_id = ?", (chat_id,))

        conn.commit()

        # Clear Cache for winners
        for user_id in player_ids_to_update:
            db.cache.clear_player_cache(user_id)

        # Send reward message
        await context.bot.send_message(chat_id, "\n".join(reward_text_parts), parse_mode="HTML")

    except sqlite3.Error as e:
        logger.error(f"Error processing boss defeat for chat {chat_id}: {e}")
        await context.bot.send_message(chat_id, "A database error occurred during reward distribution.")
        conn.rollback()
    finally:
        conn.close()
