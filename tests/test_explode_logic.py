"""Smart Exploded View 爆炸邏輯單元測試 — 不需 Omniverse 環境。"""

import math
import os
import sys

import pytest

EXT_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "exts", "tw.zin.smart_exploded", "smart_exploded"
    )
)
if EXT_DIR not in sys.path:
    sys.path.insert(0, EXT_DIR)

from explode_logic import (  # noqa: E402
    DIRECTION_LABELS,
    bounds_center,
    direction_from_index,
    direction_from_label,
    distance_from_center,
    dominant_direction_label,
    exploded_position,
    index_from_label,
    label_from_index,
    part_offset,
    suggest_distance,
)

HOME = (-318.1, 495.0, 212.9)


# ─── 方向對應 ────────────────────────────────────────────

def test_all_six_axis_directions():
    assert direction_from_label("X+") == (1.0, 0.0, 0.0)
    assert direction_from_label("X-") == (-1.0, 0.0, 0.0)
    assert direction_from_label("Y+") == (0.0, 1.0, 0.0)
    assert direction_from_label("Y-") == (0.0, -1.0, 0.0)
    assert direction_from_label("Z+") == (0.0, 0.0, 1.0)
    assert direction_from_label("Z-") == (0.0, 0.0, -1.0)


def test_label_index_roundtrip():
    for index, label in enumerate(DIRECTION_LABELS):
        assert label_from_index(index) == label
        assert index_from_label(label) == index
        assert direction_from_index(index) == direction_from_label(label)


def test_unknown_direction_label_is_rejected():
    with pytest.raises(ValueError):
        direction_from_label("W+")


def test_direction_index_out_of_range_is_rejected():
    with pytest.raises(ValueError):
        direction_from_index(99)


# ─── 位移計算 ────────────────────────────────────────────

def test_offset_scales_with_distance():
    assert part_offset((1.0, 0.0, 0.0), 50.0) == (50.0, 0.0, 0.0)


def test_offset_is_zero_when_factor_is_zero():
    assert part_offset((0.0, 0.0, 1.0), 50.0, factor=0.0) == (0.0, 0.0, 0.0)


def test_offset_scales_with_global_factor():
    assert part_offset((0.0, 0.0, 1.0), 100.0, factor=0.5) == (0.0, 0.0, 50.0)


def test_offset_scales_with_multiplier():
    assert part_offset((0.0, 1.0, 0.0), 10.0, factor=1.0, multiplier=3.0) == (0.0, 30.0, 0.0)


def test_negative_direction_moves_backwards():
    assert part_offset(direction_from_label("X-"), 25.0) == (-25.0, 0.0, 0.0)


def test_assembled_state_returns_home():
    assert exploded_position(HOME, direction_from_label("Z+"), 80.0, factor=0.0) == HOME


def test_fully_exploded_position():
    result = exploded_position(HOME, direction_from_label("Z+"), 80.0, factor=1.0)
    assert result == (-318.1, 495.0, 292.9)


def test_partial_explosion_is_linear():
    half = exploded_position(HOME, direction_from_label("Y+"), 100.0, factor=0.5)
    assert half == (-318.1, 545.0, 212.9)


# ─── 共同中心 ────────────────────────────────────────────

def test_bounds_center_uses_extents_not_average():
    """\u5075\u6e2c\u7528\u5747\u503c\u7684\u5be6\u4f5c\uff1a\u96f6\u4ef6\u5206\u4f48\u4e0d\u5747\u6642\u4e2d\u5fc3\u4e0d\u5f97\u88ab\u62c9\u504f\u3002"""
    centers = [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (10.0, 0.0, 0.0)]
    assert bounds_center(centers) == (5.0, 0.0, 0.0)


def test_bounds_center_of_empty_list():
    assert bounds_center([]) == (0.0, 0.0, 0.0)


def test_bounds_center_single_part():
    assert bounds_center([HOME]) == HOME


# ─── 自動方向判定 ────────────────────────────────────────

def test_dominant_direction_picks_largest_axis():
    # MOVES_BRACKET_R \u5728 Y+ \u5074
    assert dominant_direction_label((-318.1, 522.4, 212.9), (-318.1, 495.0, 212.9)) == "Y+"


def test_dominant_direction_negative_side():
    # MOVES_BRACKET_L \u5728 Y- \u5074
    assert dominant_direction_label((-318.1, 467.7, 212.9), (-318.1, 495.0, 212.9)) == "Y-"


def test_dominant_direction_prefers_the_strongest_offset():
    assert dominant_direction_label((5.0, 1.0, 2.0), (0.0, 0.0, 0.0)) == "X+"
    assert dominant_direction_label((1.0, 2.0, -9.0), (0.0, 0.0, 0.0)) == "Z-"


def test_dominant_direction_defaults_when_centered():
    assert dominant_direction_label((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)) == "Z+"


# ─── 距離建議 ────────────────────────────────────────────

def test_distance_from_center_is_euclidean():
    assert distance_from_center((3.0, 4.0, 0.0), (0.0, 0.0, 0.0)) == 5.0


def test_suggest_distance_uniform_when_accel_is_zero():
    near = suggest_distance((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), 100.0, accel=0.0, max_distance=10.0)
    far = suggest_distance((10.0, 0.0, 0.0), (0.0, 0.0, 0.0), 100.0, accel=0.0, max_distance=10.0)
    assert near == far == 100.0


def test_suggest_distance_proportional_when_accel_is_one():
    near = suggest_distance((2.0, 0.0, 0.0), (0.0, 0.0, 0.0), 100.0, accel=1.0, max_distance=10.0)
    far = suggest_distance((10.0, 0.0, 0.0), (0.0, 0.0, 0.0), 100.0, accel=1.0, max_distance=10.0)
    assert math.isclose(near, 20.0)
    assert math.isclose(far, 100.0)


def test_suggest_distance_handles_degenerate_extent():
    """\u6240\u6709\u96f6\u4ef6\u91cd\u5408\u6642\u4e0d\u5f97\u9664\u4ee5\u96f6\u3002"""
    assert suggest_distance((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 50.0, max_distance=0.0) == 50.0


def test_suggest_distance_clamps_accel_range():
    value = suggest_distance((5.0, 0.0, 0.0), (0.0, 0.0, 0.0), 100.0, accel=5.0, max_distance=10.0)
    assert math.isclose(value, 50.0)
