import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import asyncio

from .settings import BOT_TOKEN, logger
from .database import load_user_db, load_raw_active_games, get_server_lang, get_user_data, get_server_stats, reset_user_stats
from .game import games, GameState, load_active_games_from_disk, save_active_games
from .ui import JoinView, Dashboard, ProfileView, CloseView, LangSelect, safe_response
from .i18n import T, LANGUAGES

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    # 1. Load User DB
    await load_user_db()
    
    # 2. Recover Active Games
    await load_active_games_from_disk()
    
    recovered_count = 0
    # Re-register views
    for gid, game in games.items():
        bot.add_view(JoinView(game.lang, gid))
        bot.add_view(Dashboard(game.lang, gid))
        recovered_count += 1

    await bot.tree.sync()
    logger.info(f"Bot logged in as {bot.user}. Recovered {recovered_count} games.")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        await safe_response(interaction, f"Cooldown: {error.retry_after:.1f}s", ephemeral=True)
    elif isinstance(error, app_commands.MissingPermissions):
        await safe_response(interaction, "❌ You do not have permission to use this command.", ephemeral=True)
    else:
        logger.error(f"Command Error: {error}")
        try: await safe_response(interaction, "❌ Internal Error.", ephemeral=True)
        except: pass

@bot.tree.command(name="language", description="Change language")
async def language(interaction: discord.Interaction):
    if not interaction.guild: return
    options = [discord.SelectOption(label=LANGUAGES[k]["name"], value=k) for k in LANGUAGES.keys()]
    view = discord.ui.View()
    view.add_item(LangSelect(options))
    await safe_response(interaction, "Select Language:", view=view, ephemeral=True)

@bot.tree.command(name="create", description="Start new game")
@app_commands.describe(players="Number of players")
async def create(interaction: discord.Interaction, players: int):
    if not interaction.guild:
        await safe_response(interaction, "Servers only.", ephemeral=True)
        return
    if players < 2 or players > 25:
        await safe_response(interaction, "2-25 players.", ephemeral=True)
        return
    if interaction.guild.id in games:
        await safe_response(interaction, "Game already in progress!", ephemeral=True)
        return

    lang = get_server_lang(interaction.guild.id)
    new_game = GameState(players, interaction.user.id, lang, interaction.guild.id)
    games[interaction.guild.id] = new_game
    
    # Save state immediately (non-blocking)
    asyncio.create_task(save_active_games())
    
    emb = discord.Embed(title=T("ui.lobby_title", lang), description=f"{T('ui.host_label', lang)} {interaction.user.mention}\n{T('ui.players_label', lang)} 0/{players}", color=discord.Color.orange())
    await safe_response(interaction, embed=emb, view=JoinView(lang, interaction.guild.id))

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
    await safe_response(interaction, embed=emb, view=ProfileView(lang, is_owner), ephemeral=True)

@bot.tree.command(name="dossier", description="In-game dossier")
async def dossier(interaction: discord.Interaction):
    game = games.get(interaction.guild.id)
    if not game:
        await safe_response(interaction, "No active game.", ephemeral=True)
        return
    p = game.get_player(interaction.user.id)
    lang = get_server_lang(interaction.guild.id)
    if p:
        await safe_response(interaction, embed=discord.Embed(title="📂", description=p.get_profile_text(True), color=discord.Color.blue()), ephemeral=True, view=CloseView(lang))
    else:
        await safe_response(interaction, "Not in game", ephemeral=True)

# --- ADMIN COMMANDS ---

@bot.tree.command(name="admin_endgame", description="Force end the current game (Admin)")
@app_commands.checks.has_permissions(administrator=True)
async def admin_endgame(interaction: discord.Interaction):
    if not interaction.guild: return
    game = games.get(interaction.guild.id)
    if game:
        await game.end_game(interaction.client)
        await safe_response(interaction, "✅ Game force-ended by admin.", ephemeral=True)
    else:
        await safe_response(interaction, "❌ No active game in this server.", ephemeral=True)

@bot.tree.command(name="admin_reset_stats", description="Reset user stats (Admin)")
@app_commands.checks.has_permissions(administrator=True)
async def admin_reset_stats(interaction: discord.Interaction, user: discord.User):
    if not interaction.guild: return
    await reset_user_stats(user.id)
    await safe_response(interaction, f"✅ Stats reset for {user.mention}.", ephemeral=True)

def run():
    if BOT_TOKEN:
        bot.run(BOT_TOKEN)
    else:
        logger.critical("Error: Token not found in config.json or env vars.")