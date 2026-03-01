import math
import omni.ext
import omni.ui as ui
import omni.kit.ui
import omni.kit.app
import omni.usd
from omni.ui import DockPreference
from pxr import Usd, UsdGeom, Gf

try:
    import omni.kit.clipboard as clipboard
except Exception:
    clipboard = None

from .measure_logic import format_stage_unit, get_precision, calculate_gap, calculate_gap_points

import carb



# ========================================================
#  核心邏輯與 UI Widget
# ========================================================
class SmartMeasureWidget:
    """ 核心邏輯與 UI 元件 """
    DISPLAY_UNITS = [
        ("mm", 0.001), ("cm", 0.01), ("m", 1.0), ("inch", 0.0254), ("ft", 0.3048),
    ]

    def __init__(self):
        self._usd_context = omni.usd.get_context()
        self._last_size_m = None
        self._last_count = 0
        self._last_dist_data = None
        self._current_selection_paths = []
        self._stage_mpu = 1.0
        self._stage_unit_name = "m"
        self._up_axis = "Z"
        self._bbox_cache = None
        self._display_unit_size = "cm"
        self._display_mpu_size = 0.01
        self._custom_precision_size = ui.SimpleIntModel(2)  # 預設 cm 是 2 位
        
        self._display_unit_dist = "cm"
        self._display_mpu_dist = 0.01
        self._custom_precision_dist = ui.SimpleIntModel(2)  # 預設 cm 是 2 位
        
        self._scene_view = None
        self._scene_frame = None
        self._manipulator = None
        self._stage_event_sub = None
        self._update_sub = None

        # UI Refs
        self._sel_paths_label = None
        self._len_label = None
        self._wid_label = None
        self._hei_label = None
        self._dist_main_label = None
        self._gap_x_label = None
        self._gap_y_label = None
        self._gap_z_label = None
        self._dist_msg_label = None
        self._stage_unit_label = None
        self._up_axis_label = None

    def startup(self):
        self._init_bbox_cache()
        # [Lifecycle] Do NOT start subscriptions here.
        # self._subscribe_events()
        # self._refresh_stage_info()
        # self._check_selection_and_measure()

    def shutdown(self):
        self._stage_event_sub = None
        self._bbox_cache = None
        self._destroy_scene_overlay()

    def build_ui_layout(self):
        scroll_frame = ui.ScrollingFrame(
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
        )
        with scroll_frame:
            with ui.VStack(spacing=5, padding=8, alignment=ui.Alignment.TOP):
                # Header
                with ui.VStack(spacing=2, height=0):
                    with ui.HStack(height=18):
                        ui.Label("Stage unit :", width=ui.Pixel(80), style={"color": 0x888888FF})
                        self._stage_unit_label = ui.Label("--", style={"color": 0xFFDDDDDD})
                    with ui.HStack(height=18):
                        ui.Label("Up-Axis    :", width=ui.Pixel(80), style={"color": 0x888888FF})
                        self._up_axis_label = ui.Label("--", style={"color": 0xFFDDDDDD})
                ui.Spacer(height=4)
                
                # Selected
                with ui.CollapsableFrame("Selected", collapsed=False, height=0):
                    with ui.VStack(spacing=4, padding=4):
                        with ui.ScrollingFrame(height=80, style={"background_color": 0x33000000, "border_radius": 4}):
                             # [New] Dynamic list container
                             self._sel_list_vbox = ui.VStack(spacing=2, padding=4)

                # Size
                with ui.CollapsableFrame("Object Size (Union)", collapsed=False, height=0):
                    with ui.Frame(style={"background_color": 0x33000000, "border_radius": 4}):
                        with ui.VStack(spacing=4, padding=6, height=0):
                            with ui.VStack(spacing=2, height=0):
                                self._len_label = ui.Label("X length: --")
                                self._wid_label = ui.Label("Y width : --")
                                self._hei_label = ui.Label("Z height: --")
                            ui.Spacer(height=2)
                            with ui.ZStack(height=30):
                                with ui.VStack():
                                    ui.Spacer()
                                    with ui.HStack(spacing=4):
                                        ui.Label("Units", width=ui.Pixel(50), style={"color": 0xAAAAAAFF})
                                        items = [u[0] for u in self.DISPLAY_UNITS]
                                        cb = ui.ComboBox(1, *items, width=ui.Pixel(60), style={"background_color": 0xFF222222})
                                        cb.model.get_item_value_model().add_value_changed_fn(self._on_size_unit_changed)
                                        
                                        ui.Label("Decimals", width=ui.Pixel(50), style={"color": 0xAAAAAAFF})
                                        ui.IntDrag(self._custom_precision_size, min=0, max=6, width=ui.Pixel(40))
                                        self._custom_precision_size.add_value_changed_fn(lambda m: self._update_all_labels())
                                        
                                        ui.Spacer(width=5)
                                        ui.Button("Copy", width=ui.Pixel(50), clicked_fn=lambda: self._copy_result("size"))
                                    ui.Spacer()

                # Distance
                with ui.CollapsableFrame("Distance (2 Objects)", collapsed=False, height=0):
                    with ui.Frame(style={"background_color": 0x33000000, "border_radius": 4}):
                        with ui.VStack(spacing=4, padding=6, height=0):
                            self._dist_msg_label = ui.Label("Select exactly 2 objects", style={"color": 0xFFAA00FF}, word_wrap=True)
                            self._dist_main_label = ui.Label("Distance: --", style={"font_size": 16, "color": 0xFF6AD7D9}) # d9d76a
                            with ui.VStack(spacing=2, height=0):
                                self._gap_x_label = ui.Label("Gap X: --", style={"color": 0xFF6060AA}) # aa6060
                                self._gap_y_label = ui.Label("Gap Y: --", style={"color": 0xFF76A371}) # 71a376
                                self._gap_z_label = ui.Label("Gap Z: --", style={"color": 0xFFA07D4F}) # 4f7da0
                            ui.Spacer(height=2)
                            with ui.ZStack(height=30):
                                with ui.VStack():
                                    ui.Spacer()
                                    with ui.HStack(spacing=4):
                                        ui.Label("Units", width=ui.Pixel(50), style={"color": 0xAAAAAAFF})
                                        items = [u[0] for u in self.DISPLAY_UNITS]
                                        cb = ui.ComboBox(1, *items, width=ui.Pixel(60), style={"background_color": 0xFF222222})
                                        cb.model.get_item_value_model().add_value_changed_fn(self._on_dist_unit_changed)
                                        
                                        ui.Label("Decimals", width=ui.Pixel(50), style={"color": 0xAAAAAAFF})
                                        ui.IntDrag(self._custom_precision_dist, min=0, max=6, width=ui.Pixel(40))
                                        self._custom_precision_dist.add_value_changed_fn(lambda m: self._update_all_labels())
                                        
                                        ui.Spacer(width=5)
                                        ui.Button("Copy", width=ui.Pixel(50), clicked_fn=lambda: self._copy_result("dist"))
                                    ui.Spacer()
                ui.Spacer(height=10)
        
        # [Lifecycle] Create Subscription Lazy (Active Mode)
        if not self._stage_event_sub:
            stream = self._usd_context.get_stage_event_stream()
            self._stage_event_sub = stream.create_subscription_to_pop(self._on_stage_event, name="smart_measure_stage")

        self._refresh_stage_info()
        self._check_selection_and_measure()
        return scroll_frame


    def _init_bbox_cache(self):
        purposes = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy, UsdGeom.Tokens.guide]
        self._bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes, useExtentsHint=False)

    def _subscribe_events(self):
        # [Refactor] Consolidated into stage event stream
        stream = self._usd_context.get_stage_event_stream()
        self._stage_event_sub = stream.create_subscription_to_pop(self._on_stage_event, name="smart_measure_stage")
        # Removed per-frame update subscription

    def _on_stage_event(self, event):
        # [Lifecycle] Liveness Check
        # Check if UI is still part of the layout (visible)
        # Check vstack existence instead of label
        if not self._sel_list_vbox:
             self._stage_event_sub = None
             return

        if event.type == int(omni.usd.StageEventType.OPENED):
            self._init_bbox_cache()
            self._refresh_stage_info()
            self._check_selection_and_measure()
        
        elif event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            # [Refactor] Only update measurement on selection change
            self._check_selection_and_measure()

        elif event.type == int(omni.usd.StageEventType.CLOSING):
            self._last_size_m = None
            self._last_dist_data = None
            self._refresh_header_info()
            self._update_all_labels(clear=True)
            if self._sel_list_vbox: self._sel_list_vbox.clear()

    def _refresh_stage_info(self):
        stage = self._usd_context.get_stage()
        if stage:
            mpu = UsdGeom.GetStageMetersPerUnit(stage) or 1.0
            if not math.isclose(mpu, self._stage_mpu, rel_tol=1e-6):
                self._stage_mpu = float(mpu)
                self._stage_unit_name = self._format_stage_unit(self._stage_mpu)
            try:
                axis = UsdGeom.GetStageUpAxis(stage)
                self._up_axis = "Z" if axis == UsdGeom.Tokens.z else "Y"
            except: pass
        else:
            self._stage_mpu = 1.0
            self._stage_unit_name = "m"
            self._up_axis = "Z"
        self._refresh_header_info()

    def _refresh_header_info(self):
        try:
            if self._stage_unit_label: self._stage_unit_label.text = self._stage_unit_name
            if self._up_axis_label: self._up_axis_label.text = self._up_axis
        except: pass

    def _format_stage_unit(self, mpu):
        return format_stage_unit(mpu)

    def _check_selection_and_measure(self):
        paths = self._usd_context.get_selection().get_selected_prim_paths()
        # [Redesign] Update List UI
        if self._sel_list_vbox:
            self._sel_list_vbox.clear()
            stage = self._usd_context.get_stage()
            if paths and stage:
                with self._sel_list_vbox:
                    for p in paths:
                        prim = stage.GetPrimAtPath(p)
                        if not prim or not prim.IsValid(): continue
                        name = prim.GetName()
                        type_name = prim.GetTypeName()
                        
                        # Icon Logic — direct ${glyphs} mapping
                        # Verified paths in C:/isaac_sim_5_1_0/kit/resources/glyphs/
                        _GLYPH_MAP = {
                            "Cube":          "${glyphs}/cube.svg",
                            "Sphere":        "${glyphs}/circle.svg",
                            "Cone":          "${glyphs}/asterisk.svg",
                            "Cylinder":      "${glyphs}/geometry.svg",
                            "Capsule":       "${glyphs}/geometry.svg",
                            "Mesh":          "${glyphs}/geometry.svg",
                            "Camera":        "${glyphs}/camera.svg",
                            "Xform":         "${glyphs}/menu_xform.svg",
                            "RectLight":     "${glyphs}/light.svg",
                            "DiskLight":     "${glyphs}/light.svg",
                            "SphereLight":   "${glyphs}/light.svg",
                            "DistantLight":  "${glyphs}/light.svg",
                            "CylinderLight": "${glyphs}/light.svg",
                        }
                        icon_path = _GLYPH_MAP.get(type_name)
                        
                        with ui.HStack(height=20):
                            # Icon
                            with ui.ZStack(width=16, height=16):
                                if icon_path:
                                    # Per-type color tint — match Stage panel appearance
                                    _COLOR_MAP = {
                                        "Cube":          0xFF909090,  # darker neutral grey
                                        "Sphere":        0xFF909090,
                                        "Cone":          0xFFBBA060,  # warm gold (matches Stage star icon)
                                        "Cylinder":      0xFF909090,
                                        "Capsule":       0xFF909090,
                                        "Mesh":          0xFF909090,
                                        "Camera":        0xFFFFCC44,  # warm yellow
                                        "Xform":         0xFFEB9E3B,  # orange-gold
                                        "RectLight":     0xFF7B9BAF,  # blue-grey
                                        "DiskLight":     0xFF7B9BAF,
                                        "SphereLight":   0xFF7B9BAF,
                                        "DistantLight":  0xFF7B9BAF,
                                        "CylinderLight": 0xFF7B9BAF,
                                    }
                                    icon_color = _COLOR_MAP.get(type_name, 0xFF909090)
                                    ui.Image(
                                        icon_path,
                                        width=16, height=16,
                                        style={"color": icon_color},
                                    )
                                else:
                                    # Fallback: Color Box
                                    # Mesh: Grey [M], Xform: Blue [X], Camera: Purple [C], Light: Yellow [L]
                                    icon_color = 0xFF555555 # Default Grey
                                    if "Mesh" in type_name or "Cube" in type_name: icon_color = 0xFF777777
                                    elif "Xform" in type_name: icon_color = 0xFFEB9E3B
                                    elif "Camera" in type_name: icon_color = 0xFF880088
                                    elif "Light" in type_name: icon_color = 0xFF00FFFF
                                    ui.Rectangle(style={"background_color": icon_color, "border_radius": 3})

                            ui.Spacer(width=8)
                            ui.Label(name, style={"color": 0xFFDDDDDD})
            else:
                 with self._sel_list_vbox:
                     ui.Label("None", style={"color": 0xFF888888, "font_style": "italic"})

        if paths: self._measure_paths(paths)
        else: self._on_clear()

    def _measure_paths(self, paths):
        stage = self._usd_context.get_stage()
        if not stage: return self._on_clear()
        if not self._bbox_cache: self._init_bbox_cache()
        self._bbox_cache.Clear()

        union_box = None
        count = 0
        valid_prims = []

        for p in paths:
            prim = stage.GetPrimAtPath(p)
            if not prim or not prim.IsValid(): continue
            try:
                bbox = self._bbox_cache.ComputeWorldBound(prim)
                world = bbox.ComputeAlignedBox()
                if world.IsEmpty(): continue
                valid_prims.append((prim, world))
                if union_box is None: union_box = Gf.Range3d(world)
                else: union_box.UnionWith(world)
                count += 1
            except: continue

        if union_box and not union_box.IsEmpty() and count > 0:
            sz = union_box.GetSize()
            s = float(self._stage_mpu)
            self._last_size_m = (sz[0]*s, sz[1]*s, sz[2]*s)
            self._last_count = count
        else:
            self._last_size_m = None

        self._last_dist_data = None
        if len(valid_prims) == 2:
            dx, dy, dz, dist = self._calculate_gap(valid_prims[0][1], valid_prims[1][1])
            p1, p2 = self._calculate_gap_points(valid_prims[0][1], valid_prims[1][1])
            s = float(self._stage_mpu)
            self._last_dist_data = {"dist": dist*s, "gap": (dx*s, dy*s, dz*s), "p1": p1, "p2": p2}
        self._update_all_labels()

    def _calculate_gap(self, b1, b2):
        mn1, mx1 = b1.GetMin(), b1.GetMax()
        mn2, mx2 = b2.GetMin(), b2.GetMax()
        return calculate_gap((mn1[0], mn1[1], mn1[2]), (mx1[0], mx1[1], mx1[2]),
                             (mn2[0], mn2[1], mn2[2]), (mx2[0], mx2[1], mx2[2]))

    def _calculate_gap_points(self, b1, b2):
        mn1, mx1 = b1.GetMin(), b1.GetMax()
        mn2, mx2 = b2.GetMin(), b2.GetMax()
        return calculate_gap_points((mn1[0], mn1[1], mn1[2]), (mx1[0], mx1[1], mx1[2]),
                                    (mn2[0], mn2[1], mn2[2]), (mx2[0], mx2[1], mx2[2]))

    def _on_clear(self):
        self._last_size_m = None
        self._last_dist_data = None
        self._update_all_labels(clear=True)

    def _update_all_labels(self, clear=False):
        try:
            if not self._len_label: return
            # Size
            if clear or self._last_size_m is None:
                self._len_label.text = "X length: --"
                self._wid_label.text = "Y width : --"
                self._hei_label.text = "Z height: --"
            else:
                p = self._custom_precision_size.as_int
                m = self._display_mpu_size
                x, y, z = self._last_size_m
                self._len_label.text = f"X length: {x/m:.{p}f} {self._display_unit_size}"
                self._wid_label.text = f"Y width : {y/m:.{p}f} {self._display_unit_size}"
                self._hei_label.text = f"Z height: {z/m:.{p}f} {self._display_unit_size}"
            
            # Distance
            if clear or self._last_dist_data is None:
                self._dist_main_label.text = "Distance: --"
                self._gap_x_label.text = "Gap X: --"
                self._gap_y_label.text = "Gap Y: --"
                self._gap_z_label.text = "Gap Z: --"
                paths = self._usd_context.get_selection().get_selected_prim_paths()
                if len(paths) == 0:
                    self._dist_msg_label.text = "No selection"; self._dist_msg_label.style = {"color": 0xAAFFFFFF}
                elif len(paths) != 2:
                    self._dist_msg_label.text = "Select exactly 2 objects"; self._dist_msg_label.style = {"color": 0xFFAA00FF}
                else:
                    self._dist_msg_label.text = "Objects have no bounds"
            else:
                self._dist_msg_label.text = "Distance Calculated"; self._dist_msg_label.style = {"color": 0xFF00AA00}
                p = self._custom_precision_dist.as_int
                m = self._display_mpu_dist
                d = self._last_dist_data['dist']
                gx, gy, gz = self._last_dist_data['gap']
                self._dist_main_label.text = f"Distance: {d/m:.{p}f} {self._display_unit_dist}"
                self._gap_x_label.text = f"Gap X: {gx/m:.{p}f} {self._display_unit_dist}"
                self._gap_y_label.text = f"Gap Y: {gy/m:.{p}f} {self._display_unit_dist}"
                self._gap_z_label.text = f"Gap Z: {gz/m:.{p}f} {self._display_unit_dist}"
            
            # [Feature] Viewport Overlay
            self._update_scene_view(clear=clear)
        except: pass

    def _update_scene_view(self, clear=False):
        """使用 omni.ui.scene.SceneView 在 Viewport 上繪製測距線段與標籤"""

        # --- 清除模式：移除 overlay ---
        if clear or not self._last_dist_data:
            self._destroy_scene_overlay()
            return

        p1 = self._last_dist_data.get("p1")
        p2 = self._last_dist_data.get("p2")

        if not p1 or not p2:
            self._destroy_scene_overlay()
            return

        # --- 取得 Viewport 視窗 ---
        try:
            from omni.kit.viewport.utility import get_active_viewport_window
            viewport_window = get_active_viewport_window()
            if not viewport_window:
                return
        except ImportError:
            carb.log_warn("[SmartMeasure] omni.kit.viewport.utility not available")
            return

        # --- 重建 SceneView overlay ---
        # 每次都重建以確保繪製內容正確更新
        self._destroy_scene_overlay()

        try:
            import omni.ui.scene as sc

            # 取得 viewport 的 scene overlay frame
            self._scene_frame = viewport_window.get_frame("smart_measure_overlay")
            if not self._scene_frame:
                carb.log_warn("[SmartMeasure] Could not get overlay frame from viewport")
                return

            with self._scene_frame:
                # SceneView 自動匹配 viewport 的 camera projection
                self._scene_view = sc.SceneView(
                    aspect_ratio_policy=sc.AspectRatioPolicy.STRETCH
                )
                with self._scene_view.scene:
                    # --- 測距線段 (青色) ---
                    p1_list = list(p1)
                    p2_list = list(p2)
                    sc.Line(p1_list, p2_list, color=ui.color(0.0, 1.0, 1.0, 1.0), thicknesses=[2.0])

                    # --- 端點十字標記 ---
                    marker_size = 2.0
                    for pt in [p1_list, p2_list]:
                        with sc.Transform(transform=sc.Matrix44.get_translation_matrix(pt[0], pt[1], pt[2])):
                            sc.Line([-marker_size, 0, 0], [marker_size, 0, 0],
                                    color=ui.color(0.0, 1.0, 1.0, 0.8), thicknesses=[1.5])
                            sc.Line([0, -marker_size, 0], [0, marker_size, 0],
                                    color=ui.color(0.0, 1.0, 1.0, 0.8), thicknesses=[1.5])
                            sc.Line([0, 0, -marker_size], [0, 0, marker_size],
                                    color=ui.color(0.0, 1.0, 1.0, 0.8), thicknesses=[1.5])

                    # --- 中點距離標籤 ---
                    mid = [(p1[i] + p2[i]) / 2.0 for i in range(3)]
                    d_str = self._dist_main_label.text.replace("Distance: ", "") if self._dist_main_label else ""
                    with sc.Transform(
                        transform=sc.Matrix44.get_translation_matrix(mid[0], mid[1], mid[2]),
                        look_at=sc.Transform.LookAt.CAMERA
                    ):
                        sc.Label(
                            d_str,
                            color=ui.color(0.0, 1.0, 1.0, 1.0),
                            size=18,
                            alignment=ui.Alignment.CENTER
                        )

            # 將 SceneView 的 camera model 綁定到 viewport 的 camera
            viewport_api = viewport_window.viewport_api
            if viewport_api and self._scene_view:
                self._scene_view.model = viewport_api.scene_view.model

        except Exception as e:
            carb.log_warn(f"[SmartMeasure] Viewport overlay error: {e}")

    def _destroy_scene_overlay(self):
        """安全清除 Scene overlay 資源"""
        if hasattr(self, '_scene_view') and self._scene_view:
            try:
                self._scene_view = None
            except:
                pass
        if hasattr(self, '_scene_frame') and self._scene_frame:
            try:
                self._scene_frame.clear()
                self._scene_frame = None
            except:
                pass
        self._manipulator = None



    def _on_size_unit_changed(self, m, _=None): 
        idx = m.get_value_as_int(); u = self.DISPLAY_UNITS[max(0, min(idx, 4))]
        self._display_unit_size = u[0]; self._display_mpu_size = u[1]
        self._custom_precision_size.set_value(get_precision(u[0]) if get_precision(u[0]) is not None else 3)
        self._update_all_labels()
        
    def _on_dist_unit_changed(self, m, _=None): 
        idx = m.get_value_as_int(); u = self.DISPLAY_UNITS[max(0, min(idx, 4))]
        self._display_unit_dist = u[0]; self._display_mpu_dist = u[1]
        self._custom_precision_dist.set_value(get_precision(u[0]) if get_precision(u[0]) is not None else 3)
        self._update_all_labels()

    def _copy_result(self, mode):
        if not clipboard: return
        t = f"{self._len_label.text}\n{self._wid_label.text}\n{self._hei_label.text}" if mode == "size" else f"{self._dist_main_label.text}\n{self._gap_x_label.text}\n{self._gap_y_label.text}\n{self._gap_z_label.text}"
        clipboard.copy(t)


