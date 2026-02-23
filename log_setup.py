import os
import logging

logger = logging.getLogger(__name__)

def setup_logging():
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Logger is set up.")