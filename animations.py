import logging
import asyncio
from telegram.ext import ContextTypes

# Import game data
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Animation Helper (with Flood Control) ---
async def edit_battle_message(context: ContextTypes.DEFAULT_TYPE, battle_state, text, reply_markup=None):
    """A safe way to edit the battle message with flood control."""
    try:
        await context.bot.edit_message_text(
            chat_id=battle_state['chat_id'],
            message_id=battle_state['message_id'],
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        return True
    except Exception as e:
        logger.warning(f"Error editing battle message: {e}")
        if 'Flood control exceeded' in str(e):
            try:
                # Try to parse the retry_after value
                retry_after = int(str(e).split('Retry in ')[1].split(' ')[0])
                logger.warning(f"FLOOD CONTROL: Waiting for {retry_after} seconds...")
                await asyncio.sleep(retry_after + 1)
                # Try one more time
                await context.bot.edit_message_text(
                    chat_id=battle_state['chat_id'],
                    message_id=battle_state['message_id'],
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
                return True
            except Exception as e2:
                logger.error(f"Failed to retry after flood: {e2}")
                return False
        return False

# --- NEW SAFE ANIMATION FUNCTIONS ---

async def animate_taijutsu(context, battle_state, attacker, defender, damage, is_crit):
    """Animates a simple Taijutsu attack with fewer, slower edits."""
    message_text = battle_state['base_text']
    
    # --- Frame 1: The Attack ---
    attack_frame = f"{message_text}\n\n<i>⚔️ {attacker['username']} charges in!</i>"
    await edit_battle_message(context, battle_state, attack_frame)
    await asyncio.sleep(1.5) # Longer pause
    
    # --- Frame 2: Critical Hit (if any) ---
    crit_text = ""
    if is_crit:
        # We will just show one "Critical Hit" frame to avoid floods
        crit_frame_text = "💥 CRITICAL HIT! 💥"
        crit_frame = f"{message_text}\n\n<b>{crit_frame_text}</b>"
        await edit_battle_message(context, battle_state, crit_frame)
        await asyncio.sleep(1.5)
        crit_text = "<b>💥 CRITICAL HIT!</b>\n"

    # --- Frame 3: The Result ---
    result_text = (
        f"{crit_text}"
        f"<b>🎯 DIRECT HIT!</b>\n"
        f"<i>{defender['username']} takes {damage} damage!</i>"
    )
    result_frame = f"{message_text}\n\n{result_text}"
    await edit_battle_message(context, battle_state, result_frame)
    await asyncio.sleep(2.5) # Pause to read the result

async def battle_animation_flow(context, battle_state, attacker, defender, jutsu_info, damage_data):
    """
    Controls the full, non-spammy battle animation sequence.
    This version combines frames to prevent flooding.
    """
    
    damage, is_crit, is_super_eff = damage_data
    jutsu_name = jutsu_info['name'].replace('_', ' ').title()
    message_text = battle_state['base_text']

    # --- Frame 1: Announce + Hand Signs ---
    signs = " → ".join(jutsu_info['signs'])
    frame_1 = (
        f"{message_text}\n\n"
        f"<i>🌀 {attacker['username']} is using <b>{jutsu_name}</b>!</i>\n"
        f"<i>🤲 Forming hand signs...\n{signs}</i>"
    )
    await edit_battle_message(context, battle_state, frame_1)
    await asyncio.sleep(2.5) # Long pause for hand signs

    # --- Frame 2: Chakra Charging ---
    charge_frame = (
        f"{message_text}\n\n"
        f"<i>Chakra Gathering: [▰▰▰▰▰▰▰▰▰▰] 100% READY! 💫</i>"
    )
    await edit_battle_message(context, battle_state, charge_frame)
    await asyncio.sleep(2)

    # --- Frame 3: Jutsu Execution (elemental) ---
    element = jutsu_info['element']
    # We will just show the LAST frame of the element animation
    animation_frame = gl.ELEMENT_ANIMATIONS.get(element, ["💥"])[-1] # Get last frame
    frame_3 = f"{message_text}\n\n<b>{animation_frame}</b>"
    await edit_battle_message(context, battle_state, frame_3)
    await asyncio.sleep(2)

    # --- Frame 4: Critical hit (if any) ---
    crit_text = ""
    if is_crit:
        crit_frame_text = "💥 CRITICAL HIT! 💥"
        frame_4 = f"{message_text}\n\n<b>{crit_frame_text}</b>"
        await edit_battle_message(context, battle_state, frame_4)
        await asyncio.sleep(1.5)
        crit_text = "<b>💥 CRITICAL HIT!</b>\n"
        
    # --- Frame 5: Final Result ---
    eff_text = "<i>It's super effective!</i>\n" if is_super_eff else ""
    result_text = (
        f"{crit_text}"
        f"<b>🎯 DIRECT HIT!</b>\n"
        f"{eff_text}"
        f"<i>{defender['username']} takes {damage} damage!</i>"
    )
    frame_5 = f"{message_text}\n\n{result_text}"
    await edit_battle_message(context, battle_state, frame_5)
    await asyncio.sleep(3) # Extra long pause to read the final result
