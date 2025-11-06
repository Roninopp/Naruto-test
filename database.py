import logging
import psycopg2
import psycopg2.pool
import json
import datetime
import game_logic as gl
import cache

logger = logging.getLogger(__name__)

# --- IMPORTANT ---
# PASTE YOUR *NEW* CONNECTION STRING HERE
# (The one you get AFTER you click "Reset password")
# Make sure it is inside the quotes.
DATABASE_URL = "postgresql://neondb_owner:npg_ZBiVmpx5rCR6@ep-fragrant-feather-a4eur7c4-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require" 
# --- END ---


# --- Connection Pool ---
try:
    pool = psycopg2.pool.SimpleConnectionPool(1, 10, dsn=DATABASE_URL)
    logger.info("Database connection pool created successfully.")
except Exception as e:
    logger.critical(f"FATAL: Could not create database connection pool: {e}")
    pool = None

def get_db_connection():
    """Gets a connection from the pool."""
    if pool is None:
        logger.error("Database pool is not initialized.")
        return None
    try:
        conn = pool.getconn()
        return conn
    except Exception as e:
        logger.error(f"Error getting connection from pool: {e}")
        return None

def put_db_connection(conn):
    """Returns a connection to the pool."""
    if pool:
        pool.putconn(conn)

def dict_factory(cursor, row):
    """Converts a row to a dictionary."""
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}

# --- Schema & Table Creation ---
def create_tables():
    """Creates all database tables if they don't exist."""
    conn = get_db_connection()
    if conn is None: return
    
    # All CREATE TABLE commands
    commands = (
        """
        CREATE TABLE IF NOT EXISTS players (
            user_id BIGINT PRIMARY KEY, 
            username TEXT NOT NULL, 
            village TEXT NOT NULL,
            level INTEGER DEFAULT 1, 
            exp INTEGER DEFAULT 0, 
            total_exp INTEGER DEFAULT 0,
            max_hp INTEGER DEFAULT 100, 
            current_hp INTEGER DEFAULT 100,
            max_chakra INTEGER DEFAULT 100, 
            current_chakra INTEGER DEFAULT 100,
            strength INTEGER DEFAULT 10, 
            speed INTEGER DEFAULT 10, 
            intelligence INTEGER DEFAULT 10, 
            stamina INTEGER DEFAULT 10,
            known_jutsus JSONB DEFAULT '[]'::jsonb, 
            discovered_combinations JSONB DEFAULT '[]'::jsonb,
            ryo INTEGER DEFAULT 100, 
            rank TEXT DEFAULT 'Academy Student',
            wins INTEGER DEFAULT 0, 
            losses INTEGER DEFAULT 0,
            battle_cooldown TIMESTAMP, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            equipment JSONB DEFAULT '{}'::jsonb, 
            inventory JSONB DEFAULT '[]'::jsonb,
            daily_train_count INTEGER DEFAULT 0, 
            last_train_reset_date DATE DEFAULT NULL,
            boss_attack_cooldown TIMESTAMP, 
            story_progress INTEGER DEFAULT 0,
            akatsuki_cooldown JSONB DEFAULT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS jutsu_discoveries (
            id SERIAL PRIMARY KEY,
            combination TEXT UNIQUE,
            jutsu_name TEXT,
            discovered_by TEXT,
            discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS battle_history (
            id SERIAL PRIMARY KEY,
            player1_id BIGINT,
            player2_id BIGINT,
            winner_id BIGINT,
            battle_log TEXT,
            duration_seconds INTEGER,
            fought_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS world_boss_enabled_chats (
            chat_id BIGINT PRIMARY KEY,
            enabled_by_user_id BIGINT,
            enabled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS world_boss_status (
            chat_id BIGINT PRIMARY KEY,
            is_active INTEGER DEFAULT 0,
            boss_key TEXT,
            current_hp INTEGER,
            max_hp INTEGER,
            ryo_pool INTEGER,
            spawn_time TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS world_boss_damage (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            username TEXT NOT NULL,
            total_damage INTEGER DEFAULT 0,
            UNIQUE(chat_id, user_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS group_event_settings (
            chat_id BIGINT PRIMARY KEY,
            events_enabled INTEGER DEFAULT 1
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS active_akatsuki_fights (
            message_id BIGINT PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            enemy_name TEXT NOT NULL,
            enemy_hp INTEGER NOT NULL,
            player_1_id BIGINT DEFAULT NULL,
            player_2_id BIGINT DEFAULT NULL,
            player_3_id BIGINT DEFAULT NULL,
            turn_player_id TEXT DEFAULT NULL, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    
    try:
        with conn.cursor() as cursor:
            for command in commands:
                cursor.execute(command)
        conn.commit()
        logger.info("Database tables checked/created successfully.")
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error creating tables: {e}")
        conn.rollback()
    finally:
        put_db_connection(conn)

def update_schema():
    """Checks and updates the DB schema with new columns if they don't exist."""
    conn = get_db_connection()
    if conn is None: return
    
    # Define columns and their types
    columns_to_check = {
        'players': [
            ('equipment', "TEXT DEFAULT '{}'"), # Kept as TEXT for alter, will be treated as JSONB
            ('inventory', "TEXT DEFAULT '[]'"),
            ('daily_train_count', 'INTEGER DEFAULT 0'),
            ('last_train_reset_date', 'TEXT DEFAULT NULL'), # Will be DATE in new tables
            ('boss_attack_cooldown', 'TEXT DEFAULT NULL'), # Will be TIMESTAMP
            ('story_progress', 'INTEGER DEFAULT 0'),
            ('akatsuki_cooldown', 'TEXT DEFAULT NULL') # Will be JSONB
        ]
    }
    
    try:
        with conn.cursor() as cursor:
            for table, columns in columns_to_check.items():
                for column, col_type in columns:
                    try:
                        # Use JSONB for new JSON columns, TEXT for old ones just in case
                        if 'jsonb' in col_type.lower():
                            col_type_sql = 'JSONB'
                        else:
                            col_type_sql = col_type
                        
                        cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type_sql};")
                        logger.info(f"DB Schema: Checked/Added '{column}' column to '{table}'.")
                    except psycopg2.errors.DuplicateColumn:
                        conn.rollback() # Rollback the single ADD COLUMN transaction
                    except Exception as e:
                        logger.warning(f"Warning during schema update for {table}.{column}: {e}")
                        conn.rollback()
        conn.commit()
    except Exception as e:
        logger.error(f"Error updating database schema: {e}")
        conn.rollback()
    finally:
        put_db_connection(conn)

