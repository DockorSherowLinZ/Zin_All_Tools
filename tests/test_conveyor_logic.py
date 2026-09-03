"""Smart Conveyor 純邏輯單元測試 — 不需 Omniverse 環境。"""

import os
import sys

import pytest

EXT_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "exts", "tw.zin.smart_conveyor", "smart_conveyor"
    )
)
if EXT_DIR not in sys.path:
    sys.path.insert(0, EXT_DIR)

from conveyor_logic import (  # noqa: E402
    POOL_SAFETY_BUFFER,
    calc_required_pool_size,
    distance,
    normalize_config,
)


# ─── distance ────────────────────────────────────────────

def test_distance_along_single_axis():
    assert distance((0, 0, 0), (3, 0, 0)) == 3.0


def test_distance_is_euclidean():
    assert distance((0, 0, 0), (3, 4, 0)) == 5.0


def test_distance_accepts_any_indexable_sequence():
    assert distance([1, 2, 3], (1, 2, 3)) == 0.0


# ─── calc_required_pool_size ─────────────────────────────

def test_pool_size_defaults_when_no_waypoints():
    assert calc_required_pool_size([], 50.0, 3.0) == 2


def test_pool_size_defaults_on_non_positive_speed():
    waypoints = [{"pos": (0, 0, 0)}, {"pos": (100, 0, 0)}]
    assert calc_required_pool_size(waypoints, 0.0, 3.0) == 2


def test_pool_size_defaults_on_non_positive_interval():
    waypoints = [{"pos": (0, 0, 0)}, {"pos": (100, 0, 0)}]
    assert calc_required_pool_size(waypoints, 50.0, 0.0) == 2


def test_pool_size_from_travel_time():
    # 距離 100，速度 50 → 2 秒；間隔 1 秒 → 2 個 + 安全緩衝
    waypoints = [{"pos": (0, 0, 0)}, {"pos": (100, 0, 0)}]
    assert calc_required_pool_size(waypoints, 50.0, 1.0) == 2 + POOL_SAFETY_BUFFER


def test_pool_size_includes_waypoint_pause():
    # 移動 2 秒 + 暫停 4 秒 = 6 秒；間隔 1 秒
    waypoints = [
        {"pos": (0, 0, 0)},
        {"pos": (100, 0, 0), "pause": 4.0},
    ]
    assert calc_required_pool_size(waypoints, 50.0, 1.0) == 6 + POOL_SAFETY_BUFFER


def test_pool_size_accumulates_multiple_segments():
    waypoints = [
        {"pos": (0, 0, 0)},
        {"pos": (50, 0, 0)},
        {"pos": (50, 50, 0)},
    ]
    # 總距離 100，速度 50 → 2 秒；間隔 2 秒 → 1 個 + 緩衝
    assert calc_required_pool_size(waypoints, 50.0, 2.0) == 1 + POOL_SAFETY_BUFFER


# ─── normalize_config ────────────────────────────────────

def test_normalize_flattens_global_settings():
    result = normalize_config(
        {"global_settings": {"speed": 12.5, "initial_delay": 2.0, "dispatch_interval": 4.0}}
    )
    assert result["speed"] == 12.5
    assert result["initial_delay"] == 2.0
    assert result["dispatch_interval"] == 4.0


def test_normalize_flattens_behavior():
    result = normalize_config({"behavior": {"reverse": True, "loop": True, "end_visibility": True}})
    assert result["reverse"] is True
    assert result["loop"] is True
    assert result["end_visibility"] is True


def test_normalize_keeps_existing_top_level_values():
    """攤平式設定優先，巢狀值不得覆寫已明確指定的頂層鍵。"""
    result = normalize_config({"speed": 99.0, "global_settings": {"speed": 12.5}})
    assert result["speed"] == 99.0


def test_normalize_joins_target_pcb_paths():
    result = normalize_config({"target_pcb_paths": ["/World/A", "/World/B"]})
    assert result["prim_paths"] == "/World/A, /World/B"


def test_normalize_does_not_override_existing_prim_paths():
    result = normalize_config(
        {"prim_paths": "/World/Existing", "target_pcb_paths": ["/World/A"]}
    )
    assert result["prim_paths"] == "/World/Existing"


def test_normalize_does_not_mutate_input():
    original = {"global_settings": {"speed": 12.5}}
    normalize_config(original)
    assert "speed" not in original


def test_normalize_ignores_malformed_sections():
    """設定損毀時應維持可用，而非拋出例外。"""
    result = normalize_config({"global_settings": None, "behavior": "invalid"})
    assert "speed" not in result
    assert "reverse" not in result
