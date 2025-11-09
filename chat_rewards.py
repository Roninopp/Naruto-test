import logging
import random
import datetime
from telegram import Update
from telegram.ext import ContextTypes

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- 1. Define The Milestones and Rewards ---
REWARD_MILESTONES = {
    50: {'ryo': 40, 'exp': 60},
    100: {'ryo': 100, 'exp': 120},
    200: {'ryo': 220, 'exp': 250},
    300: {'ryo': 500, 'exp': 600},
}

# --- 2. Define The Funny Messages ---
MILESTONE_MESSAGES = {
    50: [
        "Wow, you're a talker! Keep it up!",
        "Is that 50 messages already? You're on fire!",
        "You've officially been classified as 'Chatty'. Nice!"
    ],
    100: [
        "A true Chatterbox! You've hit 100 messages!",
        "Your special jutsu: Talk-no-Jutsu! It's working!",
        "Impressive! You've already doubled the first milestone."
    ],
    200: [
        "Are your fingers tired yet? 200 messages!",
        "You are... unstoppable! A true Jonin of Jabber!",
        "Incredible! Most ninja don't have this much to say."
    ],
    300: [
        "LEGENDARY! You have mastered the art of conversation.",
        "You are the Kage of Conversation! 300 messages!",
        "The group has been officially blessed by your presence. Amazing!"
    ]
}

# --- 3. The Main Handler ---
async def on_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listens to every group message to track chat activity."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    if user.is_bot: return

    # --- DEBUG LOG: Uncomment this if it still doesn't work to see every message ---
    # logger.info(f"Chat event received from {user.id} in {chat_id}")

    player = db.get_player(user.id)
    if not player: return 

    today = datetime.date.today()
    activity = db.get_chat_activity(user.id, chat_id)
    
    current_count = 0
    last_milestone = 0

    if not activity:
        db.create_chat_activity(user.id, chat_id, today)
        current_count = 1
    else:
        # --- FIX: Ensure we are comparing dates correctly ---
        last_date = activity['last_active_date']
        # If it came from DB as a string (common with some setups), convert it
        if isinstance(last_date, str):
            try:
                last_date = datetime.date.fromisoformat(last_date)
            except ValueError:
                last_date = today # Fallback if bad data

        if last_date < today:
            # New day, reset
            db.reset_chat_activity(user.id, chat_id, today)
            current_count = 1
            last_milestone = 0
        else:
            # Same day, increment
            current_count = db.increment_chat_activity(user.id, chat_id)
            last_milestone = activity['last_reward_milestone']

    # Fallback if DB increment failed returning None
    if not current_count and activity: 
         current_count = activity.get('message_count', 0) + 1

    # --- Reward Check ---
    next_milestone = 0
    for m in sorted(REWARD_MILESTONES.keys()):
        if last_milestone < m:
            next_milestone = m
            break
            
    if next_milestone == 0: return

    if current_count >= next_milestone and last_milestone < next_milestone:
        try:
            reward = REWARD_MILESTONES[next_milestone]
            # Fetch fresh player data before awarding to avoid overwrite race conditions
            p_data = db.get_player(user.id)
            p_data['ryo'] += reward['ryo']
            p_data['exp'] += reward['exp']
            p_data['total_exp'] += reward['exp']
            
            fp, lvl, msgs = gl.check_for_level_up(p_data)
            db.update_player(user.id, fp)
            # IMPORTANT: Update milestone so they don't get it again every message
            db.update_chat_milestone(user.id, chat_id, next_milestone)
            
            msg = random.choice(MILESTONE_MESSAGES[next_milestone])
            final_msg = (f"{msg} 🎉\n\n🗣️ {user.mention_html()} hit **{next_milestone} messages** today!\n🎁 **Reward:** +{reward['ryo']} Ryo 💰 | +{reward['exp']} EXP ✨")
            
            # Find next goal for teaser
            goal = 0
            for m in sorted(REWARD_MILESTONES.keys()):
                if m > next_milestone:
                    goal = m
                    break
            if goal > 0: final_msg += f"\n\n🎯 *Next Mission:* Reach **{goal} messages**!"
            else: final_msg += f"\n\n👑 You have hit the **MAX** daily chat rewards!"

            if lvl: final_msg += "\n\n" + "\n".join(msgs)
            
            await context.bot.send_message(chat_id=chat_id, text=final_msg, parse_mode="HTML")
            logger.info(f"Chat reward {next_milestone} given to {user.id}")
            
        except Exception as e:
            logger.error(f"Error giving chat reward to {user.id}: {e}")
