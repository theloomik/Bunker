import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import asyncio

from .settings import BOT_TOKEN, logger, EmbedColors
from .database import load_user_db, load_raw_active_games, get_server_lang, get_user_data, get_server_stats, reset_user_stats
from .game import games, GameState, load_active_games_from_disk, save_active_games, GamePhase
from .ui import JoinView, Dashboard, ProfileView, CloseView, LangSelect, safe_response, check_bot_perms, VoteView, tech_embed
from .i18n import T, LANGUAGES, load_languages

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    # 1. Load User DB
    await load_user_db()
    
    # 2. Load Languages (Async) - MUST BE BEFORE RECOVERING GAMES
    await load_languages()
    
    # 3. Recover Active Games
    await load_active_games_from_disk()
    
    recovered_count = 0
    # Re-register persistent views
    for gid, game in games.items():
        bot.add_view(JoinView(game.lang, gid))
        bot.add_view(Dashboard(game.lang, gid))
        
        # If game was in VOTING, we must also recover the VoteView to allow voting to continue
        if game.phase == GamePhase.VOTING:
            alive = game.alive_players()
            mx = 2 if game.double_elim_next else 1
            bot.add_view(VoteView(alive, mx, game.lang, gid))
            
        recovered_count += 1

    await bot.tree.sync()
    logger.info(f"Bot logged in as {bot.user}. Recovered {recovered_count} games.")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        await safe_response(interaction, embed=tech_embed(f"Cooldown: {error.retry_after:.1f}s", "error"), ephemeral=True)
    elif isinstance(error, app_commands.MissingPermissions):
        await safe_response(interaction, embed=tech_embed("❌ You do not have permission to use this command.", "error"), ephemeral=True)
    else:
        logger.error(f"Command Error: {error}")
        try: await safe_response(interaction, embed=tech_embed("❌ Internal Error.", "error"), ephemeral=True)
        except: pass

@bot.tree.command(name="language", description="Change language")
@app_commands.checks.cooldown(1, 30.0, key=lambda i: (i.guild_id)) # 1 use per 30s per guild
async def language(interaction: discord.Interaction):
    if not interaction.guild: return
    
    # Check if languages loaded correctly
    if not LANGUAGES:
        await load_languages() # Try reloading if empty
        
    if not LANGUAGES:
        await safe_response(interaction, embed=tech_embed("❌ Error: Language file is empty or missing.", "error"), ephemeral=True)
        return

    # Create options based on loaded languages
    options = [discord.SelectOption(label=data.get("name", code), value=code) for code, data in LANGUAGES.items()]
    
    if not options:
        await safe_response(interaction, embed=tech_embed("❌ No languages available.", "error"), ephemeral=True)
        return

    view = discord.ui.View()
    view.add_item(LangSelect(options))
    await safe_response(interaction, "Select Language:", view=view, ephemeral=True)

@bot.tree.command(name="create", description="Start new game")
@app_commands.describe(players="Number of players")
@app_commands.checks.cooldown(1, 60.0) # 1 use per 60s per user
async def create(interaction: discord.Interaction, players: int):
    if not interaction.guild:
        await safe_response(interaction, embed=tech_embed("Servers only.", "error"), ephemeral=True)
        return
    if not check_bot_perms(interaction):
        await safe_response(interaction, embed=tech_embed("Missing permissions! I need 'Send Messages' and 'Embed Links'.", "error"), ephemeral=True)
        return
    if players < 2 or players > 25:
        await safe_response(interaction, embed=tech_embed("2-25 players.", "error"), ephemeral=True)
        return
    if interaction.guild.id in games:
        await safe_response(interaction, embed=tech_embed("Game already in progress!", "error"), ephemeral=True)
        return

    lang = get_server_lang(interaction.guild.id)
    new_game = GameState(players, interaction.user.id, lang, interaction.guild.id)
    
    # Auto-join the host immediately
    new_game.add_player(interaction.user.id, interaction.user.display_name)
    
    games[interaction.guild.id] = new_game
    
    # Save state immediately (non-blocking)
    asyncio.create_task(save_active_games())
    
    emb = discord.Embed(title=T("ui.lobby_title", lang), description=f"{T('ui.host_label', lang)} {interaction.user.mention}\n{T('ui.players_label', lang)} 1/{players}", color=EmbedColors.LOBBY)
    
    # CRITICAL FIX: ephemeral=False ensures everyone can see the lobby and join
    await safe_response(interaction, embed=emb, view=JoinView(lang, interaction.guild.id), ephemeral=False)

