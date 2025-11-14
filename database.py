import logging
import psycopg2
import psycopg2.pool
import json
import datetime
from datetime import timezone
import game_logic as gl
import cache

logger = logging.getLogger(__name__)

# --- IMPORTANT ---
DATABASE_URL = "postgresql://neondb_owner:npg_ZBiVmpx5rCR6@ep-fragrant-feather-a4eur7c4-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"
# --- END ---

try:
    pool = psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DATABASE_URL)
    logger.info("Database connection pool created successfully.")
except Exception as e:
    logger.critical(f"FATAL: Could not create database connection pool: {e}")
    pool = None

def get_db_connection():
    if pool is None:
        logger.error("Database pool is not initialized.")
        return None
    try:
        return pool.getconn()
    except Exception as e:
        logger.error(f"Error getting connection from pool: {e}")
        return None

def put_db_connection(conn):
    if pool and conn:
        pool.putconn(conn)

def dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}

# --- 1. TABLE CREATION ---
def create_tables():
    conn = get_db_connection()
    if conn is None: return
    commands = (
        """
        CREATE TABLE IF NOT EXISTS players (
            user_id BIGINT PRIMARY KEY, username TEXT NOT NULL, village TEXT NOT NULL,
            level INTEGER DEFAULT 1, exp INTEGER DEFAULT 0, total_exp INTEGER DEFAULT 0,
            max_hp INTEGER DEFAULT 100, current_hp INTEGER DEFAULT 100,
            max_chakra INTEGER DEFAULT 100, current_chakra INTEGER DEFAULT 100,
            strength INTEGER DEFAULT 10, speed INTEGER DEFAULT 10, intelligence INTEGER DEFAULT 10, stamina INTEGER DEFAULT 10,
            known_jutsus JSONB DEFAULT '[]'::jsonb, discovered_combinations JSONB DEFAULT '[]'::jsonb,
            ryo INTEGER DEFAULT 100, rank TEXT DEFAULT 'Academy Student',
            wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, battle_cooldown TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            equipment JSONB DEFAULT '{}'::jsonb, inventory JSONB DEFAULT '[]'::jsonb,
            daily_train_count INTEGER DEFAULT 0, last_train_reset_date DATE DEFAULT NULL,
            boss_attack_cooldown TIMESTAMP, story_progress INTEGER DEFAULT 0,
            akatsuki_cooldown JSONB DEFAULT NULL, steal_cooldown TIMESTAMP DEFAULT NULL,
            scout_cooldown TIMESTAMP DEFAULT NULL, assassinate_cooldown TIMESTAMP DEFAULT NULL,
            daily_mission_count INTEGER DEFAULT 0, last_mission_reset_date DATE DEFAULT NULL,
            last_daily_claim DATE DEFAULT NULL, protection_until TIMESTAMP DEFAULT NULL,
            hospitalized_until TIMESTAMP DEFAULT NULL, hospitalized_by BIGINT DEFAULT NULL, kills INTEGER DEFAULT 0,
            last_inline_game_date DATE DEFAULT NULL,
            inline_pack_cooldown TIMESTAMP DEFAULT NULL
        );
        """,
        """CREATE TABLE IF NOT EXISTS jutsu_discoveries (id SERIAL PRIMARY KEY, combination TEXT UNIQUE, jutsu_name TEXT, discovered_by TEXT, discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""",
        """CREATE TABLE IF NOT EXISTS battle_history (id SERIAL PRIMARY KEY, player1_id BIGINT, player2_id BIGINT, winner_id BIGINT, battle_log TEXT, duration_seconds INTEGER, fought_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""",
        """CREATE TABLE IF NOT EXISTS world_boss_enabled_chats (chat_id BIGINT PRIMARY KEY, enabled_by_user_id BIGINT, enabled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""",
        """CREATE TABLE IF NOT EXISTS world_boss_status (chat_id BIGINT PRIMARY KEY, is_active INTEGER DEFAULT 0, boss_key TEXT, current_hp INTEGER, max_hp INTEGER, ryo_pool INTEGER, spawn_time TIMESTAMP);""",
        """CREATE TABLE IF NOT EXISTS world_boss_damage (id SERIAL PRIMARY KEY, chat_id BIGINT NOT NULL, user_id BIGINT NOT NULL, username TEXT NOT NULL, total_damage INTEGER DEFAULT 0, UNIQUE(chat_id, user_id));""",
        """CREATE TABLE IF NOT EXISTS group_event_settings (chat_id BIGINT PRIMARY KEY, events_enabled INTEGER DEFAULT 1);""",
        """CREATE TABLE IF NOT EXISTS active_akatsuki_fights (message_id BIGINT PRIMARY KEY, chat_id BIGINT NOT NULL, enemy_name TEXT NOT NULL, enemy_hp INTEGER NOT NULL, player_1_id BIGINT DEFAULT NULL, player_2_id BIGINT DEFAULT NULL, player_3_id BIGINT DEFAULT NULL, turn_player_id TEXT DEFAULT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""",
        """CREATE TABLE IF NOT EXISTS chat_activity (user_id BIGINT NOT NULL, chat_id BIGINT NOT NULL, message_count INTEGER DEFAULT 0, last_reward_milestone INTEGER DEFAULT 0, last_active_date DATE DEFAULT CURRENT_DATE, PRIMARY KEY (user_id, chat_id));"""
    )
    try:
        with conn.cursor() as c: 
            for cmd in commands:
                c.execute(cmd)
        conn.commit()
        logger.info("Database tables checked/created successfully.")
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        conn.rollback()
    finally:
        put_db_connection(conn)

