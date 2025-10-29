import sqlite3
import logging
import game_logic 
import cache

logger = logging.getLogger(__name__)

DATABASE_FILE = 'ninja_rpg.db'

# --- NEW: Schema Update Function ---
def update_schema():
    """Checks and updates the DB schema with new columns if they don't exist."""
    conn = get_db_connection()
    if conn is None:
        return

    try:
        cursor = conn.cursor()
        
        # Get list of columns in the 'players' table
        cursor.execute("PRAGMA table_info(players);")
        columns = [row['name'] for row in cursor.fetchall()]

        # Check for and add 'equipment' column
        if 'equipment' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN equipment TEXT DEFAULT '{}';")
            logger.info("Database Schema UPDATED: Added 'equipment' column.")
            
        # Check for and add 'inventory' column
        if 'inventory' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN inventory TEXT DEFAULT '[]';")
            logger.info("Database Schema UPDATED: Added 'inventory' column.")

        # Check for and add 'discovered_combinations' (from original schema)
        if 'discovered_combinations' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN discovered_combinations TEXT DEFAULT '[]';")
            logger.info("Database Schema UPDATED: Added 'discovered_combinations' column.")
            
        # --- FIX: Add training limit columns ---
        if 'daily_train_count' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN daily_train_count INTEGER DEFAULT 0;")
            logger.info("Database Schema UPDATED: Added 'daily_train_count' column.")
        
        if 'last_train_reset_date' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN last_train_reset_date TEXT DEFAULT NULL;")
            logger.info("Database Schema UPDATED: Added 'last_train_reset_date' column.")
        # --- END FIX ---
            
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error updating database schema: {e}")
    finally:
        conn.close()


def get_db_connection():
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error connecting to database: {e}")
        return None

def create_tables():
    """Creates the database tables if they don't already exist."""
    conn = get_db_connection()
    if conn is None:
        return

    try:
        cursor = conn.cursor()
        
        # Players Table (now with new columns)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
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
            known_jutsus TEXT DEFAULT '[]',
            discovered_combinations TEXT DEFAULT '[]',
            ryo INTEGER DEFAULT 100,
            rank TEXT DEFAULT 'Academy Student',
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            battle_cooldown TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            equipment TEXT DEFAULT '{}',
            inventory TEXT DEFAULT '[]',
            daily_train_count INTEGER DEFAULT 0,
            last_train_reset_date TEXT DEFAULT NULL
        );
        """)
        
        # Other tables
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS jutsu_discoveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            combination TEXT UNIQUE,
            jutsu_name TEXT,
            discovered_by TEXT,
            discovered_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS battle_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player1_id INTEGER,
            player2_id INTEGER,
            winner_id INTEGER,
            battle_log TEXT,
            duration_seconds INTEGER,
            fought_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # --- PROTECC MODULE TABLES ---
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS protecc_spotlight (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)
        cursor.execute("INSERT OR IGNORE INTO protecc_spotlight (key, value) VALUES ('current_character', NULL);")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS protecc_collection (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            character_name TEXT NOT NULL,
            rarity TEXT NOT NULL,
            first_collected_at TEXT DEFAULT CURRENT_TIMESTAMP,
            times_collected INTEGER DEFAULT 1,
            UNIQUE(user_id, character_name)
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS protecc_stats (
            user_id INTEGER PRIMARY KEY,
            total_collected INTEGER DEFAULT 0,
            unique_collected INTEGER DEFAULT 0,
            total_ryo_earned INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES players (user_id)
        );
        """)
        
        # --- NEW: TABLE FOR ENABLED CHATS ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS protecc_enabled_chats (
            chat_id INTEGER PRIMARY KEY,
            enabled_by_user_id INTEGER,
            enabled_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # --- END OF NEW TABLES ---
        
        conn.commit()
        logger.info("Database tables checked/created successfully.")
        
    except sqlite3.Error as e:
        logger.error(f"Error creating tables: {e}")
    finally:
        conn.close()

