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
    計算兩個 AABB (Axis-Aligned Bounding Box) 之間的最小距離 (Gap)。
    回傳 (dx, dy, dz, distance)
    如果兩個 BBox 在某個軸上重疊，該軸的 distance 為 0.
    """
    gap_func = lambda a1, a2, b1, b2: b1 - a2 if a2 < b1 else (a1 - b2 if b2 < a1 else 0.0)
    
    dx = gap_func(b1_min[0], b1_max[0], b2_min[0], b2_max[0])
    dy = gap_func(b1_min[1], b1_max[1], b2_min[1], b2_max[1])
    dz = gap_func(b1_min[2], b1_max[2], b2_min[2], b2_max[2])
    
    distance = math.sqrt(dx*dx + dy*dy + dz*dz)
    return dx, dy, dz, distance
