import logging
import json
import datetime
import asyncio
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import timezone
from telegram.constants import ChatType

import database as db
import game_logic as gl
import animations as anim 

logger = logging.getLogger(__name__)

# --- Constants ---
KUNAI_EMOJI = "\U0001FA9A"
BOMB_EMOJI = "💥"
KUNAI_COOLDOWN_SECONDS = 30
BOMB_COOLDOWN_SECONDS = 120
JUTSU_COOLDOWN_SECONDS = 300
FLEE_COOLDOWN_SECONDS = 60
AKATSUKI_REWARDS = {'exp': 110, 'ryo': 180}
PLAYER_SLOTS = ['player_1_id', 'player_2_id', 'player_3_id']
EVENT_TIMEOUT_MINUTES = 180 # 3 Hours

# --- Helper: Get Battle Text ---
def get_akatsuki_battle_text(battle_state, enemy_info, players_list):
    text = (
        f"👹 **{enemy_info['name']}** Attacks! 👹\n"
        f"<i>{enemy_info['desc']}</i>\n\n"
        f"<b>HP:</b> {gl.health_bar(battle_state['enemy_hp'], enemy_info['max_hp'])}\n\n"
        f"<b>⚔️ Joined Players (Up to 3) ⚔️</b>\n"
    )
    turn_player_id = battle_state.get('turn_player_id')
    turn_player_name = "AI"
    joined_players_data = {}
    for slot in PLAYER_SLOTS:
        player_id = battle_state[slot]
        if player_id:
            player_data = db.get_player(player_id)
            if player_data: joined_players_data[player_id] = player_data
    for i, slot in enumerate(PLAYER_SLOTS):
        player_id = battle_state[slot]
        if player_id and player_id in joined_players_data:
            player_data = joined_players_data[player_id]
            player_total_stats = gl.get_total_stats(player_data)
            hp_display = f"(HP: {player_data['current_hp']}/{player_total_stats['max_hp']})"
            if player_data['current_hp'] <= 1: hp_display = "<b>(Fainted)</b>"
            text += f" {i+1}. {player_data['username']} [Lvl {player_data['level']}] {hp_display}\n"
            if str(player_id) == str(turn_player_id): turn_player_name = player_data['username']
        else: text += f" {i+1}. <i>(Waiting...)</i>\n"
    if not turn_player_id: text += "\nWaiting for 3 players to join..."
    elif turn_player_id == 'ai_turn': text += f"\n<b>Turn: {enemy_info['name']}</b>\n<i>The enemy is preparing an attack...</i>"
    else: text += f"\n<b>Turn: {turn_player_name}</b>\nChoose your action:"
    return text

