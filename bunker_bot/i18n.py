import json
import os
import asyncio
from .settings import logger, LANG_FILE
from .database import get_server_lang

# Global dictionary initialized once
LANGUAGES = {}

async def load_languages():
    """Asynchronously load language data from disk into the global dict."""
    if not os.path.exists(LANG_FILE):
        logger.critical(f"{LANG_FILE} not found.")
        return

    def _read():
        with open(LANG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    try:
        data = await asyncio.to_thread(_read)
        # FIX: Update existing dictionary instead of reassigning variable
        # This ensures imports in other files see the changes
        LANGUAGES.clear()
        LANGUAGES.update(data)
        logger.info(f"Languages loaded successfully. Available: {list(LANGUAGES.keys())}")
    except json.JSONDecodeError as e:
        logger.critical(f"Failed to parse {LANG_FILE}: {e}")
    except Exception as e:
        logger.critical(f"Error loading languages: {e}")

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
    
    # Try to get data for the requested language
    # Default to UK if language itself is missing from file
    data = LANGUAGES.get(lang, LANGUAGES.get("uk", {}))
    
    keys = key.split(".")
    
    for k in keys:
        if isinstance(data, dict) and k in data:
            data = data[k]
        else:
            # Key missing in target language
            if lang != "uk":
                logger.warning(f"Translation missing for key '{key}' in language '{lang}', falling back to UK")
            
            # Fallback to UK (Default)
            data = LANGUAGES.get("uk", {})
            for fk in keys:
                if isinstance(data, dict) and fk in data: 
                    data = data[fk]
                else: 
                    return f"[{key}]" # Missing key even in default language
            break
    
    if isinstance(data, str):
        try:
            return data.format(**kwargs)
        except Exception as e:
            logger.error(f"Formatting error for key '{key}': {e}")
            return data
    return data