"""坐标表 —— 从作者 xjw580/hs-script 逐条抄录，不要"顺手优化"。

来源：
  hs-script-app/.../utils/GameUtil.kt
  hs-script-app/.../strategy/mode/TournamentModeStrategy.kt
  hs-script-app/.../strategy/mode/AdventureModeStrategy.kt

所有数值都是 GameRect(left, right, top, bottom)，语义见 geometry.py。
改坐标之前先想清楚：作者是在特定窗口宽高比下调的，乱改等于全歪。
"""
from __future__ import annotations

from .geometry import GameRect

INVALID = GameRect(0.0, 0.0, 0.0, 0.0)

# ---------------------------------------------------------------- 对局内通用
CENTER = GameRect(-0.1, 0.1, 0.1, -0.1)
RIGHT_CENTER = GameRect(0.4, 0.5, 0.1, -0.1)
CONFIRM = GameRect(-0.0546, 0.0601, 0.2709, 0.3222)
CARD_ADJUSTMENT_CONFIRM = GameRect(-0.0445, 0.0501, 0.2766, 0.3453)  # LoginModeStrategy: 卡牌调整弹窗确定
END_TURN = GameRect(0.3700, 0.4525, -0.0572, -0.0181)
RECONNECT = GameRect(-0.1845, -0.0396, 0.2282, 0.2904)
CANCEL_CONNECT = GameRect(0.0266, 0.1714, 0.2282, 0.2904)
SURRENDER = GameRect(-0.0629, 0.0607, -0.1677, -0.1279)
RESTART_GAME = GameRect(-0.0365, 0.0302, 0.0878, 0.1272)

MY_HERO = GameRect(-0.0357, 0.0342, 0.1978, 0.2691)
RIVAL_HERO = GameRect(-0.0453, 0.0488, -0.3620, -0.2355)
MY_POWER = GameRect(0.0855, 0.1569, 0.2254, 0.3176)
RIVAL_POWER = GameRect(0.0840, 0.1554, -0.3260, -0.2338)
DECK = GameRect(0.4376, 0.4688, 0.0346, 0.1645)

STARSHIP_LAUNCH = GameRect(0.0180, 0.1268, 0.2723, 0.4089)
STARSHIP_CANCEL = GameRect(-0.1107, -0.0295, 0.3106, 0.4120)

# 表情/交互菜单（右键自己或对面英雄后出现）
EMOTE_THANK = GameRect(-0.1604, -0.0404, 0.1153, 0.1502)
EMOTE_GREET = GameRect(-0.1907, -0.0707, 0.2799, 0.3148)
EMOTE_ERROR = GameRect(0.0786, 0.1986, 0.1981, 0.2331)

# ---------------------------------------------------------------- 抉择/发现
CHOOSE_ONE = (
    GameRect(-0.2030, -0.0364, -0.1775, 0.1677),
    GameRect(0.0412, 0.2030, -0.1732, 0.1656),
)

TIMELINE = (
    GameRect(-0.4699, -0.3743, 0.1917, 0.2889),  # 0 回溯
    GameRect(-0.2965, -0.2009, 0.1917, 0.2889),  # 1 维持
)

DISCOVER_4 = (
    GameRect(-0.3332, -0.1911, -0.1702, 0.1160),
    GameRect(-0.1570, -0.0149, -0.1702, 0.1160),
    GameRect(0.0182, 0.1603, -0.1702, 0.1160),
    GameRect(0.1934, 0.3355, -0.1702, 0.1160),
)

# 「进行选择」类面板（克苏恩仪式等）：4 张大牌，间距比发现面板宽得多。
# 作者 DISCOVER_4 是按窄版发现面板量的，直接拿来点这种面板会落在两张牌之间（真机截图实证）。
CHOICE_GENERAL_4 = (
    GameRect(-0.4769, -0.2848, -0.2189, 0.2138),
    GameRect(-0.2208, -0.0286, -0.2189, 0.2138),
    GameRect(0.0354, 0.2276, -0.2189, 0.2138),
    GameRect(0.2962, 0.4883, -0.2189, 0.2138),
)