@bot.tree.command(name="profile", description="Stats")
@app_commands.checks.cooldown(1, 10.0) # 1 use per 10s per user
async def profile(interaction: discord.Interaction, user: Optional[discord.User] = None):
    if not interaction.guild: 
        await safe_response(interaction, embed=tech_embed("Use this command in a server.", "error"), ephemeral=True)
        return
    
    target = user or interaction.user
    lang = get_server_lang(interaction.guild.id)
    d = get_user_data(target.id)
    
    nm = d["name"] if d["name"] else target.display_name
    
    base_title = T("profile.title", lang, name=nm)
    emb = discord.Embed(title=f"{base_title} (Global)", color=EmbedColors.INFO)
    
    emb.set_thumbnail(url=target.display_avatar.url)
    
    emb.add_field(name=T("profile.games", lang), value=str(d["games"]), inline=True)
    emb.add_field(name=T("profile.wins", lang), value=str(d["wins"]), inline=True)
    
    winrate = 0
    if d["games"] > 0: winrate = (d["wins"] / d["games"]) * 100
    emb.add_field(name=T("profile.winrate", lang), value=f"{winrate:.1f}%", inline=True)

    # Sex Stats Display
    sex_stats = d.get("sex_stats", {"m": 0, "f": 0})
    sex_text = f"♂️ {sex_stats.get('m', 0)} | ♀️ {sex_stats.get('f', 0)}"
    emb.add_field(name=T("profile.sex", lang), value=sex_text, inline=True)
    
    # Average Age Display
    avg_age = 0
    if d["games"] > 0 and "total_age" in d:
        avg_age = d["total_age"] / d["games"]
    emb.add_field(name=T("profile.age", lang), value=f"{avg_age:.1f}", inline=True)
    
    srv_games = get_server_stats(interaction.guild.id)
    emb.set_footer(text=T("profile.server_stats", lang, count=srv_games))
    
    is_owner = (target.id == interaction.user.id)
    await safe_response(interaction, embed=emb, view=ProfileView(lang, is_owner), ephemeral=True)

@bot.tree.command(name="dossier", description="In-game dossier")
@app_commands.checks.cooldown(1, 5.0) # 1 use per 5s per user
async def dossier(interaction: discord.Interaction):
    game = games.get(interaction.guild.id)
    if not game:
        await safe_response(interaction, embed=tech_embed("No active game.", "error"), ephemeral=True)
        return
    p = game.get_player(interaction.user.id)
    lang = get_server_lang(interaction.guild.id)
    if p:
        await safe_response(interaction, embed=discord.Embed(title="📂", description=p.get_profile_text(True), color=EmbedColors.INFO), ephemeral=True, view=CloseView(lang))
    else:
        await safe_response(interaction, embed=tech_embed("Not in game", "error"), ephemeral=True)

# --- ADMIN COMMANDS ---

@bot.tree.command(name="admin_endgame", description="Force end the current game (Admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.checks.cooldown(1, 5.0)
async def admin_endgame(interaction: discord.Interaction):
    if not interaction.guild: return
    game = games.get(interaction.guild.id)
    if game:
        await game.end_game(interaction.client)
        await safe_response(interaction, embed=tech_embed("✅ Game force-ended by admin.", "success"), ephemeral=True)
    else:
        await safe_response(interaction, embed=tech_embed("❌ No active game in this server.", "error"), ephemeral=True)

@bot.tree.command(name="admin_reset_stats", description="Reset user stats (Admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.checks.cooldown(1, 5.0)
async def admin_reset_stats(interaction: discord.Interaction, user: discord.User):
    if not interaction.guild: return
    await reset_user_stats(user.id)
    await safe_response(interaction, embed=tech_embed(f"✅ Stats reset for {user.mention}.", "success"), ephemeral=True)

def run():
    if BOT_TOKEN:
        bot.run(BOT_TOKEN)
    else:
        logger.critical("Error: Token not found in config.json or env vars.")