from datetime import datetime
from typing import Optional, Dict, List

from enums import GameState


class BaseGame:
    """Lớp cơ sở cho tất cả các game."""

    def __init__(self, host_id: int):
        self.host_id = host_id
        self.state = GameState.REGISTERING
        self.players: Dict[int, dict] = {}
        self.settings: dict = {}
        self.notif_channel_id: Optional[int] = None
        self.game_channel_id: Optional[int] = None
        self.start_time: Optional[datetime] = None
        self.next_day_at: Optional[datetime] = None
        self.event_log: List[str] = []

    def get_default_settings(self) -> dict:
        """Trả về settings mặc định, override trong subclass."""
        return {}

    def validate_settings(self, settings: dict) -> tuple[bool, str]:
        """Validate settings, override trong subclass."""
        return True, ""

    async def on_game_start(self):
        """Hook khi game bắt đầu."""
        pass

    async def on_game_end(self):
        """Hook khi game kết thúc."""
        pass

    async def on_day_change(self):
        """Hook khi chuyển ngày."""
        pass

    def log_event(self, event: str):
        """Ghi log event với timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.event_log.append(f"[{timestamp}] {event}")
