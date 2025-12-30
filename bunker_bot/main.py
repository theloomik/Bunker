import discord
from discord.ext import commands
from .settings import BOT_TOKEN, logger
from .database import load_user_db, load_active_games_from_disk, global_user_db
from .game import games
from .ui import JoinView, Dashboard
from .i18n import T, LANGUAGES
from . import database # for profile stats

# We can import commands here to register them
from discord import app_commands
from typing import Optional

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await load_user_db()
    await load_active_games_from_disk()
    
    # Re-register views for persistence
    # Note: JoinView and Dashboard use custom_id, so we just need to add them once per type usually,
    # or re-add for specific messages if stateful.
    # Since we use custom_id like "bunker:join:{guild_id}", we need a dynamic factory or verify if
    # discord.py automatically handles custom_id matching without pre-registration if the view class is known.
    # Actually, for persistent views to work after restart, we must add_view() for them.
    # Since IDs are dynamic per guild, we iterate loaded games.
    
    count = 0
    for gid, game in games.items():
        bot.add_view(JoinView(game.lang, gid))
        bot.add_view(Dashboard(game.lang, gid))
        count += 1
        
    await bot.tree.sync()
    logger.info(f"Bot logged in as {bot.user}. Restored {count} active games.")

# --- COMMANDS REGISTRATION ---
# Ideally these should be in a separate cog, but for this structure we define them here
# utilizing functions from other modules

@bot.tree.command(name="language", description="Change language")
async def language(interaction: discord.Interaction):
    from .ui import LangSelect
    if not interaction.guild: return
    view = discord.ui.View()
    view.add_item(LangSelect([discord.SelectOption(label=LANGUAGES[k]["name"], value=k) for k in LANGUAGES.keys()]))
    await interaction.response.send_message("Select:", view=view, ephemeral=True)

@bot.tree.command(name="create", description="Start new game")
@app_commands.describe(players="Number of players")
async def create(interaction: discord.Interaction, players: int):
    from .game import GameState, save_active_games
    from .ui import JoinView, safe_response
    
    if not interaction.guild: return
    if players < 2 or players > 25:
        await safe_response(interaction, "2-25 players.", ephemeral=True)
        return
    if interaction.guild.id in games:
        await safe_response(interaction, "Game in progress!", ephemeral=True)
        return

    lang = database.get_server_lang(interaction.guild.id)
    new_game = GameState(players, interaction.user.id, lang, interaction.guild.id)
    games[interaction.guild.id] = new_game
    await save_active_games()
    
    emb = discord.Embed(title=T("ui.lobby_title", lang), description=f"{T('ui.host_label', lang)} {interaction.user.mention}\n{T('ui.players_label', lang)} 0/{players}", color=discord.Color.orange())
    await safe_response(interaction, embed=emb, view=JoinView(lang, interaction.guild.id))

@bot.tree.command(name="profile", description="Stats")
async def profile(interaction: discord.Interaction, user: Optional[discord.User] = None):
    from .ui import ProfileView, safe_response
    if not interaction.guild: return
    target = user or interaction.user
    lang = database.get_server_lang(interaction.guild.id)
    d = database.get_user_data(target.id)
    
    nm = d["name"] if d["name"] else target.display_name
    emb = discord.Embed(title=T("profile.title", lang, name=nm), color=discord.Color.blue())
    emb.set_thumbnail(url=target.display_avatar.url)
    emb.add_field(name=T("profile.games", lang), value=str(d["games"]))
    emb.add_field(name=T("profile.wins", lang), value=str(d["wins"]))
    
    winrate = 0
    if d["games"] > 0: winrate = (d["wins"] / d["games"]) * 100
    emb.add_field(name=T("profile.winrate", lang), value=f"{winrate:.1f}%")
    
    srv_games = database.get_server_stats(interaction.guild.id)
    emb.set_footer(text=T("profile.server_stats", lang, count=srv_games))
    
    is_owner = (target.id == interaction.user.id)
    await safe_response(interaction, embed=emb, view=ProfileView(lang, is_owner), ephemeral=True)

def run():
    if BOT_TOKEN:
        bot.run(BOT_TOKEN)
    else:
        logger.critical("No token found!")

if __name__ == "__main__":
    run()