# --- Player Functions ---

def get_player(user_id):
    """Fetches a player's data from cache or database."""
    cached_player = cache.get_player_cache(user_id)
    if cached_player: 
        return cached_player

    conn = get_db_connection()
    if conn is None: return None
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM players WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            if row:
                player_dict = dict_factory(cursor, row)
                cache.set_player_cache(user_id, player_dict)
                return player_dict
            else:
                return None
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error fetching player {user_id}: {e}")
        return None
    finally:
        put_db_connection(conn)

def create_player(user_id, username, village):
    """Creates a new player in the database."""
    conn = get_db_connection()
    if conn is None: return False
    
    base_stats = {'strength': 10, 'speed': 10, 'intelligence': 10, 'stamina': 10}
    initial_stats = gl.distribute_stats(base_stats, 0)
    
    sql = """
        INSERT INTO players
        (user_id, username, village, max_hp, current_hp, max_chakra, current_chakra,
         strength, speed, intelligence, stamina, equipment, inventory,
         daily_train_count, last_train_reset_date, boss_attack_cooldown, story_progress, akatsuki_cooldown,
         known_jutsus, discovered_combinations)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (
                user_id, username, village,
                initial_stats['max_hp'], initial_stats['max_hp'], initial_stats['max_chakra'], initial_stats['max_chakra'],
                initial_stats['strength'], initial_stats['speed'], initial_stats['intelligence'], initial_stats['stamina'],
                '{}', '[]', 0, None, None, 0, None, '[]', '[]'
            ))
        conn.commit()
        logger.info(f"New player created: {username} (ID: {user_id}) in {village}")
        cache.clear_player_cache(user_id)
        return True
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error creating player {user_id}: {e}")
        conn.rollback()
        return False
    finally:
        put_db_connection(conn)

def update_player(user_id, updates):
    """Dynamically updates a player's data."""
    conn = get_db_connection()
    if conn is None: return False
    
    set_clause = []
    values = []
    
    for key, value in updates.items():
        set_clause.append(f"{key} = %s")
        # Convert dicts/lists to JSON strings if they are JSONB columns
        if isinstance(value, (dict, list)):
            values.append(json.dumps(value))
        else:
            values.append(value)
            
    values.append(user_id)
    
    sql = f"UPDATE players SET {', '.join(set_clause)} WHERE user_id = %s"
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(values))
        conn.commit()
        logger.info(f"Player {user_id} updated in DB: {list(updates.keys())}") 
        cache.clear_player_cache(user_id)
        return True
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error updating player {user_id}: {e}")
        conn.rollback()
        return False
    finally:
        put_db_connection(conn)

