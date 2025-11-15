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
    
    # ✅ FIX 1: Make sure update has a message
    if not update.message or not update.message.text:
        return
    
    user = update.effective_user
    chat_id = update.effective_chat.id

    # ✅ FIX 2: Ignore bots
    if user.is_bot:
        return

    # ✅ FIX 3: Get player data
    player = db.get_player(user.id)
    if not player:
        return

    # ✅ FIX 4: Use date objects consistently
    today = datetime.date.today()
    activity = db.get_chat_activity(user.id, chat_id)
    
    current_count = 0
    last_milestone = 0

    if not activity:
        # First time seeing this user in this chat today
        db.create_chat_activity(user.id, chat_id, today)
        current_count = 1
        last_milestone = 0
    else:
        # ✅ FIX 5: Handle date conversion properly
        last_date = activity['last_active_date']
        
        # Convert string to date if needed
        if isinstance(last_date, str):
            try:
                last_date = datetime.date.fromisoformat(last_date)
            except (ValueError, TypeError):
                last_date = today
        
        # Check if it's a new day
        if last_date < today:
            # New day, reset counters
            db.reset_chat_activity(user.id, chat_id, today)
            current_count = 1
            last_milestone = 0
        else:
            # Same day, increment
            current_count = db.increment_chat_activity(user.id, chat_id)
            last_milestone = activity.get('last_reward_milestone', 0)
            
            # ✅ FIX 6: Handle None return from increment
            if current_count is None:
                current_count = activity.get('message_count', 0) + 1

    # ✅ FIX 7: Better logging for debugging
    logger.debug(f"Chat activity: User {user.id} in chat {chat_id} - Count: {current_count}, Last milestone: {last_milestone}")

    # --- Reward Check ---
    next_milestone = None
    for milestone in sorted(REWARD_MILESTONES.keys()):
        if current_count >= milestone and last_milestone < milestone:
            next_milestone = milestone
            break
    
    # No milestone reached yet
    if next_milestone is None:
        return

    # ✅ FIX 8: Give reward
    try:
        reward = REWARD_MILESTONES[next_milestone]
        
        # ✅ FIX 9: Fetch FRESH player data to avoid overwriting changes
        fresh_player = db.get_player(user.id)
        if not fresh_player:
            logger.error(f"Player {user.id} disappeared during reward processing!")
            return
        
        # Update player stats
        fresh_player['ryo'] += reward['ryo']
        fresh_player['exp'] += reward['exp']
        fresh_player['total_exp'] += reward['exp']
        
        # Check for level up
        final_player, leveled_up, level_up_messages = gl.check_for_level_up(fresh_player)
        
        # Save to database
        db.update_player(user.id, final_player)
        
        # ✅ FIX 10: CRITICAL - Update milestone in DB so they don't get it again
        db.update_chat_milestone(user.id, chat_id, next_milestone)
        
        # Build reward message
        msg = random.choice(MILESTONE_MESSAGES[next_milestone])
        final_msg = (
            f"{msg} 🎉\n\n"
            f"🗣️ {user.mention_html()} hit **{next_milestone} messages** today!\n"
            f"🎁 **Reward:** +{reward['ryo']} Ryo 💰 | +{reward['exp']} EXP ✨"
        )
        
        # Find next goal
        next_goal = None
        for m in sorted(REWARD_MILESTONES.keys()):
            if m > next_milestone:
                next_goal = m
                break
        
        if next_goal:
            final_msg += f"\n\n🎯 *Next Mission:* Reach **{next_goal} messages**!"
        else:
            final_msg += f"\n\n👑 You have hit the **MAX** daily chat rewards!"

        # Add level up message if applicable
        if leveled_up:
            final_msg += "\n\n" + "\n".join(level_up_messages)
        
        # ✅ FIX 11: Send message with error handling
        try:
            await context.bot.send_message(
                chat_id=chat_id, 
                text=final_msg, 
                parse_mode="HTML"
            )
            logger.info(f"✅ Chat reward {next_milestone} given to user {user.id} in chat {chat_id}")
        except Exception as send_error:
            logger.error(f"Failed to send reward message: {send_error}")
            
    except Exception as e:
        logger.error(f"❌ Error processing chat reward for user {user.id}: {e}", exc_info=True)
