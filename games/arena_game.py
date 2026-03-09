from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from enums import GameState
from games.base_game import BaseGame


@dataclass
class ArenaRoundResult:
    """Kết quả một vòng Đấu trường sinh tử."""

    round_number: int
    # Stamina changes per player (positive = gained, negative = lost)
    stamina_changes: Dict[int, int]
    # Deaths this round (player_ids)
    deaths: List[int]
    # Destroy kills: [(destroyer, victim)]
    destroy_kills: List[Tuple[int, int]]
    # Stamina snapshot after round
    stamina_after: Dict[int, int]


class ArenaGame(BaseGame):
    """Game Đấu trường sinh tử – Arena Deathmatch."""

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
        self.round_history: List[ArenaRoundResult] = []

        # Per-round actions: {player_id: {"type": str, "target": Optional[int]}}
        self.current_actions: Dict[int, dict] = {}

        # Eliminated (dead) players
        self.eliminated: List[int] = []

        # Player stamina: {player_id: int}
        self.stamina: Dict[int, int] = {}

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_default_settings(self) -> dict:
        return {
            "M": 100,
            "player_limit": 10,
            "game_interval": "5m",
        }

    def validate_settings(self, settings: dict) -> tuple[bool, str]:
        if "M" in settings:
            v = settings["M"]
            if not isinstance(v, int) or not (50 <= v <= 500):
                return False, "M phải từ 50 đến 500"

        if "player_limit" in settings:
            v = settings["player_limit"]
            if not isinstance(v, int) or not (4 <= v <= 50):
                return False, "Giới hạn người chơi phải từ 4 đến 50"

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
            self.stamina[pid] = M

        self.current_round = 0
        self.log_event(
            f"Game Đấu trường bắt đầu với {len(self.players)} người chơi | M={M}"
        )

    async def on_game_end(self):
        self.log_event("Game Đấu trường kết thúc")

    # ------------------------------------------------------------------
    # Core: choose action
    # ------------------------------------------------------------------

    def choose_action(
        self,
        player_id: int,
        action_type: str,
        target_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Player chooses an action for this round.

        action_type: "attack", "defend", "charge", "destroy", "none"
        target_id: required for attack and destroy
        """
        if player_id not in self.players:
            return False, "Bạn chưa tham gia game"

        if player_id in self.eliminated:
            return False, "Bạn đã bị loại khỏi game"

        action_type = action_type.lower()
        valid_actions = ("attack", "defend", "charge", "destroy", "none")
        if action_type not in valid_actions:
            return False, f"Hành động phải là một trong: {', '.join(valid_actions)}"

        if player_id in self.current_actions:
            return False, "Bạn đã chọn hành động rồi, không thể thay đổi"

        M = self.settings["M"]
        sta = self.stamina.get(player_id, 0)

        if action_type == "attack":
            if sta < 20:
                return False, f"Không đủ Stamina để Tấn công (cần 20, có {sta})"
            if target_id is None:
                return False, "Tấn công cần chọn mục tiêu"
            if target_id == player_id:
                return False, "Không thể tấn công chính mình"
            if target_id not in self.players:
                return False, "Mục tiêu chưa tham gia game"
            if target_id in self.eliminated:
                return False, "Mục tiêu đã bị loại"

        elif action_type == "defend":
            if sta < 10:
                return False, f"Không đủ Stamina để Phòng thủ (cần 10, có {sta})"

        elif action_type == "destroy":
            if sta < M:
                return False, f"Không đủ Stamina để Hủy diệt (cần {M}, có {sta})"
            if sta < 2 * M:
                return False, f"Cần đạt {2 * M} Stamina để mở khóa Hủy diệt (có {sta})"
            if target_id is None:
                return False, "Hủy diệt cần chọn mục tiêu"
            if target_id == player_id:
                return False, "Không thể hủy diệt chính mình"
            if target_id not in self.players:
                return False, "Mục tiêu chưa tham gia game"
            if target_id in self.eliminated:
                return False, "Mục tiêu đã bị loại"

        self.current_actions[player_id] = {
            "type": action_type,
            "target": target_id,
        }
        return True, ""

    # ------------------------------------------------------------------
    # Core: resolve round
    # ------------------------------------------------------------------

    def resolve_round(self) -> Optional[ArenaRoundResult]:
        """Process end of round with 3-phase resolution.

        Phase 1: DESTROY — instant kill, target is removed before other phases.
        Phase 2: CHARGE — heal before taking damage.
        Phase 3: ATTACK vs DEFEND — calculate damage.

        After all phases: players at <= 0 stamina die. Attackers who killed
        someone get M/4 stamina bonus.
        """
        alive = self.alive_players
        if len(alive) <= 1:
            return None

        self.current_round += 1
        M = self.settings["M"]

        stamina_changes: Dict[int, int] = {pid: 0 for pid in alive}
        deaths: List[int] = []
        destroy_kills: List[Tuple[int, int]] = []

        # Build action lookup for alive players only
        actions: Dict[int, dict] = {}
        for pid in alive:
            if pid in self.current_actions:
                actions[pid] = self.current_actions[pid]
            else:
                actions[pid] = {"type": "none", "target": None}

        # ==============================================================
        # Phase 1: DESTROY
        # ==============================================================
        destroyed_this_round: List[int] = []
        for pid, act in actions.items():
            if act["type"] == "destroy" and pid not in destroyed_this_round:
                target = act["target"]
                if target and target not in self.eliminated and target not in destroyed_this_round:
                    # Cost M stamina
                    self.stamina[pid] -= M
                    stamina_changes[pid] -= M
                    # Kill target
                    destroyed_this_round.append(target)
                    destroy_kills.append((pid, target))
                    self.log_event(
                        f"Vòng {self.current_round}: Player {pid} HỦY DIỆT Player {target}!"
                    )

        # Mark destroyed players as eliminated immediately
        for pid in destroyed_this_round:
            if pid not in self.eliminated:
                self.eliminated.append(pid)
                deaths.append(pid)

        # Remaining alive after destroy (excludes destroyed targets)
        alive_after_destroy = [p for p in alive if p not in destroyed_this_round]

        # ==============================================================
        # Phase 2: CHARGE
        # ==============================================================
        for pid in alive_after_destroy:
            if actions.get(pid, {}).get("type") == "charge":
                self.stamina[pid] += 25
                stamina_changes[pid] += 25

        # ==============================================================
        # Phase 3: ATTACK vs DEFEND
        # ==============================================================

        # Count attackers per target (only from alive, non-destroyed players)
        attackers_per_target: Dict[int, List[int]] = {}
        for pid in alive_after_destroy:
            act = actions.get(pid, {})
            if act.get("type") == "attack":
                target = act["target"]
                if target and target not in destroyed_this_round:
                    attackers_per_target.setdefault(target, []).append(pid)

        # Deduct attack cost
        for pid in alive_after_destroy:
            act = actions.get(pid, {})
            if act.get("type") == "attack":
                self.stamina[pid] -= 20
                stamina_changes[pid] -= 20

        # Deduct defend cost
        for pid in alive_after_destroy:
            act = actions.get(pid, {})
            if act.get("type") == "defend":
                self.stamina[pid] -= 10
                stamina_changes[pid] -= 10

        # Calculate damage for each target
        for target, attacker_list in attackers_per_target.items():
            if target in destroyed_this_round:
                continue

            n_attackers = len(attacker_list)
            target_action = actions.get(target, {}).get("type", "none")
            is_charging = target_action == "charge"
            is_defending = target_action == "defend"

            # Base damage per attacker
            if n_attackers >= 3:
                base_dmg = 40
            else:
                base_dmg = 30

            if is_defending:
                if n_attackers <= 2:
                    # Block completely
                    total_damage = 0
                else:
                    # Block first 2, take 50% from remainder
                    total_damage = 0
                    for i, _ in enumerate(attacker_list):
                        if i < 2:
                            continue  # blocked
                        total_damage += base_dmg
                    total_damage = total_damage // 2
            else:
                total_damage = base_dmg * n_attackers
                if is_charging:
                    # x1.5 damage when charging
                    total_damage = (total_damage * 3) // 2

            if total_damage > 0:
                self.stamina[target] -= total_damage
                stamina_changes[target] -= total_damage

        # ==============================================================
        # Post-phases: Check deaths from combat
        # ==============================================================
        combat_deaths: List[int] = []
        for pid in alive_after_destroy:
            if self.stamina[pid] <= 0 and pid not in self.eliminated:
                self.eliminated.append(pid)
                deaths.append(pid)
                combat_deaths.append(pid)

        # Bonus: Attackers who contributed to a kill get M/4 stamina
        bonus = M // 4
        if bonus > 0:
            for dead_pid in combat_deaths:
                if dead_pid in attackers_per_target:
                    # dead_pid was attacked and died — reward attackers
                    for attacker_pid in attackers_per_target[dead_pid]:
                        if attacker_pid not in self.eliminated:
                            self.stamina[attacker_pid] += bonus
                            stamina_changes[attacker_pid] += bonus

        result = ArenaRoundResult(
            round_number=self.current_round,
            stamina_changes=stamina_changes,
            deaths=deaths,
            destroy_kills=destroy_kills,
            stamina_after=dict(self.stamina),
        )
        self.round_history.append(result)

        # Clear per-round data
        self.current_actions.clear()

        return result

    # ------------------------------------------------------------------
    # Game-over check
    # ------------------------------------------------------------------

    def check_game_over(self) -> Tuple[bool, str, List[int]]:
        """Check if game is over.

        Returns: (is_over, reason, winner_ids)
          reason: "last_survivor" | "all_dead" | ""
        """
        alive = self.alive_players

        if len(alive) == 1:
            return True, "last_survivor", alive

        if len(alive) == 0:
            return True, "all_dead", []

        return False, "", []

    # ------------------------------------------------------------------
    # Info helpers
    # ------------------------------------------------------------------

    def get_round_history_summary(self) -> List[Tuple[int, Dict[int, int], List[int]]]:
        """Return [(round, stamina_changes, deaths)] for history."""
        return [
            (rr.round_number, rr.stamina_changes, rr.deaths)
            for rr in self.round_history
        ]
