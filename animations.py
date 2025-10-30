import logging
import asyncio
from telegram.ext import ContextTypes
from telegram.error import BadRequest # Import error for handling

# Import game data
import game_logic as gl

logger = logging.getLogger(__name__)

# --- Animation Helper (Handles Captions) ---
async def edit_battle_message(context: ContextTypes.DEFAULT_TYPE, battle_state, text, reply_markup=None):
    """
    A safe way to edit the battle message, handling both text and photo captions.
    """
    chat_id = battle_state['chat_id']
    message_id = battle_state['message_id']
    
    # --- THIS IS THE FIX ---
    # Determine if we should edit caption or text based on the original message context
    # We assume if 'base_text' exists, it implies an ongoing battle message
    # In world_boss, the message always originates from send_photo
    # In pvp, the message originates from send_message or edit_message_text
    
    # Let's try editing caption first, as that's needed for the boss
    edit_success = False
    try:
        await context.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=text, # Use text as the caption content
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        edit_success = True
        # logger.debug(f"Edited caption for msg {message_id} in chat {chat_id}") # Optional debug log
        return True # Edited caption successfully
        
    except BadRequest as e:
        # Check if the error is specifically "message is not modified" (ignore)
        # or "message can't be edited" (ignore, maybe deleted)
        # or "there is no caption in the message" (means it's a text message)
        error_str = str(e).lower()
        if "message is not modified" in error_str:
            logger.warning(f"Edit ignored: Message content identical. {chat_id}:{message_id}")
            return True # Treat as success, nothing needed to change
        elif "message can't be edited" in error_str:
             logger.warning(f"Edit failed: Message probably deleted. {chat_id}:{message_id}")
             return False # Cannot edit
        elif "there is no caption" in error_str or "message must have media" in error_str:
            # This indicates it's likely a text message, try editing text instead
            pass # Continue to the edit_message_text block
        elif 'flood control exceeded' in error_str:
             # Handle flood control for caption edits too
            try:
                retry_after = int(error_str.split('retry in ')[1].split(' ')[0])
                logger.warning(f"FLOOD CONTROL (Caption): Waiting for {retry_after} seconds...")
                await asyncio.sleep(retry_after + 1)
                await context.bot.edit_message_caption( # Retry caption edit
                    chat_id=chat_id, message_id=message_id, caption=text,
                    reply_markup=reply_markup, parse_mode="HTML"
                )
                edit_success = True
                return True
            except Exception as e2:
                logger.error(f"Failed to retry caption edit after flood: {e2}")
                return False
        else:
            # Unexpected BadRequest error
             logger.error(f"Unexpected BadRequest error editing caption: {e} ({chat_id}:{message_id})")
             # Fallthrough to try editing text

    except Exception as e:
        # Handle other non-BadRequest errors (like network issues)
        logger.error(f"Non-BadRequest error editing caption: {e} ({chat_id}:{message_id})")
        # Fallthrough to try editing text (less likely to succeed, but try)

    # --- Fallback: Try editing as a text message ---
    if not edit_success:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text, # Use text as the text content
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            # logger.debug(f"Edited text for msg {message_id} in chat {chat_id}") # Optional debug log
            return True # Edited text successfully
            
        except BadRequest as e:
             error_str = str(e).lower()
             if "message is not modified" in error_str:
                 logger.warning(f"Edit ignored: Message content identical (text). {chat_id}:{message_id}")
                 return True
             elif "message can't be edited" in error_str:
                 logger.warning(f"Edit failed: Message probably deleted (text). {chat_id}:{message_id}")
                 return False
             elif "there is no text in the message" in error_str:
                  logger.error(f"Edit failed: Message has neither caption nor text? {e} ({chat_id}:{message_id})")
                  return False # Cannot edit
             elif 'flood control exceeded' in error_str:
                  try:
                      retry_after = int(error_str.split('retry in ')[1].split(' ')[0])
                      logger.warning(f"FLOOD CONTROL (Text): Waiting for {retry_after} seconds...")
                      await asyncio.sleep(retry_after + 1)
                      await context.bot.edit_message_text( # Retry text edit
                          chat_id=chat_id, message_id=message_id, text=text,
                          reply_markup=reply_markup, parse_mode="HTML"
                      )
                      return True
                  except Exception as e2:
                      logger.error(f"Failed to retry text edit after flood: {e2}")
                      return False
             else:
                  logger.error(f"Unexpected BadRequest error editing text: {e} ({chat_id}:{message_id})")
                  return False
        except Exception as e:
             logger.error(f"Non-BadRequest error editing text: {e} ({chat_id}:{message_id})")
             return False
    # --- END OF FIX ---

