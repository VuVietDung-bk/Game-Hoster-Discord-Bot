from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from enums import GameState, GameType
from games.jco_game import JCoGame, JCoRoundResult

if TYPE_CHECKING:
    from bot import MinigameBot


def _in_game_channel(bot: MinigameBot, interaction: discord.Interaction) -> bool:
    if not bot.current_game:
        return True
    if bot.current_game.game_channel_id is None:
        return True
    return interaction.channel_id == bot.current_game.game_channel_id


# ------------------------------------------------------------------
# Pagination view for /checkNumber (DM)
# ------------------------------------------------------------------


class CheckNumberView(discord.ui.View):
    """Pagination view cho danh sách số trên gáy người khác."""

    PER_PAGE = 10

    def __init__(self, data: list[tuple[int, int]], bot: MinigameBot, user_id: int):
        super().__init__(timeout=120)
        self.data = data  # [(player_id, number)]
        self.bot = bot
        self.user_id = user_id
        self.current_page = 0
        self.total_pages = max(1, math.ceil(len(data) / self.PER_PAGE))
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1

    def get_page_embed(self) -> discord.Embed:
        start = self.current_page * self.PER_PAGE
        end = start + self.PER_PAGE
        page_data = self.data[start:end]

        embed = discord.Embed(
            title="👁️ Số trên gáy người chơi khác",
            description=f"Trang {self.current_page + 1}/{self.total_pages}",
            color=discord.Color.teal(),
        )
        lines = []
        for pid, num in page_data:
            user = self.bot.get_user(pid)
            name = user.display_name if user else f"ID {pid}"
            lines.append(f"• **{name}**: `{num}`")
        embed.add_field(
            name="Danh sách",
            value="\n".join(lines) if lines else "Không có",
            inline=False,
        )
        return embed

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.blurple)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Không phải của bạn!", ephemeral=True)
            return
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Không phải của bạn!", ephemeral=True)
            return
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_page_embed(), view=self)


# ------------------------------------------------------------------
# Pagination view for /history_jco
# ------------------------------------------------------------------


class JCoHistoryView(discord.ui.View):
    """Pagination view cho lịch sử loại."""

    PER_PAGE = 5

    def __init__(self, game: JCoGame, bot: MinigameBot, user_id: int):
        super().__init__(timeout=120)
        self.game = game
        self.bot = bot
        self.user_id = user_id
        self.current_page = 0
        self.total_pages = max(1, math.ceil(len(game.round_history) / self.PER_PAGE))
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1

    def get_page_embed(self) -> discord.Embed:
        start = self.current_page * self.PER_PAGE
        end = start + self.PER_PAGE
        page_rounds = self.game.round_history[start:end]

        embed = discord.Embed(
            title="📜 Lịch sử loại - J Cơ",
            description=f"Trang {self.current_page + 1}/{self.total_pages}",
            color=discord.Color.dark_red(),
        )

        for rr in page_rounds:
            def names(pids):
                n = []
                for pid in pids:
                    user = self.bot.get_user(pid)
                    n.append(user.display_name if user else f"ID {pid}")
                return ", ".join(n) if n else "Không ai"

            value_parts = []
            if rr.eliminated:
                value_parts.append(f"💀 Đoán sai/không trả lời: {names(rr.eliminated)}")
            if rr.voted_out:
                label = "🗳️ Bị vote loại"
                if rr.jco_voted_out:
                    label += " **(J Cơ!)**"
                value_parts.append(f"{label}: {names(rr.voted_out)}")
            if rr.rotation_happened:
                value_parts.append("🔄 Đảo vai J Cơ đã xảy ra!")
            if not value_parts:
                value_parts.append("Không ai bị loại")

            embed.add_field(
                name=f"Vòng {rr.round_number}",
                value="\n".join(value_parts),
                inline=False,
            )

        return embed

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.blurple)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Không phải của bạn!", ephemeral=True)
            return
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Không phải của bạn!", ephemeral=True)
            return
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_page_embed(), view=self)


# ------------------------------------------------------------------
# Cog
# ------------------------------------------------------------------


