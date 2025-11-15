import logging
import json
import asyncio 
from datetime import timedelta, datetime 

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
import world_boss 
import sudo       
import inventory  
import animations 
import akatsuki_event 
import minigames 
import leaderboard 
import chat_rewards
import daily 
import inline_handler

# --- Constants ---
BOT_TOKEN = "7307409890:AAERVuaVSOOOLGv_anuULfQR_MRPRSvLt_U"
START_IMAGE_URL = "https://envs.sh/r6z.jpg" 

# --- Welcome Message Function ---
async def on_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message when the bot is added to a new group."""
    new_members = update.message.new_chat_members
    bot_id = context.bot.id

    for member in new_members:
        if member.id == bot_id:
            chat_id = update.message.chat.id
            logger.info(f"Bot was added to new group: {chat_id}")
            
            # Auto-register the group for events
            db.register_event_chat(chat_id)
            
            welcome_text = (
                "🔥 **A new Shinobi has entered the battle!** 🔥\n\n"
                "Thank you for adding me to your group!\n\n"
                "I am a Naruto RPG bot with missions, battles, world bosses, and more. "
                "Your journey begins now!\n\n"
                "All members type `/register` to create your ninja!"
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
    player = db.get_player(user.id) 
    
    help_button = InlineKeyboardButton("❓ Help & Commands", callback_data="show_main_help")
    summon_button = InlineKeyboardButton("SUMMON ME", url="https://t.me/Naruto_gameXBot?startgroup=true")
    updates_button = InlineKeyboardButton("UPDATES", url="https://t.me/SN_Telegram_bots_Stores")
    
    if player:
        welcome_text = (
            f"🔥 Welcome back, {player.get('rank', 'Ninja')} {player.get('username', 'User')} of {player.get('village', 'Unknown Village')}! 🔥\n\n"
            "The path of the ninja is long and challenging. Continue your training, undertake perilous missions, and prove your strength against rivals!\n\n"
            "<i>What destiny awaits you today?</i>"
        )
        reply_markup = InlineKeyboardMarkup([[help_button], [summon_button, updates_button]])
        try:
            await context.bot.send_photo(update.effective_chat.id, photo=START_IMAGE_URL, caption=welcome_text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to send start photo: {e}")
            await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        if update.effective_chat.type != ChatType.PRIVATE:
            await update.message.reply_text(f"Hey {user.mention_html()}! Please use /register to start your journey in this group.", parse_mode="HTML")
            return
            
        welcome_text = (
            f"Greetings, {user.first_name}! A new legend begins...\n\n"
            "✨ Welcome to the <b>Shinobi Chronicles RPG</b>! ✨\n\n"
            "Step into a world inspired by Naruto, where you'll forge your own ninja path. Here you can:\n"
            "  💪 Train to master powerful techniques\n"
            "  📜 Embark on challenging missions for glory and reward\n"
            "  🌀 Discover secret Jutsu combinations\n"
            "  ⚔️ Test your skills in thrilling PvP battles\n"
            "  🏆 Rise through the ninja ranks, from humble Academy Student to the legendary Kage!\n\n"
            "Your adventure starts now! Choose your home village wisely, as it grants unique bonuses:"
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
    
    # ✅ FIX: Equipment is already a dict from JSONB, no need for json.loads
    player_equipment = player.get('equipment') or {}

    stats = gl.get_total_stats(player)
    eq = player_equipment
    eq_text = "\n".join([f"<b>{s.title()}:</b> {gl.SHOP_INVENTORY[eq[s]]['name'] if eq.get(s) else 'None'}" for s in ['weapon','armor','accessory']])
    
    txt = (
        f"--- 💤 NINJA PROFILE 💤 ---\n"
        f"<b>Name:</b> {player['username']}\n"
        f"<b>Village:</b> {player['village']}\n"
        f"<b>Rank:</b> {player['rank']}\n"
        f"<b>Level:</b> {player['level']}\n"
        f"<b>EXP:</b> {player['exp']} / {gl.get_exp_for_next_level(player['level'])}\n"
        f"<b>Ryo:</b> {player['ryo']} 💰\n\n"
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
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    if db.get_player(user.id):
        await query.edit_message_caption(caption=f"{user.mention_html()}, you are already registered!", parse_mode="HTML")
        return
    
    v_key = query.data.split('_')[1]
    v_name = gl.VILLAGES[v_key]
    
    if db.create_player(user.id, user.username or user.first_name, v_name):
        kb = [[InlineKeyboardButton("❓ Help", callback_data="show_main_help")], [InlineKeyboardButton("UPDATES", url="https://t.me/SN_Telegram_bots_Stores")]]
        await query.edit_message_caption(caption=f"🎉 **Registration Complete!** 🎉\n\n{user.mention_html()} has joined **{v_name}**!\nYour ninja journey begins now. Use /profile.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

def main():
    logger.info("Starting bot...")
    db.create_tables()
    db.update_schema()
    app = Application.builder().token(BOT_TOKEN).build()

    # Core
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("register", register_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("help", help_handler.show_main_help_menu))
    app.add_handler(CommandHandler("inventory", inventory.inventory_command))

    # Minigames
    app.add_handler(CommandHandler(("wallet", "bal", "balance"), minigames.wallet_command))
    app.add_handler(CommandHandler(("steal", "rob"), minigames.steal_command))
    app.add_handler(CommandHandler("scout", minigames.scout_command))
    app.add_handler(CommandHandler("kill", minigames.kill_command))
    app.add_handler(CommandHandler("gift", minigames.gift_command))
    app.add_handler(CommandHandler("protect", minigames.protect_command))
    app.add_handler(CommandHandler("heal", minigames.heal_command))

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

    # Battle
    app.add_handler(CommandHandler("fight", battle.fight_command))
    app.add_handler(CallbackQueryHandler(battle.fight_accept_callback, pattern="^fight_accept_"))
    app.add_handler(CallbackQueryHandler(battle.fight_pick_callback, pattern="^fight_pick_"))
    app.add_handler(CommandHandler("battle", battle.battle_command))
    app.add_handler(CallbackQueryHandler(battle.battle_invite_callback, pattern="^battle_invite_"))
    app.add_handler(CallbackQueryHandler(battle.battle_action_callback, pattern="^battle_action_")) 
    app.add_handler(CallbackQueryHandler(battle.battle_jutsu_callback, pattern="^battle_jutsu_"))   
    app.add_handler(CallbackQueryHandler(battle.battle_item_callback, pattern="^battle_item_"))     

    # World Boss 
    app.add_handler(CommandHandler("enable_world_boss", world_boss.enable_world_boss_command))
    app.add_handler(CommandHandler("boss_status", world_boss.boss_status_command))
    app.add_handler(CallbackQueryHandler(world_boss.boss_action_callback, pattern="^wb_action_")) 
    app.add_handler(CallbackQueryHandler(world_boss.boss_jutsu_callback, pattern="^boss_usejutsu_")) 

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

    # Akatsuki Event
    app.add_handler(CommandHandler(("auto_fight_off", "auto_Ryo_Off"), akatsuki_event.toggle_auto_fight_command))
    app.add_handler(CommandHandler("auto_fight_on", akatsuki_event.toggle_auto_fight_command))
    
    # Inline Handler
    app.add_handler(InlineQueryHandler(inline_handler.inline_query_handler))
    
    # 🆕 Jutsu Game Callback Handler (shortened pattern)
    app.add_handler(CallbackQueryHandler(inline_handler.jutsu_game_callback, pattern="^jg_"))
    
    # Passive Handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_chat_members))
    
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & (~filters.COMMAND) & (~filters.StatusUpdate.NEW_CHAT_MEMBERS), akatsuki_event.passive_group_register), group=-1)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND) & filters.ChatType.GROUPS, chat_rewards.on_chat_message), group=10)

    # Global Callbacks
    app.add_handler(CallbackQueryHandler(village_selection_callback, pattern="^village_"))
    app.add_handler(CallbackQueryHandler(help_handler.show_main_help_menu, pattern="^show_main_help$"))
    app.add_handler(CallbackQueryHandler(help_handler.show_module_help, pattern="^help_module_"))
    app.add_handler(CallbackQueryHandler(help_handler.back_to_main_help_callback, pattern="^back_to_main_help$"))

    # Job Schedule
    if app.job_queue:
        app.job_queue.run_repeating(world_boss.spawn_world_boss, interval=3600, first=10)
        logger.info("World Boss spawn job scheduled (1 hour).")

    logger.info("Bot is polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
