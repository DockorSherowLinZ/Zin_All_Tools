import omni.ext
import omni.ui as ui
import omni.ui.scene as sc
import omni.usd
import omni.timeline
from pxr import Usd, UsdGeom, UsdSkel, Gf, Sdf
import random
import statistics
import sys
import os

# Ensure tools_box is accessible
_tools_box_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../tools_box"))
if _tools_box_path not in sys.path:
    sys.path.append(_tools_box_path)
    
import tools_box.zin_ui_utils as zin_ui_utils

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
        self.manual_station_sub = ui.SimpleStringModel("Station")
        self.manual_station_content = ui.SimpleStringModel("Description")
        self.manual_takt_label = ui.SimpleStringModel("Process:")
        
        # Generic models for custom HUDs
        self.generic_title = ui.SimpleStringModel("Custom Item")
        self.generic_sub = ui.SimpleStringModel("Station")
        self.generic_content = ui.SimpleStringModel("Description")
        
        # Progress bar state
        self.current_progress_pct = 100.0
        self.current_r = 0.0
        self.current_g = 1.0
        self.progress_text = ui.SimpleStringModel("100.0%")
        self.collapsed_progress_frame = None
        self.expanded_progress_frame = None
        
        # Animation binding debug info
        self.bind_status = "N/A"      # "Success" or "Fallback"
        self.bind_target = ""          # resolved target prim path
        self.bind_cycle_len = 0.0      # detected cycle length in frames
        self.bind_is_manual = False    # True if using manual cycle override


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

        overlay_frame = self.viewport_window.get_frame("DSX_Phase7_HUD_Overlay")
        # Ensure the overlay does not trap keyboard focus from the viewport
        if hasattr(overlay_frame, "prevent_focus_on_click"):
            overlay_frame.prevent_focus_on_click = True
            
        with overlay_frame:
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
        takt_label = "Process:"
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
        
        cycle_info = self._get_anim_cycle_frames(prim.GetStage(), prim_path)
        cycle_start = cycle_info["start"]
        cycle_end = cycle_info["end"]
        fps = prim.GetStage().GetTimeCodesPerSecond()
        cycle_len = cycle_end - cycle_start
        cycle_len_seconds = cycle_len / fps if cycle_len > 0.0 else 3.0
        
        # Store binding debug info on the view model
        view_model.bind_status = cycle_info["status"]
        view_model.bind_target = cycle_info["target_path"]
        view_model.bind_cycle_len = cycle_len
        
        print(f"[Smart HUD] 🔍 {prim_path}: bind_status={cycle_info['status']}, "
              f"target={cycle_info['target_path']}, "
              f"cycle=[{cycle_start:.0f} → {cycle_end:.0f}] ({cycle_len:.0f} frames), "
              f"attrs_scanned={cycle_info['attrs_scanned']}, samples_found={cycle_info['samples_found']}")
        
        if m_type == "Machine":
            view_model.aoi_title.set_value(display_title)
        elif m_type == "Robot Station":
            view_model.robot_title.set_value(display_title)
        elif m_type == "Human Station":
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
            collapsed_widget = sc.Widget(width=150, height=55 if m_type == "Human Station" else 35)
            def build_collapsed(title=display_title, path=prim_path, m=m_type, vm=view_model):
                def on_click(x, y, button, modifier, p=path):
                    if button == 0:
                        self.toggle_hud_state(p, expand=True)
                    return False
                f = ui.Frame(style={"Frame:hovered": {"background_color": 0x00000000}}, prevent_focus_on_click=True)
                f.set_mouse_pressed_fn(on_click)
                with f:
                    _stack = ui.ZStack()
                with _stack:
                        ui.Rectangle(style={"background_color": 0xCC1A1E24, "border_color": 0x8800FFFF, "border_width": 1})
                        if m == "Human Station":
                            with ui.VStack(spacing=2):
                                ui.Spacer(height=4)
                                ui.Label(title, height=18, style={"color": ui.color(0.0, 0.88, 1.0), "font_size": 14, "alignment": ui.Alignment.CENTER})
                                with ui.HStack():
                                    ui.Spacer(width=5)
                                    pf = ui.Frame(height=16)
                                    vm.collapsed_progress_frame = pf
                                    pf.set_build_fn(lambda v=vm: self._build_progress_bar_widget(v, height=14, font_size=10))
                                    ui.Spacer(width=5)
                                ui.Spacer(height=4)
                        else:
                            ui.Label(title, style={"color": ui.color(0.0, 0.88, 1.0), "font_size": 16, "alignment": ui.Alignment.CENTER})
            collapsed_widget.frame.set_build_fn(build_collapsed)
            
        expanded_transform = sc.Transform(transform=transform_matrix, look_at=sc.Transform.LookAt.CAMERA, visible=False)
        with expanded_transform:
            scale = 1.0
            if self._ui_instance and hasattr(self._ui_instance, "hud_scale_model"):
                scale = self._ui_instance.hud_scale_model.as_float
                
            scale_matrix = [
                scale, 0, 0, 0,
                0, scale, 0, 0,
                0, 0, scale, 0,
                0, 0, 0, 1
            ]
            scale_transform = sc.Transform(transform=scale_matrix)
            
            with scale_transform:
                expanded_widget = sc.Widget(width=300, height=280)
                
                if m_type == "Machine":
                    builder = lambda vm=view_model, p=prim_path: self._build_aoi_ui(vm, p)
                elif m_type == "Robot Station":
                    builder = lambda vm=view_model, p=prim_path: self._build_robot_ui(vm, p)
                elif m_type == "Human Station":
                    builder = lambda vm=view_model, p=prim_path: self._build_manual_station_ui(vm, p)
                else:
                    builder = lambda vm=view_model, p=prim_path, sd=show_dynamic, ss=show_static: self._build_generic_ui(vm, p, sd, ss)
                    
                expanded_widget.frame.set_build_fn(builder)

        self._hud_instances[prim_path] = {
            "view_model": view_model,
            "machine_type": m_type,
            "collapsed_transform": collapsed_transform,
            "expanded_transform": expanded_transform,
            "scale_transform": scale_transform,
            "collapsed_widget": collapsed_widget,
            "expanded_widget": expanded_widget,
            "cycle_start": cycle_start,
            "cycle_end": cycle_end,
            "cycle_len_seconds": cycle_len_seconds,
            "time_remaining": cycle_len_seconds,
            "is_expanded": False
        }

    def _build_progress_bar_widget(self, view_model, height=20, font_size=14):
        import omni.ui as ui
        # Clear stale references — this method is called on every frame.rebuild()
        if not hasattr(view_model, "progress_bars"):
            view_model.progress_bars = []
        else:
            view_model.progress_bars.clear()
            
        with ui.ZStack(height=height):
            # 1. Background track
            ui.Rectangle(style={"background_color": 0x44000000, "border_radius": 3})
            
            # 2. Animated Color Fill
            with ui.HStack():
                fill = ui.Rectangle(
                    width=ui.Percent(view_model.current_progress_pct),
                    style={
                        "background_color": ui.color(view_model.current_r, view_model.current_g, 0.0, 1.0),
                        "border_radius": 3
                    }
                )
                spacer = ui.Spacer(width=ui.Percent(100.0 - view_model.current_progress_pct))
                
            # 3. White Text Overlay
            with ui.HStack():
                ui.Spacer()
                label = ui.Label(
                    view_model.progress_text.get_value_as_string(), 
                    model=view_model.progress_text,
                    width=0,
                    style={"color": 0xFFFFFFFF, "font_size": font_size},
                    alignment=ui.Alignment.RIGHT_CENTER
                )
                ui.Spacer(width=5)
                
            view_model.progress_bars.append({
                "fill": fill,
                "spacer": spacer,
                "label": label
            })

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
            return False
        f = ui.Frame(style={"Frame:hovered": {"background_color": 0x00000000}}, prevent_focus_on_click=True)
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
            return False
        f = ui.Frame(style={"Frame:hovered": {"background_color": 0x00000000}}, prevent_focus_on_click=True)
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
            return False
        f = ui.Frame(style={"Frame:hovered": {"background_color": 0x00000000}}, prevent_focus_on_click=True)
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
                    
                    pf = ui.Frame(height=20)
                    view_model.expanded_progress_frame = pf
                    pf.set_build_fn(lambda vm=view_model: self._build_progress_bar_widget(vm, height=20, font_size=14))
                    
                    ui.Spacer(height=15)
                    ui.Spacer(height=15)
                ui.Spacer(width=25)

    def _build_generic_ui(self, view_model, prim_path, show_dynamic, show_static):
        import omni.ui as ui
        def on_click(x, y, button, modifier, p=prim_path):
            if button == 0:
                self.toggle_hud_state(p, expand=False)
            return False
        f = ui.Frame(style={"Frame:hovered": {"background_color": 0x00000000}}, prevent_focus_on_click=True)
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
        """Ultimate animation cycle detection.
        
        Strategy:
          1. Resolve aif:core:animationTarget redirect
          2. Recursively scan target prim + descendants for any attr with
             GetNumTimeSamples() > 1, aggregate min/max time codes
          3. Follow skel:animationSource / skel:skeleton relationships
          4. If no time samples found, check referenced layers for
             layer.startTimeCode / layer.endTimeCode
          5. Final fallback: stage time range (marks status as Failed)
        
        Returns a dict: {start, end, status, target_path, attrs_scanned, samples_found}
        """
        import omni.usd
        from pxr import Usd, UsdGeom, Gf, Sdf
        
        fps = stage.GetTimeCodesPerSecond()
        fallback = {
            "start": stage.GetStartTimeCode(),
            "end": stage.GetEndTimeCode(),
            "status": "Failed",
            "target_path": "",
            "attrs_scanned": 0,
            "samples_found": 0,
        }
        
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return fallback

        # --- Step 0: Check for manual cycle length override ---
        custom_cycle_attr = prim.GetAttribute("hud_custom_cycle_length")
        if custom_cycle_attr and custom_cycle_attr.IsValid():
            custom_val = custom_cycle_attr.Get()
            if custom_val is not None and int(custom_val) > 0:
                custom_frames = int(custom_val)
                stage_start = stage.GetStartTimeCode()
                print(f"[Smart HUD] 🎯 Manual cycle override: {custom_frames} frames on {prim_path}")
                return {
                    "start": stage_start,
                    "end": stage_start + float(custom_frames),
                    "status": "Manual Override",
                    "target_path": str(prim.GetPath()),
                    "attrs_scanned": 0,
                    "samples_found": 0,
                }

        # --- Step 1: Resolve the animation target redirect ---
        resolved_target = ""
        anim_target_attr = prim.GetAttribute("aif:core:animationTarget")
        if anim_target_attr and anim_target_attr.IsValid():
            explicit_target = anim_target_attr.Get()
            if explicit_target and str(explicit_target).strip():
                redirect_path = str(explicit_target).strip()
                target_prim = stage.GetPrimAtPath(redirect_path)
                if target_prim and target_prim.IsValid():
                    prim = target_prim
                    resolved_target = redirect_path
                else:
                    print(f"[Smart HUD] ⚠️ animationTarget '{redirect_path}' not found on stage")
                    fallback["target_path"] = f"{redirect_path} (NOT FOUND)"
                    return fallback

        if not resolved_target:
            resolved_target = str(prim.GetPath())

        # --- Step 2: Collect all prims to scan ---
        prims_to_check = set()
        try:
            for p in Usd.PrimRange(prim):
                prims_to_check.add(p)
                
                # Follow skeleton/animation relationships
                for rel_name in ["skel:animationSource", "skel:skeleton"]:
                    rel = p.GetRelationship(rel_name)
                    if rel and rel.IsValid():
                        for t in rel.GetTargets():
                            src_prim = stage.GetPrimAtPath(t)
                            if src_prim and src_prim.IsValid():
                                for sp in Usd.PrimRange(src_prim):
                                    prims_to_check.add(sp)
        except Exception:
            pass

        # --- Step 3: Scan using GetNumTimeSamples (most robust) ---
        anim_bounds = []
        attrs_scanned = 0
        samples_found = 0
        try:
            for p in prims_to_check:
                for attr in p.GetAttributes():
                    attrs_scanned += 1
                    num_samples = attr.GetNumTimeSamples()
                    if num_samples > 1:
                        samples = attr.GetTimeSamples()
                        if samples:
                            samples_found += 1
                            anim_bounds.append((float(samples[0]), float(samples[-1])))
        except Exception as e:
            print(f"[Smart HUD] ⚠️ Error scanning attributes: {e}")

        if anim_bounds:
            start = min(b[0] for b in anim_bounds)
            end = max(b[1] for b in anim_bounds)
            if end > start:
                return {
                    "start": start,
                    "end": end,
                    "status": "Success",
                    "target_path": resolved_target,
                    "attrs_scanned": attrs_scanned,
                    "samples_found": samples_found,
                }

        # --- Step 4: Reference layer fallback ---
        # If the prim is defined via a reference, check the referenced layer's
        # own startTimeCode / endTimeCode metadata.
        try:
            prim_stack = prim.GetPrimStack()
            for prim_spec in prim_stack:
                layer = prim_spec.layer
                if layer and layer != stage.GetRootLayer():
                    layer_start = layer.startTimeCode
                    layer_end = layer.endTimeCode
                    if layer_start is not None and layer_end is not None and layer_end > layer_start:
                        print(f"[Smart HUD] 📦 Using referenced layer time codes: "
                              f"{layer.identifier} [{layer_start:.0f} → {layer_end:.0f}]")
                        return {
                            "start": layer_start,
                            "end": layer_end,
                            "status": "Success (Layer)",
                            "target_path": resolved_target,
                            "attrs_scanned": attrs_scanned,
                            "samples_found": 0,
                        }
        except Exception as e:
            print(f"[Smart HUD] ⚠️ Error querying referenced layers: {e}")

        # --- Step 5: Final fallback (stage range) ---
        fallback["target_path"] = resolved_target
        fallback["attrs_scanned"] = attrs_scanned
        fallback["samples_found"] = samples_found
        print(f"[Smart HUD] ⚠️ Cycle detection FAILED for {resolved_target}: "
              f"scanned {attrs_scanned} attrs, found {samples_found} with time samples. "
              f"Using stage fallback [{fallback['start']:.0f} → {fallback['end']:.0f}]")
        return fallback

    def _start_telemetry(self):
        import omni.kit.app
        self._update_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(self._on_update)

    def _on_update(self, event):
        import random
        import omni.usd
        import omni.timeline
        import omni.kit.viewport.utility
        from pxr import UsdGeom, Usd, Gf
        
        if not self._running:
            return

        dt = event.payload.get("dt", 0.0)

        context = omni.usd.get_context()
        stage = context.get_stage()
        
        if not stage:
            return

        timeline = omni.timeline.get_timeline_interface()
        is_playing = timeline.is_playing()
        
        time_code = Usd.TimeCode.Default()
        if is_playing:
            fps = stage.GetTimeCodesPerSecond()
            current_frame = timeline.get_current_time() * fps
            time_code = Usd.TimeCode(current_frame)
            
        # 1. Initialize Shared XformCache for performance
        xform_cache = UsdGeom.XformCache(time_code)
        
        # 2. Get Camera Position for Distance Culling
        cam_pos = None
        window = omni.kit.viewport.utility.get_active_viewport_window()
        if window and hasattr(window, "viewport_api"):
            cam_path = window.viewport_api.camera_path
            if cam_path:
                cam_prim = stage.GetPrimAtPath(cam_path)
                if cam_prim and cam_prim.IsValid():
                    cam_matrix = xform_cache.GetLocalToWorldTransform(cam_prim)
                    cam_pos = cam_matrix.ExtractTranslation()
        
        culling_distance_sq = 15000.0 * 15000.0  # Adjust as needed (e.g., 150 meters)
        
        for prim_path, instance in self._hud_instances.items():
            vm = instance["view_model"]
            m_type = instance["machine_type"]
            
            # --- Transform & Culling Update ---
            prim = stage.GetPrimAtPath(prim_path)
            if prim and prim.IsValid():
                world_transform = xform_cache.GetLocalToWorldTransform(prim)
                translation = world_transform.ExtractTranslation()
                
                # Check distance if camera is valid
                if cam_pos is not None:
                    dist_sq = (translation[0] - cam_pos[0])**2 + (translation[1] - cam_pos[1])**2 + (translation[2] - cam_pos[2])**2
                    is_visible = dist_sq < culling_distance_sq
                    
                    # Toggle visibility based on distance
                    if instance.get("is_expanded"):
                        instance["expanded_transform"].visible = is_visible
                        instance["collapsed_transform"].visible = False
                    else:
                        instance["expanded_transform"].visible = False
                        instance["collapsed_transform"].visible = is_visible
                        
                    # Skip matrix update if culled
                    if not is_visible:
                        continue
                
                # Apply Z offset for HUD positioning
                translation[2] += 80.0
                
                new_transform_matrix = [
                    1, 0, 0, 0,
                    0, 1, 0, 0,
                    0, 0, 1, 0,
                    translation[0], translation[1], translation[2], 1
                ]
                
                if instance.get("collapsed_transform"):
                    instance["collapsed_transform"].transform = new_transform_matrix
                if instance.get("expanded_transform"):
                    instance["expanded_transform"].transform = new_transform_matrix
            
            # HUD metrics/progress should only update when timeline is playing
            if not is_playing:
                continue
                
            if m_type == "Human Station":
                cycle_start = instance.get("cycle_start", 0.0)
                cycle_end = instance.get("cycle_end", 3.0 * fps)
                cycle_len_frames = cycle_end - cycle_start
                
                if cycle_len_frames > 0:
                    # Synchronize directly with character animation playback
                    elapsed_frames = (current_frame - cycle_start) % cycle_len_frames
                    rem_frames = cycle_len_frames - elapsed_frames
                    progress_pct = max(0.0, min(100.0, (rem_frames / cycle_len_frames) * 100.0))
                else:
                    progress_pct = 100.0
                    
                # Color logic: Green(100) -> Yellow(50) -> Red(0)
                if progress_pct > 50:
                    r = max(0.0, min(1.0, (100.0 - progress_pct) / 50.0))
                    g = 1.0
                else:
                    r = 1.0
                    g = max(0.0, min(1.0, progress_pct / 50.0))
                    
                # Store values on the view model
                vm.current_progress_pct = progress_pct
                vm.current_r = r
                vm.current_g = g
                
                # Update model to trigger sc.Widget repaint
                vm.progress_text.set_value(f"{progress_pct:.1f}%")
                
                # Force sc.Widget texture update since Model update alone 
                # doesn't automatically trigger 3D texture repaint in older versions
                if instance.get("is_expanded") and "expanded_widget" in instance:
                    instance["expanded_widget"].invalidate()
                elif not instance.get("is_expanded") and "collapsed_widget" in instance:
                    instance["collapsed_widget"].invalidate()
                
                # Directly update retained widget properties for immediate redraw.
                if hasattr(vm, "progress_bars"):
                    for pb in vm.progress_bars:
                        try:
                            pb["fill"].width = ui.Percent(progress_pct)
                            pb["fill"].set_style({
                                "background_color": ui.color(r, g, 0.0, 1.0),
                                "border_radius": 3
                            })
                            pb["spacer"].width = ui.Percent(100.0 - progress_pct)
                        except Exception:
                            pass
                    
            elif m_type == "Machine":
                    # Update these less frequently to avoid flickering, e.g. based on frame count or time, but keeping random logic for now
                    vm.aoi_status.set_value(random.choice(["INSPECTING", "PASS", "FAIL"]))
                    vm.aoi_defect_rate.set_value(random.uniform(0.0, 5.0))
                        
            elif m_type == "Robot Station":
                vm.robot_state.set_value(random.choice(["MOVING", "WELDING", "IDLE"]))

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
    _STYLE_POSITIVE = { 
        "Button": { "background_color": 0xFF2A5E2A }, 
        "Button:hovered": { "background_color": 0xFF33703A }, 
        "Button:pressed": { "background_color": 0xFF1F471F } 
    }
    
    _STYLE_NEGATIVE = { 
        "Button": { "background_color": 0xFF5E2A2A }, 
        "Button:hovered": { "background_color": 0xFF703333 }, 
        "Button:pressed": { "background_color": 0xFF471F1F } 
    }

    def __init__(self):
        self.engine = None
        self.is_enabled = False
        self.hud_scale_model = ui.SimpleFloatModel(1.0)
        self.hud_scale_model.add_value_changed_fn(self._on_hud_scale_changed)
        
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
                    self.toggle_btn.set_style(self._STYLE_POSITIVE)
                except Exception:
                    pass

    def build_ui(self):
        """Builds the 2D control panel inside the Zin Tools Box."""
        with ui.VStack(style=zin_ui_utils.ZIN_NATIVE_STYLE, spacing=zin_ui_utils.ZIN_V_SPACING):
            
            with ui.HStack(height=30, spacing=zin_ui_utils.ZIN_ROW_SPACING):
                # Toggle Button
                button_text = "Turn OFF" if self.is_enabled else "Turn ON"
                button_style = self._STYLE_NEGATIVE if self.is_enabled else self._STYLE_POSITIVE
                
                self.toggle_btn = ui.Button(
                    button_text, 
                    style=button_style,
                    clicked_fn=self._on_toggle_clicked
                )
                
                ui.Button(
                    "Generate Test Graybox Scene",
                    name="Button",
                    clicked_fn=self._create_test_scene,
                    tooltip="Creates 3 Graybox test machines with 'machine_type' attributes properly configured."
                )

            ui.Spacer(height=10)
            
            with ui.CollapsableFrame("Add / Edit HUD Metadata", collapsed=False, height=0):
                with ui.VStack(spacing=zin_ui_utils.ZIN_V_SPACING, padding=6):
                    ui.Label("Add custom attributes to make selected models compatible with HUD and Info Panel:", name="Description")
                    ui.Spacer(height=2)
                    
                    def build_hud_type():
                        self._topic_options = ["Human Station", "Machine", "Robot Station"]
                        self.topic_combo = ui.ComboBox(0, *self._topic_options)
                    zin_ui_utils.build_property_row("HUD Type:", build_hud_type, tooltip="Will be written to 'aif:core:assetClass'")
                        
                    def build_station():
                        self.subject_field = ui.StringField()
                        self.subject_field.model.set_value("S01")
                    zin_ui_utils.build_property_row("Station:", build_station, tooltip="Will be written to 'aif:core:modelNumber'")
                        
                    def build_desc():
                        self.content_field = ui.StringField()
                        self.content_field.model.set_value("Chassis")
                    zin_ui_utils.build_property_row("Description:", build_desc, tooltip="Will be written to 'aif:core:assetDescription'.")
                        
                    def build_process():
                        self.takt_label_field = ui.StringField()
                        self.takt_label_field.model.set_value("Process:")
                    zin_ui_utils.build_property_row("Process:", build_process, tooltip="Will be written to 'hud_takt_label'.")
                        
                    self.apply_to_children_cb = ui.SimpleBoolModel(True)
                    zin_ui_utils.build_checkbox_row("Target:", self.apply_to_children_cb, "Auto-apply to Child Meshes (For Groups)", "If checked, applying to a Group/Xform will automatically apply to its internal Meshes.")
                    
                    def build_custom_cycle():
                        self.custom_cycle_field = ui.IntField()
                        self.custom_cycle_field.model.set_value(0)
                    zin_ui_utils.build_property_row("Custom Cycle (Frames):", build_custom_cycle, tooltip="Manual override for cycle length. Set to 0 for auto-detection.")
                        
                    def build_display_settings():
                        with ui.HStack(spacing=6):
                            self.cb_dynamic = ui.CheckBox(width=20)
                            self.cb_dynamic.model.set_value(True)
                            self.cb_dynamic.model.add_value_changed_fn(self._on_display_setting_changed)
                            ui.Label("Dynamic HUD Status", width=130)
                            
                            self.cb_static = ui.CheckBox(width=20)
                            self.cb_static.model.set_value(True)
                            self.cb_static.model.add_value_changed_fn(self._on_display_setting_changed)
                            ui.Label("Factory Info")
                    zin_ui_utils.build_property_row("Display Settings:", build_display_settings)
                    
                    def build_scale():
                        ui.FloatSlider(self.hud_scale_model, min=0.5, max=3.0)
                    zin_ui_utils.build_property_row("HUD Scale:", build_scale, tooltip="Dynamically rescale the expanded HUDs.")
                    
                    ui.Spacer(height=5)
                    with ui.HStack(spacing=zin_ui_utils.ZIN_ROW_SPACING, height=24):
                        ui.Button(
                            "Add / Update",
                            style=self._STYLE_POSITIVE,
                            clicked_fn=self._apply_attributes_to_selected,
                            tooltip="Adds or updates HUD and AIF metadata attributes for selected models."
                        )
                        ui.Button(
                            "Remove",
                            style=self._STYLE_NEGATIVE,
                            clicked_fn=self._remove_attributes_from_selected,
                            tooltip="Removes HUD attributes from selected models."
                        )
                        
            ui.Spacer(height=10)
            with ui.CollapsableFrame("Animation Binding", collapsed=False, height=0):
                with ui.VStack(spacing=zin_ui_utils.ZIN_V_SPACING, padding=6):
                    def build_anim_target():
                        self.anim_target_field = ui.StringField()
                        self.anim_target_field.model.set_value("")
                    zin_ui_utils.build_property_row("Anim Target (optional):", build_anim_target, tooltip="Absolute path to the animated prim. Used to sync the progress bar.")
                    
                    zin_ui_utils.build_button_row("", "Bind to Selected", self._bind_animation_target, self._STYLE_POSITIVE, "Writes 'aif:core:animationTarget' and optional custom cycle length to the selected prims.")
                    
                    # --- Binding Diagnostic Info ---
                    ui.Spacer(height=6)
                    with ui.HStack(height=1):
                        ui.Rectangle(height=1, style={"background_color": 0xFF444444})
                    ui.Spacer(height=4)
                    ui.Label("Binding Diagnostics:", height=16, style={"color": 0xFF00AAFF, "font_size": 13, "weight": "bold"})
                    
                    def build_diag_status():
                        self._diag_status_label = ui.Label("N/A", name="Description")
                    zin_ui_utils.build_property_row("Status:", build_diag_status)
                    
                    def build_diag_target():
                        self._diag_target_label = ui.Label("(none)", name="Description")
                    zin_ui_utils.build_property_row("Target:", build_diag_target)
                    
                    def build_diag_cycle():
                        self._diag_cycle_label = ui.Label("(none)", name="Description")
                    zin_ui_utils.build_property_row("Cycle Length:", build_diag_cycle)

            ui.Spacer()

    def _on_display_setting_changed(self, model):
        # Notify the engine to rebuild HUDs to reflect the new display settings
        if self.is_enabled and self.engine:
            self.engine.rebuild_huds()
            
    def _on_hud_scale_changed(self, model):
        if not self.is_enabled or not self.engine:
            return
            
        scale = model.as_float
        scale_matrix = [
            scale, 0, 0, 0,
            0, scale, 0, 0,
            0, 0, scale, 0,
            0, 0, 0, 1
        ]
        
        for path, instance in self.engine._hud_instances.items():
            if "scale_transform" in instance:
                instance["scale_transform"].transform = scale_matrix

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
            
            # Write custom cycle length override
            custom_cycle_val = self.custom_cycle_field.model.get_value_as_int() if hasattr(self, "custom_cycle_field") else 0
            cycle_attr = prim.GetAttribute("hud_custom_cycle_length")
            if not cycle_attr:
                cycle_attr = prim.CreateAttribute("hud_custom_cycle_length", Sdf.ValueTypeNames.Int)
            cycle_attr.Set(custom_cycle_val)
            
            if custom_cycle_val > 0:
                print(f"[Smart HUD] ✅ Bound animationTarget = '{target_path}' + custom cycle = {custom_cycle_val} frames on {path}")
            else:
                print(f"[Smart HUD] ✅ Bound animationTarget = '{target_path}' (auto-detect cycle) on {path}")
        
        # Update diagnostic labels and trigger engine rebuild
        self._update_binding_diagnostics()
        if self.is_enabled and self.engine:
            self.engine.rebuild_huds()
            self._update_binding_diagnostics()

    def _find_closest_waypoint_pause(self, world_pos):
        import glob
        import json
        import math
        import omni.usd
        import os
        
        # 動態取得當前 Stage 的路徑，進而推算 ProdLine_UPH 資料夾
        context = omni.usd.get_context()
        stage_url = context.get_stage_url()
        
        json_dir = r"D:\Inventec\DigitalTwin\Factory\IMX\ProdLine_UPH" # Fallback
        if stage_url:
            stage_path = stage_url.replace("omniverse://", "").split("?")[0]
            # 假設結構為 .../IMX_1F/ProdLine/Line_S01.usd
            parent_dir = os.path.dirname(os.path.dirname(stage_path))
            dynamic_dir = os.path.join(parent_dir, "ProdLine_UPH")
            if os.path.exists(dynamic_dir):
                json_dir = dynamic_dir
                
        print(f"[Smart HUD] 🔍 Scanning JSON files in: {json_dir}")
        json_files = glob.glob(f"{json_dir}/*.json")
        
        closest_wp = None
        min_dist = float('inf')
        
        for f in json_files:
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    
                waypoints = data.get("waypoints", [])
                for wp in waypoints:
                    pos = wp.get("pos")
                    if pos and len(pos) >= 3:
                        dx = pos[0] - world_pos[0]
                        dy = pos[1] - world_pos[1]
                        dz = pos[2] - world_pos[2]
                        dist = math.sqrt(dx*dx + dy*dy + dz*dz)
                        if dist < min_dist:
                            min_dist = dist
                            closest_wp = wp
            except Exception as e:
                print(f"[Smart HUD] Error reading {f}: {e}")
                
        if closest_wp:
            print(f"[Smart HUD] 📍 Closest Waypoint '{closest_wp.get('name')}' found at distance {min_dist:.2f} units. Pause: {closest_wp.get('pause')}s")
            
        # 增加一個距離寬容值，如果離最靠近的點位大於 200 (2公尺)，可能代表抓錯了
        if closest_wp and min_dist < 500.0:
            if "pause" in closest_wp:
                return closest_wp["pause"]
            
        print("[Smart HUD] ⚠️ No valid waypoint found within 500 units.")
        return None

    def _apply_attributes_to_selected(self):
        import omni.usd
        from pxr import Sdf, UsdGeom, Usd
        
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
        topic = self._topic_options[idx] if 0 <= idx < len(self._topic_options) else "Human Station"
        subject = self.subject_field.model.get_value_as_string()
        content = self.content_field.model.get_value_as_string()
        takt_label = self.takt_label_field.model.get_value_as_string()
        
        apply_to_children = False
        if hasattr(self, "apply_to_children_cb"):
            apply_to_children = self.apply_to_children_cb.get_value_as_bool()

        target_paths = set()
        for path in selection:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue
                
            if apply_to_children and not prim.IsA(UsdGeom.Mesh):
                # Expand group: find all descendant Meshes
                meshes = [p for p in Usd.PrimRange(prim) if p.IsA(UsdGeom.Mesh)]
                if meshes:
                    for m in meshes:
                        target_paths.add(str(m.GetPath()))
                    print(f"[Smart HUD] 📦 Auto-expanded group {path} into {len(meshes)} Mesh prims.")
                else:
                    target_paths.add(path)
            else:
                target_paths.add(path)

        for path in target_paths:
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
            
            # Also persist custom cycle length if set in the UI
            custom_cycle_val = 0
            if hasattr(self, "custom_cycle_field"):
                custom_cycle_val = self.custom_cycle_field.model.get_value_as_int()
                
            # --- Auto-bind from JSON if Machine or Robot Station ---
            if topic in ["Machine", "Robot Station"]:
                world_transform = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                translation = world_transform.ExtractTranslation()
                pause_sec = self._find_closest_waypoint_pause(translation)
                
                if pause_sec is not None:
                    fps = stage.GetTimeCodesPerSecond()
                    auto_cycle_val = int(pause_sec * fps)
                    if custom_cycle_val <= 0 and auto_cycle_val > 0:  # Only override if not manually set in UI and pause > 0
                        custom_cycle_val = auto_cycle_val
                        print(f"[Smart HUD] ✅ Auto-Bound: Matched closest Waypoint. Set cycle time to {auto_cycle_val} frames (Pause: {pause_sec}s) on {path}.")
                    elif custom_cycle_val <= 0 and auto_cycle_val == 0:
                        print(f"[Smart HUD] ⚠️ Closest Waypoint has 0s pause. Cycle time not updated for {path}.")
            
            cycle_attr = prim.GetAttribute("hud_custom_cycle_length")
            if not cycle_attr:
                cycle_attr = prim.CreateAttribute("hud_custom_cycle_length", Sdf.ValueTypeNames.Int)
            cycle_attr.Set(custom_cycle_val)

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
            "hud_custom_cycle_length",
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
            "Machine": Gf.Vec3d(0, 0, 100),
            "Robot Station": Gf.Vec3d(300, 0, 100),
            "Human Station": Gf.Vec3d(-300, 0, 100)
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
            self.toggle_btn.set_style(self._STYLE_NEGATIVE)
            if not self.engine:
                self.engine = GrayboxHUDEngine(self)
            self._update_binding_diagnostics()
        else:
            self.toggle_btn.text = "Turn ON"
            self.toggle_btn.set_style(self._STYLE_POSITIVE)
            if self.engine:
                self.engine.destroy()
                self.engine = None
                
        # Explicitly release focus so hotkeys like 'F' work immediately
        import omni.kit.viewport.utility
        window = omni.kit.viewport.utility.get_active_viewport_window()
        if window:
            window.focus()

    def _update_binding_diagnostics(self):
        """Refresh the binding diagnostic labels from the engine's HUD instances."""
        if not self.engine or not self.engine._hud_instances:
            if hasattr(self, "_diag_status_label") and self._diag_status_label:
                self._diag_status_label.text = "N/A (HUD not active)"
                self._diag_status_label.set_style({"color": 0xFFAAAAAA, "font_size": 12})
            if hasattr(self, "_diag_target_label") and self._diag_target_label:
                self._diag_target_label.text = "(none)"
            if hasattr(self, "_diag_cycle_label") and self._diag_cycle_label:
                self._diag_cycle_label.text = "(none)"
            return
        
        # Aggregate binding status from all Human Station HUD instances
        for prim_path, instance in self.engine._hud_instances.items():
            vm = instance["view_model"]
            if instance["machine_type"] != "Human Station":
                continue
            
            is_manual = vm.bind_status == "Manual Override"
            is_success = vm.bind_status.startswith("Success") or is_manual
            if hasattr(self, "_diag_status_label") and self._diag_status_label:
                if is_manual:
                    self._diag_status_label.text = f"🎯 Manual Override"
                    self._diag_status_label.set_style({"color": 0xFF00CCFF, "font_size": 12})
                elif is_success:
                    self._diag_status_label.text = f"✅ Bound Successfully"
                    self._diag_status_label.set_style({"color": 0xFF44FF44, "font_size": 12})
                else:
                    self._diag_status_label.text = f"⚠️ {vm.bind_status} — Using Stage Fallback"
                    self._diag_status_label.set_style({"color": 0xFFFF8800, "font_size": 12})
            if hasattr(self, "_diag_target_label") and self._diag_target_label:
                self._diag_target_label.text = vm.bind_target if vm.bind_target else "(none)"
            if hasattr(self, "_diag_cycle_label") and self._diag_cycle_label:
                suffix = " (Manual Override)" if is_manual else ""
                self._diag_cycle_label.text = f"{vm.bind_cycle_len:.0f} frames{suffix}"
            break  # Show first Human Station's binding info

    def shutdown(self):
        """Called by ToolsBox on extension shutdown"""
        if self.engine:
            self.engine.destroy()
            self.engine = None
        self.is_enabled = False
        
        # Clear stage event subscriptions
        self._stage_event_subs = []
