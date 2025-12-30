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
    with open("config.json", "w") as f:
        json.dump({"token": ""}, f)

with open("config.json", "r") as f:
    try:
        CONFIG = json.load(f)
    except json.JSONDecodeError:
        CONFIG = {}

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN") or CONFIG.get("token")

# =========================
#  CONSTANTS
# =========================
DB_FILE = "users.json"
GAME_DB_FILE = "active_games.json"
LANG_FILE = "languages.json"

# Timeouts (in seconds)
LOBBY_TIMEOUT = 3600        # 1 hour
DASHBOARD_TIMEOUT = 7200    # 2 hours
VOTE_TIMEOUT = 600          # 10 minutes
EPHEMERAL_VIEW_TIMEOUT = 180 # 3 minutes

# Message Lifetimes (in seconds)
BRIEF_MSG_LIFETIME = 3
ANNOUNCEMENT_LIFETIME = 15
RESULT_MSG_LIFETIME = 20