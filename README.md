☢️ Bunker Discord Bot

Bunker is a feature-rich, fully interactive Discord bot that facilitates the popular social deduction board game "The Bunker" (also known as Lifeboat).

Players are generated with random characteristics (Job, Health, Phobia, Inventory, etc.) and must survive an apocalypse. The catch? The bunker has limited spots. Convince others that you are useful, reveal your traits strategically, and vote to decide who gets left behin

🛠️ Installation

Prerequisites: Python 3.9 or higher
A Discord Bot Token (from Discord Developer Portal)

Setup Steps

Clone the repository:

git clone https://github.com/theloomik/bunker.git
cd bunker

Install dependencies:

pip install discord.py

Configure the bot: Create a file named config.json in the root folder and paste your token:

{
    "token": "YOUR_DISCORD_BOT_TOKEN_HERE"
}

Run the bot:

python bunker.py
