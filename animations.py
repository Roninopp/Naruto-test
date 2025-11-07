import logging
import asyncio
from telegram.ext import ContextTypes
from telegram.error import BadRequest 

# Import game data
import game_logic as gl

logger = logging.getLogger(__name__)
KUNAI_EMOJI = "\U0001FA9A" 
BOMB_EMOJI = "💥" 

# --- Animation Helper (Handles Captions & Flood Limits) ---
async def edit_battle_message(context: ContextTypes.DEFAULT_TYPE, battle_state, text, reply_markup=None):
    """A safe way to edit the battle message, handling flood limits automatically."""
    chat_id = battle_state['chat_id']; message_id = battle_state['message_id']
    
    try:
        await context.bot.edit_message_caption(
            chat_id=chat_id, message_id=message_id, caption=text, 
            reply_markup=reply_markup, parse_mode="HTML"
        )
        return True
    except BadRequest as e:
        error_str = str(e).lower()
        if "message is not modified" in error_str: return True 
        if "there is no caption" in error_str or "message must have media" in error_str:
            # Fallback to text edit if it's not a photo anymore
            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
                return True
            except Exception as e2:
                if "flood" in str(e2).lower():
                     retry_after = int(str(e2).split('retry in ')[1].split('.')[0])
                     logger.warning(f"FLOOD WAIT: Sleeping {retry_after}s")
                     await asyncio.sleep(retry_after + 1)
                     return await edit_battle_message(context, battle_state, text, reply_markup) # Recursive retry
                return False
        if "flood" in error_str:
             retry_after = int(error_str.split('retry in ')[1].split('.')[0])
             logger.warning(f"FLOOD WAIT: Sleeping {retry_after}s")
             await asyncio.sleep(retry_after + 2) # Wait a bit longer to be safe
             return await edit_battle_message(context, battle_state, text, reply_markup) # Recursive retry
        
        logger.warning(f"Edit failed (non-critical): {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected edit error: {e}")
        return False

# --- Animation Functions (Slightly Slower to prevent Lag) ---
async def animate_taijutsu(context, battle_state, attacker, defender, damage, is_crit):
    message_text = battle_state['base_text']
    attack_frame = f"{message_text}\n\n<i>⚔️ {attacker['username']} charges in!</i>"
    await edit_battle_message(context, battle_state, attack_frame)
    await asyncio.sleep(2.0) # INCREASED DELAY
    
    crit_text = ""
    if is_crit:
        crit_frame = f"{message_text}\n\n<b>💥 CRITICAL HIT! 💥</b>"
        await edit_battle_message(context, battle_state, crit_frame)
        await asyncio.sleep(2.0) # INCREASED DELAY
        crit_text = "<b>💥 CRITICAL HIT!</b>\n"
        
    defender_name = defender.get('username', defender.get('name', 'The opponent'))
    result_text = (f"{crit_text}" f"<b>🎯 DIRECT HIT!</b>\n" f"<i>{defender_name} takes {damage} damage!</i>")
    result_frame = f"{message_text}\n\n{result_text}"
    await edit_battle_message(context, battle_state, result_frame)
    # No sleep here, let the next turn menu appear immediately

async def battle_animation_flow(context, battle_state, attacker, defender, jutsu_info, damage_data):
    damage, is_crit, is_super_eff = damage_data; jutsu_name = jutsu_info['name'].replace('_', ' ').title()
    message_text = battle_state['base_text']; signs = " → ".join(jutsu_info['signs'])
    
    frame_1 = (f"{message_text}\n\n" f"<i>🌀 {attacker['username']} is using <b>{jutsu_name}</b>!</i>\n" f"<i>🤲 Hand Signs: {signs}</i>")
    await edit_battle_message(context, battle_state, frame_1)
    await asyncio.sleep(2.5) # INCREASED DELAY

    element = jutsu_info['element']; animation_frame = gl.ELEMENT_ANIMATIONS.get(element, ["💥"])[-1] 
    frame_3 = f"{message_text}\n\n<b>{animation_frame}</b>"
    await edit_battle_message(context, battle_state, frame_3)
    await asyncio.sleep(2.0) # INCREASED DELAY
    
    crit_text = ""
    if is_crit:
        frame_4 = f"{message_text}\n\n<b>💥 CRITICAL HIT! 💥</b>"
        await edit_battle_message(context, battle_state, frame_4)
        await asyncio.sleep(1.5)
        crit_text = "<b>💥 CRITICAL HIT!</b>\n"
        
    eff_text = "<i>It's super effective!</i>\n" if is_super_eff else ""
    defender_name = defender.get('username', defender.get('name', 'The opponent'))
    result_text = (f"{crit_text}" f"<b>🎯 DIRECT HIT!</b>\n" f"{eff_text}" f"<i>{defender_name} takes {damage} damage!</i>")
    frame_5 = f"{message_text}\n\n{result_text}"
    await edit_battle_message(context, battle_state, frame_5)
    # No sleep here

async def animate_throw_kunai(context, battle_state, attacker, defender, damage, is_crit):
    message_text = battle_state['base_text']
    prep_frame = f"{message_text}\n\n<i>{KUNAI_EMOJI} {attacker['username']} throws a kunai!</i>"
    await edit_battle_message(context, battle_state, prep_frame)
    await asyncio.sleep(1.5) # INCREASED DELAY
    
    crit_text = ""
    if is_crit:
        crit_frame = f"{message_text}\n\n<b>💥 CRITICAL HIT! 💥</b>"
        await edit_battle_message(context, battle_state, crit_frame)
        await asyncio.sleep(1.5)
        crit_text = "<b>💥 CRITICAL HIT!</b>\n"

    defender_name = defender.get('username', defender.get('name', 'The opponent'))
    result_text = (f"{crit_text}" f"<b>{KUNAI_EMOJI}🎯 HIT!</b>\n" f"<i>{defender_name} takes {damage} damage!</i>")
    result_frame = f"{message_text}\n\n{result_text}"
    await edit_battle_message(context, battle_state, result_frame)

async def animate_paper_bomb(context, battle_state, attacker, defender, damage, is_crit):
    message_text = battle_state['base_text']
    prep_frame = f"{message_text}\n\n<i>{BOMB_EMOJI} {attacker['username']} planted a bomb! KATSU!</i>"
    await edit_battle_message(context, battle_state, prep_frame)
    await asyncio.sleep(2.0) # INCREASED DELAY
    
    crit_text = ""
    if is_crit:
        crit_frame = f"{message_text}\n\n<b>💥 CRITICAL HIT! 💥</b>"
        await edit_battle_message(context, battle_state, crit_frame)
        await asyncio.sleep(1.5)
        crit_text = "<b>💥 CRITICAL HIT!</b>\n"

    defender_name = defender.get('username', defender.get('name', 'The opponent'))
    result_text = (f"{crit_text}" f"<b>{BOMB_EMOJI}🔥 EXPLOSION!</b>\n" f"<i>{defender_name} takes {damage} damage!</i>")
    result_frame = f"{message_text}\n\n{result_text}"
    await edit_battle_message(context, battle_state, result_frame)
