from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from enums import GameState, GameType
from games.li_xi_game import LiXiNgayTetGame

if TYPE_CHECKING:
    from bot import MinigameBot


def _check_game_channel(bot: MinigameBot, interaction: discord.Interaction) -> bool:
    """Kiểm tra user gọi lệnh trong đúng game channel (nếu đã set)."""
    if not bot.current_game:
        return True
    if bot.current_game.game_channel_id is None:
        return True  # chưa set → cho phép ở mọi nơi
    return interaction.channel_id == bot.current_game.game_channel_id


class UserCommands(commands.Cog):
    """Lệnh chung cho người chơi."""

    def __init__(self, bot: MinigameBot):
        self.bot = bot

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def build_help_embed(game_type: Optional[str] = None) -> discord.Embed:
        if game_type:
            gt = GameType(game_type.lower())
            if gt == GameType.LI_XI_NGAY_TET:
                embed = discord.Embed(
                    title="📖 Hướng dẫn: Lì Xì Ngày Tết",
                    color=discord.Color.blue(),
                )
                embed.add_field(
                    name="Lệnh người chơi",
                    value=(
                        "`/fight` - Thách đấu người khác\n"
                        "`/stats` - Xem thông tin bản thân\n"
                        "`/reroll` - Random lại tuổi (1 lần/ngày)\n"
                        "`/leaderboard` - Xem bảng xếp hạng"
                    ),
                    inline=False,
                )
                return embed
            raise ValueError("Invalid game type")

        embed = discord.Embed(
            title="📖 Hướng dẫn Bot Minigame",
            description="Danh sách các lệnh có sẵn",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="🎮 Lệnh Host",
            value=(
                "`/host` - Tạo game mới\n"
                "`/settinggame` - Chỉnh cài đặt\n"
                "`/endregister` - Đóng đăng ký\n"
                "`/startgame` - Bắt đầu game\n"
                "`/pausegame` - Tạm dừng\n"
                "`/endgame` - Kết thúc game\n"
                "`/log` - Xuất log\n"
                "`/setnotifchannel` - Set kênh thông báo\n"
                "`/setgamechannel` - Set kênh chơi game"
            ),
            inline=False,
        )
        embed.add_field(
            name="👥 Lệnh Người chơi",
            value=(
                "`/joingame` - Tham gia game\n"
                "`/leavegame` - Rời game\n"
                "`/help [game_type]` - Xem hướng dẫn\n"
                "`/rule [game_type]` - Xem luật chơi"
            ),
            inline=False,
        )
        embed.add_field(
            name="🎲 Game khả dụng",
            value="`li_xi_ngay_tet` - Lì Xì Ngày Tết",
            inline=False,
        )
        return embed

    # ------------------------------------------------------------------
    # /help (slash)
    # ------------------------------------------------------------------

    @app_commands.command(name="help", description="Hiển thị hướng dẫn")
    @app_commands.describe(game_type="Loại game cần xem hướng dẫn (tùy chọn)")
    async def help_command(
        self, interaction: discord.Interaction, game_type: Optional[str] = None
    ):
        try:
            embed = self.build_help_embed(game_type)
        except ValueError:
            await interaction.response.send_message(
                "❌ Loại game không hợp lệ!", ephemeral=True
            )
            return
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # g!help (prefix)
    # ------------------------------------------------------------------

    @commands.command(name="help")
    async def prefix_help_command(
        self, ctx: commands.Context, game_type: Optional[str] = None
    ):
        try:
            embed = self.build_help_embed(game_type)
        except ValueError:
            await ctx.send("❌ Loại game không hợp lệ!")
            return
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------
    # /rule
    # ------------------------------------------------------------------

    @app_commands.command(name="rule", description="Xem luật chơi")
    @app_commands.describe(game_type="Loại game")
    async def rule_command(self, interaction: discord.Interaction, game_type: str):
        try:
            gt = GameType(game_type.lower())
        except ValueError:
            await interaction.response.send_message(
                "❌ Loại game không hợp lệ!", ephemeral=True
            )
            return

        if gt == GameType.LI_XI_NGAY_TET:
            embed = discord.Embed(
                title="📜 Luật chơi: Lì Xì Ngày Tết",
                color=discord.Color.purple(),
            )
            embed.add_field(
                name="Cơ chế",
                value=(
                    "• Bắt đầu với M đồng\n"
                    "• Mỗi ngày random tuổi từ 1 đến 2N\n"
                    "• Đấu với người khác, so sánh tuổi"
                ),
                inline=False,
            )
            embed.add_field(
                name="Quy tắc thắng thua",
                value=(
                    "• Người lớn tuổi hơn phải lì xì cho người nhỏ hơn\n"
                    "• Nếu hiệu tuổi > N: người lớn tuổi được coi là nhỏ → nhận lì xì\n"
                    "• Hiệu tuổi = 0 hoặc N: Hòa, cả hai +M/10"
                ),
                inline=False,
            )
            embed.add_field(
                name="Giới hạn",
                value=(
                    "• Mỗi cặp chỉ đấu 1 lần/ngày\n"
                    "• Reroll tuổi 1 lần/ngày\n"
                    "• Sau mỗi ngày: +M/10 đồng & random lại tuổi"
                ),
                inline=False,
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                "❌ Game này chưa có luật!", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /joingame
    # ------------------------------------------------------------------

    @app_commands.command(name="joingame", description="Tham gia game")
    async def join_game(self, interaction: discord.Interaction):
        if not self.bot.current_game:
            await interaction.response.send_message(
                "❌ Không có game nào đang mở đăng ký!", ephemeral=True
            )
            return

        if self.bot.current_game.state != GameState.REGISTERING:
            await interaction.response.send_message(
                "❌ Game không trong trạng thái đăng ký!", ephemeral=True
            )
            return

        if interaction.user.id in self.bot.current_game.players:
            await interaction.response.send_message(
                "❌ Bạn đã tham gia rồi!", ephemeral=True
            )
            return

        # Kiểm tra giới hạn
        if isinstance(self.bot.current_game, LiXiNgayTetGame):
            if (
                len(self.bot.current_game.players)
                >= self.bot.current_game.settings["player_limit"]
            ):
                await interaction.response.send_message(
                    "❌ Game đã đầy!", ephemeral=True
                )
                return

        self.bot.current_game.players[interaction.user.id] = {}
        self.bot.current_game.log_event(f"Player {interaction.user.id} joined")

        await interaction.response.send_message(
            f"✅ {interaction.user.mention} đã tham gia game! "
            f"({len(self.bot.current_game.players)} người chơi)"
        )

    # ------------------------------------------------------------------
    # /leavegame
    # ------------------------------------------------------------------

    @app_commands.command(name="leavegame", description="Rời game")
    async def leave_game(self, interaction: discord.Interaction):
        if not self.bot.current_game:
            await interaction.response.send_message(
                "❌ Không có game nào đang diễn ra!", ephemeral=True
            )
            return

        if self.bot.current_game.state not in (
            GameState.REGISTERING,
            GameState.REGISTRATION_CLOSED,
        ):
            await interaction.response.send_message(
                "❌ Không thể rời game khi đã bắt đầu!", ephemeral=True
            )
            return

        if interaction.user.id not in self.bot.current_game.players:
            await interaction.response.send_message(
                "❌ Bạn chưa tham gia game!", ephemeral=True
            )
            return

        del self.bot.current_game.players[interaction.user.id]
        self.bot.current_game.log_event(f"Player {interaction.user.id} left")

        await interaction.response.send_message(
            f"👋 {interaction.user.mention} đã rời game!"
        )


async def setup(bot: MinigameBot):
    await bot.add_cog(UserCommands(bot))
