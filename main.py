import logging
import json
import asyncio 
from datetime import timedelta, datetime, time

# Setup Logging FIRST
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    JobQueue,
    MessageHandler, 
    filters,
    InlineQueryHandler
)
from telegram.ext import ChatMemberHandler
from telegram.constants import ChatType
from html import escape

# Import our code modules
import database as db
import game_logic as gl
import missions
import training
import jutsu
import battle
import cache
import shop
import help_handler
import sudo       
import inventory  
import animations 
import minigames 
import minigames_v2
import leaderboard 
import daily 
# 🎮 UPDATED: New League Battle System imports
import inline_handler_league
import inline_handler_league_2
import league_system
import battle_enemies
import auto_register  # 🔥 AUTO-REGISTRATION
import data           # 🔥 LOGGING MODULE
import ai_chat        # 🔥 NEW: AI CHAT MODULE

# 🔥 NEW IMPORT: SPAWN SYSTEM
import spawn_system

# --- Constants ---
BOT_TOKEN = "8341511264:AAFjNIOYE5NbABPloFbz-r989l2ySRUs988"
START_IMAGE_URL = "https://envs.sh/r6z.jpg" 

# ═══════════════════════════════════════════════════
# 🔥 GROUP TRACKING FOR /bot_stats
# ═══════════════════════════════════════════════════

def update_group_count(context: ContextTypes.DEFAULT_TYPE, increment=True):
    """Update the total group count in bot_data"""
    try:
        if not hasattr(context.application, 'bot_data'):
            context.application.bot_data = {}
        
        current_count = context.application.bot_data.get('total_groups', 0)
        
        if increment:
            context.application.bot_data['total_groups'] = current_count + 1
            logger.info(f"✅ Group added. Total groups: {context.application.bot_data['total_groups']}")
        else:
            context.application.bot_data['total_groups'] = max(0, current_count - 1)
            logger.info(f"❌ Group removed. Total groups: {context.application.bot_data['total_groups']}")
    except Exception as e:
        logger.error(f"Error updating group count: {e}")

# --- Welcome Message Function ---
async def on_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message when the bot is added to a new group."""
    new_members = update.message.new_chat_members
    bot_id = context.bot.id

    for member in new_members:
        if member.id == bot_id:
            chat_id = update.message.chat.id
            logger.info(f"Bot was added to new group: {chat_id}")
            
            # 🔥 UPDATE GROUP COUNT
            update_group_count(context, increment=True)
            
            # 🔥 LOGGING: Send log to channel
            context.application.create_task(
                data.log_new_group(context, update.message.chat, update.message.from_user)
            )
            
            welcome_text = (
                "🔥 **A new Shinobi has entered the battle!** 🔥\n\n"
                "Thank you for adding me to your group!\n\n"
                "I am a Naruto RPG bot with missions, battles, and more. "
                "Your journey begins now!\n\n"
                "Just start using commands - no registration needed!"
            )
            
            keyboard = [
                [InlineKeyboardButton("SUMMON ME (Add to your group)", url="https://t.me/Naruto_gameXBot?startgroup=true")],
                [InlineKeyboardButton("UPDATES", url="https://t.me/SN_Telegram_bots_Stores")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=START_IMAGE_URL,
                    caption=welcome_text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to send welcome photo to {chat_id}: {e}. Sending text.")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=welcome_text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )

# 🔥 NEW: Handle Bot Removal ---
async def on_left_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detects if the bot was removed from a group."""
    left_member = update.message.left_chat_member
    bot_id = context.bot.id
    
    if left_member.id == bot_id:
        # The bot was kicked/removed
        chat = update.message.chat
        removed_by = update.message.from_user # The user who kicked the bot
        
        logger.info(f"Bot removed from group {chat.id} by {removed_by.id}")
        
        # 🔥 UPDATE GROUP COUNT
        update_group_count(context, increment=False)
        
        # Send Log
        context.application.create_task(
            data.log_bot_remove(context, chat, removed_by)
        )

