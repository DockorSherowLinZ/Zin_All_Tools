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

def _get_corners(b_min: Tuple[float, float, float], b_max: Tuple[float, float, float]):
    return [
        (b_min[0], b_min[1], b_min[2]),
        (b_min[0], b_min[1], b_max[2]),
        (b_min[0], b_max[1], b_min[2]),
        (b_min[0], b_max[1], b_max[2]),
        (b_max[0], b_min[1], b_min[2]),
        (b_max[0], b_min[1], b_max[2]),
        (b_max[0], b_max[1], b_min[2]),
        (b_max[0], b_max[1], b_max[2]),
    ]

def calculate_gap_points(b1_min: Tuple[float, float, float], b1_max: Tuple[float, float, float], 
                         b2_min: Tuple[float, float, float], b2_max: Tuple[float, float, float]) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """
    計算兩個 AABB 之間最短距離的連線起點與終點。
    改為掃描 AABB 的 8 個頂點，找出兩者之間距離最短的一對 Corners，
    這能讓 3D Viewport 中的測距線段看起來像是精確地從物件的某個角落連到另一個角落。
    """
    c1s = _get_corners(b1_min, b1_max)
    c2s = _get_corners(b2_min, b2_max)
    
    min_sq_dist = float('inf')
    best_p1 = c1s[0]
    best_p2 = c2s[0]
    
    for p1 in c1s:
        for p2 in c2s:
            dx = p1[0] - p2[0]
            dy = p1[1] - p2[1]
            dz = p1[2] - p2[2]
            sq_dist = dx*dx + dy*dy + dz*dz
            if sq_dist < min_sq_dist:
                min_sq_dist = sq_dist
                best_p1 = p1
                best_p2 = p2
                
    return best_p1, best_p2
