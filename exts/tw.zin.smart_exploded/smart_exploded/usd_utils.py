"""爆炸圖的 USD 存取封裝。

集中處理實測中確認的兩個陷阱：
  - instance proxy 是唯讀投影，USD 禁止在其上寫入屬性
  - xformOp:translate:pivot 也是 TypeTranslate，但它描述旋轉/縮放中心，
    改動它會破壞模型
"""

import carb
from pxr import Usd, UsdGeom


def find_translate_op(xformable):
    """取得組件的 xformOp:translate，找不到時回傳 None。"""
    for op in xformable.GetOrderedXformOps():
        if op.GetOpType() != UsdGeom.XformOp.TypeTranslate:
            continue
        if ":pivot" in op.GetOpName():
            continue
        return op
    return None


def is_authorable(prim):
    """instance proxy 無法寫入屬性。"""
    return not prim.IsInstanceProxy()


def get_xformable(stage, path):
    """取得可變形的組件，不可用時回傳 None。"""
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        return None
    xformable = UsdGeom.Xformable(prim)
    if not xformable:
        return None
    return xformable


def resolve_translate_op(stage, path, create=False):
    """取得組件的 translate op。

    create=True 時，若組件尚無 translate op 便建立一個。
    無法寫入或建立失敗回傳 None。
    """
    xformable = get_xformable(stage, path)
    if xformable is None:
        return None

    prim = xformable.GetPrim()
    if not is_authorable(prim):
        return None

    op = find_translate_op(xformable)
    if op is not None or not create:
        return op

    try:
        return xformable.AddTranslateOp()
    except Exception as exc:
        carb.log_warn(f"[Smart Explode] Could not create a translate op on '{path}': {exc}")
        return None


def is_movable(prim):
    """可獨立寫入位移的 prim。"""
    if not prim or not prim.IsValid():
        return False
    if not UsdGeom.Xformable(prim):
        return False
    return is_authorable(prim)


def find_component_paths(stage, root_path, max_depth=10):
    """從群組往下找出可各自拆解的組件層。

    匯出的模型常在根節點下堆疊數層單一子節點的包裝（如 ASSET/asset_xxx），
    一路往下走到第一個真正分岔的層級，那才是組件。
    根節點本身不算組件——整包一起平移不構成爆炸圖。
    找不到分岔則回傳空清單。
    """
    prim = stage.GetPrimAtPath(root_path)
    if not prim or not prim.IsValid():
        return []

    for _ in range(max_depth):
        children = [child for child in prim.GetChildren() if is_movable(child)]
        if not children:
            return []
        if len(children) > 1:
            return [str(child.GetPath()) for child in children]
        prim = children[0]

    return []


def read_translation(stage, path):
    """讀取組件目前的 translate 值，無法讀取時回傳 None。"""
    op = resolve_translate_op(stage, path)
    if op is None:
        return None
    return op.Get()


def write_translation(stage, path, value):
    """寫入組件的 translate 值，成功時回傳 True。"""
    op = resolve_translate_op(stage, path, create=True)
    if op is None:
        return False
    op.Set(value)
    return True


def make_bbox_cache():
    return UsdGeom.BBoxCache(
        Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render]
    )


def world_center(bbox_cache, stage, path):
    """組件包圍盒的世界座標中心。

    payload 未載入時包圍盒為空，此時回傳 None。
    """
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        return None

    try:
        bound = bbox_cache.ComputeWorldBound(prim).ComputeAlignedBox()
    except Exception as exc:
        carb.log_warn(f"[Smart Explode] Could not compute bounds for '{path}': {exc}")
        return None

    if bound.IsEmpty():
        return None

    midpoint = bound.GetMidpoint()
    return (midpoint[0], midpoint[1], midpoint[2])
