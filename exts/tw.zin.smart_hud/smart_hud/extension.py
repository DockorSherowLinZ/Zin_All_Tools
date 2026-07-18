import omni.ext
import omni.ui as ui
import omni.ui.scene as sc
import omni.usd
from pxr import Usd, UsdGeom, Gf
import asyncio
import random

# ==============================================================================
# Kit USD Agents Integration
# ==============================================================================
class UsdSelectionAgent:
    """
    Agent class to handle USD interactions safely and decoupled from UI.
    Listens for stage selection events and queries the machine_type.
    """
    def __init__(self, callback):
        self._callback = callback
        self._context = omni.usd.get_context()
        self._sub = self._context.get_stage_event_stream().create_subscription_to_pop(
            self._on_stage_event, name="DSX_HUD_Selection_Agent"
        )
    
    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            self._handle_selection()
            
    def _handle_selection(self):
        selected_paths = self._context.get_selection().get_selected_prim_paths()
        if not selected_paths:
            self._callback(None, None)
            return
            
        stage = self._context.get_stage()
        if not stage:
            return
            
        prim = stage.GetPrimAtPath(selected_paths[0])
        if not prim or not prim.IsValid():
            return
            
        # Check machine type attribute
        attr = prim.GetAttribute("machine_type")
        if attr and attr.IsValid():
            m_type = attr.Get()
            
            # Extract world transform
            xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
            world_transform = xform_cache.GetLocalToWorldTransform(prim)
            translation = world_transform.ExtractTranslation()
            self._callback(m_type, translation)
        else:
            self._callback(None, None)

    def destroy(self):
        self._sub = None


# ==============================================================================
# MVVM View Model
# ==============================================================================
class HUDViewModel:
    """MVVM View Model holding all the observable data."""
    def __init__(self):
        self.aoi_status = ui.SimpleStringModel("IDLE")
        self.aoi_defect_rate = ui.SimpleFloatModel(0.0)
        self.robot_state = ui.SimpleStringModel("STANDBY")
        self.manual_station_name = ui.SimpleStringModel("Manual Assembly #1")
        self.manual_takt_time_pct = ui.SimpleFloatModel(100.0)


# ==============================================================================
# HUD Engine
# ==============================================================================
class GrayboxHUDEngine:
    def __init__(self):
        self.view_model = HUDViewModel()
        self.ui_pool = {} 
        self.scene_view = None
        self._running = True
        self._telemetry_task = None
        self._selection_agent = None
        self._color_sub = None
        
        self._build_ui()
        self._start_telemetry()
        
        # Initialize Kit USD Selection Agent
        self._selection_agent = UsdSelectionAgent(self.on_selection_changed)

    def _build_ui(self):
        import omni.kit.viewport.utility
        self.viewport_window = omni.kit.viewport.utility.get_active_viewport_window()
        
        if not self.viewport_window:
            self.viewport_window = ui.Window("DSX AI Factory - Phase 7 Graybox HUD", width=800, height=600)

        with self.viewport_window.get_frame("DSX_Phase7_HUD_Overlay"):
            self.scene_view = sc.SceneView()
            
            if hasattr(self.viewport_window, "viewport_api"):
                self.viewport_window.viewport_api.add_scene_view(self.scene_view)
                
            with self.scene_view.scene:
                self.ui_pool["AOI"] = self._create_pooled_widget("AOI", self._build_aoi_ui)
                self.ui_pool["Robot"] = self._create_pooled_widget("Robot", self._build_robot_ui)
                self.ui_pool["ManualStation"] = self._create_pooled_widget("ManualStation", self._build_manual_station_ui)

    def _create_pooled_widget(self, name, ui_builder_func):
        transform = sc.Transform(look_at=sc.Transform.LookAt.CAMERA, visible=False)
        with transform:
            widget = sc.Widget(width=280, height=160)
            widget.frame.set_build_fn(ui_builder_func)
        return {"transform": transform, "widget": widget}

    def _build_aoi_ui(self):
        with ui.ZStack():
            ui.Rectangle(style={"background_color": 0xCC1A1E24, "border_color": 0xCC00FFFF, "border_width": 2, "border_radius": 5})
            with ui.HStack():
                ui.Spacer(width=25)
                with ui.VStack(spacing=5):
                    ui.Spacer(height=15)
                    ui.Label("AOI Inspection", style={"color": 0xFFFFFFFF, "font_size": 20})
                    with ui.HStack():
                        ui.Label("Status:", width=80, style={"color": 0xFFAAAAAA})
                        ui.Label("", model=self.view_model.aoi_status, style={"color": 0xFFFFFFFF})
                    with ui.HStack():
                        ui.Label("Defect %:", width=80, style={"color": 0xFFAAAAAA})
                        ui.FloatField(model=self.view_model.aoi_defect_rate, read_only=True, style={"color": 0xFFFFFFFF})
                    ui.Spacer(height=15)
                ui.Spacer(width=25)

    def _build_robot_ui(self):
        with ui.ZStack():
            ui.Rectangle(style={"background_color": 0xCC1A1E24, "border_color": 0xCC00FFFF, "border_width": 2, "border_radius": 5})
            with ui.HStack():
                ui.Spacer(width=25)
                with ui.VStack(spacing=5):
                    ui.Spacer(height=15)
                    ui.Label("Robot Arm", style={"color": 0xFFFFFFFF, "font_size": 20})
                    with ui.HStack():
                        ui.Label("State:", width=80, style={"color": 0xFFAAAAAA})
                        ui.Label("", model=self.view_model.robot_state, style={"color": 0xFFFFFFFF})
                    ui.Spacer(height=15)
                ui.Spacer(width=25)

    def _build_manual_station_ui(self):
        with ui.ZStack():
            ui.Rectangle(style={"background_color": ui.color(0.05, 0.05, 0.12, 0.85), "border_color": 0xCC00FFFF, "border_width": 2, "border_radius": 5})
            with ui.HStack():
                ui.Spacer(width=25)
                with ui.VStack(spacing=10):
                    ui.Spacer(height=15)
                    ui.Label("", model=self.view_model.manual_station_name, style={"color": 0xFFFFFFFF, "font_size": 22, "alignment": ui.Alignment.CENTER})
                    ui.Label("Takt Time Remaining:", style={"color": 0xFFAAAAAA, "font_size": 14})
                    with ui.ZStack(height=20):
                        ui.Rectangle(style={"background_color": 0x44000000, "border_radius": 3})
                        self.progress_fill = ui.Rectangle(
                            style={"background_color": ui.color(0.0, 1.0, 0.0, 1.0), "border_radius": 3},
                            width=ui.Percent(100) 
                        )
                    ui.Spacer(height=15)
                ui.Spacer(width=25)

        self._color_sub = self.view_model.manual_takt_time_pct.add_value_changed_fn(self._on_takt_time_changed)

    def _on_takt_time_changed(self, model):
        pct = model.as_float
        pct = max(0.0, min(100.0, pct))
        self.progress_fill.width = ui.Percent(pct)
        ratio = pct / 100.0
        r = 1.0 - ratio
        g = ratio
        b = 0.0
        self.progress_fill.style = {
            "background_color": ui.color(r, g, b, 1.0),
            "border_radius": 3
        }

    def on_selection_changed(self, machine_type, translation):
        for key, pool_item in self.ui_pool.items():
            pool_item["transform"].visible = False
            
        if machine_type in self.ui_pool and translation is not None:
            item = self.ui_pool[machine_type]
            transform_matrix = [
                1, 0, 0, 0,
                0, 1, 0, 0,
                0, 0, 1, 0,
                translation[0], translation[1], translation[2] + 150.0, 1
            ]
            item["transform"].transform = transform_matrix
            item["transform"].visible = True

    def _start_telemetry(self):
        self._telemetry_task = asyncio.ensure_future(self._telemetry_loop())

    async def _telemetry_loop(self):
        takt_timer = 100.0
        while self._running:
            self.view_model.aoi_status.set_value(random.choice(["INSPECTING", "PASS", "FAIL"]))
            self.view_model.aoi_defect_rate.set_value(random.uniform(0.0, 5.0))
            self.view_model.robot_state.set_value(random.choice(["MOVING", "WELDING", "IDLE"]))
            
            takt_timer -= 2.0 
            if takt_timer <= 0:
                takt_timer = 100.0
            self.view_model.manual_takt_time_pct.set_value(takt_timer)
            
            await asyncio.sleep(0.1)

    def destroy(self):
        self._running = False
        if self._selection_agent:
            self._selection_agent.destroy()
            self._selection_agent = None
        self._telemetry_task = None
        self._color_sub = None
        
        # Safe cleanup of Viewport Overlay
        if self.viewport_window:
            if hasattr(self.viewport_window, "viewport_api") and self.scene_view:
                try:
                    self.viewport_window.viewport_api.remove_scene_view(self.scene_view)
                except:
                    pass
            # Clear the frame to destroy the UI elements
            frame = self.viewport_window.get_frame("DSX_Phase7_HUD_Overlay")
            if frame:
                frame.clear()
        
        self.scene_view = None
        self.viewport_window = None


