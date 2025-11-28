"""
🔥 DATABASE.PY - ULTIMATE FIX FOR NEON.TECH + SPAWN SYSTEM
✅ Auto-reconnects on SSL/connection errors
✅ Thread-safe connection handling
✅ Graceful error recovery
✅ FIXED: Pool exhaustion after 24-30 hours
✅ UPDATED: League Battle System fields added
✅ UPDATED: Spawn System (Character Collection) added
"""

import logging
import psycopg2
from psycopg2 import pool, OperationalError, InterfaceError
import json
import datetime
from datetime import timezone
import threading
import game_logic as gl
import cache

logger = logging.getLogger(__name__)

# --- DATABASE CONFIG ---
DATABASE_URL = "postgresql://neondb_owner:npg_ZBiVmpx5rCR6@ep-fragrant-feather-a4eur7c4-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

# Thread lock for pool operations
pool_lock = threading.Lock()
connection_pool = None

def init_pool():
    """Initialize connection pool with retry logic"""
    global connection_pool
    
    try:
        connection_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=5,        # Increased from 2
            maxconn=50,       # Increased from 20 - CRITICAL FIX
            dsn=DATABASE_URL,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
            connect_timeout=10
        )
        logger.info("✅ Database connection pool created successfully.")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to create connection pool: {e}")
        connection_pool = None
        return False

# Initialize pool on import
init_pool()

def get_db_connection(retry_count=3):
    """
    Get connection with automatic retry and pool recreation.
    FIXED: Handles pool exhaustion properly
    """
    global connection_pool
    
    for attempt in range(retry_count):
        try:
            # Check if pool exists
            if connection_pool is None:
                logger.warning("Pool is None, reinitializing...")
                with pool_lock:
                    if connection_pool is None:  # Double-check
                        if not init_pool():
                            return None
            
            # Get connection from pool
            try:
                conn = connection_pool.getconn()
            except Exception as e:
                logger.error(f"Error getting connection (attempt {attempt + 1}): {e}")
                # CRITICAL FIX: If getconn fails, pool might be exhausted
                if "exhausted" in str(e).lower():
                    logger.error("Pool exhausted! Recreating pool...")
                    with pool_lock:
                        try:
                            if connection_pool:
                                connection_pool.closeall()
                        except:
                            pass
                        connection_pool = None
                        init_pool()
                continue
            
            if conn is None:
                logger.warning(f"Got None connection (attempt {attempt + 1})")
                continue
            
            # Test connection
            try:
                with conn.cursor() as test_cur:
                    test_cur.execute("SELECT 1")
                return conn  # Connection is good!
                
            except (OperationalError, InterfaceError) as e:
                logger.warning(f"Connection test failed: {e}")
                # Close bad connection
                try:
                    connection_pool.putconn(conn, close=True)
                except:
                    try:
                        conn.close()  # Force close if putconn fails
                    except:
                        pass
                
                # Reinit pool on last attempt
                if attempt == retry_count - 1:
                    logger.error("All retries failed, recreating pool...")
                    with pool_lock:
                        try:
                            if connection_pool:
                                connection_pool.closeall()
                        except:
                            pass
                        connection_pool = None
                        init_pool()
                
                continue
                
        except Exception as e:
            logger.error(f"Unexpected error in get_db_connection (attempt {attempt + 1}): {e}")
            if attempt < retry_count - 1:
                continue
    
    logger.error("Failed to get valid connection after all retries")
    return None

def put_db_connection(conn):
    """Safely return connection to pool - FIXED VERSION"""
    if not conn or not connection_pool:
        return
    
    try:
        if conn.closed:
            connection_pool.putconn(conn, close=True)
        else:
            connection_pool.putconn(conn)
    except Exception as e:
        logger.error(f"Error returning connection: {e}")
        # CRITICAL FIX: Force close if return fails
        try:
            if conn and not conn.closed:
                conn.close()
        except:
            pass

