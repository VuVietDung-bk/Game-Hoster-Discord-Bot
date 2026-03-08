from typing import Optional

from enums import GameType
from games.base_game import BaseGame
from games.li_xi_game import LiXiNgayTetGame
from games.kro_game import KRoGame
from games.jco_game import JCoGame
from games.chen_thanh_game import ChenThanhGame


class GameFactory:
    """Factory để tạo game theo loại."""

    @staticmethod
    def create_game(game_type: GameType, host_id: int) -> Optional[BaseGame]:
        if game_type == GameType.LI_XI_NGAY_TET:
            return LiXiNgayTetGame(host_id)
        if game_type == GameType.KRO:
            return KRoGame(host_id)
        if game_type == GameType.JCO:
            return JCoGame(host_id)
        if game_type == GameType.CHEN_THANH:
            return ChenThanhGame(host_id)
        return None
