"""Smart Exploded View 位移邏輯單元測試 — 不需 Omniverse 環境。"""

import os
import sys

EXT_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "exts", "tw.zin.smart_exploded", "smart_exploded"
    )
)
if EXT_DIR not in sys.path:
    sys.path.insert(0, EXT_DIR)

from displacement_logic import (  # noqa: E402
    apply_displacement,
    has_drifted,
    rebase_home,
    resolve_home,
)

HOME = (-188.25, 232.55, 0.0)


# ─── has_drifted ─────────────────────────────────────────

def test_not_drifted_when_position_matches_home_plus_offset():
    assert has_drifted((-188.25, 232.55, 0.0), HOME, [0.0, 0.0, 0.0]) is False


def test_not_drifted_with_applied_offset():
    assert has_drifted((-88.25, 232.55, 0.0), HOME, [100.0, 0.0, 0.0]) is False


def test_not_drifted_within_float_tolerance():
    assert has_drifted((-188.25 + 1e-9, 232.55, 0.0), HOME, [0.0, 0.0, 0.0]) is False


def test_drifted_when_moved_externally():
    assert has_drifted((0.0, 500.0, 0.0), HOME, [0.0, 0.0, 0.0]) is True


# ─── rebase_home ─────────────────────────────────────────

def test_rebase_home_subtracts_current_offset():
    assert rebase_home((0.0, 500.0, 0.0), [100.0, 0.0, 0.0]) == (-100.0, 500.0, 0.0)


# ─── resolve_home ────────────────────────────────────────

def test_resolve_home_keeps_home_when_untouched():
    assert resolve_home((-88.25, 232.55, 0.0), HOME, [100.0, 0.0, 0.0]) == HOME


def test_resolve_home_rebaselines_after_external_move():
    # 使用者把物件拖到 (0, 500, 0)，此時既有位移為 X=100
    assert resolve_home((0.0, 500.0, 0.0), HOME, [100.0, 0.0, 0.0]) == (-100.0, 500.0, 0.0)


def test_resolve_home_handles_missing_current_value():
    assert resolve_home(None, HOME, [0.0, 0.0, 0.0]) == HOME


# ─── apply_displacement ──────────────────────────────────

def test_first_displacement_moves_from_home():
    new_pos, new_home, new_offset = apply_displacement(
        HOME, HOME, [0.0, 0.0, 0.0], axis=0, value=100.0
    )
    assert new_pos == (-88.25, 232.55, 0.0)
    assert new_home == HOME
    assert new_offset == [100.0, 0.0, 0.0]


def test_displacement_is_absolute_not_cumulative():
    """\u6ed1\u687f\u4ee3\u8868\u76f8\u5c0d\u539f\u9ede\u7684\u7e3d\u4f4d\u79fb\uff0c\u91cd\u8907\u5957\u7528\u4e0d\u61c9\u7d2f\u52a0\u3002"""
    current = (-88.25, 232.55, 0.0)
    new_pos, _, _ = apply_displacement(current, HOME, [100.0, 0.0, 0.0], axis=0, value=100.0)
    assert new_pos == current


def test_returning_slider_to_zero_restores_home():
    new_pos, _, new_offset = apply_displacement(
        (-88.25, 232.55, 0.0), HOME, [100.0, 0.0, 0.0], axis=0, value=0.0
    )
    assert new_pos == HOME
    assert new_offset == [0.0, 0.0, 0.0]


def test_external_move_is_preserved_not_reverted():
    """\u56de\u6b78\u7f3a\u9677\uff1a\u624b\u52d5\u79fb\u52d5\u5f8c\u8abf\u6574\u6ed1\u687f\uff0c\u7269\u4ef6\u4e0d\u5f97\u5f48\u56de\u820a\u4f4d\u7f6e\u3002"""
    moved_to = (0.0, 500.0, 0.0)
    new_pos, _, _ = apply_displacement(
        moved_to, HOME, [100.0, 0.0, 0.0], axis=0, value=150.0
    )
    # \u6ed1\u687f\u5f9e 100 \u8abf\u5230 150\uff0c\u61c9\u5f9e\u73fe\u6cc1\u518d\u524d\u9032 50
    assert new_pos == (50.0, 500.0, 0.0)


def test_external_move_then_zero_slider_returns_to_moved_position():
    moved_to = (0.0, 500.0, 0.0)
    new_pos, _, _ = apply_displacement(
        moved_to, HOME, [100.0, 0.0, 0.0], axis=0, value=0.0
    )
    assert new_pos == (-100.0, 500.0, 0.0)


def test_axis_switch_keeps_other_axis_offsets():
    new_pos, _, new_offset = apply_displacement(
        (-88.25, 232.55, 0.0), HOME, [100.0, 0.0, 0.0], axis=1, value=25.0
    )
    assert new_offset == [100.0, 25.0, 0.0]
    assert new_pos == (-88.25, 257.55, 0.0)


def test_negative_displacement():
    new_pos, _, _ = apply_displacement(HOME, HOME, [0.0, 0.0, 0.0], axis=2, value=-40.0)
    assert new_pos == (-188.25, 232.55, -40.0)
