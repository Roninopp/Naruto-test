import redis
import json
import logging
import datetime # <--- IMPORTANT IMPORT

logger = logging.getLogger(__name__)

# --- NEW: Custom JSON converter ---
class DateTimeEncoder(json.JSONEncoder):
    """Converts datetime objects to strings for JSON."""
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        return super().default(obj)
# --- END NEW ---

# --- Redis Connection ---
try:
    redis_conn = redis.Redis(decode_responses=True)
    redis_conn.ping()
    logger.info("Successfully connected to Redis.")
except redis.exceptions.ConnectionError as e:
    logger.error(f"Could not connect to Redis: {e}")
    logger.error("Please ensure Redis server is installed and running.")
    redis_conn = None

# --- Cache Functions ---

def set_player_cache(user_id, player_data):
    """Saves a player's data (as a dict) to the Redis cache."""
    if not redis_conn:
        return
        
    try:
        # --- THIS IS THE FIX ---
        # Use the new DateTimeEncoder to handle timestamps
        json_data = json.dumps(player_data, cls=DateTimeEncoder)
        redis_conn.set(f"player:{user_id}", json_data, ex=3600)
        # --- END OF FIX ---
    except Exception as e:
        logger.error(f"Failed to set cache for player {user_id}: {e}")

def get_player_cache(user_id):
    """Tries to get a player's data from the Redis cache."""
    if not redis_conn:
        return None
        
    try:
        cached_data = redis_conn.get(f"player:{user_id}")
        if cached_data:
            logger.info(f"CACHE HIT for player {user_id}")
            return json.loads(cached_data)
        
        logger.info(f"CACHE MISS for player {user_id}")
        return None
    except Exception as e:
        logger.error(f"Failed to get cache for player {user_id}: {e}")
        return None

def clear_player_cache(user_id):
    """Deletes a player's data from cache (when it's updated)."""
    if not redis_conn:
        return
        
    try:
        redis_conn.delete(f"player:{user_id}")
        logger.info(f"CACHE CLEARED for player {user_id}")
    except Exception as e:
        logger.error(f"Failed to clear cache for player {user_id}: {e}")

def flush_all_cache():
    """Wipes the ENTIRE Redis cache clean."""
    if not redis_conn: return False
    try:
        redis_conn.flushdb()
        logger.info("⚠️ ALL REDIS CACHE FLUSHED ⚠️")
        return True
    except Exception as e:
        logger.error(f"Failed to flush Redis: {e}")
        return False
