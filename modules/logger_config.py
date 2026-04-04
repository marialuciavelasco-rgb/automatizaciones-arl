import sys
from pathlib import Path
from loguru import logger
from datetime import datetime

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

def setup_logger():
    logger.remove()

    # Consola: simple y legible
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO",
        colorize=True,
    )

    # Archivo diario
    log_file = LOG_DIR / f"arl_{datetime.now().strftime('%Y-%m-%d')}.log"
    logger.add(
        str(log_file),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {function}:{line} | {message}",
        level="DEBUG",
        rotation="1 day",
        retention="30 days",
        encoding="utf-8",
    )

    return logger


setup_logger()