# ========================================================
#  Extension Wrapper
# ========================================================
class SmartMeasureExtension(omni.ext.IExt):
    WINDOW_NAME = "Smart Measure"
    MENU_PATH = f"Zin Tools/{WINDOW_NAME}"

    def __init__(self):
        super().__init__()
        # [關鍵修正] 在 __init__ 中就建立 Widget 實例
        # 這樣即使 ZinAllTools 是手動實例化 Extension 而不是透過 Kit 載入，
        # self._widget 也會存在，不會報錯。
        self._widget = SmartMeasureWidget()
        self._window = None
        self._menu_added = False

    def on_startup(self, ext_id):
        # 這是獨立載入 Extension 時才會跑的
        self._build_menu()

    def on_shutdown(self):
        self._remove_menu()
        if self._widget: self._widget.shutdown(); self._widget = None
        if self._window: self._window.destroy(); self._window = None

    def _build_menu(self):
        try:
            m = omni.kit.ui.get_editor_menu()
            if m: m.add_item(self.MENU_PATH, self._toggle_window, toggle=True, value=False)
            self._menu_added = True
        except: pass

    def _remove_menu(self):
        try:
            m = omni.kit.ui.get_editor_menu()
            if m and m.has_item(self.MENU_PATH): m.remove_item(self.MENU_PATH)
        except: pass

    def _toggle_window(self, menu, value):
        if value:
            if not self._window:
                self._window = ui.Window(self.WINDOW_NAME, width=320, height=540, dockPreference=DockPreference.RIGHT)
                self._window.set_visibility_changed_fn(self._on_visibility_changed)
                with self._window.frame:
                    self._widget.build_ui_layout()
                self._widget.startup()
            self._window.visible = True
        else:
            if self._window: self._window.visible = False

    def _on_visibility_changed(self, visible):
        if self._menu_added:
            try: omni.kit.ui.get_editor_menu().set_value(self.MENU_PATH, bool(visible))
            except: pass

    # ========================================================
    #  [關鍵] 橋接方法 (Bridge Methods)
    #  供 Zin All Tools 呼叫，轉發給內部的 _widget
    # ========================================================
    def startup_logic(self):
        if self._widget:
            self._widget.startup()

    def shutdown_logic(self):
        if self._widget:
            self._widget.shutdown()

    def build_ui_layout(self):
        if self._widget:
            return self._widget.build_ui_layout()