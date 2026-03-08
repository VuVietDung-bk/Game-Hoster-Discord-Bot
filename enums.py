from enum import Enum


class GameType(Enum):
    LI_XI_NGAY_TET = "li_xi_ngay_tet"
    KRO = "kro"
    JCO = "jco"
    CHEN_THANH = "chen_thanh"


class GameState(Enum):
    IDLE = "idle"
    REGISTERING = "registering"
    REGISTRATION_CLOSED = "registration_closed"
    RUNNING = "running"
    PAUSED = "paused"
    ENDED = "ended"


class GameInterval(Enum):
    TEST_INTERVAL = "10m"
    TWELVE_HOURS = "12h"
    ONE_DAY = "1d"
    TWO_DAYS = "2d"


class KRoInterval(Enum):
    ONE_MIN = "1m"
    TWO_MIN = "2m"
    FIVE_MIN = "5m"
    TEN_MIN = "10m"
    THIRTY_MIN = "30m"
    TWELVE_HOURS = "12h"
