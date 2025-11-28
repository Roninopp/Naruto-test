import logging
import traceback
import html
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Setup simple logger for console errors
logger = logging.getLogger(__name__)

# Your Log Channel ID
LOG_CHANNEL_ID = -1003123258753

async def log_pm_start(context: ContextTypes.DEFAULT_TYPE, user):
    """
    Logs when a user starts the bot in PM.
    Format: #User started the bot in pm (mention) ID
    """
    try:
        mention = user.mention_html()
        user_id = user.id
        username = f"@{user.username}" if user.username else "No Username"
        
        log_text = (
            f"#User started the bot in pm\n"
            f"<b>User:</b> {mention}\n"
            f"<b>ID:</b> <code>{user_id}</code>\n"
            f"<b>Username:</b> {username}"
        )
        
        await context.bot.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=log_text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Failed to send PM Start Log: {e}")

async def log_new_group(context: ContextTypes.DEFAULT_TYPE, chat, added_by):
    """
    Logs when the bot is added to a group.
    Format: #NewGroup Name (chatlink) added by ()
    """
    try:
        chat_title = html.escape(chat.title)
        chat_id = chat.id
        
        # Attempt to get a link: Username > Invite Link > Fallback
        if chat.username:
            chat_link = f"https://t.me/{chat.username}"
        elif chat.invite_link:
            chat_link = chat.invite_link
        else:
            chat_link = "Private/No Link"

        adder_mention = added_by.mention_html() if added_by else "Unknown User"
        
        log_text = (
            f"#NewGroup\n"
            f"<b>Name:</b> {chat_title}\n"
            f"<b>Link:</b> {chat_link}\n"
            f"<b>ID:</b> <code>{chat_id}</code>\n"
            f"<b>Added by:</b> {adder_mention}"
        )
        
        await context.bot.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=log_text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Failed to send New Group Log: {e}")

async def log_bot_remove(context: ContextTypes.DEFAULT_TYPE, chat, removed_by):
    """
    Logs when the bot is removed/kicked from a group.
    Format: #REMOVED From (chatname) By (name)
    """
    try:
        chat_title = html.escape(chat.title)
        chat_id = chat.id
        user_mention = removed_by.mention_html() if removed_by else "Unknown User"
        
        log_text = (
            f"#REMOVED From Group\n"
            f"<b>Chat:</b> {chat_title}\n"
            f"<b>Chat ID:</b> <code>{chat_id}</code>\n"
            f"<b>By:</b> {user_mention}"
        )
        
        await context.bot.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=log_text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Failed to send Remove Log: {e}")

async def log_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """
    Logs internal errors to the channel.
    Format: #ERROR (module) (error details)
    """
    try:
        # Get the error from context
        error = context.error
        
        # Get traceback string
        tb_list = traceback.format_exception(None, error, error.__traceback__)
        tb_string = ''.join(tb_list)
        
        # Simple logic to guess which file caused it
        module_name = "Unknown Module"
        if "minigames.py" in tb_string: module_name = "minigames.py"
        elif "battle.py" in tb_string: module_name = "battle.py"
        elif "missions.py" in tb_string: module_name = "missions.py"
        elif "game_logic.py" in tb_string: module_name = "game_logic.py"
        elif "main.py" in tb_string: module_name = "main.py"
        
        # Information about the user/chat where error happened
        chat_info = "Unknown Chat"
        user_info = "Unknown User"
        
        if isinstance(update, Update):
            if update.effective_chat:
                chat_info = f"{update.effective_chat.title} ({update.effective_chat.id})"
            if update.effective_user:
                user_info = f"{update.effective_user.first_name} ({update.effective_user.id})"

        # Format the error message (Limit length to avoid Telegram limits)
        error_msg = html.escape(str(error))
        
        log_text = (
            f"#ERROR <b>{module_name}</b>\n"
            f"<b>Reason:</b> {error_msg}\n"
            f"<b>Chat:</b> {html.escape(chat_info)}\n"
            f"<b>User:</b> {html.escape(user_info)}\n\n"
            f"<b>Traceback (Snippet):</b>\n"
            f"<pre>{html.escape(tb_string[-1000:])}</pre>" # Last 1000 chars
        )
        
        await context.bot.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=log_text,
            parse_mode=ParseMode.HTML
        )
        
        # Optional: Notify user in chat that an error occurred
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ <b>An error occurred!</b>\nThis issue has been automatically reported to the developer.",
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        logger.error(f"Failed to send Error Log: {e}")
