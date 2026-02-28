import pytest
import math
from typing import Tuple

import sys
import os

# 把包含 measure_logic.py 的資料夾直接加到 sys.path
# 路徑: d:\Zin_All_Tools\exts\tw.zin.smart_measure\smart_measure
EXT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'exts', 'tw.zin.smart_measure', 'smart_measure'))
if EXT_DIR not in sys.path:
    sys.path.insert(0, EXT_DIR)

from measure_logic import format_stage_unit, get_precision, calculate_gap, calculate_gap_points


# ─── format_stage_unit 測試 ──────────────────────────────

def test_format_stage_unit_standard_values():
    assert format_stage_unit(1.0) == "m"
    assert format_stage_unit(0.1) == "dm"
    assert format_stage_unit(0.01) == "cm"
    assert format_stage_unit(0.001) == "mm"
    assert format_stage_unit(0.0254) == "inch"
    assert format_stage_unit(0.3048) == "ft"

def test_format_stage_unit_cm_special_case():
    assert format_stage_unit(100.0) == "cm"

def test_format_stage_unit_custom_scale():
    # 測試非標準單位的 fallback，四捨五入到小數點後 4 位並加上 'm'
    assert format_stage_unit(0.5) == "0.5000 m"
    assert format_stage_unit(1.23456) == "1.2346 m"

# ─── get_precision 測試 ─────────────────────────────────

def test_get_precision():
    assert get_precision("mm") == 1
    assert get_precision("cm") == 2
    assert get_precision("m") == 4
    assert get_precision("inch") == 2
    assert get_precision("ft") == 3
    
    # 測試不在列表中的單位 (預設值 3)
    assert get_precision("dm") == 3
    assert get_precision("unknown") == 3

# ─── calculate_gap 測試 ─────────────────────────────────

def test_calculate_gap_separated_boxes():
    """測試兩個完全分開的物件"""
    b1_min = (0.0, 0.0, 0.0)
    b1_max = (1.0, 1.0, 1.0)
    
    b2_min = (2.0, 0.0, 0.0)
    b2_max = (3.0, 1.0, 1.0)
    
    # X 軸距離是 1.0，Y/Z 重疊距離為 0
    """測試完全分開的兩個物件，計算 Gap X, Y, Z (中心點距離)"""
    b1_min = (0.0, 0.0, 0.0)
    b1_max = (2.0, 2.0, 2.0) # c=1,1,1
    
    b2_min = (4.0, 4.0, 4.0)
    b2_max = (6.0, 6.0, 6.0) # c=5,5,5
    
    dx, dy, dz, dist = calculate_gap(b1_min, b1_max, b2_min, b2_max)
    assert dx == 4.0
    assert dy == 4.0
    assert dz == 4.0
    # dist = sqrt(16+16+16) = sqrt(48) = 6.9282
    assert math.isclose(dist, math.sqrt(48), rel_tol=1e-5)

def test_calculate_gap_overlapping_boxes():
    """測試重疊的物件 (中心點仍會有距離除非完全重合)"""
    b1_min = (0.0, 0.0, 0.0)
    b1_max = (4.0, 4.0, 4.0) # c=2,2,2
    
    b2_min = (2.0, 2.0, 2.0)
    b2_max = (6.0, 6.0, 6.0) # c=4,4,4
    
    dx, dy, dz, dist = calculate_gap(b1_min, b1_max, b2_min, b2_max)
    assert dx == 2.0
    assert dy == 2.0
    assert dz == 2.0
    assert math.isclose(dist, math.sqrt(12), rel_tol=1e-5)

def test_calculate_gap_touching_boxes():
    """測試恰好碰在一起的物件"""
    b1_min = (0.0, 0.0, 0.0)
    b1_max = (1.0, 1.0, 1.0) # c=0.5, 0.5, 0.5
    
    b2_min = (1.0, 1.0, 1.0)
    b2_max = (2.0, 2.0, 2.0) # c=1.5, 1.5, 1.5
    
    dx, dy, dz, dist = calculate_gap(b1_min, b1_max, b2_min, b2_max)
    assert dx == 1.0
    assert dy == 1.0
    assert dz == 1.0
    assert math.isclose(dist, math.sqrt(3), rel_tol=1e-5)

def test_calculate_gap_diagonal_separation():
    """測試在斜角方向分開的物件"""
    b1_min = (0.0, 0.0, 0.0)
    b1_max = (2.0, 5.0, 6.0) # c=1.0, 2.5, 3.0
    
    b2_min = (5.0, 2.0, 10.0)
    b2_max = (8.0, 7.0, 12.0) # c=6.5, 4.5, 11.0
    
    # 中心點差值
    dx, dy, dz, dist = calculate_gap(b1_min, b1_max, b2_min, b2_max)
    assert dx == 5.5   # 6.5 - 1.0
    assert dy == 2.0   # 4.5 - 2.5
    assert dz == 8.0   # 11.0 - 3.0
    assert math.isclose(dist, math.sqrt(5.5**2 + 2.0**2 + 8.0**2), rel_tol=1e-5)

def test_calculate_gap_points():
    b1_min, b1_max = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
    b2_min, b2_max = (2.0, 0.5, 3.0), (3.0, 1.5, 4.0)

    p1, p2 = calculate_gap_points(b1_min, b1_max, b2_min, b2_max)

    # X axis: b1 is [0,1], b2 is [2,3]. Closest are 1.0 and 2.0
    assert p1[0] == 1.0
    assert p2[0] == 2.0

    # Y axis: b1 is [0,1], b2 is [0.5,1.5]. Overlap [0.5, 1.0]. Center = 0.75
    assert p1[1] == 0.75
    assert p2[1] == 0.75

    # Z axis: b1 is [0,1], b2 is [3,4]. Closest are 1.0 and 3.0
    assert p1[2] == 1.0
    assert p2[2] == 3.0
