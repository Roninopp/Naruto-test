import logging
import asyncio
import json
import random
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database as db

logger = logging.getLogger(__name__)

# --- CONFIG ---
SPAWN_CHANCE = 0.3  # 30% chance per check
MIN_COOLDOWN = 1800 # 30 minutes between spawns per group
UPDATE_CHANNEL = "@SN_Telegram_bots_Stores" # Channel for Force Join
UPDATE_CHANNEL_LINK = "https://t.me/SN_Telegram_bots_Stores"
ADMIN_ID = 6837532865 # 🔥 YOUR ID FOR /pp COMMAND

# Memory Storage
ACTIVE_SPAWNS = {}  # {chat_id: {'char': data, 'msg_id': int}}
GROUP_COOLDOWNS = {} # {chat_id: timestamp}

# --- LOAD CHARACTERS ---
try:
    with open("naruto_characters.json", "r") as f:
        CHARACTERS = json.load(f)
    logger.info(f"✅ Loaded {len(CHARACTERS)} characters for spawning.")
except Exception as e:
    logger.error(f"❌ Could not load naruto_characters.json: {e}")
    CHARACTERS = []

# --- RARITY LOGIC ---
LEGENDARY_NAMES = ["Naruto", "Sasuke", "Madara", "Itachi", "Kakashi", "Minato", "Hashirama", "Jiraiya", "Tsunade", "Orochimaru", "Pain", "Obito", "Kaguya", "Might Guy"]
EPIC_NAMES = ["Gaara", "Rock Lee", "Hinata", "Sakura", "Shikamaru", "Neji", "Killer Bee", "Kurama", "Zabuza", "Haku"]

def get_rarity(name):
    if any(n in name for n in LEGENDARY_NAMES): return "Legendary"
    if any(n in name for n in EPIC_NAMES): return "Epic"
    return "Common"

def get_catch_rate(rarity, player_rank):
    """Calculate catch chance based on Rarity vs Rank"""
    rates = {"Common": 0.70, "Epic": 0.40, "Legendary": 0.15}
    base_rate = rates.get(rarity, 0.70)
    
    # Rank Bonus
    rank_bonus = {
        "Genin": 0.05, "Chunin": 0.10, "Jonin": 0.15, 
        "Anbu": 0.20, "Kage": 0.30
    }.get(player_rank, 0)
    
    return base_rate + rank_bonus

# --- FORCE JOIN CHECKER ---
async def check_force_join(user_id, context: ContextTypes.DEFAULT_TYPE):
    """Returns True if user is in channel, False if not."""
    try:
        member = await context.bot.get_chat_member(chat_id=UPDATE_CHANNEL, user_id=user_id)
        if member.status in ['left', 'kicked', 'restricted']:
            return False
        return True
    except Exception as e:
        logger.warning(f"⚠️ Force Join Check Failed: {e}")
        return True 

# --- SCHEDULER & SPAWN LOGIC ---

