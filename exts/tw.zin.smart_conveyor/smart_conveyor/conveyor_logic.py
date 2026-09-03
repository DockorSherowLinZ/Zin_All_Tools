"""Smart Conveyor 的純計算邏輯。

與 omni / pxr 解耦，讓產線容量與設定正規化可在無 Omniverse 環境下測試。
座標以可索引序列表示，因此 Gf.Vec3d、tuple 與 list 都適用。
"""

import math

DEFAULT_SPEED = 50.0
DEFAULT_INITIAL_DELAY = 1.0
DEFAULT_DISPATCH_INTERVAL = 3.0

# 物件池的安全緩衝，避免產線尖峰時無可用實例
POOL_SAFETY_BUFFER = 2


def distance(point_a, point_b):
    """回傳兩個三維座標之間的歐氏距離。"""
    return math.sqrt(
        sum((float(point_a[i]) - float(point_b[i])) ** 2 for i in range(3))
    )


def calc_required_pool_size(waypoints, speed, dispatch_interval):
    """依路徑總長、暫停時間與派送間隔推算所需的物件池大小。

    參數無效時回傳 2，與原本的保守預設一致。
    """
    if not waypoints or speed <= 0 or dispatch_interval <= 0:
        return 2

    total_distance = 0.0
    total_pause = 0.0
    for index in range(1, len(waypoints)):
        previous = waypoints[index - 1]
        current = waypoints[index]
        total_distance += distance(current["pos"], previous["pos"])
        total_pause += float(current.get("pause", 0.0))

    total_time = (total_distance / speed) + total_pause
    required = int(math.ceil(total_time / dispatch_interval)) + POOL_SAFETY_BUFFER
    return max(1, required)


def normalize_config(config):
    """將巢狀設定格式攤平為統一的頂層鍵。

    支援兩種來源格式：
      - 攤平式：鍵直接位於頂層
      - 巢狀式：分組於 global_settings / behavior / target_pcb_paths

    不處理 waypoints 的座標轉換，該步驟需要 pxr 型別，留在 extension 層。
    """
    result = dict(config)

    global_settings = result.get("global_settings")
    if isinstance(global_settings, dict):
        result.setdefault("speed", global_settings.get("speed", DEFAULT_SPEED))
        result.setdefault(
            "initial_delay", global_settings.get("initial_delay", DEFAULT_INITIAL_DELAY)
        )
        result.setdefault(
            "dispatch_interval",
            global_settings.get("dispatch_interval", DEFAULT_DISPATCH_INTERVAL),
        )

    behavior = result.get("behavior")
    if isinstance(behavior, dict):
        result.setdefault("reverse", behavior.get("reverse", False))
        result.setdefault("loop", behavior.get("loop", False))
        result.setdefault("end_visibility", behavior.get("end_visibility", False))

    if "target_pcb_paths" in result and "prim_paths" not in result:
        result["prim_paths"] = ", ".join(result["target_pcb_paths"])

    return result
