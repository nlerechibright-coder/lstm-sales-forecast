"""
Task execution abstraction layer.

Provides a unified interface for running background tasks (training, forecasting)
that works both synchronously (local dev) and asynchronously (Celery in production).

To switch to Celery later:
  1. Set CELERY_BROKER_URL and CELERY_RESULT_BACKEND in settings
  2. Remove the sync fallback logic below, or set CELERY_SYNC_MODE=False
  3. Start a Celery worker process
  4. No changes needed in views, services, or tasks

Architecture contract:
  - Views call run_task(task_func, *args, **kwargs)
  - run_task decides sync vs async based on environment
  - Services remain pure Python with no knowledge of execution context
  - Tasks remain @shared_task decorated Celery tasks
"""
import os
import logging
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

# Environment toggle: 'true' = force sync, 'false' = try Celery first
CELERY_SYNC_MODE = os.environ.get('CELERY_SYNC_MODE', '').lower() in ('1', 'true', 'yes')


def run_task(task_func: Callable, *args, **kwargs) -> dict:
    """
    Execute a Celery-backed task function.

    Priority:
      1. If CELERY_SYNC_MODE env var is set → run synchronously
      2. If Celery broker is healthy → queue via .delay()
      3. If Celery broker is down → fall back to synchronous

    Returns:
        {
            'async': bool,           # True if queued to Celery, False if ran sync
            'task_id': str|None,     # Celery task ID (if async)
            'result': Any|None,      # Direct return value (if sync)
            'message': str,          # Human-readable status
        }
    """
    task_name = getattr(task_func, '__name__', str(task_func))

    # Force sync mode via environment
    if CELERY_SYNC_MODE:
        logger.info(f"[{task_name}] CELERY_SYNC_MODE active — running synchronously.")
        return _execute_sync(task_func, *args, **kwargs)

    # Attempt Celery async
    try:
        result = task_func.delay(*args, **kwargs)
        logger.info(f"[{task_name}] Queued via Celery. Task ID: {result.id}")
        return {
            'async': True,
            'task_id': result.id,
            'result': None,
            'message': f'{task_name} queued in background.',
        }
    except Exception as exc:
        logger.warning(
            f"[{task_name}] Celery unavailable ({type(exc).__name__}: {exc}). "
            f"Falling back to synchronous execution."
        )
        return _execute_sync(task_func, *args, **kwargs)


def _execute_sync(task_func: Callable, *args, **kwargs) -> dict:
    """
    Run the underlying task function directly, bypassing Celery.
    This unwraps the @shared_task decorator and calls the raw function.
    """
    task_name = getattr(task_func, '__name__', str(task_func))

    # Celery @shared_task wraps the function; .run gives us the raw callable
    raw_func = getattr(task_func, 'run', task_func)

    try:
        result = raw_func(*args, **kwargs)
        logger.info(f"[{task_name}] Completed synchronously.")
        return {
            'async': False,
            'task_id': None,
            'result': result,
            'message': f'{task_name} completed synchronously.',
        }
    except Exception as exc:
        logger.error(f"[{task_name}] Failed during synchronous execution: {exc}")
        raise