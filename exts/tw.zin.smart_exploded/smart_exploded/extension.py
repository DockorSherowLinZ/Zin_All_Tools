import omni.ext
import omni.ui as ui
import omni.usd
import omni.kit.app
import carb
from pxr import Usd, UsdGeom, Gf

import sys
import os

import zin_core.ui_utils as zin_ui_utils
from zin_core.menu import ZinMenuMixin

from .displacement_logic import resolve_home
from .explode_logic import (
    DIRECTION_LABELS,
    bounds_center,
    direction_from_index,
    distance_from_center,
    dominant_direction_label,
    exploded_position,
    index_from_label,
    suggest_distance,
)

# 自動分配時的基準距離，使用者可再逐項微調
DEFAULT_BASE_DISTANCE = 50.0


class ZinSmartExplodedExtension(ZinMenuMixin, omni.ext.IExt):
    """Zin Smart Exploded View — 逐組件拆解圖。

    每個組件自帶方向與距離，全域滑桿統一控制爆炸進度，
    因此可用同一個滑桿播放組裝/拆解過程。
    位移寫在被選取的組件本身，其整個子樹會一起移動。
    """
    WINDOW_NAME = "Smart Explode"
    MENU_PATH = f"Zin_All_Tools/{WINDOW_NAME}"
    
    def on_startup(self, ext_id):
        carb.log_info("[Zin Smart Exploded View] Extension started (Component Explode)")
        self._window = None
        self._menu_added = False

        # 每個組件: {"path", "name", "home", "direction", "distance_model"}
        # distance_model 隨組件長存，UI 重建時不重新註冊 callback。
        self._parts = []

        # 已警告過無法位移的 prim，避免拖曳時重複洗版
        self._unmovable_warned = set()

        self._parts_container = None
        self._status_label = None

        self._factor_model = ui.SimpleFloatModel(0.0)
        self._factor_model.add_value_changed_fn(lambda m: self._apply_explosion())
        self._multiplier_model = ui.SimpleFloatModel(1.0)
        self._multiplier_model.add_value_changed_fn(lambda m: self._apply_explosion())

        # 定義高階工業 CAD 介面風格字典 (遵循 Zin_Tools_Box 規範)
        self._style = {
            "Button": {
                "background_color": 0xFF444444, # Default: 深灰背景
                "color": 0xFFDDDDDD,
                "border_color": 0x00000000,
                "border_width": 1.0,
                "border_radius": 4.0,
                "padding": 5.0
            },
            "Button:hover": {
                "border_color": 0xFFFFA500,     # Hover: 品牌橘色邊框高亮
            },
            "Button:pressed": {
                "background_color": 0xFFFFA500, # Pressed: 品牌橘色
                "color": 0xFF000000,          
            },
            "Button.Active": {
                "background_color": 0xFFFFA500, # Active (作用中): 實心品牌橘色
                "color": 0xFF000000,
                "border_radius": 4.0
            },
            "FloatSlider": {
                "background_color": 0xFF222222,
                "color": 0xFFFFA500,            # 滑桿進度條: 品牌橘色
                "border_radius": 4.0
            },
            "Label": {
                "color": 0xFFDDDDDD,
            }
        }

        # 組件由使用者按下 Add Selected 明確加入，不隨選取自動變動，
        # 避免瀏覽場景時意外改動已設定好的拆解表。
        self._build_menu()

    def _toggle_window(self, menu, value):
        if value:
            if not self._window:
                self._window = ui.Window(self.WINDOW_NAME, width=520, height=520, dockPreference=ui.DockPreference.RIGHT_BOTTOM)
                self._window.set_visibility_changed_fn(self._on_visibility_changed)
                self.build_ui()
            self._window.visible = True
        else:
            if self._window:
                self._window.visible = False


    def build_ui(self):
        """建立逐組件拆解圖的 UI 佈局。"""
        context = self._window.frame if getattr(self, "_window", None) else ui.VStack()
        with context:
            with ui.VStack(style=zin_ui_utils.ZIN_NATIVE_STYLE, spacing=zin_ui_utils.ZIN_V_SPACING, padding=6):

                with ui.CollapsableFrame("Components", collapsed=False, height=ui.Fraction(1)):
                    with ui.VStack(spacing=zin_ui_utils.ZIN_V_SPACING, padding=6):
                        with ui.HStack(height=24, spacing=zin_ui_utils.ZIN_ROW_SPACING):
                            ui.Button("Add Selected", style=zin_ui_utils.STYLE_POSITIVE, clicked_fn=self._add_selected_parts)
                            ui.Button("Auto Assign", clicked_fn=self._auto_assign_directions,
                                      tooltip="依各組件相對共同中心的位置，自動指定方向與距離")
                            ui.Button("Clear", style=zin_ui_utils.STYLE_NEGATIVE, clicked_fn=self._clear_parts)

                        ui.Spacer(height=4)
                        with ui.HStack(height=20, spacing=4):
                            ui.Label("Component", width=ui.Fraction(1), name="Description")
                            ui.Label("Dir", width=ui.Pixel(60), name="Description")
                            ui.Label("Distance", width=ui.Pixel(80), name="Description")
                            ui.Spacer(width=ui.Pixel(28))

                        with ui.ScrollingFrame(height=ui.Fraction(1)):
                            self._parts_container = ui.VStack(spacing=2)

                with ui.CollapsableFrame("Explosion", collapsed=False, height=0):
                    with ui.VStack(spacing=zin_ui_utils.ZIN_V_SPACING, padding=6):
                        def build_factor():
                            ui.FloatSlider(self._factor_model, min=0.0, max=1.0,
                                           style={"draw_mode": ui.SliderDrawMode.HANDLE})
                        zin_ui_utils.build_property_row("Explode:", build_factor,
                                                        tooltip="0 = 組裝完成, 1 = 完全炸開")

                        def build_multiplier():
                            ui.FloatDrag(self._multiplier_model, min=0.1, max=20.0, step=0.1)
                        zin_ui_utils.build_property_row("Multiplier:", build_multiplier,
                                                        tooltip="整體距離倍率，適應不同模型尺度")

                        ui.Spacer(height=5)
                        with ui.HStack(height=24, spacing=zin_ui_utils.ZIN_ROW_SPACING):
                            ui.Button("Reset", style=zin_ui_utils.STYLE_NEGATIVE, clicked_fn=self._reset_all,
                                      tooltip="回到組裝完成狀態")
                            ui.Button("Commit", style=zin_ui_utils.STYLE_POSITIVE, clicked_fn=self._commit_positions,
                                      tooltip="將目前位置設為新的組裝原點")

                self._status_label = ui.Label("", name="Description", word_wrap=True)
                ui.Spacer()

        self._rebuild_parts_ui()

    # ----------------------------------------------------------------------
    #  Component table
    # ----------------------------------------------------------------------
    def _rebuild_parts_ui(self):
        """重畫組件清單。

        每列使用組件自帶的長存模型，因此 UI 重建不會重複註冊 callback。
        """
        if self._parts_container is None:
            return

        self._parts_container.clear()
        with self._parts_container:
            if not self._parts:
                ui.Label("尚未加入組件。請在 Stage 中選取組件後按 Add Selected。",
                         name="Description", word_wrap=True)
            else:
                for index, part in enumerate(self._parts):
                    with ui.HStack(height=24, spacing=4):
                        ui.Label(part["name"], width=ui.Fraction(1),
                                 tooltip=part["path"], elided_text=True)

                        combo = ui.ComboBox(part["direction"], *DIRECTION_LABELS, width=ui.Pixel(60))
                        combo.model.get_item_value_model().add_value_changed_fn(
                            lambda m, p=part: self._on_direction_changed(p, m)
                        )

                        ui.FloatDrag(part["distance_model"], width=ui.Pixel(80), min=0.0, max=100000.0, step=1.0)
                        ui.Button("X", width=ui.Pixel(24),
                                  clicked_fn=lambda i=index: self._remove_part(i))

        self._update_status()

    def _update_status(self):
        if self._status_label is None:
            return
        self._status_label.text = f"{len(self._parts)} component(s) registered."

    def _make_part(self, path, home, direction_label="Z+", distance=DEFAULT_BASE_DISTANCE):
        # ComboBox 需要項目模型，無法沿用值模型，故方向以純數值保存，
        # 每次重建 UI 時再建立對應的 ComboBox。
        distance_model = ui.SimpleFloatModel(float(distance))
        distance_model.add_value_changed_fn(lambda m: self._apply_explosion())

        return {
            "path": path,
            "name": path.rsplit("/", 1)[-1],
            "home": home,
            "direction": index_from_label(direction_label),
            "distance_model": distance_model,
        }

    def _on_direction_changed(self, part, model):
        part["direction"] = model.as_int
        self._apply_explosion()

    def _find_part(self, path):
        for part in self._parts:
            if part["path"] == path:
                return part
        return None

    def _add_selected_parts(self):
        """把目前選取的 prim 加入組件清單。

        位移會寫在被選取的 prim 上，其整個子樹一起移動，
        因此請選取「組件」層級而非底層 Mesh。
        """
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return

        selection = omni.usd.get_context().get_selection().get_selected_prim_paths()
        if not selection:
            carb.log_warn("[Zin Smart Exploded View] 沒有選取任何 prim。")
            return

        added = 0
        for path in selection:
            if self._find_part(path):
                continue

            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue

            xformable = UsdGeom.Xformable(prim)
            if not xformable:
                carb.log_warn(f"[Zin Smart Exploded View] '{path}' 不是 Xformable，已略過。")
                continue

            trans_op = self._get_translation_op(xformable)
            if trans_op is None:
                continue

            home = trans_op.Get()
            if home is None:
                home = Gf.Vec3d(0.0, 0.0, 0.0)

            self._parts.append(self._make_part(path, Gf.Vec3d(home)))
            added += 1

        if added:
            self._rebuild_parts_ui()
        carb.log_info(f"[Zin Smart Exploded View] Added {added} component(s).")

    def _remove_part(self, index):
        if not 0 <= index < len(self._parts):
            return
        part = self._parts[index]
        self._restore_part(part)
        del self._parts[index]
        self._rebuild_parts_ui()

    def _clear_parts(self):
        self._reset_all()
        self._parts = []
        self._rebuild_parts_ui()

    # ----------------------------------------------------------------------
    #  Auto assignment
    # ----------------------------------------------------------------------
    def _auto_assign_directions(self):
        """依各組件包圍盒中心相對共同中心的位置，自動指定方向與距離。"""
        stage = omni.usd.get_context().get_stage()
        if not stage or not self._parts:
            return

        bbox_cache = UsdGeom.BBoxCache(
            Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render]
        )

        centers = {}
        for part in self._parts:
            prim = stage.GetPrimAtPath(part["path"])
            if not prim or not prim.IsValid():
                continue
            bound = bbox_cache.ComputeWorldBound(prim).ComputeAlignedBox()
            if bound.IsEmpty():
                carb.log_warn(
                    f"[Zin Smart Exploded View] '{part['path']}' 包圍盒為空，"
                    "可能是 payload 尚未載入，已略過自動分配。"
                )
                continue
            midpoint = bound.GetMidpoint()
            centers[part["path"]] = (midpoint[0], midpoint[1], midpoint[2])

        if not centers:
            return

        shared_center = bounds_center(centers.values())
        max_distance = max(
            distance_from_center(center, shared_center) for center in centers.values()
        )

        for part in self._parts:
            center = centers.get(part["path"])
            if center is None:
                continue
            label = dominant_direction_label(center, shared_center)
            part["direction"] = index_from_label(label)
            part["distance_model"].set_value(
                suggest_distance(center, shared_center, DEFAULT_BASE_DISTANCE,
                                 accel=1.0, max_distance=max_distance)
            )

        self._rebuild_parts_ui()
        self._apply_explosion()

    # ----------------------------------------------------------------------
    #  Applying the explosion
    # ----------------------------------------------------------------------
    def _apply_explosion(self):
        """依各組件的方向與距離，套用全域爆炸進度。"""
        stage = omni.usd.get_context().get_stage()
        if not stage or not self._parts:
            return

        factor = self._factor_model.as_float
        multiplier = self._multiplier_model.as_float

        for part in self._parts:
            trans_op = self._resolve_translate_op(stage, part["path"])
            if trans_op is None:
                continue

            direction = direction_from_index(part["direction"])
            distance = part["distance_model"].as_float

            # 使用者可能以 gizmo 手動移動過組件，使記錄的原點失效；
            # 以「目前位置扣掉既有位移」重新校準，保留手動調整的結果。
            expected_offset = [
                direction[i] * distance * factor * multiplier for i in range(3)
            ]
            home = resolve_home(trans_op.Get(), part["home"], expected_offset)
            part["home"] = Gf.Vec3d(*home)

            trans_op.Set(
                Gf.Vec3d(*exploded_position(home, direction, distance, factor, multiplier))
            )

    def _resolve_translate_op(self, stage, path):
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            return None
        xformable = UsdGeom.Xformable(prim)
        if not xformable:
            return None
        return self._get_translation_op(xformable)

    def _restore_part(self, part):
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return
        trans_op = self._resolve_translate_op(stage, part["path"])
        if trans_op is not None:
            trans_op.Set(Gf.Vec3d(part["home"]))

    def _reset_all(self):
        """所有組件回到組裝完成狀態。"""
        for part in self._parts:
            self._restore_part(part)
        self._factor_model.set_value(0.0)

    def _commit_positions(self):
        """將目前位置設為新的組裝原點。"""
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return
        for part in self._parts:
            trans_op = self._resolve_translate_op(stage, part["path"])
            if trans_op is None:
                continue
            current = trans_op.Get()
            if current is not None:
                part["home"] = Gf.Vec3d(current)
        self._factor_model.set_value(0.0)

    def _can_author_transform(self, prim):
        """Instance proxy 是 instanced 階層的唯讀投影，USD 禁止在其上寫入屬性。"""
        if not prim.IsInstanceProxy():
            return True

        path = str(prim.GetPath())
        if path not in self._unmovable_warned:
            self._unmovable_warned.add(path)
            carb.log_warn(
                f"[Zin Smart Exploded View] '{path}' 是 instance proxy，無法位移。"
                "請改選取实例化的根物件，或將其 instanceable 關閉後再試。"
            )
        return False

    def _get_translation_op(self, xformable: UsdGeom.Xformable):
        """
        安全地取得或新增 xformOp:translate
        確保附加式的位移 (Additive Displacement) 不破壞模型既有的階層與旋轉結構。
        無法寫入的 prim（例如 instance proxy）回傳 None。
        """
        prim = xformable.GetPrim()
        if not self._can_author_transform(prim):
            return None

        ops = xformable.GetOrderedXformOps()
        for op in ops:
            # pivot 也是 TypeTranslate，但它描述旋轉/縮放中心，改動它會破壞模型。
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate and ":pivot" not in op.GetOpName():
                return op

        try:
            return xformable.AddTranslateOp()
        except Exception as exc:
            carb.log_warn(
                f"[Zin Smart Exploded View] 無法在 '{prim.GetPath()}' 建立 translate op：{exc}"
            )
            return None

    def _on_selection_changed(self, event):
        """保留給既有呼叫端的相容介面；組件改由 Add Selected 明確加入。"""
        return

    def on_shutdown(self):
        """清理資源：關閉視窗、清空組件表。"""
        carb.log_info("[Zin Smart Exploded View] Extension shutdown")
        self._remove_menu()

        if self._window:
            self._window.destroy()
            self._window = None

        self._parts = []
        self._parts_container = None
        self._status_label = None
        self._unmovable_warned.clear()
