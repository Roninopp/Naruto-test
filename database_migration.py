"""
🚀 DATABASE MIGRATION SCRIPT
Run this ONCE to add new minigame fields to your database!

Usage: python database_migration.py
"""

import psycopg2
import psycopg2.pool
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = "postgresql://neondb_owner:npg_ZBiVmpx5rCR6@ep-fragrant-feather-a4eur7c4-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

def migrate_database():
    """Add new fields for advanced minigame system."""
    
    conn = psycopg2.connect(DATABASE_URL)
    
    new_columns = [
        # BOUNTY SYSTEM
        ('bounty', 'INTEGER DEFAULT 0'),  # Current bounty on player's head
        ('total_bounty_earned', 'INTEGER DEFAULT 0'),  # Total bounty collected lifetime
        
        # HEAT SYSTEM
        ('heat_level', 'INTEGER DEFAULT 0'),  # Criminal heat (0-100)
        ('last_heat_decay', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),  # For automatic decay
        
        # REPUTATION SYSTEM
        ('reputation_points', 'INTEGER DEFAULT 0'),  # Overall reputation score
        ('reputation_title', 'TEXT DEFAULT NULL'),  # Current title
        ('total_steals', 'INTEGER DEFAULT 0'),  # Successful robberies
        ('total_steals_caught', 'INTEGER DEFAULT 0'),  # Failed robberies
        ('total_scouts', 'INTEGER DEFAULT 0'),  # Scout missions done
        ('total_heals_given', 'INTEGER DEFAULT 0'),  # Players healed
        ('total_gifts_given', 'INTEGER DEFAULT 0'),  # Gifts sent
        ('total_protections_bought', 'INTEGER DEFAULT 0'),  # Protections purchased
        
        # CONTRACT SYSTEM
        ('active_contracts', 'JSONB DEFAULT \'[]\'::jsonb'),  # Contracts on this player
        ('contracts_completed', 'INTEGER DEFAULT 0'),  # Contracts fulfilled
        
        # LOOT SYSTEM
        ('legendary_items', 'JSONB DEFAULT \'[]\'::jsonb'),  # Special items owned
        
        # ESCAPE SYSTEM
        ('total_escapes', 'INTEGER DEFAULT 0'),  # Successful escapes
        ('escape_cooldown', 'TIMESTAMP DEFAULT NULL'),  # Escape attempt cooldown
    ]
    
    # CREATE CONTRACT TABLE
    contract_table = """
    CREATE TABLE IF NOT EXISTS player_contracts (
        id SERIAL PRIMARY KEY,
        target_user_id BIGINT NOT NULL,
        placed_by_user_id BIGINT NOT NULL,
        placed_by_username TEXT NOT NULL,
        reward BIGINT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        is_active INTEGER DEFAULT 1
    );
    """
    
    try:
        with conn.cursor() as cursor:
            # Add new columns to players table
            for col_name, col_type in new_columns:
                try:
                    cursor.execute(f"ALTER TABLE players ADD COLUMN IF NOT EXISTS {col_name} {col_type};")
                    logger.info(f"✅ Added column: {col_name}")
                except Exception as e:
                    logger.warning(f"⚠️ Column {col_name} might already exist: {e}")
            
            # Create contracts table
            cursor.execute(contract_table)
            logger.info("✅ Created player_contracts table")
            
            conn.commit()
            logger.info("🎉 DATABASE MIGRATION COMPLETE!")
            logger.info("🚀 Your minigames are now SUPERCHARGED!")
            
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    print("🔥 Starting Database Migration...")
    migrate_database()
    print("✅ Done! You can now use the new minigames.py")