class JCoCommands(commands.Cog):
    """Lệnh dành riêng cho game J Cơ."""

    def __init__(self, bot: MinigameBot):
        self.bot = bot
        self._round_task: Optional[asyncio.Task] = None

    def cog_unload(self):
        if self._round_task and not self._round_task.done():
            self._round_task.cancel()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_running_game(self) -> Optional[JCoGame]:
        g = self.bot.current_game
        if g and isinstance(g, JCoGame) and g.state == GameState.RUNNING:
            return g
        return None

    # ------------------------------------------------------------------
    # Round loop
    # ------------------------------------------------------------------

    async def start_round_loop(self):
        """Vòng lặp tự động cho J Cơ."""
        game = self._get_running_game()
        if not game:
            return

        while game.state == GameState.RUNNING:
            game.current_answers.clear()
            game.current_votes.clear()
            alive = game.alive_players
            if len(alive) <= 1:
                break

            # Thông báo vòng mới
            channel = (
                self.bot.get_channel(game.notif_channel_id)
                if game.notif_channel_id
                else None
            )
            if channel:
                M = game.settings["M"]
                round_num = game.current_round + 1
                embed = discord.Embed(
                    title=f"🔔 Vòng {round_num} bắt đầu!",
                    description=(
                        f"Dùng `/answer` để nhập số của bạn (1-{M}).\n"
                        f"Dùng `/checknumber` để xem số người khác (qua DM).\n"
                        f"Còn **{len(alive)}** người chơi.\n"
                        f"Thời gian: **{game.settings['game_interval']}**"
                    ),
                    color=discord.Color.green(),
                )
                if round_num >= 2:
                    embed.add_field(
                        name="🗳️ Vote",
                        value="Dùng `/vote` để vote loại người nghi ngờ là J Cơ.",
                        inline=False,
                    )
                if game.settings["rotation"]:
                    embed.add_field(
                        name="🔄 Đảo vai",
                        value=f"Chuỗi vòng không loại: **{game.no_elimination_streak}/3**",
                        inline=False,
                    )
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

            # Đợi hết thời gian vòng
            await asyncio.sleep(game.interval_seconds)

            if game.state != GameState.RUNNING:
                break

            # Resolve vòng
            result = game.resolve_round()
            if not result:
                continue

            # Announce
            if channel:
                embed = self._build_result_embed(result)
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

                # Notify rotation secretly — chỉ ẩn danh, thông báo chung có "đảo vai xảy ra"
                if result.rotation_happened:
                    embed2 = discord.Embed(
                        title="🔄 ĐẢO VAI J CƠ!",
                        description="3 vòng liên tiếp không ai bị loại. J Cơ đã được đổi bí mật!",
                        color=discord.Color.red(),
                    )
                    try:
                        await channel.send(embed=embed2)
                    except discord.Forbidden:
                        pass

            # Check game over
            is_over, reason, winner_id = game.check_game_over()
            if is_over:
                game.state = GameState.ENDED
                game.log_event(f"Game kết thúc: {reason}")

                if channel:
                    embed = self._build_game_over_embed(game, reason, winner_id)
                    try:
                        await channel.send(embed=embed)
                    except discord.Forbidden:
                        pass

                self.bot.current_game = None
                self.bot.current_game_type = None
                return

    def _build_result_embed(self, rr: JCoRoundResult) -> discord.Embed:
        embed = discord.Embed(
            title=f"📊 Kết quả Vòng {rr.round_number}",
            color=discord.Color.orange(),
        )

        def names(pids):
            n = []
            for pid in pids:
                user = self.bot.get_user(pid)
                n.append(user.display_name if user else f"ID {pid}")
            return ", ".join(n) if n else "Không ai"

        if rr.eliminated:
            embed.add_field(
                name="💀 Bị loại (đoán sai / không trả lời)",
                value=names(rr.eliminated),
                inline=False,
            )
        if rr.voted_out:
            label = "🗳️ Bị vote loại"
            if rr.jco_voted_out:
                label += " — **ĐÓ LÀ J CƠ!** 🎉"
            embed.add_field(name=label, value=names(rr.voted_out), inline=False)

        if not rr.eliminated and not rr.voted_out:
            embed.add_field(
                name="✅ An toàn",
                value="Không ai bị loại vòng này!",
                inline=False,
            )

        return embed

    def _build_game_over_embed(
        self, game: JCoGame, reason: str, winner_id: Optional[int]
    ) -> discord.Embed:
        if reason == "jco_voted_out":
            # Everyone else wins
            jco_user = self.bot.get_user(game.jco_id) if game.jco_id else None
            jco_name = jco_user.display_name if jco_user else f"ID {game.jco_id}"
            alive = game.alive_players
            winners = [pid for pid in alive if pid != game.jco_id]
            winner_names = []
            for pid in winners:
                u = self.bot.get_user(pid)
                winner_names.append(u.display_name if u else f"ID {pid}")

            embed = discord.Embed(
                title="🏁 GAME KẾT THÚC — J CƠ BỊ LỘ!",
                description=(
                    f"🃏 J Cơ là: **{jco_name}**\n"
                    f"🏆 Người chiến thắng: {', '.join(winner_names) if winner_names else 'Không ai'}"
                ),
                color=discord.Color.gold(),
            )
        elif reason == "jco_last":
            jco_user = self.bot.get_user(winner_id) if winner_id else None
            jco_name = jco_user.display_name if jco_user else f"ID {winner_id}"
            embed = discord.Embed(
                title="🏁 GAME KẾT THÚC — J CƠ CHIẾN THẮNG!",
                description=f"🃏 J Cơ **{jco_name}** đã lừa được tất cả!",
                color=discord.Color.dark_red(),
            )
        else:
            embed = discord.Embed(
                title="🏁 GAME KẾT THÚC",
                description="Game đã kết thúc.",
                color=discord.Color.gold(),
            )
        return embed

    # ------------------------------------------------------------------
    # /checknumber
    # ------------------------------------------------------------------

    @app_commands.command(
        name="checknumber",
        description="[J Cơ] Xem số trên gáy người khác (gửi qua DM)",
    )
    async def check_number(self, interaction: discord.Interaction):
        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game J Cơ nào đang chạy!", ephemeral=True
            )
            return

        success, error, data = game.get_others_numbers(interaction.user.id)
        if not success:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        view = CheckNumberView(data, self.bot, interaction.user.id)
        embed = view.get_page_embed()

        try:
            dm = await interaction.user.create_dm()
            await dm.send(embed=embed, view=view)
            await interaction.response.send_message(
                "✅ Đã gửi danh sách số qua DM!", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Không thể gửi DM. Hãy bật nhận tin nhắn từ thành viên server!",
                ephemeral=True,
            )

    # ------------------------------------------------------------------
    # /answer
    # ------------------------------------------------------------------

    @app_commands.command(
        name="answer", description="[J Cơ] Đoán số của bạn cho vòng hiện tại"
    )
    @app_commands.describe(number="Số bạn đoán")
    async def answer_cmd(self, interaction: discord.Interaction, number: int):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game J Cơ nào đang chạy!", ephemeral=True
            )
            return

        success, error = game.answer(interaction.user.id, number)
        if not success:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        await interaction.response.send_message(
            f"✅ Bạn đã trả lời số **{number}**", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /history_jco
    # ------------------------------------------------------------------

    @app_commands.command(
        name="history_jco",
        description="[J Cơ] Xem lịch sử người bị loại các vòng trước",
    )
    async def history_jco(self, interaction: discord.Interaction):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game J Cơ nào đang chạy!", ephemeral=True
            )
            return

        if not game.round_history:
            await interaction.response.send_message(
                "❌ Chưa có vòng nào được chơi!", ephemeral=True
            )
            return

        view = JCoHistoryView(game, self.bot, interaction.user.id)
        embed = view.get_page_embed()
        await interaction.response.send_message(embed=embed, view=view)

    # ------------------------------------------------------------------
    # /status_jco
    # ------------------------------------------------------------------

    @app_commands.command(
        name="status_jco",
        description="[J Cơ] Xem số người còn lại và chuỗi vòng không loại",
    )
    async def status_jco(self, interaction: discord.Interaction):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game J Cơ nào đang chạy!", ephemeral=True
            )
            return

        alive = game.alive_players
        embed = discord.Embed(
            title="📋 Trạng thái Game J Cơ",
            description=f"Vòng hiện tại: **{game.current_round}**",
            color=discord.Color.dark_teal(),
        )
        embed.add_field(
            name="👥 Người chơi còn lại",
            value=str(len(alive)),
            inline=True,
        )
        embed.add_field(
            name="💀 Đã bị loại",
            value=str(len(game.eliminated)),
            inline=True,
        )
        if game.settings["rotation"]:
            embed.add_field(
                name="🔄 Chuỗi vòng không loại",
                value=f"**{game.no_elimination_streak}/3**"
                + (" ⚠️ Sắp đảo vai!" if game.no_elimination_streak >= 2 else ""),
                inline=False,
            )
        else:
            embed.add_field(
                name="🔄 Đảo vai", value="Tắt", inline=False
            )

        # Show alive player names
        alive_names = []
        for pid in alive:
            user = self.bot.get_user(pid)
            alive_names.append(user.display_name if user else f"ID {pid}")
        embed.add_field(
            name="✅ Danh sách sống sót",
            value=", ".join(alive_names) if alive_names else "Không có",
            inline=False,
        )

        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /mirror
    # ------------------------------------------------------------------

    @app_commands.command(
        name="mirror",
        description="[J Cơ] Dùng gương xem số của mình (1 lần duy nhất)",
    )
    async def mirror(self, interaction: discord.Interaction):
        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game J Cơ nào đang chạy!", ephemeral=True
            )
            return

        success, error, number = game.use_mirror(interaction.user.id)
        if not success:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        await interaction.response.send_message(
            f"🪞 Số trên gáy bạn là: **{number}**", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /vote
    # ------------------------------------------------------------------

    @app_commands.command(
        name="vote", description="[J Cơ] Vote loại một người chơi"
    )
    @app_commands.describe(player="Người bạn muốn vote")
    async def vote(self, interaction: discord.Interaction, player: discord.User):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game J Cơ nào đang chạy!", ephemeral=True
            )
            return

        success, error = game.vote(interaction.user.id, player.id)
        if not success:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        await interaction.response.send_message(
            f"🗳️ Bạn đã vote **{player.display_name}**", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /cheat_jco (J Cơ only)
    # ------------------------------------------------------------------

    @app_commands.command(
        name="cheat_jco", description="[J Cơ] Xem số của mình (chỉ J Cơ)"
    )
    async def cheat_jco(self, interaction: discord.Interaction):
        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game J Cơ nào đang chạy!", ephemeral=True
            )
            return

        success, error, number = game.cheat(interaction.user.id)
        if not success:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        await interaction.response.send_message(
            f"🃏 Số trên gáy bạn là: **{number}**", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /pause_jco (host only)
    # ------------------------------------------------------------------

    @app_commands.command(
        name="pause_jco", description="[J Cơ] Tạm dừng game (host)"
    )
    async def pause_jco(self, interaction: discord.Interaction):
        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game J Cơ nào đang chạy!", ephemeral=True
            )
            return

        if game.host_id != interaction.user.id:
            await interaction.response.send_message(
                "❌ Chỉ host mới có quyền tạm dừng!", ephemeral=True
            )
            return

        game.state = GameState.PAUSED
        game.log_event("Game J Cơ tạm dừng")
        await interaction.response.send_message("⏸️ Game J Cơ đã tạm dừng!")

    # ------------------------------------------------------------------
    # /unpause_jco (host only)
    # ------------------------------------------------------------------

    @app_commands.command(
        name="unpause_jco", description="[J Cơ] Tiếp tục game (host)"
    )
    async def unpause_jco(self, interaction: discord.Interaction):
        if not self.bot.current_game:
            await interaction.response.send_message(
                "❌ Không có game nào!", ephemeral=True
            )
            return

        game = self.bot.current_game
        if not isinstance(game, JCoGame):
            await interaction.response.send_message(
                "❌ Không có game J Cơ!", ephemeral=True
            )
            return

        if game.state != GameState.PAUSED:
            await interaction.response.send_message(
                "❌ Game không đang tạm dừng!", ephemeral=True
            )
            return

        if game.host_id != interaction.user.id:
            await interaction.response.send_message(
                "❌ Chỉ host mới có quyền!", ephemeral=True
            )
            return

        game.state = GameState.RUNNING
        game.log_event("Game J Cơ tiếp tục")
        await interaction.response.send_message("▶️ Game J Cơ tiếp tục!")

        # Restart round loop
        if self._round_task is None or self._round_task.done():
            self._round_task = asyncio.create_task(self.start_round_loop())


async def setup(bot: MinigameBot):
    await bot.add_cog(JCoCommands(bot))
