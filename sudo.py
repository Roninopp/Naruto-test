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
    except Exception as e: await update.message.reply_text(f"Error: {e}")

@owner_only
async def db_query_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Usage: `/db_query SELECT ...`", parse_mode="Markdown"); return
    query = " ".join(context.args)
    if not query.strip().upper().startswith("SELECT"): await update.message.reply_text("Only SELECT allowed."); return
    conn = db.get_db_connection()
    if not conn: await update.message.reply_text("DB connection failed."); return
    try:
        with conn.cursor() as c:
            c.execute(query); rows = c.fetchall()
            if not rows: await update.message.reply_text("No results."); return
            text = f"📊 **Results** (Limit 10):\n```\n" + "\n".join([" | ".join(map(str, row)) for row in rows[:10]]) + "\n```"
            await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e: await update.message.reply_text(f"Error: `{e}`", parse_mode="Markdown")
    finally: db.put_db_connection(conn)

@owner_only
async def sudo_give_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: uid = int(context.args[0]); type = context.args[1].lower(); amt = int(context.args[2])
    except: await update.message.reply_text("Usage: `/sudo_give <uid> <ryo|exp> <amt>`", parse_mode="Markdown"); return
    p = db.get_player(uid)
    if not p: await update.message.reply_text("Player not found."); return
    if type == 'ryo':
        if db.update_player(uid, {'ryo': p['ryo'] + amt}): await update.message.reply_text(f"Gave {amt} Ryo to {uid}.")
        else: await update.message.reply_text("Failed.")
    elif type == 'exp':
        p['exp'] += amt; p['total_exp'] += amt; fp, _, _ = gl.check_for_level_up(p)
        if db.update_player(uid, fp): await update.message.reply_text(f"Gave {amt} EXP to {uid}.")
        else: await update.message.reply_text("Failed.")

@owner_only
async def sudo_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: uid = int(context.args[0]); stat = context.args[1].lower(); val = int(context.args[2])
    except: await update.message.reply_text("Usage: `/sudo_set <uid> <stat> <val>`", parse_mode="Markdown"); return
    if db.update_player(uid, {stat: val}): await update.message.reply_text(f"Set {stat} to {val} for {uid}.")
    else: await update.message.reply_text("Failed.")

@owner_only
async def list_boss_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chats = db.get_all_boss_chats()
    await update.message.reply_text(f"Boss Chats:\n`{chats}`", parse_mode="Markdown")

@owner_only
async def sudo_leave_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await context.bot.leave_chat(int(context.args[0])); await update.message.reply_text("Left.")
    except: await update.message.reply_text("Failed to leave.")

@owner_only
async def get_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: uid = int(context.args[0])
    except: await update.message.reply_text("Usage: `/get_user <uid>`", parse_mode="Markdown"); return
    p = db.get_player(uid)
    if not p: await update.message.reply_text("Not found."); return
    text = f"```json\n{json.dumps(p, indent=2, cls=DateTimeEncoder)}\n```"
    if len(text) > 4096: text = text[:4090] + "```"
    await update.message.reply_text(text, parse_mode="Markdown")

@owner_only
async def bot_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db.get_db_connection()
    if not conn: await update.message.reply_text("DB failed."); return
    try:
        with conn.cursor() as c: c.execute("SELECT COUNT(*) FROM players"); count = c.fetchone()[0]
        await update.message.reply_text(f"📊 Users: {count}\n👹 Boss Chats: {len(db.get_all_boss_chats())}")
    finally: db.put_db_connection(conn)

@owner_only
async def clearcache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forces a cache clear for a specific user ID."""
    if not context.args: await update.message.reply_text("Usage: `/clearcache <user_id>`", parse_mode="Markdown"); return
    try:
        uid = int(context.args[0])
        db.cache.clear_player_cache(uid)
        await update.message.reply_text(f"✅ Cache cleared for {uid}.")
    except: await update.message.reply_text("Invalid ID.")

# --- NEW: MASTER FLUSH COMMAND ---
@owner_only
async def flushcache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wipes the ENTIRE Redis cache."""
    if db.cache.flush_all_cache():
        await update.message.reply_text("🌪️ **CACHE FLUSHED!** 🌪️\nAll temporary data has been wiped. Everyone will reload from the database on their next action.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Failed to flush cache. Check logs.")
# --- END NEW ---
