import discord
import asyncio
import random
from .settings import logger, VOTE_TIMEOUT, EPHEMERAL_VIEW_TIMEOUT, BRIEF_MSG_LIFETIME, ANNOUNCEMENT_LIFETIME, RESULT_MSG_LIFETIME, EmbedColors
from .i18n import T
from .database import set_server_lang, get_user_data, set_custom_name, update_user_stats, save_user_db_data
from .game import games, GamePhase, Player, save_active_games

def get_game_safe(interaction: discord.Interaction):
    if not interaction.guild: return None
    return games.get(interaction.guild.id)

def check_bot_perms(interaction: discord.Interaction) -> bool:
    if not interaction.guild: return True
    if not interaction.channel: return True
    perms = interaction.channel.permissions_for(interaction.guild.me)
    return perms.send_messages and perms.embed_links and perms.read_message_history

async def auto_del(interaction, delay=3):
    await asyncio.sleep(delay)
    try: await interaction.delete_original_response()
    except: pass

async def safe_response(interaction, content=None, embed=None, view=None, ephemeral=True, delete_after=None):
    try:
        if interaction.response.is_done():
            msg = await interaction.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral, wait=True)
            if delete_after:
                await asyncio.sleep(delete_after)
                try: await msg.delete()
                except: pass
        else:
            await interaction.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral, delete_after=delete_after)
    except Exception as e:
        if "Unknown interaction" not in str(e) and "404 Not Found" not in str(e):
             logger.error(f"UI Error in safe_response: {e}")

# --- HELPERS ---
def tech_embed(text: str, type="success") -> discord.Embed:
    color = EmbedColors.SUCCESS if type == "success" else EmbedColors.ERROR
    if type == "info": color = EmbedColors.INFO
    return discord.Embed(description=text, color=color)

class CloseBtn(discord.ui.Button):
    def __init__(self, lang):
        super().__init__(label=T("ui.close_btn", lang), style=discord.ButtonStyle.danger, custom_id="bunker:close:generic") 
    async def callback(self, interaction):
        await interaction.response.edit_message(content=None, embed=tech_embed(T("msg.closed", self.view.lang if hasattr(self.view, "lang") else "uk"), "info"), view=None)
        asyncio.create_task(auto_del(interaction))

class CloseView(discord.ui.View):
    def __init__(self, lang="uk"):
        super().__init__(timeout=EPHEMERAL_VIEW_TIMEOUT)
        self.lang = lang
        self.add_item(CloseBtn(lang))

class LangSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Select Language", options=options, custom_id="bunker:lang_select")
    async def callback(self, interaction):
        if not interaction.guild:
            await safe_response(interaction, embed=tech_embed("Servers only.", "error"), ephemeral=True)
            return
        await set_server_lang(interaction.guild.id, self.values[0])
        await safe_response(interaction, embed=tech_embed(T("msg.lang_changed", self.values[0]), "success"), ephemeral=True)

class NameModal(discord.ui.Modal):
    def __init__(self, lang):
        super().__init__(title=T("modal.title", lang), timeout=None)
        self.lang = lang
        self.name_input = discord.ui.TextInput(label=T("modal.label", lang), placeholder=T("modal.placeholder", lang), min_length=2, max_length=20, custom_id="bunker:name_input")
        self.add_item(self.name_input)

    async def on_submit(self, interaction):
        raw_name = self.name_input.value.strip()
        safe_name = discord.utils.escape_mentions(raw_name)
        safe_name = discord.utils.escape_markdown(safe_name)
        
        if len(safe_name) < 2:
             await safe_response(interaction, embed=tech_embed("Name too short.", "error"), ephemeral=True)
             return

        await set_custom_name(interaction.user.id, safe_name)
        
        game = get_game_safe(interaction)
        if game:
            p = game.get_player(interaction.user.id)
            if p: 
                p.name = safe_name
                await game.update_board(interaction.client)
                asyncio.create_task(save_active_games())
        
        await safe_response(interaction, embed=tech_embed(T("msg.name_changed", self.lang, name=safe_name), "success"), ephemeral=True)