# --- Other Animation Functions (animate_taijutsu, battle_animation_flow - unchanged) ---

async def animate_taijutsu(context, battle_state, attacker, defender, damage, is_crit):
    # (code is the same, relies on edit_battle_message)
    message_text = battle_state['base_text']
    attack_frame = f"{message_text}\n\n<i>⚔️ {attacker['username']} charges in!</i>"
    await edit_battle_message(context, battle_state, attack_frame)
    await asyncio.sleep(1.5) 
    crit_text = ""
    if is_crit:
        crit_frame_text = "💥 CRITICAL HIT! 💥"
        crit_frame = f"{message_text}\n\n<b>{crit_frame_text}</b>"
        await edit_battle_message(context, battle_state, crit_frame)
        await asyncio.sleep(1.5)
        crit_text = "<b>💥 CRITICAL HIT!</b>\n"
    result_text = (f"{crit_text}" f"<b>🎯 DIRECT HIT!</b>\n" f"<i>{defender['username']} takes {damage} damage!</i>")
    result_frame = f"{message_text}\n\n{result_text}"
    await edit_battle_message(context, battle_state, result_frame)
    await asyncio.sleep(2.5) 

async def battle_animation_flow(context, battle_state, attacker, defender, jutsu_info, damage_data):
    # (code is the same, relies on edit_battle_message)
    damage, is_crit, is_super_eff = damage_data
    jutsu_name = jutsu_info['name'].replace('_', ' ').title()
    message_text = battle_state['base_text']
    signs = " → ".join(jutsu_info['signs'])
    frame_1 = (f"{message_text}\n\n" f"<i>🌀 {attacker['username']} is using <b>{jutsu_name}</b>!</i>\n" f"<i>🤲 Forming hand signs...\n{signs}</i>")
    await edit_battle_message(context, battle_state, frame_1)
    await asyncio.sleep(2.5) 
    charge_frame = (f"{message_text}\n\n" f"<i>Chakra Gathering: [▰▰▰▰▰▰▰▰▰▰] 100% READY! 💫</i>")
    await edit_battle_message(context, battle_state, charge_frame)
    await asyncio.sleep(2)
    element = jutsu_info['element']
    animation_frame = gl.ELEMENT_ANIMATIONS.get(element, ["💥"])[-1] 
    frame_3 = f"{message_text}\n\n<b>{animation_frame}</b>"
    await edit_battle_message(context, battle_state, frame_3)
    await asyncio.sleep(2)
    crit_text = ""
    if is_crit:
        crit_frame_text = "💥 CRITICAL HIT! 💥"
        frame_4 = f"{message_text}\n\n<b>{crit_frame_text}</b>"
        await edit_battle_message(context, battle_state, frame_4)
        await asyncio.sleep(1.5)
        crit_text = "<b>💥 CRITICAL HIT!</b>\n"
    eff_text = "<i>It's super effective!</i>\n" if is_super_eff else ""
    result_text = (f"{crit_text}" f"<b>🎯 DIRECT HIT!</b>\n" f"{eff_text}" f"<i>{defender['username']} takes {damage} damage!</i>")
    frame_5 = f"{message_text}\n\n{result_text}"
    await edit_battle_message(context, battle_state, frame_5)
    await asyncio.sleep(3)
