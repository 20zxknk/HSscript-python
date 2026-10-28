"""决策层：把盒子的推荐翻译成 Plan，不自研战术。"""
from .box import BoxBridge, BridgeError, Plan

__all__ = ["BoxBridge", "BridgeError", "Plan"]
