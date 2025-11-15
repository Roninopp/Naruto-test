import logging
import psycopg2
import json
import psutil
import os
import functools
import datetime

from telegram import Update
from telegram.ext import ContextTypes

import database as db
import game_logic as gl

logger = logging.getLogger(__name__)

# --- !!! YOUR OWNER ID !!! ---
OWNER_ID = 6837532865
# -----------------------------

# --- Custom JSON converter for /get_user ---
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        return super().default(obj)

# --- Decorator for Owner Check ---
def owner_only(func):
    @functools.wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if user.id != OWNER_ID:
            logger.warning(f"Unauthorized sudo attempt by {user.id} for /{func.__name__}")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- Sudo Commands ---

@owner_only
async def server_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        text = (f"🖥️ **Server Status**\nCPU: {cpu}%\nRAM: {mem.percent}%\nDisk: {disk.percent}%")
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e: 
        await update.message.reply_text(f"Error: {e}")

@owner_only
async def db_query_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: 
        await update.message.reply_text("Usage: `/db_query SELECT ...`", parse_mode="Markdown")
        return
    
    query = " ".join(context.args)
    if not query.strip().upper().startswith("SELECT"): 
        await update.message.reply_text("Only SELECT allowed.")
        return
    
    conn = db.get_db_connection()
    if not conn: 
        await update.message.reply_text("DB connection failed.")
        return
    
    try:
        with conn.cursor() as c:
            c.execute(query)
            rows = c.fetchall()
            if not rows: 
                await update.message.reply_text("No results.")
                return
            text = f"📊 **Results** (Limit 10):\n```\n" + "\n".join([" | ".join(map(str, row)) for row in rows[:10]]) + "\n```"
            await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e: 
        await update.message.reply_text(f"Error: `{e}`", parse_mode="Markdown")
    finally: 
        db.put_db_connection(conn)

@owner_only
async def sudo_give_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: 
        uid = int(context.args[0])
        type = context.args[1].lower()
        amt = int(context.args[2])
    except: 
        await update.message.reply_text("Usage: `/sudo_give <uid> <ryo|exp> <amt>`", parse_mode="Markdown")
        return
    
    p = db.get_player(uid)
    if not p: 
        await update.message.reply_text("Player not found.")
        return
    
    if type == 'ryo':
        if db.update_player(uid, {'ryo': p['ryo'] + amt}): 
            await update.message.reply_text(f"Gave {amt} Ryo to {uid}.")
        else: 
            await update.message.reply_text("Failed.")
    elif type == 'exp':
        p['exp'] += amt
        p['total_exp'] += amt
        fp, _, _ = gl.check_for_level_up(p)
        if db.update_player(uid, fp): 
            await update.message.reply_text(f"Gave {amt} EXP to {uid}.")
        else: 
            await update.message.reply_text("Failed.")

@owner_only
async def sudo_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: 
        uid = int(context.args[0])
        stat = context.args[1].lower()
        val = int(context.args[2])
    except: 
        await update.message.reply_text("Usage: `/sudo_set <uid> <stat> <val>`", parse_mode="Markdown")
        return
    
    if db.update_player(uid, {stat: val}): 
        await update.message.reply_text(f"Set {stat} to {val} for {uid}.")
    else: 
        await update.message.reply_text("Failed.")

@owner_only
async def list_boss_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chats = db.get_all_boss_chats()
    await update.message.reply_text(f"Boss Chats:\n`{chats}`", parse_mode="Markdown")

@owner_only
async def sudo_leave_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: 
        await context.bot.leave_chat(int(context.args[0]))
        await update.message.reply_text("Left.")
    except: 
        await update.message.reply_text("Failed to leave.")

@owner_only
async def get_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: 
        uid = int(context.args[0])
    except: 
        await update.message.reply_text("Usage: `/get_user <uid>`", parse_mode="Markdown")
        return
    
    p = db.get_player(uid)
    if not p: 
        await update.message.reply_text("Not found.")
        return
    
    text = f"```json\n{json.dumps(p, indent=2, cls=DateTimeEncoder)}\n```"
    if len(text) > 4096: 
        text = text[:4090] + "```"
    await update.message.reply_text(text, parse_mode="Markdown")

