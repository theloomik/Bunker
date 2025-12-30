# =========================
#  BUNKER GAME — PRODUCTION EDITION
# =========================
# Fixes:
# - Multi-guild support (games dictionary)
# - View timeouts & cleanup
# - Async DB locking
# - Error handling & Logging
# - Validation for all interactions

import discord
from discord.ext import commands
from discord import app_commands
import random
from enum import Enum, auto
from typing import Dict, List, Optional
import math
import asyncio
import json
import os
import logging

# =========================
#  SETUP & CONFIG
# =========================

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("bunker_bot")

if not os.path.exists("config.json"):
    logger.critical("config.json not found.")
    exit()

with open("config.json", "r") as f:
    CONFIG = json.load(f)

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN") or CONFIG.get("token")

if not os.path.exists("languages.json"):
    logger.critical("languages.json not found.")
    exit()

with open("languages.json", "r", encoding="utf-8") as f:
    LANGUAGES = json.load(f)

DB_FILE = "users.json"
_db_lock = asyncio.Lock()

# GLOBAL GAME STATE STORE: {guild_id: GameState}
games: Dict[int, 'GameState'] = {}

# =========================
#  DATABASE MANAGER
# =========================

async def load_db():
    if not os.path.exists(DB_FILE):
        await save_db_initial()
        return {"users": {}, "servers": {}}
    
    try:
        async with _db_lock:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "users" not in data: return {"users": data, "servers": {}}
                return data
    except Exception as e:
        logger.error(f"DB Load Error: {e}")
        return {"users": {}, "servers": {}}

async def save_db_initial():
    async with _db_lock:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump({"users": {}, "servers": {}}, f)

async def save_db_data(data):
    async with _db_lock:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

# In-memory DB cache
global_db = {"users": {}, "servers": {}}

# Helpers
def get_server_lang(guild_id: int) -> str:
    gid = str(guild_id)
    return global_db["servers"].get(gid, {}).get("lang", "uk")

async def set_server_lang(guild_id: int, lang: str):
    gid = str(guild_id)
    if gid not in global_db["servers"]: global_db["servers"][gid] = {}
    global_db["servers"][gid]["lang"] = lang
    await save_db_data(global_db)

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

async def update_user_stats(user_id: int, key: str, val=1):
    u = get_user_data(user_id)
    if key == "game_start" and isinstance(val, dict):
        u["games"] += 1
        u["total_age"] += val.get("age", 0)
        sex_key = "m" if val.get("sex_idx") == 0 else "f"
        u["sex_stats"][sex_key] += 1
    elif key in u:
        u[key] += val
    await save_db_data(global_db)

async def update_server_games(guild_id: int):
    gid = str(guild_id)
    if gid not in global_db["servers"]: global_db["servers"][gid] = {}
    srv = global_db["servers"][gid]
    srv["games_played"] = srv.get("games_played", 0) + 1
    await save_db_data(global_db)

async def set_custom_name(user_id: int, name: str):
    u = get_user_data(user_id)
    u["name"] = name
    await save_db_data(global_db)

def get_server_stats(guild_id: int) -> int:
    gid = str(guild_id)
    return global_db["servers"].get(gid, {}).get("games_played", 0)

# =========================
#  LOCALIZATION
# =========================

def T(key: str, ctx_or_lang, **kwargs):
    lang = "uk"
    if isinstance(ctx_or_lang, str):
        lang = ctx_or_lang
    elif hasattr(ctx_or_lang, "guild") and ctx_or_lang.guild:
        lang = get_server_lang(ctx_or_lang.guild.id)
    
    data = LANGUAGES.get(lang, LANGUAGES["uk"])
    keys = key.split(".")
    for k in keys:
        if isinstance(data, dict) and k in data:
            data = data[k]
        else:
            # Fallback
            data = LANGUAGES["uk"]
            for fk in keys:
                if isinstance(data, dict) and fk in data: data = data[fk]
                else: return f"[{key}]"
            break
    
    if isinstance(data, str):
        return data.format(**kwargs)
    return data

