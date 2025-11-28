"""
🚀 AUTO_REGISTER.PY - Automatic Player Registration System
This module handles automatic player registration when they use ANY command.

Features:
- Auto-register on first command use
- Random village/clan assignment
- Works for both command user and replied-to users
- Seamless integration with existing commands
"""

import logging
import random
import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# Random village selection pool
RANDOM_VILLAGES = [
    "Konohagakure (Leaf)",
    "Kirigakure (Mist)", 
    "Kumogakure (Cloud)",
    "Sunagakure (Sand)",
    "Iwagakure (Rock)"
]


def auto_register_player(user_id, username):
    """
    Auto-registers a player if they don't exist.
    
    Args:
        user_id (int): Telegram user ID
        username (str): User's name/username
        
    Returns:
        dict: Player data (existing or newly created)
        bool: True if newly registered, False if already existed
    """
    # Sanitize username (remove special chars that might cause DB issues)
    safe_username = ''.join(char for char in username if char.isalnum() or char in (' ', '_', '-'))[:50]
    if not safe_username:
        safe_username = f"Player_{user_id}"
    
    # Check if player already exists
    player = db.get_player(user_id)
    
    if player:
        logger.info(f"Player {safe_username} (ID: {user_id}) already exists.")
        return player, False
    
    # Player doesn't exist - auto-register with random village
    random_village = random.choice(RANDOM_VILLAGES)
    
    # Mark as auto-registered
    success = db.create_player(user_id, safe_username, random_village, auto_registered=True)
    
    if success:
        logger.info(f"✅ AUTO-REGISTERED: {safe_username} (ID: {user_id}) → {random_village}")
        # Fetch the newly created player - try multiple times
        for attempt in range(3):
            new_player = db.get_player(user_id)
            if new_player:
                return new_player, True
            logger.warning(f"Retry {attempt + 1}/3: Fetching newly created player {user_id}")
            import time
            time.sleep(0.1)  # Brief delay
        
        logger.error(f"❌ Created player but can't fetch: {safe_username} (ID: {user_id})")
        return None, False
    else:
        logger.error(f"❌ Failed to auto-register {safe_username} (ID: {user_id})")
        # Try fetching one more time in case of race condition
        player = db.get_player(user_id)
        if player:
            logger.info(f"⚠️ Player existed after all: {safe_username} (ID: {user_id})")
            return player, False
        return None, False


def ensure_player_exists(user_id, username):
    """
    Simplified version - just ensures player exists.
    Returns player data or None.
    
    Args:
        user_id (int): Telegram user ID
        username (str): User's name/username
        
    Returns:
        dict or None: Player data
    """
    player, was_created = auto_register_player(user_id, username)
    return player


def auto_register_both_users(user, target_user=None):
    """
    Auto-registers both the command user and the target user (if replied).
    
    Args:
        user: Telegram User object (command sender)
        target_user: Telegram User object (replied-to user, optional)
        
    Returns:
        tuple: (sender_player, target_player, sender_was_new, target_was_new)
    """
    # Auto-register command sender
    sender_username = user.username or user.first_name or f"User_{user.id}"
    sender_player, sender_new = auto_register_player(user.id, sender_username)
    
    target_player = None
    target_new = False
    
    # Auto-register target if provided
    if target_user and not target_user.is_bot:
        target_username = target_user.username or target_user.first_name or f"User_{target_user.id}"
        target_player, target_new = auto_register_player(target_user.id, target_username)
    
    return sender_player, target_player, sender_new, target_new


def get_welcome_message(username, village, is_group=False):
    """
    Returns a welcome message for newly auto-registered players.
    
    Args:
        username (str): Player's username
        village (str): Assigned village
        is_group (bool): Whether registration happened in a group
        
    Returns:
        str: Welcome message
    """
    if is_group:
        return (
            f"🎉 <b>AUTO-REGISTERED!</b>\n\n"
            f"<b>{username}</b> has joined <b>{village}</b>!\n"
            f"Your ninja journey begins now! 🥷"
        )
    else:
        return (
            f"✨ <b>WELCOME, SHINOBI!</b> ✨\n\n"
            f"You've been automatically registered!\n"
            f"<b>Village:</b> {village}\n\n"
            f"Use /profile to see your stats!"
        )


# ============================================
# USAGE EXAMPLES FOR EXISTING COMMANDS
# ============================================

"""
HOW TO INTEGRATE INTO YOUR COMMANDS:

1. SIMPLE COMMAND (e.g., /wallet on yourself):
   -----------------------------------------------
   from auto_register import ensure_player_exists
   
   async def wallet_command(update, context):
       user = update.effective_user
       
       # 🔥 AUTO-REGISTER IF NEEDED
       player = ensure_player_exists(user.id, user.username or user.first_name)
       
       if not player:
           await update.message.reply_text("❌ Registration failed. Try again.")
           return
       
       # Continue with normal command logic...
       await update.message.reply_text(f"💰 Ryo: {player['ryo']}")


2. COMMAND WITH REPLY TARGET (e.g., /kill, /gift, /steal):
   -----------------------------------------------
   from auto_register import auto_register_both_users
   
   async def kill_command(update, context):
       user = update.effective_user
       
       if not update.message.reply_to_message:
           await update.message.reply_text("Reply to a user to kill them!")
           return
       
       target_user = update.message.reply_to_message.from_user
       
       # 🔥 AUTO-REGISTER BOTH USERS
       attacker, victim, attacker_new, victim_new = auto_register_both_users(user, target_user)
       
       if not attacker or not victim:
           await update.message.reply_text("❌ Registration failed.")
           return
       
       # Optional: Show welcome message for new players
       if attacker_new:
           await update.message.reply_text(
               f"✨ You've been auto-registered as a ninja! Village: {attacker['village']}"
           )
       
       if victim_new:
           await update.message.reply_text(
               f"✨ {target_user.first_name} has been auto-registered! Village: {victim['village']}"
           )
       
       # Continue with normal kill logic...
       # ... rest of kill command code ...


3. GROUP COMMAND (e.g., /fight in group):
   -----------------------------------------------
   from auto_register import auto_register_both_users, get_welcome_message
   
   async def fight_command(update, context):
       user = update.effective_user
       target_user = update.message.reply_to_message.from_user if update.message.reply_to_message else None
       
       # 🔥 AUTO-REGISTER BOTH
       player1, player2, p1_new, p2_new = auto_register_both_users(user, target_user)
       
       # Show welcome for new players in groups
       if p1_new:
           welcome = get_welcome_message(user.first_name, player1['village'], is_group=True)
           await update.message.reply_text(welcome, parse_mode="HTML")
       
       if p2_new and player2:
           welcome = get_welcome_message(target_user.first_name, player2['village'], is_group=True)
           await update.message.reply_text(welcome, parse_mode="HTML")
       
       # Continue with fight logic...
"""