# ==============================================================================
# Zin Tools Box UI Interface
# ==============================================================================
class SmartHudUI:
    """
    UI Class managed by Zin Tools Box.
    Handles the toggle logic for the HUD Engine.
    """
    def __init__(self):
        self.engine = None
        self.is_enabled = False

    def build_ui(self):
        """Builds the control panel inside the Zin Tools Box 'HUD' tab."""
        with ui.VStack(spacing=10):
            ui.Label("Digital Twin HUD Control", style={"font_size": 18, "color": 0xFFDDDDDD})
            ui.Spacer(height=10)
            
            with ui.HStack(height=30, spacing=10):
                ui.Label("Enable 3D HUD Overlay:", width=150)
                
                # Toggle Button
                button_text = "Turn OFF" if self.is_enabled else "Turn ON"
                button_color = 0xFF4444FF if self.is_enabled else 0xFF44AA44
                
                self.toggle_btn = ui.Button(
                    button_text, 
                    style={"background_color": button_color, "border_radius": 4},
                    clicked_fn=self._on_toggle_clicked
                )
            
            ui.Spacer(height=20)
            ui.Label("Instructions:\n1. Turn ON the HUD.\n2. Click any Graybox Machine in the viewport.\n3. The data panel will float above it.", 
                     style={"color": 0xFFAAAAAA, "font_size": 14})
            
            ui.Spacer(height=20)
            ui.Label("Quick Start Demo", style={"font_size": 16, "color": 0xFFDDDDDD})
            ui.Button(
                "Generate Test Graybox Scene",
                height=30,
                style={"background_color": 0xFF444444, "border_radius": 4},
                clicked_fn=self._create_test_scene,
                tooltip="Creates 3 Graybox test machines with 'machine_type' attributes properly configured."
            )

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
            self.toggle_btn.set_style({"background_color": 0xFF4444FF, "border_radius": 4})
            if not self.engine:
                self.engine = GrayboxHUDEngine()
        else:
            self.toggle_btn.text = "Turn ON"
            self.toggle_btn.set_style({"background_color": 0xFF44AA44, "border_radius": 4})
            if self.engine:
                self.engine.destroy()
                self.engine = None

    def shutdown(self):
        """Called by ToolsBox on extension shutdown"""
        if self.engine:
            self.engine.destroy()
            self.engine = None
        self.is_enabled = False
