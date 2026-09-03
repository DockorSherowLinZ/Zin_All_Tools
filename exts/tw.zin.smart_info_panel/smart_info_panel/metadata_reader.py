# =============================================================================
# metadata_reader.py
# Smart Info Panel — AIF Metadata Reader
#
# 讀取 USD Prim 的 AIF 屬性並計算 BBox 尺寸。
# =============================================================================

import math

import carb
from pxr import Usd, UsdGeom, Gf


# ─────────────────────────────────────────────
#  GB300 硬編碼測試資料（場景中機台無 AIF metadata 時使用）
# ─────────────────────────────────────────────
_GB300_FALLBACK = {
    "core": {
        "assetClass":       ("Compute Rack", "Class of AI Factory Equipment"),
        "manufacturer":     ("NVIDIA, CORPORATION", "Equipment manufacturer name"),
        "modelNumber":      ("Grace Blackwell 300 NVL72", "Equipment model number"),
        "assetDescription": ("NVIDIA GB300 NVL72 SuperCluster - 72 Blackwell B300 GPUs, "
                             "144 Grace CPUs, liquid-cooled AI compute rack",
                             "Human Readable Description of Asset"),
        "width":            (600.0, "Equipment width in mm"),
        "depth":            (1200.0, "Equipment depth in mm"),
        "height":           (2300.0, "Equipment height in mm"),
        "weight":           (1500.0, "Equipment weight in kilograms"),
        "assetVersion":     ("0.1.0", "Design Revision of Digital Twin Asset"),
        "assetCreationDate":("2026-03-03", "Creation Date"),
    },
    "spec": {
        "numGPUs":              (72, "Number of discrete GPUs in rack"),
        "maxPowerDcTdp":        (136.0, "Max. Power DC Thermal Design Power (kW)"),
        "maxPowerAcEdpp1":      (142.0, "Max. Power AC EDDP2 (kW)"),
        "maxPowerDcEdpp2":      (240.0, "Max. Power DC EDDP2 (kW)"),
        "liquidCooling":        (116.0, "Liquid Cooling (kW)"),
        "airCooling":           (19.3, "Air Cooling (kW)"),
        "heatCaptureRatio":     (87.0, "Heat captured by liquid cooling (%)"),
        "namePlatePower":       (136000, "UPS Rating in W"),
        "idlePowerDefault30Pct":(40.8, "Idle power at default 30% utilization (kW)"),
    },
}


def read_aif_metadata(prim):
    """
    讀取 prim 的 AIF 屬性 (aif:core:* / aif:spec:*)。

    Returns:
        dict: {"core": {attr_short_name: (value, doc), ...},
               "spec": {attr_short_name: (value, doc), ...}}
        如果 prim 沒有 AIF 屬性，回傳 None。
    """
    if not prim or not prim.IsValid():
        return None

    result = {"core": {}, "spec": {}}
    found = False

    for attr in prim.GetAttributes():
        name = attr.GetName()
        if name.startswith("aif:core:"):
            short = name.replace("aif:core:", "")
            val = attr.Get()
            doc = attr.GetDocumentation() or ""
            result["core"][short] = (val, doc)
            found = True
        elif name.startswith("aif:spec:"):
            short = name.replace("aif:spec:", "")
            val = attr.Get()
            doc = attr.GetDocumentation() or ""
            result["spec"][short] = (val, doc)
            found = True

    return result if found else None


def find_aif_prim(prim):
    """
    從 prim 開始向上遍歷 parent，找到第一個帶有 aif:core: 屬性的 prim。
    如果找不到，回傳 None。
    """
    current = prim
    while current and current.IsValid() and current.GetPath().pathString != "/":
        for attr in current.GetAttributes():
            if attr.GetName().startswith("aif:core:"):
                return current
        current = current.GetParent()
    return None


def get_fallback_metadata():
    """回傳 GB300 的硬編碼測試 metadata。"""
    return _GB300_FALLBACK.copy()


def compute_bbox_dimensions(prim, bbox_cache, stage_mpu=1.0):
    """
    使用 UsdGeom.BBoxCache 計算 prim 的 Bounding Box 尺寸。

    Args:
        prim: USD Prim
        bbox_cache: UsdGeom.BBoxCache 實例
        stage_mpu: Stage 的 metersPerUnit

    Returns:
        dict: {"x_cm": float, "y_cm": float, "z_cm": float,
               "center": (x, y, z), "top_center": (x, y, z)}
        如果無法計算，回傳 None。
    """
    if not prim or not prim.IsValid():
        return None

    try:
        bbox = bbox_cache.ComputeWorldBound(prim)
        world = bbox.ComputeAlignedBox()
        if world.IsEmpty():
            return None

        sz = world.GetSize()
        # 轉換為公分 (cm)
        to_cm = stage_mpu * 100.0  # meters → cm
        x_cm = sz[0] * to_cm
        y_cm = sz[1] * to_cm
        z_cm = sz[2] * to_cm

        # 計算中心與頂部中心
        min_pt = world.GetMin()
        max_pt = world.GetMax()
        center = (
            (min_pt[0] + max_pt[0]) / 2.0,
            (min_pt[1] + max_pt[1]) / 2.0,
            (min_pt[2] + max_pt[2]) / 2.0,
        )
        top_center = (
            (min_pt[0] + max_pt[0]) / 2.0,
            (min_pt[1] + max_pt[1]) / 2.0,
            max_pt[2],  # Z-up: 頂部
        )

        return {
            "x_cm": x_cm,
            "y_cm": y_cm,
            "z_cm": z_cm,
            "center": center,
            "top_center": top_center,
            "bbox_min": (min_pt[0], min_pt[1], min_pt[2]),
            "bbox_max": (max_pt[0], max_pt[1], max_pt[2]),
        }
    except Exception as e:
        carb.log_warn(f"[SmartInfoPanel] BBox compute error: {e}")
        return None


def format_value(val):
    """將 USD 屬性值格式化為易讀的字串。"""
    if isinstance(val, float):
        # 判斷是否為整數值
        if val == int(val) and abs(val) < 1e9:
            return str(int(val))
        return f"{val:.2f}"
    elif isinstance(val, int):
        return str(val)
    elif isinstance(val, str):
        return val
    elif hasattr(val, '__len__') and len(val) == 3:
        # Gf.Vec3f / float3 / tuple
        return f"({val[0]:.1f}, {val[1]:.1f}, {val[2]:.1f})"
    else:
        return str(val)
