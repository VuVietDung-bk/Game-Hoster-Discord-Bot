from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from enums import GameState
from games.li_xi_game import LiXiNgayTetGame

if TYPE_CHECKING:
    from bot import MinigameBot


class LeaderboardView(discord.ui.View):
    """View cho phân trang bảng xếp hạng."""

    def __init__(self, leaderboard_data: list, game_day: int, bot, user_id: int):
        super().__init__()
        self.leaderboard_data = leaderboard_data
        self.game_day = game_day
        self.bot = bot
        self.user_id = user_id
        self.current_page = 0
        self.total_pages = (len(leaderboard_data) + 9) // 10  # Làm tròn lên
        self.update_buttons()

    def update_buttons(self):
        """Cập nhật trạng thái các nút."""
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == self.total_pages - 1

    def get_page_embed(self) -> discord.Embed:
        """Tạo embed cho trang hiện tại."""
        start_idx = self.current_page * 10
        end_idx = start_idx + 10
        page_data = self.leaderboard_data[start_idx:end_idx]

        embed = discord.Embed(
            title="🏆 BẢNG XẾP HẠNG",
            description=f"Ngày {self.game_day} | Trang {self.current_page + 1}/{self.total_pages}",
            color=discord.Color.gold(),
        )

        description = ""
        for idx, (player_id, money) in enumerate(page_data, start=start_idx + 1):
            try:
                user = self.bot.get_user(player_id)
                if not user:
                    continue
                medal = (
                    ["🥇", "🥈", "🥉"][idx - 1] if idx <= 3 else f"#{idx}"
                )
                description += f"{medal} **{user.display_name}**: {money:,} đồng\n"
            except Exception:
                continue

        embed.description = description or "Không có người chơi"
        return embed

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.blurple)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ Chỉ người gọi lệnh mới có thể sử dụng nút này!", ephemeral=True
            )
            return
        
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ Chỉ người gọi lệnh mới có thể sử dụng nút này!", ephemeral=True
            )
            return
        
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_page_embed(), view=self)


def _in_game_channel(bot: MinigameBot, interaction: discord.Interaction) -> bool:
    """True nếu game_channel chưa set hoặc user đang ở đúng kênh."""
    if not bot.current_game:
        return True
    if bot.current_game.game_channel_id is None:
        return True
    return interaction.channel_id == bot.current_game.game_channel_id