def execute_with_retry(operation, *args, max_retries=3, **kwargs):
    """
    Execute database operation with automatic retry on connection errors.
    FIXED: Always returns connections to pool, prevents exhaustion
    """
    conn = None  # Track connection
    
    for attempt in range(max_retries):
        try:
            conn = get_db_connection()
            if not conn:
                logger.error(f"Could not get connection (attempt {attempt + 1})")
                continue
            
            # Execute operation
            result = operation(conn, *args, **kwargs)
            
            # CRITICAL FIX: Always return connection on success
            put_db_connection(conn)
            conn = None  # Mark as returned
            return result
            
        except (OperationalError, InterfaceError) as e:
            logger.warning(f"Connection error in operation (attempt {attempt + 1}): {e}")
            # CRITICAL FIX: Always try to return connection
            if conn:
                try:
                    put_db_connection(conn)
                except:
                    try:
                        conn.close()
                    except:
                        pass
                conn = None
            
            if attempt < max_retries - 1:
                continue
            else:
                logger.error(f"Operation failed after {max_retries} attempts")
                return None
                
        except Exception as e:
            logger.error(f"Unexpected error in operation: {e}")
            # CRITICAL FIX: Always cleanup connection
            if conn:
                try:
                    if not conn.closed:
                        conn.rollback()
                    put_db_connection(conn)
                except:
                    try:
                        conn.close()
                    except:
                        pass
                conn = None
            return None
        
        finally:
            # CRITICAL FIX: Safety net - ensure connection is ALWAYS returned
            if conn:
                try:
                    put_db_connection(conn)
                except:
                    try:
                        conn.close()
                    except:
                        pass
    
    return None

def dict_factory(cursor, row):
    """Convert row to dictionary"""
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}

