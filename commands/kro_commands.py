from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from enums import GameState, GameType
from games.kro_game import KRoGame, RoundResult

if TYPE_CHECKING:
    from bot import MinigameBot


def _in_game_channel(bot: MinigameBot, interaction: discord.Interaction) -> bool:
    if not bot.current_game:
        return True
    if bot.current_game.game_channel_id is None:
        return True
    return interaction.channel_id == bot.current_game.game_channel_id


class HistoryView(discord.ui.View):
    """Pagination view cho /history."""

    def __init__(self, game: KRoGame, bot: MinigameBot, user_id: int):
        super().__init__(timeout=120)
        self.game = game
        self.bot = bot
        self.user_id = user_id
        self.current_page = len(game.round_history) - 1  # start from latest
        self.update_buttons()

    @property
    def total_pages(self) -> int:
        return len(self.game.round_history)

    def update_buttons(self):
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1

    def get_page_embed(self) -> discord.Embed:
        rr = self.game.round_history[self.current_page]
        return _build_round_embed(rr, self.bot, self.current_page + 1, self.total_pages)

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.blurple)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ Chỉ người gọi lệnh mới có thể dùng nút này!", ephemeral=True
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
                "❌ Chỉ người gọi lệnh mới có thể dùng nút này!", ephemeral=True
            )
            return
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(
                embed=self.get_page_embed(), view=self
            )


def _build_round_embed(
    rr: RoundResult,
    bot: MinigameBot,
    page: Optional[int] = None,
    total_pages: Optional[int] = None,
) -> discord.Embed:
    title = f"📊 Vòng {rr.round_number}"
    if page is not None and total_pages is not None:
        title += f" (Trang {page}/{total_pages})"

    embed = discord.Embed(title=title, color=discord.Color.blue())

    # Picks
    pick_lines = []
    for pid, num in rr.picks.items():
        user = bot.get_user(pid)
        name = user.display_name if user else f"ID {pid}"
        marker = " ⛔" if num in rr.invalid_numbers else ""
        pick_lines.append(f"• **{name}**: {num}{marker}")
    embed.add_field(
        name="🔢 Số đã chọn",
        value="\n".join(pick_lines) if pick_lines else "Không ai chọn",
        inline=False,
    )

    # Stats
    if rr.average is not None:
        embed.add_field(
            name="📈 Trung bình", value=f"{rr.average:.2f}", inline=True
        )
        embed.add_field(
            name="🎯 Mục tiêu (×0.8)", value=f"{rr.target:.2f}", inline=True
        )
    else:
        embed.add_field(
            name="📈 Trung bình", value="N/A (tất cả bị vô hiệu)", inline=True
        )

    if rr.invalid_numbers:
        embed.add_field(
            name="⛔ Số bị vô hiệu",
            value=", ".join(str(n) for n in rr.invalid_numbers),
            inline=True,
        )

    # Winners / losers
    def mention_list(pids):
        names = []
        for pid in pids:
            user = bot.get_user(pid)
            names.append(user.display_name if user else f"ID {pid}")
        return ", ".join(names) if names else "Không có"

    if rr.rule_0_100_winner:
        user = bot.get_user(rr.rule_0_100_winner)
        name = user.display_name if user else f"ID {rr.rule_0_100_winner}"
        embed.add_field(
            name="🏆 Thắng (luật 0 vs 100)",
            value=name,
            inline=False,
        )
    elif rr.special_winner:
        user = bot.get_user(rr.special_winner)
        name = user.display_name if user else f"ID {rr.special_winner}"
        embed.add_field(
            name="🏆 Thắng tuyệt đối (đúng mục tiêu!)",
            value=name,
            inline=False,
        )
    else:
        embed.add_field(
            name="🏆 Thắng", value=mention_list(rr.winners), inline=True
        )

    embed.add_field(
        name=f"💀 Thua (+{rr.penalty} phạt)",
        value=mention_list(rr.losers),
        inline=True,
    )

    return embed


