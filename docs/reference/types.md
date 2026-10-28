# 数据结构

这三个结构是层与层之间唯一的接口（见 [0001](../adr/0001-architecture-three-layers.md)）：
日志解析出 `GameState`，盒子的推荐翻译成 `Plan`，鼠标只认 `GameRect` 算出来的坐标。

下面每一段都**与源码逐字一致**，由
[`scripts/verify_type_equiv.py`](../../scripts/verify_type_equiv.py) 校验：改了源码不改文档，
`pre-commit` 直接失败。

## `Entity` —— 日志里的一个实体

游戏日志里的每张牌、每个随从、每个英雄都是一个实体，用 `entity_id` 区分。
`zone` 和 `zone_pos` 决定它在不在手牌/场上，`card_id` 可能为空（对手的手牌读不到）。

<!-- type-equiv: Entity -->
```python type-equiv
class Entity:
    eid: int
    card_id: str = ""
    name: str = ""
    card_type: str = ""  # MINION / HERO / SPELL / WEAPON / ...
    controller: int = 0
    zone: str = ""  # HAND / PLAY / DECK / SECRET / GRAVEYARD
    zone_pos: int = 0
    cost: int = 0
    atk: int = 0
    health: int = 0
    damage: int = 0
    armor: int = 0
    taunt: bool = False
    divine_shield: bool = False
    frozen: bool = False
    stealth: bool = False
    exhausted: bool = False  # 本回合刚上场
    num_attacks: int = 0
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def is_minion(self) -> bool:
        """场面随从（可被攻击的目标）。

        判据以卡池为准（`type == "MINION"`）：地标、法术、附魔都不算随从。
        `card_type` 只当后备 —— 真机实证很多衍生/召唤物（如 BE_085t、CATA_725t）
        在日志里 `cardType` 是空的，但已经是随从；反过来附魔带攻血却**不是**随从。
        """
        if self.zone != "PLAY":
            return False
        k = card_db.kind(self.card_id)
        if k is not None:
            return k == "MINION"
        if self.card_type in ("HERO", "HERO_POWER", "WEAPON", "ENCHANTMENT", "INVALID",
                              "GAME", "SPELL", "LOCATION"):
            return False
        if self.card_type == "MINION":
            return True
        return not self.card_type and (self.atk > 0 or self.health > 0)

    @property
    def is_hero(self) -> bool:
        return self.card_type == "HERO"

    @property
    def hp(self) -> int:
        return max(0, self.health - self.damage)
```

## `GameState` —— 一整局的可观测状态

`pump()` 每读进一行日志就 fold 一次；`rebuild()` 从头重放整份日志得到确定性的状态。
所有字段都是从日志推出来的，没有一处是猜的——读不到就是空。

<!-- type-equiv: GameState -->
```python type-equiv
class GameState:
    started: bool = False
    finished: bool = False
    turn: int = 0
    turn_global: int = 0
    my_id: int = 0
    current_player: int = 0
    players: dict[int, Player] = field(default_factory=dict)
    entities: dict[int, Entity] = field(default_factory=dict)
    discover_open: bool = False
    discover_options: int = 0
    choice_open: bool = False
    choices: list = field(default_factory=list)
    choice_player: str = ""
    choice_type: str = ""
    choice_min: int = 0
    choice_max: int = 0
    mulligan_open: bool = False
    hand_options: dict[int, dict[int, str]] = field(default_factory=dict)
    hand_option_eids: dict[int, dict[int, int]] = field(default_factory=dict)
    hand_options_seq: int = 0
    hand_mutation_seq: int = 0
    option_errors: dict[int, str] = field(default_factory=dict)
    end_turn_option_seq: int = 0
    turn_seq: int = 0
    hand_entities_seq: int = 0
    # ……方法略（见源码）
```

## `GameState` 的字段被谁读

字段有了，还得知道谁在用——层与层只通过它有交流，读错了字段就会在真机上表现为“点了没反应”。

