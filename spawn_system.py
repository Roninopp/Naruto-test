import logging
import asyncio
import json
import random
from telegram import Update
from telegram.ext import ContextTypes
import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- CONFIG ---
SPAWN_CHANCE = 0.3  # 30% chance per check
MIN_COOLDOWN = 1800 # 30 minutes between spawns per group
ACTIVE_SPAWNS = {}  # Stores current spawn: {chat_id: {char_data, message_id}}
GROUP_COOLDOWNS = {} # Stores last spawn time: {chat_id: timestamp}

# --- LOAD CHARACTERS ---
try:
    with open("naruto_characters.json", "r") as f:
        CHARACTERS = json.load(f)
    logger.info(f"✅ Loaded {len(CHARACTERS)} characters for spawning.")
except Exception as e:
    logger.error(f"❌ Could not load naruto_characters.json: {e}")
    CHARACTERS = []

# --- RARITY LOGIC ---
# Simple logic to make known characters harder to catch
LEGENDARY_NAMES = ["Naruto", "Sasuke", "Madara", "Itachi", "Kakashi", "Minato", "Hashirama", "Jiraiya", "Tsunade", "Orochimaru", "Pain", "Obito", "Kaguya"]
EPIC_NAMES = ["Gaara", "Rock Lee", "Hinata", "Sakura", "Shikamaru", "Neji", "Killer Bee", "Kurama", "Guy"]

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

# --- SCHEDULER ---
async def spawn_scheduler(app):
    """Background task to spawn characters"""
    logger.info("🚀 Spawn Scheduler Started!")
    while True:
        try:
            # 1. Wait random time to avoid predictable patterns
            await asyncio.sleep(random.randint(60, 300)) # Check every 1-5 minutes
            
            # 2. Get all groups (You might need a function in db to get all active group IDs)
            # For now, we will rely on groups that have sent messages recently (cached in main)
            # Or use a placeholder list if you don't track active groups in DB yet
            # active_chats = app.bot_data.get('active_group_ids', []) 
            
            # [TEMPORARY FIX] If you don't have a 'get_all_groups' function:
            # We skip the global loop and rely on 'trigger_spawn_on_message' instead (See below)
            pass 

        except Exception as e:
            logger.error(f"Spawn loop error: {e}")

async def trigger_spawn_on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Called from main.py on every message. 
    Checks cooldown and triggers spawn randomly.
    """
    chat_id = update.effective_chat.id
    current_time = asyncio.get_event_loop().time()
    
    # 1. Check Cooldown
    last_spawn = GROUP_COOLDOWNS.get(chat_id, 0)
    if current_time - last_spawn < MIN_COOLDOWN:
        return

    # 2. Random Chance
    if random.random() > SPAWN_CHANCE:
        return

    # 3. SPAWN!
    await spawn_character(chat_id, context)
    GROUP_COOLDOWNS[chat_id] = current_time

async def spawn_character(chat_id, context):
    """Selects character and sends to group"""
    if not CHARACTERS: return

    char = random.choice(CHARACTERS)
    rarity = get_rarity(char['name'])
    char['rarity'] = rarity # Inject rarity
    
    caption = (
        f"⚠️ **A Wild Ninja Appeared!**\n\n"
        f"👤 **{char['name']}**\n"
        f"🌟 Rarity: **{rarity}**\n\n"
        f"⚔️ /recruit {char['name']} (or click button)"
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
        logger.error(f"Failed to spawn in {chat_id}: {e}")

# --- RECRUIT / ATTACK HANDLER ---
async def recruit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # 1. Is there a spawn?
    spawn = ACTIVE_SPAWNS.get(chat_id)
    if not spawn:
        await update.message.reply_text("There is no ninja nearby to recruit!", quote=True)
        return

    # 2. Check Player
    player = db.get_player(user.id)
    if not player:
        await update.message.reply_text("You must /register first!", quote=True)
        return

    # 3. Check Name Match
    # User must type "/recruit Naruto" (case insensitive)
    target_name = spawn['char']['name'].lower()
    
    # Allow loose matching if command has args
    if not context.args:
         await update.message.reply_text(f"❌ You must specify the name!\nExample: <code>/recruit {target_name.split()[0]}</code>", parse_mode="HTML")
         return

    user_input = " ".join(context.args).lower()
    
    # Simple check: is the input inside the name?
    if user_input not in target_name:
         await update.message.reply_text("❌ Wrong name! The ninja attacks you and flees!", quote=True)
         # Optional: Punish player HP here
         return

    # 4. Calculate Success
    rarity = spawn['char']['rarity']
    success_rate = get_catch_rate(rarity, player['rank'])
    
    # 5. Result
    if random.random() < success_rate:
        # SUCCESS!
        reward_xp = 50 if rarity == "Common" else 200
        
        # Save to DB
        db.add_character_to_collection(user.id, spawn['char'])
        db.atomic_add_exp(user.id, reward_xp)
        
        await update.message.reply_text(
            f"🎉 **SUCCESS!**\n\n"
            f"{user.mention_html()} recruited **{spawn['char']['name']}**!\n"
            f"📦 Added to Collection.\n"
            f"⚡ +{reward_xp} EXP",
            parse_mode="HTML"
        )
        
        # Clear Spawn
        del ACTIVE_SPAWNS[chat_id]
        
    else:
        # FAIL
        await update.message.reply_text(
            f"💨 **FAILED!**\n\n"
            f"{spawn['char']['name']} dodged your attempt and escaped!",
            parse_mode="Markdown"
        )
        # Clear Spawn (It ran away)
        del ACTIVE_SPAWNS[chat_id]