class ProfileView(discord.ui.View):
    def __init__(self, lang, is_owner):
        super().__init__(timeout=EPHEMERAL_VIEW_TIMEOUT)
        self.lang = lang
        self.add_item(CloseBtn(lang))
        if is_owner:
            b = discord.ui.Button(label=T("ui.change_name_btn", lang), style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="bunker:profile_edit")
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
        opts.append(discord.SelectOption(label=T("ui.reveal_all_opt", lang), value="all", description=T("ui.reveal_all_desc", lang)))
        
        for k, v in titles.items():
            emoji = "✅" if player.opened.get(k) else "🔒"
            desc = player.cards[k] if player.opened.get(k) else "???"
            opts.append(discord.SelectOption(label=v, value=k, description=desc, emoji=emoji))
        super().__init__(placeholder=T("ui.reveal_placeholder", lang), min_values=1, max_values=len(opts), options=opts, custom_id=f"bunker:card_sel:{player.user_id}")

    async def callback(self, interaction):
        game = get_game_safe(interaction)
        if not game or not self.player.alive: return
        if game.phase == GamePhase.FINISHED:
            await safe_response(interaction, embed=tech_embed("Game Over", "error"), ephemeral=True)
            return

        lang = self.player.lang
        
        vals = self.values
        if "all" in vals:
            for k in self.player.cards: self.player.opened[k] = True
            await interaction.channel.send(embed=discord.Embed(title=T("msg.reveal_all_public_title", lang, name=self.player.name), description=T("msg.reveal_all_public_desc", lang), color=EmbedColors.VOTING), delete_after=ANNOUNCEMENT_LIFETIME)
        else:
            titles = T("card_titles", lang)
            rev = []
            for v in vals:
                if not self.player.opened.get(v):
                    self.player.opened[v] = True
                    rev.append(f"**{titles.get(v, v)}**: `{self.player.cards[v]}`")
            
            if rev:
                await interaction.channel.send(embed=discord.Embed(title=T("msg.reveal_public_title", lang, name=self.player.name), description="\n".join(rev), color=EmbedColors.SUCCESS), delete_after=ANNOUNCEMENT_LIFETIME)
                await safe_response(interaction, embed=tech_embed(T("msg.reveal_success", lang), "success"), ephemeral=True, delete_after=BRIEF_MSG_LIFETIME)
            else:
                await safe_response(interaction, embed=tech_embed(T("msg.reveal_nothing", lang), "info"), ephemeral=True, delete_after=BRIEF_MSG_LIFETIME)
        
        asyncio.create_task(save_active_games())
        
        await asyncio.sleep(BRIEF_MSG_LIFETIME)
        try: await interaction.delete_original_response()
        except: pass
        
        await game.update_board(interaction.client)

class RevealView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=EPHEMERAL_VIEW_TIMEOUT)
        self.player = player
        self.lang = player.lang
        
        # Add the dropdown
        self.add_item(CardSelect(player))
        
        # Add the explicit Reveal All button
        all_btn = discord.ui.Button(
            label=T("ui.reveal_all_opt", self.lang),
            style=discord.ButtonStyle.danger,
            emoji="⚠️",
            custom_id=f"bunker:reveal_all:{player.user_id}"
        )
        all_btn.callback = self.reveal_all_callback
        self.add_item(all_btn)

    async def reveal_all_callback(self, interaction: discord.Interaction):
        game = get_game_safe(interaction)
        if not game or not self.player.alive: return
        if game.phase == GamePhase.FINISHED:
             await safe_response(interaction, embed=tech_embed("Game Over", "error"), ephemeral=True)
             return

        for k in self.player.cards: self.player.opened[k] = True
        
        await interaction.channel.send(
            embed=discord.Embed(
                title=T("msg.reveal_all_public_title", self.lang, name=self.player.name), 
                description=T("msg.reveal_all_public_desc", self.lang), 
                color=EmbedColors.VOTING
            ), 
            delete_after=ANNOUNCEMENT_LIFETIME
        )
        
        await interaction.response.edit_message(content=None, embed=tech_embed(T("msg.reveal_success", self.lang), "success"), view=None)
        
        asyncio.create_task(save_active_games())
        await asyncio.sleep(BRIEF_MSG_LIFETIME)
        try: await interaction.delete_original_response()
        except: pass

        await game.update_board(interaction.client)

