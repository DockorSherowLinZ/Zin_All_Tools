import omni.ext
import omni.ui as ui
import omni.ui.scene as sc
import omni.usd
import omni.timeline
from pxr import Usd, UsdGeom, UsdSkel, Gf, Sdf
import asyncio
import random
import statistics

# ==============================================================================
# MVVM View Model
# ==============================================================================
class HUDViewModel:
    """MVVM View Model holding all the observable data."""
    def __init__(self):
        self.aoi_status = ui.SimpleStringModel("IDLE")
        self.aoi_defect_rate = ui.SimpleFloatModel(0.0)
        self.aoi_title = ui.SimpleStringModel("AOI Inspection")
        self.robot_state = ui.SimpleStringModel("STANDBY")
        self.robot_title = ui.SimpleStringModel("Robot Arm")
        self.manual_station_name = ui.SimpleStringModel("Manual Assembly #1")
        self.manual_station_sub = ui.SimpleStringModel("Sub Title")
        self.manual_station_content = ui.SimpleStringModel("Content")
        self.manual_takt_label = ui.SimpleStringModel("Takt Time Remaining:")
        
        # Generic models for custom HUDs
        self.generic_title = ui.SimpleStringModel("Custom Item")
        self.generic_sub = ui.SimpleStringModel("Sub Title")
        self.generic_content = ui.SimpleStringModel("Status: Active")


