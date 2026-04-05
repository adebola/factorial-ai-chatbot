import os
import sys
import logging
from loguru import logger


def setup_logging(log_level: str = None):
    logger.remove()
    level = log_level or os.environ.get("LOG_LEVEL", "INFO")
    environment = os.environ.get("ENVIRONMENT", "development")

    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True
    )
    logging.getLogger("aio_pika").setLevel(getattr(logging, level, logging.INFO))
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    if environment == "production":
        logger.add(sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            colorize=False, level=level)
    else:
        logger.add(sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | {message}",
            colorize=True, level=level)


def get_logger(name: str = None):
    return logger.bind(module=name or "audit-service")
