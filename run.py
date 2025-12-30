import asyncio
import os
import sys

# Додаємо поточну папку в шлях пошуку модулів
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from bunker_bot.main import run
except ImportError as e:
    print("❌ Critical Error: Could not import bot modules.")
    print(f"Details: {e}")
    print("Make sure you are running 'python run.py' from the root folder.")
    sys.exit(1)

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user.")