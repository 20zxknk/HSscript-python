"""输入层：把游戏日志解析成 GameState，不碰盒子与鼠标。"""
from .powerlog import PowerLog
from .state import Entity, GameState, Player

__all__ = ["PowerLog", "GameState", "Player", "Entity"]
