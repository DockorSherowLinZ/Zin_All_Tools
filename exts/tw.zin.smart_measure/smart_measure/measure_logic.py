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

def calculate_gap_points(b1_min: Tuple[float, float, float], b1_max: Tuple[float, float, float], 
                         b2_min: Tuple[float, float, float], b2_max: Tuple[float, float, float]) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """
    計算兩個 AABB 之間最短距離的連線起點與終點。
    回傳 (p1, p2)，其中 p1 是在 b1 上的最近點，p2 是在 b2 上的最近點。
    如果兩個 BBox 在某個軸上重疊，該軸上的最近點會取重疊區域的中心點。
    """
    p1 = [0.0, 0.0, 0.0]
    p2 = [0.0, 0.0, 0.0]
    
    for i in range(3):
        if b1_max[i] < b2_min[i]:
            p1[i] = b1_max[i]
            p2[i] = b2_min[i]
        elif b1_min[i] > b2_max[i]:
            p1[i] = b1_min[i]
            p2[i] = b2_max[i]
        else:
            # 重疊時取交集的中心點
            center = (max(b1_min[i], b2_min[i]) + min(b1_max[i], b2_max[i])) / 2.0
            p1[i] = center
            p2[i] = center
            
    return (p1[0], p1[1], p1[2]), (p2[0], p2[1], p2[2])