DISCOVER_3 = (
    GameRect(-0.3037, -0.1595, -0.1702, 0.1160),
    GameRect(-0.0666, 0.0741, -0.1702, 0.1160),
    GameRect(0.1656, 0.3106, -0.1702, 0.1160),
)

# ---------------------------------------------------------------- 手牌
# MY_HAND_DECK_RECTS[size-1][index]，size = 手牌张数（1..10）
MY_HAND = (
    (GameRect(-0.0693, 0.0136, 0.3675, 0.5000),),
    (
        GameRect(-0.1149, -0.0316, 0.3675, 0.5000),
        GameRect(-0.0242, 0.0590, 0.3675, 0.5000),
    ),
    (
        GameRect(-0.1599, -0.0767, 0.3675, 0.5000),
        GameRect(-0.0693, 0.0140, 0.3675, 0.5000),
        GameRect(0.0214, 0.1047, 0.3675, 0.5000),
    ),
    (
        GameRect(-0.1930, -0.1307, 0.3855, 0.5000),
        GameRect(-0.1092, -0.0347, 0.3742, 0.5000),
        GameRect(-0.0208, 0.0507, 0.3814, 0.4995),
        GameRect(0.0744, 0.1425, 0.4158, 0.5000),
    ),
    (
        GameRect(-0.2034, -0.1471, 0.4116, 0.5000),
        GameRect(-0.1338, -0.0704, 0.3888, 0.5000),
        GameRect(-0.0704, -0.0071, 0.3698, 0.5000),
        GameRect(0.0077, 0.0604, 0.3935, 0.5000),
        GameRect(0.0858, 0.1456, 0.4144, 0.5000),
    ),
    (
        GameRect(-0.2115, -0.1672, 0.4144, 0.5000),
        GameRect(-0.1514, -0.1028, 0.3964, 0.5000),
        GameRect(-0.0975, -0.0448, 0.3755, 0.5000),
        GameRect(-0.0384, 0.0087, 0.3755, 0.5000),
        GameRect(0.0270, 0.0671, 0.3812, 0.4990),
        GameRect(0.0903, 0.1579, 0.4240, 0.5000),
    ),
    (
        GameRect(-0.2179, -0.1799, 0.4192, 0.5000),
        GameRect(-0.1640, -0.1232, 0.4040, 0.5000),
        GameRect(-0.1155, -0.0690, 0.3869, 0.5000),
        GameRect(-0.0712, -0.0233, 0.3717, 0.5000),
        GameRect(-0.0152, 0.0235, 0.3755, 0.5000),
        GameRect(0.0418, 0.0727, 0.3821, 0.5000),
        GameRect(0.0956, 0.1617, 0.4211, 0.5000),
    ),
    (
        GameRect(-0.2210, -0.1901, 0.4259, 0.5000),
        GameRect(-0.1746, -0.1394, 0.4125, 0.5000),
        GameRect(-0.1324, -0.0916, 0.3973, 0.5000),
        GameRect(-0.0912, -0.0490, 0.3745, 0.5000),
        GameRect(-0.0469, -0.0103, 0.3688, 0.5000),
        GameRect(0.0038, 0.0326, 0.3745, 0.5000),
        GameRect(0.0534, 0.0759, 0.4040, 0.5000),
        GameRect(0.1030, 0.1536, 0.4163, 0.4990),
    ),
    (
        GameRect(-0.2274, -0.1964, 0.4335, 0.5000),
        GameRect(-0.1820, -0.1496, 0.4335, 0.5000),
        GameRect(-0.1429, -0.1099, 0.4059, 0.5000),
        GameRect(-0.1060, -0.0687, 0.3888, 0.5000),
        GameRect(-0.0712, -0.0346, 0.3698, 0.5000),
        GameRect(-0.0268, 0.0034, 0.3745, 0.5000),
        GameRect(0.0186, 0.0502, 0.3764, 0.4563),
        GameRect(0.0639, 0.0942, 0.3878, 0.4610),
        GameRect(0.1083, 0.1653, 0.4125, 0.5000),
    ),
    (
        GameRect(-0.2305, -0.2024, 0.4401, 0.5000),
        GameRect(-0.1894, -0.1598, 0.4401, 0.5000),
        GameRect(-0.1524, -0.1250, 0.4097, 0.5000),
        GameRect(-0.1176, -0.0859, 0.3964, 0.5000),
        GameRect(-0.0859, -0.0522, 0.3726, 0.5000),
        GameRect(-0.0511, -0.0208, 0.3726, 0.5000),
        GameRect(-0.0089, 0.0207, 0.3740, 0.4501),
        GameRect(0.0302, 0.0583, 0.3783, 0.4515),
        GameRect(0.0692, 0.0974, 0.3926, 0.4610),
        GameRect(0.1093, 0.1677, 0.4163, 0.5000),
    ),
)

