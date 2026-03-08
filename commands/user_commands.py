from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from enums import GameState, GameType
from games.li_xi_game import LiXiNgayTetGame
from games.kro_game import KRoGame
from games.jco_game import JCoGame

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
                        "`/giveaway` - Tặng tiền cho người khác\n"
                        "`/gamble` - Người chơi không bao giờ thắng (1% thắng 200x, 99% thua)\n"
                        "`/leaderboard` - Xem bảng xếp hạng"
                    ),
                    inline=False,
                )
                return embed
            if gt == GameType.KRO:
                embed = discord.Embed(
                    title="📖 Hướng dẫn: K Rô",
                    color=discord.Color.blue(),
                )
                embed.add_field(
                    name="Lệnh người chơi",
                    value=(
                        "`/pick` - Chọn số (0-100)\n"
                        "`/rules_update` - Xem luật bổ sung đang kích hoạt\n"
                        "`/status_kro` - Xem điểm phạt và người bị loại\n"
                        "`/history_kro` - Xem lại kết quả các vòng trước\n"
                        "`/lastround` - Kết quả vòng gần nhất"
                    ),
                    inline=False,
                )
                return embed
            if gt == GameType.JCO:
                embed = discord.Embed(
                    title="📖 Hướng dẫn: J Cơ",
                    color=discord.Color.blue(),
                )
                embed.add_field(
                    name="Lệnh người chơi",
                    value=(
                        "`/checknumber` - Xem số trên gáy người khác (DM)\n"
                        "`/answer` - Dự đoán số của mình\n"
                        "`/mirror` - Dùng gương xem số (1 lần duy nhất)\n"
                        "`/vote` - Vote loại người nghi ngờ (từ vòng 2)\n"
                        "`/history_jco` - Lịch sử người bị loại\n"
                        "`/status_jco` - Trạng thái game\n"
                        "`/cheat_jco` - Xem số (chỉ J Cơ)"
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
            value=(
                "`li_xi_ngay_tet` - Lì Xì Ngày Tết\n"
                "`kro` - K Rô\n"
                "`jco` - J Cơ"
            ),
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
            embed.add_field(
                name="Tính năng khác",
                value=(
                    "• Giveaway: Tặng tiền cho người khác\n"
                    "• Gamble: Con bạc simulator"
                ),
                inline=False,
            )
            await interaction.response.send_message(embed=embed)
        elif gt == GameType.KRO:
            embed = discord.Embed(
                title="📜 Luật chơi: K Rô",
                color=discord.Color.purple(),
            )
            embed.add_field(
                name="Cơ chế",
                value=(
                    "• Tất cả bắt đầu với 0 điểm phạt\n"
                    "• Mỗi vòng, chọn số từ 0 đến 100\n"
                    "• Mục tiêu = trung bình × 0.8\n"
                    "• Người gần mục tiêu nhất thắng\n"
                    "• Người thua +1 điểm phạt\n"
                    "• Chạm mức phạt tối đa → bị loại\n"
                    "• Còn 1 người → chiến thắng"
                ),
                inline=False,
            )
            embed.add_field(
                name="Luật bổ sung (≤4 người)",
                value="Nếu 2+ người chọn cùng số, số đó bị vô hiệu",
                inline=False,
            )
            embed.add_field(
                name="Luật bổ sung (≤3 người)",
                value="Chọn đúng mục tiêu → thắng tuyệt đối, thua nhận 2 phạt",
                inline=False,
            )
            embed.add_field(
                name="Luật bổ sung (2 người)",
                value="Nếu 1 người chọn 0, người chọn 100 thắng",
                inline=False,
            )
            await interaction.response.send_message(embed=embed)
        elif gt == GameType.JCO:
            embed = discord.Embed(
                title="📜 Luật chơi: J Cơ",
                color=discord.Color.purple(),
            )
            embed.add_field(
                name="Cơ chế",
                value=(
                    "• Mỗi người được gán 1 số (1–M) trên gáy\n"
                    "• Bạn thấy số của người khác, không thấy số mình\n"
                    "• 1 người bí mật là J Cơ — biết số của mình\n"
                    "• Mỗi vòng: đoán số mình hoặc bỏ qua\n"
                    "• Đoán đúng → sống sót, đoán sai → bị loại"
                ),
                inline=False,
            )
            embed.add_field(
                name="Vote (từ vòng 2)",
                value=(
                    "• Mỗi người vote 1 người nghi là J Cơ\n"
                    "• Quá bán (>50%) → người đó bị loại\n"
                    "• J Cơ bị vote loại → tất cả còn lại thắng"
                ),
                inline=False,
            )
            embed.add_field(
                name="Gương & Rotation",
                value=(
                    "• `/mirror` — xem số mình (1 lần duy nhất)\n"
                    "• Nếu bật rotation: sau 3 vòng không ai bị loại, "
                    "số được gán lại ngẫu nhiên"
                ),
                inline=False,
            )
            embed.add_field(
                name="Điều kiện kết thúc",
                value=(
                    "• J Cơ bị vote loại → tất cả thắng\n"
                    "• Chỉ còn J Cơ sống → J Cơ thắng\n"
                    "• Mọi người bị loại → hoà"
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

        if isinstance(self.bot.current_game, KRoGame):
            if (
                len(self.bot.current_game.players)
                >= self.bot.current_game.settings["player_limit"]
            ):
                await interaction.response.send_message(
                    "❌ Game đã đầy!", ephemeral=True
                )
                return

        if isinstance(self.bot.current_game, JCoGame):
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