# 🔥 NEW: Global Error Handler ---
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log the error and send a telegram message to notify the developer."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    # Send to log channel
    await data.log_error(update, context)

# 🎮 NEW: Daily Battle Reset Job
async def daily_battle_reset_job(context: ContextTypes.DEFAULT_TYPE):
    """Reset daily battles counter at midnight."""
    try:
        db.reset_daily_battles()
        logger.info("✅ Daily battles reset completed")
    except Exception as e:
        logger.error(f"Error in daily battle reset: {e}")

async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows users to register directly in the group."""
    user = update.effective_user
    if db.get_player(user.id):
        await update.message.reply_text(f"{user.mention_html()}, you are already registered! Use /profile to see your stats.", parse_mode="HTML")
        return

    keyboard = [[InlineKeyboardButton(name, callback_data=f"village_{key}")] for key, name in gl.VILLAGES.items()]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_photo(photo=START_IMAGE_URL, caption=f"🥷 **Welcome, {user.mention_html()}!**\n\nTo begin your journey in the Shinobi World, you must choose your home village.\n\n**Choose wisely:**", reply_markup=reply_markup, parse_mode="HTML")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # 🔥 LOGGING: Send log if started in PM
    if update.effective_chat.type == ChatType.PRIVATE:
        context.application.create_task(data.log_pm_start(context, user))
        
    player = db.get_player(user.id) 
    
    help_button = InlineKeyboardButton("❓ Help & Commands", callback_data="show_main_help")
    summon_button = InlineKeyboardButton("➕ Add to Group", url="https://t.me/Naruto_gameXBot?startgroup=true")
    updates_button = InlineKeyboardButton("📢 Updates Channel", url="https://t.me/SN_Telegram_bots_Stores")
    
    if player:
        # 🎮 Get league info
        league_display = league_system.get_league_display(player)
        
        # Existing player - personalized welcome back
        welcome_text = (
            f"🔥 <b>WELCOME BACK, {player.get('rank', 'Ninja').upper()}!</b> 🔥\n\n"
            f"<b>{escape(player.get('username', 'Warrior'))}</b> of <b>{player.get('village', 'Unknown Village')}</b>\n\n"
            f"┌────────────────────┐\n"
            f"📊 <b>Your Status:</b>\n"
            f"├ Level: <b>{player['level']}</b>\n"
            f"├ Rank: <b>{player.get('rank')}</b>\n"
            f"├ League: <b>{league_display['emoji']} {league_display['tier_name']}</b> ({league_display['points']} pts)\n"
            f"├ Ryo: <b>{player['ryo']:,} 💰</b>\n"
            f"├ Kills: <b>{player.get('kills', 0)} ☠️</b>\n"
            f"└ Record: <b>{player['wins']}W - {player['losses']}L</b>\n"
            f"└────────────────────┘\n\n"
            "The shinobi world awaits your return!\n\n"
            "<b>🎯 Quick Actions:</b>\n"
            "• <code>/missions</code> - Continue your journey\n"
            "• <code>/battle</code> - Challenge rivals\n"
            "• <code>@Naruto_gameXBot</code> - Inline League Battles!\n"
            "• <code>/shop</code> - Upgrade equipment\n"
            "• <code>/help</code> - Full command list\n\n"
            "<i>💡 Tip: Use inline mode for League Battles!</i>"
        )
        reply_markup = InlineKeyboardMarkup([[help_button], [summon_button, updates_button]])
        
        try:
            await context.bot.send_photo(update.effective_chat.id, photo=START_IMAGE_URL, caption=welcome_text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to send start photo: {e}")
            await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        # New player - epic introduction
        if update.effective_chat.type != ChatType.PRIVATE:
            await update.message.reply_text(f"👋 Hey {user.mention_html()}! Please use /register to start your ninja journey in this group.", parse_mode="HTML")
            return
            
        welcome_text = (
            f"🌟 <b>WELCOME TO SHINOBI CHRONICLES!</b> 🌟\n\n"
            f"Greetings, <b>{escape(user.first_name)}</b>!\n\n"
            "┌────────────────────────┐\n"
            "<b>⚡ THE ULTIMATE NARUTO RPG EXPERIENCE</b>\n"
            "└────────────────────────┘\n\n"
            
            "Step into a living, breathing ninja world where <b>YOUR</b> choices shape your destiny!\n\n"
            
            "<b>🎮 EPIC FEATURES AWAIT:</b>\n\n"
            
            "<b>⚔️ Combat & Competition:</b>\n"
            "• PvP Battles with real strategy\n"
            "• 🎮 League Battle System (Inline Mode!)\n"
            "• Criminal underworld (rob, assassinate, escape!)\n"
            "• Dynamic bounty & heat systems\n\n"
            
            "<b>📈 Character Progression:</b>\n"
            "• Level up from Academy Student → Kage\n"
            "• Climb League Ranks (Genin → Kage League)\n"
            "• Discover 10+ unique jutsu techniques\n"
            "• Unlock reputation titles with bonuses\n"
            "• Customize with weapons, armor & accessories\n\n"
            
            "<b>🌍 Living World:</b>\n"
            "• Daily missions & rewards\n"
            "• Player-driven economy & contracts\n"
            "• Legendary loot drops\n"
            "• Win streaks & multipliers\n\n"
            
            "<b>🏆 Compete & Dominate:</b>\n"
            "• Multiple leaderboards\n"
            "• Reputation system\n"
            "• Bounty hunter gameplay\n"
            "• Form alliances or go rogue!\n\n"
            
            "┌────────────────────────┐\n\n"
            
            "<b>🎯 CHOOSE YOUR VILLAGE:</b>\n"
            "Each village grants unique bonuses!\n\n"
            
            "🔥 <b>Konoha (Fire)</b> - Balanced & versatile\n"
            "💧 <b>Kiri (Water)</b> - Defensive specialists\n"
            "⚡ <b>Kumo (Lightning)</b> - Speed demons\n"
            "💨 <b>Suna (Wind)</b> - Tactical masters\n"
            "🪨 <b>Iwa (Earth)</b> - Tank builds\n\n"
            
            "└────────────────────────┘\n\n"
            
            "<b>💡 NEW PLAYER TIPS:</b>\n"
            "1️⃣ Complete missions for fast leveling\n"
            "2️⃣ Train daily to boost stats\n"
            "3️⃣ Try inline mode: <code>@Naruto_gameXBot</code>\n"
            "4️⃣ Check <code>/help</code> for full guide\n"
            "5️⃣ Claim <code>/daily</code> rewards!\n\n"
            
            "<i>🌙 Your legend begins with a single choice...\n"
            "Which village will you call home?</i>"
        )
        
        village_keyboard = [[InlineKeyboardButton(name, callback_data=f"village_{key}")] for key, name in gl.VILLAGES.items()]
        village_keyboard.append([help_button])
        village_keyboard.append([summon_button, updates_button])
        reply_markup = InlineKeyboardMarkup(village_keyboard)
        
        try:
            await context.bot.send_photo(update.effective_chat.id, photo=START_IMAGE_URL, caption=welcome_text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to send start photo: {e}")
            await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=reply_markup)

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = db.get_player(user.id)
    
    if not player:
        await update.message.reply_text(f"{user.mention_html()}, please /register first!", parse_mode="HTML")
        return
    
    player_equipment = player.get('equipment') or {}
    stats = gl.get_total_stats(player)
    eq = player_equipment
    eq_text = "\n".join([f"<b>{s.title()}:</b> {gl.SHOP_INVENTORY[eq[s]]['name'] if eq.get(s) else 'None'}" for s in ['weapon','armor','accessory']])
    
    # 🎮 Get league info
    league_display = league_system.get_league_display(player)
    streak = player.get('win_streak', 0)
    
    # Format next tier points (FIXED - no nested f-strings)
    next_tier_text = f" / {league_display['next_tier_points']}" if league_display['next_tier_points'] else " (MAX)"
    
    txt = (
        f"--- 💤 NINJA PROFILE 💤 ---\n"
        f"<b>Name:</b> {player['username']}\n"
        f"<b>Village:</b> {player['village']}\n"
        f"<b>Rank:</b> {player['rank']}\n"
        f"<b>Level:</b> {player['level']}\n"
        f"<b>EXP:</b> {player['exp']} / {gl.get_exp_for_next_level(player['level'])}\n"
        f"<b>Ryo:</b> {player['ryo']} 💰\n\n"
        f"--- 🎮 LEAGUE STATUS ---\n"
        f"<b>League:</b> {league_display['emoji']} {league_display['tier_name']} {league_display['stars']}\n"
        f"<b>Points:</b> {league_display['points']}{next_tier_text}\n"
        f"<b>Win Streak:</b> {'🔥' * min(streak, 10)}{streak}\n"
        f"<b>Total Battles:</b> {player.get('total_battles', 0)}\n\n"
        f"<b>HP:</b> {gl.health_bar(player['current_hp'], stats['max_hp'])}\n"
        f"<b>Chakra:</b> {gl.chakra_bar(player['current_chakra'], stats['max_chakra'])}\n\n"
        f"--- STATS ---\n"
        f"<b>Str:</b> {stats['strength']}\n"
        f"<b>Spd:</b> {stats['speed']}\n"
        f"<b>Int:</b> {stats['intelligence']}\n"
        f"<b>Stam:</b> {stats['stamina']}\n\n"
        f"--- EQUIPMENT ---\n{eq_text}\n"
        f"<b>Wins:</b> {player['wins']} | <b>Losses:</b> {player['losses']}\n"
        f"<b>Kills:</b> {player.get('kills', 0)} ☠️"
    )
    
    await update.message.reply_text(txt, parse_mode="HTML")

async def village_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle village selection with proper message type detection - FIXED"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    # Check if already registered
    if db.get_player(user.id):
        try:
            # ✅ FIX: Detect message type and edit accordingly
            if query.message.photo:
                # Message has photo - edit caption
                await query.edit_message_caption(
                    caption=f"{user.mention_html()}, you are already registered!",
                    parse_mode="HTML"
                )
            else:
                # Message is text only - edit text
                await query.edit_message_text(
                    text=f"{user.mention_html()}, you are already registered!",
                    parse_mode="HTML"
                )
        except Exception as e:
            # Fallback: send new message if editing fails
            logger.error(f"Error editing registration message: {e}")
            await query.message.reply_text(
                f"{user.mention_html()}, you are already registered!",
                parse_mode="HTML"
            )
        return
    
    # Get selected village
    v_key = query.data.split('_')[1]
    v_name = gl.VILLAGES[v_key]
    
    # Create player
    if db.create_player(user.id, user.username or user.first_name, v_name):
        kb = [
            [InlineKeyboardButton("❓ Help", callback_data="show_main_help")],
            [InlineKeyboardButton("UPDATES", url="https://t.me/SN_Telegram_bots_Stores")]
        ]
        
        success_text = (
            f"🎉 <b>REGISTRATION COMPLETE!</b> 🎉\n\n"
            f"{user.mention_html()} has joined <b>{v_name}</b>!\n\n"
            f"Your ninja journey begins now.\n"
            f"Use /profile to see your stats!\n\n"
            f"💡 <b>Try inline battles:</b> Type <code>@Naruto_gameXBot</code> in any chat!"
        )
        
        try:
            # ✅ FIX: Detect message type
            if query.message.photo:
                # Message has photo - edit caption
                await query.edit_message_caption(
                    caption=success_text,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            else:
                # Message is text only - edit text
                await query.edit_message_text(
                    text=success_text,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
        except Exception as e:
            # Fallback: send new message if editing fails
            logger.error(f"Error editing success message: {e}")
            await query.message.reply_text(
                success_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(kb)
            )
    else:
        # Registration failed
        await query.message.reply_text(
            "❌ <b>Registration failed!</b>\n\nPlease try again with /register",
            parse_mode="HTML"
        )

def main():
    logger.info("Starting bot...")
    db.create_tables()
    db.update_schema()
    app = Application.builder().token(BOT_TOKEN).build()
    
    # 🔥 Initialize group counter to 0 on bot start
    app.bot_data['total_groups'] = 0

    # Core
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("register", register_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("help", help_handler.show_main_help_menu))
    app.add_handler(CommandHandler("inventory", inventory.inventory_command))

    # 🔥 NEW: SPAWN SYSTEM HANDLERS
    app.add_handler(CommandHandler(("recruit", "catch"), spawn_system.recruit_command))
    app.add_handler(CommandHandler("collection", spawn_system.collection_command))
    app.add_handler(CommandHandler("forcespawn", spawn_system.forcespawn_command))

    # Minigames - Core (Enhanced)
    app.add_handler(CommandHandler(("wallet", "balance"), minigames.wallet_command))
    app.add_handler(CommandHandler("bal", minigames.balance_command))
    app.add_handler(CommandHandler(("steal", "rob"), minigames.steal_command))
    app.add_handler(CommandHandler("scout", minigames.scout_command))
    app.add_handler(CommandHandler("kill", minigames.kill_command))
    app.add_handler(CommandHandler("gift", minigames.gift_command))
    app.add_handler(CommandHandler("protect", minigames.protect_command))
    app.add_handler(CommandHandler("heal", minigames.heal_command))

    # 🆕 MINIGAMES V2 - Advanced Systems
    app.add_handler(CommandHandler("bountyboard", minigames_v2.bounty_board_command))
    app.add_handler(CommandHandler("contracts", minigames_v2.contracts_command))
    app.add_handler(CommandHandler("contract", minigames_v2.place_contract_command))
    app.add_handler(CommandHandler("legendary", minigames_v2.inventory_command))
    app.add_handler(CommandHandler("reputation", minigames_v2.reputation_command))
    app.add_handler(CommandHandler("heat", minigames_v2.heat_status_command))
    
    # 🆕 ESCAPE MECHANICS CALLBACK
    app.add_handler(CallbackQueryHandler(minigames.escape_callback, pattern="^escape_"))
    
    # 🆕 LEGENDARY ITEM CALLBACKS
    app.add_handler(CallbackQueryHandler(minigames_v2.use_item_callback, pattern="^use_legendary_item$"))
    app.add_handler(CallbackQueryHandler(minigames_v2.use_item_callback, pattern="^use_item_"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.edit_message_text("Cancelled."), pattern="^cancel_item_use$"))

    # Daily & Leaderboard
    app.add_handler(CommandHandler("daily", daily.daily_command))
    app.add_handler(CallbackQueryHandler(daily.daily_callback, pattern="^daily_claim_check$"))
    app.add_handler(CommandHandler("leaderboard", leaderboard.leaderboard_command))
    app.add_handler(CommandHandler("topkillers", leaderboard.topkillers_command))
    app.add_handler(CallbackQueryHandler(leaderboard.leaderboard_back_callback, pattern="^leaderboard_main$"))
    app.add_handler(CallbackQueryHandler(leaderboard.leaderboard_callback, pattern="^leaderboard_"))

    # RPG Modules
    app.add_handler(CommandHandler("missions", missions.missions_command))
    app.add_handler(CallbackQueryHandler(missions.mission_callback, pattern="^mission_"))
    app.add_handler(CommandHandler("train", training.training_command))
    app.add_handler(CallbackQueryHandler(training.training_callback, pattern="^train_"))
    app.add_handler(CommandHandler("jutsus", jutsu.jutsus_command))
    app.add_handler(CommandHandler("combine", jutsu.combine_command))
    app.add_handler(CommandHandler("shop", shop.shop_command))
    app.add_handler(CallbackQueryHandler(shop.shop_buy_callback, pattern="^shop_buy_"))

    # Battle - /fight REMOVED, only /battle remains
    app.add_handler(CommandHandler("battle", battle.battle_command))
    app.add_handler(CallbackQueryHandler(battle.battle_invite_callback, pattern="^battle_invite_"))
    app.add_handler(CallbackQueryHandler(battle.battle_action_callback, pattern="^battle_action_")) 
    app.add_handler(CallbackQueryHandler(battle.battle_stance_callback, pattern="^battle_stance_"))
    app.add_handler(CallbackQueryHandler(battle.battle_jutsu_callback, pattern="^battle_jutsu_"))   
    app.add_handler(CallbackQueryHandler(battle.battle_item_callback, pattern="^battle_item_"))
    app.add_handler(CallbackQueryHandler(battle.battle_predict_callback, pattern="^predict_"))

    # Sudo 
    app.add_handler(CommandHandler("server_stats", sudo.server_stats_command))
    app.add_handler(CommandHandler("db_query", sudo.db_query_command))
    app.add_handler(CommandHandler("sudo_give", sudo.sudo_give_command))
    app.add_handler(CommandHandler("sudo_set", sudo.sudo_set_command))
    app.add_handler(CommandHandler("list_boss_chats", sudo.list_boss_chats_command))
    app.add_handler(CommandHandler("sudo_leave", sudo.sudo_leave_command))
    app.add_handler(CommandHandler("get_user", sudo.get_user_command))
    app.add_handler(CommandHandler("bot_stats", sudo.bot_stats_command))
    app.add_handler(CommandHandler("clearcache", sudo.clearcache_command))
    app.add_handler(CommandHandler("flushcache", sudo.flushcache_command))
    
    # 🎮 UPDATED: New League Battle System Inline Handlers
    app.add_handler(InlineQueryHandler(inline_handler_league.inline_query_handler))
    
    # 🎮 NEW: League Battle Callback Handler (pattern: lb_ = league battle)
    app.add_handler(CallbackQueryHandler(inline_handler_league_2.league_battle_callback, pattern="^lb_"))
    
    # Passive Handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_chat_members))
    
    # 🔥 NEW: Log when bot is removed
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_left_chat_member))

    # Global Callbacks
    app.add_handler(CallbackQueryHandler(village_selection_callback, pattern="^village_"))
    app.add_handler(CallbackQueryHandler(help_handler.show_main_help_menu, pattern="^show_main_help$"))
    app.add_handler(CallbackQueryHandler(help_handler.show_module_help, pattern="^help_module_"))
    app.add_handler(CallbackQueryHandler(help_handler.back_to_main_help_callback, pattern="^back_to_main_help$"))

    # 🔥 SPAWN SYSTEM TRIGGER (Checks every message, runs in Group 5)
    app.add_handler(MessageHandler(
        filters.TEXT & (~filters.COMMAND), 
        spawn_system.trigger_spawn_on_message
    ), group=5)
    
    # 🔥 UPDATED: Now accepts TEXT AND STICKERS with CORRECT Filter
    app.add_handler(MessageHandler((filters.TEXT | filters.Sticker.ALL) & (~filters.COMMAND), ai_chat.naruto_chat_handler), group=2)
    
    # 🔥 NEW: Register Global Error Handler
    app.add_error_handler(global_error_handler)
    
    # 🎮 NEW: Daily Battle Reset Job (runs at midnight)
    job_queue = app.job_queue
    job_queue.run_daily(
        daily_battle_reset_job,
        time=time(hour=0, minute=0, second=0)  # Midnight UTC
    )
    logger.info("✅ Daily battle reset job scheduled")

    logger.info("🔥 Bot is polling - OPTIMIZED & FAST with LEAGUE BATTLES! 🔥")
    app.run_polling()

if __name__ == "__main__":
    main()
