"""SQLite lock retry helpers for long-running workers."""

import time
from functools import wraps

from django.db.utils import OperationalError

from config.logger_utils import get_logger


logger = get_logger(__name__)


def is_db_locked_error(exc: BaseException) -> bool:
    error_str = str(exc).lower()
    return "database is locked" in error_str or "locked" in error_str


def retry_on_db_lock(max_retries=10, base_delay=0.05, max_delay=5.0):
    """Retry a function on SQLite 'database is locked' errors."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except OperationalError as exc:
                    if not is_db_locked_error(exc):
                        raise
                    last_exception = exc
                    if attempt < max_retries - 1:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        jitter = base_delay * 0.1 * (attempt + 1)
                        logger.warning(
                            "[retry_on_db_lock] %s attempt %s/%s, retry in %.3fs",
                            func.__name__,
                            attempt + 1,
                            max_retries,
                            delay + jitter,
                        )
                        time.sleep(delay + jitter)
                    else:
                        logger.error(
                            "[retry_on_db_lock] %s failed after %s attempts",
                            func.__name__,
                            max_retries,
                        )
            if last_exception:
                raise last_exception
            return None

        return wrapper

    return decorator
