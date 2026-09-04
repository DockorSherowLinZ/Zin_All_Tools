"""Smart Explode 純邏輯單元測試 — 不需 Omniverse 環境。"""

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
    has_drifted,
    index_from_label,
    label_from_index,
    ordered_stages,
    part_offset,
    resolve_home,
    stage_progress,
    suggest_distance,
)

# 取自使用者實際模型 MOVES_BRACKET_R 的座標
HOME = (-318.1, 495.0, 212.9)
ASSEMBLY_CENTER = (-318.1, 495.0, 212.9)


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


def test_unknown_label_is_rejected():
    with pytest.raises(ValueError):
        direction_from_label("W+")


def test_index_out_of_range_is_rejected():
    with pytest.raises(ValueError):
        label_from_index(99)


# ─── 位移 ────────────────────────────────────────────────

def test_offset_scales_with_distance():
    assert part_offset((1.0, 0.0, 0.0), 50.0) == (50.0, 0.0, 0.0)


def test_offset_is_zero_when_assembled():
    assert part_offset((0.0, 0.0, 1.0), 50.0, factor=0.0) == (0.0, 0.0, 0.0)


def test_offset_scales_with_factor():
    assert part_offset((0.0, 0.0, 1.0), 100.0, factor=0.5) == (0.0, 0.0, 50.0)


def test_offset_scales_with_multiplier():
    assert part_offset((0.0, 1.0, 0.0), 10.0, multiplier=3.0) == (0.0, 30.0, 0.0)


def test_negative_direction_moves_backwards():
    assert part_offset(direction_from_label("X-"), 25.0) == (-25.0, 0.0, 0.0)


def test_assembled_state_returns_home():
    assert exploded_position(HOME, direction_from_label("Z+"), 80.0, factor=0.0) == HOME


def test_fully_exploded_position():
    assert exploded_position(HOME, direction_from_label("Z+"), 80.0) == (-318.1, 495.0, 292.9)


def test_explosion_progress_is_linear():
    assert exploded_position(HOME, direction_from_label("Y+"), 100.0, factor=0.5) == (
        -318.1, 545.0, 212.9
    )


def test_explosion_is_absolute_not_cumulative():
    """\u6ed1\u687f\u4ee3\u8868\u76f8\u5c0d\u539f\u9ede\u7684\u7e3d\u4f4d\u79fb\uff0c\u91cd\u8907\u5957\u7528\u4e0d\u61c9\u7d2f\u52a0\u3002"""
    first = exploded_position(HOME, direction_from_label("Z+"), 80.0, factor=1.0)
    second = exploded_position(HOME, direction_from_label("Z+"), 80.0, factor=1.0)
    assert first == second


# ─── 分階段展開 ──────────────────────────────────────────

def test_ordered_stages_dedupes_and_sorts():
    assert ordered_stages([3, 1, 2, 1, 3]) == (1, 2, 3)


def test_ordered_stages_of_empty():
    assert ordered_stages([]) == ()


def test_single_stage_follows_global_progress():
    assert stage_progress(0.0, 1, [1]) == 0.0
    assert stage_progress(0.4, 1, [1]) == 0.4
    assert stage_progress(1.0, 1, [1]) == 1.0


def test_stages_play_in_sequence():
    """\u4e09\u500b\u968e\u6bb5\uff1a\u524d\u4e00\u968e\u6bb5\u5b8c\u6210\u5f8c\u4e0b\u4e00\u968e\u6bb5\u624d\u958b\u59cb\u3002"""
    stages = [1, 2, 3]

    # \u5168\u57df 1/3 \u6642\uff0c\u7b2c\u4e00\u968e\u6bb5\u525b\u597d\u5b8c\u6210\uff0c\u5176\u9918\u672a\u52d5
    assert math.isclose(stage_progress(1 / 3, 1, stages), 1.0)
    assert math.isclose(stage_progress(1 / 3, 2, stages), 0.0)
    assert math.isclose(stage_progress(1 / 3, 3, stages), 0.0)

    # \u5168\u57df 1/2 \u6642\uff0c\u7b2c\u4e8c\u968e\u6bb5\u8d70\u4e00\u534a
    assert math.isclose(stage_progress(0.5, 1, stages), 1.0)
    assert math.isclose(stage_progress(0.5, 2, stages), 0.5)
    assert math.isclose(stage_progress(0.5, 3, stages), 0.0)


def test_all_stages_complete_at_full_progress():
    stages = [1, 2, 3]
    for stage in stages:
        assert stage_progress(1.0, stage, stages) == 1.0


def test_all_stages_assembled_at_zero():
    stages = [1, 2, 3]
    for stage in stages:
        assert stage_progress(0.0, stage, stages) == 0.0


