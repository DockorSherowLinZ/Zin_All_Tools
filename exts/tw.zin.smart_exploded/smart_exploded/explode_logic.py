"""爆炸圖的純計算邏輯。

不依賴 omni 或 pxr，因此可在無 Omniverse 環境下完整單元測試。
座標以可索引序列表示，Gf.Vec3d、tuple 與 list 皆適用。

模型為「逐組件」而非「逐 mesh」：每個組件自帶方向與距離，
全域係數統一控制爆炸進度，因此單一滑桿即可播放組裝/拆解過程。
"""

import math

# 六個可選軸向，順序即為 UI 下拉選單的順序
DIRECTION_LABELS = ("X+", "X-", "Y+", "Y-", "Z+", "Z-")

_LABEL_TO_VECTOR = {
    "X+": (1.0, 0.0, 0.0),
    "X-": (-1.0, 0.0, 0.0),
    "Y+": (0.0, 1.0, 0.0),
    "Y-": (0.0, -1.0, 0.0),
    "Z+": (0.0, 0.0, 1.0),
    "Z-": (0.0, 0.0, -1.0),
}

# 判定組件是否被外部移動的容差，需大於浮點寫入誤差但小於任何有意義的位移
POSITION_EPSILON = 1e-4


# ─────────────────────────────────────────────
#  方向
# ─────────────────────────────────────────────

def direction_from_label(label):
    try:
        return _LABEL_TO_VECTOR[label]
    except KeyError:
        raise ValueError("unknown direction label: %r" % (label,))


def direction_from_index(index):
    return direction_from_label(label_from_index(index))


def label_from_index(index):
    if not 0 <= index < len(DIRECTION_LABELS):
        raise ValueError("direction index out of range: %r" % (index,))
    return DIRECTION_LABELS[index]


def index_from_label(label):
    try:
        return DIRECTION_LABELS.index(label)
    except ValueError:
        raise ValueError("unknown direction label: %r" % (label,))


# ─────────────────────────────────────────────
#  位移
# ─────────────────────────────────────────────

def part_offset(direction, distance, factor=1.0, multiplier=1.0):
    """單一組件的位移向量。

    factor 為全域爆炸進度 (0 = 組裝完成, 1 = 完全炸開)，
    multiplier 讓整體比例可依模型尺度調整。
    """
    scale = float(distance) * float(factor) * float(multiplier)
    return tuple(float(direction[i]) * scale for i in range(3))


def exploded_position(home, direction, distance, factor=1.0, multiplier=1.0):
    offset = part_offset(direction, distance, factor, multiplier)
    return tuple(float(home[i]) + offset[i] for i in range(3))


# ─────────────────────────────────────────────
#  外部移動偵測
# ─────────────────────────────────────────────

def has_drifted(current, home, offset, epsilon=POSITION_EPSILON):
    """判斷組件是否被本工具以外的方式移動過。

    預期位置為 home + offset；若實際位置偏離，
    代表使用者用 gizmo 或其他工具動過它，記錄的原點已失效。
    """
    return any(
        abs(float(current[i]) - (float(home[i]) + float(offset[i]))) > epsilon
        for i in range(3)
    )


def resolve_home(current, home, offset, epsilon=POSITION_EPSILON):
    """回傳套用位移前應使用的原點。

    未被外部移動時維持原本的原點；被移動過則以「目前位置扣掉既有位移」
    重新校準，使後續調整相對於組件現況套用，不會把手動移動蓋掉。
    """
    if current is None:
        return tuple(float(v) for v in home)
    if has_drifted(current, home, offset, epsilon):
        return tuple(float(current[i]) - float(offset[i]) for i in range(3))
    return tuple(float(v) for v in home)


# ─────────────────────────────────────────────
#  自動分配
# ─────────────────────────────────────────────

def bounds_center(centers):
    """由多個組件中心求共同中心。

    取各軸最小/最大值的中點而非平均值，
    避免零件數量分佈不均時中心被拉偏。
    """
    points = [tuple(float(p[i]) for i in range(3)) for p in centers]
    if not points:
        return (0.0, 0.0, 0.0)

    mins = list(points[0])
    maxs = list(points[0])
    for point in points[1:]:
        for i in range(3):
            mins[i] = min(mins[i], point[i])
            maxs[i] = max(maxs[i], point[i])

    return tuple((mins[i] + maxs[i]) / 2.0 for i in range(3))


def distance_from_center(part_center, center):
    return math.sqrt(
        sum((float(part_center[i]) - float(center[i])) ** 2 for i in range(3))
    )


def dominant_direction_label(part_center, center):
    """依組件相對共同中心的偏移，選出最接近的軸向。

    偏移完全為零時回傳 Z+，避免無方向可用。
    """
    delta = [float(part_center[i]) - float(center[i]) for i in range(3)]
    magnitudes = [abs(value) for value in delta]
    largest = max(magnitudes)

    if largest == 0.0:
        return "Z+"

    axis = magnitudes.index(largest)
    return "XYZ"[axis] + ("+" if delta[axis] >= 0.0 else "-")


def suggest_distance(part_center, center, base_distance, accel=1.0, max_distance=None):
    """依組件距中心的遠近，建議初始爆炸距離。

    accel = 0 時所有組件距離相同；accel = 1 時正比於距中心遠近，
    也就是整體等比向外放大，最接近傳統爆炸圖。
    """
    if max_distance is None:
        max_distance = distance_from_center(part_center, center)

    if max_distance <= 0.0:
        ratio = 1.0
    else:
        ratio = distance_from_center(part_center, center) / max_distance

    accel = min(max(float(accel), 0.0), 1.0)
    return float(base_distance) * ((1.0 - accel) + accel * ratio)
