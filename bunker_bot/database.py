import json
import os
import asyncio
from .settings import logger, DB_FILE

_user_db_lock = asyncio.Lock()

# In-memory cache
global_db = {"users": {}, "servers": {}}

async def load_user_db():
    global global_db
    if not os.path.exists(DB_FILE):
        await save_user_db_data({"users": {}, "servers": {}})
        return {"users": {}, "servers": {}}
    
    try:
        async with _user_db_lock:
            def read():
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            data = await asyncio.to_thread(read)
            
            # Migration check
            if "users" not in data: 
                global_db = {"users": data, "servers": {}}
            else:
                global_db = data
            return global_db
    except Exception as e:
        logger.error(f"User DB Load Error: {e}")
        return {"users": {}, "servers": {}}

async def save_user_db_data(data):
    try:
        async with _user_db_lock:
            def write():
                with open(DB_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
            await asyncio.to_thread(write)
    except Exception as e:
        logger.error(f"User DB Write Error: {e}")

# --- Synchronous Accessors (reading from cache) ---
def get_server_lang(guild_id: int) -> str:
    gid = str(guild_id)
    return global_db["servers"].get(gid, {}).get("lang", "uk")

def get_server_stats(guild_id: int) -> int:
    gid = str(guild_id)
    return global_db["servers"].get(gid, {}).get("games_played", 0)

def get_user_data(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in global_db["users"]:
        global_db["users"][uid] = {
            "name": None, "games": 0, "wins": 0, "deaths": 0,
            "total_age": 0, "sex_stats": {"m": 0, "f": 0}
        }
    u = global_db["users"][uid]
    # Ensure keys exist
    if "total_age" not in u: u["total_age"] = 0
    if "sex_stats" not in u: u["sex_stats"] = {"m": 0, "f": 0}
    return u

# --- Async Modifiers (writing to disk) ---
async def set_server_lang(guild_id: int, lang: str):
    gid = str(guild_id)
    if gid not in global_db["servers"]: global_db["servers"][gid] = {}
    global_db["servers"][gid]["lang"] = lang
    await save_user_db_data(global_db)

async def update_user_stats(user_id: int, key: str, val=1):
    u = get_user_data(user_id)
    if key == "game_start" and isinstance(val, dict):
        u["games"] += 1
        u["total_age"] += val.get("age", 0)
        sex_key = "m" if val.get("sex_idx") == 0 else "f"
        u["sex_stats"][sex_key] += 1
    elif key in u:
        u[key] += val
    await save_user_db_data(global_db)

async def update_server_games(guild_id: int):
    gid = str(guild_id)
    if gid not in global_db["servers"]: global_db["servers"][gid] = {}
    srv = global_db["servers"][gid]
    srv["games_played"] = srv.get("games_played", 0) + 1
    await save_user_db_data(global_db)

async def set_custom_name(user_id: int, name: str):
    u = get_user_data(user_id)
    u["name"] = name
    await save_user_db_data(global_db)