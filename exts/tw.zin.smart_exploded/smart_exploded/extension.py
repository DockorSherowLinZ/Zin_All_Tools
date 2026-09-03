"""Smart Explode — 逐組件拆解圖。

在 Stage 中選取「組件」層級的 prim 加入清單，各自指定方向與距離，
再用單一滑桿控制整體爆炸進度。位移寫在被選取的組件本身，
其整個子樹會一起移動，因此組件與組件之間分離，而非內部每個 mesh 各自散開。

本模組不註冊任何事件訂閱，關閉時不會有殘留回呼。
"""

import carb
import omni.ext
import omni.kit.commands
import omni.ui as ui
import omni.usd
from pxr import Gf

import zin_core.ui_utils as zin_ui_utils
from zin_core.menu import ZinMenuMixin

from . import usd_utils
from .explode_logic import (
    DIRECTION_LABELS,
    bounds_center,
    direction_from_index,
    distance_from_center,
    dominant_direction_label,
    exploded_position,
    index_from_label,
    part_offset,
    resolve_home,
    suggest_distance,
)

# 自動分配的基準距離，使用者可再逐項微調
DEFAULT_BASE_DISTANCE = 50.0


class ZinExplodeTransformCommand(omni.kit.commands.Command):
    """記錄組件位移，讓爆炸操作可被 Ctrl+Z 復原。

    changes 為 [(prim_path, 舊座標, 新座標)]，一次拖曳合併為單一復原步驟。
    """

    def __init__(self, changes):
        self._changes = list(changes)

    def do(self):
        self._write({path: new for path, _old, new in self._changes})

    def undo(self):
        self._write({path: old for path, old, _new in self._changes})

    def _write(self, positions):
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return
        for path, value in positions.items():
            usd_utils.write_translation(stage, path, Gf.Vec3d(value))