class GuideCategorySelect(discord.ui.Select):
    def __init__(self, lang):
        self.lang = lang
        g_txt = T("guide", lang)
        options = [
            discord.SelectOption(label=g_txt.get("phobia_label", "Phobias") if isinstance(g_txt, dict) else "Phobias", value="phobia", emoji="😱"),
            discord.SelectOption(label=g_txt.get("health_label", "Health") if isinstance(g_txt, dict) else "Health", value="health", emoji="🏥")
        ]
        placeholder = g_txt.get("select_category", "Select Category") if isinstance(g_txt, dict) else "Select Category"
        super().__init__(placeholder=placeholder, options=options, custom_id="bunker:guide_cat")

    async def callback(self, interaction):
        data_dict = T("phobias" if self.values[0] == "phobia" else "health", self.lang)
        view = discord.ui.View()
        view.add_item(GuideItemSelect(data_dict, self.values[0], self.lang))
        await safe_response(interaction, content="Select:", view=view, ephemeral=True)

class GuideItemSelect(discord.ui.Select):
    def __init__(self, data_source, category_name, lang):
        self.data_source = data_source
        self.lang = lang
        options = []
        for k in sorted(data_source.keys()):
            options.append(discord.SelectOption(label=k))
        if len(options) > 25: options = options[:25]
        super().__init__(placeholder=f"List: {category_name}", options=options, custom_id=f"bunker:guide_item:{category_name}")

    async def callback(self, interaction):
        item = self.values[0]
        info = self.data_source.get(item)
        if info:
            await safe_response(
                interaction,
                embed=discord.Embed(title=f"📌 {item}", description=f"{info['desc']}\n\n**⚠️ Risk:**\n{info['risk']}", color=EmbedColors.INFO), 
                view=CloseView(self.lang),
                ephemeral=True
            )

