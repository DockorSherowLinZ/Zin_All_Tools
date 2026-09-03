"""Smart Exploded View 的純位移計算邏輯。

與 omni / pxr 解耦，讓「附加式位移」與「外部移動後重新校準」
的行為可在無 Omniverse 環境下驗證。
座標以可索引序列表示，因此 Gf.Vec3d、tuple 與 list 都適用。
"""

# 判定物件是否被外部移動的容差，需大於浮點寫入誤差但小於任何有意義的位移
POSITION_EPSILON = 1e-4


def has_drifted(current, home, offset, epsilon=POSITION_EPSILON):
    """判斷物件是否被本模組以外的方式移動過。

    預期位置為 home + offset；若實際位置偏離，代表使用者用 gizmo
    或其他工具動過它，記錄的原點已失效。
    """
    return any(
        abs(float(current[i]) - (float(home[i]) + float(offset[i]))) > epsilon
        for i in range(3)
    )


def rebase_home(current, offset):
    """以目前位置扣掉既有位移，重新算出原點。"""
    return tuple(float(current[i]) - float(offset[i]) for i in range(3))


def resolve_home(current, home, offset, epsilon=POSITION_EPSILON):
    """回傳套用位移前應使用的原點。

    未被外部移動時維持原本的原點；被移動過則重新校準，
    使得後續的滑桿改變量相對於物件現況套用。
    """
    if current is None:
        return tuple(float(v) for v in home)
    if has_drifted(current, home, offset, epsilon):
        return rebase_home(current, offset)
    return tuple(float(v) for v in home)


def apply_displacement(current, home, offset, axis, value, epsilon=POSITION_EPSILON):
    """計算套用單軸位移後的新位置。

    回傳 (new_position, new_home, new_offset)。
    """
    resolved_home = resolve_home(current, home, offset, epsilon)

    new_offset = [float(v) for v in offset]
    new_offset[axis] = float(value)

    new_position = tuple(resolved_home[i] + new_offset[i] for i in range(3))
    return new_position, resolved_home, new_offset
