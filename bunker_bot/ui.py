import discord
import asyncio
import random
from .settings import logger
from .i18n import T
from .database import set_server_lang, get_user_data, set_custom_name, update_user_stats, save_user_db_data
from .game import games, GamePhase, Player

def get_game_safe(interaction: discord.Interaction):
    if not interaction.guild: return None
    return games.get(interaction.guild.id)

async def auto_del(interaction, delay=3):
    await asyncio.sleep(delay)
    try: await interaction.delete_original_response()
    except: pass

async def safe_response(interaction, content=None, embed=None, view=None, ephemeral=True, delete_after=None):
    try:
        if interaction.response.is_done():
            msg = await interaction.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral)
            if delete_after:
                await asyncio.sleep(delete_after)
                try: await msg.delete()
                except: pass
        else:
            await interaction.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral, delete_after=delete_after)
    except Exception as e:
        logger.error(f"UI Error: {e}")

class CloseBtn(discord.ui.Button):
    def __init__(self, lang):
        super().__init__(label=T("ui.close_btn", lang), style=discord.ButtonStyle.danger)
    async def callback(self, interaction):
        await interaction.response.edit_message(content=T("msg.closed", self.view.lang), embed=None, view=None)
        asyncio.create_task(auto_del(interaction))

class CloseView(discord.ui.View):
    def __init__(self, lang="uk"):
        super().__init__(timeout=180)
        self.lang = lang
        self.add_item(CloseBtn(lang))

class LangSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Select Language", options=options)
    async def callback(self, interaction):
        await set_server_lang(interaction.guild.id, self.values[0])
        await safe_response(interaction, T("msg.lang_changed", self.values[0]), ephemeral=True)

class NameModal(discord.ui.Modal):
    def __init__(self, lang):
        super().__init__(title=T("modal.title", lang))
        self.lang = lang
        self.name_input = discord.ui.TextInput(label=T("modal.label", lang), placeholder=T("modal.placeholder", lang), min_length=2, max_length=20)
        self.add_item(self.name_input)

    async def on_submit(self, interaction):
        await set_custom_name(interaction.user.id, self.name_input.value)
        game = get_game_safe(interaction)
        if game:
            p = game.get_player(interaction.user.id)
            if p: 
                p.name = self.name_input.value
                await game.update_board(interaction.client)
        await safe_response(interaction, T("msg.name_changed", self.lang, name=self.name_input.value), ephemeral=True)

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

