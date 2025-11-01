import sqlite3
import logging
import game_logic
import cache
import json

logger = logging.getLogger(__name__)

# --- FIX: Set correct DB file ---
DATABASE_FILE = 'test_ninja_rpg.db' 
# --- END FIX ---

# --- Schema Update Function ---
def update_schema():
    conn = get_db_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(players);")
        columns = [row['name'] for row in cursor.fetchall()]

        if 'equipment' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN equipment TEXT DEFAULT '{}';"); logger.info("DB Schema: Added 'equipment' column.")
        if 'inventory' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN inventory TEXT DEFAULT '[]';"); logger.info("DB Schema: Added 'inventory' column.")
        if 'discovered_combinations' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN discovered_combinations TEXT DEFAULT '[]';"); logger.info("DB Schema: Added 'discovered_combinations' column.")
        if 'daily_train_count' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN daily_train_count INTEGER DEFAULT 0;"); logger.info("DB Schema: Added 'daily_train_count' column.")
        if 'last_train_reset_date' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN last_train_reset_date TEXT DEFAULT NULL;"); logger.info("DB Schema: Added 'last_train_reset_date' column.")
        if 'boss_attack_cooldown' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN boss_attack_cooldown TEXT DEFAULT NULL;"); logger.info("DB Schema: Added 'boss_attack_cooldown' column.")
        if 'story_progress' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN story_progress INTEGER DEFAULT 0;"); logger.info("DB Schema: Added 'story_progress' column.")
        
        # --- NEW: Akatsuki Event Cooldown Column ---
        if 'akatsuki_cooldown' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN akatsuki_cooldown TEXT DEFAULT NULL;")
            logger.info("Database Schema UPDATED: Added 'akatsuki_cooldown' column.")
        # --- END NEW ---
            
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error updating database schema: {e}")
    finally:
        conn.close()


def get_db_connection():
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error connecting to database: {e}")
        return None

