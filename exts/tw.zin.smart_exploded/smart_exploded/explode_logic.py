"""Smart Exploded View 的爆炸計算邏輯。

與 omni / pxr 解耦，讓方向、距離與自動分配的計算可在無 Omniverse 環境下驗證。
座標以可索引序列表示，因此 Gf.Vec3d、tuple 與 list 都適用。

爆炸模型為「逐組件」而非「逐 mesh」：
每個組件有自己的方向與距離，全域係數統一控制爆炸進度，
因此可用同一個滑桿播放組裝/拆解過程。
"""

import math

# 使用者可選的六個軸向，順序即為 UI 下拉選單的順序
DIRECTION_LABELS = ("X+", "X-", "Y+", "Y-", "Z+", "Z-")

_LABEL_TO_VECTOR = {
    "X+": (1.0, 0.0, 0.0),
    "X-": (-1.0, 0.0, 0.0),
    "Y+": (0.0, 1.0, 0.0),
    "Y-": (0.0, -1.0, 0.0),
    "Z+": (0.0, 0.0, 1.0),
    "Z-": (0.0, 0.0, -1.0),
}


def direction_from_label(label):
    """由 'X+' 這類標籤取得單位方向向量。"""
    try:
        return _LABEL_TO_VECTOR[label]
    except KeyError:
        raise ValueError("unknown direction label: %r" % (label,))


def direction_from_index(index):
    """由 UI 下拉選單索引取得單位方向向量。"""
    if not 0 <= index < len(DIRECTION_LABELS):
        raise ValueError("direction index out of range: %r" % (index,))
    return _LABEL_TO_VECTOR[DIRECTION_LABELS[index]]


def label_from_index(index):
    if not 0 <= index < len(DIRECTION_LABELS):
        raise ValueError("direction index out of range: %r" % (index,))
    return DIRECTION_LABELS[index]


def index_from_label(label):
    try:
        return DIRECTION_LABELS.index(label)
    except ValueError:
        raise ValueError("unknown direction label: %r" % (label,))


def part_offset(direction, distance, factor=1.0, multiplier=1.0):
    """計算單一組件的位移向量。

    factor 為全域爆炸進度 (0 = 組裝完成, 1 = 完全炸開)，
    multiplier 讓整體比例可依模型尺度調整。
    """
    scale = float(distance) * float(factor) * float(multiplier)
    return tuple(float(direction[i]) * scale for i in range(3))


def exploded_position(home, direction, distance, factor=1.0, multiplier=1.0):
    """由原點與方向算出爆炸後的位置。"""
    offset = part_offset(direction, distance, factor, multiplier)
    return tuple(float(home[i]) + offset[i] for i in range(3))


def bounds_center(centers):
    """由多個組件中心求共同中心。

    使用各軸的最小/最大值中點，而非平均值，
    避免零件數量分佈不均時中心被拉偏。
    """
    points = list(centers)
    if not points:
        return (0.0, 0.0, 0.0)

    mins = [float(points[0][i]) for i in range(3)]
    maxs = list(mins)
    for point in points[1:]:
        for i in range(3):
            value = float(point[i])
            if value < mins[i]:
                mins[i] = value
            if value > maxs[i]:
                maxs[i] = value

    return tuple((mins[i] + maxs[i]) / 2.0 for i in range(3))


def dominant_direction_label(part_center, center):
    """依組件相對共同中心的偏移，選出最接近的軸向。

    用於自動產生初始方向，使用者再逐項微調。
    偏移量完全為零時回傳 Z+，避免無方向可用。
    """
    delta = [float(part_center[i]) - float(center[i]) for i in range(3)]
    magnitudes = [abs(value) for value in delta]
    largest = max(magnitudes)

    if largest == 0.0:
        return "Z+"

    axis = magnitudes.index(largest)
    sign = "+" if delta[axis] >= 0.0 else "-"
    return "XYZ"[axis] + sign


def distance_from_center(part_center, center):
    """組件中心到共同中心的直線距離。"""
    return math.sqrt(
        sum((float(part_center[i]) - float(center[i])) ** 2 for i in range(3))
    )


def suggest_distance(part_center, center, base_distance, accel=1.0, max_distance=None):
    """依組件距中心的遠近，建議一個初始爆炸距離。

    accel = 0 時所有組件距離相同；accel = 1 時正比於距中心的遠近，
    也就是整體等比向外放大，最接近傳統爆炸圖。
    """
    if max_distance is None:
        max_distance = distance_from_center(part_center, center)

    if max_distance <= 0.0:
        ratio = 1.0
    else:
        ratio = distance_from_center(part_center, center) / max_distance

    accel = min(max(float(accel), 0.0), 1.0)
    weight = (1.0 - accel) + accel * ratio
    return float(base_distance) * weight
