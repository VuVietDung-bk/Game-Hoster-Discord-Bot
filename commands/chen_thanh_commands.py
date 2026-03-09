from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from enums import GameState, GameType
from games.chen_thanh_game import ChenThanhGame, ChenThanhRoundResult

if TYPE_CHECKING:
    from bot import MinigameBot


def _in_game_channel(bot: MinigameBot, interaction: discord.Interaction) -> bool:
    if not bot.current_game:
        return True
    if bot.current_game.game_channel_id is None:
        return True
    return interaction.channel_id == bot.current_game.game_channel_id


# ------------------------------------------------------------------
# Pagination view for /history_chenthanh
# ------------------------------------------------------------------


class ChenThanhHistoryView(discord.ui.View):
    """Pagination view cho lịch sử vòng Chén Thánh."""

    def __init__(
        self, game: ChenThanhGame, bot: MinigameBot, user_id: int
    ):
        super().__init__(timeout=120)
        self.game = game
        self.bot = bot
        self.user_id = user_id
        self.current_page = len(game.round_history) - 1  # latest first
        self.update_buttons()

    @property
    def total_pages(self) -> int:
        return len(self.game.round_history)

    def update_buttons(self):
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1

    def get_page_embed(self) -> discord.Embed:
        rr = self.game.round_history[self.current_page]
        return _build_round_embed(
            rr, self.bot, self.current_page + 1, self.total_pages
        )

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.blurple)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ Chỉ người gọi lệnh mới dùng được!", ephemeral=True
            )
            return
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(
                embed=self.get_page_embed(), view=self
            )

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.blurple)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ Chỉ người gọi lệnh mới dùng được!", ephemeral=True
            )
            return
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(
                embed=self.get_page_embed(), view=self
            )


def _build_round_embed(
    rr: ChenThanhRoundResult,
    bot: MinigameBot,
    page: Optional[int] = None,
    total_pages: Optional[int] = None,
) -> discord.Embed:
    title = f"📊 Vòng {rr.round_number}"
    if page is not None and total_pages is not None:
        title += f" (Trang {page}/{total_pages})"

    embed = discord.Embed(title=title, color=discord.Color.dark_gold())

    embed.add_field(
        name="📈 Hành động",
        value=(
            f"Đóng góp: **{rr.contributor_count}** | "
            f"Đánh cắp: **{rr.stealer_count}**"
            + (f" | Không hành động: **{rr.no_action_count}**" if rr.no_action_count else "")
        ),
        inline=False,
    )

    embed.add_field(
        name="🏺 Hũ",
        value=f"Trước: **{rr.pot_before}** → Sau: **{rr.pot_after}**",
        inline=False,
    )

    # Dares
    if rr.dares:
        dare_lines = []
        for challenger_id, target_id, target_stole in rr.dares:
            c_user = bot.get_user(challenger_id)
            t_user = bot.get_user(target_id)
            c_name = c_user.display_name if c_user else f"ID {challenger_id}"
            t_name = t_user.display_name if t_user else f"ID {target_id}"
            result_text = "→ Target bị loại!" if target_stole else "→ Challenger bị loại!"
            dare_lines.append(f"⚔️ **{c_name}** thách thức **{t_name}** {result_text}")
        embed.add_field(
            name="🗡️ Thách thức",
            value="\n".join(dare_lines),
            inline=False,
        )

    return embed


