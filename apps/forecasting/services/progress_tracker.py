import json
import logging
from django.conf import settings
import redis

logger = logging.getLogger(__name__)


def _get_redis_client():
    try:
        return redis.from_url(settings.CELERY_BROKER_URL)
    except Exception as e:
        logger.warning(f"Redis unavailable for progress tracking: {e}")
        return None


def update_run_progress(run_id: int, current: int, total: int, message: str):
    """Store epoch-level progress in Redis."""
    r = _get_redis_client()
    if not r:
        return
    
    payload = {
        'current': current,
        'total': total,
        'message': message,
        'percent': int((current / total) * 100) if total > 0 else 0
    }
    
    try:
        # Expire after 2 hours to prevent memory leaks
        r.setex(f"forecast_run:{run_id}:progress", 7200, json.dumps(payload))
    except Exception as e:
        logger.error(f"Failed to write progress to Redis: {e}")


def get_run_progress(run_id: int) -> dict:
    """Retrieve current progress from Redis."""
    r = _get_redis_client()
    if not r:
        return {'current': 0, 'total': 0, 'percent': 0, 'message': 'Initializing...'}
        
    try:
        data = r.get(f"forecast_run:{run_id}:progress")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.error(f"Failed to read progress from Redis: {e}")
        
    return {'current': 0, 'total': 0, 'percent': 0, 'message': 'Waiting for worker...'}


def clear_run_progress(run_id: int):
    """Remove progress key after completion."""
    r = _get_redis_client()
    if r:
        try:
            r.delete(f"forecast_run:{run_id}:progress")
        except Exception:
            pass