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


# ========================================================
#  核心邏輯與 UI Widget
# ========================================================
class SmartMeasureWidget:
    """ 核心邏輯與 UI 元件 """
    METERS_PER_UNIT_TO_NAME = {
        1.0: "m", 0.1: "dm", 0.01: "cm", 0.001: "mm", 0.0254: "inch", 0.3048: "ft",
    }
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
        self._display_unit_dist = "cm"
        self._display_mpu_dist = 0.01
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
                                        cb = ui.ComboBox(1, *items, width=ui.Fraction(1), style={"background_color": 0xFF222222})
                                        cb.model.get_item_value_model().add_value_changed_fn(self._on_size_unit_changed)
                                        ui.Button("Copy", width=ui.Pixel(50), clicked_fn=lambda: self._copy_result("size"))
                                    ui.Spacer()

                # Distance
                with ui.CollapsableFrame("Distance (2 Objects)", collapsed=False, height=0):
                    with ui.Frame(style={"background_color": 0x33000000, "border_radius": 4}):
                        with ui.VStack(spacing=4, padding=6, height=0):
                            self._dist_msg_label = ui.Label("Select exactly 2 objects", style={"color": 0xFFAA00FF}, word_wrap=True)
                            self._dist_main_label = ui.Label("Dist: --", style={"font_size": 16, "color": 0xFF00AA00})
                            with ui.VStack(spacing=2, height=0):
                                self._gap_x_label = ui.Label("Gap X: --")
                                self._gap_y_label = ui.Label("Gap Y: --")
                                self._gap_z_label = ui.Label("Gap Z: --")
                            ui.Spacer(height=2)
                            with ui.ZStack(height=30):
                                with ui.VStack():
                                    ui.Spacer()
                                    with ui.HStack(spacing=4):
                                        ui.Label("Units", width=ui.Pixel(50), style={"color": 0xAAAAAAFF})
                                        items = [u[0] for u in self.DISPLAY_UNITS]
                                        cb = ui.ComboBox(1, *items, width=ui.Fraction(1), style={"background_color": 0xFF222222})
                                        cb.model.get_item_value_model().add_value_changed_fn(self._on_dist_unit_changed)
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
        for val, name in self.METERS_PER_UNIT_TO_NAME.items():
            if math.isclose(mpu, val, rel_tol=1e-5): return name
        return f"{math.ceil(mpu*100)/100.0:.4f} m"

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
            s = float(self._stage_mpu)
            self._last_dist_data = {"dist": dist*s, "gap": (dx*s, dy*s, dz*s)}
        self._update_all_labels()

    def _calculate_gap(self, b1, b2):
        mn1, mx1 = b1.GetMin(), b1.GetMax()
        mn2, mx2 = b2.GetMin(), b2.GetMax()
        gap = lambda a1, a2, b1, b2: b1 - a2 if a2 < b1 else (a1 - b2 if b2 < a1 else 0.0)
        dx = gap(mn1[0], mx1[0], mn2[0], mx2[0])
        dy = gap(mn1[1], mx1[1], mn2[1], mx2[1])
        dz = gap(mn1[2], mx1[2], mn2[2], mx2[2])
        return dx, dy, dz, math.sqrt(dx*dx + dy*dy + dz*dz)

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
                p = self._precision(self._display_unit_size)
                m = self._display_mpu_size
                x, y, z = self._last_size_m
                self._len_label.text = f"X length: {x/m:.{p}f} {self._display_unit_size}"
                self._wid_label.text = f"Y width : {y/m:.{p}f} {self._display_unit_size}"
                self._hei_label.text = f"Z height: {z/m:.{p}f} {self._display_unit_size}"
            
            # Distance
            if clear or self._last_dist_data is None:
                self._dist_main_label.text = "Dist: --"
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
                p = self._precision(self._display_unit_dist)
                m = self._display_mpu_dist
                d = self._last_dist_data['dist']
                gx, gy, gz = self._last_dist_data['gap']
                self._dist_main_label.text = f"Dist: {d/m:.{p}f} {self._display_unit_dist}"
                self._gap_x_label.text = f"Gap X: {gx/m:.{p}f} {self._display_unit_dist}"
                self._gap_y_label.text = f"Gap Y: {gy/m:.{p}f} {self._display_unit_dist}"
                self._gap_z_label.text = f"Gap Z: {gz/m:.{p}f} {self._display_unit_dist}"
        except: pass

    def _precision(self, unit): return {"mm": 1, "cm": 2, "m": 4, "inch": 2, "ft": 3}.get(unit, 3)
    def _on_size_unit_changed(self, m, _=None): 
        idx = m.get_value_as_int(); u = self.DISPLAY_UNITS[max(0, min(idx, 4))]
        self._display_unit_size = u[0]; self._display_mpu_size = u[1]; self._update_all_labels()
    def _on_dist_unit_changed(self, m, _=None):
        idx = m.get_value_as_int(); u = self.DISPLAY_UNITS[max(0, min(idx, 4))]
        self._display_unit_dist = u[0]; self._display_mpu_dist = u[1]; self._update_all_labels()
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