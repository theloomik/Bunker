# ☢️ Bunker Discord Bot

Bunker is a feature-rich, fully interactive Discord bot that facilitates the popular social deduction board game "The Bunker" (also known as Lifeboat).

Players are generated with random characteristics (Job, Health, Phobia, Inventory, etc.) and must survive an apocalypse. The catch? The bunker has limited spots. Convince others that you are useful, reveal your traits strategically, and vote to decide who gets left behind.

## ✨ Key Features

🎮 **Interactive UI:** No more command spam! The game is controlled entirely via Buttons and Dropdown Menus (Selects).

📊 **Live Dashboard:** A pinned message that updates in real-time, showing the bunker status, lore, and living players.

👑 **Host System:** The player who creates the lobby becomes the Host, managing the game flow (Start, Voting, Cancellation).

🌍 **Multi-Language Support:** Fully localized (currently supports English and Ukrainian). Easy to add new languages via languages.json.

💾 **Persistence & Stats:**  Global player profiles with stats (Games, Wins, Deaths, Winrate).


## 🧠 Smart Game Logic:

Lore Generation: Random catastrophes, bunker types, and conditions every game.

Voting System: Includes double elimination logic for draws.

Endings: The bot analyzes the surviving team (Doctors, Engineers, Military) and writes a story conclusion.

## 🛠️ Installation

Prerequisites

Python 3.9 or higher

A Discord Bot Token (from Discord Developer Portal)

Setup Steps

Clone the repository:

```
git clone https://github.com/LooMik4332/bunker.git
cd bunker
```

Install dependencies:

```
pip install discord.py
```

Configure the bot:
Create a file named config.json in the root folder and paste your token:

```
{
    "token": "YOUR_DISCORD_BOT_TOKEN_HERE"
}
```

Run the bot:

```
python bunker.py
```

## 🚀 How to Play

### **1. Lobby**

Use /create [players] to open a lobby.


<img width="298" height="106" alt="зображення" src="https://github.com/user-attachments/assets/83fd74c6-60f1-43b6-84c8-0ecb6667f408" />

Users click Join.


<img width="332" height="227" alt="зображення" src="https://github.com/user-attachments/assets/31c415af-650a-441d-958a-2b5b249f7327" />

The Host clicks Start Game once the lobby is full.


<img width="358" height="225" alt="зображення" src="https://github.com/user-attachments/assets/7cbcaf05-a7ee-437e-8cc6-2a67d9054a26" />


### **2. The Game**

<img width="276" height="504" alt="зображення" src="https://github.com/user-attachments/assets/3f6e8a5c-c668-4c77-a0cf-3b8e95aec5bc" />


Dashboard: A persistent message appears with buttons:

📂 **My Profile:** Check your secret stats (Ephemerally).

📢 **Reveal:** Show specific cards to everyone.

📖 **Guide:** Read about specific traits/diseases.

🔴 **Start Vote (Host only).**

**Gameplay:** Players discuss, reveal traits, and argue their case.

### **3. Voting**

The Host starts the vote via the Dashboard.

Players select who to exile via a Dropdown menu.

If there is a draw, a Double Elimination round occurs next.

### **4. Ending**

When the number of survivors matches the bunker spots, the game ends.

The bot generates an ending story based on the professions and health status of the survivors.

## 📂 Project Structure

bunker.py - The main bot logic (Game loop, UI, Commands).

languages.json - Localization file containing all text strings, game data (jobs, phobias), and lore.

users.json - Auto-generated database for player stats.

config.json - Configuration file for the bot token (needs to be created).

## 🌍 Adding a Language

Open languages.json.

Copy the "en" block.

Paste it as a new key (e.g., "es" for Spanish).

Translate the values.

The bot will automatically detect the new language in the /language command!

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the issues page.
>>>>>>> 49378058ad98f0b261431b06cfa00cbb881021b0
