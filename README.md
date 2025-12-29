☢️ BUNKER — Discord Game Bot

BUNKER is an interactive Discord game bot based on the social survival board game “Bunker”.
Players receive unique characters, reveal information step by step, debate, vote, and decide who will survive and enter the bunker.

This bot is designed as a full game experience, not just a command-based bot.

🎮 Core Concept

A global catastrophe has destroyed the world.

A bunker can save only a limited number of people.
Each player has a randomly generated character with strengths and weaknesses.

Through discussion, strategy, and voting, players must decide:

Who deserves to survive

Who must be excluded

The game continues until only the required number of survivors remains.

✨ Key Features
🔘 Button-Based Gameplay

No command spam

No confusing syntax

Almost all actions are handled via interactive buttons

One dynamic game board message that updates in real time

👑 Host / Curator System

The player who creates the game becomes the Host

Only the Host can:

start the game

control voting phases

end or reset the game

Prevents chaos and keeps the game structured

🧍 Player Profiles

Each player has a unique character with attributes such as:

Gender

Age

Body type

Profession & experience

Health condition

Phobia

Hobbies

Inventory

Extra traits

Profiles are private and can be viewed using /profile.

Players can also set a custom in-game name, which is used instead of their Discord nickname.

📇 Card Reveal System

Players decide which cards to reveal and when

Cards are revealed via buttons

Revealed information is visible to everyone

Unrevealed information remains secret

This creates tension and strategic decision-making.

🗳️ Advanced Voting System

Voting is fully automated

Players cannot vote for themselves

Eliminated players cannot vote

Tie logic:

First tie → nobody is eliminated

Next round → double elimination

Voting results are calculated automatically

☢️ Bunker Lore System

Each game starts with a randomly generated scenario, such as:

Type of global catastrophe

Condition of the bunker

Duration of survival

Available resources

This adds atmosphere and affects how players argue their usefulness.

🧠 Game Phases

The game progresses through clear phases:

Lobby (players join)

Character generation

Information reveal

Voting rounds

Final survivors & ending

Each phase restricts available actions to prevent exploits.

🧾 Commands

Only two slash commands exist:

/create

Creates a new game

Assigns the Host

Starts the lobby phase

/profile

Shows your private character profile

Allows setting a custom in-game name

Displays player statistics

Everything else is handled via buttons.

🛠️ Technical Notes

Written in Python using discord.py

Clean, readable architecture

Game logic separated from Discord UI logic

Single-file structure (by design, easy to refactor later)

Designed for stability and extensibility

🚀 Planned / Optional Enhancements

Expanded lore with gameplay impact

Random events between rounds

Deeper explanations for traits (phobias, body types, health)

Post-game story / epilogue

Persistent player statistics

Public bot release

🏁 Project Status

✔ Fully playable
✔ Stable core mechanics
✔ Clean UI & UX
✔ Designed for real players

This project is not a prototype — it is a complete game with room for growth.

📜 License

Private project (for now).
Public release may follow in the future.
