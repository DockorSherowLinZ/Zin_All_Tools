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


class SmartMeasureExtension(omni.ext.IExt):
    WINDOW_NAME = "Smart Measure"
    MENU_PATH = f"Zin Tools/{WINDOW_NAME}"

    METERS_PER_UNIT_TO_NAME = {
        1.0: "m",
        0.1: "dm",
        0.01: "cm",
        0.001: "mm",
        0.0254: "inch",
        0.3048: "ft",
    }

    DISPLAY_UNITS = [
        ("mm", 0.001),
        ("cm", 0.01),
        ("m", 1.0),
        ("inch", 0.0254),
        ("ft", 0.3048),
    ]

    # ---------------- lifecycle ----------------
    def on_startup(self, ext_id):
        self._usd_context = omni.usd.get_context()

        # State
        self._last_size_m = None
        self._last_count = 0
        self._last_dist_data = None
        
        self._stage_mpu = 1.0
        self._stage_unit_name = "m"
        self._up_axis = "Z"
        
        # Display settings
        self._display_unit_size = "cm"
        self._display_mpu_size = 0.01
        self._display_unit_dist = "cm"
        self._display_mpu_dist = 0.01

        # Subs
        self._stage_event_sub = None
        self._update_sub = None # [關鍵] 用於即時更新
        self._menu_added = False

        self._build_menu()
        self._build_window()
        self._subscribe_events()

        # 啟動時刷新一次
        self._refresh_stage_info()
        self._refresh_and_measure()

    def on_shutdown(self):
        try:
            if self._menu_added:
                editor_menu = omni.kit.ui.get_editor_menu()
                if editor_menu and hasattr(editor_menu, "has_item") and editor_menu.has_item(self.MENU_PATH):
                    editor_menu.remove_item(self.MENU_PATH)
        except Exception:
            pass

        self._stage_event_sub = None
        self._update_sub = None
        self._window = None

    # ---------------- UI ----------------
    def _build_menu(self):
        try:
            editor_menu = omni.kit.ui.get_editor_menu()
            if editor_menu:
                editor_menu.add_item(self.MENU_PATH, self._toggle_window, toggle=True, value=True)
                self._menu_added = True
        except Exception:
            self._menu_added = False

    def _build_window(self):
        self._window = ui.Window(
            SmartMeasureExtension.WINDOW_NAME,
            width=320,
            height=520,
            dockPreference=DockPreference.RIGHT,
        )
        self._window.set_visibility_changed_fn(self._on_visibility_changed)

        with self._window.frame:
            with ui.ScrollingFrame(
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
            ):
                with ui.VStack(spacing=5, padding=8, alignment=ui.Alignment.TOP):

                    # ---------- Header (Stage Info) ----------
                    with ui.VStack(spacing=2, height=0):
                        with ui.HStack(height=18):
                            ui.Label("Stage unit :", width=80, style={"color": 0x888888FF})
                            self._stage_unit_label = ui.Label("m", style={"color": 0xFFDDDDDD})
                        with ui.HStack(height=18):
                            ui.Label("Up-Axis    :", width=80, style={"color": 0x888888FF})
                            self._up_axis_label = ui.Label("Z", style={"color": 0xFFDDDDDD})
                    
                    ui.Spacer(height=4)
                    ui.Line(style={"color": 0x33FFFFFF})
                    ui.Spacer(height=4)

                    # ---------- 1. Selected List ----------
                    with ui.CollapsableFrame("Selected", collapsed=False, height=0):
                        with ui.VStack(spacing=4, padding=4):
                            with ui.HStack(height=0):
                                ui.Label("Prim", width=40, style={"color": 0xAAAAAAFF})
                                with ui.ScrollingFrame(height=70, style={"background_color": 0x33000000, "border_radius": 4}):
                                    self._sel_paths_label = ui.Label(
                                        "",
                                        word_wrap=True,
                                        alignment=ui.Alignment.LEFT_TOP,
                                        style={"margin": 4}
                                    )

                    # ---------- 2. Object Size (Union) ----------
                    with ui.CollapsableFrame("Object Size (Union)", collapsed=False, height=0):
                        with ui.Frame(style={"background_color": 0x11111111, "border_radius": 4}):
                            with ui.VStack(spacing=4, padding=6, height=0):
                                with ui.VStack(spacing=2, height=0):
                                    self._len_label = ui.Label("X length: --")
                                    self._wid_label = ui.Label("Y width : --")
                                    self._hei_label = ui.Label("Z height: --")
                                
                                ui.Spacer(height=2)
                                
                                with ui.HStack(height=24):
                                    ui.Label("Units", width=50, style={"color": 0xAAAAAAFF})
                                    items = [u[0] for u in self.DISPLAY_UNITS]
                                    self._unit_combo_size = ui.ComboBox(1, *items) 
                                    self._unit_combo_size.model.get_item_value_model().add_value_changed_fn(
                                        self._on_size_unit_changed
                                    )
                                    ui.Spacer(width=5)
                                    ui.Button("Copy", width=50, clicked_fn=lambda: self._copy_result("size"))

                    # ---------- 3. Distance (2 Objects) ----------
                    with ui.CollapsableFrame("Distance (2 Objects)", collapsed=False, height=0):
                        with ui.Frame(style={"background_color": 0x11111111, "border_radius": 4}):
                            with ui.VStack(spacing=4, padding=6, height=0):
                                self._dist_msg_label = ui.Label("Select exactly 2 objects", style={"color": 0xFFAA00FF}, word_wrap=True)
                                self._dist_main_label = ui.Label("Dist: --", style={"font_size": 16, "color": 0xFF00AA00})

                                with ui.VStack(spacing=2, height=0):
                                    self._gap_x_label = ui.Label("Gap X: --")
                                    self._gap_y_label = ui.Label("Gap Y: --")
                                    self._gap_z_label = ui.Label("Gap Z: --")

                                ui.Spacer(height=2)

                                with ui.HStack(height=24):
                                    ui.Label("Units", width=50, style={"color": 0xAAAAAAFF})
                                    items = [u[0] for u in self.DISPLAY_UNITS]
                                    self._unit_combo_dist = ui.ComboBox(1, *items)
                                    self._unit_combo_dist.model.get_item_value_model().add_value_changed_fn(
                                        self._on_dist_unit_changed
                                    )
                                    ui.Spacer(width=5)
                                    ui.Button("Copy", width=50, clicked_fn=lambda: self._copy_result("dist"))
                                
                                ui.Spacer(height=2)

                    ui.Spacer(height=10)

    # ---------------- events ----------------
    def _subscribe_events(self):
        # 1. Stage Events (開啟/關閉場景)
        stream = self._usd_context.get_stage_event_stream()
        self._stage_event_sub = stream.create_subscription_to_pop(
            self._on_stage_event, name="smart_measure_stage"
        )

        # 2. Update Loop (每一幀執行) - 這是實現無崩潰即時監聽的關鍵
        app = omni.kit.app.get_app()
        update_stream = app.get_update_event_stream()
        self._update_sub = update_stream.create_subscription_to_pop(
            self._on_update, name="smart_measure_update"
        )

    def _toggle_window(self, menu, value):
        if self._window:
            self._window.visible = bool(value)

    def _on_visibility_changed(self, visible):
        if not self._menu_added:
            return
        try:
            editor_menu = omni.kit.ui.get_editor_menu()
            if editor_menu:
                editor_menu.set_value(self.MENU_PATH, bool(visible))
        except Exception:
            pass

    def _on_stage_event(self, event):
        t = event.type
        if t == int(omni.usd.StageEventType.OPENED):
            self._refresh_stage_info()
            self._update_all_labels(clear=True)
            self._refresh_and_measure()
        elif t == int(omni.usd.StageEventType.CLOSING):
            self._last_size_m = None
            self._last_dist_data = None
            self._last_count = 0
            self._stage_mpu = 1.0
            self._refresh_header_info()
            self._update_all_labels(clear=True)
            self._render_selected_paths([])

    def _on_update(self, _):
        """ 
        每一幀被呼叫。
        只有當視窗開啟時，才去檢查選取並執行測量。
        這取代了不穩定的 Tf.Notice 監聽器。
        """
        if self._window and self._window.visible:
            # 這裡不需擔心效能，因為 BBoxCache 和 USD 查詢非常快
            self._refresh_and_measure()

    # ---------------- selected list ----------------
    def _render_selected_paths(self, paths):
        self._sel_paths_label.text = "\n".join(paths) if paths else ""

    # ---------------- units logic ----------------
    def _on_size_unit_changed(self, model, _=None):
        idx = model.get_value_as_int()
        name, mpu = self.DISPLAY_UNITS[max(0, min(idx, len(self.DISPLAY_UNITS) - 1))]
        self._display_unit_size = name
        self._display_mpu_size = mpu
        self._update_all_labels()

    def _on_dist_unit_changed(self, model, _=None):
        idx = model.get_value_as_int()
        name, mpu = self.DISPLAY_UNITS[max(0, min(idx, len(self.DISPLAY_UNITS) - 1))]
        self._display_unit_dist = name
        self._display_mpu_dist = mpu
        self._update_all_labels()

    def _format_stage_unit(self, mpu: float) -> str:
        for val, name in self.METERS_PER_UNIT_TO_NAME.items():
            if math.isclose(mpu, val, rel_tol=1e-5):
                return name
        v = math.ceil(float(mpu) * 100) / 100.0
        return f"{v:.4f} m"

    def _refresh_stage_info(self):
        stage = self._usd_context.get_stage()
        if stage:
            mpu = UsdGeom.GetStageMetersPerUnit(stage) or 1.0
            self._stage_mpu = float(mpu)
            self._stage_unit_name = self._format_stage_unit(self._stage_mpu)
            try:
                axis_token = UsdGeom.GetStageUpAxis(stage)
                self._up_axis = "Z" if axis_token == UsdGeom.Tokens.z else "Y"
            except Exception:
                self._up_axis = "Z"
        else:
            self._stage_mpu = 1.0
            self._stage_unit_name = "m"
            self._up_axis = "Z"
        self._refresh_header_info()

    def _refresh_header_info(self):
        self._stage_unit_label.text = self._stage_unit_name
        self._up_axis_label.text = self._up_axis

    # ---------------- MEASUREMENT LOGIC ----------------
    def _refresh_and_measure(self):
        # 1. 取得當前選取
        paths = self._usd_context.get_selection().get_selected_prim_paths()
        
        # 2. 更新選取清單 UI (如果選取沒變，這行其實可以優化，但為了即時性先保留)
        self._render_selected_paths(paths)
        
        if paths:
            self._measure_paths(paths)
        else:
            self._on_clear()

    def _measure_paths(self, paths):
        stage = self._usd_context.get_stage()
        if not stage or not paths:
            self._on_clear()
            return

        # 使用 BBoxCache 確保能抓到所有幾何體
        purposes = [
            UsdGeom.Tokens.default_, UsdGeom.Tokens.render, 
            UsdGeom.Tokens.proxy, UsdGeom.Tokens.guide
        ]
        # useExtentsHint=True 雖然快，但有時不準確，這裡拿掉以求精確，或保留看需求
        # 如果拖曳時太卡，可以加回 useExtentsHint=True
        bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes)

        # PART A: Union Size
        union_aabb_stage = None
        count = 0
        valid_prims = []

        for p in paths:
            prim = stage.GetPrimAtPath(p)
            if not prim or not prim.IsValid(): continue
            
            try:
                # 這裡會每幀運算，確保 Transform 變化時 BBox 跟著變
                bbox = bbox_cache.ComputeWorldBound(prim)
                world_aabb = bbox.ComputeAlignedBox()
                if world_aabb.IsEmpty(): continue

                valid_prims.append((prim, world_aabb))

                if union_aabb_stage is None:
                    union_aabb_stage = Gf.Range3d(world_aabb)
                else:
                    union_aabb_stage.UnionWith(world_aabb)
                count += 1
            except Exception:
                continue

        if union_aabb_stage and not union_aabb_stage.IsEmpty() and count > 0:
            size_stage = union_aabb_stage.GetSize()
            s = float(self._stage_mpu)
            self._last_size_m = (float(size_stage[0]) * s, float(size_stage[1]) * s, float(size_stage[2]) * s)
            self._last_count = count
        else:
            self._last_size_m = None
            self._last_count = 0

        # PART B: Distance
        self._last_dist_data = None
        if len(valid_prims) == 2:
            boxA = valid_prims[0][1]
            boxB = valid_prims[1][1]
            dx_stage, dy_stage, dz_stage, dist_stage = self._calculate_gap_vector(boxA, boxB)
            s = float(self._stage_mpu)
            self._last_dist_data = {
                "dist": dist_stage * s,
                "gap": (dx_stage * s, dy_stage * s, dz_stage * s)
            }

        self._update_all_labels()

    def _gap_1d(self, a_min, a_max, b_min, b_max):
        if a_max < b_min: return b_min - a_max
        if b_max < a_min: return a_min - b_max
        return 0.0

    def _calculate_gap_vector(self, boxA, boxB):
        mnA, mxA = boxA.GetMin(), boxA.GetMax()
        mnB, mxB = boxB.GetMin(), boxB.GetMax()
        dx = self._gap_1d(mnA[0], mxA[0], mnB[0], mxB[0])
        dy = self._gap_1d(mnA[1], mxA[1], mnB[1], mxB[1])
        dz = self._gap_1d(mnA[2], mxA[2], mnB[2], mxB[2])
        dist = math.sqrt(dx*dx + dy*dy + dz*dz)
        return dx, dy, dz, dist

    def _on_clear(self):
        self._last_size_m = None
        self._last_dist_data = None
        self._last_count = 0
        self._update_all_labels(clear=True)
        self._render_selected_paths([])

    # ---------------- display ----------------
    def _fmt(self, meters_value: float, mpu: float) -> float:
        return meters_value / mpu if mpu > 0 else meters_value

    def _precision_by_unit(self, unit_name: str) -> int:
        return {"mm": 1, "cm": 2, "m": 4, "inch": 2, "ft": 3}.get(unit_name, 3)

    def _update_all_labels(self, clear=False):
        # Size
        if clear or self._last_size_m is None:
            self._len_label.text = "X length: --"
            self._wid_label.text = "Y width : --"
            self._hei_label.text = "Z height: --"
        else:
            p = self._precision_by_unit(self._display_unit_size)
            mpu = self._display_mpu_size
            x = self._fmt(self._last_size_m[0], mpu)
            y = self._fmt(self._last_size_m[1], mpu)
            z = self._fmt(self._last_size_m[2], mpu)
            
            self._len_label.text = f"X length: {x:.{p}f} {self._display_unit_size}"
            self._wid_label.text = f"Y width : {y:.{p}f} {self._display_unit_size}"
            self._hei_label.text = f"Z height: {z:.{p}f} {self._display_unit_size}"

        # Distance
        if clear or self._last_dist_data is None:
            self._dist_main_label.text = "Dist: --"
            self._gap_x_label.text = "Gap X: --"
            self._gap_y_label.text = "Gap Y: --"
            self._gap_z_label.text = "Gap Z: --"
            
            paths = self._usd_context.get_selection().get_selected_prim_paths()
            if len(paths) == 0:
                self._dist_msg_label.text = "No selection"
                self._dist_msg_label.style = {"color": 0xAAFFFFFF}
            elif len(paths) != 2:
                self._dist_msg_label.text = f"Select exactly 2 objects"
                self._dist_msg_label.style = {"color": 0xFFAA00FF}
            else:
                self._dist_msg_label.text = "Objects have no bounds"
        else:
            self._dist_msg_label.text = "Distance Calculated"
            self._dist_msg_label.style = {"color": 0xFF00AA00}
            
            p = self._precision_by_unit(self._display_unit_dist)
            mpu = self._display_mpu_dist
            d = self._fmt(self._last_dist_data['dist'], mpu)
            gx = self._fmt(self._last_dist_data['gap'][0], mpu)
            gy = self._fmt(self._last_dist_data['gap'][1], mpu)
            gz = self._fmt(self._last_dist_data['gap'][2], mpu)

            self._dist_main_label.text = f"Dist: {d:.{p}f} {self._display_unit_dist}"
            self._gap_x_label.text = f"Gap X: {gx:.{p}f} {self._display_unit_dist}"
            self._gap_y_label.text = f"Gap Y: {gy:.{p}f} {self._display_unit_dist}"
            self._gap_z_label.text = f"Gap Z: {gz:.{p}f} {self._display_unit_dist}"

    def _copy_result(self, mode="size"):
        if not clipboard: return
        if mode == "size":
            txt = f"{self._len_label.text}\n{self._wid_label.text}\n{self._hei_label.text}"
        else:
            txt = f"{self._dist_main_label.text}\n{self._gap_x_label.text}\n{self._gap_y_label.text}\n{self._gap_z_label.text}"
        clipboard.copy(txt)