| 字段 | 读它的地方 | 用途 |
|---|---|---|
| `turn` / `current_player` / `my_id` | `engine.py`、`run.py` | 判断是不是我的回合、盒子的 turnNum 是否过期 |
| `my_hand` / `entities` | `engine.py`、`verify.py` | 出牌槽位解析、`resolve_play_slot` 的卡号核对 |
| `hand_option_eids` / `option_errors` | `engine.py` | 槽位 → eid → 可用性（`REQ_ENOUGH_MANA` 这类拒绝理由） |
| `my_board` / `rival_board` | `engine.py` | 攻击者槽位、目标选择 |
| `choice_open` / `choices` | `engine.py` | 发现/抉择面板：要不要进 `_do_choice`、点第几个 |
| `started` / `finished` | `navigator.py`、`run.py`、`sync.py` | 进对局判据、对局结束判据 |

这张表是人工维护的（`scripts/verify_type_equiv.py` 只管代码块逐字一致，管不了语义），
改字段消费方时记得一起改。

## `Plan` —— 盒子的推荐翻译成的动作

`action` 只有 play / attack / end / hero_power / choice / unknown 这几种；
`hand_position` 是盒子给的手牌槽位（1 基），`board_position` 是上场的槽位。
它不含任何战术判断——盒子说什么就是什么。

<!-- type-equiv: Plan -->
```python type-equiv
class Plan:
    action: str = ""
    plan: str = "A"
    raw_action: str = ""
    hand_position: int | None = None
    board_position: int | None = None
    # 默认必须是"没有目标"：以前默认 "board"，而 _target() 把 "board" 当**敌方场面**，
    # 于是任何没写 target 的方案（盒子少给一个字段、或单测里直接构造）都会变成
    # "指向敌方场面"。盒子正常会显式给 null，这里只是把地雷拆掉。
    target: str = ""
    target_position: int | None = None
    target_card_id: str = ""
    card_name: str = ""
    card_id: str = ""
    option_id: int | None = None
    ai_win_rate: float | None = None
    mulligan_positions: list[int] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, d: dict) -> "Plan":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        known.pop("extra", None)
        return cls(**known, extra={k: v for k, v in d.items() if k not in known})
```

## `GameRect` —— 归一化矩形到真实像素

作者的表全是相对值，用 `relative(w, h)` 换算成客户区像素。横轴按 `real_h * CONTENT_RATIO`
缩放而不是按真实宽度：游戏是按高度等比渲染、两侧留边，用真实宽度算会整体偏宽。

<!-- type-equiv: GameRect -->
```python type-equiv
class GameRect:
    """作者 GameRect 的等价物。"""

    left: float
    right: float
    top: float
    bottom: float

    def relative(self, real_w: int, real_h: int) -> tuple[int, int, int, int]:
        """-> (x, y, w, h)，x/y 相对窗口内容区左上角。作者原式，别改。

        横轴按 `realH * CONTENT_RATIO` 缩放，不是按客户区真实宽度：游戏按高度
        等比渲染、两侧留边。按真实宽度算会把整排拉宽（1905×982 时 6 张手牌的
        牌心从 700…1115 变成按宽度算的更大跨度）。

        具体的像素值随窗口尺寸变，别在文档里写死：算式是
            usable_w = real_h * CONTENT_RATIO
            x = real_w//2 + left * usable_w
        需要核对时直接跑一句 `python -X utf8 -c "..."` 算，别抄注释。
        """
        usable_h = real_h
        usable_w = int(real_h * CONTENT_RATIO)
        middle_x = real_w >> 1
        middle_y = real_h >> 1
        x = middle_x + self.left * usable_w
        y = middle_y + self.top * usable_h
        w = (self.right - self.left) * usable_w
        h = (self.bottom - self.top) * usable_h
        return int(x), int(y), int(w), int(h)

    def click_point(self, real_w: int, real_h: int, rng: random.Random | None = None) -> tuple[int, int]:
        """作者 getClickPos()：矩形内随机取一点，避免每次都点同一个像素。"""
        r = rng or random
        x, y, w, h = self.relative(real_w, real_h)
        x1, x2 = sorted((x, x + w))
        y1, y2 = sorted((y, y + h))
        # 内缩 1px，避免落在矩形边界上
        x1, x2 = x1 + 1, max(x1 + 1, x2 - 1)
        y1, y2 = y1 + 1, max(y1 + 1, y2 - 1)
        return r.randint(x1, x2), r.randint(y1, y2)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.left + self.right) / 2, (self.top + self.bottom) / 2)
```