class LiXiCommands(commands.Cog):
    """Lệnh dành riêng cho game Lì Xì Ngày Tết."""

    def __init__(self, bot: MinigameBot):
        self.bot = bot

    def _get_running_game(self) -> LiXiNgayTetGame | None:
        """Trả về game Lì Xì đang chạy, hoặc None."""
        g = self.bot.current_game
        if g and isinstance(g, LiXiNgayTetGame) and g.state == GameState.RUNNING:
            return g
        return None

    # ------------------------------------------------------------------
    # /fight
    # ------------------------------------------------------------------

    @app_commands.command(
        name="fight", description="[Lì Xì] Thách đấu người khác"
    )
    @app_commands.describe(opponent="Người muốn thách đấu", bet="Số tiền đặt cược")
    async def fight(
        self, interaction: discord.Interaction, opponent: discord.User, bet: int
    ):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game Lì Xì nào đang chạy!", ephemeral=True
            )
            return

        if bet <= 0:
            await interaction.response.send_message(
                "❌ Số tiền phải lớn hơn 0!", ephemeral=True
            )
            return

        can, error = game.can_fight(interaction.user.id, opponent.id)
        if not can:
            await interaction.response.send_message(
                f"❌ {error}", ephemeral=True
            )
            return

        success, error, result = game.fight(interaction.user.id, opponent.id, bet)
        if not success:
            await interaction.response.send_message(
                f"❌ {error}", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="⚔️ KẾT QUẢ GIAO ĐẤU", color=discord.Color.gold()
        )
        embed.add_field(
            name=interaction.user.display_name,
            value=f"Tuổi: ??",
            inline=True,
        )
        embed.add_field(name="VS", value="⚡", inline=True)
        embed.add_field(
            name=opponent.display_name,
            value=f"Tuổi: ??",
            inline=True,
        )

        if result["winner"] == "draw":
            embed.add_field(
                name="🤝 KẾT QUẢ",
                value=f"**HÒA!**\nCả hai nhận +{result['money_change']} đồng",
                inline=False,
            )
        else:
            winner = await self.bot.fetch_user(result["winner"])
            embed.add_field(
                name="🏆 KẾT QUẢ",
                value=(
                    f"**{winner.mention} THẮNG!**\n"
                    f"Thay đổi: ±{result['money_change']} đồng"
                ),
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /stats_lixi
    # ------------------------------------------------------------------

    @app_commands.command(
        name="stats_lixi", description="[Lì Xì] Xem thông tin bản thân"
    )
    async def stats_lixi(self, interaction: discord.Interaction):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game Lì Xì nào đang chạy!", ephemeral=True
            )
            return

        if interaction.user.id not in game.players:
            await interaction.response.send_message(
                "❌ Bạn chưa tham gia game!", ephemeral=True
            )
            return

        p = game.players[interaction.user.id]
        gamble_remaining = 200 - p.get("gamble_count", 0)
        embed = discord.Embed(
            title=f"📊 Thống kê của {interaction.user.display_name}",
            color=discord.Color.blue(),
        )
        embed.add_field(name="💰 Tiền", value=f"{p['money']:,} đồng", inline=True)
        embed.add_field(name="🎂 Tuổi", value=str(p["age"]), inline=True)
        embed.add_field(
            name="⚔️ Đấu hôm nay", value=str(len(p["fights_today"])), inline=True
        )
        embed.add_field(
            name="🔄 Reroll",
            value="Đã dùng" if p["reroll_used"] else "Chưa dùng",
            inline=True,
        )
        embed.add_field(
            name="🎰 Cược hôm nay",
            value=f"{p.get('gamble_count', 0)}/200 (còn {gamble_remaining})",
            inline=True,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /reroll
    # ------------------------------------------------------------------

    @app_commands.command(
        name="reroll", description="[Lì Xì] Random lại tuổi"
    )
    async def reroll(self, interaction: discord.Interaction):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game Lì Xì nào đang chạy!", ephemeral=True
            )
            return

        success, error, new_age = game.reroll_age(interaction.user.id)
        if not success:
            await interaction.response.send_message(
                f"❌ {error}", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"🔄 Bạn đã reroll! Tuổi mới: **{new_age}**", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /giveaway
    # ------------------------------------------------------------------

    @app_commands.command(
        name="giveaway", description="[Lì Xì] Tặng tiền cho người khác"
    )
    @app_commands.describe(user="Người nhận tiền", money="Số tiền tặng")
    async def giveaway(
        self, interaction: discord.Interaction, user: discord.User, money: int
    ):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game Lì Xì nào đang chạy!", ephemeral=True
            )
            return

        success, error = game.giveaway(interaction.user.id, user.id, money)
        if not success:
            await interaction.response.send_message(
                f"❌ {error}", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎁 TẶNG TIỀN THÀNH CÔNG",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Tặng từ",
            value=interaction.user.mention,
            inline=True,
        )
        embed.add_field(name="→", value="💸", inline=True)
        embed.add_field(
            name="Tặng cho",
            value=user.mention,
            inline=True,
        )
        embed.add_field(
            name="💰 Số tiền",
            value=f"{money:,} đồng",
            inline=False,
        )

        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /gamble
    # ------------------------------------------------------------------

    @app_commands.command(
        name="gamble", description="[Lì Xì] Cố gắng vận may (1% thắng 200x, 99% thua)"
    )
    @app_commands.describe(bet="Số tiền cược")
    async def gamble(self, interaction: discord.Interaction, bet: int):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game Lì Xì nào đang chạy!", ephemeral=True
            )
            return

        if bet <= 0:
            await interaction.response.send_message(
                "❌ Số tiền phải lớn hơn 0!", ephemeral=True
            )
            return

        success, error, result = game.gamble(interaction.user.id, bet)
        if not success:
            await interaction.response.send_message(
                f"❌ {error}", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎰 KẾT QUẢ CƯỢC",
            color=discord.Color.gold() if result["win"] else discord.Color.red(),
        )

        if result["win"]:
            embed.add_field(
                name="🎉 VÃI LOZ",
                value=f"**+{result['money_change']:,}** đồng (cược {bet:,} đồng → thắng 200 lần!)",
                inline=False,
            )
        else:
            embed.add_field(
                name="😢 BỎ ĐI MÀ LÀM NGƯỜI!",
                value=f"**-{bet:,}** đồng (xui là 99% mà!)",
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /leaderboard
    # ------------------------------------------------------------------

    @app_commands.command(
        name="leaderboard", description="[Lì Xì] Xem bảng xếp hạng"
    )
    async def leaderboard(self, interaction: discord.Interaction):
        if not _in_game_channel(self.bot, interaction):
            await interaction.response.send_message(
                "❌ Lệnh này chỉ được dùng trong kênh game!", ephemeral=True
            )
            return

        game = self._get_running_game()
        if not game:
            await interaction.response.send_message(
                "❌ Không có game Lì Xì nào đang chạy!", ephemeral=True
            )
            return

        leaderboard_data = game.get_leaderboard()
        
        if not leaderboard_data:
            await interaction.response.send_message(
                "❌ Không có người chơi nào!", ephemeral=True
            )
            return

        view = LeaderboardView(leaderboard_data, game.current_day, self.bot, interaction.user.id)
        embed = view.get_page_embed()
        
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: MinigameBot):
    await bot.add_cog(LiXiCommands(bot))