# --- 2. SCHEMA UPDATER ---
def update_schema():
    conn = get_db_connection()
    if conn is None: return
    cols = {
        'players': [
            ('equipment', "JSONB DEFAULT '{}'::jsonb"), ('inventory', "JSONB DEFAULT '[]'::jsonb"),
            ('daily_train_count', 'INTEGER DEFAULT 0'), ('last_train_reset_date', 'DATE DEFAULT NULL'),
            ('boss_attack_cooldown', 'TIMESTAMP DEFAULT NULL'), ('story_progress', 'INTEGER DEFAULT 0'),
            ('akatsuki_cooldown', 'JSONB DEFAULT NULL'), ('steal_cooldown', 'TIMESTAMP DEFAULT NULL'),
            ('scout_cooldown', 'TIMESTAMP DEFAULT NULL'), ('assassinate_cooldown', 'TIMESTAMP DEFAULT NULL'),
            ('daily_mission_count', 'INTEGER DEFAULT 0'), ('last_mission_reset_date', 'DATE DEFAULT NULL'),
            ('last_daily_claim', 'DATE DEFAULT NULL'), ('protection_until', 'TIMESTAMP DEFAULT NULL'),
            ('hospitalized_until', 'TIMESTAMP DEFAULT NULL'), ('hospitalized_by', 'BIGINT DEFAULT NULL'), ('kills', 'INTEGER DEFAULT 0'),
            ('last_inline_game_date', 'DATE DEFAULT NULL'),
            ('inline_pack_cooldown', 'TIMESTAMP DEFAULT NULL')
        ]
    }
    try:
        with conn.cursor() as c:
            for t, clist in cols.items():
                for col, dtype in clist:
                    try:
                        c.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS {col} {dtype};")
                    except psycopg2.errors.DuplicateColumn:
                        conn.rollback()
                    except Exception:
                        conn.rollback()
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        put_db_connection(conn)