def get_player(user_id):
    """
    Fetches a player's data.
    First, it tries the cache. If not found, it gets from SQLite.
    Returns a DICTIONARY.
    """
    
    cached_player = cache.get_player_cache(user_id)
    if cached_player:
        if 'equipment' in cached_player:
            return cached_player
        else:
            cache.clear_player_cache(user_id)
            
    conn = get_db_connection()
    if conn is None:
        return None
        
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
    """Creates a new player in the database."""
    conn = get_db_connection()
    if conn is None:
        return False
        
    try:
        base_stats = {
            'strength': 10, 'speed': 10, 'intelligence': 10, 'stamina': 10
        }
        initial_stats = game_logic.distribute_stats(base_stats, 0)
        
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO players 
            (user_id, username, village, max_hp, current_hp, max_chakra, current_chakra, 
             strength, speed, intelligence, stamina, equipment, inventory,
             daily_train_count, last_train_reset_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, village, 
             initial_stats['max_hp'], initial_stats['max_hp'],
             initial_stats['max_chakra'], initial_stats['max_chakra'],
             initial_stats['strength'], initial_stats['speed'], 
             initial_stats['intelligence'], initial_stats['stamina'],
             '{}', '[]',
             0, None)
        )
        
        cursor.execute(
            "INSERT OR IGNORE INTO protecc_stats (user_id, total_collected, unique_collected, total_ryo_earned) VALUES (?, 0, 0, 0)",
            (user_id,)
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
    """
    Dynamically updates a player's data in the database
    AND clears the cache.
    """
    conn = get_db_connection()
    if conn is None:
        return False

    try:
        set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values())
        values.append(user_id)
        
        query = f"UPDATE players SET {set_clause} WHERE user_id = ?"
        
        cursor = conn.cursor()
        cursor.execute(query, tuple(values))
        conn.commit()
        
        logger.info(f"Player {user_id} updated in DB: {updates.keys()}")
        
        cache.clear_player_cache(user_id)
        return True
    except sqlite3.Error as e:
        logger.error(f"Error updating player {user_id}: {e}")
        return False
    finally:
        conn.close()

# --- Specific Database functions for Protecc ---

def get_protecc_stats(user_id):
    """Fetches a player's collection stats."""
    conn = get_db_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM protecc_stats WHERE user_id = ?", (user_id,))
        stats_row = cursor.fetchone()
        return dict(stats_row) if stats_row else None
    except sqlite3.Error as e:
        logger.error(f"Error fetching protecc_stats for {user_id}: {e}")
        return None
    finally:
        conn.close()

def get_player_collection(user_id):
    """Fetches all collected characters for a player."""
    conn = get_db_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT character_name, rarity, times_collected FROM protecc_collection WHERE user_id = ? ORDER BY rarity", (user_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.error(f"Error fetching protecc_collection for {user_id}: {e}")
        return []
    finally:
        conn.close()

def get_current_spotlight():
    """Gets the currently posted character from the DB."""
    conn = get_db_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM protecc_spotlight WHERE key = 'current_character'")
        row = cursor.fetchone()
        if row and row['value']:
            return json.loads(row['value'])
        return None
    except sqlite3.Error as e:
        logger.error(f"Error getting current_spotlight: {e}")
        return None
    finally:
        conn.close()

def update_current_spotlight(character_data):
    """Saves the new character to the DB."""
    conn = get_db_connection()
    if conn is None: return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE protecc_spotlight SET value = ? WHERE key = 'current_character'", (json.dumps(character_data),))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error updating current_spotlight: {e}")
    finally:
        conn.close()

# --- NEW: Functions for enabled chats ---

def enable_protecc_chat(chat_id, user_id):
    """Adds a chat to the enabled list."""
    conn = get_db_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO protecc_enabled_chats (chat_id, enabled_by_user_id) VALUES (?, ?)", (chat_id, user_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error enabling protecc for chat {chat_id}: {e}")
        return False
    finally:
        conn.close()

def get_all_protecc_chats():
    """Gets a list of all chat IDs where protecc is enabled."""
    conn = get_db_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM protecc_enabled_chats")
        rows = cursor.fetchall()
        return [row['chat_id'] for row in rows] # Return a simple list of IDs
    except sqlite3.Error as e:
        logger.error(f"Error getting all protecc chats: {e}")
        return []
    finally:
        conn.close()
# --- END OF NEW FUNCTIONS ---


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Initializing database...")
    create_tables()
    update_schema() # Also update schema when run directly
