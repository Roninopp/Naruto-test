# ... (all the imports and other functions are the same) ...
import sqlite3
import logging
import game_logic
import cache
import json

logger = logging.getLogger(__name__)

DATABASE_FILE = 'ninja_rpg.db'

# --- NEW: Schema Update Function ---
def update_schema():
    # ... (code is the same) ...
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

        if 'daily_train_count' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN daily_train_count INTEGER DEFAULT 0;")
            logger.info("Database Schema UPDATED: Added 'daily_train_count' column.")

        if 'last_train_reset_date' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN last_train_reset_date TEXT DEFAULT NULL;")
            logger.info("Database Schema UPDATED: Added 'last_train_reset_date' column.")

        # --- NEW: World Boss Cooldown Column ---
        if 'boss_attack_cooldown' not in columns:
            cursor.execute("ALTER TABLE players ADD COLUMN boss_attack_cooldown TEXT DEFAULT NULL;")
            logger.info("Database Schema UPDATED: Added 'boss_attack_cooldown' column.")
        # --- END NEW ---

        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error updating database schema: {e}")
    finally:
        conn.close()


def get_db_connection():
    # ... (code is the same) ...
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error connecting to database: {e}")
        return None

def create_tables():
    # ... (code is the same for players, jutsu_discoveries, battle_history) ...
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
            last_train_reset_date TEXT DEFAULT NULL,
            boss_attack_cooldown TEXT DEFAULT NULL  -- NEW: Cooldown column
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

        # --- NEW: WORLD BOSS MODULE TABLES ---

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS world_boss_enabled_chats (
            chat_id INTEGER PRIMARY KEY,
            enabled_by_user_id INTEGER,
            enabled_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS world_boss_status (
            chat_id INTEGER PRIMARY KEY,
            is_active INTEGER DEFAULT 0,
            boss_key TEXT,
            current_hp INTEGER,
            max_hp INTEGER,
            ryo_pool INTEGER,
            spawn_time TEXT
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS world_boss_damage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            total_damage INTEGER DEFAULT 0,
            UNIQUE(chat_id, user_id)
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
    # ... (code is the same) ...
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
    # ... (code is the same) ...
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
             daily_train_count, last_train_reset_date, boss_attack_cooldown) -- NEW: Added cooldown
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, village,
             initial_stats['max_hp'], initial_stats['max_hp'],
             initial_stats['max_chakra'], initial_stats['max_chakra'],
             initial_stats['strength'], initial_stats['speed'],
             initial_stats['intelligence'], initial_stats['stamina'],
             '{}', '[]',
             0, None, None) # NEW: Default value for cooldown
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
    # ... (code is the same) ...
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


# --- NEW: World Boss DB Functions ---

def enable_boss_chat(chat_id, user_id):
    """Adds a chat to the enabled list for world boss."""
    conn = get_db_connection()
    if conn is None: return False
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO world_boss_enabled_chats (chat_id, enabled_by_user_id) VALUES (?, ?)", (chat_id, user_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error enabling world_boss for chat {chat_id}: {e}")
        return False
    finally:
        conn.close()

# --- THIS FUNCTION WAS MISSING OR INCORRECT IN YOUR FILE ---
def get_all_boss_chats():
    """Gets a list of all chat IDs where world_boss is enabled."""
    conn = get_db_connection()
    if conn is None: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM world_boss_enabled_chats")
        rows = cursor.fetchall()
        return [row['chat_id'] for row in rows] # Return a simple list of IDs
    except sqlite3.Error as e:
        logger.error(f"Error getting all world_boss chats: {e}")
        return []
    finally:
        conn.close()
# --- END FIX ---

def get_boss_status(chat_id):
    """Gets the current boss status for a specific chat."""
    conn = get_db_connection()
    if conn is None: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM world_boss_status WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        else:
            # If no row exists, create one
            cursor.execute("INSERT INTO world_boss_status (chat_id, is_active) VALUES (?, 0)", (chat_id,))
            conn.commit()
            return {'chat_id': chat_id, 'is_active': 0, 'boss_key': None, 'current_hp': 0, 'max_hp': 0, 'ryo_pool': 0, 'spawn_time': None}

    except sqlite3.Error as e:
        logger.error(f"Error getting boss status for chat {chat_id}: {e}")
        return None
    finally:
        # !!! IMPORTANT FIX: Added conn.close() here !!!
        if conn:
            conn.close()

# --- END NEW ---

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Initializing database...")
    create_tables()
    update_schema() # Also update schema when run directly