# --- 3. PLAYER FUNCTIONS ---
def get_player(user_id):
    cp = cache.get_player_cache(user_id)
    if cp:
        for k in ['battle_cooldown','boss_attack_cooldown','steal_cooldown','scout_cooldown','assassinate_cooldown','protection_until','hospitalized_until','created_at', 'inline_pack_cooldown']:
            if cp.get(k): 
                try:
                    cp[k] = datetime.datetime.fromisoformat(cp[k])
                except:
                    pass
        for k in ['last_train_reset_date','last_mission_reset_date','last_daily_claim', 'last_inline_game_date']:
             if cp.get(k):
                 try:
                     cp[k] = datetime.date.fromisoformat(cp[k])
                 except:
                     pass
        return cp
    conn = get_db_connection()
    if not conn: return None
    try: 
        with conn.cursor() as c:
            c.execute("SELECT * FROM players WHERE user_id = %s", (user_id,))
            r = c.fetchone()
            if r:
                p = dict_factory(c, r)
                cache.set_player_cache(user_id, p)
                return p
        return None
    except Exception as e:
        logger.error(f"DB Error in get_player({user_id}): {e}")
        return None
    finally:
        put_db_connection(conn)

def create_player(user_id, username, village):
    conn = get_db_connection()
    if not conn: return False
    s = gl.distribute_stats({'strength':10,'speed':10,'intelligence':10,'stamina':10}, 0)
    sql = """INSERT INTO players (user_id, username, village, max_hp, current_hp, max_chakra, current_chakra, strength, speed, intelligence, stamina, equipment, inventory, daily_train_count, last_train_reset_date, boss_attack_cooldown, story_progress, akatsuki_cooldown, known_jutsus, discovered_combinations, steal_cooldown, scout_cooldown, assassinate_cooldown, daily_mission_count, last_mission_reset_date, last_daily_claim, protection_until, hospitalized_until, hospitalized_by, kills, last_inline_game_date, inline_pack_cooldown) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    try:
        with conn.cursor() as c:
            c.execute(sql, (user_id, username, village, s['max_hp'], s['max_hp'], s['max_chakra'], s['max_chakra'], s['strength'], s['speed'], s['intelligence'], s['stamina'], '{}', '[]', 0, None, None, 0, None, '[]', '[]', None, None, None, 0, None, None, None, None, None, 0, None, None))
        conn.commit()
        logger.info(f"New player created: {username} (ID: {user_id})")
        cache.clear_player_cache(user_id)
        return True
    except Exception as e:
        logger.error(f"Create player error: {e}")
        conn.rollback()
        return False
    finally:
        put_db_connection(conn)

def update_player(user_id, updates):
    conn = get_db_connection()
    if not conn: return False
    set_c = []; vals = []
    for k, v in updates.items():
        set_c.append(f"{k} = %s")
        if isinstance(v, (dict, list)):
            vals.append(json.dumps(v))
        else:
            vals.append(v)
    vals.append(user_id)
    try:
        with conn.cursor() as c:
            c.execute(f"UPDATE players SET {', '.join(set_c)} WHERE user_id = %s", tuple(vals))
        conn.commit()
        cache.clear_player_cache(user_id)
        return True
    except Exception as e:
        logger.error(f"Update player error: {e}")
        conn.rollback()
        return False
    finally:
        put_db_connection(conn)

# ✅ NEW: ATOMIC RYO OPERATIONS (Prevents race conditions)
def atomic_add_ryo(user_id, amount):
    """Atomically adds (or subtracts if negative) Ryo to a player's balance."""
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as c:
            c.execute("UPDATE players SET ryo = ryo + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()
        cache.clear_player_cache(user_id)
        return True
    except Exception as e:
        logger.error(f"Atomic ryo update error for {user_id}: {e}")
        conn.rollback()
        return False
    finally:
        put_db_connection(conn)

def atomic_add_exp(user_id, amount):
    """Atomically adds EXP and total_exp to a player."""
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as c:
            c.execute("UPDATE players SET exp = exp + %s, total_exp = total_exp + %s WHERE user_id = %s", (amount, amount, user_id))
        conn.commit()
        cache.clear_player_cache(user_id)
        return True
    except Exception as e:
        logger.error(f"Atomic exp update error for {user_id}: {e}")
        conn.rollback()
        return False
    finally:
        put_db_connection(conn)

# --- 4. BOSS & EVENT FUNCTIONS ---
def enable_boss_chat(cid, uid):
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO world_boss_enabled_chats (chat_id, enabled_by_user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (cid, uid))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        put_db_connection(conn)

def get_all_boss_chats():
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor() as c:
            c.execute("SELECT chat_id FROM world_boss_enabled_chats")
            return [r[0] for r in c.fetchall()]
    except Exception:
        return []
    finally:
        put_db_connection(conn)

def get_boss_status(cid):
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor() as c:
            c.execute("SELECT * FROM world_boss_status WHERE chat_id = %s", (cid,))
            row = c.fetchone()
            if row: return dict_factory(c, row)
            c.execute("INSERT INTO world_boss_status (chat_id, is_active) VALUES (%s, 0) ON CONFLICT DO NOTHING", (cid,))
        conn.commit()
        return {'chat_id': cid, 'is_active': 0, 'boss_key': None, 'current_hp': 0, 'max_hp': 0, 'ryo_pool': 0, 'spawn_time': None}
    except Exception:
        return None
    finally:
        put_db_connection(conn)

def register_event_chat(cid):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO group_event_settings (chat_id, events_enabled) VALUES (%s, 1) ON CONFLICT DO NOTHING", (cid,))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        put_db_connection(conn)

def get_event_settings_dict():
    conn = get_db_connection()
    if not conn: return {}
    try:
        with conn.cursor() as c:
            c.execute("SELECT chat_id, events_enabled FROM group_event_settings")
            return {r[0]: r[1] for r in c.fetchall()}
    except Exception:
        return {}
    finally:
        put_db_connection(conn)

def toggle_auto_events(cid, status):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO group_event_settings (chat_id, events_enabled) VALUES (%s, %s) ON CONFLICT (chat_id) DO UPDATE SET events_enabled = %s", (cid, status, status))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        put_db_connection(conn)

def create_akatsuki_fight(mid, cid, name):
    conn = get_db_connection()
    if not conn: return
    info = gl.AKATSUKI_ENEMIES.get(name)
    if not info: return
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO active_akatsuki_fights (message_id, chat_id, enemy_name, enemy_hp) VALUES (%s, %s, %s, %s)", (mid, cid, name, info['max_hp']))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        put_db_connection(conn)

def get_akatsuki_fight(cid, mid=None):
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor() as c:
            if mid:
                c.execute("SELECT * FROM active_akatsuki_fights WHERE message_id = %s", (mid,))
            else:
                c.execute("SELECT * FROM active_akatsuki_fights WHERE chat_id = %s", (cid,))
            row = c.fetchone()
            return dict_factory(c, row) if row else None
    except Exception:
        return None
    finally:
        put_db_connection(conn)

def add_player_to_fight(mid, cid, uid):
    conn = get_db_connection()
    if not conn: return {'status': 'failed'}
    try:
        with conn.cursor() as c:
            c.execute("SELECT * FROM active_akatsuki_fights WHERE message_id = %s AND chat_id = %s", (mid, cid))
            row = c.fetchone()
            if not row: return {'status': 'failed'}
            f = dict_factory(c, row)
            if uid in [f['player_1_id'], f['player_2_id'], f['player_3_id']]: return {'status': 'already_joined'}
            slot = 'player_1_id' if f['player_1_id'] is None else 'player_2_id' if f['player_2_id'] is None else 'player_3_id' if f['player_3_id'] is None else None
            if not slot: return {'status': 'full'}
            c.execute(f"UPDATE active_akatsuki_fights SET {slot} = %s WHERE message_id = %s", (uid, mid))
        conn.commit()
        return {'status': 'ready'} if slot == 'player_3_id' else {'status': 'joined'}
    except Exception:
        conn.rollback()
        return {'status': 'failed'}
    finally:
        put_db_connection(conn)

def set_akatsuki_turn(mid, turn_id):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as c:
            c.execute("UPDATE active_akatsuki_fights SET turn_player_id = %s WHERE message_id = %s", (str(turn_id), mid))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        put_db_connection(conn)

def update_akatsuki_fight_hp(mid, hp):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as c:
            c.execute("UPDATE active_akatsuki_fights SET enemy_hp = %s WHERE message_id = %s", (hp, mid))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        put_db_connection(conn)

def add_player_damage_to_fight(mid, uid, dmg):
    pass

def clear_akatsuki_fight(cid):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as c:
            c.execute("DELETE FROM active_akatsuki_fights WHERE chat_id = %s", (cid,))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        put_db_connection(conn)

def remove_player_from_fight(mid, uid):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as c:
            c.execute("UPDATE active_akatsuki_fights SET player_1_id = NULL WHERE message_id = %s AND player_1_id = %s", (mid, uid))
            c.execute("UPDATE active_akatsuki_fights SET player_2_id = NULL WHERE message_id = %s AND player_2_id = %s", (mid, uid))
            c.execute("UPDATE active_akatsuki_fights SET player_3_id = NULL WHERE message_id = %s AND player_3_id = %s", (mid, uid))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        put_db_connection(conn)

# --- 5. LEADERBOARD FUNCTIONS ---
def get_top_players_by_ryo(limit=10):
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor() as c:
            c.execute("SELECT user_id, username, ryo FROM players ORDER BY ryo DESC LIMIT %s", (limit,))
            return [dict(zip([col[0] for col in c.description], r)) for r in c.fetchall()]
    except Exception:
        return []
    finally:
        put_db_connection(conn)

def get_top_players_by_exp(limit=10):
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor() as c:
            c.execute("SELECT user_id, username, level, total_exp FROM players ORDER BY total_exp DESC LIMIT %s", (limit,))
            return [dict(zip([col[0] for col in c.description], r)) for r in c.fetchall()]
    except Exception:
        return []
    finally:
        put_db_connection(conn)

def get_top_players_by_wins(limit=10):
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor() as c:
            c.execute("SELECT user_id, username, wins FROM players WHERE wins > 0 ORDER BY wins DESC LIMIT %s", (limit,))
            return [dict(zip([col[0] for col in c.description], r)) for r in c.fetchall()]
    except Exception:
        return []
    finally:
        put_db_connection(conn)

def get_top_players_by_kills(limit=10):
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor() as c:
            c.execute("SELECT user_id, username, kills FROM players WHERE kills > 0 ORDER BY kills DESC LIMIT %s", (limit,))
            return [dict(zip([col[0] for col in c.description], r)) for r in c.fetchall()]
    except Exception:
        return []
    finally:
        put_db_connection(conn)

# --- 6. CHAT REWARD FUNCTIONS ---
def get_chat_activity(uid, cid):
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor() as c:
            c.execute("SELECT * FROM chat_activity WHERE user_id = %s AND chat_id = %s", (uid, cid))
            r = c.fetchone()
            return dict_factory(c, r) if r else None
    except Exception:
        return None
    finally:
        put_db_connection(conn)

def create_chat_activity(uid, cid, today):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO chat_activity (user_id, chat_id, message_count, last_reward_milestone, last_active_date) VALUES (%s, %s, 1, 0, %s) ON CONFLICT DO NOTHING", (uid, cid, today))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        put_db_connection(conn)

def reset_chat_activity(uid, cid, today):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as c:
            c.execute("UPDATE chat_activity SET message_count = 1, last_reward_milestone = 0, last_active_date = %s WHERE user_id = %s AND chat_id = %s", (today, uid, cid))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        put_db_connection(conn)

def increment_chat_activity(uid, cid):
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor() as c:
            c.execute("UPDATE chat_activity SET message_count = message_count + 1 WHERE user_id = %s AND chat_id = %s RETURNING message_count", (uid, cid))
            return c.fetchone()[0]
    except Exception:
        conn.rollback()
        return None
    finally:
        put_db_connection(conn)

def update_chat_milestone(uid, cid, milestone):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as c:
            c.execute("UPDATE chat_activity SET last_reward_milestone = %s WHERE user_id = %s AND chat_id = %s", (milestone, uid, cid))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        put_db_connection(conn)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Initializing database...")
    create_tables()
    update_schema()