# ==============================================================================
# HUD Engine
# ==============================================================================
class GrayboxHUDEngine:
    def __init__(self, ui_instance):
        self._hud_instances = {} 
        self.scene_view = None
        self._running = True
        self._update_sub = None
        self._ui_instance = ui_instance
        
        self._build_ui()
        self._scan_stage_and_build_huds()
        self._start_telemetry()

    def _build_ui(self):
        import omni.kit.viewport.utility
        import omni.ui.scene as sc
        import omni.ui as ui
        self.viewport_window = omni.kit.viewport.utility.get_active_viewport_window()
        
        if not self.viewport_window:
            self.viewport_window = ui.Window("DSX AI Factory - Phase 7 Graybox HUD", width=800, height=600)

        with self.viewport_window.get_frame("DSX_Phase7_HUD_Overlay"):
            self.scene_view = sc.SceneView()
            if hasattr(self.viewport_window, "viewport_api"):
                self.viewport_window.viewport_api.add_scene_view(self.scene_view)

    def _scan_stage_and_build_huds(self):
        import omni.usd
        from pxr import UsdGeom, Usd
        
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return
            
        with self.scene_view.scene:
            for prim in stage.Traverse():
                attr = prim.GetAttribute("machine_type")
                if attr and attr.IsValid():
                    m_type = attr.Get()
                    if m_type:
                        self._create_hud_for_prim(prim, str(m_type))
                        
    def rebuild_huds(self):
        if self.scene_view and self.scene_view.scene:
            self.scene_view.scene.clear()
        self._hud_instances.clear()
        self._scan_stage_and_build_huds()

    def _create_hud_for_prim(self, prim, m_type):
        import omni.ui as ui
        import omni.ui.scene as sc
        from pxr import UsdGeom, Usd
        
        prim_path = str(prim.GetPath())
        world_transform = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        purposes = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render]
        bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes)
        bbox = bbox_cache.ComputeWorldBound(prim)
        world_box = bbox.ComputeAlignedBox()
        
        if not world_box.IsEmpty():
            min_pt = world_box.GetMin()
            max_pt = world_box.GetMax()
            top_center = ((min_pt[0] + max_pt[0]) / 2.0, (min_pt[1] + max_pt[1]) / 2.0, max_pt[2])
            translation = list(top_center)
        else:
            translation = list(world_transform.ExtractTranslation())
            
        translation[2] += 80.0  # Z offset
        
        transform_matrix = [
            1, 0, 0, 0,
            0, 1, 0, 0,
            0, 0, 1, 0,
            translation[0], translation[1], translation[2], 1
        ]
        
        view_model = HUDViewModel()
        
        sub_title = ""
        content = ""
        takt_label = "Takt Time Remaining:"
        sub_attr = prim.GetAttribute("hud_sub_title")
        content_attr = prim.GetAttribute("hud_content")
        takt_label_attr = prim.GetAttribute("hud_takt_label")
        
        if sub_attr and sub_attr.IsValid():
            sub_title = str(sub_attr.Get())
        if content_attr and content_attr.IsValid():
            content = str(content_attr.Get())
        if takt_label_attr and takt_label_attr.IsValid():
            takt_label = str(takt_label_attr.Get())
            
        display_title = sub_title or m_type
        
        cycle_start, cycle_end = self._get_anim_cycle_frames(prim.GetStage(), prim_path)
        fps = prim.GetStage().GetTimeCodesPerSecond()
        cycle_len = cycle_end - cycle_start
        cycle_len_seconds = cycle_len / fps if cycle_len > 0.0 else 3.0
        
        if m_type == "AOI":
            view_model.aoi_title.set_value(display_title)
        elif m_type == "Robot":
            view_model.robot_title.set_value(display_title)
        elif m_type == "ManualStation":
            view_model.manual_station_name.set_value(m_type)
            view_model.manual_station_sub.set_value(sub_title)
            view_model.manual_station_content.set_value(content)
            view_model.manual_takt_label.set_value(takt_label)
        else:
            view_model.generic_title.set_value(m_type)
            view_model.generic_sub.set_value(sub_title)
            view_model.generic_content.set_value(content)
            
        show_dynamic = True
        show_static = True
        if self._ui_instance:
            if hasattr(self._ui_instance, "cb_dynamic"):
                show_dynamic = self._ui_instance.cb_dynamic.model.get_value_as_bool()
            if hasattr(self._ui_instance, "cb_static"):
                show_static = self._ui_instance.cb_static.model.get_value_as_bool()
                
        collapsed_transform = sc.Transform(transform=transform_matrix, look_at=sc.Transform.LookAt.CAMERA, visible=True)
        with collapsed_transform:
            collapsed_widget = sc.Widget(width=150, height=35)
            def build_collapsed(title=display_title, path=prim_path):
                def on_click(x, y, button, modifier, p=path):
                    if button == 0:
                        self.toggle_hud_state(p, expand=True)
                f = ui.Frame()
                f.set_mouse_pressed_fn(on_click)
                with f:
                    _stack = ui.ZStack()
                with _stack:
                        ui.Rectangle(style={"background_color": 0xCC1A1E24, "border_color": 0x8800FFFF, "border_width": 1})
                        ui.Label(title, style={"color": ui.color(0.0, 0.88, 1.0), "font_size": 16, "alignment": ui.Alignment.CENTER})
            collapsed_widget.frame.set_build_fn(build_collapsed)
            
        expanded_transform = sc.Transform(transform=transform_matrix, look_at=sc.Transform.LookAt.CAMERA, visible=False)
        with expanded_transform:
            expanded_widget = sc.Widget(width=300, height=240)
            
            if m_type == "AOI":
                builder = lambda vm=view_model, p=prim_path: self._build_aoi_ui(vm, p)
            elif m_type == "Robot":
                builder = lambda vm=view_model, p=prim_path: self._build_robot_ui(vm, p)
            elif m_type == "ManualStation":
                builder = lambda vm=view_model, p=prim_path: self._build_manual_station_ui(vm, p)
            else:
                builder = lambda vm=view_model, p=prim_path, sd=show_dynamic, ss=show_static: self._build_generic_ui(vm, p, sd, ss)
                
            expanded_widget.frame.set_build_fn(builder)

        self._hud_instances[prim_path] = {
            "view_model": view_model,
            "machine_type": m_type,
            "collapsed_transform": collapsed_transform,
            "expanded_transform": expanded_transform,
            "expanded_widget": expanded_widget,
            "cycle_start": cycle_start,
            "cycle_end": cycle_end,
            "cycle_len_seconds": cycle_len_seconds,
            "time_remaining": cycle_len_seconds,
            "is_expanded": False
        }

    def toggle_hud_state(self, prim_path, expand):
        if prim_path in self._hud_instances:
            instance = self._hud_instances[prim_path]
            instance["is_expanded"] = expand
            instance["collapsed_transform"].visible = not expand
            instance["expanded_transform"].visible = expand

    def _build_aoi_ui(self, view_model, prim_path):
        import omni.ui as ui
        def on_click(x, y, button, modifier, p=prim_path):
            if button == 0:
                self.toggle_hud_state(p, expand=False)
        f = ui.Frame()
        f.set_mouse_pressed_fn(on_click)
        with f:
            _stack = ui.ZStack()
        with _stack:
            ui.Rectangle(style={"background_color": 0xCC1A1E24, "border_color": 0xCC00FFFF, "border_width": 2, "border_radius": 5})
            with ui.HStack():
                ui.Spacer(width=25)
                with ui.VStack(spacing=5):
                    ui.Spacer(height=15)
                    ui.Label(view_model.aoi_title.get_value_as_string(), model=view_model.aoi_title, style={"color": 0xFF00FFFF, "font_size": 20, "alignment": ui.Alignment.CENTER})
                    with ui.HStack(height=1):
                        ui.Spacer(width=5)
                        ui.Rectangle(height=1, style={"background_color": ui.color(0.0, 0.8, 1.0, 0.30)})
                        ui.Spacer(width=5)
                    ui.Spacer(height=5)
                    with ui.HStack():
                        ui.Label("Status:", width=80, style={"color": 0xFFAAAAAA})
                        ui.Label(view_model.aoi_status.get_value_as_string(), model=view_model.aoi_status, style={"color": 0xFFFFFFFF})
                    with ui.HStack():
                        ui.Label("Defect %:", width=80, style={"color": 0xFFAAAAAA})
                        ui.FloatField(model=view_model.aoi_defect_rate, read_only=True, style={"color": 0xFFFFFFFF})
                    ui.Spacer(height=15)
                ui.Spacer(width=25)

    def _build_robot_ui(self, view_model, prim_path):
        import omni.ui as ui
        def on_click(x, y, button, modifier, p=prim_path):
            if button == 0:
                self.toggle_hud_state(p, expand=False)
        f = ui.Frame()
        f.set_mouse_pressed_fn(on_click)
        with f:
            _stack = ui.ZStack()
        with _stack:
            ui.Rectangle(style={"background_color": 0xCC1A1E24, "border_color": 0xCC00FFFF, "border_width": 2, "border_radius": 5})
            with ui.HStack():
                ui.Spacer(width=25)
                with ui.VStack(spacing=5):
                    ui.Spacer(height=15)
                    ui.Label(view_model.robot_title.get_value_as_string(), model=view_model.robot_title, style={"color": 0xFF00FFFF, "font_size": 20, "alignment": ui.Alignment.CENTER})
                    with ui.HStack(height=1):
                        ui.Spacer(width=5)
                        ui.Rectangle(height=1, style={"background_color": ui.color(0.0, 0.8, 1.0, 0.30)})
                        ui.Spacer(width=5)
                    ui.Spacer(height=5)
                    with ui.HStack():
                        ui.Label("State:", width=80, style={"color": 0xFFAAAAAA})
                        ui.Label(view_model.robot_state.get_value_as_string(), model=view_model.robot_state, style={"color": 0xFFFFFFFF})
                    ui.Spacer(height=15)
                ui.Spacer(width=25)

    def _build_manual_station_ui(self, view_model, prim_path):
        import omni.ui as ui
        def on_click(x, y, button, modifier, p=prim_path):
            if button == 0:
                self.toggle_hud_state(p, expand=False)
        f = ui.Frame()
        f.set_mouse_pressed_fn(on_click)
        with f:
            _stack = ui.ZStack()
        with _stack:
            ui.Rectangle(style={"background_color": ui.color(0.05, 0.05, 0.12, 0.85), "border_color": 0xCC00FFFF, "border_width": 2, "border_radius": 5})
            with ui.HStack():
                ui.Spacer(width=25)
                with ui.VStack(spacing=5):
                    ui.Spacer(height=15)
                    ui.Label(view_model.manual_station_name.get_value_as_string(), model=view_model.manual_station_name, style={"color": 0xFF00FFFF, "font_size": 22, "alignment": ui.Alignment.CENTER})
                    with ui.HStack(height=1):
                        ui.Spacer(width=5)
                        ui.Rectangle(height=1, style={"background_color": ui.color(0.0, 0.8, 1.0, 0.30)})
                        ui.Spacer(width=5)
                    ui.Label(view_model.manual_station_sub.get_value_as_string(), height=16, model=view_model.manual_station_sub, style={"color": 0xFFFFAA00, "font_size": 14, "alignment": ui.Alignment.CENTER})
                    ui.Label(view_model.manual_station_content.get_value_as_string(), height=16, model=view_model.manual_station_content, style={"color": 0xFFAAAAAA, "font_size": 14, "alignment": ui.Alignment.CENTER})
                    ui.Spacer(height=5)
                    ui.Label(view_model.manual_takt_label.get_value_as_string(), model=view_model.manual_takt_label, style={"color": 0xFFAAAAAA, "font_size": 14})
                    
                    view_model.current_progress_pct = 100.0
                    view_model.current_r = 0.0
                    view_model.current_g = 1.0
                    
                    view_model.progress_frame = ui.Frame()
                    
                    def build_progress_bar():
                        with ui.ZStack(height=20):
                            # 1. Background track
                            ui.Rectangle(style={"background_color": 0x44000000, "border_radius": 3})
                            
                            # 2. Animated Color Fill
                            with ui.HStack():
                                ui.Rectangle(
                                    width=ui.Percent(view_model.current_progress_pct),
                                    style={
                                        "background_color": ui.color(view_model.current_r, view_model.current_g, 0.0, 1.0),
                                        "border_radius": 3
                                    }
                                )
                                ui.Spacer(width=ui.Percent(100.0 - view_model.current_progress_pct))
                                
                            # 3. White Text Overlay
                            with ui.HStack():
                                ui.Spacer()
                                ui.Label(
                                    f"{view_model.current_progress_pct:.1f}%", 
                                    width=0,
                                    style={"color": 0xFFFFFFFF, "font_size": 14},
                                    alignment=ui.Alignment.RIGHT_CENTER
                                )
                                ui.Spacer(width=5)
                                
                    view_model.progress_frame.set_build_fn(build_progress_bar)
                    ui.Spacer(height=15)
                    ui.Spacer(height=15)
                ui.Spacer(width=25)

    def _build_generic_ui(self, view_model, prim_path, show_dynamic, show_static):
        import omni.ui as ui
        def on_click(x, y, button, modifier, p=prim_path):
            if button == 0:
                self.toggle_hud_state(p, expand=False)
        f = ui.Frame()
        f.set_mouse_pressed_fn(on_click)
        with f:
            _stack = ui.ZStack()
        with _stack:
            if show_dynamic or show_static:
                ui.Rectangle(style={"background_color": ui.color(0.1, 0.1, 0.15, 0.85), "border_color": 0xCC00FFFF, "border_width": 2, "border_radius": 5})
            with ui.HStack():
                ui.Spacer(width=15)
                with ui.VStack(spacing=5):
                    ui.Spacer(height=10)
                    if show_dynamic:
                        with ui.VStack(spacing=2):
                            ui.Label(view_model.generic_title.get_value_as_string(), height=22, model=view_model.generic_title, style={"color": 0xFF00FFFF, "font_size": 20, "weight": "bold"})
                            with ui.HStack(height=1):
                                ui.Spacer(width=5)
                                ui.Rectangle(height=1, style={"background_color": ui.color(0.0, 0.8, 1.0, 0.30)})
                                ui.Spacer(width=5)
                            ui.Spacer(height=3)
                            ui.Label(view_model.generic_sub.get_value_as_string(), height=16, model=view_model.generic_sub, style={"color": 0xFFFFAA00, "font_size": 14})
                            ui.Label(view_model.generic_content.get_value_as_string(), height=16, model=view_model.generic_content, style={"color": 0xFFAAAAAA, "font_size": 14})
                            ui.Spacer(height=5)
                            ui.Line(style={"color": 0xFF444444, "border_width": 1})
                            ui.Spacer(height=5)
                    if show_static:
                        with ui.VStack(spacing=2):
                            ui.Label("Factory Info", height=16, style={"color": 0xFF00AAFF, "font_size": 14, "weight": "bold"})
                            ui.Spacer(height=3)
                            with ui.HStack(height=16):
                                ui.Label("Asset Class:", width=90, style={"color": 0xFF888888, "font_size": 12})
                                ui.Label(view_model.generic_title.get_value_as_string(), model=view_model.generic_title, style={"color": 0xFFDDDDDD, "font_size": 12})
                            with ui.HStack(height=16):
                                ui.Label("Model No:", width=90, style={"color": 0xFF888888, "font_size": 12})
                                ui.Label(view_model.generic_sub.get_value_as_string(), model=view_model.generic_sub, style={"color": 0xFFDDDDDD, "font_size": 12})
                            with ui.HStack(height=16):
                                ui.Label("Status:", width=90, style={"color": 0xFF888888, "font_size": 12})
                                ui.Label("Active", style={"color": 0xFF44AA44, "font_size": 12})
                    ui.Spacer(height=10)
                ui.Spacer(width=15)

    def _get_anim_cycle_frames(self, stage, prim_path):
        import omni.usd
        from pxr import Usd, UsdGeom, Gf
        
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return (0.0, 3.0 * stage.GetTimeCodesPerSecond())

        anim_target_attr = prim.GetAttribute("aif:core:animationTarget")
        if anim_target_attr and anim_target_attr.IsValid():
            explicit_target = anim_target_attr.Get()
            if explicit_target and str(explicit_target).strip():
                redirect_path = str(explicit_target).strip()
                target_prim = stage.GetPrimAtPath(redirect_path)
                if target_prim and target_prim.IsValid():
                    prim = target_prim

        xform_bounds = []
        xform_transform_attrs = []
        try:
            for p in Usd.PrimRange(prim):
                xformable = UsdGeom.Xformable(p)
                if xformable:
                    for op in xformable.GetOrderedXformOps():
                        attr = op.GetAttr()
                        if attr and attr.HasAuthoredValue():
                            samples = attr.GetTimeSamples()
                            if samples and len(samples) >= 2:
                                xform_bounds.append((float(samples[0]), float(samples[-1]), len(samples), attr.GetName()))
                                if attr.GetName() == "xformOp:transform":
                                    xform_transform_attrs.append({
                                        "prim_path": str(p.GetPath()),
                                        "attr": attr,
                                        "samples": samples,
                                    })
        except Exception as e:
            pass

        if xform_bounds:
            start = min(b[0] for b in xform_bounds)
            end = max(b[1] for b in xform_bounds)
            total_span = end - start
            if 0 < total_span <= 2000:
                return (start, end)

        if xform_transform_attrs:
            best_attr_info = max(xform_transform_attrs, key=lambda x: len(x["samples"]))
            attr = best_attr_info["attr"]
            sample_times = list(best_attr_info["samples"])

            stage_start = stage.GetStartTimeCode()
            ref_idx = 0
            for idx, t in enumerate(sample_times):
                if t >= stage_start:
                    ref_idx = idx
                    break

            check_count = min(len(sample_times), 3000)
            cycle_frame_idx = None

            try:
                ref_matrix = attr.Get(sample_times[ref_idx])
                if ref_matrix is not None and hasattr(ref_matrix, 'GetRow'):
                    min_search_idx = ref_idx + 15
                    for i in range(min_search_idx, check_count):
                        test_matrix = attr.Get(sample_times[i])
                        if test_matrix is not None:
                            diff = 0.0
                            for r in range(4):
                                row1 = ref_matrix.GetRow(r)
                                row2 = test_matrix.GetRow(r)
                                for c in range(4):
                                    diff += abs(row1[c] - row2[c])
                            if diff < 1e-4:
                                cycle_frame_idx = i
                                break
            except Exception as e:
                pass

            if cycle_frame_idx:
                start = sample_times[ref_idx]
                end = sample_times[cycle_frame_idx]
                if end > start:
                    return (start, end)

        fallback_start = 0.0
        fallback_end = 3.0 * stage.GetTimeCodesPerSecond()
        return (fallback_start, fallback_end)

    def _start_telemetry(self):
        import omni.kit.app
        self._update_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(self._on_update)

    def _on_update(self, event):
        import random
        import omni.usd
        import omni.timeline
        
        if not self._running:
            return

        dt = event.payload.get("dt", 0.0)

        context = omni.usd.get_context()
        stage = context.get_stage()
        
        if stage:
            timeline = omni.timeline.get_timeline_interface()
            fps = stage.GetTimeCodesPerSecond()
            current_frame = timeline.get_current_time() * fps
            
            for prim_path, instance in self._hud_instances.items():
                vm = instance["view_model"]
                m_type = instance["machine_type"]
                
                if m_type == "ManualStation":
                    cycle_len_sec = instance.get("cycle_len_seconds", 3.0)
                    time_rem = instance.get("time_remaining", cycle_len_sec)
                    
                    # 1. Delta Time Countdown
                    time_rem -= dt
                    if time_rem <= 0.0:
                        time_rem = cycle_len_sec
                        
                    instance["time_remaining"] = time_rem
                    progress_pct = max(0.0, min(100.0, (time_rem / cycle_len_sec) * 100.0))
                        
                    # Color logic: Green(100) -> Yellow(50) -> Red(0)
                    if progress_pct > 50:
                        r = max(0.0, min(1.0, (100.0 - progress_pct) / 50.0))
                        g = 1.0
                    else:
                        r = 1.0
                        g = max(0.0, min(1.0, progress_pct / 50.0))
                        
                    # Store values and forcefully rebuild the UI frame
                    vm.current_progress_pct = progress_pct
                    vm.current_r = r
                    vm.current_g = g
                    
                    if hasattr(vm, "progress_frame") and vm.progress_frame:
                        vm.progress_frame.rebuild()
                        
                elif m_type == "AOI":
                    # Update these less frequently to avoid flickering, e.g. based on frame count or time, but keeping random logic for now
                    vm.aoi_status.set_value(random.choice(["INSPECTING", "PASS", "FAIL"]))
                    vm.aoi_defect_rate.set_value(random.uniform(0.0, 5.0))
                        
                elif m_type == "Robot":
                    vm.robot_state.set_value(random.choice(["MOVING", "WELDING", "IDLE"]))

            # Force UI engine to wake up and redraw sc.Widget texture
            try:
                import omni.appwindow
                app_win = omni.appwindow.get_default_app_window()
                if app_win:
                    pos = app_win.get_mouse_position()
                    app_win.post_mouse_move_event(pos[0], pos[1])
            except Exception:
                pass

    def destroy(self):
        self._running = False
        self._update_sub = None
        self._hud_instances.clear()
        
        if self.scene_view:
            if self.scene_view.scene:
                self.scene_view.scene.clear()
            
            if self.viewport_window:
                if hasattr(self.viewport_window, "viewport_api"):
                    try:
                        self.viewport_window.viewport_api.remove_scene_view(self.scene_view)
                    except Exception:
                        pass
        self.scene_view = None