def test_stage_numbers_need_not_be_contiguous():
    """\u4f7f\u7528\u8005\u53ef\u80fd\u7559\u4e0b\u7f3a\u865f\uff0c\u6392\u5e8f\u5f8c\u4f9d\u5e8f\u64ad\u653e\u5373\u53ef\u3002"""
    stages = [1, 5, 9]
    assert math.isclose(stage_progress(1 / 3, 1, stages), 1.0)
    assert math.isclose(stage_progress(1 / 3, 5, stages), 0.0)
    assert math.isclose(stage_progress(2 / 3, 5, stages), 1.0)


def test_unknown_stage_is_ordered_in():
    """\u67e5\u8a62\u5c1a\u672a\u767b\u9304\u7684\u968e\u6bb5\u4e0d\u5f97\u62cb\u932f\u3002"""
    assert 0.0 <= stage_progress(0.5, 7, [1, 2]) <= 1.0


def test_stage_progress_is_clamped():
    assert stage_progress(-1.0, 1, [1, 2]) == 0.0
    assert stage_progress(5.0, 2, [1, 2]) == 1.0


# ─── 外部移動偵測 ────────────────────────────────────────

def test_not_drifted_when_position_matches():
    assert has_drifted(HOME, HOME, (0.0, 0.0, 0.0)) is False


def test_not_drifted_with_applied_offset():
    assert has_drifted((-318.1, 495.0, 292.9), HOME, (0.0, 0.0, 80.0)) is False


def test_not_drifted_within_float_tolerance():
    assert has_drifted((-318.1 + 1e-9, 495.0, 212.9), HOME, (0.0, 0.0, 0.0)) is False


def test_drifted_after_manual_move():
    assert has_drifted((0.0, 0.0, 0.0), HOME, (0.0, 0.0, 0.0)) is True


def test_resolve_home_keeps_home_when_untouched():
    assert resolve_home((-318.1, 495.0, 292.9), HOME, (0.0, 0.0, 80.0)) == HOME


def test_resolve_home_rebaselines_after_manual_move():
    # 使用者把組件拖到 (0, 500, 0)，當時既有位移為 Z=80
    assert resolve_home((0.0, 500.0, 0.0), HOME, (0.0, 0.0, 80.0)) == (0.0, 500.0, -80.0)


def test_resolve_home_handles_missing_value():
    assert resolve_home(None, HOME, (0.0, 0.0, 0.0)) == HOME


def test_manual_move_is_preserved_not_reverted():
    """\u56de\u6b78\u7f3a\u9677\uff1a\u624b\u52d5\u79fb\u52d5\u5f8c\u8abf\u6574\u6ed1\u687f\uff0c\u7d44\u4ef6\u4e0d\u5f97\u5f48\u56de\u820a\u4f4d\u7f6e\u3002"""
    moved_to = (0.0, 500.0, 0.0)
    direction = direction_from_label("Z+")
    old_offset = part_offset(direction, 80.0, factor=1.0)

    home = resolve_home(moved_to, HOME, old_offset)
    result = exploded_position(home, direction, 120.0, factor=1.0)

    # 位移由 80 調到 120，應從現況再前進 40
    assert result == (0.0, 500.0, 40.0)


# ─── 共同中心 ────────────────────────────────────────────

def test_bounds_center_uses_extents_not_average():
    """\u96f6\u4ef6\u5206\u4f48\u4e0d\u5747\u6642\u4e2d\u5fc3\u4e0d\u5f97\u88ab\u62c9\u504f\u3002"""
    centers = [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (10.0, 0.0, 0.0)]
    assert bounds_center(centers) == (5.0, 0.0, 0.0)


def test_bounds_center_of_empty_list():
    assert bounds_center([]) == (0.0, 0.0, 0.0)


def test_bounds_center_single_component():
    assert bounds_center([HOME]) == HOME


# ─── 自動方向判定 ────────────────────────────────────────

def test_auto_direction_matches_real_bracket_layout():
    """\u5be6\u6e2c\u5ea7\u6a19\uff1aR \u5728 Y+ \u5074\u3001L \u5728 Y- \u5074\u3002"""
    assert dominant_direction_label((-318.1, 522.4, 212.9), ASSEMBLY_CENTER) == "Y+"
    assert dominant_direction_label((-318.1, 467.7, 212.9), ASSEMBLY_CENTER) == "Y-"


def test_auto_direction_picks_strongest_offset():
    assert dominant_direction_label((5.0, 1.0, 2.0), (0.0, 0.0, 0.0)) == "X+"
    assert dominant_direction_label((1.0, 2.0, -9.0), (0.0, 0.0, 0.0)) == "Z-"


def test_auto_direction_defaults_when_centered():
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
    """\u6240\u6709\u7d44\u4ef6\u91cd\u5408\u6642\u4e0d\u5f97\u9664\u4ee5\u96f6\u3002"""
    assert suggest_distance((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 50.0, max_distance=0.0) == 50.0


def test_suggest_distance_clamps_accel():
    value = suggest_distance((5.0, 0.0, 0.0), (0.0, 0.0, 0.0), 100.0, accel=5.0, max_distance=10.0)
    assert math.isclose(value, 50.0)
