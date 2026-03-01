from pathlib import Path

import datetime as dt
import logging
import os

logger = logging.getLogger(__name__)

def setup_logging():
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_DIR = os.getenv("LOG_DIR", "logs")
    LOG_DIR = Path(dt.datetime.today().strftime(f"{LOG_DIR}/%Y-%m-%d"))
    
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)

    console_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(os.path.join(LOG_DIR, "run.log"))

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s') # Common format
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    logger.info("Logger is set up.")