# ---------------------------------------------------------------- 场上随从
# [size & 1][index]，偶数张用第 0 组，奇数张用第 1 组
MY_BOARD = (
    (
        GameRect(-0.2689, -0.2111, -0.0033, 0.1050),
        GameRect(-0.1731, -0.1153, -0.0033, 0.1050),
        GameRect(-0.0773, -0.0195, -0.0033, 0.1050),
        GameRect(0.0195, 0.0773, -0.0033, 0.1050),
        GameRect(0.1153, 0.1731, -0.0033, 0.1050),
        GameRect(0.2111, 0.2689, -0.0033, 0.1050),
    ),
    (
        GameRect(-0.3156, -0.2578, -0.0041, 0.1043),
        GameRect(-0.2204, -0.1626, -0.0041, 0.1043),
        GameRect(-0.1257, -0.0691, -0.0041, 0.1043),
        GameRect(-0.0299, 0.0267, -0.0041, 0.1043),
        GameRect(0.0691, 0.1257, -0.0041, 0.1043),
        GameRect(0.1626, 0.2204, -0.0041, 0.1043),
        GameRect(0.2578, 0.3156, -0.0041, 0.1043),
    ),
)

RIVAL_BOARD = (
    (
        GameRect(-0.2689, -0.2111, -0.1730, -0.0716),
        GameRect(-0.1731, -0.1153, -0.1730, -0.0716),
        GameRect(-0.0773, -0.0195, -0.1730, -0.0716),
        GameRect(0.0195, 0.0773, -0.1730, -0.0716),
        GameRect(0.1153, 0.1731, -0.1730, -0.0716),
        GameRect(0.2111, 0.2689, -0.1730, -0.0716),
    ),
    (
        GameRect(-0.3156, -0.2578, -0.1730, -0.0716),
        GameRect(-0.2204, -0.1626, -0.1730, -0.0716),
        GameRect(-0.1257, -0.0691, -0.1730, -0.0716),
        GameRect(-0.0299, 0.0267, -0.1730, -0.0716),
        GameRect(0.0691, 0.1257, -0.1730, -0.0716),
        GameRect(0.1626, 0.2204, -0.1730, -0.0716),
        GameRect(0.2578, 0.3156, -0.1730, -0.0716),
    ),
)

# ---------------------------------------------------------------- 选卡组（对战界面）
DECK_POS = (
    GameRect(-0.4108, -0.2487, -0.2782, -0.2019),
    GameRect(-0.2368, -0.0833, -0.2782, -0.2019),
    GameRect(-0.0672, 0.0863, -0.2782, -0.2019),
    GameRect(-0.4034, -0.2498, -0.0699, 0.0065),
    GameRect(-0.2368, -0.0833, -0.0699, 0.0065),
    GameRect(-0.0672, 0.0863, -0.0699, 0.0065),
    GameRect(-0.4003, -0.2468, 0.1384, 0.2148),
    GameRect(-0.2337, -0.0802, 0.1384, 0.2148),
    GameRect(-0.0672, 0.0863, 0.1384, 0.2148),
)

