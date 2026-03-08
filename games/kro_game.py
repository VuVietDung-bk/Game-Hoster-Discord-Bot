from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from enums import GameState
from games.base_game import BaseGame


@dataclass
class RoundResult:
    """Kết quả một vòng K Rô."""

    round_number: int
    picks: Dict[int, int]  # player_id -> number picked
    invalid_numbers: List[int]  # numbers voided (duplicate rule ≤4 players)
    valid_picks: Dict[int, int]  # after removing invalids
    average: Optional[float]
    target: Optional[float]
    winners: List[int]
    losers: List[int]
    penalty: int  # 1 or 2
    special_winner: Optional[int]  # exact-target winner (≤3 rule)
    rule_0_100_winner: Optional[int]  # 2-player 0-vs-100 rule


class KRoGame(BaseGame):
    """Game K Rô – Guess 0.8× average."""

    # ----- intervals accepted by this game (in seconds) -----
    INTERVAL_MAP = {
        "1m": 60,
        "2m": 120,
        "5m": 300,
        "10m": 600,
        "30m": 1800,
        "12h": 43200,
    }

    def __init__(self, host_id: int):
        super().__init__(host_id)
        self.settings = self.get_default_settings()

        # round tracking
        self.current_round: int = 0
        self.round_history: List[RoundResult] = []

        # per-round picks  {player_id: number}
        self.current_picks: Dict[int, int] = {}

        # penalty scores  {player_id: int}
        self.penalties: Dict[int, int] = {}

        # eliminated player ids (in order)
        self.eliminated: List[int] = []

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_default_settings(self) -> dict:
        return {
            "max_penalty": 10,
            "game_interval": "5m",
            "player_limit": 5,
        }

    def validate_settings(self, settings: dict) -> tuple[bool, str]:
        if "max_penalty" in settings:
            v = settings["max_penalty"]
            if not isinstance(v, int) or not (5 <= v <= 20):
                return False, "Điểm phạt tối đa phải từ 5 đến 20"

        if "player_limit" in settings:
            v = settings["player_limit"]
            if not isinstance(v, int) or not (2 <= v <= 5):
                return False, "Giới hạn người chơi phải từ 2 đến 5"

        if "game_interval" in settings:
            v = settings["game_interval"]
            if v not in self.INTERVAL_MAP:
                valid = ", ".join(self.INTERVAL_MAP.keys())
                return False, f"game_interval phải là một trong: {valid}"

        return True, ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def alive_players(self) -> List[int]:
        """Danh sách player còn sống (chưa bị loại)."""
        return [pid for pid in self.players if pid not in self.eliminated]

    @property
    def interval_seconds(self) -> int:
        return self.INTERVAL_MAP.get(self.settings["game_interval"], 300)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_game_start(self):
        for pid in self.players:
            self.players[pid] = {}
            self.penalties[pid] = 0
        self.current_round = 0
        self.log_event(f"Game K Rô bắt đầu với {len(self.players)} người chơi")

    async def on_game_end(self):
        self.log_event("Game K Rô kết thúc")

    # ------------------------------------------------------------------
    # Core: pick
    # ------------------------------------------------------------------

    def pick(self, player_id: int, number: int) -> Tuple[bool, str]:
        """Người chơi chọn số cho vòng hiện tại."""
        if player_id not in self.players:
            return False, "Bạn chưa tham gia game"

        if player_id in self.eliminated:
            return False, "Bạn đã bị loại khỏi game"

        if not (0 <= number <= 100):
            return False, "Số phải từ 0 đến 100"

        self.current_picks[player_id] = number
        return True, ""

    # ------------------------------------------------------------------
    # Core: resolve round
    # ------------------------------------------------------------------

    def resolve_round(self) -> Optional[RoundResult]:
        """Xử lý kết quả vòng hiện tại. Trả về None nếu không ai pick."""
        alive = self.alive_players
        if not alive:
            return None

        self.current_round += 1

        picks: Dict[int, int] = {}
        for pid in alive:
            if pid in self.current_picks:
                picks[pid] = self.current_picks[pid]

        # Players that didn't pick get penalty automatically
        no_pick = [pid for pid in alive if pid not in picks]

        active_count = len(alive)

        # --- Duplicate rule (≤4 alive) ---
        invalid_numbers: List[int] = []
        valid_picks: Dict[int, int] = dict(picks)

        if active_count <= 4:
            # Count occurrences of each number among pickers
            from collections import Counter

            num_counts = Counter(picks.values())
            invalid_numbers = [n for n, c in num_counts.items() if c >= 2]
            if invalid_numbers:
                valid_picks = {
                    pid: n for pid, n in picks.items() if n not in invalid_numbers
                }

        # --- Compute average & target ---
        if valid_picks:
            avg = sum(valid_picks.values()) / len(valid_picks)
            target = avg * 0.8
        else:
            avg = None
            target = None

        # --- Determine winners / losers ---
        winners: List[int] = []
        losers: List[int] = []
        penalty = 1
        special_winner: Optional[int] = None
        rule_0_100_winner: Optional[int] = None

        # --- 2-player rule: 0 vs 100 ---
        if active_count == 2 and len(picks) == 2:
            vals = list(picks.values())
            pids = list(picks.keys())
            if set(vals) == {0, 100}:
                # Whoever picked 100 wins
                winner_pid = pids[0] if vals[0] == 100 else pids[1]
                loser_pid = pids[0] if vals[0] == 0 else pids[1]
                rule_0_100_winner = winner_pid
                winners = [winner_pid]
                losers = [loser_pid]
                # ≤3 player penalty still applies (2 ≤ 3)
                penalty = 2

                result = RoundResult(
                    round_number=self.current_round,
                    picks=dict(picks),
                    invalid_numbers=invalid_numbers,
                    valid_picks=valid_picks,
                    average=avg,
                    target=target,
                    winners=winners,
                    losers=losers + no_pick,
                    penalty=penalty,
                    special_winner=special_winner,
                    rule_0_100_winner=rule_0_100_winner,
                )

                self._apply_penalties(result, no_pick)
                self.round_history.append(result)
                self.current_picks.clear()
                return result

        if target is not None:
            # --- Exact target rule (≤3 alive) ---
            if active_count <= 3:
                exact_pickers = [
                    pid for pid, n in valid_picks.items() if n == target
                ]
                if len(exact_pickers) == 1:
                    special_winner = exact_pickers[0]
                    penalty = 2
                    winners = [special_winner]
                    losers = [pid for pid in picks if pid != special_winner]
                elif len(exact_pickers) > 1:
                    # Multiple exact → they are all winners
                    penalty = 2
                    winners = exact_pickers
                    losers = [pid for pid in picks if pid not in winners]

            # --- Normal closest-to-target logic ---
            if not winners:
                distances = {
                    pid: abs(n - target) for pid, n in picks.items()
                }
                if distances:
                    min_dist = min(distances.values())
                    winners = [pid for pid, d in distances.items() if d == min_dist]
                    losers = [pid for pid in picks if pid not in winners]
        else:
            # No valid picks at all – everyone who picked is loser? 
            # Actually if all picks are invalid (duplicates), no target.
            # Everyone who picked (with invalid numbers) loses.
            losers = list(picks.keys())

        result = RoundResult(
            round_number=self.current_round,
            picks=dict(picks),
            invalid_numbers=invalid_numbers,
            valid_picks=valid_picks,
            average=avg,
            target=target,
            winners=winners,
            losers=losers + no_pick,
            penalty=penalty,
            special_winner=special_winner,
            rule_0_100_winner=rule_0_100_winner,
        )

        self._apply_penalties(result, no_pick)
        self.round_history.append(result)
        self.current_picks.clear()
        return result

    def _apply_penalties(self, result: RoundResult, no_pick: List[int]):
        """Áp dụng điểm phạt và loại người chạm mức giới hạn."""
        max_pen = self.settings["max_penalty"]

        for pid in result.losers:
            self.penalties[pid] = self.penalties.get(pid, 0) + result.penalty
            if pid in no_pick:
                self.log_event(
                    f"Vòng {result.round_number}: Player {pid} không chọn số → +{result.penalty} điểm phạt"
                )

        # Eliminate players that hit the cap
        for pid in list(result.losers):
            if self.penalties.get(pid, 0) >= max_pen and pid not in self.eliminated:
                self.eliminated.append(pid)
                self.log_event(
                    f"Vòng {result.round_number}: Player {pid} bị loại "
                    f"({self.penalties[pid]}/{max_pen} điểm phạt)"
                )

    # ------------------------------------------------------------------
    # Game-over check
    # ------------------------------------------------------------------

    def check_game_over(self) -> Tuple[bool, Optional[int]]:
        """Kiểm tra game kết thúc. Trả về (is_over, winner_id or None)."""
        alive = self.alive_players
        if len(alive) <= 1:
            return True, alive[0] if alive else None
        return False, None

    # ------------------------------------------------------------------
    # Info helpers
    # ------------------------------------------------------------------

    def get_active_rules(self) -> List[str]:
        """Trả về danh sách luật bổ sung đang kích hoạt."""
        alive_count = len(self.alive_players)
        rules: List[str] = []
        if alive_count <= 4:
            rules.append(
                "🔹 **≤4 người chơi:** Nếu 2+ người chọn cùng một số, "
                "số đó bị vô hiệu và không tính vào trung bình."
            )
        if alive_count <= 3:
            rules.append(
                "🔸 **≤3 người chơi:** Nếu ai chọn đúng số mục tiêu, "
                "người đó thắng tuyệt đối. Người thua nhận 2 điểm phạt."
            )
        if alive_count <= 2:
            rules.append(
                "🔻 **2 người chơi:** Nếu một người chọn 0, "
                "người chọn 100 sẽ chiến thắng."
            )
        return rules

    def get_status_embed_data(self) -> Tuple[List[Tuple[int, int]], List[int]]:
        """Trả về (alive_list[(pid, penalty)], eliminated_list)."""
        alive = [
            (pid, self.penalties.get(pid, 0))
            for pid in self.players
            if pid not in self.eliminated
        ]
        alive.sort(key=lambda x: x[1])
        return alive, list(self.eliminated)
