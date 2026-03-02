import math
from typing import Tuple

METERS_PER_UNIT_TO_NAME = {
    1.0: "m", 0.1: "dm", 0.01: "cm", 0.001: "mm", 0.0254: "inch", 0.3048: "ft",
}

def format_stage_unit(mpu: float) -> str:
    """根據 Stage 的 metersPerUnit 轉換為易讀的單位字串"""
    for val, name in METERS_PER_UNIT_TO_NAME.items():
        if math.isclose(mpu, val, rel_tol=1e-5):
            return name
        elif math.isclose(mpu, 100, rel_tol=1e-5):
             return "cm"
    return f"{mpu:.4f} m"

def get_precision(unit: str) -> int:
    """根據選擇的單位返回建議的小數點位數"""
    return {"mm": 1, "cm": 2, "m": 4, "inch": 2, "ft": 3}.get(unit, 3)

def calculate_gap(b1_min: Tuple[float, float, float], b1_max: Tuple[float, float, float], 
                  b2_min: Tuple[float, float, float], b2_max: Tuple[float, float, float]) -> Tuple[float, float, float, float]:
    """
    計算兩個 AABB (Axis-Aligned Bounding Box) 中心點之間在各軸上的距離 (Gap X, Y, Z)。
    回傳 (dx, dy, dz, distance)
    """
    c1 = [(b1_min[i] + b1_max[i]) / 2.0 for i in range(3)]
    c2 = [(b2_min[i] + b2_max[i]) / 2.0 for i in range(3)]
    
    dx = abs(c1[0] - c2[0])
    dy = abs(c1[1] - c2[1])
    dz = abs(c1[2] - c2[2])
    
    distance = math.sqrt(dx*dx + dy*dy + dz*dz)
    return dx, dy, dz, distance

def _ray_exit_aabb(origin: Tuple[float, float, float],
                   direction: Tuple[float, float, float],
                   b_min: Tuple[float, float, float],
                   b_max: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """
    從 AABB 內部的 origin 沿 direction 射出，
    找出射線離開 AABB 的交點（exit point）。
    direction 必須非零向量。
    """
    t_exit = float('inf')
    for i in range(3):
        if abs(direction[i]) > 1e-12:
            # 離開的那面 = direction 正→max面, direction 負→min面
            face = b_max[i] if direction[i] > 0 else b_min[i]
            t = (face - origin[i]) / direction[i]
            if 0 < t < t_exit:
                t_exit = t

    if t_exit == float('inf'):
        return tuple(origin)

    return (
        origin[0] + direction[0] * t_exit,
        origin[1] + direction[1] * t_exit,
        origin[2] + direction[2] * t_exit,
    )


def calculate_gap_points(b1_min: Tuple[float, float, float], b1_max: Tuple[float, float, float], 
                         b2_min: Tuple[float, float, float], b2_max: Tuple[float, float, float]) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """
    計算兩個 AABB 之間測距線段的起點與終點。
    使用 Ray-AABB 交點法：
      1. 求兩個 AABB 的中心點 c1, c2
      2. 從 c1 沿 c1→c2 方向射線，找出離開 AABB1 的交點 → p1
      3. 從 c2 沿 c2→c1 方向射線，找出離開 AABB2 的交點 → p2
    這樣端點會落在包圍盒表面上，對球體、圓錐等曲面物件更精確。
    """
    c1 = [(b1_min[i] + b1_max[i]) / 2.0 for i in range(3)]
    c2 = [(b2_min[i] + b2_max[i]) / 2.0 for i in range(3)]

    # 方向向量 c1 → c2
    d = [c2[i] - c1[i] for i in range(3)]
    length = math.sqrt(d[0]*d[0] + d[1]*d[1] + d[2]*d[2])

    if length < 1e-12:
        # 兩中心重疊，fallback 到中心點
        return tuple(c1), tuple(c2)

    # p1: 從 c1 往 c2 方向射出 AABB1
    p1 = _ray_exit_aabb(c1, d, b1_min, b1_max)
    # p2: 從 c2 往 c1 方向射出 AABB2（反向）
    d_rev = [-d[i] for i in range(3)]
    p2 = _ray_exit_aabb(c2, d_rev, b2_min, b2_max)

    return p1, p2