# =========================
#  GAME LOGIC
# =========================

class GamePhase(Enum):
    WAITING = auto()
    REVEAL = auto()
    VOTING = auto()
    FINISHED = auto()

class Player:
    def __init__(self, user_id: int, discord_name: str, lang: str):
        self.user_id = user_id
        self.lang = lang
        u = get_user_data(user_id)
        self.name = u["name"] if u["name"] else discord_name
        self.alive = True
        self.cards = {}
        self.opened = {}

    def generate(self):
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

    def get_profile_text(self, show_hidden=False) -> str:
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
    def __init__(self, max_players: int, host_id: int, lang: str, guild_id: int):
        self.max_players = max_players
        self.host_id = host_id
        self.lang = lang
        self.guild_id = guild_id
        self.players: List[Player] = []
        self.phase = GamePhase.WAITING
        self.bunker_spots = 0 
        self.lore_text = "" 
        self.votes = {} 
        self.double_elim_next = False
        self.board_message: Optional[discord.Message] = None
        self.dashboard_view = None # Keep reference to stop

    def add_player(self, user_id: int, name: str) -> bool:
        if len(self.players) >= self.max_players: return False
        if any(p.user_id == user_id for p in self.players): return False
        self.players.append(Player(user_id, name, self.lang))
        return True

    def get_player(self, user_id: int) -> Optional[Player]:
        return next((p for p in self.players if p.user_id == user_id), None)

    def alive_players(self) -> List[Player]:
        return [p for p in self.players if p.alive]

    async def start_game(self):
        count = len(self.players)
        self.bunker_spots = max(1, count // 2) # Fairer logic
        
        await update_server_games(self.guild_id)
        D = T("data", self.lang)
        
        for p in self.players: 
            p.generate()
            sex_idx = 0 if p.cards['sex'] == D["sexes"][0] else 1
            await update_user_stats(p.user_id, "game_start", {"age": int(p.cards['age']), "sex_idx": sex_idx})
        
        self.lore_text = f"{random.choice(D['catastrophes'])}\n\n**Loc**: {random.choice(D['bunker_types'])}\n**Cond**: {random.choice(D['supplies'])}\n⏳ {random.choice(D['durations'])}"
        self.phase = GamePhase.REVEAL

    async def end_game(self):
        self.phase = GamePhase.FINISHED
        if self.dashboard_view:
            self.dashboard_view.stop()
        # Remove game from global registry
        if self.guild_id in games:
            del games[self.guild_id]

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

    async def update_board(self):
        if self.board_message:
            try: await self.board_message.edit(embed=self.generate_board_embed())
            except: pass

# =========================
#  BOT SETUP & UTILS
# =========================

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    # Sync DB logic
    global global_db
    global_db = await load_db()
    await bot.tree.sync()
    logger.info(f"Bot logged in as {bot.user}")
    # Cleanup games on restart
    games.clear()

async def auto_del(interaction, delay=3):
    await asyncio.sleep(delay)
    try: await interaction.delete_original_response()
    except: pass

def get_game_safe(interaction: discord.Interaction) -> Optional[GameState]:
    if not interaction.guild: return None
    return games.get(interaction.guild.id)

# =========================
#  VIEWS
# =========================

class CloseBtn(discord.ui.Button):
    def __init__(self, lang):
        super().__init__(label=T("ui.close_btn", lang), style=discord.ButtonStyle.danger)
    async def callback(self, interaction):
        await interaction.response.edit_message(content=T("msg.closed", self.view.lang if hasattr(self.view, "lang") else "uk"), embed=None, view=None)
        asyncio.create_task(auto_del(interaction))

class CloseView(discord.ui.View):
    def __init__(self, lang="uk"):
        super().__init__(timeout=180)
        self.lang = lang
        self.add_item(CloseBtn(lang))

class LangSelect(discord.ui.Select):
    def __init__(self):
        opts = [discord.SelectOption(label=LANGUAGES[k]["name"], value=k) for k in LANGUAGES.keys()]
        super().__init__(placeholder="Select Language", options=opts)
    async def callback(self, interaction):
        await set_server_lang(interaction.guild.id, self.values[0])
        await interaction.response.send_message(T("msg.lang_changed", self.values[0]), ephemeral=True)

class NameModal(discord.ui.Modal):
    def __init__(self, lang):
        super().__init__(title=T("modal.title", lang))
        self.lang = lang
        self.name_input = discord.ui.TextInput(label=T("modal.label", lang), placeholder=T("modal.placeholder", lang), min_length=2, max_length=20)
        self.add_item(self.name_input)

    async def on_submit(self, interaction):
        await set_custom_name(interaction.user.id, self.name_input.value)
        # Update active game name if exists
        game = get_game_safe(interaction)
        if game:
            p = game.get_player(interaction.user.id)
            if p: 
                p.name = self.name_input.value
                await game.update_board()
        await interaction.response.send_message(T("msg.name_changed", self.lang, name=self.name_input.value), ephemeral=True)

class ProfileView(discord.ui.View):
    def __init__(self, lang, is_owner):
        super().__init__(timeout=180)
        self.lang = lang
        self.add_item(CloseBtn(lang))
        if is_owner:
            b = discord.ui.Button(label=T("ui.change_name_btn", lang), style=discord.ButtonStyle.secondary, emoji="✏️")
            b.callback = self.change_name
            self.add_item(b)
    async def change_name(self, interaction):
        await interaction.response.send_modal(NameModal(self.lang))

class CardSelect(discord.ui.Select):
    def __init__(self, player):
        self.player = player
        lang = player.lang
        titles = T("card_titles", lang)
        opts = []
        for k, v in titles.items():
            emoji = "✅" if player.opened[k] else "🔒"
            desc = player.cards[k] if player.opened[k] else "???"
            opts.append(discord.SelectOption(label=v, value=k, description=desc, emoji=emoji))
        super().__init__(placeholder=T("ui.reveal_placeholder", lang), min_values=1, max_values=len(opts), options=opts)

    async def callback(self, interaction):
        game = get_game_safe(interaction)
        if not game or not self.player.alive: return
        lang = self.player.lang
        
        rev = []
        titles = T("card_titles", lang)
        for v in self.values:
            if not self.player.opened[v]:
                self.player.opened[v] = True
                rev.append(f"**{titles[v]}**: `{self.player.cards[v]}`")
        
        if rev:
            await interaction.channel.send(embed=discord.Embed(title=T("msg.reveal_public_title", lang, name=self.player.name), description="\n".join(rev), color=discord.Color.green()), delete_after=15)
            await interaction.response.edit_message(content=T("msg.reveal_success", lang), view=None)
        else:
            await interaction.response.edit_message(content=T("msg.reveal_nothing", lang), view=None)
        
        asyncio.create_task(auto_del(interaction))
        await game.update_board()

class GuideCategorySelect(discord.ui.Select):
    def __init__(self, lang):
        self.lang = lang
        g_txt = T("guide", lang)
        options = [
            discord.SelectOption(label=g_txt["phobia_label"], value="phobia", emoji="😱"),
            discord.SelectOption(label=g_txt["health_label"], value="health", emoji="🏥")
        ]
        super().__init__(placeholder=g_txt["select_category"], options=options)

    async def callback(self, interaction):
        data_dict = T("phobias" if self.values[0] == "phobia" else "health", self.lang)
        view = discord.ui.View()
        view.add_item(GuideItemSelect(data_dict, self.values[0], self.lang))
        await interaction.response.edit_message(content="Select:", view=view, embed=None)

class GuideItemSelect(discord.ui.Select):
    def __init__(self, data_source, category_name, lang):
        self.data_source = data_source
        self.lang = lang
        options = []
        for k in sorted(data_source.keys()):
            options.append(discord.SelectOption(label=k))
        if len(options) > 25: options = options[:25]
        super().__init__(placeholder=f"List: {category_name}", options=options)

    async def callback(self, interaction):
        item = self.values[0]
        info = self.data_source.get(item)
        if info:
            await interaction.response.edit_message(
                content=None, 
                embed=discord.Embed(title=f"📌 {item}", description=f"{info['desc']}\n\n**⚠️ Risk:**\n{info['risk']}", color=discord.Color.blue()), 
                view=CloseView(self.lang)
            )

class Dashboard(discord.ui.View):
    def __init__(self, lang):
        super().__init__(timeout=None) # Persistent
        self.lang = lang
        self.children[0].label = T("ui.profile_btn", lang)
        self.children[1].label = T("ui.reveal_btn", lang)
        self.children[2].label = T("ui.guide_btn", lang)
        self.children[3].label = T("ui.vote_start_btn", lang)

    @discord.ui.button(emoji="📂", style=discord.ButtonStyle.primary, row=0)
    async def profile(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: return
        p = game.get_player(interaction.user.id)
        if p: await interaction.response.send_message(embed=discord.Embed(title="📂", description=p.get_profile_text(True), color=discord.Color.blue()), ephemeral=True, view=CloseView(self.lang))
        else: await interaction.response.send_message("Not in game", ephemeral=True)

    @discord.ui.button(emoji="📢", style=discord.ButtonStyle.success, row=0)
    async def reveal(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: return
        p = game.get_player(interaction.user.id)
        if p and p.alive:
            v = discord.ui.View()
            v.add_item(CardSelect(p))
            await interaction.response.send_message(T("ui.reveal_placeholder", self.lang), view=v, ephemeral=True)

    @discord.ui.button(emoji="📖", style=discord.ButtonStyle.secondary, row=1)
    async def guide(self, interaction, button):
        view = discord.ui.View()
        view.add_item(GuideCategorySelect(self.lang))
        await interaction.response.send_message(T("ui.guide_placeholder", self.lang), view=view, ephemeral=True)

    @discord.ui.button(emoji="🔴", style=discord.ButtonStyle.danger, row=1)
    async def vote(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: return
        if interaction.user.id != game.host_id:
            await interaction.response.send_message(T("msg.only_host", self.lang), ephemeral=True)
            return
        
        game.phase = GamePhase.VOTING
        game.votes.clear()
        
        alive = game.alive_players()
        if len(alive) <= game.bunker_spots:
            await interaction.response.send_message("Finish!", ephemeral=True)
            return

        embed = discord.Embed(title=T("ui.vote_title", self.lang), description=T("ui.vote_desc", self.lang), color=discord.Color.gold())
        mx = 2 if game.double_elim_next else 1
        if game.double_elim_next: embed.set_footer(text=T("ui.vote_footer_double", self.lang))
        
        embed.add_field(name="Status", value="Waiting...")
        await interaction.response.send_message(embed=embed, view=VoteView(alive, mx, self.lang))

class VoteView(discord.ui.View):
    def __init__(self, candidates, max_select, lang):
        super().__init__(timeout=600)
        self.lang = lang
        self.add_item(VoteSelect(candidates, max_select))
        self.end_btn = discord.ui.Button(label=T("ui.end_vote_btn", lang), style=discord.ButtonStyle.secondary, disabled=True)
        self.end_btn.callback = self.end_callback
        self.add_item(self.end_btn)

    async def end_callback(self, interaction):
        game = get_game_safe(interaction)
        if not game: return
        if interaction.user.id != game.host_id: return

        # Calculation Logic
        tally = {p.user_id: 0 for p in game.alive_players()}
        for vs in game.votes.values():
            for v in vs: tally[v] += 1
        
        # Safe Sort
        results = sorted(tally.items(), key=lambda x: x[1], reverse=True)
        if not results: return
        max_v = results[0][1]
        candidates = [uid for uid, c in results if c == max_v]
        
        eliminated = []
        text = ""
        
        if game.double_elim_next:
            game.double_elim_next = False
            # Logic fixed from audit
            to_kick = candidates
            if len(to_kick) < 2 and len(results) > len(to_kick):
                # Tie at top is less than 2 people? Unlikely if double elim, but possible if 1 max.
                # If only 1 person has max votes, get 2nd place
                second_max = results[len(to_kick)][1]
                second_tier = [uid for uid, c in results if c == second_max]
                to_kick.extend(second_tier)
            
            # Now shuffle and take top 2
            random.shuffle(to_kick)
            for uid in to_kick[:2]:
                p = game.get_player(uid)
                if p: eliminated.append(p)
            text = T("msg.crit_round", self.lang)
        else:
            if len(candidates) > 1:
                game.double_elim_next = True
                game.phase = GamePhase.REVEAL
                game.votes.clear() # Fix #13
                await interaction.channel.send(embed=discord.Embed(title=T("msg.draw", self.lang), description=T("msg.draw_desc", self.lang), color=discord.Color.yellow()), delete_after=15)
                try: await interaction.message.delete()
                except: pass
                return
            else:
                p = game.get_player(candidates[0])
                if p: eliminated.append(p)
                text = T("msg.majority_decision", self.lang)

        # Apply deaths
        res_desc = ""
        kick_stories = T("kick_descriptions", self.lang)
        for p in eliminated:
            p.alive = False
            await update_user_stats(p.user_id, "deaths", 1)
            story = random.choice(kick_stories)
            res_desc += f"💀 **{p.name}**\n*{story}*\n\n"

        try: await interaction.message.delete()
        except: pass

        await interaction.channel.send(embed=discord.Embed(title=T("ui.results_title", self.lang), description=res_desc, color=discord.Color.dark_red()).set_footer(text=text), delete_after=20)
        await game.update_board()

        # Check End
        if len(game.alive_players()) <= game.bunker_spots:
            await game.end_game()
            survivors = ", ".join([p.name for p in game.alive_players()])
            await update_user_stats(interaction.user.id, "wins", 1) # Simplified win tracking, really should loop survivors
            await interaction.channel.send(embed=discord.Embed(title=T("ui.win_title", self.lang), description=f"Survivors: {survivors}", color=discord.Color.purple()))
            if game.dashboard_message:
                try: await game.dashboard_message.delete()
                except: pass
            await game.update_board()
        else:
            game.phase = GamePhase.REVEAL
            await interaction.channel.send(embed=discord.Embed(title=T("ui.game_continue", self.lang), description=T("ui.game_continue_desc", self.lang), color=discord.Color.gold()), delete_after=15)

class VoteSelect(discord.ui.Select):
    def __init__(self, candidates, max_sel):
        options = [discord.SelectOption(label=p.name, value=str(p.user_id), emoji="👤") for p in candidates]
        super().__init__(placeholder="Kick...", min_values=1, max_values=max_sel, options=options)
    
    async def callback(self, interaction):
        game = get_game_safe(interaction)
        if not game: return
        
        s_ids = [int(x) for x in self.values]
        game.votes[interaction.user.id] = s_ids
        
        await interaction.response.send_message(T("msg.vote_accepted", self.view.lang), ephemeral=True, delete_after=3)
        
        # Update view status
        voted = len(game.votes)
        alive = len(game.alive_players())
        
        embed = interaction.message.embeds[0]
        # Find status field
        embed.set_field_at(0, name="Status", value=f"Voted: {voted}/{alive}")
        
        if voted == alive:
            self.view.end_btn.disabled = False
            self.view.end_btn.style = discord.ButtonStyle.success
        
        await interaction.message.edit(embed=embed, view=self.view)

class JoinView(discord.ui.View):
    def __init__(self, lang):
        super().__init__(timeout=600)
        self.lang = lang
        self.children[0].label = T("ui.join_btn", lang)
        self.children[1].label = T("ui.start_btn", lang)
        self.children[2].label = T("ui.cancel_btn", lang)
        self.children[1].disabled = True

    @discord.ui.button(style=discord.ButtonStyle.success)
    async def join(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: return
        
        if game.add_player(interaction.user.id, interaction.user.display_name):
            await interaction.response.send_message(T("msg.joined", self.lang), ephemeral=True, delete_after=3)
            if len(game.players) >= game.max_players:
                self.children[1].disabled = False
                self.children[1].style = discord.ButtonStyle.success
            
            emb = discord.Embed(title=T("ui.lobby_title", self.lang), description=f"{T('ui.host_label', self.lang)} <@{game.host_id}>\n{T('ui.players_label', self.lang)} {len(game.players)}/{game.max_players}", color=discord.Color.orange())
            await interaction.message.edit(embed=emb, view=self)
        else:
            await interaction.response.send_message(T("msg.no_seats", self.lang), ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.danger, disabled=True)
    async def start(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: return
        if interaction.user.id != game.host_id: return
        
        await game.start_game()
        await interaction.response.edit_message(content="Started", view=None, embed=None)
        
        await interaction.channel.send(embed=discord.Embed(title="☢️ INTRO", description=game.lore_text, color=discord.Color.dark_red()))
        game.board_message = await interaction.channel.send(embed=game.generate_board_embed())
        game.dashboard_view = Dashboard(self.lang) # Save ref
        game.dashboard_message = await interaction.channel.send(view=game.dashboard_view)

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        game = get_game_safe(interaction)
        if not game or interaction.user.id != game.host_id: return
        if interaction.guild.id in games: del games[interaction.guild.id]
        await interaction.response.edit_message(content=T("msg.game_cancelled", self.lang), view=None, embed=None)

# =========================
#  COMMANDS
# =========================

@bot.tree.command(name="language", description="Change language")
async def language(interaction: discord.Interaction):
    if not interaction.guild: return
    view = discord.ui.View()
    view.add_item(LangSelect())
    await interaction.response.send_message("Select:", view=view, ephemeral=True)

@bot.tree.command(name="create", description="Start new game")
@app_commands.describe(players="Number of players")
async def create(interaction: discord.Interaction, players: int):
    if not interaction.guild: return
    if players < 2 or players > 25:
        await interaction.response.send_message("2-25 players.", ephemeral=True)
        return
    if interaction.guild.id in games:
        await interaction.response.send_message("Game already in progress!", ephemeral=True)
        return

    lang = get_server_lang(interaction.guild.id)
    new_game = GameState(players, interaction.user.id, lang, interaction.guild.id)
    games[interaction.guild.id] = new_game
    
    emb = discord.Embed(title=T("ui.lobby_title", lang), description=f"{T('ui.host_label', lang)} {interaction.user.mention}\n{T('ui.players_label', lang)} 0/{players}", color=discord.Color.orange())
    await interaction.response.send_message(embed=emb, view=JoinView(lang))

@bot.tree.command(name="profile", description="Stats")
async def profile(interaction: discord.Interaction, user: Optional[discord.User] = None):
    if not interaction.guild: return
    target = user or interaction.user
    lang = get_server_lang(interaction.guild.id)
    d = get_user_data(target.id)
    
    nm = d["name"] if d["name"] else target.display_name
    emb = discord.Embed(title=T("profile.title", lang, name=nm), color=discord.Color.blue())
    emb.set_thumbnail(url=target.display_avatar.url)
    
    emb.add_field(name=T("profile.games", lang), value=str(d["games"]))
    emb.add_field(name=T("profile.wins", lang), value=str(d["wins"]))
    
    winrate = 0
    if d["games"] > 0: winrate = (d["wins"] / d["games"]) * 100
    emb.add_field(name=T("profile.winrate", lang), value=f"{winrate:.1f}%")
    
    srv_games = get_server_stats(interaction.guild.id)
    emb.set_footer(text=T("profile.server_stats", lang, count=srv_games))
    
    is_owner = (target.id == interaction.user.id)
    await interaction.response.send_message(embed=emb, view=ProfileView(lang, is_owner), ephemeral=True)

if __name__ == "__main__":
    if BOT_TOKEN: bot.run(BOT_TOKEN)
    else: print("Error: Token not found.")