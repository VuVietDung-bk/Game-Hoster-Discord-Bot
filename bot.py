import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from typing import Optional

from enums import GameState, GameType, GameInterval
from games.base_game import BaseGame
from games.li_xi_game import LiXiNgayTetGame
from games.kro_game import KRoGame
from games.jco_game import JCoGame


class MinigameBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix="g!",
            intents=intents,
            help_command=None,
        )

        self.current_game: Optional[BaseGame] = None
        self.current_game_type: Optional[GameType] = None

    async def setup_hook(self):
        # Load command cogs
        await self.load_extension("commands.host_commands")
        await self.load_extension("commands.user_commands")
        await self.load_extension("commands.lixi_commands")
        await self.load_extension("commands.kro_commands")
        await self.load_extension("commands.jco_commands")

        await self.tree.sync()
        print("Commands synced!")

    async def on_ready(self):
        print(f"{self.user} đã online!")
        if not self.check_game_interval.is_running():
            self.check_game_interval.start()

    # ------------------------------------------------------------------
    # Interval map helper
    # ------------------------------------------------------------------

    @staticmethod
    def get_interval_timedelta(interval: GameInterval) -> timedelta:
        mapping = {
            GameInterval.TEST_INTERVAL: timedelta(minutes=10),
            GameInterval.TWELVE_HOURS: timedelta(hours=12),
            GameInterval.ONE_DAY: timedelta(days=1),
            GameInterval.TWO_DAYS: timedelta(days=2),
        }
        return mapping.get(interval, timedelta(days=1))

    # ------------------------------------------------------------------
    # Background task – check day changes
    # ------------------------------------------------------------------

    @tasks.loop(minutes=10)
    async def check_game_interval(self):
        """Kiểm tra và xử lý chuyển ngày game."""
        if not self.current_game:
            return

        if self.current_game.state != GameState.RUNNING:
            return

        if not isinstance(self.current_game, LiXiNgayTetGame):
            return

        game = self.current_game
        now = datetime.now()

        interval_td = self.get_interval_timedelta(
            game.settings.get("game_interval", GameInterval.ONE_DAY)
        )

        # Thiết lập mốc ngày kế tiếp nếu chưa có
        if game.next_day_at is None:
            base_time = game.start_time or now
            game.next_day_at = base_time + interval_td

        # Catch-up nếu bot bị sleep / trễ nhiều chu kỳ
        while game.next_day_at and now >= game.next_day_at:
            await game.on_day_change()
            game.next_day_at += interval_td

            # Hết thời hạn game → kết thúc
            duration_days = game.settings.get("game_duration_days", 7)
            if game.current_day >= duration_days:
                leaderboard = game.get_leaderboard()
                await game.on_game_end()
                game.state = GameState.ENDED
                game.log_event("Game kết thúc (hết thời hạn)")

                channel = (
                    self.get_channel(game.notif_channel_id)
                    if game.notif_channel_id
                    else None
                )
                if channel:
                    embed = discord.Embed(
                        title="🏁 GAME KẾT THÚC (Hết thời hạn)",
                        color=discord.Color.gold(),
                    )
                    description = ""
                    for idx, (player_id, money) in enumerate(leaderboard[:10], 1):
                        try:
                            user = await self.fetch_user(player_id)
                            medal = (
                                ["🥇", "🥈", "🥉"][idx - 1]
                                if idx <= 3
                                else f"#{idx}"
                            )
                            description += (
                                f"{medal} {user.mention}: **{money:,}** đồng\n"
                            )
                        except Exception:
                            continue

                    embed.description = description or "Không có người chơi"
                    try:
                        await channel.send(embed=embed)
                    except discord.Forbidden:
                        pass

                self.current_game = None
                self.current_game_type = None
                return

            # Thông báo đổi ngày
            channel = (
                self.get_channel(game.notif_channel_id)
                if game.notif_channel_id
                else None
            )
            if channel:
                embed = discord.Embed(
                    title=f"🌅 Ngày {game.current_day}",
                    description=(
                        f"Tuổi đã được random lại.\n"
                        f"Tất cả người chơi +{game.settings['M'] // 10} đồng và reset lượt."
                    ),
                    color=discord.Color.blue(),
                )
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    @check_game_interval.before_loop
    async def before_check_game_interval(self):
        await self.wait_until_ready()