class ChenThanhCommands(commands.Cog):
    """Lệnh dành riêng cho game Chén Thánh Phản Bội."""

    def __init__(self, bot: MinigameBot):
        self.bot = bot
        self._round_task: Optional[asyncio.Task] = None

    def cog_unload(self):
        if self._round_task and not self._round_task.done():
            self._round_task.cancel()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_running_game(self) -> Optional[ChenThanhGame]:
        g = self.bot.current_game
        if g and isinstance(g, ChenThanhGame) and g.state == GameState.RUNNING:
            return g
        return None

    # ------------------------------------------------------------------
    # Round loop
    # ------------------------------------------------------------------

    async def start_round_loop(self):
        """Bắt đầu vòng lặp tự động cho Chén Thánh."""
        game = self._get_running_game()
        if not game:
            return

        while game.state == GameState.RUNNING:
            game.current_actions.clear()
            game.current_dares.clear()
            alive = game.alive_players
            if len(alive) <= 1:
                break

            # Notify new round
            channel = (
                self.bot.get_channel(game.notif_channel_id)
                if game.notif_channel_id
                else None
            )
            if channel:
                next_round = game.current_round + 1
                embed = discord.Embed(
                    title=f"🔔 Vòng {next_round} bắt đầu!",
                    description=(
                        f"Mỗi người nhận **{game.settings['M']}** xu. Đóng góp = bỏ vào hũ. Đánh cắp = giữ lại.\n"
                        f"Dùng `/action_chenthanh` để chọn **Đóng góp** hoặc **Đánh cắp**.\n"
                        f"Còn **{len(alive)}** người chơi.\n"
                        f"Hũ hiện tại: **{game.pot}** xu.\n"
                        f"Thời gian: **{game.settings['game_interval']}**"
                    ),
                    color=discord.Color.green(),
                )
                if next_round > 1:
                    embed.add_field(
                        name="⚔️ Thách thức",
                        value=(
                            "Dùng `/dare` để thách thức người bạn nghi đã Đánh cắp!\n"
                            "Điều kiện: bạn đã Đóng góp ở vòng trước."
                        ),
                        inline=False,
                    )
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

            # Wait for the round interval
            await asyncio.sleep(game.interval_seconds)

            # Game may have been paused / ended during sleep
            if game.state != GameState.RUNNING:
                break

            # Resolve
            result = game.resolve_round()
            if not result:
                continue

            game.log_event(
                f"Vòng {result.round_number}: "
                f"contributors={result.contributor_count}, "
                f"stealers={result.stealer_count}, "
                f"pot={result.pot_before}→{result.pot_after}"
            )

            # Announce result
            if channel:
                embed = _build_round_embed(result, self.bot)
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

            # Check game over
            is_over, reason, winners = game.check_game_over()
            if is_over:
                game.state = GameState.ENDED
                game.log_event(f"Game kết thúc: {reason}, winners={winners}")
                if channel:
                    embed = await self._build_endgame_embed(game, reason, winners)
                    try:
                        await channel.send(embed=embed)
                    except discord.Forbidden:
                        pass

                self.bot.current_game = None
                self.bot.current_game_type = None
                return

    async def _build_endgame_embed(
        self,
        game: ChenThanhGame,
        reason: str,
        winners: list[int],
    ) -> discord.Embed:
        embed = discord.Embed(
            title="🏁 GAME CHÉN THÁNH KẾT THÚC!",
            color=discord.Color.gold(),
        )
        if reason == "target_reached":
            winner_names = []
            for pid in winners:
                user = self.bot.get_user(pid)
                winner_names.append(user.mention if user else f"ID {pid}")
            embed.description = (
                f"🏆 Đạt mục tiêu **{game.settings['N']}** xu!\n"
                f"Người thắng: {', '.join(winner_names)}"
            )
        elif reason == "last_survivor":
            user = self.bot.get_user(winners[0]) if winners else None
            name = user.mention if user else f"ID {winners[0]}" if winners else "?"
            embed.description = f"🏆 Người sống sót cuối cùng: {name}"
        elif reason == "all_dead":
            embed.description = "💀 Tất cả đã bị loại! Không ai thắng."
        else:
            embed.description = "Game kết thúc."

        # Show final standings
        all_players = sorted(
            game.players.keys(),
            key=lambda pid: game.balances.get(pid, 0),
            reverse=True,
        )
        lines = []
        for idx, pid in enumerate(all_players[:10], 1):
            user = self.bot.get_user(pid)
            name = user.display_name if user else f"ID {pid}"
            bal = game.balances.get(pid, 0)
            contribs = game.total_contributions.get(pid, 0)
            status = " 💀" if pid in game.eliminated else ""
            medal = ["🥇", "🥈", "🥉"][idx - 1] if idx <= 3 else f"#{idx}"
            lines.append(
                f"{medal} **{name}**: {bal} xu | {contribs} lần đóng góp{status}"
            )
        embed.add_field(
            name="📊 Bảng xếp hạng",
            value="\n".join(lines) if lines else "Không có",
            inline=False,
        )
        return embed

    # ------------------------------------------------------------------
    # /action_chenthanh
    # ------------------------------------------------------------------

    @app_commands.command(
        name="action_chenthanh",
        description="[Chén Thánh] Chọn Đóng góp hoặc Đánh cắp",
    )
    @app_commands.describe(action="contribute hoặc steal")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Đóng góp (Contribute)", value="contribute"),
            app_commands.Choice(name="Đánh cắp (Steal)", value="steal"),
        ]
    )
    async def action_chenthanh(
        self, interaction: discord.Interaction, action: app_commands.Choice[str]
    ):
        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game Chén Thánh nào đang chạy!", ephemeral=True
            )
            return

        success, error = game.choose_action(interaction.user.id, action.value)
        if not success:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        label = "Đóng góp 🤝" if action.value == "contribute" else "Đánh cắp 🗡️"
        await interaction.response.send_message(
            f"✅ Bạn đã chọn: **{label}**", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /dare
    # ------------------------------------------------------------------

    @app_commands.command(
        name="dare",
        description="[Chén Thánh] Thách thức người bạn nghi đã Đánh cắp",
    )
    @app_commands.describe(player="Người muốn thách thức")
    async def dare(
        self, interaction: discord.Interaction, player: discord.Member
    ):
        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game Chén Thánh nào đang chạy!", ephemeral=True
            )
            return

        success, error, dead_id = game.dare(interaction.user.id, player.id)
        if not success:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        # Announce result immediately
        dead_user = self.bot.get_user(dead_id) if dead_id else None
        dead_name = dead_user.display_name if dead_user else f"ID {dead_id}"
        challenger_name = interaction.user.display_name
        target_name = player.display_name

        if dead_id == player.id:
            result_text = (
                f"⚔️ **{challenger_name}** thách thức **{target_name}** → "
                f"Target đã **Đánh cắp** vòng trước → **{dead_name}** bị loại! 💀"
            )
        else:
            result_text = (
                f"⚔️ **{challenger_name}** thách thức **{target_name}** → "
                f"Target đã **Đóng góp** vòng trước → **{dead_name}** bị loại! 💀"
            )

        await interaction.response.send_message(result_text)

        # Check game over after dare
        is_over, reason, winners = game.check_game_over()
        if is_over:
            game.state = GameState.ENDED
            game.log_event(f"Game kết thúc: {reason}, winners={winners}")
            channel = (
                self.bot.get_channel(game.notif_channel_id)
                if game.notif_channel_id
                else None
            )
            if channel:
                embed = await self._build_endgame_embed(game, reason, winners)
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass
            # Cancel round loop
            if self._round_task and not self._round_task.done():
                self._round_task.cancel()
            self.bot.current_game = None
            self.bot.current_game_type = None

    # ------------------------------------------------------------------
    # /history_chenthanh
    # ------------------------------------------------------------------

    @app_commands.command(
        name="history_chenthanh",
        description="[Chén Thánh] Xem lịch sử các vòng",
    )
    async def history_chenthanh(self, interaction: discord.Interaction):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game Chén Thánh nào đang chạy!", ephemeral=True
            )
            return

        if not game.round_history:
            await interaction.response.send_message(
                "❌ Chưa có vòng nào được chơi!", ephemeral=True
            )
            return

        view = ChenThanhHistoryView(game, self.bot, interaction.user.id)
        embed = view.get_page_embed()
        await interaction.response.send_message(embed=embed, view=view)

    # ------------------------------------------------------------------
    # /status_chenthanh
    # ------------------------------------------------------------------

    @app_commands.command(
        name="status_chenthanh",
        description="[Chén Thánh] Xem trạng thái game",
    )
    async def status_chenthanh(self, interaction: discord.Interaction):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game Chén Thánh nào đang chạy!", ephemeral=True
            )
            return

        N = game.settings["N"]
        embed = discord.Embed(
            title="📋 Trạng thái Game Chén Thánh",
            description=(
                f"Vòng hiện tại: **{game.current_round}** | "
                f"Hũ: **{game.pot}** xu | Mục tiêu: **{N}** xu"
            ),
            color=discord.Color.dark_gold(),
        )

        # Alive players sorted by balance
        alive_lines = []
        sorted_alive = sorted(
            game.alive_players,
            key=lambda pid: game.balances.get(pid, 0),
            reverse=True,
        )
        for pid in sorted_alive:
            user = self.bot.get_user(pid)
            name = user.display_name if user else f"ID {pid}"
            bal = game.balances.get(pid, 0)
            bar_len = 10
            filled = int(bal / N * bar_len) if N else 0
            filled = min(filled, bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            alive_lines.append(f"**{name}**: {bal}/{N} |{bar}|")

        embed.add_field(
            name=f"✅ Còn sống ({len(sorted_alive)})",
            value="\n".join(alive_lines) if alive_lines else "Không có",
            inline=False,
        )

        # Eliminated
        if game.eliminated:
            elim_lines = []
            for idx, pid in enumerate(game.eliminated, 1):
                user = self.bot.get_user(pid)
                name = user.display_name if user else f"ID {pid}"
                elim_lines.append(f"{idx}. ~~{name}~~")
            embed.add_field(
                name=f"💀 Đã bị loại ({len(game.eliminated)})",
                value="\n".join(elim_lines),
                inline=False,
            )

        await interaction.response.send_message(embed=embed)


    # ------------------------------------------------------------------
    # /stats_chenthanh
    # ------------------------------------------------------------------

    @app_commands.command(
        name="stats_chenthanh",
        description="[Chén Thánh] Xem số tiền hiện tại của mình",
    )
    async def stats_chenthanh(self, interaction: discord.Interaction):
        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game Chén Thánh nào đang chạy!", ephemeral=True
            )
            return

        pid = interaction.user.id
        if pid not in game.players:
            await interaction.response.send_message(
                "❌ Bạn chưa tham gia game!", ephemeral=True
            )
            return

        bal = game.balances.get(pid, 0)
        contribs = game.total_contributions.get(pid, 0)
        alive = pid not in game.eliminated
        N = game.settings["N"]

        embed = discord.Embed(
            title=f"📊 Thống kê của {interaction.user.display_name}",
            color=discord.Color.dark_gold(),
        )
        embed.add_field(name="💰 Số xu", value=f"{bal:,} xu", inline=True)
        embed.add_field(name="🎯 Mục tiêu", value=f"{N:,} xu", inline=True)
        embed.add_field(
            name="🤝 Số lần đóng góp", value=str(contribs), inline=True
        )
        embed.add_field(
            name="❤️ Trạng thái",
            value="Còn sống" if alive else "💀 Đã bị loại",
            inline=True,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: MinigameBot):
    await bot.add_cog(ChenThanhCommands(bot))
