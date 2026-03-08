from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from enums import GameState
from games.base_game import BaseGame


@dataclass
class JCoRoundResult:
    """Kết quả một vòng J Cơ."""

    round_number: int
    eliminated: List[int]  # player ids eliminated this round (wrong answer / no answer)
    voted_out: List[int]  # player ids voted out this round
    jco_voted_out: bool  # True if J Cơ was voted out → everyone else wins
    rotation_happened: bool  # True if J Cơ role was rotated this round
    new_jco_id: Optional[int]  # new J Cơ after rotation (None if no rotation)


class JCoGame(BaseGame):
    """Game J Cơ – Guess your hidden number."""

    INTERVAL_MAP = {
        "5m": 300,
        "10m": 600,
        "30m": 1800,
        "1h": 3600,
        "6h": 21600,
        "12h": 43200,
    }

    def __init__(self, host_id: int):
        super().__init__(host_id)
        self.settings = self.get_default_settings()

        # Round tracking
        self.current_round: int = 0
        self.round_history: List[JCoRoundResult] = []

        # Player data: {player_id: {"number": int, "mirror_used": bool}}
        # number is the hidden number on their back
        # players dict is inherited from BaseGame

        # J Cơ identity
        self.jco_id: Optional[int] = None

        # Per-round answers: {player_id: int}
        self.current_answers: Dict[int, int] = {}

        # Per-round votes: {voter_id: target_id}
        self.current_votes: Dict[int, int] = {}

        # Eliminated players (in order)
        self.eliminated: List[int] = []

        # Consecutive rounds with no elimination (for rotation)
        self.no_elimination_streak: int = 0

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_default_settings(self) -> dict:
        return {
            "M": 4,  # numbers 1..M
            "game_interval": "1h",
            "player_limit": 10,
            "rotation": True,  # on/off
        }

    def validate_settings(self, settings: dict) -> tuple[bool, str]:
        if "M" in settings:
            v = settings["M"]
            if not isinstance(v, int) or not (2 <= v <= 10):
                return False, "M phải từ 2 đến 10"

        if "player_limit" in settings:
            v = settings["player_limit"]
            if not isinstance(v, int) or not (4 <= v <= 50):
                return False, "Giới hạn người chơi phải từ 4 đến 50"

        if "game_interval" in settings:
            v = settings["game_interval"]
            if v not in self.INTERVAL_MAP:
                valid = ", ".join(self.INTERVAL_MAP.keys())
                return False, f"game_interval phải là một trong: {valid}"

        if "rotation" in settings:
            v = settings["rotation"]
            if not isinstance(v, bool):
                return False, "rotation phải là On hoặc Off"

        return True, ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def alive_players(self) -> List[int]:
        return [pid for pid in self.players if pid not in self.eliminated]

    @property
    def interval_seconds(self) -> int:
        return self.INTERVAL_MAP.get(self.settings["game_interval"], 3600)

    def _assign_numbers(self):
        """Gán số ngẫu nhiên (1..M) cho tất cả người chơi còn sống."""
        M = self.settings["M"]
        for pid in self.alive_players:
            self.players[pid]["number"] = random.randint(1, M)

    def _pick_jco(self, exclude: Optional[int] = None) -> int:
        """Chọn ngẫu nhiên J Cơ từ người chơi còn sống."""
        candidates = [pid for pid in self.alive_players if pid != exclude]
        return random.choice(candidates)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_game_start(self):
        M = self.settings["M"]
        for pid in self.players:
            self.players[pid] = {
                "number": random.randint(1, M),
                "mirror_used": False,
            }

        # Pick J Cơ
        alive = list(self.players.keys())
        self.jco_id = random.choice(alive)

        self.current_round = 0
        self.no_elimination_streak = 0
        self.log_event(
            f"Game J Cơ bắt đầu với {len(self.players)} người chơi | "
            f"J Cơ: Player {self.jco_id}"
        )

    async def on_game_end(self):
        self.log_event("Game J Cơ kết thúc")

    # ------------------------------------------------------------------
    # Core: answer
    # ------------------------------------------------------------------

    def answer(self, player_id: int, number: int) -> Tuple[bool, str]:
        """Người chơi đoán số của mình cho vòng hiện tại."""
        if player_id not in self.players:
            return False, "Bạn chưa tham gia game"

        if player_id in self.eliminated:
            return False, "Bạn đã bị loại khỏi game"

        M = self.settings["M"]
        if not (1 <= number <= M):
            return False, f"Số phải từ 1 đến {M}"

        self.current_answers[player_id] = number
        return True, ""

    # ------------------------------------------------------------------
    # Core: vote
    # ------------------------------------------------------------------

    def vote(self, voter_id: int, target_id: int) -> Tuple[bool, str]:
        """Vote loại một người chơi (từ vòng 2 trở đi)."""
        if self.current_round < 1:
            return False, "Không thể vote ở vòng đầu tiên"

        if voter_id not in self.players:
            return False, "Bạn chưa tham gia game"

        if voter_id in self.eliminated:
            return False, "Bạn đã bị loại"

        if target_id not in self.players:
            return False, "Người này chưa tham gia game"

        if target_id in self.eliminated:
            return False, "Người này đã bị loại"

        if voter_id == target_id:
            return False, "Bạn không thể vote chính mình"

        if voter_id in self.current_votes:
            return False, "Bạn đã vote rồi, không thể thay đổi"

        self.current_votes[voter_id] = target_id
        return True, ""

    # ------------------------------------------------------------------
    # Core: mirror
    # ------------------------------------------------------------------

    def use_mirror(self, player_id: int) -> Tuple[bool, str, Optional[int]]:
        """Dùng gương để xem số của mình (1 lần duy nhất)."""
        if player_id not in self.players:
            return False, "Bạn chưa tham gia game", None

        if player_id in self.eliminated:
            return False, "Bạn đã bị loại", None

        if self.players[player_id]["mirror_used"]:
            return False, "Bạn đã dùng gương rồi!", None

        self.players[player_id]["mirror_used"] = True
        number = self.players[player_id]["number"]
        self.log_event(f"Player {player_id} đã dùng gương")
        return True, "", number

    # ------------------------------------------------------------------
    # Core: cheat (J Cơ only)
    # ------------------------------------------------------------------

    def cheat(self, player_id: int) -> Tuple[bool, str, Optional[int]]:
        """J Cơ xem số của mình."""
        if player_id != self.jco_id:
            return False, "❌ Bạn không phải J Cơ!", None

        number = self.players[player_id]["number"]
        return True, "", number

    # ------------------------------------------------------------------
    # Core: get others' numbers (checkNumber)
    # ------------------------------------------------------------------

    def get_others_numbers(self, player_id: int) -> Tuple[bool, str, List[Tuple[int, int]]]:
        """Xem số trên gáy của tất cả người chơi khác còn sống."""
        if player_id not in self.players:
            return False, "Bạn chưa tham gia game", []

        if player_id in self.eliminated:
            return False, "Bạn đã bị loại", []

        result = []
        for pid in self.alive_players:
            if pid != player_id:
                result.append((pid, self.players[pid]["number"]))

        return True, "", result

    # ------------------------------------------------------------------
    # Core: resolve round
    # ------------------------------------------------------------------

    def resolve_round(self) -> Optional[JCoRoundResult]:
        """Xử lý kết quả vòng hiện tại."""
        alive = self.alive_players
        if len(alive) <= 1:
            return None

        self.current_round += 1

        eliminated_this_round: List[int] = []
        voted_out_this_round: List[int] = []
        jco_voted_out = False
        rotation_happened = False
        new_jco_id: Optional[int] = None

        # --- Phase 1: Check answers ---
        for pid in alive:
            if pid == self.jco_id:
                # J Cơ always knows their number, auto-survives answer phase
                continue

            if pid not in self.current_answers:
                # No answer → eliminated
                eliminated_this_round.append(pid)
                self.log_event(
                    f"Vòng {self.current_round}: Player {pid} không trả lời → bị loại"
                )
            else:
                real_number = self.players[pid]["number"]
                guessed = self.current_answers[pid]
                if guessed != real_number:
                    eliminated_this_round.append(pid)
                    self.log_event(
                        f"Vòng {self.current_round}: Player {pid} đoán sai "
                        f"({guessed} vs {real_number}) → bị loại"
                    )

        # --- Phase 2: Vote resolution (from round 2+) ---
        if self.current_round >= 2 and self.current_votes:
            # Count votes per target
            vote_counts: Dict[int, int] = {}
            for target_id in self.current_votes.values():
                vote_counts[target_id] = vote_counts.get(target_id, 0) + 1

            # >50% of alive players needed
            alive_count = len(alive)
            threshold = alive_count / 2

            for target_id, count in vote_counts.items():
                if count > threshold and target_id not in eliminated_this_round:
                    voted_out_this_round.append(target_id)
                    if target_id == self.jco_id:
                        jco_voted_out = True
                    self.log_event(
                        f"Vòng {self.current_round}: Player {target_id} bị vote loại "
                        f"({count}/{alive_count} phiếu)"
                    )

        # Apply eliminations
        for pid in eliminated_this_round:
            if pid not in self.eliminated:
                self.eliminated.append(pid)
        for pid in voted_out_this_round:
            if pid not in self.eliminated:
                self.eliminated.append(pid)

        # --- Phase 3: Rotation check ---
        total_eliminated = len(eliminated_this_round) + len(voted_out_this_round)
        if total_eliminated == 0:
            self.no_elimination_streak += 1
        else:
            self.no_elimination_streak = 0

        if (
            self.settings["rotation"]
            and self.no_elimination_streak >= 3
            and not jco_voted_out
            and len(self.alive_players) >= 2
        ):
            old_jco = self.jco_id
            new_jco_id = self._pick_jco(exclude=old_jco)
            self.jco_id = new_jco_id
            rotation_happened = True
            self.no_elimination_streak = 0
            self.log_event(
                f"Vòng {self.current_round}: Đảo vai J Cơ! "
                f"Player {old_jco} → Player {new_jco_id}"
            )

        # --- Reassign numbers for next round ---
        self._assign_numbers()

        result = JCoRoundResult(
            round_number=self.current_round,
            eliminated=eliminated_this_round,
            voted_out=voted_out_this_round,
            jco_voted_out=jco_voted_out,
            rotation_happened=rotation_happened,
            new_jco_id=new_jco_id,
        )

        self.round_history.append(result)

        # Clear per-round data
        self.current_answers.clear()
        self.current_votes.clear()

        return result

    # ------------------------------------------------------------------
    # Game-over check
    # ------------------------------------------------------------------

    def check_game_over(self) -> Tuple[bool, str, Optional[int]]:
        """
        Kiểm tra game kết thúc.
        Returns: (is_over, reason, winner_or_none)
          reason: "jco_voted_out" | "jco_last" | "all_dead" | ""
        """
        alive = self.alive_players

        # J Cơ bị vote → tất cả thắng
        if self.round_history and self.round_history[-1].jco_voted_out:
            return True, "jco_voted_out", None

        # J Cơ bị loại (safety — phòng trường hợp bị loại ngoài vote)
        if self.jco_id in self.eliminated:
            return True, "jco_voted_out", None

        # Chỉ còn J Cơ
        if len(alive) == 1 and alive[0] == self.jco_id:
            return True, "jco_last", self.jco_id

        # Không còn ai (hoặc chỉ còn 1 người — J Cơ đã bị loại ở check trên)
        if len(alive) <= 1:
            return True, "all_dead", alive[0] if alive else None

        return False, "", None

    # ------------------------------------------------------------------
    # Info helpers
    # ------------------------------------------------------------------

    def get_elimination_history(self) -> List[Tuple[int, List[int], List[int]]]:
        """Trả về [(round_number, eliminated, voted_out)] cho history."""
        return [
            (rr.round_number, rr.eliminated, rr.voted_out)
            for rr in self.round_history
        ]