class KRoCommands(commands.Cog):
    """Lệnh dành riêng cho game K Rô."""

    def __init__(self, bot: MinigameBot):
        self.bot = bot
        self._round_task: Optional[asyncio.Task] = None

    def cog_unload(self):
        if self._round_task and not self._round_task.done():
            self._round_task.cancel()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_running_game(self) -> Optional[KRoGame]:
        g = self.bot.current_game
        if g and isinstance(g, KRoGame) and g.state == GameState.RUNNING:
            return g
        return None

    # ------------------------------------------------------------------
    # Round loop
    # ------------------------------------------------------------------

    async def start_round_loop(self):
        """Bắt đầu vòng lặp tự động cho K Rô."""
        game = self._get_running_game()
        if not game:
            return

        while game.state == GameState.RUNNING:
            game.current_picks.clear()
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
                alive_count = len(alive)
                embed = discord.Embed(
                    title=f"🔔 Vòng {game.current_round + 1} bắt đầu!",
                    description=(
                        f"Dùng `/pick` để chọn số từ **0** đến **100**.\n"
                        f"Còn **{alive_count}** người chơi.\n"
                        f"Thời gian: **{game.settings['game_interval']}**"
                    ),
                    color=discord.Color.green(),
                )
                rules = game.get_active_rules()
                if rules:
                    embed.add_field(
                        name="📜 Luật bổ sung đang kích hoạt",
                        value="\n".join(rules),
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
                f"Vòng {result.round_number}: target={result.target}, "
                f"winners={result.winners}, losers={result.losers}"
            )

            # Announce result
            if channel:
                embed = _build_round_embed(result, self.bot)
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

            # Check game over
            is_over, winner_id = game.check_game_over()
            if is_over:
                game.state = GameState.ENDED
                game.log_event("Game kết thúc")
                if channel:
                    if winner_id:
                        user = self.bot.get_user(winner_id)
                        name = user.mention if user else f"ID {winner_id}"
                        embed = discord.Embed(
                            title="🏁 GAME KẾT THÚC!",
                            description=f"🏆 Người chiến thắng: {name}",
                            color=discord.Color.gold(),
                        )
                    else:
                        embed = discord.Embed(
                            title="🏁 GAME KẾT THÚC!",
                            description="Không còn ai sống sót!",
                            color=discord.Color.gold(),
                        )
                    try:
                        await channel.send(embed=embed)
                    except discord.Forbidden:
                        pass

                self.bot.current_game = None
                self.bot.current_game_type = None
                return

    # ------------------------------------------------------------------
    # /pick
    # ------------------------------------------------------------------

    @app_commands.command(name="pick", description="[K Rô] Chọn một số từ 0 đến 100")
    @app_commands.describe(number="Số bạn muốn chọn (0-100)")
    async def pick(self, interaction: discord.Interaction, number: int):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game K Rô nào đang chạy!", ephemeral=True
            )
            return

        success, error = game.pick(interaction.user.id, number)
        if not success:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        await interaction.response.send_message(
            f"✅ Bạn đã chọn số **{number}**", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /rules_update
    # ------------------------------------------------------------------

    @app_commands.command(
        name="rules_update",
        description="[K Rô] Xem luật bổ sung đang kích hoạt",
    )
    async def rules_update(self, interaction: discord.Interaction):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game K Rô nào đang chạy!", ephemeral=True
            )
            return

        rules = game.get_active_rules()
        alive_count = len(game.alive_players)
        eliminated_count = len(game.eliminated)

        embed = discord.Embed(
            title="📜 Luật bổ sung đang kích hoạt",
            description=(
                f"Người chơi còn lại: **{alive_count}** | "
                f"Đã bị loại: **{eliminated_count}**"
            ),
            color=discord.Color.purple(),
        )

        if rules:
            embed.add_field(
                name="Luật hiện tại",
                value="\n".join(rules),
                inline=False,
            )
        else:
            embed.add_field(
                name="Luật hiện tại",
                value="Chưa có luật bổ sung nào được kích hoạt (>4 người chơi).",
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /status
    # ------------------------------------------------------------------

    @app_commands.command(
        name="status", description="[K Rô] Xem điểm phạt và danh sách bị loại"
    )
    async def status(self, interaction: discord.Interaction):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game K Rô nào đang chạy!", ephemeral=True
            )
            return

        alive_data, eliminated_ids = game.get_status_embed_data()
        max_pen = game.settings["max_penalty"]

        embed = discord.Embed(
            title="📋 Trạng thái Game K Rô",
            description=f"Vòng hiện tại: **{game.current_round}** | Điểm phạt tối đa: **{max_pen}**",
            color=discord.Color.blue(),
        )

        # Alive players
        alive_lines = []
        for pid, pen in alive_data:
            user = self.bot.get_user(pid)
            name = user.display_name if user else f"ID {pid}"
            bar_len = 10
            filled = int(pen / max_pen * bar_len) if max_pen else 0
            bar = "█" * filled + "░" * (bar_len - filled)
            alive_lines.append(f"**{name}**: {pen}/{max_pen} |{bar}|")

        embed.add_field(
            name=f"✅ Còn sống ({len(alive_data)})",
            value="\n".join(alive_lines) if alive_lines else "Không có",
            inline=False,
        )

        # Eliminated
        if eliminated_ids:
            elim_lines = []
            for idx, pid in enumerate(eliminated_ids, 1):
                user = self.bot.get_user(pid)
                name = user.display_name if user else f"ID {pid}"
                elim_lines.append(f"{idx}. ~~{name}~~")
            embed.add_field(
                name=f"💀 Đã bị loại ({len(eliminated_ids)})",
                value="\n".join(elim_lines),
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /history
    # ------------------------------------------------------------------

    @app_commands.command(
        name="history", description="[K Rô] Xem lại kết quả các vòng trước"
    )
    async def history(self, interaction: discord.Interaction):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game K Rô nào đang chạy!", ephemeral=True
            )
            return

        if not game.round_history:
            await interaction.response.send_message(
                "❌ Chưa có vòng nào được chơi!", ephemeral=True
            )
            return

        view = HistoryView(game, self.bot, interaction.user.id)
        embed = view.get_page_embed()
        await interaction.response.send_message(embed=embed, view=view)

    # ------------------------------------------------------------------
    # /lastround
    # ------------------------------------------------------------------

    @app_commands.command(
        name="lastround", description="[K Rô] Xem nhanh kết quả vòng gần nhất"
    )
    async def last_round(self, interaction: discord.Interaction):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game K Rô nào đang chạy!", ephemeral=True
            )
            return

        if not game.round_history:
            await interaction.response.send_message(
                "❌ Chưa có vòng nào được chơi!", ephemeral=True
            )
            return

        rr = game.round_history[-1]
        embed = _build_round_embed(rr, self.bot)
        await interaction.response.send_message(embed=embed)


async def setup(bot: MinigameBot):
    await bot.add_cog(KRoCommands(bot))
