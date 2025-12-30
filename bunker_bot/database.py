import json
import os
import asyncio
import shutil
from typing import Dict, Any
from .settings import logger, DB_FILE, GAME_DB_FILE

_user_db_lock = asyncio.Lock()
_game_db_lock = asyncio.Lock()

# In-memory cache for users
global_db: Dict[str, Any] = {"users": {}, "servers": {}}

# --- HELPER ---
def _load_json_file(filepath: str) -> Dict[str, Any]:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

# --- USER STATS OPERATIONS ---

async def load_user_db() -> Dict[str, Any]:
    global global_db
    if not os.path.exists(DB_FILE):
        await save_user_db_data({"users": {}, "servers": {}})
        return {"users": {}, "servers": {}}
    
    try:
        async with _user_db_lock:
            def read_primary():
                return _load_json_file(DB_FILE)
            
            try:
                data = await asyncio.to_thread(read_primary)
            except Exception as e:
                logger.error(f"Primary User DB corrupt: {e}. Attempting backup recovery...")
                
                # Attempt Backup Recovery
                if os.path.exists(f"{DB_FILE}.backup"):
                    def read_backup():
                        return _load_json_file(f"{DB_FILE}.backup")
                    try:
                        data = await asyncio.to_thread(read_backup)
                        logger.info("Recovered User DB from backup!")
                    except Exception as backup_e:
                        logger.critical(f"Backup User DB also corrupt: {backup_e}. Starting fresh.")
                        data = {"users": {}, "servers": {}}
                else:
                    logger.error("No User DB backup found. Starting fresh.")
                    data = {"users": {}, "servers": {}}

            # Data validation/migration
            if "users" not in data: 
                global_db = {"users": data, "servers": {}}
            else:
                global_db = data
            return global_db
    except Exception as e:
        logger.error(f"User DB Load Error: {e}")
        return {"users": {}, "servers": {}}

async def save_user_db_data(data: Dict[str, Any]) -> None:
    try:
        async with _user_db_lock:
            def write():
                # Create backup before overwrite
                if os.path.exists(DB_FILE):
                    try:
                        shutil.copy2(DB_FILE, f"{DB_FILE}.backup")
                    except Exception as e:
                        logger.warning(f"Failed to create User DB backup: {e}")

                with open(DB_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
            await asyncio.to_thread(write)
    except Exception as e:
        logger.error(f"User DB Write Error: {e}")

# --- ACTIVE GAMES OPERATIONS (RAW JSON) ---

async def save_raw_active_games(data_dict: Dict[str, Any]) -> None:
    """Saves the dictionary of active games to JSON file."""
    try:
        async with _game_db_lock:
            def write():
                # Create backup before overwrite
                if os.path.exists(GAME_DB_FILE):
                    try:
                        shutil.copy2(GAME_DB_FILE, f"{GAME_DB_FILE}.backup")
                    except Exception as e:
                        logger.warning(f"Failed to create Game DB backup: {e}")

                with open(GAME_DB_FILE, "w", encoding="utf-8") as f:
                    json.dump(data_dict, f, ensure_ascii=False, indent=4)
            await asyncio.to_thread(write)
    except Exception as e:
        logger.error(f"Game DB Save Error: {e}")

async def load_raw_active_games() -> Dict[str, Any]:
    """Loads raw JSON data for active games."""
    if not os.path.exists(GAME_DB_FILE):
        return {}
    
    try:
        async with _game_db_lock:
            def read_primary():
                return _load_json_file(GAME_DB_FILE)

            try:
                return await asyncio.to_thread(read_primary)
            except Exception as e:
                logger.error(f"Primary Game DB corrupt: {e}. Attempting backup recovery...")
                
                # Attempt Backup Recovery
                if os.path.exists(f"{GAME_DB_FILE}.backup"):
                    def read_backup():
                        return _load_json_file(f"{GAME_DB_FILE}.backup")
                    try:
                        data = await asyncio.to_thread(read_backup)
                        logger.info("Recovered Game DB from backup!")
                        return data
                    except Exception as backup_e:
                        logger.critical(f"Backup Game DB also corrupt: {backup_e}.")
                        return {}
                else:
                    logger.error("No Game DB backup found.")
                    return {}

    except Exception as e:
        logger.error(f"Game DB Load Error: {e}")
        return {}

# --- ACCESSORS ---

def get_server_lang(guild_id: int) -> str:
    gid = str(guild_id)
    return global_db["servers"].get(gid, {}).get("lang", "uk")

def get_server_stats(guild_id: int) -> int:
    gid = str(guild_id)
    return global_db["servers"].get(gid, {}).get("games_played", 0)

def get_user_data(user_id: int) -> Dict[str, Any]:
    uid = str(user_id)
    if uid not in global_db["users"]:
        global_db["users"][uid] = {
            "name": None, "games": 0, "wins": 0, "deaths": 0,
            "total_age": 0, "sex_stats": {"m": 0, "f": 0}
        }
    u = global_db["users"][uid]
    if "total_age" not in u: u["total_age"] = 0
    if "sex_stats" not in u: u["sex_stats"] = {"m": 0, "f": 0}
    return u

async def set_server_lang(guild_id: int, lang: str) -> None:
    gid = str(guild_id)
    if gid not in global_db["servers"]: global_db["servers"][gid] = {}
    global_db["servers"][gid]["lang"] = lang
    await save_user_db_data(global_db)

async def update_user_stats(user_id: int, key: str, val: Any = 1) -> None:
    u = get_user_data(user_id)
    if key == "game_start" and isinstance(val, dict):
        u["games"] += 1
        u["total_age"] += val.get("age", 0)
        sex_key = "m" if val.get("sex_idx") == 0 else "f"
        u["sex_stats"][sex_key] += 1
    elif key in u:
        u[key] += val
    await save_user_db_data(global_db)

async def reset_user_stats(user_id: int) -> None:
    u = get_user_data(user_id)
    u["games"] = 0
    u["wins"] = 0
    u["deaths"] = 0
    u["total_age"] = 0
    u["sex_stats"] = {"m": 0, "f": 0}
    await save_user_db_data(global_db)

async def update_server_games(guild_id: int) -> None:
    gid = str(guild_id)
    if gid not in global_db["servers"]: global_db["servers"][gid] = {}
    srv = global_db["servers"][gid]
    srv["games_played"] = srv.get("games_played", 0) + 1
    await save_user_db_data(global_db)

async def set_custom_name(user_id: int, name: str) -> None:
    u = get_user_data(user_id)
    u["name"] = name
    await save_user_db_data(global_db)