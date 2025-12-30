import random
import asyncio
import discord
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Any
import logging
import math

from .settings import logger, GAME_DB_FILE
from .i18n import T
from .database import get_user_data, update_user_stats, update_server_games, save_raw_active_games

# Global games registry: {guild_id: GameState}
games: Dict[int, 'GameState'] = {}

class SaveManager:
    """
    Handles game state persistence with debouncing to prevent
    disk I/O thrashing and race conditions.
    """
    _save_scheduled = False
    _lock = asyncio.Lock()

    @classmethod
    async def request(cls) -> None:
        """Schedules a save operation in the near future (Debounce).
        
        If a save is already scheduled, this call returns immediately to group
        multiple updates into a single write operation.
        """
        if cls._save_scheduled:
            return
        
        cls._save_scheduled = True
        # Wait a bit to collect concurrent updates (e.g. rapid voting)
        await asyncio.sleep(2.0)
        
        await cls.force()
        cls._save_scheduled = False

    @classmethod
    async def force(cls) -> None:
        """Immediately serializes and saves all active games to disk.
        
        This method uses a lock to ensure thread safety during the write operation.
        """
        async with cls._lock:
            # 1. Serialize Synchronously (Atomic operation in asyncio)
            # This prevents state from mutating while we are preparing data
            try:
                data = {str(gid): game.to_dict() for gid, game in games.items()}
            except Exception as e:
                logger.error(f"Serialization Error in SaveManager: {e}")
                return

            # 2. Write Asynchronously (Thread-safe via database.py)
            await save_raw_active_games(data)

class GamePhase(Enum):
    """Enum representing the current phase of the game."""
    WAITING = 1
    REVEAL = 2
    VOTING = 3
    FINISHED = 4

class Player:
    """Represents a single player in the game."""
    def __init__(self, user_id: int, discord_name: str, lang: str):
        self.user_id = user_id
        self.lang = lang
        u = get_user_data(user_id)
        self.name = u["name"] if u["name"] else discord_name
        self.alive = True
        self.cards: Dict[str, str] = {}
        self.opened: Dict[str, bool] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "lang": self.lang,
            "alive": self.alive,
            "cards": self.cards,
            "opened": self.opened
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Player':
        p = cls(data["user_id"], data["name"], data["lang"])
        p.alive = data["alive"]
        p.cards = data["cards"]
        p.opened = data["opened"]
        return p

    def generate(self) -> None:
        D = T("data", self.lang)
        H_Dict = T("health", self.lang)
        P_Dict = T("phobias", self.lang)
        
        h_keys = list(H_Dict.keys()) if isinstance(H_Dict, dict) else ["Healthy"]
        p_keys = list(P_Dict.keys()) if isinstance(P_Dict, dict) else ["None"]

        self.cards = {
            "sex": D["sexes"][random.randint(0, 1)],
            "age": str(random.randint(18, 90)),
            "height": str(random.randint(150, 210)) + " cm",
            "body": random.choice(D["bodies"]),
            "job": random.choice(D["jobs"]),
            "health": random.choice(h_keys),
            "hobby": random.choice(D["hobbies"]),
            "phobia": random.choice(p_keys),
            "inventory": random.choice(D["inventory"]),
            "extra": random.choice(D["extra"]),
        }
        self.opened = {k: False for k in self.cards}

    def get_profile_text(self, show_hidden: bool = False) -> str:
        lines = []
        titles = T("card_titles", self.lang)
        for key, title in titles.items():
            value = self.cards.get(key, "???")
            is_open = self.opened.get(key, False)
            status = "✅" if is_open or show_hidden else "🔒"
            val_text = value if is_open or show_hidden else "???"
            lines.append(f"{status} **{title}**: {val_text}")
        return "\n".join(lines)