class JoinView(discord.ui.View):
    def __init__(self, lang, guild_id):
        super().__init__(timeout=3600)
        self.lang = lang
        self.children[0].label = T("ui.join_btn", lang)
        self.children[0].custom_id = f"bunker:join:{guild_id}"
        self.children[1].label = T("ui.start_btn", lang)
        self.children[1].custom_id = f"bunker:start:{guild_id}"
        self.children[1].disabled = True
        self.children[2].label = T("ui.cancel_btn", lang)
        self.children[2].custom_id = f"bunker:cancel:{guild_id}"

    async def on_timeout(self):
        for item in self.children: item.disabled = True

    @discord.ui.button(style=discord.ButtonStyle.success)
    async def join(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: return await safe_response(interaction, "No game.", ephemeral=True)
        
        if game.add_player(interaction.user.id, interaction.user.display_name):
            await safe_response(interaction, T("msg.joined", self.lang), ephemeral=True, delete_after=3)
            if len(game.players) >= game.max_players:
                self.children[1].disabled = False
                self.children[1].style = discord.ButtonStyle.success
            emb = discord.Embed(title=T("ui.lobby_title", self.lang), description=f"{T('ui.host_label', self.lang)} <@{game.host_id}>\n{T('ui.players_label', self.lang)} {len(game.players)}/{game.max_players}", color=discord.Color.orange())
            await interaction.message.edit(embed=emb, view=self)
        else:
            await safe_response(interaction, T("msg.no_seats", self.lang), ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.danger, disabled=True)
    async def start(self, interaction, button):
        game = get_game_safe(interaction)
        if not game or interaction.user.id != game.host_id: return
        await game.start_game()
        await interaction.response.edit_message(content="Started", view=None, embed=None)
        await interaction.channel.send(embed=discord.Embed(title="☢️ INTRO", description=game.lore_text, color=discord.Color.dark_red()))
        game.board_message = await interaction.channel.send(embed=game.generate_board_embed())
        game.board_msg_id = game.board_message.id
        game.channel_id = interaction.channel.id
        
        # We need to import Dashboard here or pass it to avoid circular imports if Dashboard is in this file
        # Dashboard is in this file, so it's fine.
        game.dashboard_view = Dashboard(self.lang, game.guild_id)
        game.dashboard_message = await interaction.channel.send(view=game.dashboard_view)
        game.dash_msg_id = game.dashboard_message.id
        # Update persistence done in start_game()

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        game = get_game_safe(interaction)
        if not game or interaction.user.id != game.host_id: return
        await game.end_game(interaction.client)
        await interaction.response.edit_message(content=T("msg.game_cancelled", self.lang), view=None, embed=None)

class CardSelect(discord.ui.Select):
    def __init__(self, player):
        self.player = player
        lang = player.lang
        titles = T("card_titles", lang)
        opts = [discord.SelectOption(label=T("ui.reveal_all_opt", lang), value="all", description=T("ui.reveal_all_desc", lang))]
        for k, v in titles.items():
            emoji = "✅" if player.opened.get(k) else "🔒"
            desc = player.cards[k] if player.opened.get(k) else "???"
            opts.append(discord.SelectOption(label=v, value=k, description=desc, emoji=emoji))
        super().__init__(placeholder=T("ui.reveal_placeholder", lang), min_values=1, max_values=len(opts), options=opts)

    async def callback(self, interaction):
        game = get_game_safe(interaction)
        if not game or not self.player.alive: return
        
        vals = self.values
        if "all" in vals:
            for k in self.player.cards: self.player.opened[k] = True
            await interaction.channel.send(embed=discord.Embed(title=T("msg.reveal_all_public_title", self.player.lang, name=self.player.name), description=T("msg.reveal_all_public_desc", self.player.lang), color=discord.Color.gold()), delete_after=15)
        else:
            titles = T("card_titles", self.player.lang)
            rev = []
            for v in vals:
                if not self.player.opened.get(v):
                    self.player.opened[v] = True
                    rev.append(f"**{titles.get(v, v)}**: `{self.player.cards[v]}`")
            if rev:
                await interaction.channel.send(embed=discord.Embed(title=T("msg.reveal_public_title", self.player.lang, name=self.player.name), description="\n".join(rev), color=discord.Color.green()), delete_after=15)
                await safe_response(interaction, T("msg.reveal_success", self.player.lang), ephemeral=True, delete_after=3)
            else:
                await safe_response(interaction, T("msg.reveal_nothing", self.player.lang), ephemeral=True, delete_after=3)
        
        await game.update_board(interaction.client)

class Dashboard(discord.ui.View):
    def __init__(self, lang, guild_id):
        super().__init__(timeout=7200)
        self.lang = lang
        # Setup buttons
        self.children[0].custom_id = f"bunker:profile:{guild_id}"
        self.children[0].label = T("ui.profile_btn", lang)
        self.children[1].custom_id = f"bunker:reveal:{guild_id}"
        self.children[1].label = T("ui.reveal_btn", lang)
        self.children[2].custom_id = f"bunker:guide:{guild_id}"
        self.children[2].label = T("ui.guide_btn", lang)
        self.children[3].custom_id = f"bunker:vote:{guild_id}"
        self.children[3].label = T("ui.vote_start_btn", lang)

    async def on_timeout(self):
        for child in self.children: child.disabled = True

    @discord.ui.button(emoji="📂", style=discord.ButtonStyle.primary, row=0)
    async def profile(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: return await safe_response(interaction, "No game.", ephemeral=True)
        p = game.get_player(interaction.user.id)
        if p: await safe_response(interaction, embed=discord.Embed(title="📂", description=p.get_profile_text(True), color=discord.Color.blue()), ephemeral=True, view=CloseView(self.lang))
        else: await safe_response(interaction, "Not in game", ephemeral=True)

    @discord.ui.button(emoji="📢", style=discord.ButtonStyle.success, row=0)
    async def reveal(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: return
        p = game.get_player(interaction.user.id)
        if p and p.alive:
            v = discord.ui.View()
            v.add_item(CardSelect(p))
            await safe_response(interaction, T("ui.reveal_placeholder", self.lang), view=v, ephemeral=True)

    @discord.ui.button(emoji="📖", style=discord.ButtonStyle.secondary, row=1)
    async def guide(self, interaction, button):
        view = discord.ui.View()
        # Need to fix guide category select
        from .game import T # circular? no T is imported from i18n
        # Actually GuideCategorySelect logic is self-contained
        view.add_item(GuideCategorySelect(self.lang)) 
        await safe_response(interaction, T("ui.guide_placeholder", self.lang), view=view, ephemeral=True)

    @discord.ui.button(emoji="🔴", style=discord.ButtonStyle.danger, row=1)
    async def vote(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: return
        if interaction.user.id != game.host_id:
            return await safe_response(interaction, T("msg.only_host", self.lang), ephemeral=True)
        
        game.phase = GamePhase.VOTING
        game.votes.clear()
        
        alive = game.alive_players()
        if len(alive) <= game.bunker_spots:
            return await safe_response(interaction, "Finish!", ephemeral=True)

        embed = discord.Embed(title=T("ui.vote_title", self.lang), description=T("ui.vote_desc", self.lang), color=discord.Color.gold())
        mx = 2 if game.double_elim_next else 1
        if game.double_elim_next: embed.set_footer(text=T("ui.vote_footer_double", self.lang))
        
        embed.add_field(name="Status", value="Waiting...")
        await safe_response(interaction, embed=embed, view=VoteView(alive, mx, self.lang))

# Guide classes
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

class VoteSelect(discord.ui.Select):
    def __init__(self, candidates, max_sel):
        options = [discord.SelectOption(label=p.name, value=str(p.user_id), emoji="👤") for p in candidates]
        super().__init__(placeholder="Kick...", min_values=1, max_values=max_sel, options=options)
    
    async def callback(self, interaction):
        game = get_game_safe(interaction)
        if not game: return
        
        s_ids = [int(x) for x in self.values]
        await game.register_vote(interaction.user.id, s_ids)
        await safe_response(interaction, T("msg.vote_accepted", self.view.lang), ephemeral=True, delete_after=3)
        
        voters = [v for v in game.votes.keys() if game.get_player(v) and game.get_player(v).alive]
        alive = len(game.alive_players())
        
        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name="Status", value=f"Voted: {len(voters)}/{alive}")
        
        if len(voters) == alive:
            self.view.end_btn.disabled = False
            self.view.end_btn.style = discord.ButtonStyle.success
        
        await interaction.message.edit(embed=embed, view=self.view)

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

        eliminated, text, is_draw = game.resolve_votes()
        
        try: await interaction.message.delete()
        except: pass

        if is_draw:
            await interaction.channel.send(embed=discord.Embed(title=T("msg.draw", self.lang), description=T("msg.draw_desc", self.lang), color=discord.Color.yellow()), delete_after=15)
            return

        res_desc = ""
        kick_stories = T("kick_descriptions", self.lang)
        for p in eliminated:
            p.alive = False
            await update_user_stats(p.user_id, "deaths", 1)
            story = random.choice(kick_stories)
            res_desc += f"💀 **{p.name}**\n*{story}*\n\n"

        await interaction.channel.send(embed=discord.Embed(title=T("ui.results_title", self.lang), description=res_desc, color=discord.Color.dark_red()).set_footer(text=text), delete_after=20)
        await game.update_board(interaction.client)

        if len(game.alive_players()) <= game.bunker_spots:
            await game.end_game(interaction.client)
            survivors = ", ".join([p.name for p in game.alive_players()])
            for p in game.alive_players():
                await update_user_stats(p.user_id, "wins", 1)
            
            story = game.calculate_ending()
            await interaction.channel.send(embed=discord.Embed(title=T("ui.win_title", self.lang), description=f"**Survivors:** {survivors}\n\n{story}", color=discord.Color.purple()))
        else:
            game.phase = GamePhase.REVEAL
            await interaction.channel.send(embed=discord.Embed(title=T("ui.game_continue", self.lang), description=T("ui.game_continue_desc", self.lang), color=discord.Color.gold()), delete_after=15)