from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from enums import GameState, GameType
from games.arena_game import ArenaGame, ArenaRoundResult

if TYPE_CHECKING:
    from bot import MinigameBot


def _in_game_channel(bot: MinigameBot, interaction: discord.Interaction) -> bool:
    if not bot.current_game:
        return True
    if bot.current_game.game_channel_id is None:
        return True
    return interaction.channel_id == bot.current_game.game_channel_id


# ------------------------------------------------------------------
# Pagination view for /history_arena
# ------------------------------------------------------------------


class ArenaHistoryView(discord.ui.View):
    """Pagination view cho lịch sử vòng Đấu trường."""

    def __init__(self, game: ArenaGame, bot: MinigameBot, user_id: int):
        super().__init__(timeout=120)
        self.game = game
        self.bot = bot
        self.user_id = user_id
        self.current_page = len(game.round_history) - 1
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
    rr: ArenaRoundResult,
    bot: MinigameBot,
    page: Optional[int] = None,
    total_pages: Optional[int] = None,
) -> discord.Embed:
    title = f"📊 Vòng {rr.round_number}"
    if page is not None and total_pages is not None:
        title += f" (Trang {page}/{total_pages})"

    embed = discord.Embed(title=title, color=discord.Color.dark_red())

    # Stamina changes (don't reveal actions)
    change_lines = []
    for pid, delta in rr.stamina_changes.items():
        user = bot.get_user(pid)
        name = user.display_name if user else f"ID {pid}"
        if delta > 0:
            change_lines.append(f"**{name}**: +{delta} ❤️")
        elif delta < 0:
            change_lines.append(f"**{name}**: {delta} 💔")
        else:
            change_lines.append(f"**{name}**: ±0")

    embed.add_field(
        name="💫 Biến động Stamina",
        value="\n".join(change_lines) if change_lines else "Không có",
        inline=False,
    )

    # Deaths
    if rr.deaths:
        death_lines = []
        for pid in rr.deaths:
            user = bot.get_user(pid)
            name = user.display_name if user else f"ID {pid}"
            death_lines.append(f"💀 **{name}**")
        embed.add_field(
            name="☠️ Tử vong",
            value="\n".join(death_lines),
            inline=False,
        )

    return embed