# ==============================================================================
# Zin Tools Box UI Interface
# ==============================================================================
class SmartHudUI:
    """
    UI Class managed by Zin Tools Box.
    Handles the toggle logic for the HUD Engine and Metadata configuration.
    """
    
    # Define styles locally to ensure they render correctly even inside nested frames
    _STYLE_DEFAULT = {
        "Button": {"background_color": 0xFF343432, "border_radius": 4, "margin": 2},
        "Button:hovered": {"background_color": 0xFF4A4A48},
        "Button:pressed": {"background_color": 0xFF5A5A58},
    }
    _STYLE_CORRECT = {
        "Button": {"background_color": 0xFF2A5E2A, "border_radius": 4, "margin": 2},
        "Button:hovered": {"background_color": 0xFF33703A},
        "Button:pressed": {"background_color": 0xFF44AA44},
    }
    _STYLE_ERROR = {
        "Button": {"background_color": 0xFF5E2A2A, "border_radius": 4, "margin": 2},
        "Button:hovered": {"background_color": 0xFF703333},
        "Button:pressed": {"background_color": 0xFFAA4444},
    }

    def __init__(self):
        self.engine = None
        self.is_enabled = False
        
        # Subscribe to stage events to auto-disable HUD on stage change
        import omni.usd
        event_stream = omni.usd.get_context().get_stage_event_stream()
        self._stage_event_subs = [
            event_stream.create_subscription_to_pop_by_type(int(omni.usd.StageEventType.CLOSING), self._on_stage_event),
            event_stream.create_subscription_to_pop_by_type(int(omni.usd.StageEventType.CLOSED), self._on_stage_event),
            event_stream.create_subscription_to_pop_by_type(int(omni.usd.StageEventType.OPENED), self._on_stage_event)
        ]

    def _on_stage_event(self, event):
        """Safely shuts down the HUD engine if the stage changes to prevent orphaned viewports/overlays."""
        if self.is_enabled:
            print(f"[Smart HUD] Stage event detected (type {event.type}). Disabling HUD.")
            self.is_enabled = False
            if self.engine:
                self.engine.destroy()
                self.engine = None
            if hasattr(self, "toggle_btn") and self.toggle_btn:
                try:
                    self.toggle_btn.text = "Turn ON"
                    self.toggle_btn.set_style(self._STYLE_CORRECT)
                except Exception:
                    pass

    def build_ui(self):
        """Builds the 2D control panel inside the Zin Tools Box."""
        with ui.VStack(spacing=2):
            
            with ui.HStack(height=30, spacing=10):
                # Toggle Button
                button_text = "Turn OFF" if self.is_enabled else "Turn ON"
                button_style = self._STYLE_ERROR if self.is_enabled else self._STYLE_CORRECT
                
                self.toggle_btn = ui.Button(
                    button_text, 
                    style=button_style,
                    clicked_fn=self._on_toggle_clicked
                )
                
                ui.Button(
                    "Generate Test Graybox Scene",
                    style=self._STYLE_DEFAULT,
                    clicked_fn=self._create_test_scene,
                    tooltip="Creates 3 Graybox test machines with 'machine_type' attributes properly configured."
                )

            ui.Spacer(height=10)
            
            with ui.CollapsableFrame("Add / Edit HUD Metadata", collapsed=False, style={"font_size": 16, "color": 0xFFFFFFFF}):
                with ui.VStack(spacing=2, padding=6):
                    ui.Label("Add custom attributes to make selected models compatible with HUD and Info Panel:", 
                             style={"color": 0xFFAAAAAA, "font_size": 14})
                    
                    with ui.HStack(height=24, spacing=10):
                        ui.Label("Topic (Machine Type):", width=140, style={"color": 0xFFDDDDDD}, tooltip="Will be written to 'aif:core:assetClass' and displayed as 'Asset Class' in Factory Info.")
                        self._topic_options = ["ManualStation", "AOI", "Robot"]
                        self.topic_combo = ui.ComboBox(0, *self._topic_options, style={"color": 0xFFDDDDDD})
                        
                    with ui.HStack(height=24, spacing=10):
                        ui.Label("Subject (Sub Title):", width=140, style={"color": 0xFFDDDDDD}, tooltip="Will be written to 'aif:core:modelNumber' and displayed as 'Model No' in Factory Info.")
                        self.subject_field = ui.StringField(style={"color": 0xFFDDDDDD})
                        self.subject_field.model.set_value("S01")
                        
                    with ui.HStack(height=24, spacing=10):
                        ui.Label("Content:", width=140, style={"color": 0xFFDDDDDD}, tooltip="Will be written to 'aif:core:assetDescription'. Status is hardcoded to 'Active' for demo.")
                        self.content_field = ui.StringField(style={"color": 0xFFDDDDDD})
                        self.content_field.model.set_value("Chassis")
                        
                    with ui.HStack(height=24, spacing=10):
                        ui.Label("Takt Label:", width=140, style={"color": 0xFFDDDDDD}, tooltip="Will be written to 'hud_takt_label'.")
                        self.takt_label_field = ui.StringField(style={"color": 0xFFDDDDDD})
                        self.takt_label_field.model.set_value("Takt Time Remaining:")
                    
                    ui.Spacer(height=5)
                    with ui.HStack(spacing=10, height=30):
                        ui.Button(
                            "Add / Update",
                            style=self._STYLE_CORRECT,
                            clicked_fn=self._apply_attributes_to_selected,
                            tooltip="Adds or updates HUD and AIF metadata attributes for selected models."
                        )
                        ui.Button(
                            "Remove",
                            style=self._STYLE_ERROR,
                            clicked_fn=self._remove_attributes_from_selected,
                            tooltip="Removes HUD attributes from selected models."
                        )
                        
            ui.Spacer(height=10)
            with ui.CollapsableFrame("Animation Binding", collapsed=False, style={"font_size": 16, "color": 0xFFFFFFFF}):
                with ui.VStack(spacing=2, padding=6):
                    ui.Label("Bind HUD progress to a specific animated character (optional):", style={"color": 0xFFAAAAAA, "font_size": 13})
                    with ui.HStack(height=24, spacing=10):
                        ui.Label("Anim Target:", width=90, style={"color": 0xFFDDDDDD}, tooltip="Absolute path to the animated prim. Used to sync the progress bar.")
                        self.anim_target_field = ui.StringField(style={"color": 0xFFDDDDDD})
                        self.anim_target_field.model.set_value("/World/IMX_Factory_After/ASSET/asset_IMX_Factory_After_v2/Lifting_4/Scene1")
                    ui.Button(
                        "Bind to Selected",
                        height=24,
                        style=self._STYLE_DEFAULT,
                        clicked_fn=self._bind_animation_target,
                        tooltip="Writes 'aif:core:animationTarget' to the selected prims."
                    )

            ui.Spacer(height=10)
            with ui.CollapsableFrame("Display Settings", collapsed=False, style={"font_size": 16, "color": 0xFFFFFFFF}):
                with ui.VStack(spacing=2, padding=6):
                    ui.Label("Select information to display on the HUD overlay:", style={"color": 0xFFAAAAAA, "font_size": 13})
                    
                    with ui.HStack(height=22, spacing=6):
                        self.cb_dynamic = ui.CheckBox(width=18, height=18)
                        self.cb_dynamic.model.set_value(True)
                        self.cb_dynamic.model.add_value_changed_fn(self._on_display_setting_changed)
                        ui.Label("Dynamic HUD Status", style={"color": 0xFFDDDDDD, "font_size": 13})

                    with ui.HStack(height=22, spacing=6):
                        self.cb_static = ui.CheckBox(width=18, height=18)
                        self.cb_static.model.set_value(True)
                        self.cb_static.model.add_value_changed_fn(self._on_display_setting_changed)
                        ui.Label("Factory Info (Metadata)", style={"color": 0xFFDDDDDD, "font_size": 13})

            ui.Spacer()

    def _on_display_setting_changed(self, model):
        # Notify the engine to rebuild HUDs to reflect the new display settings
        if self.is_enabled and self.engine:
            self.engine.rebuild_huds()

    def _bind_animation_target(self):
        """Writes 'aif:core:animationTarget' to selected prims."""
        import omni.usd
        from pxr import Sdf
        
        context = omni.usd.get_context()
        stage = context.get_stage()
        if not stage:
            print("[Smart HUD] ❌ Error: No USD stage is currently open.")
            return

        selection = context.get_selection().get_selected_prim_paths()
        if not selection:
            print("[Smart HUD] ⚠️ No models selected. Please select a model in the stage first.")
            return

        target_path = self.anim_target_field.model.get_value_as_string().strip()
        if not target_path:
            print("[Smart HUD] ⚠️ Anim Target field is empty.")
            return

        for path in selection:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue

            attr = prim.GetAttribute("aif:core:animationTarget")
            if not attr:
                attr = prim.CreateAttribute("aif:core:animationTarget", Sdf.ValueTypeNames.String)
            attr.Set(target_path)
            print(f"[Smart HUD] ✅ Bound animationTarget = '{target_path}' on {path}")

    def _apply_attributes_to_selected(self):
        import omni.usd
        from pxr import Sdf
        
        context = omni.usd.get_context()
        stage = context.get_stage()
        if not stage:
            print("[Smart HUD] ❌ Error: No USD stage is currently open.")
            return

        selection = context.get_selection().get_selected_prim_paths()
        if not selection:
            print("[Smart HUD] ⚠️ No models selected. Please select a model in the stage first.")
            return

        idx = self.topic_combo.model.get_item_value_model().get_value_as_int()
        topic = self._topic_options[idx] if 0 <= idx < len(self._topic_options) else "ManualStation"
        subject = self.subject_field.model.get_value_as_string()
        content = self.content_field.model.get_value_as_string()
        takt_label = self.takt_label_field.model.get_value_as_string()

        for path in selection:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue

            # 1. Add smart_hud attributes
            attr_type = prim.GetAttribute("machine_type")
            if not attr_type: attr_type = prim.CreateAttribute("machine_type", Sdf.ValueTypeNames.String)
            attr_type.Set(topic)
            
            attr_sub = prim.GetAttribute("hud_sub_title")
            if not attr_sub: attr_sub = prim.CreateAttribute("hud_sub_title", Sdf.ValueTypeNames.String)
            attr_sub.Set(subject)
            
            attr_cont = prim.GetAttribute("hud_content")
            if not attr_cont: attr_cont = prim.CreateAttribute("hud_content", Sdf.ValueTypeNames.String)
            attr_cont.Set(content)
            
            attr_takt = prim.GetAttribute("hud_takt_label")
            if not attr_takt: attr_takt = prim.CreateAttribute("hud_takt_label", Sdf.ValueTypeNames.String)
            attr_takt.Set(takt_label)

            # 2. Add smart_info_panel attributes (aif:core and aif:spec)
            # 遵循 AIF Pipeline Samples 綁定規範 (AIF-MANAGED, Locked)
            aif_attrs = {
                "aif:core:assetClass": {
                    "value": topic, 
                    "doc": "Class of AI Factory Equipment"
                },
                "aif:core:modelNumber": {
                    "value": subject, 
                    "doc": "Equipment model number"
                },
                "aif:core:manufacturer": {
                    "value": "Inventec", 
                    "doc": "Equipment manufacturer name"
                },
                "aif:core:assetDescription": {
                    "value": content, 
                    "doc": "Human Readable Description of Asset"
                },
                "aif:spec:status": {
                    "value": "Active", 
                    "doc": "Current status of the equipment"
                }
            }

            for attr_name, attr_info in aif_attrs.items():
                attr = prim.GetAttribute(attr_name)
                
                # Unlock existing locked attribute before writing
                if attr and attr.IsValid():
                    existing_cd = attr.GetCustomData()
                    if existing_cd.get('omni', {}).get('kit', {}).get('locked', False):
                        unlocked_cd = dict(existing_cd)
                        unlocked_cd['omni'] = dict(unlocked_cd.get('omni', {}))
                        unlocked_cd['omni']['kit'] = dict(unlocked_cd['omni'].get('kit', {}))
                        unlocked_cd['omni']['kit']['locked'] = False
                        attr.SetCustomData(unlocked_cd)
                
                if not attr or not attr.IsValid():
                    attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.String)
                attr.Set(attr_info["value"])
                
                # AIF 規範：加入 [AIF-MANAGED] 標籤與鎖定屬性
                managed_doc = f"{attr_info['doc']} [AIF-MANAGED]"
                attr.SetDocumentation(managed_doc)
                
                custom_data = {
                    'omni': {
                        'kit': {
                            'locked': True
                        }
                    }
                }
                attr.SetCustomData(custom_data)
                
            print(f"[Smart HUD] ✅ Applied HUD and AIF-MANAGED attributes to {path}")
            
        if self.is_enabled and self.engine:
            self.engine.rebuild_huds()

    def _remove_attributes_from_selected(self):
        import omni.usd
        
        context = omni.usd.get_context()
        stage = context.get_stage()
        if not stage: return

        selection = context.get_selection().get_selected_prim_paths()
        if not selection: return

        attrs_to_remove = [
            "machine_type", "hud_sub_title", "hud_content", "hud_takt_label",
            "aif:core:assetClass", "aif:core:modelNumber", 
            "aif:core:manufacturer", "aif:core:assetDescription", 
            "aif:spec:status"
        ]

        for path in selection:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid(): continue
            
            for attr_name in attrs_to_remove:
                prim.RemoveProperty(attr_name)
                
            print(f"[Smart HUD] 🗑️ Removed HUD and Info Panel attributes from {path}")

    def _create_test_scene(self):
        import omni.usd
        from pxr import UsdGeom, Sdf, Gf
        
        stage = omni.usd.get_context().get_stage()
        if not stage:
            print("[Smart HUD] ❌ Error: No USD stage is currently open. Please create or open a stage first.")
            return

        machines = {
            "AOI": Gf.Vec3d(0, 0, 100),
            "Robot": Gf.Vec3d(300, 0, 100),
            "ManualStation": Gf.Vec3d(-300, 0, 100)
        }

        world_path = "/World"
        if not stage.GetPrimAtPath(world_path):
            UsdGeom.Xform.Define(stage, world_path)

        for m_type, pos in machines.items():
            path = f"{world_path}/Graybox_{m_type}"
            cube = UsdGeom.Cube.Define(stage, path)
            
            # Set realistic size (e.g., 200 cm)
            cube.GetSizeAttr().Set(200.0)
            
            # Set position using XformCommonAPI to avoid appending multiple ops
            xform_api = UsdGeom.XformCommonAPI(cube)
            xform_api.SetTranslate(pos)
            
            # Add the custom 'machine_type' attribute
            prim = cube.GetPrim()
            attr = prim.GetAttribute("machine_type")
            if not attr:
                attr = prim.CreateAttribute("machine_type", Sdf.ValueTypeNames.String)
            attr.Set(m_type)
            
            print(f"[Smart HUD] Created {m_type} at {path}")

    def _on_toggle_clicked(self):
        self.is_enabled = not self.is_enabled
        
        if self.is_enabled:
            self.toggle_btn.text = "Turn OFF"
            self.toggle_btn.set_style(self._STYLE_ERROR)
            if not self.engine:
                self.engine = GrayboxHUDEngine(self)
        else:
            self.toggle_btn.text = "Turn ON"
            self.toggle_btn.set_style(self._STYLE_CORRECT)
            if self.engine:
                self.engine.destroy()
                self.engine = None

    def shutdown(self):
        """Called by ToolsBox on extension shutdown"""
        if self.engine:
            self.engine.destroy()
            self.engine = None
        self.is_enabled = False
        
        # Clear stage event subscriptions
        self._stage_event_subs = []
