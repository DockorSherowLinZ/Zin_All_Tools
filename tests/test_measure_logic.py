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

from measure_logic import format_stage_unit, get_precision, calculate_gap


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
    dx, dy, dz, dist = calculate_gap(b1_min, b1_max, b2_min, b2_max)
    assert math.isclose(dx, 1.0)
    assert math.isclose(dy, 0.0)
    assert math.isclose(dz, 0.0)
    assert math.isclose(dist, 1.0)

def test_calculate_gap_overlapping_boxes():
    """測試兩個重疊的物件"""
    b1_min = (0.0, 0.0, 0.0)
    b1_max = (2.0, 2.0, 2.0)
    
    b2_min = (1.0, 1.0, 1.0)
    b2_max = (3.0, 3.0, 3.0)
    
    # 三軸皆重疊，所有差值皆為 0
    dx, dy, dz, dist = calculate_gap(b1_min, b1_max, b2_min, b2_max)
    assert dx == 0.0
    assert dy == 0.0
    assert dz == 0.0
    assert dist == 0.0

def test_calculate_gap_touching_boxes():
    """測試恰好碰在一起的物件"""
    b1_min = (0.0, 0.0, 0.0)
    b1_max = (1.0, 1.0, 1.0)
    
    b2_min = (1.0, 1.0, 1.0)
    b2_max = (2.0, 2.0, 2.0)
    
    # 邊界碰在一起，距離為 0
    dx, dy, dz, dist = calculate_gap(b1_min, b1_max, b2_min, b2_max)
    assert dx == 0.0
    assert dy == 0.0
    assert dz == 0.0
    assert dist == 0.0

def test_calculate_gap_diagonal_separation():
    """測試在斜角方向分開的物件"""
    b1_min = (0.0, 0.0, 0.0)
    b1_max = (1.0, 1.0, 1.0)
    
    b2_min = (2.0, 2.0, 2.0)
    b2_max = (3.0, 3.0, 3.0)
    
    # 每個軸的距離都是 1
    dx, dy, dz, dist = calculate_gap(b1_min, b1_max, b2_min, b2_max)
    assert dx == 1.0
    assert dy == 1.0
    assert dz == 1.0
    # sqrt(1^2 + 1^2 + 1^2) = sqrt(3) ~= 1.732
    assert math.isclose(dist, math.sqrt(3))