async def trigger_spawn_on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called on every text message to potentially trigger a spawn."""
    chat_id = update.effective_chat.id
    current_time = datetime.datetime.now().timestamp()
    
    # 1. Check Cooldown
    last_spawn = GROUP_COOLDOWNS.get(chat_id, 0)
    if current_time - last_spawn < MIN_COOLDOWN:
        return

    # 2. Random Chance (30%)
    if random.random() > SPAWN_CHANCE:
        return

    # 3. SPAWN!
    await spawn_character(chat_id, context)
    GROUP_COOLDOWNS[chat_id] = current_time

async def forcespawn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """⚡ Admin command to force a spawn immediately (Testing)"""
    chat_id = update.effective_chat.id
    
    await update.message.reply_text("⚡ **Summoning Jutsu! Force Spawning...**", parse_mode="Markdown")
    
    # Reset cooldown so it spawns instantly
    GROUP_COOLDOWNS[chat_id] = 0
    await spawn_character(chat_id, context)

async def spawn_character(chat_id, context):
    """Selects character and sends to group"""
    if not CHARACTERS: return

    char = random.choice(CHARACTERS)
    rarity = get_rarity(char['name'])
    char['rarity'] = rarity # Inject rarity
    
    # 🔥 HIDDEN NAME LOGIC
    # We show ??? instead of the name so they have to guess!
    caption = (
        f"⚠️ **A Wild Ninja Appeared!**\n\n"
        f"👤 **Name:** ???\n"
        f"🌟 **Rarity:** ???\n\n"
        f"⚔️ /recruit [Character Name]"
    )
    
    try:
        msg = await context.bot.send_photo(
            chat_id=chat_id,
            photo=char['image'],
            caption=caption,
            parse_mode="Markdown"
        )
        
        # Save to memory
        ACTIVE_SPAWNS[chat_id] = {
            'char': char,
            'msg_id': msg.message_id
        }
        
    except Exception as e:
        logger.error(f"Failed to spawn {char['name']}: {e}")
        # Fallback image if main fails
        try:
            fallback = "https://upload.wikimedia.org/wikipedia/en/c/c7/Naruto_logo.svg"
            msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=fallback,
                caption=caption + "\n\n*(Image failed, but you can still catch!)*",
                parse_mode="Markdown"
            )
            ACTIVE_SPAWNS[chat_id] = {
                'char': char,
                'msg_id': msg.message_id
            }
        except:
            pass

# --- ⚔️ BATTLE ANIMATION FUNCTION ⚔️ ---
async def play_battle_animation(update, context, attacker_name, enemy_name, move_name):
    """Edits a message 3 times to simulate a battle"""
    msg = await update.message.reply_text(
        f"⚔️ **{attacker_name}** challenges **{enemy_name}**!",
        parse_mode="Markdown"
    )
    
    # Frame 1: Preparing
    await asyncio.sleep(0.5)
    await msg.edit_text(
        f"⚔️ **Battle Started!**\n"
        f"😤 {attacker_name} is charging Chakra...",
        parse_mode="Markdown"
    )
    
    # Frame 2: Enemy Attack
    await asyncio.sleep(0.5)
    await msg.edit_text(
        f"⚔️ **Battle Started!**\n"
        f"😤 {attacker_name} is charging Chakra...\n"
        f"💨 {enemy_name} throws a Kunai!",
        parse_mode="Markdown"
    )
    
    # Frame 3: Your Attack
    await asyncio.sleep(0.5)
    await msg.edit_text(
        f"⚔️ **Battle Started!**\n"
        f"😤 {attacker_name} is charging Chakra...\n"
        f"💨 {enemy_name} throws a Kunai!\n"
        f"💥 **{attacker_name} uses {move_name}!**",
        parse_mode="Markdown"
    )
    
    await asyncio.sleep(0.5)
    return msg # Return message object so we can edit it one last time with result

# --- RECRUIT / CATCH COMMAND ---
async def recruit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # 1. Is there a spawn?
    spawn = ACTIVE_SPAWNS.get(chat_id)
    if not spawn:
        # Don't reply if no spawn to avoid spam
        return

    # 2. 🛡️ FORCE JOIN SYSTEM 🛡️
    is_member = await check_force_join(user.id, context)
    if not is_member:
        keyboard = [[InlineKeyboardButton("📢 Join Update Channel", url=UPDATE_CHANNEL_LINK)]]
        await update.message.reply_text(
            f"🚫 **Access Denied!**\n\n"
            f"{user.mention_html()}, you must join our update channel to play!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
            quote=True
        )
        return

    # 3. Check Player Registration
    player = db.get_player(user.id)
    if not player:
        await update.message.reply_text("You must /register first!", quote=True)
        return

    # 4. Check Name Match
    target_name = spawn['char']['name'].lower()
    
    if not context.args:
         await update.message.reply_text(f"❌ Usage: `/recruit [Character Name]`", parse_mode="Markdown")
         return

    user_input = " ".join(context.args).lower()
    
    # --- 🔥 GUESSING LOGIC ---
    if user_input not in target_name:
         # WRONG NAME: Send message and delete after 3s to avoid flood
         fail_msg = await update.message.reply_text(
             f"❌ **Wrong Name!**\nIt is NOT {user_input}. Try again!", 
             quote=True,
             parse_mode="Markdown"
         )
         await asyncio.sleep(3)
         try: await fail_msg.delete()
         except: pass
         return

    # 5. CORRECT NAME! START BATTLE!
    # Pick a random Jutsu for animation
    moves = ["Rasengan", "Chidori", "Shadow Clone", "Fireball Jutsu", "Taijutsu Kick"]
    user_move = random.choice(moves)
    
    # 🔥 RUN ANIMATION
    battle_msg = await play_battle_animation(
        update, context, 
        attacker_name=user.first_name, 
        enemy_name=spawn['char']['name'], 
        move_name=user_move
    )
    
    # 6. Calculate Result
    rarity = spawn['char']['rarity']
    success_rate = get_catch_rate(rarity, player['rank'])
    
    if random.random() < success_rate:
        # SUCCESS!
        reward_xp = 50 if rarity == "Common" else (100 if rarity == "Epic" else 300)
        reward_ryo = 100 if rarity == "Common" else (500 if rarity == "Epic" else 2000)
        
        db.add_character_to_collection(user.id, spawn['char'])
        db.atomic_add_exp(user.id, reward_xp)
        db.atomic_add_ryo(user.id, reward_ryo)
        
        # Edit the battle message to show VICTORY
        await battle_msg.edit_text(
            f"🎉 **VICTORY!**\n\n"
            f"👤 **{spawn['char']['name']}** ({rarity})\n"
            f"📦 Captured by {user.mention_html()}!\n\n"
            f"⚡ +{reward_xp} EXP | 💰 +{reward_ryo} Ryo",
            parse_mode="HTML"
        )
        
        del ACTIVE_SPAWNS[chat_id]
        
    else:
        # FAIL
        await battle_msg.edit_text(
            f"💨 **DEFEAT...**\n\n"
            f"**{spawn['char']['name']}** dodged your {user_move} and escaped!\n"
            f"Better luck next time!",
            parse_mode="Markdown"
        )
        del ACTIVE_SPAWNS[chat_id]

# --- 🕵️ SECRET ADMIN COMMAND (/pp) ---
async def peek_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the current spawn name (Admin Only)"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Security Check
    if user_id != ADMIN_ID:
        return # Ignore non-admins
        
    spawn = ACTIVE_SPAWNS.get(chat_id)
    if not spawn:
        await update.message.reply_text("No character spawned here.", quote=True)
        return
        
    # Send the name secretly
    await update.message.reply_text(
        f"🕵️ **Secret Info:**\nName: `{spawn['char']['name']}`",
        parse_mode="Markdown"
    )

# --- COLLECTION COMMAND ---
async def collection_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the user's captured characters"""
    user = update.effective_user
    player = db.get_player(user.id)
    
    if not player:
        await update.message.reply_text("You must /register first!", quote=True)
        return

    collection = player.get('character_collection', {})
    
    if not collection:
        await update.message.reply_text(
            f"📜 **{user.first_name}'s Bingo Book**\n\n"
            "You haven't recruited any ninjas yet!\n"
            "Wait for them to appear in the group and use /recruit [name].",
            parse_mode="Markdown"
        )
        return

    sorted_items = sorted(
        collection.values(), 
        key=lambda x: (
            0 if x['rarity'] == 'Legendary' else 
            1 if x['rarity'] == 'Epic' else 2
        )
    )

    text = f"📜 **{user.first_name}'s Bingo Book** ({len(collection)} caught)\n\n"
    
    count = 0
    for char in sorted_items:
        if count >= 50:
            text += f"\n...and {len(sorted_items) - 50} more."
            break
            
        icon = "🌟" if char['rarity'] == 'Legendary' else "🔥" if char['rarity'] == 'Epic' else "⚪"
        text += f"{icon} **{char['name']}** (x{char['count']})\n"
        count += 1

    await update.message.reply_text(text, parse_mode="Markdown")
