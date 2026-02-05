"""
Redis distributed locking utility for scheduled jobs.

This module provides a distributed locking mechanism using Redis to prevent
duplicate job execution when multiple billing-service instances are running.
"""
import logging
from contextlib import contextmanager
from typing import Generator
import redis
import os

logger = logging.getLogger(__name__)

# Initialize Redis client
redis_client = None

def get_redis_client() -> redis.Redis:
    """
    Get or create Redis client instance.

    Returns:
        Redis client instance
    """
    global redis_client

    if redis_client is None:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        redis_client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        logger.info(f"Redis client initialized: {redis_url}")

    return redis_client


@contextmanager
def distributed_lock(
    lock_name: str,
    timeout: int = 3600,
    blocking: bool = False,
    blocking_timeout: int = 1
) -> Generator[bool, None, None]:
    """
    Acquire a distributed lock for scheduled jobs.

    This context manager ensures that only one instance of a scheduled job
    runs across multiple service instances. Uses Redis for coordination.

    Args:
        lock_name: Unique name for the lock (e.g., "check_trial_expirations")
        timeout: Lock expiration time in seconds (default: 3600 = 1 hour)
        blocking: Whether to wait for lock if already held (default: False)
        blocking_timeout: Max seconds to wait if blocking=True (default: 1)

    Yields:
        bool: True if lock was acquired, False if another instance holds it

    Example:
        >>> with distributed_lock("my_job") as acquired:
        ...     if not acquired:
        ...         logger.info("Job already running on another instance")
        ...         return
        ...     # Job logic here
    """
    client = get_redis_client()
    full_lock_name = f"job_lock:{lock_name}"
    lock = None
    acquired = False

    try:
        # Create Redis lock
        lock = client.lock(
            full_lock_name,
            timeout=timeout,
            blocking=blocking,
            blocking_timeout=blocking_timeout
        )

        # Try to acquire lock
        acquired = lock.acquire(blocking=blocking, blocking_timeout=blocking_timeout)

        if acquired:
            logger.info(f"✅ Acquired distributed lock: {lock_name}")
        else:
            logger.info(f"⏭️  Lock already held by another instance: {lock_name}")

        yield acquired

    except redis.exceptions.RedisError as e:
        logger.error(f"❌ Redis error acquiring lock '{lock_name}': {e}")
        # Fail open - allow job to run if Redis is unavailable
        # This prevents Redis outages from blocking all job execution
        yield True

    except Exception as e:
        logger.exception(f"❌ Unexpected error with lock '{lock_name}': {e}")
        # Fail open
        yield True

    finally:
        # Release lock if we acquired it
        if acquired and lock is not None:
            try:
                lock.release()
                logger.debug(f"Released distributed lock: {lock_name}")
            except Exception as e:
                logger.warning(f"Failed to release lock '{lock_name}': {e}")


def check_redis_connection() -> bool:
    """
    Check if Redis connection is healthy.

    Returns:
        bool: True if Redis is reachable, False otherwise
    """
    try:
        client = get_redis_client()
        client.ping()
        logger.info("✅ Redis connection healthy")
        return True
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        return False


def clear_lock(lock_name: str) -> bool:
    """
    Manually clear a lock (use with caution).

    This should only be used for debugging or emergency situations where
    a lock is stuck due to an unexpected service crash.

    Args:
        lock_name: Name of the lock to clear

    Returns:
        bool: True if lock was cleared, False otherwise
    """
    try:
        client = get_redis_client()
        full_lock_name = f"job_lock:{lock_name}"
        result = client.delete(full_lock_name)
        if result:
            logger.warning(f"⚠️  Manually cleared lock: {lock_name}")
            return True
        else:
            logger.info(f"Lock '{lock_name}' does not exist")
            return False
    except Exception as e:
        logger.error(f"Failed to clear lock '{lock_name}': {e}")
        return False