class Dashboard(discord.ui.View):
    def __init__(self, lang, guild_id):
        super().__init__(timeout=None)
        self.lang = lang
        self.guild_id = guild_id
        
        self.children[0].custom_id = f"bunker:profile:{guild_id}"
        self.children[0].label = T("ui.profile_btn", lang)
        
        self.children[1].custom_id = f"bunker:reveal:{guild_id}"
        self.children[1].label = T("ui.reveal_btn", lang)
        
        self.children[2].custom_id = f"bunker:guide:{guild_id}"
        self.children[2].label = T("ui.guide_btn", lang)
        
        self.children[3].custom_id = f"bunker:vote:{guild_id}"
        self.children[3].label = T("ui.vote_start_btn", lang)

    async def on_timeout(self):
        pass

    @discord.ui.button(emoji="📂", style=discord.ButtonStyle.primary, row=0)
    async def profile(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: 
            await safe_response(interaction, embed=tech_embed("No active game.", "error"), ephemeral=True)
            return
        p = game.get_player(interaction.user.id)
        
        if not p:
            await safe_response(interaction, embed=tech_embed("Not in game", "error"), ephemeral=True)
            return
        if not p.alive:
             await safe_response(interaction, embed=tech_embed("💀 Dead players cannot view profiles.", "error"), ephemeral=True)
             return

        await safe_response(interaction, embed=discord.Embed(title="📂", description=p.get_profile_text(True), color=EmbedColors.INFO), ephemeral=True, view=CloseView(self.lang))

    @discord.ui.button(emoji="📢", style=discord.ButtonStyle.success, row=0)
    async def reveal(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: return
        p = game.get_player(interaction.user.id)
        
        if p and p.alive:
            await safe_response(interaction, T("ui.reveal_placeholder", self.lang), view=RevealView(p), ephemeral=True)
        else:
            await safe_response(interaction, embed=tech_embed("Not in game or dead.", "error"), ephemeral=True)

    @discord.ui.button(emoji="📖", style=discord.ButtonStyle.secondary, row=1)
    async def guide(self, interaction, button):
        game = get_game_safe(interaction)
        if game:
            p = game.get_player(interaction.user.id)
            if p and not p.alive:
                 await safe_response(interaction, embed=tech_embed("💀 Dead players cannot use the guide.", "error"), ephemeral=True)
                 return

        view = discord.ui.View()
        view.add_item(GuideCategorySelect(self.lang))
        await safe_response(interaction, content=None, embed=tech_embed(T("ui.guide_placeholder", self.lang), "info"), view=view, ephemeral=True)

    @discord.ui.button(emoji="🔴", style=discord.ButtonStyle.danger, row=1)
    async def vote(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: return
        if interaction.user.id != game.host_id:
            await safe_response(interaction, embed=tech_embed(T("msg.only_host", self.lang), "error"), ephemeral=True)
            return
        
        game.phase = GamePhase.VOTING
        game.votes.clear()
        
        alive = game.alive_players()
        if len(alive) <= game.bunker_spots:
            await safe_response(interaction, embed=tech_embed("Time to finish!", "info"), ephemeral=True)
            return

        embed = discord.Embed(title=T("ui.vote_title", self.lang), description=T("ui.vote_desc", self.lang), color=EmbedColors.VOTING)
        mx = 2 if game.double_elim_next else 1
        if game.double_elim_next: embed.set_footer(text=T("ui.vote_footer_double", self.lang))
        
        embed.add_field(name="Status", value="Waiting...")
        await safe_response(interaction, embed=embed, view=VoteView(alive, mx, self.lang, game.guild_id), ephemeral=False)
        asyncio.create_task(save_active_games())

class VoteView(discord.ui.View):
    def __init__(self, candidates, max_select, lang, guild_id):
        super().__init__(timeout=VOTE_TIMEOUT)
        self.lang = lang
        self.guild_id = guild_id
        self.add_item(VoteSelect(candidates, max_select, guild_id))
        self.end_btn = discord.ui.Button(label=T("ui.end_vote_btn", lang), style=discord.ButtonStyle.secondary, disabled=True, custom_id=f"bunker:vote_end:{guild_id}")
        self.end_btn.callback = self.end_callback
        self.add_item(self.end_btn)

    async def on_timeout(self):
        # Auto-resolve logic on timeout
        game = games.get(self.guild_id)
        
        if not game or game.phase != GamePhase.VOTING: return
        
        channel = None
        client = None

        if hasattr(self, 'message') and self.message:
            channel = self.message.channel
            client = self.message.guild.me.client
            try:
                for child in self.children: child.disabled = True
                await self.message.edit(view=self)
            except: pass
        
        if not channel: return

        eliminated, text, is_draw = game.resolve_votes()

        timeout_embed = discord.Embed(title="⏰ " + T("ui.vote_title", self.lang), description="Voting timed out. Resolving...", color=EmbedColors.ERROR)
        await channel.send(embed=timeout_embed, delete_after=ANNOUNCEMENT_LIFETIME)

        if is_draw:
            await channel.send(embed=discord.Embed(title=T("msg.draw", self.lang), description=T("msg.draw_desc", self.lang), color=EmbedColors.VOTING), delete_after=ANNOUNCEMENT_LIFETIME)
            asyncio.create_task(save_active_games())
            return

        res_desc = ""
        kick_stories = T("kick_descriptions", self.lang)
        for p in eliminated:
            p.alive = False
            await update_user_stats(p.user_id, "deaths", 1)
            story = random.choice(kick_stories)
            res_desc += f"💀 **{p.name}**\n*{story}*\n\n"

        await channel.send(embed=discord.Embed(title=T("ui.results_title", self.lang), description=res_desc, color=EmbedColors.ELIMINATION).set_footer(text=text), delete_after=RESULT_MSG_LIFETIME)
        
        if client: await game.update_board(client)
        asyncio.create_task(save_active_games())

        if len(game.alive_players()) <= game.bunker_spots:
            if client: await game.end_game(client)
            survivors = ", ".join([p.name for p in game.alive_players()])
            for p in game.alive_players():
                await update_user_stats(p.user_id, "wins", 1)
            
            # AUDIT FIX: Stats for all participants at end of game
            D = T("data", game.lang)
            for p in game.players:
                 try:
                    age_val = int(p.cards.get('age', 25))
                 except: age_val = 25
                 sex_val = p.cards.get('sex')
                 sex_idx = 0 if sex_val == D["sexes"][0] else 1
                 await update_user_stats(p.user_id, "game_start", {"age": age_val, "sex_idx": sex_idx})

            story = game.calculate_ending()
            await channel.send(embed=discord.Embed(title=T("ui.win_title", self.lang), description=f"**Survivors:** {survivors}\n\n{story}", color=EmbedColors.VICTORY))
            
            if client: await game.update_board(client)
        else:
            game.phase = GamePhase.REVEAL
            await channel.send(embed=discord.Embed(title=T("ui.game_continue", self.lang), description=T("ui.game_continue_desc", self.lang), color=EmbedColors.VOTING), delete_after=ANNOUNCEMENT_LIFETIME)
            asyncio.create_task(save_active_games())

    async def update_status(self, message):
        game = games.get(self.guild_id)
        if not game: return
        
        voted_count = len(game.votes)
        alive_count = len(game.alive_players())
        
        embed = message.embeds[0]
        embed.set_field_at(0, name="Status", value=f"Voted: {voted_count}/{alive_count}")
        
        if voted_count >= alive_count:
            self.end_btn.disabled = False
            self.end_btn.style = discord.ButtonStyle.success
        else:
            self.end_btn.disabled = True
            self.end_btn.style = discord.ButtonStyle.secondary
        
        await message.edit(embed=embed, view=self)

    async def end_callback(self, interaction):
        game = get_game_safe(interaction)
        if not game: return
        if interaction.user.id != game.host_id:
            await safe_response(interaction, embed=tech_embed(T("msg.only_host", self.lang), "error"), ephemeral=True)
            return
        
        if not check_bot_perms(interaction):
             await safe_response(interaction, embed=tech_embed("Permissions missing.", "error"), ephemeral=True)
             return

        eliminated, text, is_draw = game.resolve_votes()
        
        try: await interaction.message.delete()
        except: pass

        if is_draw:
            await interaction.channel.send(embed=discord.Embed(title=T("msg.draw", self.lang), description=T("msg.draw_desc", self.lang), color=EmbedColors.VOTING), delete_after=ANNOUNCEMENT_LIFETIME)
            asyncio.create_task(save_active_games())
            return

        res_desc = ""
        kick_stories = T("kick_descriptions", self.lang)
        for p in eliminated:
            p.alive = False
            await update_user_stats(p.user_id, "deaths", 1)
            story = random.choice(kick_stories)
            res_desc += f"💀 **{p.name}**\n*{story}*\n\n"

        await interaction.channel.send(embed=discord.Embed(title=T("ui.results_title", self.lang), description=res_desc, color=EmbedColors.ELIMINATION).set_footer(text=text), delete_after=RESULT_MSG_LIFETIME)
        
        await game.update_board(interaction.client)
        asyncio.create_task(save_active_games())

        if len(game.alive_players()) <= game.bunker_spots:
            await game.end_game(interaction.client)
            survivors = ", ".join([p.name for p in game.alive_players()])
            for p in game.alive_players():
                await update_user_stats(p.user_id, "wins", 1)
            
            # Update stats for everyone at end of game
            D = T("data", game.lang)
            for p in game.players:
                 try:
                    age_val = int(p.cards.get('age', 25))
                 except: age_val = 25
                 sex_val = p.cards.get('sex')
                 sex_idx = 0 if sex_val == D["sexes"][0] else 1
                 await update_user_stats(p.user_id, "game_start", {"age": age_val, "sex_idx": sex_idx})

            story = game.calculate_ending()
            await interaction.channel.send(embed=discord.Embed(title=T("ui.win_title", self.lang), description=f"**Survivors:** {survivors}\n\n{story}", color=EmbedColors.VICTORY))
            
            await game.update_board(interaction.client)
        else:
            game.phase = GamePhase.REVEAL
            await interaction.channel.send(embed=discord.Embed(title=T("ui.game_continue", self.lang), description=T("ui.game_continue_desc", self.lang), color=EmbedColors.VOTING), delete_after=ANNOUNCEMENT_LIFETIME)
            asyncio.create_task(save_active_games())

class VoteSelect(discord.ui.Select):
    def __init__(self, candidates, max_sel, guild_id):
        options = [discord.SelectOption(label=p.name, value=str(p.user_id), emoji="👤") for p in candidates]
        super().__init__(placeholder="Kick...", min_values=1, max_values=max_sel, options=options, custom_id=f"bunker:vote_sel:{guild_id}")
    
    async def callback(self, interaction):
        game = get_game_safe(interaction)
        if not game: return
        
        # Verify Phase
        if game.phase != GamePhase.VOTING:
            await safe_response(interaction, embed=tech_embed("Voting closed.", "error"), ephemeral=True)
            return

        s_ids = [int(x) for x in self.values]
        
        try:
            await game.register_vote(interaction.user.id, s_ids)
        except ValueError as e:
            await safe_response(interaction, embed=tech_embed(str(e), "error"), ephemeral=True)
            return
        
        await safe_response(interaction, embed=tech_embed(T("msg.vote_accepted", self.view.lang), "success"), ephemeral=True, delete_after=BRIEF_MSG_LIFETIME)
        await self.view.update_status(interaction.message)

class JoinView(discord.ui.View):
    def __init__(self, lang, guild_id):
        super().__init__(timeout=None)
        self.lang = lang
        self.guild_id = guild_id
        
        self.children[0].label = T("ui.join_btn", lang)
        self.children[0].custom_id = f"bunker:join:{guild_id}"
        
        self.children[1].label = T("ui.start_btn", lang)
        self.children[1].custom_id = f"bunker:start:{guild_id}"
        self.children[1].disabled = True
        
        self.children[2].label = T("ui.cancel_btn", lang)
        self.children[2].custom_id = f"bunker:cancel:{guild_id}"

    async def on_timeout(self):
        # Persistent view doesn't timeout automatically
        pass

    @discord.ui.button(style=discord.ButtonStyle.success)
    async def join(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: 
            await safe_response(interaction, embed=tech_embed("No game found.", "error"), ephemeral=True)
            return
        
        if game.add_player(interaction.user.id, interaction.user.display_name):
            await safe_response(interaction, embed=tech_embed(T("msg.joined", self.lang), "success"), ephemeral=True, delete_after=BRIEF_MSG_LIFETIME)
            if len(game.players) >= game.max_players:
                self.children[1].disabled = False
                self.children[1].style = discord.ButtonStyle.success
            
            emb = discord.Embed(title=T("ui.lobby_title", self.lang), description=f"{T('ui.host_label', self.lang)} <@{game.host_id}>\n{T('ui.players_label', self.lang)} {len(game.players)}/{game.max_players}", color=EmbedColors.LOBBY)
            await interaction.message.edit(embed=emb, view=self)
        else:
            await safe_response(interaction, embed=tech_embed(T("msg.no_seats", self.lang), "error"), ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.danger, disabled=True)
    async def start(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: return
        if interaction.user.id != game.host_id: return
        
        await game.start_game()
        # Delete lobby message to clean up
        await interaction.message.delete()
        
        await interaction.channel.send(embed=discord.Embed(title="☢️ INTRO", description=game.lore_text, color=EmbedColors.INTRO))
        
        game.board_message = await interaction.channel.send(embed=game.generate_board_embed())
        game.board_msg_id = game.board_message.id
        game.channel_id = interaction.channel.id
        
        game.dashboard_view = Dashboard(self.lang, game.guild_id)
        msg = await interaction.channel.send(view=game.dashboard_view)
        game.dash_msg_id = msg.id
        
        from .game import save_active_games
        asyncio.create_task(save_active_games())

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        game = get_game_safe(interaction)
        if not game: return
        if interaction.user.id != game.host_id: 
            await safe_response(interaction, embed=tech_embed(T("msg.only_host", self.lang), "error"), ephemeral=True)
            return

        # NEW CONFIRMATION LOGIC
        confirm_view = discord.ui.View(timeout=60)
        confirm_btn = discord.ui.Button(label="Yes, Cancel Game", style=discord.ButtonStyle.danger)

        async def confirm_callback(conf_interaction: discord.Interaction):
            from .game import delete_active_game
            await delete_active_game(interaction.guild.id)
            
            # Update ephemeral confirmation message
            await conf_interaction.response.edit_message(
                content=None,
                embed=tech_embed(T("msg.game_cancelled", self.lang), "error"),
                view=None
            )
            
            # Update original lobby message to show cancelled status
            try:
                if interaction.message:
                    await interaction.message.edit(content=None, embed=tech_embed(T("msg.game_cancelled", self.lang), "error"), view=None)
            except:
                pass

        confirm_btn.callback = confirm_callback
        confirm_view.add_item(confirm_btn)

        await safe_response(
            interaction,
            content="⚠️ Are you sure you want to cancel? This action cannot be undone.",
            view=confirm_view,
            ephemeral=True
        )