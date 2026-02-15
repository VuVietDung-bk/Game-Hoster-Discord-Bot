from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from enums import GameInterval, GameState, GameType
from game_factory import GameFactory
from games.base_game import BaseGame
from games.li_xi_game import LiXiNgayTetGame

if TYPE_CHECKING:
    from bot import MinigameBot


class HostCommands(commands.Cog):
    """Lệnh dành cho host."""

    def __init__(self, bot: MinigameBot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /host
    # ------------------------------------------------------------------

    @app_commands.command(name="host", description="Khởi tạo game mới")
    @app_commands.describe(game_type="Loại game muốn tạo")
    async def host(self, interaction: discord.Interaction, game_type: str):
        if self.bot.current_game and self.bot.current_game.state not in (
            GameState.IDLE,
            GameState.ENDED,
        ):
            await interaction.response.send_message(
                "❌ Đang có game khác diễn ra!", ephemeral=True
            )
            return

        try:
            gt = GameType(game_type.lower())
        except ValueError:
            await interaction.response.send_message(
                "❌ Loại game không hợp lệ!", ephemeral=True
            )
            return

        game = GameFactory.create_game(gt, interaction.user.id)
        if not game:
            await interaction.response.send_message(
                "❌ Không thể tạo game!", ephemeral=True
            )
            return

        self.bot.current_game = game
        self.bot.current_game_type = gt

        embed = discord.Embed(
            title="🎮 Game mới đã được tạo!",
            description=(
                f"**Host:** {interaction.user.mention}\n**Game:** {gt.value}"
            ),
            color=discord.Color.green(),
        )
        embed.add_field(name="Trạng thái", value="Đang mở đăng ký", inline=False)
        embed.add_field(
            name="Hướng dẫn", value="Dùng `/joingame` để tham gia!", inline=False
        )

        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /settinggame
    # ------------------------------------------------------------------

    @app_commands.command(name="settinggame", description="Chỉnh thông số game")
    async def setting_game(self, interaction: discord.Interaction):
        if not self.bot.current_game:
            await interaction.response.send_message(
                "❌ Không có game nào đang diễn ra!", ephemeral=True
            )
            return

        if self.bot.current_game.host_id != interaction.user.id:
            await interaction.response.send_message(
                "❌ Chỉ host mới có quyền setting game!", ephemeral=True
            )
            return

        if self.bot.current_game.state != GameState.REGISTERING:
            await interaction.response.send_message(
                "❌ Chỉ có thể setting khi đang mở đăng ký!", ephemeral=True
            )
            return

        class SettingModal(discord.ui.Modal, title="Cài đặt Game"):
            def __init__(modal_self, game: BaseGame):
                super().__init__()
                modal_self.game = game

                if isinstance(game, LiXiNgayTetGame):
                    modal_self.m_input = discord.ui.TextInput(
                        label="M (Tiền ban đầu: 10-10000)",
                        default=str(game.settings["M"]),
                        max_length=5,
                    )
                    modal_self.add_item(modal_self.m_input)

                    modal_self.n_input = discord.ui.TextInput(
                        label="N (Ngưỡng tuổi: 5-500)",
                        default=str(game.settings["N"]),
                        max_length=3,
                    )
                    modal_self.add_item(modal_self.n_input)

                    modal_self.player_limit = discord.ui.TextInput(
                        label="Giới hạn người chơi (10-100)",
                        default=str(game.settings["player_limit"]),
                        max_length=3,
                    )
                    modal_self.add_item(modal_self.player_limit)

                    modal_self.duration = discord.ui.TextInput(
                        label="Thời hạn game (ngày: 2-20)",
                        default=str(game.settings["game_duration_days"]),
                        max_length=2,
                    )
                    modal_self.add_item(modal_self.duration)

                    modal_self.interval_input = discord.ui.TextInput(
                        label="Chu kỳ ngày (10m / 12h / 1d / 2d)",
                        default=str(game.settings["game_interval"].value),
                        max_length=4,
                    )
                    modal_self.add_item(modal_self.interval_input)

            async def on_submit(modal_self, interaction: discord.Interaction):
                try:
                    new_settings: dict = {}

                    if isinstance(modal_self.game, LiXiNgayTetGame):
                        new_settings["M"] = int(modal_self.m_input.value)
                        new_settings["N"] = int(modal_self.n_input.value)
                        new_settings["player_limit"] = int(
                            modal_self.player_limit.value
                        )
                        new_settings["game_duration_days"] = int(
                            modal_self.duration.value
                        )
                        new_settings["game_interval"] = GameInterval(
                            modal_self.interval_input.value.strip().lower()
                        )

                    valid, error_msg = modal_self.game.validate_settings(new_settings)
                    if not valid:
                        await interaction.response.send_message(
                            f"❌ {error_msg}", ephemeral=True
                        )
                        return

                    modal_self.game.settings.update(new_settings)

                    embed = discord.Embed(
                        title="✅ Đã cập nhật cài đặt",
                        color=discord.Color.green(),
                    )
                    for key, value in new_settings.items():
                        display = value.value if isinstance(value, Enum) else value
                        embed.add_field(name=key, value=str(display), inline=True)

                    await interaction.response.send_message(embed=embed)

                except ValueError:
                    await interaction.response.send_message(
                        "❌ Giá trị không hợp lệ!", ephemeral=True
                    )

        await interaction.response.send_modal(SettingModal(self.bot.current_game))

    # ------------------------------------------------------------------
    # /endregister
    # ------------------------------------------------------------------

    @app_commands.command(name="endregister", description="Đóng đăng ký game")
    async def end_register(self, interaction: discord.Interaction):
        if not self.bot.current_game:
            await interaction.response.send_message(
                "❌ Không có game nào đang diễn ra!", ephemeral=True
            )
            return

        if self.bot.current_game.host_id != interaction.user.id:
            await interaction.response.send_message(
                "❌ Chỉ host mới có quyền đóng đăng ký!", ephemeral=True
            )
            return

        if self.bot.current_game.state != GameState.REGISTERING:
            await interaction.response.send_message(
                "❌ Game không trong trạng thái đăng ký!", ephemeral=True
            )
            return

        self.bot.current_game.state = GameState.REGISTRATION_CLOSED
        self.bot.current_game.log_event("Đã đóng đăng ký")

        embed = discord.Embed(
            title="🔒 Đã đóng đăng ký!",
            description=f"Số người chơi: **{len(self.bot.current_game.players)}**",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /startgame
    # ------------------------------------------------------------------

    @app_commands.command(name="startgame", description="Bắt đầu game")
    @app_commands.describe(
        delay_minutes="Số phút delay trước khi bắt đầu (mặc định: 0)"
    )
    async def start_game(
        self, interaction: discord.Interaction, delay_minutes: int = 0
    ):
        if not self.bot.current_game:
            await interaction.response.send_message(
                "❌ Không có game nào đang diễn ra!", ephemeral=True
            )
            return

        if self.bot.current_game.host_id != interaction.user.id:
            await interaction.response.send_message(
                "❌ Chỉ host mới có quyền bắt đầu game!", ephemeral=True
            )
            return

        if self.bot.current_game.state != GameState.REGISTRATION_CLOSED:
            await interaction.response.send_message(
                "❌ Phải đóng đăng ký trước khi bắt đầu!", ephemeral=True
            )
            return

        if self.bot.current_game.notif_channel_id is None:
            await interaction.response.send_message(
                "❌ Phải set notification channel trước!", ephemeral=True
            )
            return

        if len(self.bot.current_game.players) == 0:
            await interaction.response.send_message(
                "❌ Không có người chơi nào đã đăng ký!", ephemeral=True
            )
            return

        if delay_minutes > 0:
            await interaction.response.send_message(
                f"⏰ Game sẽ bắt đầu sau {delay_minutes} phút!"
            )
            await asyncio.sleep(delay_minutes * 60)
        else:
            await interaction.response.send_message("🎮 Game bắt đầu ngay!")

        game = self.bot.current_game
        game.state = GameState.RUNNING
        game.start_time = datetime.now()

        interval_td = self.bot.get_interval_timedelta(
            game.settings.get("game_interval", GameInterval.ONE_DAY)
        )
        game.next_day_at = game.start_time + interval_td

        await game.on_game_start()

        # Thông báo vào notif channel
        channel = self.bot.get_channel(game.notif_channel_id)
        if channel:
            embed = discord.Embed(
                title="🎮 GAME BẮT ĐẦU!",
                description=(
                    f"**Game:** {self.bot.current_game_type.value}\n"
                    f"**Số người chơi:** {len(game.players)}"
                ),
                color=discord.Color.gold(),
            )
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    # ------------------------------------------------------------------
    # /pausegame
    # ------------------------------------------------------------------

    @app_commands.command(name="pausegame", description="Tạm dừng game")
    async def pause_game(self, interaction: discord.Interaction):
        if not self.bot.current_game:
            await interaction.response.send_message(
                "❌ Không có game nào đang diễn ra!", ephemeral=True
            )
            return

        if self.bot.current_game.host_id != interaction.user.id:
            await interaction.response.send_message(
                "❌ Chỉ host mới có quyền tạm dừng game!", ephemeral=True
            )
            return

        if self.bot.current_game.state != GameState.RUNNING:
            await interaction.response.send_message(
                "❌ Game không đang chạy!", ephemeral=True
            )
            return

        self.bot.current_game.state = GameState.PAUSED
        self.bot.current_game.log_event("Game bị tạm dừng")

        await interaction.response.send_message("⏸️ Game đã tạm dừng!")

    # ------------------------------------------------------------------
    # /endgame
    # ------------------------------------------------------------------

    @app_commands.command(name="endgame", description="Kết thúc game")
    async def end_game(self, interaction: discord.Interaction):
        if not self.bot.current_game:
            await interaction.response.send_message(
                "❌ Không có game nào đang diễn ra!", ephemeral=True
            )
            return

        if self.bot.current_game.host_id != interaction.user.id:
            await interaction.response.send_message(
                "❌ Chỉ host mới có quyền kết thúc game!", ephemeral=True
            )
            return

        game = self.bot.current_game

        # Lấy leaderboard TRƯỚC khi đổi state
        leaderboard = game.get_leaderboard() if isinstance(game, LiXiNgayTetGame) else []

        await game.on_game_end()
        game.state = GameState.ENDED
        game.log_event("Game kết thúc")

        if isinstance(game, LiXiNgayTetGame) and leaderboard:
            embed = discord.Embed(
                title="🏆 GAME KẾT THÚC - BẢNG XẾP HẠNG CUỐI CÙNG",
                color=discord.Color.gold(),
            )
            description = ""
            for idx, (player_id, money) in enumerate(leaderboard[:10], 1):
                try:
                    user = await self.bot.fetch_user(player_id)
                    medal = (
                        ["🥇", "🥈", "🥉"][idx - 1] if idx <= 3 else f"#{idx}"
                    )
                    description += f"{medal} {user.mention}: **{money:,}** đồng\n"
                except Exception:
                    continue

            embed.description = description or "Không có người chơi"
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("🏁 Game đã kết thúc!")

        # Reset
        self.bot.current_game = None
        self.bot.current_game_type = None

    # ------------------------------------------------------------------
    # /log – gửi log qua DM cho host
    # ------------------------------------------------------------------

    @app_commands.command(name="log", description="Xuất log game (gửi qua DM)")
    async def log_command(self, interaction: discord.Interaction):
        if not self.bot.current_game:
            await interaction.response.send_message(
                "❌ Không có game nào đang diễn ra!", ephemeral=True
            )
            return

        if self.bot.current_game.host_id != interaction.user.id:
            await interaction.response.send_message(
                "❌ Chỉ host mới có quyền xem log!", ephemeral=True
            )
            return

        log_content = "\n".join(self.bot.current_game.event_log) or "(Trống)"
        file = discord.File(
            io.BytesIO(log_content.encode("utf-8")), filename="game_log.txt"
        )

        try:
            dm = await interaction.user.create_dm()
            await dm.send("📝 Game log:", file=file)
            await interaction.response.send_message(
                "✅ Đã gửi log qua DM!", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Không thể gửi DM. Hãy bật nhận tin nhắn từ thành viên server!",
                ephemeral=True,
            )

    # ------------------------------------------------------------------
    # /setnotifchannel
    # ------------------------------------------------------------------

    @app_commands.command(name="setnotifchannel", description="Set kênh thông báo")
    @app_commands.describe(channel="Kênh để bot thông báo")
    async def set_notif_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        if not self.bot.current_game:
            await interaction.response.send_message(
                "❌ Không có game nào đang diễn ra!", ephemeral=True
            )
            return

        if self.bot.current_game.host_id != interaction.user.id:
            await interaction.response.send_message(
                "❌ Chỉ host mới có quyền set channel!", ephemeral=True
            )
            return

        self.bot.current_game.notif_channel_id = channel.id
        self.bot.current_game.log_event(f"Set notification channel: {channel.name}")

        await interaction.response.send_message(
            f"✅ Đã set notification channel: {channel.mention}"
        )

    # ------------------------------------------------------------------
    # /setgamechannel
    # ------------------------------------------------------------------

    @app_commands.command(name="setgamechannel", description="Set kênh chơi game")
    @app_commands.describe(channel="Kênh để chơi game")
    async def set_game_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        if not self.bot.current_game:
            await interaction.response.send_message(
                "❌ Không có game nào đang diễn ra!", ephemeral=True
            )
            return

        if self.bot.current_game.host_id != interaction.user.id:
            await interaction.response.send_message(
                "❌ Chỉ host mới có quyền set channel!", ephemeral=True
            )
            return

        self.bot.current_game.game_channel_id = channel.id
        self.bot.current_game.log_event(f"Set game channel: {channel.name}")

        await interaction.response.send_message(
            f"✅ Đã set game channel: {channel.mention}"
        )


async def setup(bot: MinigameBot):
    await bot.add_cog(HostCommands(bot))
