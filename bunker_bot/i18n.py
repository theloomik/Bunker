import json
import os
from .settings import logger, LANG_FILE
from .database import get_server_lang

LANGUAGES = {}

def load_languages():
    global LANGUAGES
    if not os.path.exists(LANG_FILE):
        logger.critical(f"{LANG_FILE} not found.")
        return

    with open(LANG_FILE, "r", encoding="utf-8") as f:
        try:
            LANGUAGES = json.load(f)
            logger.info("Languages loaded successfully.")
        except json.JSONDecodeError as e:
            logger.critical(f"Failed to parse {LANG_FILE}: {e}")

def T(key: str, ctx_or_lang, **kwargs):
    """
    Get localized string.
    ctx_or_lang: can be 'uk'/'en' string OR interaction/context object
    """
    lang = "uk"
    if isinstance(ctx_or_lang, str):
        lang = ctx_or_lang
    elif hasattr(ctx_or_lang, "guild") and ctx_or_lang.guild:
        lang = get_server_lang(ctx_or_lang.guild.id)
    
    # Default to Ukrainian if language not found
    data = LANGUAGES.get(lang, LANGUAGES.get("uk", {}))
    
    keys = key.split(".")
    for k in keys:
        if isinstance(data, dict) and k in data:
            data = data[k]
        else:
            # Fallback to UK
            data = LANGUAGES.get("uk", {})
            for fk in keys:
                if isinstance(data, dict) and fk in data: 
                    data = data[fk]
                else: 
                    return f"[{key}]" # Missing key indicator
            break
    
    if isinstance(data, str):
        try:
            return data.format(**kwargs)
        except Exception as e:
            logger.error(f"Formatting error for key '{key}': {e}")
            return data
    return data

# Initial load
load_languages()