class ZinSmartExplodedExtension(ZinMenuMixin, omni.ext.IExt):
    WINDOW_NAME = "Smart Explode"
    MENU_PATH = f"Zin_All_Tools/{WINDOW_NAME}"

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------
    def on_startup(self, ext_id):
        carb.log_info("[Smart Explode] Extension started")

        self._window = None
        self._menu_added = False

        # 每個組件: {"path", "name", "home", "direction", "distance_model"}
        self._components = []

        self._components_container = None
        self._status_label = None

        # 一次拖曳期間的起始座標，用於合併成單一 undo 步驟
        self._change_snapshot = None

        self._factor_model = ui.SimpleFloatModel(0.0)
        self._multiplier_model = ui.SimpleFloatModel(1.0)
        for model in (self._factor_model, self._multiplier_model):
            model.add_value_changed_fn(lambda m: self._apply())
            model.add_begin_edit_fn(lambda m: self._begin_change())
            model.add_end_edit_fn(lambda m: self._end_change())

        omni.kit.commands.register(ZinExplodeTransformCommand)
        self._build_menu()

    def on_shutdown(self):
        carb.log_info("[Smart Explode] Extension shutdown")
        self._remove_menu()

        try:
            omni.kit.commands.unregister(ZinExplodeTransformCommand)
        except Exception as exc:
            carb.log_verbose(f"[Smart Explode] Command already unregistered: {exc}")

        if self._window:
            self._window.destroy()
            self._window = None

        self._components = []
        self._components_container = None
        self._status_label = None
        self._change_snapshot = None

    def _toggle_window(self, menu, value):
        if value:
            if not self._window:
                self._window = ui.Window(
                    self.WINDOW_NAME, width=520, height=560,
                    dockPreference=ui.DockPreference.RIGHT_BOTTOM,
                )
                self._window.set_visibility_changed_fn(self._on_visibility_changed)
                with self._window.frame:
                    self.build_ui()
            self._window.visible = True
        elif self._window:
            self._window.visible = False

    # ------------------------------------------------------------------
    #  UI
    # ------------------------------------------------------------------
    def build_ui(self):
        """建立 UI。可獨立視窗使用，也可由 Tools Box 嵌入分頁。

        Kit 的 UI 字型不含中日韓字元，所有顯示字串一律使用英文。
        """
        with ui.VStack(style=zin_ui_utils.ZIN_NATIVE_STYLE,
                       spacing=zin_ui_utils.ZIN_V_SPACING, padding=6):

            ui.Label(
                "Select component-level prims, then Add Selected. "
                "Each component moves with its whole subtree.",
                name="Description", word_wrap=True, height=0,
            )

            with ui.HStack(height=24, spacing=zin_ui_utils.ZIN_ROW_SPACING):
                ui.Button("Add Selected", style=zin_ui_utils.STYLE_POSITIVE,
                          clicked_fn=self._add_selected)
                ui.Button("Auto Assign", clicked_fn=self._on_auto_assign,
                          tooltip="Assign direction and distance from each component's "
                                  "offset relative to the shared center")
                ui.Button("Clear", style=zin_ui_utils.STYLE_NEGATIVE,
                          clicked_fn=self._clear_components)

            # 爆炸控制是主要操作，放在按鈕下方避免被清單擠到視窗底部
            with ui.CollapsableFrame("Explosion", collapsed=False, height=0):
                with ui.VStack(spacing=zin_ui_utils.ZIN_V_SPACING, padding=6):
                    def build_factor():
                        ui.FloatSlider(self._factor_model, min=0.0, max=1.0)
                    zin_ui_utils.build_property_row(
                        "Explode:", build_factor,
                        tooltip="0 = assembled, 1 = fully exploded")

                    def build_multiplier():
                        ui.FloatDrag(self._multiplier_model, min=0.1, max=20.0, step=0.1)
                    zin_ui_utils.build_property_row(
                        "Multiplier:", build_multiplier,
                        tooltip="Overall distance scale for different model sizes")

                    with ui.HStack(height=24, spacing=zin_ui_utils.ZIN_ROW_SPACING):
                        ui.Button("Reset", style=zin_ui_utils.STYLE_NEGATIVE,
                                  clicked_fn=self._on_reset,
                                  tooltip="Return every component to its assembled position")
                        ui.Button("Commit", style=zin_ui_utils.STYLE_POSITIVE,
                                  clicked_fn=self._on_commit,
                                  tooltip="Use the current positions as the new assembled state")

            with ui.HStack(height=20, spacing=4):
                ui.Label("Component", width=ui.Fraction(1), name="Description")
                ui.Label("Dir", width=ui.Pixel(64), name="Description")
                ui.Label("Distance", width=ui.Pixel(84), name="Description")
                ui.Spacer(width=ui.Pixel(28))

            # 清單放在最後才佔用剩餘空間，空清單不會撐開版面
            with ui.ScrollingFrame(height=ui.Fraction(1)):
                self._components_container = ui.VStack(spacing=2)

            self._status_label = ui.Label("", name="Description", word_wrap=True, height=0)

        self._rebuild_component_rows()

    def _rebuild_component_rows(self):
        """重畫組件清單。

        distance_model 隨組件長存，方向以純數值保存，
        因此 UI 重建不會重複註冊 callback。
        """
        if self._components_container is None:
            return

        self._components_container.clear()
        with self._components_container:
            if not self._components:
                ui.Label("No components added yet.", name="Description", height=0)
            else:
                for index, component in enumerate(self._components):
                    self._build_component_row(index, component)

        self._update_status()

    def _build_component_row(self, index, component):
        with ui.HStack(height=24, spacing=4):
            ui.Label(component["name"], width=ui.Fraction(1),
                     tooltip=component["path"], elided_text=True)

            combo = ui.ComboBox(component["direction"], *DIRECTION_LABELS, width=ui.Pixel(64))
            combo.model.get_item_value_model().add_value_changed_fn(
                lambda m, c=component: self._on_direction_changed(c, m)
            )

            drag = ui.FloatDrag(component["distance_model"], width=ui.Pixel(84),
                                min=0.0, max=100000.0, step=1.0)
            drag.model.add_begin_edit_fn(lambda m: self._begin_change())
            drag.model.add_end_edit_fn(lambda m: self._end_change())

            ui.Button("X", width=ui.Pixel(24),
                      clicked_fn=lambda i=index: self._remove_component(i))

    def _update_status(self):
        if self._status_label is not None:
            self._status_label.text = f"{len(self._components)} component(s)."

    # ------------------------------------------------------------------
    #  Component management
    # ------------------------------------------------------------------
    def _make_component(self, path, home, direction_label="Z+", distance=DEFAULT_BASE_DISTANCE):
        distance_model = ui.SimpleFloatModel(float(distance))
        distance_model.add_value_changed_fn(lambda m: self._apply())

        return {
            "path": path,
            "name": path.rsplit("/", 1)[-1],
            "home": Gf.Vec3d(home),
            "direction": index_from_label(direction_label),
            "distance_model": distance_model,
        }

    def _add_selected(self):
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return

        selection = omni.usd.get_context().get_selection().get_selected_prim_paths()
        if not selection:
            self._set_status("Select one or more prims in the stage first.")
            return

        known = {component["path"] for component in self._components}
        added = 0
        skipped = []

        for path in selection:
            if path in known:
                continue

            op = usd_utils.resolve_translate_op(stage, path, create=True)
            if op is None:
                skipped.append(path.rsplit("/", 1)[-1])
                continue

            home = op.Get()
            self._components.append(
                self._make_component(path, home if home is not None else Gf.Vec3d(0.0))
            )
            added += 1

        self._rebuild_component_rows()

        if skipped:
            self._set_status(
                f"Added {added} component(s). Skipped {len(skipped)} that cannot be moved "
                f"(instance proxy or not Xformable): " + ", ".join(skipped[:3])
            )
        else:
            self._set_status(f"Added {added} component(s).")

    def _remove_component(self, index):
        if not 0 <= index < len(self._components):
            return
        component = self._components[index]
        self._tracked(lambda: self._restore(component))
        del self._components[index]
        self._rebuild_component_rows()

    def _clear_components(self):
        self._tracked(self._reset_all)
        self._components = []
        self._rebuild_component_rows()

    def _set_status(self, message):
        carb.log_info(f"[Smart Explode] {message}")
        if self._status_label is not None:
            self._status_label.text = message

    # ------------------------------------------------------------------
    #  Actions
    # ------------------------------------------------------------------
    def _on_direction_changed(self, component, model):
        self._begin_change()
        component["direction"] = model.as_int
        self._apply()
        self._end_change()

    def _on_auto_assign(self):
        self._tracked(self._auto_assign)

    def _on_reset(self):
        self._tracked(self._reset_all)

    def _on_commit(self):
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return
        for component in self._components:
            current = usd_utils.read_translation(stage, component["path"])
            if current is not None:
                component["home"] = Gf.Vec3d(current)
        self._factor_model.set_value(0.0)
        self._set_status("Current positions are now the assembled state.")

    def _auto_assign(self):
        stage = omni.usd.get_context().get_stage()
        if not stage or not self._components:
            return

        bbox_cache = usd_utils.make_bbox_cache()
        centers = {}
        for component in self._components:
            center = usd_utils.world_center(bbox_cache, stage, component["path"])
            if center is not None:
                centers[component["path"]] = center

        if not centers:
            self._set_status("Could not compute bounds; the payload may not be loaded.")
            return

        shared_center = bounds_center(centers.values())
        max_distance = max(
            distance_from_center(center, shared_center) for center in centers.values()
        )

        for component in self._components:
            center = centers.get(component["path"])
            if center is None:
                continue
            component["direction"] = index_from_label(
                dominant_direction_label(center, shared_center)
            )
            component["distance_model"].set_value(
                suggest_distance(center, shared_center, DEFAULT_BASE_DISTANCE,
                                 accel=1.0, max_distance=max_distance)
            )

        self._rebuild_component_rows()
        self._apply()
        self._set_status(f"Assigned direction and distance for {len(centers)} component(s).")

    def _reset_all(self):
        for component in self._components:
            self._restore(component)
        self._factor_model.set_value(0.0)

    def _restore(self, component):
        stage = omni.usd.get_context().get_stage()
        if stage:
            usd_utils.write_translation(stage, component["path"], Gf.Vec3d(component["home"]))

    # ------------------------------------------------------------------
    #  Core: applying the explosion
    # ------------------------------------------------------------------
    def _apply(self):
        """依各組件的方向與距離，套用全域爆炸進度。"""
        stage = omni.usd.get_context().get_stage()
        if not stage or not self._components:
            return

        factor = self._factor_model.as_float
        multiplier = self._multiplier_model.as_float

        for component in self._components:
            op = usd_utils.resolve_translate_op(stage, component["path"], create=True)
            if op is None:
                continue

            direction = direction_from_index(component["direction"])
            distance = component["distance_model"].as_float

            # 使用者可能以 gizmo 手動移動過組件，使記錄的原點失效；
            # 重新校準後手動調整的結果才不會被蓋掉。
            offset = part_offset(direction, distance, factor, multiplier)
            home = resolve_home(op.Get(), component["home"], offset)
            component["home"] = Gf.Vec3d(*home)

            op.Set(Gf.Vec3d(*exploded_position(home, direction, distance, factor, multiplier)))

    # ------------------------------------------------------------------
    #  Undo
    # ------------------------------------------------------------------
    def _capture_positions(self):
        stage = omni.usd.get_context().get_stage()
        positions = {}
        if not stage:
            return positions

        for component in self._components:
            current = usd_utils.read_translation(stage, component["path"])
            if current is not None:
                positions[component["path"]] = Gf.Vec3d(current)
        return positions

    def _begin_change(self):
        self._change_snapshot = self._capture_positions()

    def _end_change(self):
        """把這次操作前後的差異登錄為一個可復原的步驟。"""
        before = self._change_snapshot
        self._change_snapshot = None
        if not before:
            return

        after = self._capture_positions()
        changes = [
            (path, before[path], after[path])
            for path in after
            if path in before and after[path] != before[path]
        ]
        if changes:
            omni.kit.commands.execute("ZinExplodeTransform", changes=changes)

    def _tracked(self, action):
        """執行會改動座標的操作，並登錄為單一 undo 步驟。"""
        self._begin_change()
        action()
        self._end_change()
