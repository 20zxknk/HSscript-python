"""事件类型常量 —— 单独一个模块，避免 events/powerlog 循环 import。"""

# 对局段
EV_GAME_CREATE = "game/create"
EV_GAME_COMPLETE = "game/complete"
EV_MULLIGAN = "game/mulligan"

# 实体
EV_PLAYER = "player/entity"
EV_PLAYER_NAME = "player/name"
EV_ENTITY_FULL = "entity/full"
EV_ENTITY_SHOW = "entity/show"

# 方块边界（PowerTaskList 与 GameState 都有）：
#   BLOCK_START 的 Entity= 是裸 `tag=` 的归属者；BLOCK_END / HIDE_ENTITY 让它作废。
EV_BLOCK_START = "block/start"
EV_BLOCK_END = "block/end"

# tag
EV_TAG = "tag"
EV_TAG_BLOCK = "tag/block"          # FULL_ENTITY 块里的 tag
EV_GLOBAL_TAG = "tag/global"        # TURN / STATE / CURRENT_PLAYER（含 PowerTaskList 版）

# 游戏列出的"当前可执行选项"（DebugPrintOptions）——盒子读的就是它
EV_OPTIONS_HEADER = "options/header"
EV_OPTION = "options/option"

# 选择面板（DebugPrintEntityChoices）：发现/抉择/四选一，候选按 Entities[i] 顺序
EV_CHOICE_HEADER = "choice/header"
EV_CHOICE_ENTITY = "choice/entity"
EV_CHOICE_DONE = "choice/done"

# 流
EV_STREAM_RESET = "stream/reset"
EV_STREAM_INTERRUPTED = "stream/interrupted"