# --- TABLE CREATION ---
def create_tables():
    """Create database tables"""
    def _create_tables(conn):
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
                character_collection JSONB DEFAULT '{}'::jsonb,
                daily_train_count INTEGER DEFAULT 0, last_train_reset_date DATE DEFAULT NULL,
                story_progress INTEGER DEFAULT 0,
                steal_cooldown TIMESTAMP DEFAULT NULL,
                scout_cooldown TIMESTAMP DEFAULT NULL, assassinate_cooldown TIMESTAMP DEFAULT NULL,
                daily_mission_count INTEGER DEFAULT 0, last_mission_reset_date DATE DEFAULT NULL,
                last_daily_claim DATE DEFAULT NULL, protection_until TIMESTAMP DEFAULT NULL,
                hospitalized_until TIMESTAMP DEFAULT NULL, hospitalized_by BIGINT DEFAULT NULL, kills INTEGER DEFAULT 0,
                last_inline_game_date DATE DEFAULT NULL,
                inline_pack_cooldown TIMESTAMP DEFAULT NULL,
                heat_level INTEGER DEFAULT 0,
                bounty INTEGER DEFAULT 0,
                reputation_points INTEGER DEFAULT 0,
                reputation_title TEXT DEFAULT NULL,
                total_steals INTEGER DEFAULT 0,
                total_steals_caught INTEGER DEFAULT 0,
                total_scouts INTEGER DEFAULT 0,
                total_gifts_given INTEGER DEFAULT 0,
                total_heals_given INTEGER DEFAULT 0,
                total_escapes INTEGER DEFAULT 0,
                total_protections_bought INTEGER DEFAULT 0,
                contracts_completed INTEGER DEFAULT 0,
                legendary_items JSONB DEFAULT '[]'::jsonb,
                auto_registered BOOLEAN DEFAULT FALSE,
                last_heat_decay TIMESTAMP DEFAULT NULL,
                league_points INTEGER DEFAULT 0,
                win_streak INTEGER DEFAULT 0,
                battles_today INTEGER DEFAULT 0,
                total_battles INTEGER DEFAULT 0,
                daily_missions_data JSONB DEFAULT '{}'::jsonb,
                daily_missions_reset TIMESTAMP DEFAULT NULL
            );
            """,
            """CREATE TABLE IF NOT EXISTS jutsu_discoveries (id SERIAL PRIMARY KEY, combination TEXT UNIQUE, jutsu_name TEXT, discovered_by TEXT, discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""",
            """CREATE TABLE IF NOT EXISTS battle_history (id SERIAL PRIMARY KEY, player1_id BIGINT, player2_id BIGINT, winner_id BIGINT, battle_log TEXT, duration_seconds INTEGER, fought_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"""
        )
        
        with conn.cursor() as c:
            for cmd in commands:
                c.execute(cmd)
        conn.commit()
        logger.info("✅ Database tables checked/created successfully.")
        return True
    
    return execute_with_retry(_create_tables)

# --- SCHEMA UPDATER ---
def update_schema():
    """Update database schema"""
    def _update_schema(conn):
        cols = {
            'players': [
                # 🔥 NEW COLUMN FOR SPAWN SYSTEM 🔥
                ('character_collection', "JSONB DEFAULT '{}'::jsonb"),
                # Existing columns
                ('equipment', "JSONB DEFAULT '{}'::jsonb"),
                ('inventory', "JSONB DEFAULT '[]'::jsonb"),
                ('daily_train_count', 'INTEGER DEFAULT 0'),
                ('last_train_reset_date', 'DATE DEFAULT NULL'),
                ('story_progress', 'INTEGER DEFAULT 0'),
                ('steal_cooldown', 'TIMESTAMP DEFAULT NULL'),
                ('scout_cooldown', 'TIMESTAMP DEFAULT NULL'),
                ('assassinate_cooldown', 'TIMESTAMP DEFAULT NULL'),
                ('daily_mission_count', 'INTEGER DEFAULT 0'),
                ('last_mission_reset_date', 'DATE DEFAULT NULL'),
                ('last_daily_claim', 'DATE DEFAULT NULL'),
                ('protection_until', 'TIMESTAMP DEFAULT NULL'),
                ('hospitalized_until', 'TIMESTAMP DEFAULT NULL'),
                ('hospitalized_by', 'BIGINT DEFAULT NULL'),
                ('kills', 'INTEGER DEFAULT 0'),
                ('last_inline_game_date', 'DATE DEFAULT NULL'),
                ('inline_pack_cooldown', 'TIMESTAMP DEFAULT NULL'),
                ('heat_level', 'INTEGER DEFAULT 0'),
                ('bounty', 'INTEGER DEFAULT 0'),
                ('reputation_points', 'INTEGER DEFAULT 0'),
                ('reputation_title', 'TEXT DEFAULT NULL'),
                ('total_steals', 'INTEGER DEFAULT 0'),
                ('total_steals_caught', 'INTEGER DEFAULT 0'),
                ('total_scouts', 'INTEGER DEFAULT 0'),
                ('total_gifts_given', 'INTEGER DEFAULT 0'),
                ('total_heals_given', 'INTEGER DEFAULT 0'),
                ('total_escapes', 'INTEGER DEFAULT 0'),
                ('total_protections_bought', 'INTEGER DEFAULT 0'),
                ('contracts_completed', 'INTEGER DEFAULT 0'),
                ('legendary_items', "JSONB DEFAULT '[]'::jsonb"),
                ('auto_registered', 'BOOLEAN DEFAULT FALSE'),
                ('last_heat_decay', 'TIMESTAMP DEFAULT NULL'),
                ('active_guaranteed_kill', 'BOOLEAN DEFAULT FALSE'),
                ('rob_boost_until', 'TIMESTAMP DEFAULT NULL'),
                ('rob_boost_value', 'REAL DEFAULT 0'),
                # 🎮 League Battle System Fields
                ('league_points', 'INTEGER DEFAULT 0'),
                ('win_streak', 'INTEGER DEFAULT 0'),
                ('battles_today', 'INTEGER DEFAULT 0'),
                ('total_battles', 'INTEGER DEFAULT 0'),
                ('daily_missions_data', "JSONB DEFAULT '{}'::jsonb"),
                ('daily_missions_reset', 'TIMESTAMP DEFAULT NULL')
            ]
        }
        
        with conn.cursor() as c:
            for table, col_list in cols.items():
                for col, dtype in col_list:
                    try:
                        c.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {dtype};")
                    except:
                        pass
        
        conn.commit()
        logger.info("✅ Schema updated successfully!")
        return True
    
    return execute_with_retry(_update_schema)

# --- PLAYER FUNCTIONS ---
def get_player(user_id):
    """Get player data from cache or database"""
    # Check cache first
    cp = cache.get_player_cache(user_id)
    if cp:
        # Convert ISO strings back to datetime/date objects
        for k in ['battle_cooldown','steal_cooldown','scout_cooldown','assassinate_cooldown',
                  'protection_until','hospitalized_until','created_at','inline_pack_cooldown','last_heat_decay','daily_missions_reset']:
            if cp.get(k):
                try:
                    cp[k] = datetime.datetime.fromisoformat(cp[k])
                except:
                    pass
        for k in ['last_train_reset_date','last_mission_reset_date','last_daily_claim','last_inline_game_date']:
            if cp.get(k):
                try:
                    cp[k] = datetime.date.fromisoformat(cp[k])
                except:
                    pass
        return cp
    
    # Get from database
    def _get_player(conn):
        with conn.cursor() as c:
            c.execute("SELECT * FROM players WHERE user_id = %s", (user_id,))
            r = c.fetchone()
            if r:
                p = dict_factory(c, r)
                # Set defaults for league & collection fields
                p.setdefault('league_points', 0)
                p.setdefault('win_streak', 0)
                p.setdefault('battles_today', 0)
                p.setdefault('total_battles', 0)
                p.setdefault('daily_missions_data', {})
                p.setdefault('daily_missions_reset', None)
                p.setdefault('character_collection', {}) # 🔥 Default for new column
                cache.set_player_cache(user_id, p)
                return p
        return None
    
    return execute_with_retry(_get_player)

def create_player(user_id, username, village, auto_registered=False):
    """Create new player"""
    def _create_player(conn):
        s = gl.distribute_stats({'strength':10,'speed':10,'intelligence':10,'stamina':10}, 0)
        
        sql = """INSERT INTO players 
        (user_id, username, village, max_hp, current_hp, max_chakra, current_chakra, 
        strength, speed, intelligence, stamina, equipment, inventory, character_collection, daily_train_count, 
        last_train_reset_date, story_progress, known_jutsus, discovered_combinations, 
        steal_cooldown, scout_cooldown, assassinate_cooldown, daily_mission_count, 
        last_mission_reset_date, last_daily_claim, protection_until, hospitalized_until, 
        hospitalized_by, kills, last_inline_game_date, inline_pack_cooldown, heat_level, 
        bounty, reputation_points, reputation_title, total_steals, total_steals_caught, 
        total_scouts, total_gifts_given, total_heals_given, total_escapes, 
        total_protections_bought, contracts_completed, legendary_items, auto_registered, 
        last_heat_decay, league_points, win_streak, battles_today, total_battles, 
        daily_missions_data, daily_missions_reset) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        
        with conn.cursor() as c:
            c.execute(sql, (
                user_id, username, village, s['max_hp'], s['max_hp'], s['max_chakra'], 
                s['max_chakra'], s['strength'], s['speed'], s['intelligence'], s['stamina'], 
                '{}', '[]', '{}', 0, None, 0, '[]', '[]', None, None, None, 0, None, None, None, 
                None, None, 0, None, None, 0, 0, 0, None, 0, 0, 0, 0, 0, 0, 0, 0, '[]', 
                auto_registered, None, 0, 0, 0, 0, '{}', None
            ))
        conn.commit()
        
        reg_type = "AUTO-REGISTERED" if auto_registered else "MANUALLY REGISTERED"
        logger.info(f"✅ {reg_type}: {username} (ID: {user_id}) → {village}")
        
        cache.clear_player_cache(user_id)
        return True
    
    result = execute_with_retry(_create_player)
    return result if result else False

def update_player(user_id, updates):
    """Update player data"""
    def _update_player(conn):
        set_clauses = []
        values = []
        
        for k, v in updates.items():
            set_clauses.append(f"{k} = %s")
            if isinstance(v, (dict, list)):
                values.append(json.dumps(v))
            else:
                values.append(v)
        
        values.append(user_id)
        
        with conn.cursor() as c:
            c.execute(f"UPDATE players SET {', '.join(set_clauses)} WHERE user_id = %s", tuple(values))
        conn.commit()
        
        cache.clear_player_cache(user_id)
        return True
    
    result = execute_with_retry(_update_player)
    return result if result else False

def atomic_add_ryo(user_id, amount):
    """Atomically add/subtract Ryo"""
    def _atomic_add_ryo(conn):
        with conn.cursor() as c:
            c.execute("UPDATE players SET ryo = ryo + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()
        cache.clear_player_cache(user_id)
        return True
    
    result = execute_with_retry(_atomic_add_ryo)
    return result if result else False

def atomic_add_exp(user_id, amount):
    """Atomically add EXP"""
    def _atomic_add_exp(conn):
        with conn.cursor() as c:
            c.execute("UPDATE players SET exp = exp + %s, total_exp = total_exp + %s WHERE user_id = %s", 
                     (amount, amount, user_id))
        conn.commit()
        cache.clear_player_cache(user_id)
        return True
    
    result = execute_with_retry(_atomic_add_exp)
    return result if result else False

# 🔥 NEW FUNCTION FOR SPAWN SYSTEM 🔥
def add_character_to_collection(user_id, char_data):
    """Add a caught character to the player's collection"""
    def _add_char(conn):
        with conn.cursor() as c:
            # 1. Get current collection
            c.execute("SELECT character_collection FROM players WHERE user_id = %s", (user_id,))
            result = c.fetchone()
            
            # Initialize if null
            collection = result[0] if result and result[0] else {}
            
            # 2. Add or Update character
            char_id = str(char_data['id'])
            if char_id in collection:
                collection[char_id]['count'] += 1
            else:
                collection[char_id] = {
                    'name': char_data['name'],
                    'rarity': char_data.get('rarity', 'Common'),
                    'image': char_data['image'],
                    'count': 1,
                    'caught_at': str(datetime.datetime.now())
                }
            
            # 3. Save back to DB
            c.execute("UPDATE players SET character_collection = %s WHERE user_id = %s", 
                     (json.dumps(collection), user_id))
        conn.commit()
        cache.clear_player_cache(user_id)
        return True
    
    return execute_with_retry(_add_char)

# --- LEADERBOARD FUNCTIONS ---
def get_top_players_by_ryo(limit=10):
    """Get top players by Ryo"""
    def _get_top_ryo(conn):
        with conn.cursor() as c:
            c.execute("SELECT user_id, username, ryo FROM players ORDER BY ryo DESC LIMIT %s", (limit,))
            return [dict(zip([col[0] for col in c.description], r)) for r in c.fetchall()]
    
    result = execute_with_retry(_get_top_ryo)
    return result if result else []

def get_top_players_by_exp(limit=10):
    """Get top players by EXP"""
    def _get_top_exp(conn):
        with conn.cursor() as c:
            c.execute("SELECT user_id, username, level, total_exp FROM players ORDER BY total_exp DESC LIMIT %s", (limit,))
            return [dict(zip([col[0] for col in c.description], r)) for r in c.fetchall()]
    
    result = execute_with_retry(_get_top_exp)
    return result if result else []

def get_top_players_by_wins(limit=10):
    """Get top players by wins"""
    def _get_top_wins(conn):
        with conn.cursor() as c:
            c.execute("SELECT user_id, username, wins FROM players WHERE wins > 0 ORDER BY wins DESC LIMIT %s", (limit,))
            return [dict(zip([col[0] for col in c.description], r)) for r in c.fetchall()]
    
    result = execute_with_retry(_get_top_wins)
    return result if result else []

def get_top_players_by_kills(limit=10):
    """Get top players by kills"""
    def _get_top_kills(conn):
        with conn.cursor() as c:
            c.execute("SELECT user_id, username, kills FROM players WHERE kills > 0 ORDER BY kills DESC LIMIT %s", (limit,))
            return [dict(zip([col[0] for col in c.description], r)) for r in c.fetchall()]
    
    result = execute_with_retry(_get_top_kills)
    return result if result else []

# 🎮 League Battle System Functions
def get_top_players_by_league(limit=10):
    """Get top players by league points"""
    def _get_top_league(conn):
        with conn.cursor() as c:
            c.execute("""
                SELECT user_id, username, league_points, win_streak 
                FROM players 
                WHERE league_points > 0 
                ORDER BY league_points DESC 
                LIMIT %s
            """, (limit,))
            return [dict(zip([col[0] for col in c.description], r)) for r in c.fetchall()]
    
    result = execute_with_retry(_get_top_league)
    return result if result else []

def reset_daily_battles():
    """Reset battles_today for all players (called daily via cron/scheduler)"""
    def _reset_battles(conn):
        with conn.cursor() as c:
            c.execute("UPDATE players SET battles_today = 0")
        conn.commit()
        logger.info("✅ Daily battles reset completed")
        return True
    
    result = execute_with_retry(_reset_battles)
    return result if result else False

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Initializing database...")
    create_tables()
    update_schema()
    logger.info("✅ Database ready!")
