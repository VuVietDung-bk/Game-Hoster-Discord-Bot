import random
from typing import List

from enums import GameInterval, GameState
from games.base_game import BaseGame


class LiXiNgayTetGame(BaseGame):
    """Game Lì Xì Ngày Tết."""

    def __init__(self, host_id: int):
        super().__init__(host_id)
        self.settings = self.get_default_settings()
        self.current_day = 0

    def get_default_settings(self) -> dict:
        return {
            "M": 10,
            "N": 10,
            "game_interval": GameInterval.ONE_DAY,
            "player_limit": 50,
            "game_duration_days": 7,
        }

    def validate_settings(self, settings: dict) -> tuple[bool, str]:
        if "M" in settings:
            if not isinstance(settings["M"], int) or not (10 <= settings["M"] <= 10000):
                return False, "M phải là số nguyên từ 10 đến 10000"

        if "N" in settings:
            if not isinstance(settings["N"], int) or not (5 <= settings["N"] <= 500):
                return False, "N phải là số nguyên từ 5 đến 500"

        if "player_limit" in settings:
            if not isinstance(settings["player_limit"], int) or not (10 <= settings["player_limit"] <= 100):
                return False, "Giới hạn người chơi phải từ 10 đến 100"

        if "game_duration_days" in settings:
            if not isinstance(settings["game_duration_days"], int) or not (2 <= settings["game_duration_days"] <= 20):
                return False, "Thời hạn game phải từ 2 đến 20 ngày"

        if "game_interval" in settings:
            val = settings["game_interval"]
            if not isinstance(val, GameInterval):
                try:
                    GameInterval(val)
                except ValueError:
                    return False, "game_interval phải là 12h, 1d hoặc 2d"

        return True, ""

    # ------------------------------------------------------------------
    # Game lifecycle hooks
    # ------------------------------------------------------------------

    async def on_game_start(self):
        """Khởi tạo dữ liệu người chơi khi game bắt đầu."""
        M = self.settings["M"]
        N = self.settings["N"]

        for player_id in self.players:
            self.players[player_id] = {
                "money": M,
                "age": random.randint(1, 2 * N),
                "fights_today": set(),
                "reroll_used": False,
            }

        self.log_event(f"Game bắt đầu với {len(self.players)} người chơi")

    async def on_day_change(self):
        """Reset trạng thái mỗi ngày và cộng thêm tiền."""
        M = self.settings["M"]
        N = self.settings["N"]
        self.current_day += 1

        for player_id in self.players:
            self.players[player_id]["fights_today"] = set()
            self.players[player_id]["reroll_used"] = False
            self.players[player_id]["money"] += M // 10
            # Random lại tuổi đầu ngày
            self.players[player_id]["age"] = random.randint(1, 2 * N)

        self.log_event(f"Ngày {self.current_day}: Reset trạng thái người chơi")

    # ------------------------------------------------------------------
    # Game logic
    # ------------------------------------------------------------------

    def can_fight(self, player1_id: int, player2_id: int) -> tuple[bool, str]:
        """Kiểm tra xem 2 người có thể đấu không."""
        if player1_id == player2_id:
            return False, "Bạn không thể tự đấu với chính mình"

        if player1_id not in self.players:
            return False, "Bạn chưa tham gia game"

        if player2_id not in self.players:
            return False, "Đối thủ chưa tham gia game"

        if player2_id in self.players[player1_id]["fights_today"]:
            return False, "Bạn đã đấu với người này hôm nay rồi"

        return True, ""

    def fight(self, player1_id: int, player2_id: int, bet: int) -> tuple[bool, str, dict]:
        """Xử lý combat giữa 2 người chơi."""
        player1 = self.players[player1_id]
        player2 = self.players[player2_id]

        if player1["money"] < bet:
            return False, "Bạn không đủ tiền", {}

        if player2["money"] < bet:
            return False, "Đối thủ không đủ tiền", {}

        age1 = player1["age"]
        age2 = player2["age"]
        N = self.settings["N"]
        M = self.settings["M"]

        age_diff = abs(age1 - age2)

        result = {
            "age1": age1,
            "age2": age2,
            "bet": bet,
            "winner": None,
            "loser": None,
            "money_change": 0,
        }

        # Hòa: hiệu tuổi == 0 hoặc == N
        if age_diff == 0 or age_diff == N:
            bonus = M // 10
            player1["money"] += bonus
            player2["money"] += bonus
            result["money_change"] = bonus
            result["winner"] = "draw"
            self.log_event(
                f"Player {player1_id} vs {player2_id}: HÒA "
                f"(tuổi {age1} vs {age2}), mỗi người +{bonus}"
            )

        # Thắng / Thua
        else:
            if age_diff > N:
                # Hiệu > N ⇒ người lớn tuổi hơn được coi là nhỏ → nhận lì xì
                if age1 > age2:
                    winner_id, loser_id = player1_id, player2_id
                else:
                    winner_id, loser_id = player2_id, player1_id
            else:
                # Hiệu <= N bình thường ⇒ người nhỏ tuổi hơn nhận lì xì
                if age1 < age2:
                    winner_id, loser_id = player1_id, player2_id
                else:
                    winner_id, loser_id = player2_id, player1_id

            self.players[winner_id]["money"] += bet
            self.players[loser_id]["money"] -= bet
            result["winner"] = winner_id
            result["loser"] = loser_id
            result["money_change"] = bet

            self.log_event(
                f"Player {player1_id} vs {player2_id}: "
                f"{winner_id} THẮNG, ±{bet}"
            )

        # Đánh dấu đã đấu hôm nay
        player1["fights_today"].add(player2_id)
        player2["fights_today"].add(player1_id)

        return True, "", result

    def reroll_age(self, player_id: int) -> tuple[bool, str, int]:
        """Random lại tuổi (1 lần / ngày)."""
        if player_id not in self.players:
            return False, "Bạn chưa tham gia game", 0

        if self.players[player_id]["reroll_used"]:
            return False, "Bạn đã dùng reroll hôm nay rồi", 0

        N = self.settings["N"]
        old_age = self.players[player_id]["age"]
        new_age = random.randint(1, 2 * N)
        self.players[player_id]["age"] = new_age
        self.players[player_id]["reroll_used"] = True

        self.log_event(f"Player {player_id} reroll: {old_age} -> {new_age}")
        return True, "", new_age

    def get_leaderboard(self) -> List[tuple[int, int]]:
        """Lấy bảng xếp hạng (dùng được cả khi game ENDED)."""
        leaderboard = [
            (player_id, data["money"])
            for player_id, data in self.players.items()
        ]
        leaderboard.sort(key=lambda x: x[1], reverse=True)
        return leaderboard