# --- Boss Functions ---

def enable_boss_chat(chat_id, user_id):
    conn = get_db_connection()
    if conn is None: return False
    sql = "INSERT INTO world_boss_enabled_chats (chat_id, enabled_by_user_id) VALUES (%s, %s) ON CONFLICT (chat_id) DO NOTHING"
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (chat_id, user_id))
        conn.commit()
        return True
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error enabling world_boss for chat {chat_id}: {e}")
        conn.rollback()
        return False
    finally:
        put_db_connection(conn)

def get_all_boss_chats():
    conn = get_db_connection()
    if conn is None: return []
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT chat_id FROM world_boss_enabled_chats")
            rows = cursor.fetchall()
            return [row[0] for row in rows] 
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error getting all world_boss chats: {e}")
        return []
    finally:
        put_db_connection(conn)

def get_boss_status(chat_id):
    conn = get_db_connection()
    if conn is None: return None
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM world_boss_status WHERE chat_id = %s", (chat_id,))
            row = cursor.fetchone()
            if row:
                return dict_factory(cursor, row)
            else:
                # Create a new entry if it doesn't exist
                cursor.execute("INSERT INTO world_boss_status (chat_id, is_active) VALUES (%s, 0)", (chat_id,))
                conn.commit()
                return {'chat_id': chat_id, 'is_active': 0, 'boss_key': None, 'current_hp': 0, 'max_hp': 0, 'ryo_pool': 0, 'spawn_time': None}
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error getting boss status for chat {chat_id}: {e}")
        return None
    finally:
        put_db_connection(conn)

# --- Akatsuki Event Functions ---

def register_event_chat(chat_id):
    conn = get_db_connection()
    if conn is None: return
    sql = "INSERT INTO group_event_settings (chat_id, events_enabled) VALUES (%s, 1) ON CONFLICT (chat_id) DO NOTHING"
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (chat_id,))
        conn.commit()
        logger.info(f"Passively registered chat {chat_id} for events.")
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error registering event chat {chat_id}: {e}")
        conn.rollback()
    finally:
        put_db_connection(conn)

def get_event_settings_dict():
    conn = get_db_connection()
    if conn is None: return {}
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT chat_id, events_enabled FROM group_event_settings")
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error getting event settings dict: {e}")
        return {}
    finally:
        put_db_connection(conn)

def toggle_auto_events(chat_id, status):
    conn = get_db_connection()
    if conn is None: return
    sql = "INSERT INTO group_event_settings (chat_id, events_enabled) VALUES (%s, %s) ON CONFLICT (chat_id) DO UPDATE SET events_enabled = %s"
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (chat_id, status, status))
        conn.commit()
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error toggling events for chat {chat_id}: {e}")
        conn.rollback()
    finally:
        put_db_connection(conn)

def create_akatsuki_fight(message_id, chat_id, enemy_name):
    conn = get_db_connection()
    if conn is None: return
    
    enemy_info = gl.AKATSUKI_ENEMIES.get(enemy_name)
    if not enemy_info: 
        logger.error(f"Invalid enemy_name '{enemy_name}' passed to create_akatsuki_fight.")
        return
        
    sql = "INSERT INTO active_akatsuki_fights (message_id, chat_id, enemy_name, enemy_hp) VALUES (%s, %s, %s, %s)"
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (message_id, chat_id, enemy_name, enemy_info['max_hp']))
        conn.commit()
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error creating akatsuki fight {message_id}: {e}")
        conn.rollback()
    finally:
        put_db_connection(conn)
        
def get_akatsuki_fight(chat_id, message_id=None):
    conn = get_db_connection()
    if conn is None: return None
    try:
        with conn.cursor() as cursor:
            if message_id:
                cursor.execute("SELECT * FROM active_akatsuki_fights WHERE message_id = %s", (message_id,))
            else:
                cursor.execute("SELECT * FROM active_akatsuki_fights WHERE chat_id = %s", (chat_id,))
            row = cursor.fetchone()
            return dict_factory(cursor, row) if row else None
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error getting akatsuki fight for chat {chat_id}: {e}")
        return None
    finally:
        put_db_connection(conn)