class GameState:
    """Manages the state of a single game session."""
    def __init__(self, max_players: int, host_id: int, lang: str, guild_id: int):
        self.max_players = max_players
        self.host_id = host_id
        self.lang = lang
        self.guild_id = guild_id
        self.players: List[Player] = []
        self.phase = GamePhase.WAITING
        self.bunker_spots = 0 
        self.lore_text = "" 
        self.votes: Dict[int, List[int]] = {} 
        self.double_elim_next = False
        
        self.board_msg_id: Optional[int] = None
        self.dash_msg_id: Optional[int] = None
        self.channel_id: Optional[int] = None

        self.board_message: Optional[discord.Message] = None
        self.dashboard_view: Optional[discord.ui.View] = None
        self.join_view: Optional[discord.ui.View] = None 

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_players": self.max_players,
            "host_id": self.host_id,
            "lang": self.lang,
            "guild_id": self.guild_id,
            "phase": self.phase.value,
            "bunker_spots": self.bunker_spots,
            "lore_text": self.lore_text,
            "votes": self.votes,
            "double_elim_next": self.double_elim_next,
            "board_msg_id": self.board_msg_id,
            "dash_msg_id": self.dash_msg_id,
            "channel_id": self.channel_id,
            "players": [p.to_dict() for p in self.players]
        }

    @classmethod
    def from_dict(cls, guild_id: int, data: Dict[str, Any]) -> 'GameState':
        g = cls(data["max_players"], data["host_id"], data["lang"], guild_id)
        g.phase = GamePhase(data["phase"])
        g.bunker_spots = data["bunker_spots"]
        g.lore_text = data["lore_text"]
        g.votes = {int(k): [int(uid) for uid in v] for k, v in data["votes"].items()}
        g.double_elim_next = data["double_elim_next"]
        g.board_msg_id = data.get("board_msg_id")
        g.dash_msg_id = data.get("dash_msg_id")
        g.channel_id = data.get("channel_id")
        g.players = [Player.from_dict(p_data) for p_data in data["players"]]
        return g

    def validate(self) -> bool:
        """Validates the consistency of the loaded game state."""
        try:
            if not isinstance(self.players, list):
                return False
            
            alive = sum(1 for p in self.players if p.alive)
            if alive < 0 or alive > len(self.players):
                return False
                
            known_ids = {p.user_id for p in self.players}
            for voter_id, targets in self.votes.items():
                if voter_id not in known_ids:
                    return False
                if not isinstance(targets, list):
                    return False
                for target_id in targets:
                    if target_id not in known_ids:
                        return False
            return True
        except Exception as e:
            logger.warning(f"Validation failed for guild {self.guild_id}: {e}")
            return False

    def add_player(self, user_id: int, name: str) -> bool:
        if len(self.players) >= self.max_players: return False
        if any(p.user_id == user_id for p in self.players): return False
        
        self.players.append(Player(user_id, name, self.lang))
        logger.debug(f"Player {user_id} added to game in guild {self.guild_id}")
        
        asyncio.create_task(SaveManager.request())
        return True

    def get_player(self, user_id: int) -> Optional[Player]:
        return next((p for p in self.players if p.user_id == user_id), None)

    def alive_players(self) -> List[Player]:
        return [p for p in self.players if p.alive]

    async def start_game(self) -> None:
        logger.info(f"Starting game in guild {self.guild_id}")
        count = len(self.players)
        self.bunker_spots = max(1, math.ceil(count / 2))
        
        await update_server_games(self.guild_id)
        D = T("data", self.lang)
        
        for p in self.players: 
            p.generate()
            sex_idx = 0 if p.cards['sex'] == D["sexes"][0] else 1
            await update_user_stats(p.user_id, "game_start", {"age": int(p.cards['age']), "sex_idx": sex_idx})
        
        self.lore_text = f"{random.choice(D['catastrophes'])}\n\n**Loc**: {random.choice(D['bunker_types'])}\n**Cond**: {random.choice(D['supplies'])}\n⏳ {random.choice(D['durations'])}"
        self.phase = GamePhase.REVEAL
        asyncio.create_task(SaveManager.request())

    async def end_game(self, bot: commands.Bot) -> None:
        logger.info(f"Ending game in guild {self.guild_id}")
        self.phase = GamePhase.FINISHED
        
        if self.dashboard_view:
            self.dashboard_view.stop()
        if self.join_view:
            self.join_view.stop()

        if self.channel_id:
            try:
                ch = bot.get_channel(self.channel_id)
                if not ch: 
                    try: ch = await bot.fetch_channel(self.channel_id)
                    except: pass
                
                if ch:
                    # Clean Dashboard
                    if self.dash_msg_id:
                        try:
                            msg = await ch.fetch_message(self.dash_msg_id)
                            await msg.delete()
                        except (discord.NotFound, discord.Forbidden): pass
                        except discord.HTTPException as e:
                            if e.status == 429: logger.warning(f"Guild {self.guild_id}: Rate limited deleting dashboard: {e}")
                            else: logger.error(f"Guild {self.guild_id}: HTTP error deleting dashboard: {e}")
                        except Exception as e: logger.error(f"Guild {self.guild_id}: Unexpected error cleaning dashboard: {e}")
                    
                    # Clean Status Board
                    if self.board_msg_id:
                        try:
                            msg = await ch.fetch_message(self.board_msg_id)
                            await msg.delete()
                        except (discord.NotFound, discord.Forbidden): pass
                        except discord.HTTPException as e:
                            if e.status == 429: logger.warning(f"Guild {self.guild_id}: Rate limited deleting board: {e}")
                            else: logger.error(f"Guild {self.guild_id}: HTTP error deleting board: {e}")
                        except Exception as e: logger.error(f"Guild {self.guild_id}: Unexpected error cleaning board: {e}")
            except Exception as e:
                logger.warning(f"Guild {self.guild_id}: Channel cleanup error (channel likely missing): {e}")
        
        self.players.clear()
        self.votes.clear()
        self.board_message = None
        self.dashboard_view = None
        self.join_view = None

        if self.guild_id in games:
            del games[self.guild_id]
            asyncio.create_task(SaveManager.force())

    async def register_vote(self, user_id: int, targets: List[int]) -> None:
        self.votes[user_id] = [int(t) for t in targets]
        logger.debug(f"User {user_id} voted in guild {self.guild_id}")
        asyncio.create_task(SaveManager.request())

    def resolve_votes(self) -> Tuple[List[Player], str, bool]:
        alive_ids = {p.user_id for p in self.alive_players()}
        active_votes = {k: v for k, v in self.votes.items() if k in alive_ids}

        tally = {uid: 0 for uid in alive_ids}
        for vs in active_votes.values():
            for v in vs: 
                if v in tally: tally[v] += 1
        
        results = sorted(tally.items(), key=lambda x: x[1], reverse=True)
        if not results: return [], "No votes", False
        
        max_v = results[0][1]
        candidates = [uid for uid, c in results if c == max_v]
        
        eliminated = []
        text = ""
        is_draw = False

        if self.double_elim_next:
            self.double_elim_next = False
            to_kick = list(candidates)
            if len(to_kick) < 2 and len(results) > len(to_kick):
                second_max = results[len(to_kick)][1]
                second_tier = [uid for uid, c in results if c == second_max]
                to_kick.extend(second_tier)
            
            random.shuffle(to_kick)
            for uid in to_kick[:2]:
                p = self.get_player(uid)
                if p and p.alive: eliminated.append(p)
            text = T("msg.crit_round", self.lang)
        else:
            if len(candidates) > 1:
                self.double_elim_next = True
                self.phase = GamePhase.REVEAL
                self.votes.clear()
                is_draw = True
            else:
                p = self.get_player(candidates[0])
                if p and p.alive: eliminated.append(p)
                text = T("msg.majority_decision", self.lang)
        
        asyncio.create_task(SaveManager.request())
        return eliminated, text, is_draw

    def calculate_ending(self) -> str:
        E = T("endings", self.lang)
        return E["neutral"]

    def generate_board_embed(self) -> discord.Embed:
        if self.phase == GamePhase.FINISHED:
            return discord.Embed(title=T("ui.win_title", self.lang), color=discord.Color.purple())

        embed = discord.Embed(title="📊 BUNKER DASHBOARD", color=discord.Color.dark_teal())
        
        host_lbl = T('ui.host_label', self.lang)
        pl_lbl = T('ui.players_label', self.lang)
        places_lbl = T('ui.places_label', self.lang)
        kick_lbl = T('ui.kick_label', self.lang)

        info = (f"{host_lbl} <@{self.host_id}>\n"
                f"👥 {pl_lbl} **{len(self.players)}**\n"
                f"🚪 {places_lbl} **{self.bunker_spots}**\n"
                f"☠️ {kick_lbl} **{len(self.players) - self.bunker_spots}**")
        
        embed.add_field(name="📋 Info", value=info, inline=False)

        ptxt = ""
        titles = T("card_titles", self.lang)
        for p in self.players:
            status = "🟢" if p.alive else "💀"
            if not p.alive:
                ptxt += f"{status} ~~{p.name}~~\n\n"
                continue
            
            revealed = [f"> **{titles.get(k, k)}**: {v}" for k,v in p.cards.items() if p.opened.get(k)]
            ptxt += f"{status} **{p.name}**\n" + ("\n".join(revealed) if revealed else "> *???*") + "\n\n"

        if len(ptxt) > 1024: ptxt = ptxt[:1020] + "..."
        embed.add_field(name="Players", value=ptxt, inline=False)
        return embed

    async def update_board(self, bot: commands.Bot) -> None:
        if not self.channel_id or not self.board_msg_id: return
        
        if not self.board_message:
            try:
                ch = bot.get_channel(self.channel_id)
                if ch: 
                    self.board_message = await ch.fetch_message(self.board_msg_id)
                else:
                    logger.warning(f"Guild {self.guild_id}: Channel not found for update_board.")
                    return
            except discord.NotFound:
                logger.warning(f"Guild {self.guild_id}: Board message not found.")
                self.board_msg_id = None
                return
            except discord.Forbidden:
                logger.warning(f"Guild {self.guild_id}: Permission denied for board update.")
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    logger.warning(f"Guild {self.guild_id}: Rate limited fetching board msg. Retry in {e.retry_after:.2f}s")
                else:
                    logger.error(f"Guild {self.guild_id}: HTTP error fetching board msg: {e}")
                return
            except Exception as e:
                logger.error(f"Guild {self.guild_id}: Fetch error in update_board: {e}")
                return

        if self.board_message:
            try: 
                await self.board_message.edit(embed=self.generate_board_embed())
            except discord.NotFound:
                logger.warning(f"Guild {self.guild_id}: Board message deleted during edit.")
                self.board_message = None
                self.board_msg_id = None
            except discord.HTTPException as e:
                if e.status == 429:
                    logger.warning(f"Guild {self.guild_id}: Rate limited editing board. Retry in {e.retry_after:.2f}s")
                else:
                    logger.error(f"Guild {self.guild_id}: HTTP error editing board: {e}")
            except Exception as e:
                logger.error(f"Guild {self.guild_id}: Edit error in update_board: {e}")

# --- Exposed functions ---
async def save_active_games() -> None:
    await SaveManager.request()

async def delete_active_game(guild_id: int) -> None:
    if guild_id in games:
        del games[guild_id]
        await SaveManager.force()

async def load_active_games_from_disk() -> None:
    if not os.path.exists(GAME_DB_FILE): return
    try:
        from .database import load_raw_active_games
        data = await load_raw_active_games()
        recovered = 0
        for gid_str, g_data in data.items():
            gid = int(gid_str)
            try:
                game = GameState.from_dict(gid, g_data)
                if game.validate():
                    games[gid] = game
                    recovered += 1
                else:
                    logger.warning(f"Skipping corrupted game state for guild {gid}")
            except Exception as e:
                logger.error(f"Failed to recover game {gid}: {e}")
        logger.info(f"Recovered {recovered} games from disk.")
    except Exception as e:
        logger.error(f"Game Load Error: {e}")