class ArenaCommands(commands.Cog):
    """Lệnh dành riêng cho game Đấu trường sinh tử."""

    def __init__(self, bot: MinigameBot):
        self.bot = bot
        self._round_task: Optional[asyncio.Task] = None

    def cog_unload(self):
        if self._round_task and not self._round_task.done():
            self._round_task.cancel()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_running_game(self) -> Optional[ArenaGame]:
        g = self.bot.current_game
        if g and isinstance(g, ArenaGame) and g.state == GameState.RUNNING:
            return g
        return None

    # ------------------------------------------------------------------
    # Round loop
    # ------------------------------------------------------------------

    async def start_round_loop(self):
        """Vòng lặp tự động cho Đấu trường sinh tử."""
        game = self._get_running_game()
        if not game:
            return

        while game.state == GameState.RUNNING:
            game.current_actions.clear()
            alive = game.alive_players
            if len(alive) <= 1:
                break

            channel = (
                self.bot.get_channel(game.notif_channel_id)
                if game.notif_channel_id
                else None
            )
            if channel:
                next_round = game.current_round + 1
                M = game.settings["M"]
                embed = discord.Embed(
                    title=f"🔔 Vòng {next_round} bắt đầu!",
                    description=(
                        f"Dùng `/action_arena` để chọn hành động.\n"
                        f"Còn **{len(alive)}** chiến binh.\n"
                        f"Thời gian: **{game.settings['game_interval']}**"
                    ),
                    color=discord.Color.red(),
                )
                embed.add_field(
                    name="⚔️ Hành động",
                    value=(
                        f"**ATTACK** – Tấn công (-20 ST, gây 30 dmg)\n"
                        f"**DEFEND** – Phòng thủ (-10 ST, chặn 2 đòn)\n"
                        f"**CHARGE** – Tích lũy (+25 ST, nhận dmg x1.5)\n"
                        f"**DESTROY** – Hủy diệt (cần {2 * M} ST, -{M} ST, giết 1 người)\n"
                        f"**Không làm gì** cũng được"
                    ),
                    inline=False,
                )
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

            # Wait for round interval
            await asyncio.sleep(game.interval_seconds)

            if game.state != GameState.RUNNING:
                break

            # Resolve
            result = game.resolve_round()
            if not result:
                continue

            game.log_event(
                f"Vòng {result.round_number}: "
                f"deaths={result.deaths}"
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
                    embed = self._build_endgame_embed(game, reason, winners)
                    try:
                        await channel.send(embed=embed)
                    except discord.Forbidden:
                        pass

                self.bot.current_game = None
                self.bot.current_game_type = None
                return

    def _build_endgame_embed(
        self,
        game: ArenaGame,
        reason: str,
        winners: list[int],
    ) -> discord.Embed:
        embed = discord.Embed(
            title="🏁 GAME ĐẤU TRƯỜNG KẾT THÚC!",
            color=discord.Color.gold(),
        )
        if reason == "last_survivor":
            user = self.bot.get_user(winners[0]) if winners else None
            name = user.mention if user else f"ID {winners[0]}" if winners else "?"
            embed.description = f"🏆 Chiến binh cuối cùng: {name}"
        elif reason == "all_dead":
            embed.description = "💀 Tất cả đã ngã! Không ai thắng."
        else:
            embed.description = "Game kết thúc."

        # Final standings
        all_players = sorted(
            game.players.keys(),
            key=lambda pid: game.stamina.get(pid, 0),
            reverse=True,
        )
        lines = []
        for idx, pid in enumerate(all_players[:10], 1):
            user = self.bot.get_user(pid)
            name = user.display_name if user else f"ID {pid}"
            sta = game.stamina.get(pid, 0)
            status = " 💀" if pid in game.eliminated else ""
            medal = ["🥇", "🥈", "🥉"][idx - 1] if idx <= 3 else f"#{idx}"
            lines.append(f"{medal} **{name}**: {sta} ST{status}")
        embed.add_field(
            name="📊 Bảng xếp hạng",
            value="\n".join(lines) if lines else "Không có",
            inline=False,
        )
        return embed

    # ------------------------------------------------------------------
    # /action_arena
    # ------------------------------------------------------------------

    @app_commands.command(
        name="action_arena",
        description="[Đấu Trường] Chọn hành động: ATTACK/DEFEND/CHARGE/DESTROY",
    )
    @app_commands.describe(
        action="Hành động của bạn",
        target="Mục tiêu (cần cho ATTACK và DESTROY)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Tấn công (Attack)", value="attack"),
            app_commands.Choice(name="Phòng thủ (Defend)", value="defend"),
            app_commands.Choice(name="Tích lũy (Charge)", value="charge"),
            app_commands.Choice(name="Hủy diệt (Destroy)", value="destroy"),
            app_commands.Choice(name="Không làm gì", value="none"),
        ]
    )
    async def action_arena(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        target: Optional[discord.Member] = None,
    ):
        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game Đấu Trường nào đang chạy!", ephemeral=True
            )
            return

        target_id = target.id if target else None
        success, error = game.choose_action(
            interaction.user.id, action.value, target_id
        )
        if not success:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        labels = {
            "attack": "Tấn công ⚔️",
            "defend": "Phòng thủ 🛡️",
            "charge": "Tích lũy 💪",
            "destroy": "Hủy diệt 💥",
            "none": "Không làm gì 😴",
        }
        label = labels.get(action.value, action.value)
        msg = f"✅ Bạn đã chọn: **{label}**"
        if target:
            msg += f" → **{target.display_name}**"

        # Send via DM
        try:
            dm = await interaction.user.create_dm()
            await dm.send(msg)
            await interaction.response.send_message(
                "✅ Hành động đã được ghi nhận! Kiểm tra DM.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(msg, ephemeral=True)

    # ------------------------------------------------------------------
    # /stats_arena
    # ------------------------------------------------------------------

    @app_commands.command(
        name="stats_arena",
        description="[Đấu Trường] Xem Stamina hiện tại của mọi người",
    )
    async def stats_arena(self, interaction: discord.Interaction):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game Đấu Trường nào đang chạy!", ephemeral=True
            )
            return

        M = game.settings["M"]
        embed = discord.Embed(
            title="📊 Stamina Đấu Trường",
            description=f"Vòng hiện tại: **{game.current_round}** | M = **{M}**",
            color=discord.Color.dark_red(),
        )

        # Alive players sorted by stamina
        alive_lines = []
        sorted_alive = sorted(
            game.alive_players,
            key=lambda pid: game.stamina.get(pid, 0),
            reverse=True,
        )
        for pid in sorted_alive:
            user = self.bot.get_user(pid)
            name = user.display_name if user else f"ID {pid}"
            sta = game.stamina.get(pid, 0)
            bar_len = 10
            max_sta = 2 * M
            filled = int(sta / max_sta * bar_len) if max_sta else 0
            filled = min(max(filled, 0), bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            destroy_marker = " 💥" if sta >= 2 * M else ""
            alive_lines.append(f"**{name}**: {sta} ST |{bar}|{destroy_marker}")

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
                name=f"💀 Đã tử trận ({len(game.eliminated)})",
                value="\n".join(elim_lines),
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /history_arena
    # ------------------------------------------------------------------

    @app_commands.command(
        name="history_arena",
        description="[Đấu Trường] Xem biến động máu vòng trước",
    )
    async def history_arena(self, interaction: discord.Interaction):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game Đấu Trường nào đang chạy!", ephemeral=True
            )
            return

        if not game.round_history:
            await interaction.response.send_message(
                "❌ Chưa có vòng nào được chơi!", ephemeral=True
            )
            return

        view = ArenaHistoryView(game, self.bot, interaction.user.id)
        embed = view.get_page_embed()
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: MinigameBot):
    await bot.add_cog(ArenaCommands(bot))