def add_player_to_fight(message_id, chat_id, user_id):
    conn = get_db_connection()
    if conn is None: return {'status': 'failed'}
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM active_akatsuki_fights WHERE message_id = %s AND chat_id = %s", (message_id, chat_id))
            row = cursor.fetchone()
            
            if not row:
                return {'status': 'failed'} 

            fight = dict_factory(cursor, row)
            
            if user_id in [fight['player_1_id'], fight['player_2_id'], fight['player_3_id']]:
                return {'status': 'already_joined'}
                
            empty_slot = None
            if fight['player_1_id'] is None:
                empty_slot = 'player_1_id'
            elif fight['player_2_id'] is None:
                empty_slot = 'player_2_id'
            elif fight['player_3_id'] is None:
                empty_slot = 'player_3_id'
            else:
                return {'status': 'full'} 
                
            cursor.execute(f"UPDATE active_akatsuki_fights SET {empty_slot} = %s WHERE message_id = %s", (user_id, message_id))
            conn.commit()
            
            return {'status': 'ready'} if empty_slot == 'player_3_id' else {'status': 'joined'}
            
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error adding player {user_id} to fight {message_id}: {e}")
        conn.rollback()
        return {'status': 'failed'}
    finally:
        put_db_connection(conn)

def set_akatsuki_turn(message_id, turn_player_id):
    conn = get_db_connection()
    if conn is None: return
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE active_akatsuki_fights SET turn_player_id = %s WHERE message_id = %s", (str(turn_player_id), message_id))
        conn.commit()
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error setting akatsuki turn for {message_id}: {e}")
        conn.rollback()
    finally:
        put_db_connection(conn)

def update_akatsuki_fight_hp(message_id, new_hp):
    conn = get_db_connection()
    if conn is None: return
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE active_akatsuki_fights SET enemy_hp = %s WHERE message_id = %s", (new_hp, message_id))
        conn.commit()
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error updating akatsuki HP for {message_id}: {e}")
        conn.rollback()
    finally:
        put_db_connection(conn)

def add_player_damage_to_fight(message_id, user_id, damage_dealt):
    """(Placeholder) In the future, you could add a table to track this."""
    logger.info(f"Player {user_id} dealt {damage_dealt} to Akatsuki fight {message_id}")

def clear_akatsuki_fight(chat_id):
    conn = get_db_connection()
    if conn is None: return
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM active_akatsuki_fights WHERE chat_id = %s", (chat_id,))
        conn.commit()
        logger.info(f"Cleared active Akatsuki fight for chat {chat_id}")
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error clearing akatsuki fight for chat {chat_id}: {e}")
        conn.rollback()
    finally:
        put_db_connection(conn)

def set_akatsuki_cooldown(user_id, action, cooldown_seconds):
    """Sets a specific action's cooldown."""
    player = get_player(user_id)
    if not player: return
    
    try:
        cooldowns = player.get('akatsuki_cooldown') or {}
        if isinstance(cooldowns, str): # Handle old text-based data
            cooldowns = json.loads(cooldowns)
    except:
        cooldowns = {}
        
    cooldown_end_time = (datetime.datetime.now() + datetime.timedelta(seconds=cooldown_seconds)).isoformat()
    cooldowns[action] = cooldown_end_time
    
    update_player(user_id, {'akatsuki_cooldown': json.dumps(cooldowns)})

def remove_player_from_fight(message_id, user_id):
    """Removes a fleeing player from an active fight slot."""
    conn = get_db_connection()
    if conn is None: return
    
    commands = [
        "UPDATE active_akatsuki_fights SET player_1_id = NULL WHERE message_id = %s AND player_1_id = %s",
        "UPDATE active_akatsuki_fights SET player_2_id = NULL WHERE message_id = %s AND player_2_id = %s",
        "UPDATE active_akatsuki_fights SET player_3_id = NULL WHERE message_id = %s AND player_3_id = %s"
    ]
    try:
        with conn.cursor() as cursor:
            for command in commands:
                cursor.execute(command, (message_id, user_id))
        conn.commit()
    except (Exception, psycopg2.DatabaseError) as e:
        logger.error(f"Error removing player {user_id} from fight {message_id}: {e}")
        conn.rollback()
    finally:
        put_db_connection(conn)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Initializing database...")
    create_tables()
    update_schema()