# ---------------------------------------------------------------- 模式入口
TOURNAMENT_MODE = GameRect(-0.0790, 0.0811, -0.2090, -0.1737)  # 主界面 -> 对战
TOURNAMENT_START = GameRect(0.2586, 0.3459, 0.2706, 0.3794)  # 开始匹配
TOURNAMENT_ERROR = GameRect(-0.0397, 0.0325, 0.0856, 0.1249)
CHANGE_MODE = GameRect(0.2868, 0.3256, -0.4672, -0.4279)
WILD_MODE = GameRect(-0.3072, -0.1755, -0.1924, -0.0647)
STANDARD_MODE = GameRect(-0.0691, 0.0612, -0.2446, -0.1097)
CASUAL_MODE = GameRect(0.1622, 0.2886, -0.1817, -0.0540)
TOURNAMENT_MODE_SELECT = GameRect(-0.0790, 0.0811, -0.2090, -0.1737)
FIRST_DECK_LIMIT = GameRect(-0.4072, -0.2516, -0.0696, 0.0139)
PREV_DECK_PAGE = GameRect(-0.4755, -0.4473, -0.0302, 0.0095)
MODE_BACK = GameRect(0.4041, 0.4575, 0.4083, 0.4410)
MODE_CANCEL = GameRect(-0.0251, 0.0530, 0.3203, 0.3802)

# 主界面 -> 其他模式 -> 冒险（GameModeModeStrategy.kt）
OTHER_MODE = GameRect(-0.0845, 0.0779, 0.0058, 0.0424)
OTHER_ADVENTURE = GameRect(-0.0725, 0.0519, -0.2398, -0.0702)
OTHER_ADVENTURE_CHOOSE = GameRect(0.2229, 0.3398, 0.1287, 0.2661)
OTHER_BACK = GameRect(0.3975, 0.4558, 0.4058, 0.4376)

# 冒险（练习模式走这条）
ADV_CHOOSE = GameRect(0.2467, 0.3441, 0.2778, 0.3772)
ADV_PRACTICE = GameRect(0.1655, 0.4198, -0.4079, -0.3187)
ADV_START = GameRect(0.2564, 0.3452, 0.2690, 0.3728)
ADV_FIRST_HERO = GameRect(0.1765, 0.4151, -0.4037, -0.3615)


# ---------------------------------------------------------------- 查表函数
def hand_card(index: int, size: int) -> GameRect:
    """作者 getMyHandCardRect，原样查表（不再有"本地实测校正"）。"""
    if index < 0 or index > size - 1 or size > len(MY_HAND) or size < 1:
        return INVALID
    return MY_HAND[size - 1][index]


def _play_card(index: int, size: int, table) -> GameRect:
    """作者 getPlayCardRect：按场面数量居中偏移。"""
    s = max(size, 0)
    rects = table[s & 1]
    offset = (len(rects) - s) >> 1
    i = max(offset + index, 0)
    i = min(i, len(rects) - 1)
    return rects[i]


def my_minion(index: int, size: int) -> GameRect:
    return _play_card(index, size, MY_BOARD)


def rival_minion(index: int, size: int) -> GameRect:
    return _play_card(index, size, RIVAL_BOARD)


def deck_pos(pos: int) -> GameRect:
    """作者 lClickDeckPos，pos 从 1 开始。"""
    if pos < 1 or pos > len(DECK_POS):
        return INVALID
    return DECK_POS[pos - 1]


def discover(options: int) -> tuple[GameRect, ...]:
    return DISCOVER_4 if options >= 4 else DISCOVER_3


# ---------------------------------------------------------------- 覆盖层 UI（比例 0..1）
# 任务/日志/商店这类是 HUB 上的覆盖层，不改变 LoadingScreen.log 的状态，
# 只能靠 UI 元素位置退出。这里存比例，跨分辨率有效。
UI_RATIO = {
    "overlay_back": (0.198, 0.858),   # 日志/任务页左下角返回箭头
    "overlay_close": (0.500, 0.930),  # 「点击继续」/弹窗底部确认
}

