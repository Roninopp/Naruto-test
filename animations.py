import logging
import asyncio
from telegram.ext import ContextTypes
from telegram.error import BadRequest 

# Import game data
import game_logic as gl

logger = logging.getLogger(__name__)
KUNAI_EMOJI = "\U0001FA9A" 
BOMB_EMOJI = "💥" # New Emoji

# --- Animation Helper (Handles Captions) ---
async def edit_battle_message(context: ContextTypes.DEFAULT_TYPE, battle_state, text, reply_markup=None):
    """A safe way to edit the battle message, handling both text and photo captions."""
    chat_id = battle_state['chat_id']; message_id = battle_state['message_id']
    edit_success = False
    
    try: # Try caption first
        await context.bot.edit_message_caption(
            chat_id=chat_id, message_id=message_id, caption=text, 
            reply_markup=reply_markup, parse_mode="HTML"
        )
        edit_success = True; return True
    except BadRequest as e:
        error_str = str(e).lower()
        if "message is not modified" in error_str: return True 
        elif "message can't be edited" in error_str: logger.warning(f"Edit failed: Deleted? {chat_id}:{message_id}"); return False
        elif "there is no caption" in error_str or "message must have media" in error_str: pass # Fallthrough
        elif 'flood control exceeded' in error_str:
            try:
                retry_after = int(error_str.split('retry in ')[1].split(' ')[0]); logger.warning(f"FLOOD (Caption): Wait {retry_after}s..."); await asyncio.sleep(retry_after + 1)
                await context.bot.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=text, reply_markup=reply_markup, parse_mode="HTML")
                edit_success = True; return True
            except Exception as e2: logger.error(f"Retry caption failed: {e2}"); return False
        else: logger.error(f"Unexpected BadRequest caption: {e} ({chat_id}:{message_id})")
    except Exception as e: logger.error(f"Non-BadRequest caption: {e} ({chat_id}:{message_id})")

    if not edit_success: # Fallback: Try editing text
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text, 
                reply_markup=reply_markup, parse_mode="HTML"
            )
            return True
        except BadRequest as e:
             error_str = str(e).lower()
             if "message is not modified" in error_str: return True
             elif "message can't be edited" in error_str: logger.warning(f"Edit failed (text): Deleted? {chat_id}:{message_id}"); return False
             elif "there is no text in the message" in error_str: logger.error(f"Edit failed: No caption/text? {e} ({chat_id}:{message_id})"); return False
             elif 'flood control exceeded' in error_str:
                  try:
                      retry_after = int(error_str.split('retry in ')[1].split(' ')[0]); logger.warning(f"FLOOD (Text): Wait {retry_after}s..."); await asyncio.sleep(retry_after + 1)
                      await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
                      return True
                  except Exception as e2: logger.error(f"Retry text failed: {e2}"); return False
             else: logger.error(f"Unexpected BadRequest text: {e} ({chat_id}:{message_id})"); return False
        except Exception as e: logger.error(f"Non-BadRequest text: {e} ({chat_id}:{message_id})"); return False

# --- Animation Functions ---
async def animate_taijutsu(context, battle_state, attacker, defender, damage, is_crit):
    """Animates a simple Taijutsu attack with fewer, slower edits."""
    message_text = battle_state['base_text']
    attack_frame = f"{message_text}\n\n<i>⚔️ {attacker['username']} charges in!</i>"
    await edit_battle_message(context, battle_state, attack_frame); await asyncio.sleep(1.5) 
    crit_text = ""
    if is_crit:
        crit_frame_text = "💥 CRITICAL HIT! 💥"; crit_frame = f"{message_text}\n\n<b>{crit_frame_text}</b>"
        await edit_battle_message(context, battle_state, crit_frame); await asyncio.sleep(1.5)
        crit_text = "<b>💥 CRITICAL HIT!</b>\n"
    # Use defender['username'] or defender['name']
    defender_name = defender.get('username', defender.get('name', 'The opponent'))
    result_text = (f"{crit_text}" f"<b>🎯 DIRECT HIT!</b>\n" f"<i>{defender_name} takes {damage} damage!</i>")
    result_frame = f"{message_text}\n\n{result_text}"
    await edit_battle_message(context, battle_state, result_frame); await asyncio.sleep(2.5) 