# --- Helper: Send/Edit Battle Message ---
async def send_or_edit_akatsuki_message(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id=None, text=None, photo_url=None, reply_markup=None):
    try:
        if message_id:
            await context.bot.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await context.bot.send_photo(chat_id=chat_id, photo=photo_url, caption=text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error sending/editing Akatsuki message for chat {chat_id}: {e}")
            if "Message to edit not found" in str(e) or "message to edit not found" in str(e):
                db.clear_akatsuki_fight(chat_id)
            elif "message must have media" in str(e):
                 try:
                     await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
                 except Exception as e2:
                     logger.error(f"Fallback edit failed: {e2}")
                     db.clear_akatsuki_fight(chat_id)

# --- Admin Command ---
async def toggle_auto_fight_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat; user = update.effective_user
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("Only works in groups.")
        return
    try:
        chat_admins = await context.bot.get_chat_administrators(chat.id)
        if user.id not in [admin.user.id for admin in chat_admins]:
            await update.message.reply_text("Admin only.")
            return
    except:
        await update.message.reply_text("Error checking admin status.")
        return
    command = update.message.text.split(' ')[0].split('@')[0].lower()
    new_status = 0 if command in ["/auto_fight_off", "/auto_ryo_off"] else 1
    db.toggle_auto_events(chat.id, new_status)
    await update.message.reply_text(f"{'✅' if new_status else '❌'} Akatsuki Ambushes {'ENABLED' if new_status else 'DISABLED'}.")

# --- Passive Register ---
async def passive_group_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        db.register_event_chat(update.effective_chat.id)

# --- Event Spawning ---
async def spawn_akatsuki_event(context: ContextTypes.DEFAULT_TYPE):
    logger.info("AKATSUKI JOB: Running spawn check...")
    boss_chats = set(db.get_all_boss_chats()); event_settings = db.get_event_settings_dict()
    all_known_chats = boss_chats.union(set(event_settings.keys()))
    enabled_chat_ids = [cid for cid in all_known_chats if event_settings.get(cid, 1) == 1]
    if not enabled_chat_ids:
        logger.info("AKATSUKI JOB: No enabled chats.")
        return

    enemy_key = 'sasuke_clone'; enemy_info = gl.AKATSUKI_ENEMIES.get(enemy_key)
    if not enemy_info: return
    message_text = f"**The Akatsuki Organization Is Coming To Destroy Your Village!**\n\nA rogue ninja, {enemy_info['name']}, blocks the path!\n**Up to 3 ninjas** can join this fight.\n<i>Psst... Admins can use /auto_fight_off to stop these.</i>"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⚔️ Protect Village!", callback_data="akatsuki_join")]])
    now = datetime.datetime.now(timezone.utc); timeout = datetime.timedelta(minutes=EVENT_TIMEOUT_MINUTES)

    for chat_id in enabled_chat_ids:
        battle_state = db.get_akatsuki_fight(chat_id)
        if battle_state:
            try:
                created_at = battle_state['created_at']
                if isinstance(created_at, str): created_at = datetime.datetime.fromisoformat(created_at)
                if created_at.tzinfo is None: created_at = created_at.replace(tzinfo=timezone.utc)
                if (now - created_at) >= timeout:
                    logger.warning(f"AKATSUKI JOB: Chat {chat_id} timed out. Clearing.")
                    db.clear_akatsuki_fight(chat_id)
                    try:
                        await context.bot.send_message(chat_id, "The Akatsuki member got bored and left...")
                    except:
                        pass
                    battle_state = None
                else: continue
            except Exception as e:
                logger.error(f"AKATSUKI JOB: Error checking timeout {chat_id}: {e}")
                db.clear_akatsuki_fight(chat_id)
                battle_state = None

        if not battle_state:
            try:
                msg = await context.bot.send_photo(chat_id=chat_id, photo=enemy_info['image'], caption=message_text, reply_markup=reply_markup, parse_mode="HTML")
                db.create_akatsuki_fight(msg.message_id, chat_id, enemy_key)
                await asyncio.sleep(1)
            except Exception as e:
                 logger.error(f"AKATSUKI JOB: Send failed {chat_id}: {e}")
                 if "forbidden" in str(e).lower() or "kicked" in str(e).lower(): db.toggle_auto_events(chat_id, 0)
    logger.info("AKATSUKI JOB: Finished.")

# --- Callbacks ---
async def akatsuki_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    if not db.get_player(user.id):
        await query.answer("You must /start first!", show_alert=True)
        return

    join_result = db.add_player_to_fight(message_id, chat_id, user.id)
    battle_state = db.get_akatsuki_fight(chat_id, message_id)
    
    if not battle_state:
        await query.answer("Fight no longer active.", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except:
            pass
        return

    if join_result['status'] == 'full':
        await query.answer("Fight is full!", show_alert=True)
        return
    if join_result['status'] == 'already_joined':
        await query.answer("You already joined!", show_alert=True)
        return
        
    await query.answer("You joined the fight!")
    enemy_info = gl.AKATSUKI_ENEMIES.get(battle_state['enemy_name'])
    
    if join_result['status'] == 'ready':
        db.set_akatsuki_turn(message_id, battle_state['player_1_id'])
        battle_state['turn_player_id'] = str(battle_state['player_1_id'])
        text = get_akatsuki_battle_text(battle_state, enemy_info, [])
        keyboard = [[InlineKeyboardButton(f"{KUNAI_EMOJI} Throw Kunai", callback_data="akatsuki_action_throw_kunai"), InlineKeyboardButton(f"{BOMB_EMOJI} Paper Bomb", callback_data="akatsuki_action_paper_bomb")], [InlineKeyboardButton("🌀 Use Jutsu", callback_data="akatsuki_action_jutsu"), InlineKeyboardButton("🏃 Flee", callback_data="akatsuki_action_flee")]]
        await send_or_edit_akatsuki_message(context, chat_id, message_id, text, None, InlineKeyboardMarkup(keyboard))
    else:
        text = get_akatsuki_battle_text(battle_state, enemy_info, [])
        await send_or_edit_akatsuki_message(context, chat_id, message_id, text, None, query.message.reply_markup)

async def akatsuki_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = "_".join(query.data.split('_')[2:])
    user = query.from_user
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    
    battle_state = db.get_akatsuki_fight(chat_id, message_id)
    if not battle_state:
        await query.answer("Fight ended.", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except:
            pass
        return

    if str(battle_state['turn_player_id']) != str(user.id):
        await query.answer("Not your turn!", show_alert=True)
        return
        
    player_data = db.get_player(user.id)
    if not player_data:
        await query.answer("Player data not found!", show_alert=True)
        return

    enemy_info = gl.AKATSUKI_ENEMIES.get(battle_state['enemy_name'])
    if player_data['current_hp'] <= 1:
        await query.answer("You are fainted! Waiting for AI...", show_alert=True)
        await _next_turn(context, chat_id, message_id, battle_state, enemy_info)
        return

    if action == "flee":
        await query.answer()
        await query.edit_message_caption(caption=f"🏃 {player_data['username']} fled!")
        db.remove_player_from_fight(message_id, user.id)
        rem = db.get_akatsuki_fight(chat_id, message_id)
        if not rem['player_1_id'] and not rem['player_2_id'] and not rem['player_3_id']:
            await end_akatsuki_fight(context, chat_id, message_id, battle_state, enemy_info, success=False, flee=True)
        else:
            await _next_turn(context, chat_id, message_id, battle_state, enemy_info)
        return

    cd_seconds = KUNAI_COOLDOWN_SECONDS if action == "throw_kunai" else BOMB_COOLDOWN_SECONDS if action == "paper_bomb" else JUTSU_COOLDOWN_SECONDS
    cd_check, rem_sec = _check_akatsuki_cooldown(player_data, action, cd_seconds)
    if not cd_check:
        await query.answer(f"⏳ Cooldown! Wait {rem_sec:.0f}s.", show_alert=True)
        return

    if action == "jutsu":
        if player_data['level'] < 5:
            await query.answer("Need Level 5+ for Jutsus!", show_alert=True)
            return
        known = json.loads(player_data['known_jutsus']) if player_data.get('known_jutsus') else []
        if not known:
            await query.answer("You don't know any Jutsus! Use /combine.", show_alert=True)
            return
        await query.answer()
        base_text = get_akatsuki_battle_text(battle_state, enemy_info, []).split("\n\nTurn:")[0]
        kb = [[InlineKeyboardButton(f"{gl.JUTSU_LIBRARY[k]['name']} ({gl.JUTSU_LIBRARY[k]['chakra_cost']})", callback_data=f"akatsuki_jutsu_{k}")] for k in known if gl.JUTSU_LIBRARY.get(k) and player_data['current_chakra'] >= gl.JUTSU_LIBRARY[k]['chakra_cost']]
        if not kb: kb.append([InlineKeyboardButton("Not enough Chakra!", callback_data="akatsuki_nochakra")])
        kb.append([InlineKeyboardButton("Cancel", callback_data="akatsuki_jutsu_cancel")])
        await send_or_edit_akatsuki_message(context, chat_id, message_id, f"{base_text}\n\nSelect a Jutsu:", None, InlineKeyboardMarkup(kb))
        return

    await query.answer()
    base_text = get_akatsuki_battle_text(battle_state, enemy_info, []).split("\n\nTurn:")[0]
    await send_or_edit_akatsuki_message(context, chat_id, message_id, f"{base_text}\n\n<i>Turn: {player_data['username']}</i>\nProcessing...", None, None)
    
    damage = 0
    if action == "throw_kunai":
        damage = int((random.randint(8, 12) + player_data['level']) * (1.8 if random.random() < 0.08 else 1.0))
        await anim.animate_throw_kunai(context, {'chat_id':chat_id,'message_id':message_id,'base_text':base_text}, player_data, {'username':enemy_info['name']}, damage, damage > (12+player_data['level']))
    elif action == "paper_bomb":
        damage = int((random.randint(15, 25) + player_data['level'] * 2) * (2.0 if random.random() < 0.12 else 1.0))
        await anim.animate_paper_bomb(context, {'chat_id':chat_id,'message_id':message_id,'base_text':base_text}, player_data, {'name':enemy_info['name']}, damage, damage > (25+player_data['level']*2))

    db.update_akatsuki_fight_hp(message_id, max(0, battle_state['enemy_hp'] - damage))
    db.set_akatsuki_cooldown(user.id, action, cd_seconds)
    if max(0, battle_state['enemy_hp'] - damage) == 0:
        await end_akatsuki_fight(context, chat_id, message_id, battle_state, enemy_info, success=True)
    else:
        await _next_turn(context, chat_id, message_id, battle_state, enemy_info)

async def akatsuki_jutsu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    battle_state = db.get_akatsuki_fight(chat_id, message_id)
    if not battle_state or str(battle_state['turn_player_id']) != str(user.id):
        await query.answer("Not your turn!", show_alert=True)
        return
    player_data = db.get_player(user.id)
    jutsu_key = "_".join(query.data.split('_')[2:])
    enemy_info = gl.AKATSUKI_ENEMIES.get(battle_state['enemy_name'])

    if jutsu_key == "cancel": 
        await query.answer()
        text = get_akatsuki_battle_text(battle_state, enemy_info, [])
        kb = [[InlineKeyboardButton(f"{KUNAI_EMOJI} Throw Kunai", callback_data="akatsuki_action_throw_kunai"), InlineKeyboardButton(f"{BOMB_EMOJI} Paper Bomb", callback_data="akatsuki_action_paper_bomb")], [InlineKeyboardButton("🌀 Use Jutsu", callback_data="akatsuki_action_jutsu"), InlineKeyboardButton("🏃 Flee", callback_data="akatsuki_action_flee")]]
        await send_or_edit_akatsuki_message(context, chat_id, message_id, text, None, InlineKeyboardMarkup(kb))
        return
    if jutsu_key == "nochakra":
        await query.answer("Not enough Chakra!", show_alert=True)
        return

    jutsu_info = gl.JUTSU_LIBRARY.get(jutsu_key)
    if not jutsu_info or player_data['current_chakra'] < jutsu_info['chakra_cost']:
        await query.answer("Error or not enough chakra.", show_alert=True)
        return
    
    cd_check, rem = _check_akatsuki_cooldown(player_data, "jutsu", JUTSU_COOLDOWN_SECONDS)
    if not cd_check:
        await query.answer(f"⏳ Jutsu cooldown! Wait {rem:.0f}s.", show_alert=True)
        return

    await query.answer()
    base_text = get_akatsuki_battle_text(battle_state, enemy_info, []).split("\n\nTurn:")[0]
    await send_or_edit_akatsuki_message(context, chat_id, message_id, f"{base_text}\n\n<i>Processing Jutsu...</i>", None, None)

    stats = gl.get_total_stats(player_data)
    base_dmg = jutsu_info['power'] + (stats['intelligence'] * 2.5)
    dmg = int(random.randint(int(base_dmg * 0.9), int(base_dmg * 1.1)) * (2.5 if random.random() < 0.15 else 1.0))
    player_data['current_chakra'] -= jutsu_info['chakra_cost']
    
    await anim.battle_animation_flow(context, {'chat_id':chat_id,'message_id':message_id,'base_text':base_text}, player_data, {'username':enemy_info['name'],'village':'none'}, jutsu_info, (dmg, dmg > base_dmg*1.1, False))
    
    db.update_akatsuki_fight_hp(message_id, max(0, battle_state['enemy_hp'] - dmg))
    db.set_akatsuki_cooldown(user.id, "jutsu", JUTSU_COOLDOWN_SECONDS)
    db.update_player(user.id, {'current_chakra': player_data['current_chakra']})

    if max(0, battle_state['enemy_hp'] - dmg) == 0:
        await end_akatsuki_fight(context, chat_id, message_id, battle_state, enemy_info, success=True)
    else:
        await _next_turn(context, chat_id, message_id, battle_state, enemy_info)

async def _run_ai_turn(context, chat_id, message_id, battle_state, enemy_info):
    living = [db.get_player(battle_state[s]) for s in PLAYER_SLOTS if battle_state[s] and db.get_player(battle_state[s])['current_hp'] > 1]
    if not living:
        await end_akatsuki_fight(context, chat_id, message_id, battle_state, enemy_info, success=False)
        return
    target = random.choice(living)
    dmg = int((enemy_info.get('strength', 20) * 0.8 + enemy_info['level'] * 0.5) * (1.8 if random.random() < 0.1 else 1.0))
    base_text = get_akatsuki_battle_text(battle_state, enemy_info, []).split("\n\nTurn:")[0]
    await anim.animate_taijutsu(context, {'chat_id':chat_id,'message_id':message_id,'base_text':base_text}, {'username':enemy_info['name']}, target, dmg, dmg > (enemy_info.get('strength', 20) * 0.8 + enemy_info['level'] * 0.5))
    db.update_player(target['user_id'], {'current_hp': max(1, target['current_hp'] - dmg)})
    
    living_after = [p for s in PLAYER_SLOTS if battle_state[s] and (p := db.get_player(battle_state[s])) and p['current_hp'] > 1]
    if not living_after:
        await end_akatsuki_fight(context, chat_id, message_id, battle_state, enemy_info, success=False)
    else:
        await _next_turn(context, chat_id, message_id, battle_state, enemy_info, next_turn_id=battle_state['player_1_id'])

async def _next_turn(context, chat_id, message_id, battle_state, enemy_info, next_turn_id=None):
    curr_str = str(battle_state['turn_player_id'])
    p_ids = [str(battle_state[s]) if battle_state[s] else None for s in PLAYER_SLOTS]
    if not next_turn_id:
        try: idx = p_ids.index(curr_str)
        except: idx = -1
        next_turn_id = battle_state['player_2_id'] if idx == 0 else battle_state['player_3_id'] if idx == 1 else 'ai_turn'
    
    if next_turn_id and next_turn_id != 'ai_turn':
        p = db.get_player(next_turn_id)
        if not p or p['current_hp'] <= 1:
            battle_state['turn_player_id'] = str(next_turn_id)
            await _next_turn(context, chat_id, message_id, battle_state, enemy_info)
            return

    db.set_akatsuki_turn(message_id, str(next_turn_id))
    battle_state['turn_player_id'] = str(next_turn_id)
    text = get_akatsuki_battle_text(battle_state, enemy_info, [])
    if next_turn_id == 'ai_turn':
        await send_or_edit_akatsuki_message(context, chat_id, message_id, text, None, None)
        await asyncio.sleep(2)
        await _run_ai_turn(context, chat_id, message_id, battle_state, enemy_info)
    else:
        kb = [[InlineKeyboardButton(f"{KUNAI_EMOJI} Throw Kunai", callback_data="akatsuki_action_throw_kunai"), InlineKeyboardButton(f"{BOMB_EMOJI} Paper Bomb", callback_data="akatsuki_action_paper_bomb")], [InlineKeyboardButton("🌀 Use Jutsu", callback_data="akatsuki_action_jutsu"), InlineKeyboardButton("🏃 Flee", callback_data="akatsuki_action_flee")]]
        await send_or_edit_akatsuki_message(context, chat_id, message_id, text, None, InlineKeyboardMarkup(kb))

async def end_akatsuki_fight(context, chat_id, message_id, battle_state, enemy_info, success=True, flee=False):
    if flee: text = "🏃 **Battle Ended!** All players fled."
    elif success: text = f"🏆 **YOU PROTECTED THE VILLAGE!** 🏆\nThe {enemy_info['name']} was defeated!\nRewards: **+{AKATSUKI_REWARDS['exp']} EXP**, **+{AKATSUKI_REWARDS['ryo']} Ryo**!"
    else: text = f"💔 **MISSION FAILED!** 💔\nThe {enemy_info['name']} defeated your team..."
    try:
        await send_or_edit_akatsuki_message(context, chat_id, message_id, text, None, None)
    except:
        await context.bot.send_message(chat_id, text, parse_mode="HTML")
    if success:
        msgs = []
        for pid in [battle_state[s] for s in PLAYER_SLOTS if battle_state[s]]:
            p = db.get_player(pid)
            if p:
                p['ryo'] += AKATSUKI_REWARDS['ryo']
                p['exp'] += AKATSUKI_REWARDS['exp']
                p['total_exp'] += AKATSUKI_REWARDS['exp']
                fp, lvl, m = gl.check_for_level_up(p)
                db.update_player(pid, fp)
                if lvl: msgs.append(f"@{p['username']}\n" + "\n".join(m))
        if msgs:
            await context.bot.send_message(chat_id, "\n\n".join(msgs))
    db.clear_akatsuki_fight(chat_id)

def _check_akatsuki_cooldown(player_data, action, cooldown_seconds):
    cd_str = player_data.get('akatsuki_cooldown')
    now = datetime.datetime.now()
    if player_data.get('current_hp', 100) <= 1: return False, 3600 
    if not cd_str: return True, 0
    try: cds = json.loads(cd_str)
    except: cds = {}
    act_cd = cds.get(action)
    if not act_cd: return True, 0
    cd_time = datetime.datetime.fromisoformat(act_cd)
    if now < cd_time: return False, (cd_time - now).total_seconds()
    return True, 0
