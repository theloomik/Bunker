# ☢️ **Bunker Discord Bot**

Bunker is a feature-rich, fully interactive Discord bot that facilitates the popular social deduction board game "The Bunker" (also known as Lifeboat).

Players are generated with random characteristics (Job, Health, Phobia, Inventory, etc.) and must survive an apocalypse. The catch? The bunker has limited spots. Convince others that you are useful, reveal your traits strategically, and vote to decide who gets left behind.

## 🛠️ **Installation**

### Prerequisites

* Python 3.9 or higher.
* A Discord Bot Token (from [Discord Developer Portal](https://discord.com/developers/applications))

### Setup Steps
* Clone the repository:
```
git clone https://github.com/theloomik/bunker.git
cd bunker
```

* Install dependencies:
```
pip install -r requirements.txt
```

* Configure the bot:
Create a file named config.json in the root folder and paste your token:
```
{
    "token": "YOUR_DISCORD_BOT_TOKEN_HERE"
}
```

* Run the bot:
```
python run.py
```

## 🚀 **How to Play**

### 1. Lobby

Use /create [players] to open a lobby.
Users click Join.
The Host clicks Start Game once the lobby is full.

### 2. The Game

Dashboard: A persistent message appears with buttons:
* 📂 My Profile: Check your secret stats (Ephemerally).
* 📢 Reveal: Show specific cards to everyone.
* 📖 Guide: Read about specific traits/diseases.
* 🔴 Start Vote: (Host only).
* Gameplay: Players discuss, reveal traits, and argue their case.

### 3. Voting

The Host starts the vote via the Dashboard.
Players select who to exile via a Dropdown menu.
If there is a draw, a Double Elimination round occurs next.

### 4. Ending

When the number of survivors matches the bunker spots, the game ends.
The bot generates an ending story based on the professions and health status of the survivors.

## 📂 Project Structure
```
root/
├── run.py                  # Entry point script
├── config.json             # Bot Token (Hidden)
├── languages.json          # Localization strings (EN/UK)
├── bunker_bot/             # Main Package
│   ├── main.py             # Bot initialization & Commands
│   ├── game.py             # Core Game Logic & State Management
│   ├── ui.py               # Discord Views (Buttons, Selects, Modals)
│   ├── database.py         # Thread-safe JSON Database Handler
│   ├── settings.py         # Config loading & Logging setup
│   └── i18n.py             # Translation Helper
├── users.json              # Player stats database (Auto-generated)
├── active_games.json       # Game state recovery file (Auto-generated)
└── bunker.log              # Error logs (Auto-generated)
```
## 🌍 Adding a Language

Open languages.json.
Copy the "en" block.
Paste it as a new key (e.g., "es" for Spanish).
Translate the values.
The bot will automatically detect the new language in the /language command!

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the issues page.

## 📜 License

This project is licensed under the MIT License.
