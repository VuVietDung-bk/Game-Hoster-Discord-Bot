from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from enums import GameState
from games.base_game import BaseGame


@dataclass
class ChenThanhRoundResult:
    """Kết quả một vòng Chén Thánh Phản Bội."""

    round_number: int
    # Actions (not revealing who did what)
    contributor_count: int
    stealer_count: int
    no_action_count: int
    # Pot dynamics
    pot_before: int
    pot_after: int
    # Money distribution
    money_gained: Dict[int, int]  # player_id -> money earned this round (from pot)
    # Dares
    dares: List[Tuple[int, int, bool]]  # (challenger_id, target_id, target_stole_last_round)
    dare_deaths: List[int]  # player_ids who died from dares
    # Economy
    balances_after: Dict[int, int]  # player_id -> balance after round


class ChenThanhGame(BaseGame):
    """Game Chén Thánh Phản Bội – Contribute or Steal."""

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

        # Round tracking
        self.current_round: int = 0
        self.round_history: List[ChenThanhRoundResult] = []

        # The Holy Grail pot
        self.pot: int = 0

        # Per-round actions: {player_id: "contribute" | "steal"}
        self.current_actions: Dict[int, str] = {}

        # Previous round actions (for dare eligibility)
        self.previous_actions: Dict[int, str] = {}

        # Per-round dares: {challenger_id: target_id}
        self.current_dares: Dict[int, int] = {}

        # Eliminated (dead) players
        self.eliminated: List[int] = []

        # Player balances: {player_id: int}
        self.balances: Dict[int, int] = {}

        # Total contributions per player (for tiebreaker)
        self.total_contributions: Dict[int, int] = {}

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_default_settings(self) -> dict:
        return {
            "M": 10,  # coins given each round
            "N": 50,  # target to win
            "player_limit": 10,
            "game_interval": "5m",
        }

    def validate_settings(self, settings: dict) -> tuple[bool, str]:
        M = settings.get("M", self.settings["M"])
        N = settings.get("N", self.settings["N"])

        if "M" in settings:
            v = settings["M"]
            if not isinstance(v, int) or not (10 <= v <= 100):
                return False, "M phải từ 10 đến 100"

        if "N" in settings:
            v = settings["N"]
            if not isinstance(v, int) or not (50 <= v <= 1000):
                return False, "N phải từ 50 đến 1000"

        if "player_limit" in settings:
            v = settings["player_limit"]
            if not isinstance(v, int) or not (4 <= v <= 50):
                return False, "Giới hạn người chơi phải từ 4 đến 50"

        if "game_interval" in settings:
            v = settings["game_interval"]
            if v not in self.INTERVAL_MAP:
                valid = ", ".join(self.INTERVAL_MAP.keys())
                return False, f"game_interval phải là một trong: {valid}"

        # N must be > M
        if N <= M:
            return False, "N phải lớn hơn M"

        return True, ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def alive_players(self) -> List[int]:
        return [pid for pid in self.players if pid not in self.eliminated]

    @property
    def interval_seconds(self) -> int:
        return self.INTERVAL_MAP.get(self.settings["game_interval"], 300)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_game_start(self):
        M = self.settings["M"]
        for pid in self.players:
            self.players[pid] = {}
            self.balances[pid] = 0
            self.total_contributions[pid] = 0

        self.pot = 0
        self.current_round = 0
        self.previous_actions.clear()
        self.log_event(
            f"Game Chén Thánh bắt đầu với {len(self.players)} người chơi | "
            f"M={M}, N={self.settings['N']}"
        )

    async def on_game_end(self):
        self.log_event("Game Chén Thánh kết thúc")

    # ------------------------------------------------------------------
    # Core: choose action
    # ------------------------------------------------------------------

    def choose_action(self, player_id: int, action: str) -> Tuple[bool, str]:
        """Player chooses contribute or steal for this round."""
        if player_id not in self.players:
            return False, "Bạn chưa tham gia game"

        if player_id in self.eliminated:
            return False, "Bạn đã bị loại khỏi game"

        action = action.lower()
        if action not in ("contribute", "steal"):
            return False, "Hành động phải là `contribute` hoặc `steal`"

        if player_id in self.current_actions:
            return False, "Bạn đã chọn hành động rồi, không thể thay đổi"

        self.current_actions[player_id] = action
        return True, ""

    # ------------------------------------------------------------------
    # Core: dare (challenge)
    # ------------------------------------------------------------------

    def dare(self, challenger_id: int, target_id: int) -> Tuple[bool, str, Optional[int]]:
        """
        Challenge another player. Resolves immediately.
        Available from round 2+ if contributed last round.
        Returns: (success, error_msg, dead_player_id_or_None)
        """
        if challenger_id not in self.players:
            return False, "Bạn chưa tham gia game", None

        if challenger_id in self.eliminated:
            return False, "Bạn đã bị loại", None

        if target_id not in self.players:
            return False, "Người này chưa tham gia game", None

        if target_id in self.eliminated:
            return False, "Người này đã bị loại", None

        if challenger_id == target_id:
            return False, "Bạn không thể thách thức chính mình", None

        if self.current_round < 1:
            return False, "Chỉ có thể thách thức từ vòng 2 trở đi", None

        # Challenger must have contributed last round
        if self.previous_actions.get(challenger_id) != "contribute":
            return False, "Bạn phải Đóng góp ở vòng trước để được thách thức", None

        if challenger_id in self.current_dares:
            return False, "Bạn đã thách thức người khác rồi trong vòng này", None

        # Resolve immediately
        self.current_dares[challenger_id] = target_id
        target_stole = self.previous_actions.get(target_id) == "steal"

        if target_stole:
            dead_id = target_id
            self.log_event(
                f"Vòng {self.current_round + 1}: Player {challenger_id} thách thức "
                f"Player {target_id} → Target đã Đánh cắp → Target chết!"
            )
        else:
            dead_id = challenger_id
            self.log_event(
                f"Vòng {self.current_round + 1}: Player {challenger_id} thách thức "
                f"Player {target_id} → Target đã Đóng góp → Challenger chết!"
            )

        if dead_id not in self.eliminated:
            self.eliminated.append(dead_id)

        return True, "", dead_id

    # ------------------------------------------------------------------
    # Core: resolve round
    # ------------------------------------------------------------------

    def resolve_round(self) -> Optional[ChenThanhRoundResult]:
        """Process end of round: pot resolution based on actions.

        Economy:
        - Each alive player receives M coins.
        - Contributors spend M to put into pot.
        - Stealers keep their M (don't contribute to pot).
        - No-action players receive nothing.
        Dares are resolved immediately when called, not here.
        """
        alive = self.alive_players
        if len(alive) <= 1:
            return None

        self.current_round += 1
        M = self.settings["M"]

        # --- Phase 0: Distribute M and apply actions ---
        contributors = []
        stealers = []
        no_action = []

        for pid in alive:
            if pid in self.current_actions:
                # Player acted → receives M
                self.balances[pid] += M
                if self.current_actions[pid] == "contribute":
                    # Contributor puts M into pot (net 0 on hand)
                    self.balances[pid] -= M
                    self.pot += M
                    contributors.append(pid)
                else:
                    # Stealer keeps M
                    stealers.append(pid)
            else:
                # No action → receives nothing, counted as non-contributor
                no_action.append(pid)

        pot_before = self.pot

        # Collect dare records from current_dares (already resolved)
        dare_deaths: List[int] = []
        dare_records: List[Tuple[int, int, bool]] = []
        for challenger_id, target_id in self.current_dares.items():
            target_stole = self.previous_actions.get(target_id) == "steal"
            dare_records.append((challenger_id, target_id, target_stole))
            dead_id = target_id if target_stole else challenger_id
            if dead_id not in dare_deaths:
                dare_deaths.append(dead_id)

        # --- Phase 1: Resolve pot distribution ---
        # Only count actions of players still alive (not eliminated by dare)
        contributors = [p for p in contributors if p not in self.eliminated]
        stealers = [p for p in stealers if p not in self.eliminated]
        no_action = [p for p in no_action if p not in self.eliminated]

        alive_after_dares = self.alive_players
        money_gained: Dict[int, int] = {pid: 0 for pid in alive_after_dares}

        if len(stealers) == 0 and len(contributors) > 0:
            # All alive contributed → pot doubles, split evenly
            doubled_pot = self.pot * 2
            share = doubled_pot // len(contributors)
            for pid in contributors:
                self.balances[pid] += share
                money_gained[pid] = share
            self.pot = doubled_pot - share * len(contributors)
            self.log_event(
                f"Vòng {self.current_round}: Tất cả Đóng góp! "
                f"Hũ {self.pot + share * len(contributors)} → chia {share}/người"
            )
        elif len(stealers) > 0 and (len(contributors) > 0 or self.pot > 0):
            # Some steal → stealers split entire pot
            if self.pot > 0:
                share = self.pot // len(stealers)
                for pid in stealers:
                    self.balances[pid] += share
                    money_gained[pid] = share
                self.pot = self.pot - share * len(stealers)
            else:
                share = 0
            self.log_event(
                f"Vòng {self.current_round}: {len(stealers)} kẻ Đánh cắp "
                f"chia hũ → {share}/kẻ cắp"
            )
        elif len(stealers) == 0 and len(contributors) == 0:
            # Nobody contributed and nobody stole (all no-action)
            self.log_event(
                f"Vòng {self.current_round}: Không ai hành động! Hũ giữ nguyên."
            )

        # Track contributions for tiebreaker
        for pid in contributors:
            self.total_contributions[pid] = self.total_contributions.get(pid, 0) + 1

        # Save previous actions for next round's dare (only those who acted)
        self.previous_actions = dict(self.current_actions)

        pot_after = self.pot

        result = ChenThanhRoundResult(
            round_number=self.current_round,
            contributor_count=len(contributors),
            stealer_count=len(stealers),
            no_action_count=len(no_action),
            pot_before=pot_before,
            pot_after=pot_after,
            money_gained=money_gained,
            dares=dare_records,
            dare_deaths=dare_deaths,
            balances_after=dict(self.balances),
        )
        self.round_history.append(result)

        # Clear per-round data
        self.current_actions.clear()
        self.current_dares.clear()

        return result

    # ------------------------------------------------------------------
    # Game-over check
    # ------------------------------------------------------------------

    def check_game_over(self) -> Tuple[bool, str, List[int]]:
        """
        Check if game is over.
        Returns: (is_over, reason, winner_ids)
          reason: "target_reached" | "last_survivor" | "all_dead" | ""
          winner_ids: list of winner player IDs (can be multiple for ties)
        """
        alive = self.alive_players
        N = self.settings["N"]

        # Check if anyone reached N
        reached = [pid for pid in alive if self.balances.get(pid, 0) >= N]
        if reached:
            # Sort by balance descending, then by total_contributions descending
            reached.sort(
                key=lambda pid: (
                    self.balances[pid],
                    self.total_contributions.get(pid, 0),
                ),
                reverse=True,
            )
            # Winner(s): highest balance
            max_balance = self.balances[reached[0]]
            top = [pid for pid in reached if self.balances[pid] == max_balance]
            if len(top) == 1:
                return True, "target_reached", top
            # Tiebreaker: most contributions
            max_contrib = max(self.total_contributions.get(pid, 0) for pid in top)
            winners = [
                pid for pid in top
                if self.total_contributions.get(pid, 0) == max_contrib
            ]
            return True, "target_reached", winners

        # Last survivor
        if len(alive) == 1:
            return True, "last_survivor", alive

        # All dead
        if len(alive) == 0:
            return True, "all_dead", []

        return False, "", []

    # ------------------------------------------------------------------
    # Info helpers
    # ------------------------------------------------------------------

    def get_round_history_summary(self) -> List[Tuple[int, int, int, int, List[int]]]:
        """Return [(round, contributors, stealers, dare_deaths)] for history."""
        return [
            (
                rr.round_number,
                rr.contributor_count,
                rr.stealer_count,
                rr.no_action_count,
                rr.dare_deaths,
            )
            for rr in self.round_history
        ]
