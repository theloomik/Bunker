import os
import json
import logging
from logging.handlers import RotatingFileHandler

# =========================
#  LOGGING SETUP
# =========================
def setup_logging():
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    file_handler = RotatingFileHandler("bunker.log", maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
    file_handler.setFormatter(log_formatter)
    
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(log_formatter)
    
    logger = logging.getLogger("bunker_bot")
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger

logger = setup_logging()

# =========================
#  CONFIG LOADER
# =========================
if not os.path.exists("config.json"):
    # Fallback/Create default if missing to prevent immediate crash during dev
    with open("config.json", "w") as f:
        json.dump({"token": ""}, f)
    logger.warning("config.json created. Please fill in the token.")

with open("config.json", "r") as f:
    try:
        CONFIG = json.load(f)
    except json.JSONDecodeError:
        CONFIG = {}
        logger.critical("config.json is invalid JSON.")

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN") or CONFIG.get("token")

# =========================
#  CONSTANTS
# =========================
DB_FILE = "users.json"
GAME_DB_FILE = "active_games.json"
LANG_FILE = "languages.json"