async def battle_animation_flow(context, battle_state, attacker, defender, jutsu_info, damage_data):
    """Controls the full, non-spammy battle animation sequence."""
    damage, is_crit, is_super_eff = damage_data; jutsu_name = jutsu_info['name'].replace('_', ' ').title()
    message_text = battle_state['base_text']; signs = " → ".join(jutsu_info['signs'])
    frame_1 = (f"{message_text}\n\n" f"<i>🌀 {attacker['username']} is using <b>{jutsu_name}</b>!</i>\n" f"<i>🤲 Forming hand signs...\n{signs}</i>")
    await edit_battle_message(context, battle_state, frame_1); await asyncio.sleep(2.5) 
    charge_frame = (f"{message_text}\n\n" f"<i>Chakra Gathering: [▰▰▰▰▰▰▰▰▰▰] 100% READY! 💫</i>")
    await edit_battle_message(context, battle_state, charge_frame); await asyncio.sleep(2)
    element = jutsu_info['element']; animation_frame = gl.ELEMENT_ANIMATIONS.get(element, ["💥"])[-1] 
    frame_3 = f"{message_text}\n\n<b>{animation_frame}</b>"
    await edit_battle_message(context, battle_state, frame_3); await asyncio.sleep(2)
    crit_text = ""
    if is_crit:
        crit_frame_text = "💥 CRITICAL HIT! 💥"; frame_4 = f"{message_text}\n\n<b>{crit_frame_text}</b>"
        await edit_battle_message(context, battle_state, frame_4); await asyncio.sleep(1.5)
        crit_text = "<b>💥 CRITICAL HIT!</b>\n"
    eff_text = "<i>It's super effective!</i>\n" if is_super_eff else ""
    defender_name = defender.get('username', defender.get('name', 'The opponent'))
    result_text = (f"{crit_text}" f"<b>🎯 DIRECT HIT!</b>\n" f"{eff_text}" f"<i>{defender_name} takes {damage} damage!</i>")
    frame_5 = f"{message_text}\n\n{result_text}"
    await edit_battle_message(context, battle_state, frame_5); await asyncio.sleep(3) 

async def animate_throw_kunai(context, battle_state, attacker, defender, damage, is_crit):
    """Animates a simple Kunai throw attack."""
    message_text = battle_state['base_text']
    
    # Frame 1: Prepare
    prep_frame = f"{message_text}\n\n<i>{KUNAI_EMOJI} {attacker['username']} prepares a kunai...</i>"
    await edit_battle_message(context, battle_state, prep_frame)
    await asyncio.sleep(1.0)
    
    # Frame 2: Throw
    throw_frame = f"{message_text}\n\n<i>{KUNAI_EMOJI} Throws! ===></i>"
    await edit_battle_message(context, battle_state, throw_frame)
    await asyncio.sleep(1.0)
    
    # Frame 3: Critical Hit (if any)
    crit_text = ""
    if is_crit:
        crit_frame_text = "💥 CRITICAL HIT! 💥"; crit_frame = f"{message_text}\n\n<b>{crit_frame_text}</b>"
        await edit_battle_message(context, battle_state, crit_frame); await asyncio.sleep(1.5)
        crit_text = "<b>💥 CRITICAL HIT!</b>\n"

    # Frame 4: The Result
    defender_name = defender.get('username', defender.get('name', 'The opponent'))
    result_text = (
        f"{crit_text}"
        f"<b>{KUNAI_EMOJI}🎯 HIT!</b>\n" 
        f"<i>{defender_name} takes {damage} damage!</i>"
    )
    result_frame = f"{message_text}\n\n{result_text}"
    await edit_battle_message(context, battle_state, result_frame)
    await asyncio.sleep(2.5) 

# --- NEW: Paper Bomb Animation ---
async def animate_paper_bomb(context, battle_state, attacker, defender, damage, is_crit):
    """Animates a Paper Bomb attack."""
    message_text = battle_state['base_text']
    
    # Frame 1: Prepare
    prep_frame = f"{message_text}\n\n<i>{BOMB_EMOJI} {attacker['username']} places a paper bomb tag...</i>"
    await edit_battle_message(context, battle_state, prep_frame)
    await asyncio.sleep(1.5)
    
    # Frame 2: Katsu!
    throw_frame = f"{message_text}\n\n<i>{BOMB_EMOJI} Katsu!</i>"
    await edit_battle_message(context, battle_state, throw_frame)
    await asyncio.sleep(1.0)
    
    # Frame 3: Critical Hit (if any)
    crit_text = ""
    if is_crit:
        crit_frame_text = "💥 CRITICAL HIT! 💥"; crit_frame = f"{message_text}\n\n<b>{crit_frame_text}</b>"
        await edit_battle_message(context, battle_state, crit_frame); await asyncio.sleep(1.5)
        crit_text = "<b>💥 CRITICAL HIT!</b>\n"

    # Frame 4: The Result
    defender_name = defender.get('username', defender.get('name', 'The opponent'))
    result_text = (
        f"{crit_text}"
        f"<b>{BOMB_EMOJI}🔥 EXPLOSION!</b>\n"
        f"<i>{defender_name} takes {damage} damage!</i>"
    )
    result_frame = f"{message_text}\n\n{result_text}"
    await edit_battle_message(context, battle_state, result_frame)
    await asyncio.sleep(2.5) # Pause to read the result
# --- END NEW ---