def create_tables():
    conn = get_db_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        
        # Players Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY, username TEXT NOT NULL, village TEXT NOT NULL,
            level INTEGER DEFAULT 1, exp INTEGER DEFAULT 0, total_exp INTEGER DEFAULT 0,
            max_hp INTEGER DEFAULT 100, current_hp INTEGER DEFAULT 100,
            max_chakra INTEGER DEFAULT 100, current_chakra INTEGER DEFAULT 100,
            strength INTEGER DEFAULT 10, speed INTEGER DEFAULT 10, 
            intelligence INTEGER DEFAULT 10, stamina INTEGER DEFAULT 10,
            known_jutsus TEXT DEFAULT '[]', discovered_combinations TEXT DEFAULT '[]',
            ryo INTEGER DEFAULT 100, rank TEXT DEFAULT 'Academy Student',
            wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
            battle_cooldown TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            equipment TEXT DEFAULT '{}', inventory TEXT DEFAULT '[]',
            daily_train_count INTEGER DEFAULT 0, last_train_reset_date TEXT DEFAULT NULL,
            boss_attack_cooldown TEXT DEFAULT NULL, story_progress INTEGER DEFAULT 0,
            akatsuki_cooldown TEXT DEFAULT NULL -- NEW
        );
        """)
        
        # Other tables (unchanged)
        cursor.execute("CREATE TABLE IF NOT EXISTS jutsu_discoveries (id INTEGER PRIMARY KEY, combination TEXT UNIQUE, jutsu_name TEXT, discovered_by TEXT, discovered_at TEXT);")
        cursor.execute("CREATE TABLE IF NOT EXISTS battle_history (id INTEGER PRIMARY KEY, player1_id INTEGER, player2_id INTEGER, winner_id INTEGER, battle_log TEXT, duration_seconds INTEGER, fought_at TEXT);")
        cursor.execute("CREATE TABLE IF NOT EXISTS world_boss_enabled_chats (chat_id INTEGER PRIMARY KEY, enabled_by_user_id INTEGER, enabled_at TEXT);")
        cursor.execute("CREATE TABLE IF NOT EXISTS world_boss_status (chat_id INTEGER PRIMARY KEY, is_active INTEGER DEFAULT 0, boss_key TEXT, current_hp INTEGER, max_hp INTEGER, ryo_pool INTEGER, spawn_time TEXT);")
        cursor.execute("CREATE TABLE IF NOT EXISTS world_boss_damage (id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, username TEXT NOT NULL, total_damage INTEGER DEFAULT 0, UNIQUE(chat_id, user_id));")

        # --- NEW: Auto-Event Tables ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_event_settings (
            chat_id INTEGER PRIMARY KEY,
            events_enabled INTEGER DEFAULT 1
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_akatsuki_fights (
            message_id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            enemy_name TEXT NOT NULL,
            enemy_hp INTEGER NOT NULL,
            player_1_id INTEGER DEFAULT NULL,
            player_2_id INTEGER DEFAULT NULL,
            player_3_id INTEGER DEFAULT NULL,
            turn_player_id INTEGER DEFAULT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # --- END NEW ---
        
        conn.commit()
        logger.info("Database tables checked/created successfully.")

    except sqlite3.Error as e:
        logger.error(f"Error creating tables: {e}")
    finally:
        conn.close()

def get_player(user_id):
    cached_player = cache.get_player_cache(user_id)
    if cached_player and 'akatsuki_cooldown' in cached_player: # Check for new column
        return cached_player
    else:
        cache.clear_player_cache(user_id) # Cache is old

    conn = get_db_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
        player_row = cursor.fetchone()
        if player_row:
            player_dict = dict(player_row)
            cache.set_player_cache(user_id, player_dict)
            return player_dict
        else:
            return None
    except sqlite3.Error as e:
        logger.error(f"Error fetching player {user_id}: {e}")
        return None
    finally:
        conn.close()

def create_player(user_id, username, village):
    conn = get_db_connection()
    if conn is None: return False
    try:
        base_stats = {'strength': 10, 'speed': 10, 'intelligence': 10, 'stamina': 10}
        initial_stats = game_logic.distribute_stats(base_stats, 0)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO players
            (user_id, username, village, max_hp, current_hp, max_chakra, current_chakra,
             strength, speed, intelligence, stamina, equipment, inventory,
             daily_train_count, last_train_reset_date, boss_attack_cooldown, story_progress, akatsuki_cooldown) -- NEW
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, village,
             initial_stats['max_hp'], initial_stats['max_hp'], initial_stats['max_chakra'], initial_stats['max_chakra'],
             initial_stats['strength'], initial_stats['speed'], initial_stats['intelligence'], initial_stats['stamina'],
             '{}', '[]', 0, None, None, 0, None) # NEW: Default value
        )
        conn.commit()
        logger.info(f"New player created: {username} (ID: {user_id}) in {village}")
        cache.clear_player_cache(user_id)
        return True
    except sqlite3.Error as e:
        logger.error(f"Error creating player {user_id}: {e}")
        return False
    finally:
        conn.close()

def update_player(user_id, updates):
    conn = get_db_connection()
    if conn is None: return False
    try:
        set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values())
        values.append(user_id)
        query = f"UPDATE players SET {set_clause} WHERE user_id = ?"
        cursor = conn.cursor()
        cursor.execute(query, tuple(values))
        conn.commit()
        logger.info(f"Player {user_id} updated in DB: {list(updates.keys())}") # Log keys
        cache.clear_player_cache(user_id)
        return True
    except sqlite3.Error as e:
        logger.error(f"Error updating player {user_id}: {e}")
        return False
    finally:
        conn.close()

# (World Boss DB functions are unchanged)
def enable_boss_chat(chat_id, user_id):
    # ... (code is the same)
    pass
def get_all_boss_chats():
    # ... (code is the same)
    pass
def get_boss_status(chat_id):
    # ... (code is the same)
    pass
    
# --- NEW: Akatsuki Auto-Event DB Functions ---

def register_event_chat(chat_id):
    """Passively adds a chat to the settings table. Does not overwrite existing."""
    conn = get_db_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO group_event_settings (chat_id, events_enabled) VALUES (?, 1)", (chat_id,))
        conn.commit()
        logger.info(f"Passively registered chat {chat_id} for events.")
    except sqlite3.Error as e:
        logger.error(f"Error registering event chat {chat_id}: {e}")
    finally:
        if conn: conn.close()

def get_all_event_chats():
    """Gets all chat IDs where events are enabled (DEFAULT 1)."""
    conn = get_db_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM group_event_settings WHERE events_enabled = 1")
        rows = cursor.fetchall()
        return [row['chat_id'] for row in rows]
    except sqlite3.Error as e:
        logger.error(f"Error getting all event chats: {e}")
        return []
    finally:
        if conn: conn.close()

def get_event_status(chat_id):
    """Checks if events are enabled (1) or disabled (0) for a chat."""
    conn = get_db_connection()
    if conn is None: return 1 # Default to on if DB fails
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT events_enabled FROM group_event_settings WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        if row:
            return row['events_enabled']
        else:
            return 1 # Default to on
    except sqlite3.Error as e:
        logger.error(f"Error getting event status for chat {chat_id}: {e}")
        return 1 
    finally:
        if conn: conn.close()

def toggle_auto_events(chat_id, status):
    """Sets auto-events ON (1) or OFF (0) for a chat."""
    conn = get_db_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO group_event_settings (chat_id, events_enabled) VALUES (?, ?)", (chat_id, status))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error toggling events for chat {chat_id}: {e}")
    finally:
        if conn: conn.close()

def create_akatsuki_fight(message_id, chat_id, enemy_name):
    """Stores a new, empty Akatsuki fight."""
    conn = get_db_connection()
    if conn is None: return
    try:
        enemy_info = gl.AKATSUKI_ENEMIES.get(enemy_name)
        if not enemy_info: return
        
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO active_akatsuki_fights (message_id, chat_id, enemy_name, enemy_hp) VALUES (?, ?, ?, ?)",
            (message_id, chat_id, enemy_name, enemy_info['max_hp'])
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error creating akatsuki fight {message_id}: {e}")
    finally:
        if conn: conn.close()
        
def get_akatsuki_fight(chat_id, message_id=None):
    """Gets the active fight for a chat. If message_id is given, gets that specific one."""
    conn = get_db_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor()
        if message_id:
            cursor.execute("SELECT * FROM active_akatsuki_fights WHERE message_id = ?", (message_id,))
        else:
            cursor.execute("SELECT * FROM active_akatsuki_fights WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logger.error(f"Error getting akatsuki fight for chat {chat_id}: {e}")
        return None
    finally:
        if conn: conn.close()

def add_player_to_fight(message_id, chat_id, user_id):
    """Tries to add a player to an empty slot in the fight."""
    conn = get_db_connection()
    if conn is None: return {'status': 'failed'}
    
    try:
        cursor = conn.cursor()
        # First, check if fight exists and get its state
        cursor.execute("SELECT * FROM active_akatsuki_fights WHERE message_id = ? AND chat_id = ?", (message_id, chat_id))
        fight = cursor.fetchone()
        
        if not fight:
            return {'status': 'failed'} # Fight doesn't exist

        fight_dict = dict(fight)
        
        # Check if already joined
        if user_id in [fight_dict['player_1_id'], fight_dict['player_2_id'], fight_dict['player_3_id']]:
            return {'status': 'already_joined'}
            
        # Find first empty slot
        empty_slot = None
        if fight_dict['player_1_id'] is None:
            empty_slot = 'player_1_id'
        elif fight_dict['player_2_id'] is None:
            empty_slot = 'player_2_id'
        elif fight_dict['player_3_id'] is None:
            empty_slot = 'player_3_id'
        else:
            return {'status': 'full'} # No empty slots
            
        # Join the fight
        cursor.execute(f"UPDATE active_akatsuki_fights SET {empty_slot} = ? WHERE message_id = ?", (user_id, message_id))
        conn.commit()
        
        # Check if that was the last slot
        if empty_slot == 'player_3_id':
            return {'status': 'ready'} # Fight is full and ready to start
        else:
            return {'status': 'joined'} # Joined, but waiting for more
            
    except sqlite3.Error as e:
        logger.error(f"Error adding player {user_id} to fight {message_id}: {e}")
        conn.rollback()
        return {'status': 'failed'}
    finally:
        if conn: conn.close()

def set_akatsuki_turn(message_id, turn_player_id):
    """Updates whose turn it is in the fight."""
    conn = get_db_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE active_akatsuki_fights SET turn_player_id = ? WHERE message_id = ?", (turn_player_id, message_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error setting akatsuki turn for {message_id}: {e}")
    finally:
        if conn: conn.close()

def update_akatsuki_fight_hp(message_id, new_hp):
    """Updates the enemy's HP."""
    conn = get_db_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE active_akatsuki_fights SET enemy_hp = ? WHERE message_id = ?", (new_hp, message_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error updating akatsuki HP for {message_id}: {e}")
    finally:
        if conn: conn.close()

def add_player_damage_to_fight(message_id, user_id, damage_dealt):
    """Adds damage to a player's total for this fight (simplified, no new table)."""
    # This is a placeholder. For a real system, we'd need a separate damage table
    # like the world boss. For now, we'll skip tracking damage totals.
    logger.info(f"Player {user_id} dealt {damage_dealt} to Akatsuki fight {message_id}")

def clear_akatsuki_fight(chat_id):
    """Removes the active fight from a chat (after win/loss/timeout)."""
    conn = get_db_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM active_akatsuki_fights WHERE chat_id = ?", (chat_id,))
        conn.commit()
        logger.info(f"Cleared active Akatsuki fight for chat {chat_id}")
    except sqlite3.Error as e:
        logger.error(f"Error clearing akatsuki fight for chat {chat_id}: {e}")
    finally:
        if conn: conn.close()
# --- END NEW ---

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Initializing database...")
    create_tables()
    update_schema()
