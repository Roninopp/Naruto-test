import redis
import json
import logging

logger = logging.getLogger(__name__)

# --- Redis Connection ---
# This connects to a standard Redis install on the same machine.
# decode_responses=True makes it return strings instead of bytes.
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
        # We store the player's dict as a JSON string
        # We set an expiration of 1 hour (3600 seconds)
        # This auto-clears old data.
        redis_conn.set(f"player:{user_id}", json.dumps(player_data), ex=3600)
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
            # Convert the JSON string back into a Python dict
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