# 🆕 UPGRADED BOT STATS
@owner_only
async def bot_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows comprehensive bot statistics."""
    conn = db.get_db_connection()
    if not conn:
        await update.message.reply_text("DB connection failed.")
        return
    
    try:
        with conn.cursor() as c:
            # 1. Total Users
            c.execute("SELECT COUNT(*) FROM players")
            total_users = c.fetchone()[0]
            
            # 2. Active Users (last 7 days)
            seven_days_ago = datetime.datetime.now() - datetime.timedelta(days=7)
            c.execute("SELECT COUNT(*) FROM players WHERE created_at >= %s", (seven_days_ago,))
            new_users_week = c.fetchone()[0]
            
            # 3. Total Groups (from world boss enabled chats)
            c.execute("SELECT COUNT(*) FROM world_boss_enabled_chats")
            boss_enabled_groups = c.fetchone()[0]
            
            # 4. Total Groups (from event settings)
            c.execute("SELECT COUNT(*) FROM group_event_settings")
            event_enabled_groups = c.fetchone()[0]
            
            # Total unique groups (combine both tables)
            c.execute("""
                SELECT COUNT(DISTINCT chat_id) FROM (
                    SELECT chat_id FROM world_boss_enabled_chats
                    UNION
                    SELECT chat_id FROM group_event_settings
                ) AS combined_groups
            """)
            total_groups = c.fetchone()[0]
            
            # 5. Total Ryo in circulation
            c.execute("SELECT SUM(ryo) FROM players")
            total_ryo = c.fetchone()[0] or 0
            
            # 6. Highest Level Player
            c.execute("SELECT username, level FROM players ORDER BY level DESC LIMIT 1")
            top_player = c.fetchone()
            top_player_name = top_player[0] if top_player else "None"
            top_player_level = top_player[1] if top_player else 0
            
            # 7. Richest Player
            c.execute("SELECT username, ryo FROM players ORDER BY ryo DESC LIMIT 1")
            richest = c.fetchone()
            richest_name = richest[0] if richest else "None"
            richest_ryo = richest[1] if richest else 0
            
            # 8. Total Battles
            c.execute("SELECT SUM(wins + losses) FROM players")
            total_battles = c.fetchone()[0] or 0
            
            # 9. Total Kills
            c.execute("SELECT SUM(kills) FROM players")
            total_kills = c.fetchone()[0] or 0
            
            # 10. Players in Hospital
            now = datetime.datetime.now(datetime.timezone.utc)
            c.execute("SELECT COUNT(*) FROM players WHERE hospitalized_until > %s", (now,))
            hospitalized = c.fetchone()[0]
            
            # 11. Active World Bosses
            c.execute("SELECT COUNT(*) FROM world_boss_status WHERE is_active = 1")
            active_bosses = c.fetchone()[0]
            
            # 12. Total Chat Activity Messages (today)
            today = datetime.date.today()
            c.execute("SELECT SUM(message_count) FROM chat_activity WHERE last_active_date = %s", (today,))
            messages_today = c.fetchone()[0] or 0
            
            # 13. Average Player Level
            c.execute("SELECT AVG(level) FROM players")
            avg_level = c.fetchone()[0] or 0
            
            # 14. Server Stats
            try:
                cpu = psutil.cpu_percent(interval=0.5)
                mem = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                server_stats_text = (
                    f"CPU: {cpu}%\n"
                    f"RAM: {mem.percent}%\n"
                    f"Disk: {disk.percent}%"
                )
            except:
                server_stats_text = "Unavailable"
        
        # Build the epic stats message
        stats_text = (
            f"📊 **NARUTO RPG BOT STATISTICS** 📊\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            
            f"👥 **PLAYER STATS:**\n"
            f"  • Total Players: **{total_users:,}**\n"
            f"  • New (Last 7 Days): **{new_users_week:,}**\n"
            f"  • Average Level: **{avg_level:.1f}**\n"
            f"  • In Hospital: **{hospitalized}** 🏥\n\n"
            
            f"🏆 **TOP PLAYERS:**\n"
            f"  • Highest Level: **{top_player_name}** (Lvl {top_player_level})\n"
            f"  • Richest: **{richest_name}** ({richest_ryo:,} Ryo 💰)\n\n"
            
            f"🏘️ **GROUPS:**\n"
            f"  • Total Groups: **{total_groups:,}** 🎯\n"
            f"  • Boss Enabled: **{boss_enabled_groups:,}**\n"
            f"  • Events Enabled: **{event_enabled_groups:,}**\n\n"
            
            f"⚔️ **BATTLE STATS:**\n"
            f"  • Total Battles: **{total_battles:,}**\n"
            f"  • Total Assassinations: **{total_kills:,}** ☠️\n"
            f"  • Active Bosses: **{active_bosses}** 💹\n\n"
            
            f"💰 **ECONOMY:**\n"
            f"  • Total Ryo Circulation: **{total_ryo:,}**\n"
            f"  • Messages Today: **{messages_today:,}** 💬\n\n"
            
            f"🖥️ **SERVER STATUS:**\n"
            f"  {server_stats_text}\n\n"
            
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 Bot is running smoothly! 🔥"
        )
        
        await update.message.reply_text(stats_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error in bot_stats: {e}", exc_info=True)
        await update.message.reply_text(f"Error fetching stats: {e}")
    finally:
        db.put_db_connection(conn)

@owner_only
async def clearcache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forces a cache clear for a specific user ID."""
    if not context.args: 
        await update.message.reply_text("Usage: `/clearcache <user_id>`", parse_mode="Markdown")
        return
    try:
        uid = int(context.args[0])
        db.cache.clear_player_cache(uid)
        await update.message.reply_text(f"✅ Cache cleared for {uid}.")
    except: 
        await update.message.reply_text("Invalid ID.")

@owner_only
async def flushcache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wipes the ENTIRE Redis cache."""
    if db.cache.flush_all_cache():
        await update.message.reply_text("🌪️ **CACHE FLUSHED!** 🌪️\nAll temporary data wiped. Everyone will reload from DB.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Failed to flush cache. Check logs.")
