import omni.ext
import omni.ui as ui
import omni.usd
import omni.kit.app
import omni.kit.menu.utils
import omni.client
import carb
from pxr import UsdGeom, Gf, Usd, Sdf
import sys, os, json

# omni.timeline 可能在某些現引編罯不存在，支援安全降級
try:
    import omni.timeline as _omni_timeline
except Exception:
    _omni_timeline = None

# omni.kit.window.filepicker: optional, graceful fallback if not available
try:
    from omni.kit.window.filepicker import FilePickerDialog
    _HAS_FILEPICKER = True
except Exception:
    FilePickerDialog = None
    _HAS_FILEPICKER = False

# ── Import Zin Design System ─────────────────────────────────────────────────
try:
    _tools_box_dir = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "tools_box", "tools_box"
    )
    if os.path.isdir(_tools_box_dir) and _tools_box_dir not in sys.path:
        sys.path.insert(0, _tools_box_dir)
    from zin_style import (
        ZIN_GLOBAL_STYLE,
        ARGB_CORRECT_LABEL, ARGB_TEXT_PRIMARY, ARGB_TEXT_SECONDARY,
        ARGB_TEXT_MUTED, ARGB_ICON_FOLDER, ARGB_CORRECT_BG,
    )
    from zin_components import ZinButton
except Exception as _e:
    carb.log_warn(f"[smart_conveyor] Could not import Zin style: {_e}. Using fallback styles.")
    ZIN_GLOBAL_STYLE    = {}
    ARGB_CORRECT_LABEL  = 0xFF44AA44
    ARGB_TEXT_PRIMARY   = 0xFFDDDDDD
    ARGB_TEXT_SECONDARY = 0xFFAAAAAA
    ARGB_TEXT_MUTED     = 0xFF888888
    ARGB_ICON_FOLDER    = 0xFFDCA550
    ARGB_CORRECT_BG     = 0xFF2A5E2A
    class ZinButton:
        def __init__(self, text, state="default", clicked_fn=None, **kwargs):
            _COLOR = {"correct": 0xFF2A5E2A, "error": 0xFF5E2A2A, "default": 0xFF343432}
            self._btn = ui.Button(text, clicked_fn=clicked_fn,
                                  style={"background_color": _COLOR.get(state, 0xFF343432)},
                                  **kwargs)
        def set_state(self, s): pass
        @property
        def widget(self): return self._btn

# ==========================================
# Core Logic: PCB Conveyor Controller
# ==========================================
class PCBConveyorController:
    def __init__(self, config):
        self.stage = omni.usd.get_context().get_stage()
        self.config = config
        
        self.template_path = config.get("template_path", "")

        self.prim_path = config.get("prim_path", "/World/PCB_Board")
        if not self.stage:
            carb.log_error("[tw.zin.smart_conveyor] No valid USD Stage found!")
            self.prim = None
            return

        self.prim = self.stage.GetPrimAtPath(self.prim_path)

        if not self.prim.IsValid():
            carb.log_info(f"[tw.zin.smart_conveyor] 偵測到物件已遺失 ({self.prim_path})，自動將其回收到備用池。")
            self.state = "FINISHED"
            self.prim = None
            self.waypoints = config.get("waypoints", [])
            self.timer = 0.0
            return

        # Ensure the prim has Xformable ops for translation and rotation
        self.xformable = UsdGeom.Xformable(self.prim)
        self.translate_op = self._get_or_create_op(UsdGeom.XformOp.TypeTranslate)
        self.rotate_op = self._get_or_create_op(UsdGeom.XformOp.TypeRotateXYZ)
        self.scale_op = self._get_or_create_op(UsdGeom.XformOp.TypeScale)

        # Load config values
        self.waypoints = config.get("waypoints", [])
        self.speed = config.get("speed", 50.0)
        self.initial_delay = config.get("initial_delay", 0.0)
        self.end_visibility = config.get("end_visibility", False)
        self.is_reverse = config.get("reverse", False)
        self.is_loop = config.get("loop", False)  # Loop: jump back to wp[0] and repeat

        self.current_wp_idx = 0
        self.timer = 0.0
        self.state = "INITIAL_DELAY" if self.initial_delay > 0 else "MOVING"
        self.direction = 1

        if self.waypoints:
            init_pos, init_rot = self._get_target_world_transform(self.waypoints[0]["pos"], self.waypoints[0]["rot"])
            self._apply_world_transform(init_pos, init_rot)
            self._set_visibility(True)

        # Register frame update event subscription (named for Profiler visibility)
        self._update_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
            self._on_update, name="tw.zin.smart_conveyor.update"
        )
        carb.log_info("[tw.zin.smart_conveyor] Controller started.")

    def _get_ref_matrix(self) -> Gf.Matrix4d:
        if not self.template_path or not self.stage:
            return Gf.Matrix4d(1.0)
        prim = self.stage.GetPrimAtPath(self.template_path)
        if prim and prim.IsValid():
            parent = prim.GetParent()
            if parent and parent.GetPath() != "/":
                import omni.timeline
                from pxr import UsdGeom, Usd
                time = omni.timeline.get_timeline_interface().get_current_time()
                cache = UsdGeom.XformCache(Usd.TimeCode(time))
                return cache.GetLocalToWorldTransform(parent)
        return Gf.Matrix4d(1.0)

    def _get_target_world_transform(self, wp_pos, wp_rot):
        ref_mat = self._get_ref_matrix()
        target_world_pos = ref_mat.Transform(Gf.Vec3d(wp_pos))
        
        local_rot_mat = Gf.Matrix4d().SetRotate(
            Gf.Rotation(Gf.Vec3d.XAxis(), wp_rot[0]) *
            Gf.Rotation(Gf.Vec3d.YAxis(), wp_rot[1]) *
            Gf.Rotation(Gf.Vec3d.ZAxis(), wp_rot[2])
        )
        world_rot_mat = local_rot_mat * ref_mat
        
        return target_world_pos, world_rot_mat.ExtractRotation()

    def _get_or_create_op(self, op_type):
        # USD best practice: check for existing op before adding a new one
        for op in self.xformable.GetOrderedXformOps():
            if op.GetOpType() == op_type:
                return op
        return self.xformable.AddXformOp(op_type, UsdGeom.XformOp.PrecisionDouble)

    def _apply_world_transform(self, world_pos, world_rot):
        """將世界座標 (pos, rot) 轉換為局部座標後套用至 xformOp。"""
        if not self.translate_op or not self.rotate_op or not self.prim.IsValid():
            return

        xformable = UsdGeom.Xformable(self.prim)
        for op in xformable.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeOrient:
                op.Set(Gf.Quatf(1.0, 0.0, 0.0, 0.0))

        # 1. 建立目標的世界變換矩陣 (Target World Matrix)
        target_world_mat = Gf.Matrix4d().SetRotate(world_rot)
        target_world_mat.SetTranslateOnly(world_pos)

        # 2. 取得父層級的世界變換反矩陣 (Parent World Inverse Matrix)
        parent_prim = self.prim.GetParent()
        if parent_prim and parent_prim.GetPath() != "/":
            parent_inv_mat = omni.usd.get_world_transform_matrix(parent_prim).GetInverse()
        else:
            parent_inv_mat = Gf.Matrix4d(1.0)

        # 3. 世界變換 * 父層反變換 = 局部變換 (Local Matrix)
        local_mat = target_world_mat * parent_inv_mat

        # 4. 提取 Local Pos 與 Local Rot
        local_pos = local_mat.ExtractTranslation()
        local_rot_q = local_mat.ExtractRotation()
        euler = local_rot_q.Decompose(Gf.Vec3d.ZAxis(), Gf.Vec3d.YAxis(), Gf.Vec3d.XAxis())

        # 5. 套用
        self.translate_op.Set(Gf.Vec3d(local_pos))
        self.rotate_op.Set(Gf.Vec3d(euler[2], euler[1], euler[0]))
        
        # 6. Apply World Scale from parent
        if hasattr(self, "scale_op"):
            ref_mat = self._get_ref_matrix()
            scale_x = ref_mat.GetRow3(0).GetLength()
            scale_y = ref_mat.GetRow3(1).GetLength()
            scale_z = ref_mat.GetRow3(2).GetLength()
            # 避免 scale 為 0
            scale_x = scale_x if scale_x > 0 else 1.0
            scale_y = scale_y if scale_y > 0 else 1.0
            scale_z = scale_z if scale_z > 0 else 1.0
            self.scale_op.Set(Gf.Vec3d(scale_x, scale_y, scale_z))

    def _set_visibility(self, visible):
        if self.prim and self.prim.IsValid():
            imageable = UsdGeom.Imageable(self.prim)
            # USD best practice: use MakeVisible/MakeInvisible instead of Set("inherited")
            if visible:
                imageable.MakeVisible()
            else:
                imageable.MakeInvisible()

    def _on_update(self, e: carb.events.IEvent):
        # Safety check: validate prim every frame (user may delete it at runtime)
        if not self.waypoints or self.state == "FINISHED" or not self.prim or not self.prim.IsValid():
            if self.state != "FINISHED":
                carb.log_warn("[tw.zin.smart_conveyor] Target prim is invalid or deleted - stopping to prevent crash.")
                self.stop()
            return

        dt = e.payload["dt"]

        # Overshoot protection: clamp dt to max 0.1s (below 10 FPS)
        # Prevents the model from tunneling through waypoints during severe frame drops
        dt = min(dt, 0.1)

        if self.state == "INITIAL_DELAY":
            self.timer += dt
            if self.timer >= self.initial_delay:
                self.timer = 0.0
                self.state = "MOVING"

        elif self.state == "PAUSING":
            self.timer += dt
            current_wp = self.waypoints[self.current_wp_idx]
            pause_time = current_wp.get("pause", 0.0)
            if self.timer >= pause_time:
                self.timer = 0.0
                self._advance_waypoint()

        elif self.state == "MOVING":
            # 必須在同一個「世界座標系」下計算向量，才不會因為父層旋轉導致方向偏移
            current_world_mat = omni.usd.get_world_transform_matrix(self.prim)
            current_world_pos = current_world_mat.ExtractTranslation()
            
            next_idx = self.current_wp_idx + self.direction

            if next_idx >= len(self.waypoints) or next_idx < 0:
                self._handle_end_point()
                return

            target_wp = self.waypoints[next_idx]
            target_world_pos, target_world_rot = self._get_target_world_transform(target_wp["pos"], target_wp["rot"])

            move_vec = target_world_pos - current_world_pos
            distance = move_vec.GetLength()

            # Guard: treat near-zero distance as arrived to avoid divide-by-zero in GetNormalized()
            if distance < 1e-5:
                self._apply_world_transform(target_world_pos, target_world_rot)
                self.current_wp_idx = next_idx
                if target_wp.get("pause", 0.0) > 0:
                    self.state = "PAUSING"
                else:
                    self._advance_waypoint()
                return

            step = self.speed * dt

            if step >= distance:
                self._apply_world_transform(target_world_pos, target_world_rot)
                self.current_wp_idx = next_idx
                if target_wp.get("pause", 0.0) > 0:
                    self.state = "PAUSING"
                else:
                    self._advance_waypoint()
            else:
                move_dir = move_vec.GetNormalized()
                new_world_pos = current_world_pos + (move_dir * step)
                
                # --- Smooth Rotation Interpolation (Slerp) ---
                alpha = step / distance
                current_rot = current_world_mat.ExtractRotation()
                target_rot = target_world_rot
                
                q0 = current_rot.GetQuat()
                q1 = target_rot.GetQuat()
                
                # shortest path
                dot = q0.GetReal() * q1.GetReal() + q0.GetImaginary()[0] * q1.GetImaginary()[0] + q0.GetImaginary()[1] * q1.GetImaginary()[1] + q0.GetImaginary()[2] * q1.GetImaginary()[2]
                if dot < 0.0:
                    q1 = Gf.Quatd(-q1.GetReal(), -q1.GetImaginary()[0], -q1.GetImaginary()[1], -q1.GetImaginary()[2])
                    dot = -dot
                    
                if dot > 0.9995:
                    interp_q = Gf.Quatd(q0.GetReal() + alpha*(q1.GetReal()-q0.GetReal()), 
                                        q0.GetImaginary()[0] + alpha*(q1.GetImaginary()[0]-q0.GetImaginary()[0]),
                                        q0.GetImaginary()[1] + alpha*(q1.GetImaginary()[1]-q0.GetImaginary()[1]),
                                        q0.GetImaginary()[2] + alpha*(q1.GetImaginary()[2]-q0.GetImaginary()[2]))
                    interp_q.Normalize()
                else:
                    import math
                    theta_0 = math.acos(dot)
                    theta = theta_0 * alpha
                    sin_theta = math.sin(theta)
                    sin_theta_0 = math.sin(theta_0)
                    s0 = math.cos(theta) - dot * sin_theta / sin_theta_0
                    s1 = sin_theta / sin_theta_0
                    interp_q = Gf.Quatd(s0*q0.GetReal() + s1*q1.GetReal(),
                                        s0*q0.GetImaginary()[0] + s1*q1.GetImaginary()[0],
                                        s0*q0.GetImaginary()[1] + s1*q1.GetImaginary()[1],
                                        s0*q0.GetImaginary()[2] + s1*q1.GetImaginary()[2])
                                        
                interp_rot = Gf.Rotation(interp_q)
                self._apply_world_transform(new_world_pos, interp_rot)

    def _advance_waypoint(self):
        if (self.direction == 1 and self.current_wp_idx == len(self.waypoints) - 1) or \
           (self.direction == -1 and self.current_wp_idx == 0):
            self._handle_end_point()
        else:
            self.state = "MOVING"

    def _handle_end_point(self):
        # Priority: Reverse > Loop > Stop (if both checked, Reverse takes effect)
        if self.is_reverse:
            # Reverse: flip direction and keep moving
            self.direction *= -1
            self.state = "MOVING"
        elif self.is_loop:
            # Loop: teleport back to waypoint[0] and restart forward
            self._apply_world_transform(self.waypoints[0]["pos"], self.waypoints[0]["rot"])
            self.current_wp_idx = 0
            self.direction = 1
            self.state = "MOVING"
            carb.log_info("[tw.zin.smart_conveyor] Loop: restarting from waypoint 0.")
        else:
            if not self.end_visibility:
                # Hide model at endpoint so it can be recycled normally
                if self.prim and self.prim.IsValid():
                    self._set_visibility(False)
                self.state = "FINISHED"
                self.stop()
            else:
                # If end_visibility is True, we keep it visible and set state to "STOPPED".
                # This prevents _spawner_loop from recycling it, allowing PCBs to pile up at the end.
                self.state = "STOPPED"
                self.stop()

    def stop(self):
        # Safely unsubscribe from the update event stream
        if hasattr(self, '_update_sub'):
            self._update_sub = None
        if self.state != "STOPPED":
            self.state = "FINISHED"
        carb.log_info("[tw.zin.smart_conveyor] Controller stopped.")


# ==========================================
# Extension UI & Lifecycle Management
# ==========================================
class SmartConveyorExtension(omni.ext.IExt):
    _primary_instance = None
    MENU_PATH = "Zin_All_Tools/Smart Conveyor Panel"

    def __init__(self):
        # Pre-initialize all instance attributes to safe defaults.
        # This is required because tools_box embeds this class by calling
        # SmartConveyorExtension() directly — on_startup() is never invoked
        # in that context, so any attribute accessed by UI callbacks must
        # already exist to avoid AttributeError crashes.
        super().__init__()
        self._window = None
        self._menu = None
        self._timeline_sub = None
        self._filepicker_save = None   # FilePickerDialog for Save JSON
        self._filepicker_load = None   # FilePickerDialog for Load JSON
        self._spawner_sub = None       # Timer loop for dynamic spawning
        self._active_spawners = []     # List of active spawner configs
        self._inactive_pools = {}      # dict mapping line_id -> list of idle prim paths
        self._stage_sub = None         # Stage event subscription
        # UI data models are created lazily by _ensure_models()

    def on_startup(self, ext_id):
        carb.log_info("[tw.zin.smart_conveyor] Extension starting up")
        self._window = None
        self._timeline_sub = None          # Timeline event subscription
        self._filepicker_save = None       # FilePickerDialog instance for Save JSON
        self._filepicker_load = None       # FilePickerDialog instance for Load JSON
        self._spawner_sub = None           # Spawner loop
        self._active_spawners = []
        self._inactive_pools = {}
        self._stage_sub = None
        self._ensure_models()

        # 1. Register menu item
        self._menu = omni.kit.menu.utils.add_menu_items([
            omni.kit.menu.utils.MenuItemDescription(
                name="Smart Conveyor Panel",
                onclick_fn=self._toggle_window
            )
        ], "Zin_All_Tools")

        # 2. Register UI Workspace for docking support
        ui.Workspace.set_show_window_fn("Smart Conveyor Panel", self._set_window_visibility)

        # 3. Subscribe to omni.timeline events (auto Start/Stop on Play/Stop)
        try:
            if _omni_timeline is not None:
                tl = _omni_timeline.get_timeline_interface()
                self._timeline_sub = tl.get_timeline_event_stream().create_subscription_to_pop(
                    self._on_timeline_event, name="tw.zin.smart_conveyor.timeline"
                )
        except Exception as _te:
            carb.log_warn(f"[tw.zin.smart_conveyor] Timeline subscription failed: {_te}")

        # 3.5 Subscribe to Stage events (auto Stop on Scene Change)
        try:
            self._stage_sub = omni.usd.get_context().get_stage_event_stream().create_subscription_to_pop(
                self._on_stage_event, name="tw.zin.smart_conveyor.stage_event"
            )
        except Exception as _e:
            carb.log_warn(f"[tw.zin.smart_conveyor] Stage event subscription failed: {_e}")

        # 4. Do not show the standalone panel automatically on startup
        # (Users can open it from the menu, or use the embedded Zin Tools Box tab)
        # self._set_window_visibility(True)

        # 5. Auto-restore config from the USD scene after UI is built
        self._usd_auto_load()

    def startup_as_embedded(self, ext_id: str = ""):
        """Lightweight startup for use when hosted inside tools_box (or any parent extension).

        Performs full runtime initialization — Timeline subscription, data models,
        and USD auto-load — but intentionally skips:
          - Creating the standalone 'Smart Conveyor Panel' window
          - Registering a Zin_All_Tools menu item
          - Registering a Workspace show-window callback

        Call this instead of on_startup() when embedding the tool in a tab.
        The matching teardown is on_shutdown(), which cleans up everything safely.
        """
        carb.log_info("[tw.zin.smart_conveyor] Starting up in embedded mode (no standalone window).")
        self._ensure_models()

        # Subscribe to Timeline events so Play/Stop work from the parent window too
        try:
            if _omni_timeline is not None:
                tl = _omni_timeline.get_timeline_interface()
                self._timeline_sub = tl.get_timeline_event_stream().create_subscription_to_pop(
                    self._on_timeline_event, name="tw.zin.smart_conveyor.timeline"
                )
                carb.log_info("[tw.zin.smart_conveyor] Timeline subscription active (embedded mode).")
        except Exception as _te:
            carb.log_warn(f"[tw.zin.smart_conveyor] Timeline subscription failed: {_te}")

        # Subscribe to Stage events
        try:
            self._stage_sub = omni.usd.get_context().get_stage_event_stream().create_subscription_to_pop(
                self._on_stage_event, name="tw.zin.smart_conveyor.stage_event"
            )
        except Exception as _e:
            carb.log_warn(f"[tw.zin.smart_conveyor] Stage event subscription failed: {_e}")

        # Auto-restore config from the current USD scene (silent if no config prim exists)
        self._usd_auto_load()



    # ------------------------------------------------------------------
    # Model initialization (idempotent)
    # ------------------------------------------------------------------
    def _ensure_models(self):
        """Create all UI data models. Safe to call multiple times - only creates if missing."""
        if not hasattr(self, 'controllers'):
            self.controllers = []          # List of active PCBConveyorController instances
        if not hasattr(self, '_prim_path_model') or self._prim_path_model is None:
            self._prim_path_model = ui.SimpleStringModel("")
        if not hasattr(self, '_enable_inline_model') or self._enable_inline_model is None:
            self._enable_inline_model = ui.SimpleBoolModel(True)
        if not hasattr(self, '_speed_model') or self._speed_model is None:
            self._speed_model = ui.SimpleFloatModel(50.0)
        if not hasattr(self, '_initial_delay_model') or self._initial_delay_model is None:
            self._initial_delay_model = ui.SimpleFloatModel(1.0)
        if not hasattr(self, '_dispatch_interval_model') or self._dispatch_interval_model is None:
            self._dispatch_interval_model = ui.SimpleFloatModel(3.0)
        if not hasattr(self, '_reverse_model') or self._reverse_model is None:
            self._reverse_model = ui.SimpleBoolModel(False)
        if not hasattr(self, '_loop_model') or self._loop_model is None:
            self._loop_model = ui.SimpleBoolModel(False)
        if not hasattr(self, '_visible_at_end_model') or self._visible_at_end_model is None:
            self._visible_at_end_model = ui.SimpleBoolModel(False)
        if not hasattr(self, '_waypoint_models') or not self._waypoint_models:
            self._waypoint_models = [
                self._make_wp_model(0,   0, 0, 0, 0, 0, 0.0, "S"),   # Start
                self._make_wp_model(200, 0, 0, 0, 0, 0, 0.0, "E"),   # End
            ]
        if not hasattr(self, '_batch_pause_model') or self._batch_pause_model is None:
            self._batch_pause_model = ui.SimpleFloatModel(0.0)
        if not hasattr(self, '_offset_x_model') or self._offset_x_model is None:
            self._offset_x_model = ui.SimpleFloatModel(0.0)
        if not hasattr(self, '_offset_y_model') or self._offset_y_model is None:
            self._offset_y_model = ui.SimpleFloatModel(0.0)
        if not hasattr(self, '_offset_z_model') or self._offset_z_model is None:
            self._offset_z_model = ui.SimpleFloatModel(0.0)
        if not hasattr(self, '_offset_rx_model') or self._offset_rx_model is None:
            self._offset_rx_model = ui.SimpleFloatModel(0.0)
        if not hasattr(self, '_offset_ry_model') or self._offset_ry_model is None:
            self._offset_ry_model = ui.SimpleFloatModel(0.0)
        if not hasattr(self, '_offset_rz_model') or self._offset_rz_model is None:
            self._offset_rz_model = ui.SimpleFloatModel(0.0)
        if not hasattr(self, '_multi_line_models') or self._multi_line_models is None:
            self._multi_line_models = [self._make_multi_line_model() for _ in range(5)]
        if not hasattr(self, '_undo_stack') or self._undo_stack is None:
            self._undo_stack = []
        if not hasattr(self, '_redo_stack') or self._redo_stack is None:
            self._redo_stack = []
        if not hasattr(self, '_ml_undo_stack') or self._ml_undo_stack is None:
            self._ml_undo_stack = []
        if not hasattr(self, '_ml_redo_stack') or self._ml_redo_stack is None:
            self._ml_redo_stack = []
            
        if not hasattr(self, '_scene_overrides_models') or self._scene_overrides_models is None:
            self._scene_overrides_models = []
        if not hasattr(self, '_scene_overrides_vbox') or self._scene_overrides_vbox is None:
            self._scene_overrides_vbox = None

    def _make_multi_line_model(self, paths="", config_file=""):
        return {
            "show_settings": ui.SimpleBoolModel(False),
            "override": ui.SimpleBoolModel(False),
            "speed": ui.SimpleFloatModel(50.0),
            "initial_delay": ui.SimpleFloatModel(0.0),
            "dispatch_interval": ui.SimpleFloatModel(2.0),
            "paths": ui.SimpleStringModel(paths),
            "config_file": ui.SimpleStringModel(config_file)
        }

    def _make_scene_override_model(self, path="", enabled=True, override=False, speed=50.0, initial_delay=0.0, dispatch_interval=3.0):
        return {
            "path": ui.SimpleStringModel(path),
            "enabled": ui.SimpleBoolModel(enabled),
            "override": ui.SimpleBoolModel(override),
            "speed": ui.SimpleFloatModel(speed),
            "initial_delay": ui.SimpleFloatModel(initial_delay),
            "dispatch_interval": ui.SimpleFloatModel(dispatch_interval),
            "show_settings": ui.SimpleBoolModel(False)
        }

    def _make_wp_model(self, px, py, pz, rx, ry, rz, pause, name="WP"):
        """Return a dict of SimpleModels for one waypoint."""
        return {
            "name":  ui.SimpleStringModel(str(name)),
            "px":    ui.SimpleFloatModel(float(px)),
            "py":    ui.SimpleFloatModel(float(py)),
            "pz":    ui.SimpleFloatModel(float(pz)),
            "rx":    ui.SimpleFloatModel(float(rx)),
            "ry":    ui.SimpleFloatModel(float(ry)),
            "rz":    ui.SimpleFloatModel(float(rz)),
            "pause": ui.SimpleFloatModel(float(pause)),
        }

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------
    def _set_window_visibility(self, visible):
        if visible:
            if not self._window:
                self._build_ui()
            self._window.visible = True
        else:
            if self._window:
                self._window.visible = False

    def _toggle_window(self):
        if self._window and self._window.visible:
            self._set_window_visibility(False)
        else:
            self._set_window_visibility(True)

    def _build_ui(self):
        self._window = ui.Window(
            "Smart Conveyor Panel",
            width=400, height=640,
            dockPreference=ui.DockPreference.RIGHT_TOP
        )
        self._window.set_visibility_changed_fn(self._on_window_visibility_changed)
        with self._window.frame:
            # 獨立面板模式：在最外層提供全局樣式供內部繼承
            with ui.VStack(style=ZIN_GLOBAL_STYLE if ZIN_GLOBAL_STYLE else {}):
                self.build_ui_layout()

    # ------------------------------------------------------------------
    # Main UI (called by tools_box tab or standalone window)
    # ------------------------------------------------------------------
    def build_ui_layout(self):
        SmartConveyorExtension._primary_instance = self
        self._ensure_models()

        with ui.VStack(spacing=5, padding=8, alignment=ui.Alignment.TOP):
            scroll_frame = ui.ScrollingFrame(
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                height=ui.Fraction(1)
        )
            with scroll_frame:
            # 移除重複綁定，完全依賴外部（Standalone視窗 或 Tools_box）傳遞進來的樣式繼承
                with ui.VStack(spacing=5, alignment=ui.Alignment.TOP):



                    # ══ 1. Template PCB Prim ═════════════════════
                    with ui.CollapsableFrame("Template PCB Prim", collapsed=False, height=0):
                        with ui.VStack(spacing=4, padding=4):
                            with ui.Frame(style={"background_color": 0x33000000,
                                                 "border_radius": 4}):
                                with ui.VStack(spacing=4, padding=6, height=0):
                                    with ui.HStack(height=22, spacing=6):
                                        cb_style = {"background_color": 0xFF1A1A1A, "color": 0xFFDDDDDD, "border_radius": 2}
                                        ui.CheckBox(model=self._enable_inline_model, width=18, height=18, style=cb_style)
                                        ui.Label("Enable Simulation for Inline Prim Paths", style={"color": ARGB_TEXT_PRIMARY, "font_size": 14})
                                    ui.StringField(model=self._prim_path_model, height=22)
                                
                            btn_append = ZinButton(
                                "Append Selection to List",
                                state="correct",
                                clicked_fn=self._pick_from_selection,
                                height=26
                            )
                            btn_append.set_state("correct")

                    # ══ 2 & 6. Speed & Initial Delay ══════════
                    with ui.CollapsableFrame("Speed, Delay & Dispatch",
                                             collapsed=False, height=0):
                        with ui.Frame(style={"background_color": 0x33000000,
                                             "border_radius": 4}):
                            with ui.VStack(spacing=4, padding=6, height=0):
                                with ui.HStack(height=22, spacing=4):
                                    ui.Label("Speed (units/s):", width=ui.Pixel(160),
                                             style={"color": ARGB_TEXT_SECONDARY})
                                    ui.FloatField(model=self._speed_model, height=22)
                                with ui.HStack(height=22, spacing=4):
                                    ui.Label("Initial Delay (s):", width=ui.Pixel(160),
                                             style={"color": ARGB_TEXT_SECONDARY})
                                    ui.FloatField(model=self._initial_delay_model, height=22)
                                with ui.HStack(height=22, spacing=4):
                                    ui.Label("Dispatch Interval (s):", width=ui.Pixel(160),
                                             style={"color": ARGB_TEXT_SECONDARY})
                                    ui.FloatField(model=self._dispatch_interval_model, height=22)

                    # ══ 5 & 7. Behavior at Endpoint ═══════════
                    with ui.CollapsableFrame("Behavior at Endpoint",
                                             collapsed=False, height=0):
                        with ui.Frame(style={"background_color": 0x33000000,
                                             "border_radius": 4}):
                            _cb_style = {"background_color": 0xFF1A1A1A, "color": 0xFFDDDDDD, "border_radius": 2}
                            with ui.VStack(spacing=4, padding=6, height=0):
                                with ui.HStack(height=22, spacing=6):
                                    ui.CheckBox(model=self._reverse_model, width=18, height=18, style=_cb_style)
                                    ui.Label("Reverse direction at endpoint",
                                             style={"color": ARGB_TEXT_PRIMARY})
                                with ui.HStack(height=22, spacing=6):
                                    ui.CheckBox(model=self._loop_model, width=18, height=18, style=_cb_style)
                                    ui.Label("Loop to start at endpoint (repeat)",
                                             style={"color": ARGB_TEXT_PRIMARY})
                                with ui.HStack(height=22, spacing=6):
                                    ui.CheckBox(model=self._visible_at_end_model, width=18, height=18, style=_cb_style)
                                    ui.Label("Visible model at endpoint",
                                             style={"color": ARGB_TEXT_PRIMARY})

                    # ══ 3 & 4. Waypoints ══════════════════════
                    with ui.CollapsableFrame("Waypoints ( Start -> Nodes -> End )",
                                             collapsed=False, height=ui.Fraction(1)) as cf_wp:
                        cf_wp.set_collapsed_changed_fn(lambda c, f=cf_wp: setattr(f, "height", ui.Pixel(0) if c else ui.Fraction(1)))
                        with ui.VStack(spacing=4, padding=4):

                            with ui.HStack(height=26, spacing=4):
                                btn_import = ZinButton("Import Selected as Waypoints", state="correct",
                                                       clicked_fn=self._batch_import_waypoints)
                                btn_import.set_state("correct")

                            ui.Spacer(height=4)
                            with ui.HStack(height=26, spacing=4):
                                btn_slope = ZinButton("Create Smart Slope (Auto Size)", state="correct", clicked_fn=self._open_smart_slope_wizard)
                                btn_slope.set_state("correct")
                            ui.Spacer(height=4)

                            with ui.HStack(height=26, spacing=4):
                                btn_add = ZinButton("+ Add Waypoint", state="default",
                                          clicked_fn=self._add_waypoint)
                                btn_add.set_state("default")
                                btn_remove = ZinButton("- Remove Last",  state="error",
                                          clicked_fn=self._remove_waypoint)
                                btn_remove.set_state("error")
                            
                                self._btn_undo = ZinButton("Undo", state="default", clicked_fn=self._undo)
                                self._btn_undo.set_state("default")
                                self._btn_redo = ZinButton("Redo", state="default", clicked_fn=self._redo)
                                self._btn_redo.set_state("default")
                            
                                btn_reset = ZinButton("Reset All", state="error",
                                          clicked_fn=self._reset_waypoints)
                                btn_reset.set_state("error")
                            
                                self._update_undo_redo_buttons()

                            # --- Batch Tools Section ---
                            with ui.Frame(style={"Frame": {"background_color": 0x33000000, "border_radius": 4}}):
                                with ui.VStack(spacing=4, padding=4):
                                    with ui.HStack(height=26, spacing=4):
                                        ui.Label("Set Pos:", width=64, style={"color": ARGB_TEXT_SECONDARY})
                                        ui.Label("X", width=10, style={"color": ARGB_TEXT_PRIMARY})
                                        ui.FloatField(model=self._offset_x_model, width=ui.Fraction(1), height=22)
                                        btn_set_x = ZinButton("Set", state="default", width=40,
                                                              clicked_fn=lambda: self._apply_batch_set("X"))
                                        ui.Spacer(width=4)
                                        ui.Label("Y", width=10, style={"color": ARGB_TEXT_PRIMARY})
                                        ui.FloatField(model=self._offset_y_model, width=ui.Fraction(1), height=22)
                                        btn_set_y = ZinButton("Set", state="default", width=40,
                                                              clicked_fn=lambda: self._apply_batch_set("Y"))
                                        ui.Spacer(width=4)
                                        ui.Label("Z", width=10, style={"color": ARGB_TEXT_PRIMARY})
                                        ui.FloatField(model=self._offset_z_model, width=ui.Fraction(1), height=22)
                                        btn_set_z = ZinButton("Set", state="default", width=40,
                                                              clicked_fn=lambda: self._apply_batch_set("Z"))
                                                          
                                    with ui.HStack(height=26, spacing=4):
                                        ui.Label("Set Rot:", width=64, style={"color": ARGB_TEXT_SECONDARY})
                                        ui.Label("X", width=10, style={"color": 0xFF88AAFF})
                                        ui.FloatField(model=self._offset_rx_model, width=ui.Fraction(1), height=22)
                                        btn_set_rx = ZinButton("Set", state="default", width=40,
                                                               clicked_fn=lambda: self._apply_batch_set("RX"))
                                        ui.Spacer(width=4)
                                        ui.Label("Y", width=10, style={"color": 0xFF88AAFF})
                                        ui.FloatField(model=self._offset_ry_model, width=ui.Fraction(1), height=22)
                                        btn_set_ry = ZinButton("Set", state="default", width=40,
                                                               clicked_fn=lambda: self._apply_batch_set("RY"))
                                        ui.Spacer(width=4)
                                        ui.Label("Z", width=10, style={"color": 0xFF88AAFF})
                                        ui.FloatField(model=self._offset_rz_model, width=ui.Fraction(1), height=22)
                                        btn_set_rz = ZinButton("Set", state="default", width=40,
                                                               clicked_fn=lambda: self._apply_batch_set("RZ"))
                                                           
                                    with ui.HStack(height=26, spacing=4):
                                        ui.Label("Batch Pause (s):", width=100, style={"color": ARGB_TEXT_SECONDARY})
                                        ui.FloatField(model=self._batch_pause_model, width=ui.Fraction(1), height=22)
                                        btn_apply_pause = ZinButton("Apply All", state="default", width=80,
                                                                    clicked_fn=self._apply_batch_pause)
                            # ---------------------------

                            # Column header
                            with ui.Frame(style={"background_color": 0x22000000,
                                                 "border_radius": 2}):
                                with ui.HStack(height=20, spacing=2):
                                    ui.Label("Item", width=28, style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.CENTER})
                                    ui.Label("Pick",   width=48,
                                             style={"font_size": 13, "color": ARGB_TEXT_PRIMARY})
                                    ui.Spacer(width=84)
                                    ui.Label("Name",   width=ui.Fraction(1),
                                             style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.LEFT_CENTER})
                                    ui.Label("Pos X",  width=56,
                                             style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.LEFT_CENTER})
                                    ui.Label("Pos Y",  width=56,
                                             style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.LEFT_CENTER})
                                    ui.Label("Pos Z",  width=56,
                                             style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.LEFT_CENTER})
                                    ui.Label("Rot X",  width=48,
                                             style={"font_size": 13, "color": 0xFF88AAFF, "alignment": ui.Alignment.LEFT_CENTER})
                                    ui.Label("Rot Y",  width=48,
                                             style={"font_size": 13, "color": 0xFF88AAFF, "alignment": ui.Alignment.LEFT_CENTER})
                                    ui.Label("Rot Z",  width=48,
                                             style={"font_size": 13, "color": 0xFF88AAFF, "alignment": ui.Alignment.LEFT_CENTER})
                                    ui.Label("Pause",  width=48,
                                             style={"font_size": 13, "color": ARGB_TEXT_SECONDARY})

                            # Scrollable rows
                            with ui.ScrollingFrame(height=ui.Fraction(1)):
                                self._waypoints_vstack = ui.VStack(spacing=2)
                                self._rebuild_waypoints_ui()

                    # ── Multi-Line Orchestrator ─────────────────────
                    with ui.CollapsableFrame("Multi-Line Orchestrator (External JSONs)",
                                             name="group",
                                             collapsed=True, height=ui.Pixel(0)) as cf_ml:
                        cf_ml.set_collapsed_changed_fn(lambda c, f=cf_ml: setattr(f, "height", ui.Pixel(0) if c else ui.Fraction(1)))
                        with ui.VStack(spacing=4, padding=4):
                            with ui.HStack(height=26, spacing=4):
                                btn_add = ZinButton("+ Add Line", state="default", clicked_fn=self._add_multi_line)
                                btn_add.set_state("default")
                                btn_rem = ZinButton("- Remove Line", state="default", clicked_fn=self._remove_multi_line)
                                btn_rem.set_state("default")
                            
                                btn_undo = ZinButton("Undo", state="default", clicked_fn=self._ml_undo)
                                btn_undo.set_state("default")
                                btn_redo = ZinButton("Redo", state="default", clicked_fn=self._ml_redo)
                                btn_redo.set_state("default")
                                btn_reset = ZinButton("Reset All", state="error", clicked_fn=self._ml_reset)
                                btn_reset.set_state("error")

                            with ui.Frame(style={"background_color": 0x22000000, "border_radius": 2}):
                                with ui.HStack(height=20, spacing=2):
                                    ui.Label("Item", width=28, style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.CENTER})
                                    ui.Label("En", width=24, style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.CENTER})
                                    ui.Label("Opt", width=32, style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.CENTER})
                                    ui.Label("Pick", width=48, style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.CENTER})
                                    ui.Label("Prim Paths (comma separated)", width=ui.Fraction(0.4), style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.LEFT_CENTER})
                                    ui.Label("Config File Path (.json)", width=ui.Fraction(0.6), style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.LEFT_CENTER})
                        
                            with ui.ScrollingFrame(height=ui.Fraction(1)):
                                self._multi_lines_vstack = ui.VStack(spacing=2)
                                self._rebuild_multi_line_ui()

                    # ── Scene Overrides (Referenced Lines) ────────────────
                    with ui.CollapsableFrame("Scene Overrides (Referenced Lines)",
                                             name="group",
                                             collapsed=True, height=ui.Pixel(0)) as cf_so:
                        cf_so.set_collapsed_changed_fn(lambda c, f=cf_so: setattr(f, "height", ui.Pixel(0) if c else ui.Fraction(1)))
                        with ui.VStack(spacing=4, padding=4):
                            with ui.HStack(height=26, spacing=4):
                                btn_scan = ZinButton("Scan Referenced Lines", state="correct", clicked_fn=self._scan_referenced_lines)
                                btn_scan.set_state("correct")

                            with ui.Frame(style={"background_color": 0x22000000, "border_radius": 2}):
                                with ui.HStack(height=20, spacing=2):
                                    ui.Label("Item", width=30, style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.CENTER})
                                    ui.Label("En", width=24, style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.CENTER})
                                    ui.Label("Opt", width=24, style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.CENTER})
                                    ui.Label("Referenced Line Path", width=ui.Fraction(1), style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.LEFT_CENTER})
                                    ui.Label("Set", width=30, style={"font_size": 13, "color": ARGB_TEXT_PRIMARY, "alignment": ui.Alignment.CENTER})
                        
                            with ui.ScrollingFrame(height=ui.Fraction(1)):
                                self._scene_overrides_vbox = ui.VStack(spacing=2)
                                self._rebuild_scene_overrides_ui()


            with ui.VStack(height=0, spacing=5):
                # ── Status bar ─────────────────────────────
                with ui.Frame(style={"background_color": 0x44000000, "border_radius": 4}):
                    with ui.HStack(height=22, spacing=6, style={"margin": 4}):
                        self._status_label = ui.Label(
                            "Status: Idle",
                            style={"font_size": 14, "color": ARGB_TEXT_PRIMARY},
                            word_wrap=True
                        )


                # ── Start / Stop / Save to USD ───────────────
                with ui.HStack(height=28, spacing=6):
                    btn_start = ZinButton("Start",           state="correct", clicked_fn=self.start_sim)
                    btn_start.set_state("correct")
                    btn_stop = ZinButton("Stop",            state="error",   clicked_fn=self.stop_sim)
                    btn_stop.set_state("error")
                    btn_save_usd = ZinButton("Save to USD",     state="default", clicked_fn=self._usd_save_config)
                    btn_save_usd.set_state("default")

                # ── JSON File Management ──────────────────────
                with ui.HStack(height=28, spacing=6):
                    btn_load = ZinButton("Load JSON",  state="default", clicked_fn=self._on_load_clicked)
                    btn_load.set_state("default")
                    btn_save_json = ZinButton("Save JSON",  state="default", clicked_fn=self._on_save_clicked)
                    btn_save_json.set_state("default")

                ui.Spacer(height=4)

        return scroll_frame

    # ------------------------------------------------------------------
    # Smart Slope & Waypoint Helpers
    # ------------------------------------------------------------------
    def _get_pcb_length(self, prim_paths_str: str) -> float:
        stage = omni.usd.get_context().get_stage()
        if not stage or not prim_paths_str:
            return 65.0
            
        first_path = prim_paths_str.split(',')[0].strip()
        prim = stage.GetPrimAtPath(first_path)
        if not prim.IsValid():
            return 65.0
            
        import math
        from pxr import UsdGeom, Usd
        bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
        bounds = bbox_cache.ComputeWorldBound(prim)
        aligned_range = bounds.ComputeAlignedRange()
        
        size = aligned_range.GetSize()
        max_len = max(size[0], size[1])
        if max_len <= 0 or math.isinf(max_len):
            return 65.0
        return float(max_len)

    def _init_slope_wp_models(self):
        if not hasattr(self, "_slope_wp_models"):
            self._slope_wp_models = [
                self._make_wp_model(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "Start"),
                self._make_wp_model(200.0, 0.0, 50.0, 0.0, 0.0, 0.0, 0.0, "End")
            ]

    def _open_smart_slope_wizard(self):
        self._init_slope_wp_models()
        if hasattr(self, "_smart_slope_window") and self._smart_slope_window:
            self._smart_slope_window.visible = True
            self._rebuild_slope_waypoints_ui()
            return

        self._smart_slope_window = ui.Window("Smart Slope Generator", width=550, height=350, visible=True)
        with self._smart_slope_window.frame:
            with ui.VStack(spacing=8, padding=10):
                ui.Label("This wizard generates waypoints for smooth slope transitions. Use the list below to define the path, picking coordinates directly from your 3D scene.", word_wrap=True, style={"color": 0xFFAAAAAA, "font_size": 14})
                
                ui.Spacer(height=4)
                
                self._slope_wp_list_frame = ui.VStack(spacing=4)
                self._rebuild_slope_waypoints_ui()
                
                ui.Spacer(height=4)
                with ui.HStack(height=26, spacing=4):
                    btn_add = ZinButton("+ Add Point", state="default", clicked_fn=self._add_slope_waypoint)
                    btn_add.set_state("default")
                    
                ui.Spacer(height=4)
                with ui.HStack(height=24, spacing=4):
                    ui.Label("Slope Z-Offset:", width=100, style={"color": ARGB_TEXT_PRIMARY})
                    if not hasattr(self, "_slope_z_offset_model"):
                        self._slope_z_offset_model = ui.SimpleFloatModel()
                        self._slope_z_offset_model.set_value(0.0)
                    ui.FloatField(model=self._slope_z_offset_model)
                    ui.Label("(Adjust if floating)", style={"color": 0xFF888888, "font_size": 12})
                    
                ui.Spacer(height=10)
                btn_gen = ZinButton("Generate Smart Slope", state="correct", clicked_fn=self._generate_smart_slope)
                btn_gen.set_state("correct")

    def _rebuild_slope_waypoints_ui(self):
        if not hasattr(self, "_slope_wp_list_frame") or not self._slope_wp_list_frame:
            return
            
        self._slope_wp_list_frame.clear()
        with self._slope_wp_list_frame:
            for i, wp_model in enumerate(self._slope_wp_models):
                with ui.HStack(height=24, spacing=4):
                    if "enabled" not in wp_model:
                        wp_model["enabled"] = ui.SimpleBoolModel(True)
                    ui.CheckBox(wp_model["enabled"], width=16)
                    
                    def make_pick_handler(idx):
                        return lambda: self._pick_slope_waypoint(idx)
                    btn_pick = ZinButton("Pick", state="default", clicked_fn=make_pick_handler(i))
                    btn_pick.set_state("default")
                    
                    ui.Label(f"P{i+1}:", width=25, style={"color": ARGB_TEXT_PRIMARY})
                    
                    ui.FloatField(model=wp_model["px"])
                    ui.FloatField(model=wp_model["py"])
                    ui.FloatField(model=wp_model["pz"])
                    
                    def make_up_handler(idx):
                        return lambda: self._move_slope_waypoint_up(idx)
                    btn_up = ZinButton("Up", state="default", clicked_fn=make_up_handler(i))
                    btn_up.set_state("default")
                    
                    def make_dn_handler(idx):
                        return lambda: self._move_slope_waypoint_down(idx)
                    btn_dn = ZinButton("Dn", state="default", clicked_fn=make_dn_handler(i))
                    btn_dn.set_state("default")
                    
                    def make_del_handler(idx):
                        return lambda: self._remove_slope_waypoint_at(idx)
                    btn_del = ZinButton("Del", state="error", clicked_fn=make_del_handler(i))
                    btn_del.set_state("error")

    def _defer_slope_rebuild(self):
        """延遲到下一幀才重建 Slope Wizard UI，避免在按鈕回呼中直接清除 UI 樹造成崩潰。"""
        import asyncio
        import omni.kit.app
        async def _deferred():
            await omni.kit.app.get_app().next_update_async()
            self._rebuild_slope_waypoints_ui()
        asyncio.ensure_future(_deferred())

    def _add_slope_waypoint(self):
        self._slope_wp_models.append(self._make_wp_model(0,0,0, 0,0,0, 0, f"Point {len(self._slope_wp_models)+1}"))
        self._defer_slope_rebuild()

    def _remove_slope_waypoint_at(self, idx):
        if 0 <= idx < len(self._slope_wp_models):
            self._slope_wp_models.pop(idx)
            self._defer_slope_rebuild()

    def _move_slope_waypoint_up(self, idx):
        if idx > 0:
            self._slope_wp_models[idx], self._slope_wp_models[idx-1] = self._slope_wp_models[idx-1], self._slope_wp_models[idx]
            self._defer_slope_rebuild()

    def _move_slope_waypoint_down(self, idx):
        if idx < len(self._slope_wp_models) - 1:
            self._slope_wp_models[idx], self._slope_wp_models[idx+1] = self._slope_wp_models[idx+1], self._slope_wp_models[idx]
            self._defer_slope_rebuild()

    def _pick_slope_waypoint(self, idx):
        import omni.usd
        ctx = omni.usd.get_context()
        sel = ctx.get_selection().get_selected_prim_paths()
        if not sel:
            self._update_status("Please select a prim first.", 0xFFFF4444)
            return
            
        prim_path = sel[0]
        stage = ctx.get_stage()
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            return
            
        mat = omni.usd.get_world_transform_matrix(prim)
        pos = mat.ExtractTranslation()
        self._slope_wp_models[idx]["px"].set_value(float(pos[0]))
        self._slope_wp_models[idx]["py"].set_value(float(pos[1]))
        self._slope_wp_models[idx]["pz"].set_value(float(pos[2]))

    def _generate_smart_slope(self):
        enabled_wps = [wp for wp in self._slope_wp_models if wp.get("enabled", ui.SimpleBoolModel(True)).get_value_as_bool()]
        
        if len(enabled_wps) < 2:
            self._update_status("Error: Need at least 2 enabled points to generate a slope.", 0xFFFF4444)
            return
            
        pcb_len = self._get_pcb_length(self._prim_path_model.get_value_as_string())
        offset_dist = pcb_len / 2.0
        
        slope_offset_z = self._slope_z_offset_model.get_value_as_float()
        
        import math
        from pxr import Gf
        
        self._save_undo_snapshot()
        
        pts = []
        for wp in enabled_wps:
            pts.append([
                wp["px"].get_value_as_float(),
                wp["py"].get_value_as_float(),
                wp["pz"].get_value_as_float()
            ])
            
        N = len(pts)
        
        dirs_3d = []
        dirs_2d = []
        yaws = []
        pitches = []
        slope_lens = []
        
        for i in range(N - 1):
            sx, sy, sz = pts[i]
            ex, ey, ez = pts[i+1]
            dx, dy, dz = ex - sx, ey - sy, ez - sz
            h_dist = math.sqrt(dx*dx + dy*dy)
            slope_len = math.sqrt(dx*dx + dy*dy + dz*dz)
            
            if h_dist < 1e-5:
                if i > 0:
                    dirs_3d.append(dirs_3d[-1])
                    dirs_2d.append(dirs_2d[-1])
                    yaws.append(yaws[-1])
                    pitches.append(pitches[-1])
                    slope_lens.append(slope_len)
                else:
                    dirs_3d.append([1.0, 0.0, 0.0])
                    dirs_2d.append([1.0, 0.0])
                    yaws.append(0.0)
                    pitches.append(0.0)
                    slope_lens.append(slope_len)
                continue
                
            yaw = math.degrees(math.atan2(dy, dx))
            pitch = -math.degrees(math.atan2(dz, h_dist))
            
            dirs_3d.append([dx/slope_len, dy/slope_len, dz/slope_len])
            dirs_2d.append([dx/h_dist, dy/h_dist])
            yaws.append(yaw)
            pitches.append(pitch)
            slope_lens.append(slope_len)
            
        def get_z_off(p):
            return slope_offset_z if abs(p) > 1.0 else 0.0

        p0 = pts[0]
        off_0 = min(offset_dist, slope_lens[0] / 2.0) if slope_lens[0] > 0 else offset_dist
        dir2d_0 = dirs_2d[0]
        dir3d_0 = dirs_3d[0]
        
        wp_approach = [p0[0] - dir2d_0[0] * offset_dist, p0[1] - dir2d_0[1] * offset_dist, p0[2]]
        wp_start = [p0[0] + dir3d_0[0] * off_0, p0[1] + dir3d_0[1] * off_0, p0[2] + dir3d_0[2] * off_0 + get_z_off(pitches[0])]
        
        self._waypoint_models.append(self._make_wp_model(
            wp_approach[0], wp_approach[1], wp_approach[2],
            0.0, 0.0, yaws[0], 0.0, "S_Flat_In"
        ))
        self._waypoint_models.append(self._make_wp_model(
            wp_start[0], wp_start[1], wp_start[2],
            0.0, pitches[0], yaws[0], 0.0, "S_Tilt_Out"
        ))
        
        for i in range(1, N - 1):
            p_i = pts[i]
            
            off_in = min(offset_dist, slope_lens[i-1] / 2.0) if slope_lens[i-1] > 0 else offset_dist
            off_out = min(offset_dist, slope_lens[i] / 2.0) if slope_lens[i] > 0 else offset_dist
            
            d3d_in = dirs_3d[i-1]
            wp_before = [p_i[0] - d3d_in[0] * off_in, p_i[1] - d3d_in[1] * off_in, p_i[2] - d3d_in[2] * off_in + get_z_off(pitches[i-1])]
            
            d3d_out = dirs_3d[i]
            wp_after = [p_i[0] + d3d_out[0] * off_out, p_i[1] + d3d_out[1] * off_out, p_i[2] + d3d_out[2] * off_out + get_z_off(pitches[i])]
            
            self._waypoint_models.append(self._make_wp_model(
                wp_before[0], wp_before[1], wp_before[2],
                0.0, pitches[i-1], yaws[i-1], 0.0, f"P{i+1}_In"
            ))
            self._waypoint_models.append(self._make_wp_model(
                wp_after[0], wp_after[1], wp_after[2],
                0.0, pitches[i], yaws[i], 0.0, f"P{i+1}_Out"
            ))
            
        pn = pts[-1]
        off_n = min(offset_dist, slope_lens[-1] / 2.0) if slope_lens[-1] > 0 else offset_dist
        dir2d_n = dirs_2d[-1]
        dir3d_n = dirs_3d[-1]
        
        wp_end = [pn[0] - dir3d_n[0] * off_n, pn[1] - dir3d_n[1] * off_n, pn[2] - dir3d_n[2] * off_n + get_z_off(pitches[-1])]
        wp_depart = [pn[0] + dir2d_n[0] * offset_dist, pn[1] + dir2d_n[1] * offset_dist, pn[2]]
        
        self._waypoint_models.append(self._make_wp_model(
            wp_end[0], wp_end[1], wp_end[2],
            0.0, pitches[-1], yaws[-1], 0.0, "E_Tilt_In"
        ))
        self._waypoint_models.append(self._make_wp_model(
            wp_depart[0], wp_depart[1], wp_depart[2],
            0.0, 0.0, yaws[-1], 0.0, "E_Flat_Out"
        ))

        self._rebuild_waypoints_ui()
        if hasattr(self, "_smart_slope_window"):
            self._smart_slope_window.visible = False
            
        self._update_status(f"Smart Slope generated! ({N-1} segments, PCB length: {pcb_len:.1f}cm)", 0xFF44CC44)

    # ------------------------------------------------------------------
    # Waypoint helpers
    # ------------------------------------------------------------------
    def _update_undo_redo_buttons(self):
        # ZinButton loses its custom hover/active style when disabled,
        # so we keep them always enabled to match the Add Waypoint button's UI.
        pass

    def _get_current_snapshot(self):
        snapshot = []
        for wp in self._waypoint_models:
            snapshot.append({
                "name": wp["name"].get_value_as_string(),
                "px": wp["px"].get_value_as_float(),
                "py": wp["py"].get_value_as_float(),
                "pz": wp["pz"].get_value_as_float(),
                "rx": wp["rx"].get_value_as_float(),
                "ry": wp["ry"].get_value_as_float(),
                "rz": wp["rz"].get_value_as_float(),
                "pause": wp["pause"].get_value_as_float(),
            })
        return snapshot

    def _save_undo_snapshot(self):
        self._undo_stack.append(self._get_current_snapshot())
        self._redo_stack.clear()
        self._update_undo_redo_buttons()

    def _restore_snapshot(self, snapshot):
        self._waypoint_models.clear()
        for data in snapshot:
            self._waypoint_models.append(self._make_wp_model(
                data["px"], data["py"], data["pz"],
                data["rx"], data["ry"], data["rz"], data["pause"], data["name"]
            ))
        
        import asyncio
        import omni.kit.app
        async def defer_rebuild():
            await omni.kit.app.get_app().next_update_async()
            self._rebuild_waypoints_ui()
            self._update_undo_redo_buttons()
        asyncio.ensure_future(defer_rebuild())

    def _undo(self):
        if not self._undo_stack: return
        self._redo_stack.append(self._get_current_snapshot())
        state = self._undo_stack.pop()
        self._restore_snapshot(state)
        self._update_status("Undo successful.", 0xFF44CC44)

    def _redo(self):
        if not self._redo_stack: return
        self._undo_stack.append(self._get_current_snapshot())
        state = self._redo_stack.pop()
        self._restore_snapshot(state)
        self._update_status("Redo successful.", 0xFF44CC44)

    def _rebuild_waypoints_ui(self):
        if not hasattr(self, '_waypoints_vstack') or not self._waypoints_vstack:
            return
        self._waypoints_vstack.clear()
        count = len(self._waypoint_models)
        with self._waypoints_vstack:
            for i, wp in enumerate(self._waypoint_models):
                if "name" not in wp:
                    if i == 0: n = "S"
                    elif i == count - 1: n = "E"
                    else: n = str(i)
                    wp["name"] = ui.SimpleStringModel(n)
                if "selected" not in wp:
                    wp["selected"] = ui.SimpleBoolModel(False)

                row_bg = 0x18FFFFFF if i % 2 == 0 else 0x00000000
                with ui.Frame(style={"Frame": {"background_color": row_bg}}):
                    with ui.HStack(height=24, spacing=2):
                        with ui.Frame(width=28):
                            with ui.HStack():
                                ui.Spacer()
                                ui.CheckBox(model=wp["selected"], width=16)
                                ui.Spacer()

                        def make_pick_handler(target_wp):
                            return lambda: self._pick_waypoint_from_selection(target_wp)
                        
                        btn_pick = ZinButton("Pick", state="default", clicked_fn=make_pick_handler(wp), width=48, height=24)
                        btn_pick.set_state("default")

                        def make_move_up_handler(idx):
                            return lambda: self._move_waypoint(idx, max(0, idx - 1))
                        def make_move_down_handler(idx):
                            return lambda: self._move_waypoint(idx, min(count - 1, idx + 1))
                            
                        btn_up = ZinButton("Up", state="default", clicked_fn=make_move_up_handler(i), width=24, height=24, tooltip="Move Up")
                        btn_up.set_state("default")
                        btn_down = ZinButton("Dn", state="default", clicked_fn=make_move_down_handler(i), width=24, height=24, tooltip="Move Down")
                        btn_down.set_state("default")
                        
                        def make_del_handler(idx):
                            return lambda: self._remove_specific_waypoint(idx)
                        btn_del = ZinButton("Del", state="error", clicked_fn=make_del_handler(i), width=24, height=24, tooltip="Delete Waypoint")
                        btn_del.set_state("error")

                        _f_style = {"alignment": ui.Alignment.LEFT_CENTER}
                        ui.StringField(model=wp["name"], width=ui.Fraction(1), height=24, style=_f_style)
                        ui.FloatField(model=wp["px"], width=56, height=24, style=_f_style)
                        ui.FloatField(model=wp["py"], width=56, height=24, style=_f_style)
                        ui.FloatField(model=wp["pz"], width=56, height=24, style=_f_style)
                        ui.FloatField(model=wp["rx"], width=48, height=24, style=_f_style)
                        ui.FloatField(model=wp["ry"], width=48, height=24, style=_f_style)
                        ui.FloatField(model=wp["rz"], width=48, height=24, style=_f_style)
                        ui.FloatField(model=wp["pause"], width=48, height=24)

    def _move_waypoint(self, source_idx, target_idx):
        if source_idx < 0 or source_idx >= len(self._waypoint_models): return
        if target_idx < 0 or target_idx >= len(self._waypoint_models): return
        if source_idx == target_idx: return
        
        self._save_undo_snapshot()
        item = self._waypoint_models.pop(source_idx)
        self._waypoint_models.insert(target_idx, item)
        
        import asyncio
        import omni.kit.app
        async def defer_rebuild():
            await omni.kit.app.get_app().next_update_async()
            self._rebuild_waypoints_ui()
            self._update_undo_redo_buttons()
            
        asyncio.ensure_future(defer_rebuild())

    def _remove_specific_waypoint(self, idx):
        if len(self._waypoint_models) <= 2:
            self._update_status("Min 2 waypoints required!", 0xFF0044FF)
            return
        if idx < 0 or idx >= len(self._waypoint_models):
            return
        
        self._save_undo_snapshot()
        self._waypoint_models.pop(idx)
        
        import asyncio
        import omni.kit.app
        async def defer_rebuild():
            await omni.kit.app.get_app().next_update_async()
            self._rebuild_waypoints_ui()
            self._update_undo_redo_buttons()
            
        asyncio.ensure_future(defer_rebuild())

    def _pick_waypoint_from_selection(self, wp_model):
        """讀取目前選取物件的 World Transform 並填入該列 wp_model"""
        paths = omni.usd.get_context().get_selection().get_selected_prim_paths()
        if not paths:
            self._update_status("Pick failed: No object selected!", 0xFFFF4444)
            carb.log_warn("[tw.zin.smart_conveyor] Pick failed: No object selected.")
            return

        prim_path = paths[0]
        pos, rot = self._get_world_transform(prim_path)
        if pos is None or rot is None:
            self._update_status(f"Pick failed: Could not get transform for {prim_path}", 0xFFFF4444)
            return

        self._save_undo_snapshot()
        wp_model["px"].set_value(float(pos[0]))
        wp_model["py"].set_value(float(pos[1]))
        wp_model["pz"].set_value(float(pos[2]))
        wp_model["rx"].set_value(float(rot[0]))
        wp_model["ry"].set_value(float(rot[1]))
        wp_model["rz"].set_value(float(rot[2]))
        
        self._update_status(f"Picked transform from {prim_path}", 0xFF44CC44)

    def _get_world_transform(self, prim_path: str):
        """輔助函式：取得相對於目標產線(Template PCB 父層)的局部座標與旋轉角度(Euler XYZ in degrees)"""
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return None, None
            
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            return None, None
            
        world_transform = omni.usd.get_world_transform_matrix(prim)
        
        # 轉換為局部座標：取得目前 UI 設定的 Template PCB，反推其父層的 World Matrix Inverse
        ref_inv_mat = Gf.Matrix4d(1.0)
        template_path = self._prim_path_model.get_value_as_string().split(",")[0].strip()
        if template_path:
            tpl_prim = stage.GetPrimAtPath(template_path)
            if tpl_prim and tpl_prim.GetParent():
                parent = tpl_prim.GetParent()
                if parent.GetPath() != "/":
                    from pxr import UsdGeom, Usd
                    time = _omni_timeline.get_timeline_interface().get_current_time() if _omni_timeline else 0.0
                    cache = UsdGeom.XformCache(Usd.TimeCode(time))
                    ref_inv_mat = cache.GetLocalToWorldTransform(parent).GetInverse()
                    
        local_mat = world_transform * ref_inv_mat
        
        pos = local_mat.ExtractTranslation()
        
        # 分解旋轉矩陣為 XYZ 尤拉角 (degrees)
        rot_q = local_mat.ExtractRotation()
        rot_euler = rot_q.Decompose(Gf.Vec3d.XAxis(), Gf.Vec3d.YAxis(), Gf.Vec3d.ZAxis())
        
        return pos, rot_euler

    def _add_waypoint(self):
        """Append a new waypoint copying position from the last one."""
        self._save_undo_snapshot()
        if self._waypoint_models:
            last = self._waypoint_models[-1]
            new_wp = self._make_wp_model(
                last["px"].get_value_as_float(), last["py"].get_value_as_float(),
                last["pz"].get_value_as_float(), last["rx"].get_value_as_float(),
                last["ry"].get_value_as_float(), last["rz"].get_value_as_float(), 0.0
            )
        else:
            new_wp = self._make_wp_model(0, 0, 0, 0, 0, 0, 0.0)
        self._waypoint_models.append(new_wp)
        self._rebuild_waypoints_ui()

    def _remove_waypoint(self):
        """Remove selected waypoints, or the last one if none selected. Minimum 2 waypoints required."""
        if len(self._waypoint_models) <= 2:
            self._update_status("Min 2 waypoints required!", 0xFF0044FF)
            return
            
        self._save_undo_snapshot()
        
        to_remove = [wp for wp in self._waypoint_models if wp.get("selected") and wp["selected"].get_value_as_bool()]
        
        if to_remove:
            for wp in to_remove:
                if len(self._waypoint_models) > 2:
                    self._waypoint_models.remove(wp)
        else:
            self._waypoint_models.pop()
            
        self._rebuild_waypoints_ui()

    def _reset_waypoints(self):
        """Reset the waypoints list to the default Start and End points."""
        self._save_undo_snapshot()
        self._waypoint_models.clear()
        self._waypoint_models = [
            self._make_wp_model(0,   0, 0, 0, 0, 0, 0.0, "S"),   # Start
            self._make_wp_model(100, 0, 0, 0, 0, 0, 0.0, "E"),   # End
        ]
        self._rebuild_waypoints_ui()
        self._update_status("Waypoints reset to default.", 0xFF44CC44)
        carb.log_info("[tw.zin.smart_conveyor] Waypoints reset to default.")

    def _batch_import_waypoints(self):
        """Batch import waypoints from selected prims, expanding children if exactly 1 prim is selected."""
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return

        selected_paths = omni.usd.get_context().get_selection().get_selected_prim_paths()
        if not selected_paths:
            self._update_status("Import failed: No object selected!", 0xFFFF4444)
            carb.log_warn("[tw.zin.smart_conveyor] Batch import failed: No object selected.")
            return

        # 1. Expand single group selection
        if len(selected_paths) == 1:
            prim = stage.GetPrimAtPath(selected_paths[0])
            if prim and prim.IsValid():
                children = prim.GetChildren()
                if children:
                    selected_paths = [child.GetPath().pathString for child in children]
                    carb.log_info(f"[tw.zin.smart_conveyor] Expanded group {prim.GetPath().pathString} into {len(selected_paths)} children.")



        # 3. Create Waypoint models
        new_models = []
        for path in selected_paths:
            pos, rot = self._get_world_transform(path)
            if pos is not None and rot is not None:
                prim_name = path.split('/')[-1]
                new_models.append(
                    self._make_wp_model(pos[0], pos[1], pos[2], rot[0], rot[1], rot[2], 0.0, prim_name)
                )

        # 4. Apply and Update UI
        if new_models:
            self._save_undo_snapshot()
            self._waypoint_models.extend(new_models)
            self._rebuild_waypoints_ui()
            self._update_undo_redo_buttons()
            self._update_status(f"Imported {len(new_models)} Waypoints successfully.", 0xFF44CC44)
            carb.log_info(f"[tw.zin.smart_conveyor] Batch imported {len(new_models)} waypoints.")
        else:
            self._update_status("Import failed: No valid Prims found.", 0xFFFF4444)

    def _apply_batch_pause(self):
        """Apply the batch pause value to all waypoints."""
        if len(self._waypoint_models) < 2:
            return
        self._save_undo_snapshot()
        new_pause = self._batch_pause_model.get_value_as_float()
        updated_count = 0
        
        for wp in self._waypoint_models:
            wp["pause"].set_value(new_pause)
            updated_count += 1
                
        self._update_status(f"Applied {new_pause}s pause to {updated_count} nodes.", 0xFF44CC44)
        carb.log_info(f"[tw.zin.smart_conveyor] Batch applied pause {new_pause}s to {updated_count} nodes.")

    def _apply_batch_set(self, axis: str):
        """Apply the batch offset value to a specific axis across all waypoints."""
        if not self._waypoint_models:
            return
        self._save_undo_snapshot()
        
        if axis == "X":
            val = self._offset_x_model.get_value_as_float()
            for wp in self._waypoint_models:
                wp["px"].set_value(val)
        elif axis == "Y":
            val = self._offset_y_model.get_value_as_float()
            for wp in self._waypoint_models:
                wp["py"].set_value(val)
        elif axis == "Z":
            val = self._offset_z_model.get_value_as_float()
            for wp in self._waypoint_models:
                wp["pz"].set_value(val)
        elif axis == "RX":
            val = self._offset_rx_model.get_value_as_float()
            for wp in self._waypoint_models:
                wp["rx"].set_value(val)
        elif axis == "RY":
            val = self._offset_ry_model.get_value_as_float()
            for wp in self._waypoint_models:
                wp["ry"].set_value(val)
        elif axis == "RZ":
            val = self._offset_rz_model.get_value_as_float()
            for wp in self._waypoint_models:
                wp["rz"].set_value(val)
            
        self._rebuild_waypoints_ui()
        self._update_status(f"Set all {axis} coordinates to: {val:.1f}", 0xFF44CC44)
        carb.log_info(f"[tw.zin.smart_conveyor] Batch set {axis}={val} to {len(self._waypoint_models)} nodes.")

    # ------------------------------------------------------------------
    # Multi-Line Helpers
    # ------------------------------------------------------------------
    def _rebuild_multi_line_ui(self):
        if not hasattr(self, '_multi_lines_vstack') or not self._multi_lines_vstack:
            return
        self._multi_lines_vstack.clear()
        with self._multi_lines_vstack:
            for i, model in enumerate(self._multi_line_models):
                if "show_settings" not in model:
                    model["show_settings"] = ui.SimpleBoolModel(False)
                    model["override"] = ui.SimpleBoolModel(False)
                    model["speed"] = ui.SimpleFloatModel(50.0)
                    model["initial_delay"] = ui.SimpleFloatModel(0.0)
                    model["dispatch_interval"] = ui.SimpleFloatModel(2.0)
                if "selected" not in model:
                    model["selected"] = ui.SimpleBoolModel(False)
                if "enabled" not in model:
                    model["enabled"] = ui.SimpleBoolModel(True)
                    
                row_bg = 0x18FFFFFF if i % 2 == 0 else 0x00000000
                with ui.Frame(style={"Frame": {"background_color": row_bg}}):
                    with ui.VStack(spacing=2):
                        with ui.HStack(height=24, spacing=2):
                            with ui.Frame(width=28):
                                with ui.HStack():
                                    ui.Spacer()
                                    ui.CheckBox(model=model["selected"], width=16)
                                    ui.Spacer()
                            with ui.Frame(width=24):
                                with ui.HStack():
                                    ui.Spacer()
                                    ui.CheckBox(model=model["enabled"], width=16)
                                    ui.Spacer()
                            def make_toggle_handler(target_model):
                                def toggle():
                                    current = target_model["show_settings"].get_value_as_bool()
                                    target_model["show_settings"].set_value(not current)
                                return toggle
                                
                            btn_gear = ZinButton("Opt", state="default", clicked_fn=make_toggle_handler(model), width=32, height=24)
                            btn_gear.set_state("default")
                            
                            def make_browse_handler(target_model):
                                return lambda: self._pick_json_for_line(target_model)
                            
                            btn = ZinButton("Pick", state="default", clicked_fn=make_browse_handler(model), width=48, height=24)
                            btn.set_state("default")
                            
                            field_paths = ui.StringField(model=model["paths"], width=ui.Fraction(0.4), height=24)
                            field_config = ui.StringField(model=model["config_file"], width=ui.Fraction(0.6), height=24, style={"alignment": ui.Alignment.RIGHT_CENTER})
                            
                            # Set initial tooltips
                            field_paths.tooltip = model["paths"].get_value_as_string()
                            field_config.tooltip = model["config_file"].get_value_as_string()
                            
                            # Dynamically update tooltips when user types or picks a file
                            def update_paths_tooltip(m, f=field_paths):
                                f.tooltip = m.get_value_as_string()
                            model["paths"].add_value_changed_fn(update_paths_tooltip)
                            
                            def update_config_tooltip(m, f=field_config):
                                f.tooltip = m.get_value_as_string()
                            model["config_file"].add_value_changed_fn(update_config_tooltip)
                            
                        settings_frame = ui.Frame(
                            style={"background_color": 0x33000000, "border_radius": 4},
                            visible=model["show_settings"].get_value_as_bool()
                        )
                        
                        def _on_show_settings_changed(m, f=settings_frame):
                            f.visible = m.get_value_as_bool()
                        model["show_settings"].add_value_changed_fn(_on_show_settings_changed)
                        
                        with settings_frame:
                            with ui.HStack(height=24, spacing=8, style={"margin": 4}):
                                    cb_style = {"background_color": 0xFF1A1A1A, "color": 0xFFDDDDDD, "border_radius": 2}
                                    ui.CheckBox(model=model["override"], width=18, height=18, style=cb_style)
                                    ui.Label("Override JSON", width=100, style={"font_size": 13, "color": ARGB_TEXT_PRIMARY})
                                    
                                    ui.Label("Speed:", width=45, style={"font_size": 12, "color": ARGB_TEXT_PRIMARY})
                                    f_speed = ui.FloatField(model=model["speed"], width=50, height=20)
                                    
                                    ui.Label("Delay:", width=40, style={"font_size": 12, "color": ARGB_TEXT_PRIMARY})
                                    f_delay = ui.FloatField(model=model["initial_delay"], width=50, height=20)
                                    
                                    ui.Label("Interval:", width=50, style={"font_size": 12, "color": ARGB_TEXT_PRIMARY})
                                    f_interval = ui.FloatField(model=model["dispatch_interval"], width=50, height=20)
                                    
                                    def _on_override_changed(m, speed=f_speed, delay=f_delay, interval=f_interval):
                                        enabled = m.get_value_as_bool()
                                        speed.enabled = enabled
                                        delay.enabled = enabled
                                        interval.enabled = enabled
                                    model["override"].add_value_changed_fn(_on_override_changed)
                                    _on_override_changed(model["override"])

    def _add_multi_line(self):
        self._save_ml_undo_snapshot()
        self._multi_line_models.append(self._make_multi_line_model())
        self._rebuild_multi_line_ui()

    def _remove_multi_line(self):
        if not self._multi_line_models:
            return
            
        self._save_ml_undo_snapshot()
        
        to_remove = [m for m in self._multi_line_models if m.get("selected") and m["selected"].get_value_as_bool()]
        
        if to_remove:
            for m in to_remove:
                self._multi_line_models.remove(m)
        else:
            self._multi_line_models.pop()
            
        self._rebuild_multi_line_ui()

    def _pick_json_for_line(self, line_model):
        def on_selected(filename, path):
            self._save_ml_undo_snapshot()
            full_path = f"{path}/{filename}".replace("\\", "/")
            line_model["config_file"].set_value(full_path)
            if hasattr(self, '_multi_line_filepicker'):
                self._multi_line_filepicker.hide()
                self._multi_line_filepicker = None
                
        if not hasattr(self, '_multi_line_filepicker') or self._multi_line_filepicker is None:
            from omni.kit.window.filepicker import FilePickerDialog
            self._multi_line_filepicker = FilePickerDialog(
                "Select JSON Config",
                click_apply_handler=on_selected,
                click_cancel_handler=lambda f, p: self._multi_line_filepicker.hide()
            )
        self._multi_line_filepicker.show()

    # ------------------------------------------------------------------
    # Multi-Line Undo / Redo
    # ------------------------------------------------------------------
    def _get_ml_snapshot(self):
        snapshot = []
        for ml in self._multi_line_models:
            snapshot.append({
                "show_settings": ml["show_settings"].get_value_as_bool(),
                "override": ml["override"].get_value_as_bool(),
                "speed": ml["speed"].get_value_as_float(),
                "initial_delay": ml["initial_delay"].get_value_as_float(),
                "dispatch_interval": ml["dispatch_interval"].get_value_as_float(),
                "paths": ml["paths"].get_value_as_string(),
                "config_file": ml["config_file"].get_value_as_string()
            })
        return snapshot
        
    def _save_ml_undo_snapshot(self):
        self._ml_undo_stack.append(self._get_ml_snapshot())
        self._ml_redo_stack.clear()
        
    def _restore_ml_snapshot(self, snapshot):
        self._multi_line_models.clear()
        for data in snapshot:
            ml = self._make_multi_line_model(data["paths"], data["config_file"])
            ml["show_settings"].set_value(data["show_settings"])
            ml["override"].set_value(data["override"])
            ml["speed"].set_value(data["speed"])
            ml["initial_delay"].set_value(data["initial_delay"])
            ml["dispatch_interval"].set_value(data["dispatch_interval"])
            self._multi_line_models.append(ml)
            
        import asyncio
        import omni.kit.app
        async def defer_rebuild():
            await omni.kit.app.get_app().next_update_async()
            self._rebuild_multi_line_ui()
        asyncio.ensure_future(defer_rebuild())
        
    def _ml_undo(self):
        if not self._ml_undo_stack: return
        self._ml_redo_stack.append(self._get_ml_snapshot())
        state = self._ml_undo_stack.pop()
        self._restore_ml_snapshot(state)
        self._update_status("Multi-Line Undo successful.", 0xFF44CC44)
        
    def _ml_redo(self):
        if not self._ml_redo_stack: return
        self._ml_undo_stack.append(self._get_ml_snapshot())
        state = self._ml_redo_stack.pop()
        self._restore_ml_snapshot(state)
        self._update_status("Multi-Line Redo successful.", 0xFF44CC44)
        
    def _ml_reset(self):
        self._save_ml_undo_snapshot()
        self._multi_line_models = [self._make_multi_line_model() for _ in range(5)]
        self._rebuild_multi_line_ui()

    # ------------------------------------------------------------------
    # Scene Overrides (Referenced Lines) Helpers
    # ------------------------------------------------------------------
    def _scan_referenced_lines(self):
        """Scan the stage for headless configurations (excluding local UI config)."""
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return

        self._scene_overrides_models.clear()
        
        # We need to find all prims that have zin:conveyor_config, but skip the local one
        # If the local one hasn't been saved yet, it might not exist, but if it does, skip it.
        local_ui_path = self._USD_CONFIG_PATH
        
        for prim in stage.Traverse():
            if prim.HasAttribute("zin:conveyor_config"):
                prim_path = prim.GetPath().pathString
                if prim_path == local_ui_path:
                    continue  # Skip the local UI configuration itself
                
                # Attempt to parse the actual JSON to get the real parameters
                actual_speed = 50.0
                actual_delay = 0.0
                actual_interval = 3.0
                try:
                    attr = prim.GetAttribute("zin:conveyor_config")
                    if attr and attr.IsValid():
                        json_str = attr.Get()
                        if json_str:
                            import json
                            cfg_data = json.loads(str(json_str))
                            parsed_cfg = self._parse_config_dict(cfg_data)
                            actual_speed = float(parsed_cfg.get("speed", 50.0))
                            actual_delay = float(parsed_cfg.get("initial_delay", 0.0))
                            actual_interval = float(parsed_cfg.get("dispatch_interval", 3.0))
                except Exception as e:
                    carb.log_warn(f"[tw.zin.smart_conveyor] Failed to parse config for {prim_path}: {e}")
                
                model = self._make_scene_override_model(
                    path=prim_path,
                    enabled=True,
                    override=False,
                    speed=actual_speed,
                    initial_delay=actual_delay,
                    dispatch_interval=actual_interval
                )
                self._scene_overrides_models.append(model)
                
        self._rebuild_scene_overrides_ui()
        self._update_status(f"Scanned and found {len(self._scene_overrides_models)} referenced lines.", 0xFF44CC44)
        carb.log_info(f"[tw.zin.smart_conveyor] Scanned {len(self._scene_overrides_models)} scene overrides.")

    def _rebuild_scene_overrides_ui(self):
        if not hasattr(self, '_scene_overrides_vbox') or not self._scene_overrides_vbox:
            return
        self._scene_overrides_vbox.clear()
        with self._scene_overrides_vbox:
            for i, model in enumerate(self._scene_overrides_models):
                with ui.HStack(height=26, spacing=4):
                    ui.Label(str(i+1), width=30, style={"color": 0xFF888888, "alignment": ui.Alignment.CENTER})
                    
                    cb_style = {"background_color": 0xFF1A1A1A, "color": 0xFFDDDDDD, "border_radius": 2}
                    # Wrap checkboxes in HStacks with fixed width and CENTER alignment so they match the headers exactly
                    with ui.HStack(width=24):
                        ui.Spacer()
                        ui.CheckBox(model=model["enabled"], width=18, height=18, style=cb_style, tooltip="Enable Simulation")
                        ui.Spacer()
                    with ui.HStack(width=24):
                        ui.Spacer()
                        ui.CheckBox(model=model["override"], width=18, height=18, style=cb_style, tooltip="Apply Override")
                        ui.Spacer()
                    
                    ui.StringField(model=model["path"], width=ui.Fraction(1), height=22, read_only=True)
                    
                    # Settings toggle
                    def toggle_settings(m=model):
                        m["show_settings"].set_value(not m["show_settings"].get_value_as_bool())
                        import asyncio
                        import omni.kit.app
                        async def defer_rebuild():
                            await omni.kit.app.get_app().next_update_async()
                            self._rebuild_scene_overrides_ui()
                        asyncio.ensure_future(defer_rebuild())
                        
                    btn_text = "V" if model["show_settings"].get_value_as_bool() else ">"
                    btn = ZinButton(btn_text, state="default", width=30, clicked_fn=toggle_settings)
                    btn.set_state("default")
                    
                if model["show_settings"].get_value_as_bool():
                    with ui.HStack(height=22, spacing=4):
                        ui.Spacer(width=50)
                        ui.Label("Spd:", width=30, style={"color": ARGB_TEXT_SECONDARY})
                        ui.FloatField(model=model["speed"], width=ui.Fraction(1), height=20)
                        ui.Label("Dly:", width=30, style={"color": ARGB_TEXT_SECONDARY})
                        ui.FloatField(model=model["initial_delay"], width=ui.Fraction(1), height=20)
                        ui.Label("Int:", width=30, style={"color": ARGB_TEXT_SECONDARY})
                        ui.FloatField(model=model["dispatch_interval"], width=ui.Fraction(1), height=20)

    # ------------------------------------------------------------------
    # Config & simulation
    # ------------------------------------------------------------------
    def _build_config_from_ui(self) -> dict:
        """Assemble pcb_config by reading all current UI model values."""
        waypoints = []
        for wp in self._waypoint_models:
            wp_name = wp["name"].get_value_as_string() if "name" in wp else "WP"
            waypoints.append({
                "name": wp_name,
                "pos": Gf.Vec3d(wp["px"].get_value_as_float(),
                                wp["py"].get_value_as_float(),
                                wp["pz"].get_value_as_float()),
                "rot": Gf.Vec3d(wp["rx"].get_value_as_float(),
                                wp["ry"].get_value_as_float(),
                                wp["rz"].get_value_as_float()),
                "pause": wp["pause"].get_value_as_float()
            })
        return {
            "prim_path":      self._prim_path_model.get_value_as_string().strip(),
            "speed":          self._speed_model.get_value_as_float(),
            "initial_delay":  self._initial_delay_model.get_value_as_float(),
            "reverse":        self._reverse_model.get_value_as_bool(),
            "loop":           self._loop_model.get_value_as_bool(),
            "end_visibility": self._visible_at_end_model.get_value_as_bool(),
            "waypoints":      waypoints,
        }

    def _on_window_visibility_changed(self, visible):
        ui.Workspace.show_window("Smart Conveyor Panel", visible)

    def _pick_from_selection(self):
        """Append all currently selected Stage prims to the path field (comma-separated)."""
        paths = omni.usd.get_context().get_selection().get_selected_prim_paths()
        if not paths:
            self._update_status("No prim selected in Stage!", 0xFFFF6600)
            return
        current = self._prim_path_model.get_value_as_string().strip()
        # Filter out blank placeholder text
        existing = [p.strip() for p in current.split(",") if p.strip()] if current else []
        new_paths = [p for p in paths if p not in existing]
        merged = existing + new_paths
        self._prim_path_model.set_value(", ".join(merged))
        self._update_status(f"Appended {len(new_paths)} prim(s). Total: {len(merged)}", 0xFF00CC44)
        carb.log_info(f"[tw.zin.smart_conveyor] Paths updated: {merged}")

    def _update_status(self, text: str, color: int = 0xFF888888):
        if hasattr(self, '_status_label') and self._status_label:
            self._status_label.text = text
            self._status_label.set_style({"color": color})

    def _calc_required_pool_size(self, waypoints: list, speed: float, dispatch_interval: float) -> int:
        if not waypoints or speed <= 0 or dispatch_interval <= 0:
            return 2
        import math
        total_dist = 0.0
        total_pause = 0.0
        for i in range(1, len(waypoints)):
            wp_prev = waypoints[i-1]
            wp_curr = waypoints[i]
            # Use math.dist or vector length
            vec = wp_curr["pos"] - wp_prev["pos"]
            total_dist += vec.GetLength()
            total_pause += wp_curr.get("pause", 0.0)
        total_time = (total_dist / speed) + total_pause
        required = int(math.ceil(total_time / dispatch_interval)) + 2 # Safety buffer of 2
        return max(1, required)

    def start_sim(self):
        """Configure template models, pre-allocate Object Pools, and start Spawner loop."""
        self.stop_sim()
        
        base_config = self._build_config_from_ui()
        base_delay = base_config.get("initial_delay", 0.0)
        dispatch_interval = self._dispatch_interval_model.get_value_as_float()
        
        self._active_spawners = []
        self._inactive_pools = {}
        success_count = 0
        failed_paths = []
        
        stage = omni.usd.get_context().get_stage()
        if not stage:
            self._update_status("Error: No USD Stage open!", 0xFFFF4444)
            return
            
        spawner_root = "/World/Spawned_PCBs"
        if not stage.GetPrimAtPath(spawner_root).IsValid():
            stage.DefinePrim(spawner_root, "Xform")

        # --- Helper to initialize a pool ---
        def _init_pool(line_id, tpl_path, config_dict, disp_interval, b_delay):
            tpl_prim = stage.GetPrimAtPath(tpl_path)
            if not tpl_prim.IsValid():
                return False
                
            # Hide the template prim during simulation
            tpl_img = UsdGeom.Imageable(tpl_prim)
            if tpl_img:
                tpl_img.MakeInvisible()
                if not hasattr(self, '_hidden_templates'):
                    self._hidden_templates = set()
                self._hidden_templates.add(tpl_path)
                
            req_spawns = self._calc_required_pool_size(config_dict["waypoints"], config_dict["speed"], disp_interval)
            pool = []
            for i in range(req_spawns):
                new_path = f"{spawner_root}/{line_id}_inst_{i:03d}"
                new_prim = stage.DefinePrim(new_path, "Xform")
                new_prim.GetReferences().AddInternalReference(tpl_path)
                
                # Make initially invisible
                imageable = UsdGeom.Imageable(new_prim)
                if not imageable:
                    imageable = UsdGeom.Imageable.Define(stage, new_path)
                imageable.MakeInvisible()
                
                pool.append(new_path)
                
            self._inactive_pools[line_id] = pool
            
            cfg = dict(config_dict)
            cfg["initial_delay"] = 0.0
            cfg["template_path"] = tpl_path
            
            self._active_spawners.append({
                "template_path": tpl_path,
                "config": cfg,
                "dispatch_interval": disp_interval,
                "timer": disp_interval - b_delay,
                "line_id": line_id
            })
            return True

        # --- Parse Inline Template ---
        if hasattr(self, "_enable_inline_model") and self._enable_inline_model.get_value_as_bool():
            raw = self._prim_path_model.get_value_as_string()
            inline_templates = [p.strip() for p in raw.replace(",", " ").split() if p.strip()]
            
            for idx, tpl_path in enumerate(inline_templates):
                if _init_pool(f"Inline_{idx}", tpl_path, base_config, dispatch_interval, base_delay):
                    success_count += 1
                else:
                    failed_paths.append(tpl_path)

        # --- Parse Multi-Line Templates ---
        for m_idx, m_model in enumerate(self._multi_line_models):
            if "enabled" in m_model and not m_model["enabled"].get_value_as_bool():
                continue
            m_paths_raw = m_model["paths"].get_value_as_string()
            m_templates = [p.strip() for p in m_paths_raw.replace(",", " ").split() if p.strip()]
            m_config_file = m_model["config_file"].get_value_as_string().strip()
            
            if not m_templates or not m_config_file: continue
            m_json_str = self._read_json_file(m_config_file)
            if not m_json_str: continue
                
            try:
                import json
                m_config_data = json.loads(m_json_str)
                m_parsed_config = self._parse_config_dict(m_config_data)
            except: continue
                
            m_base_delay = m_parsed_config.get("initial_delay", 0.0)
            m_dispatch = m_parsed_config.get("dispatch_interval", dispatch_interval)
            
            # --- Apply UI Overrides ---
            if "override" in m_model and m_model["override"].get_value_as_bool():
                m_parsed_config["speed"] = m_model["speed"].get_value_as_float()
                m_base_delay = m_model["initial_delay"].get_value_as_float()
                m_dispatch = m_model["dispatch_interval"].get_value_as_float()
                
                m_parsed_config["initial_delay"] = m_base_delay
                m_parsed_config["dispatch_interval"] = m_dispatch
                
            for p_idx, tpl_path in enumerate(m_templates):
                if _init_pool(f"Line{m_idx}_{p_idx}", tpl_path, m_parsed_config, m_dispatch, m_base_delay):
                    success_count += 1
                else:
                    failed_paths.append(tpl_path)

        # --- Parse Headless Referenced Configs (For Auto-play in large scenes) ---
        # Only scan referenced configs when NO templates were configured via UI,
        # to avoid duplicating templates that the user already set up manually.
        if success_count == 0:
          try:
            import json
            for prim in stage.Traverse():
                # Skip the local UI configuration
                if prim.GetPath().pathString == self._USD_CONFIG_PATH:
                    continue
                
                attr = prim.GetAttribute(self._USD_CONFIG_ATTR)
                if attr and attr.IsValid():
                    json_str = attr.Get()
                    if not json_str: continue
                    
                    try:
                        h_cfg = json.loads(str(json_str))
                        h_cfg = self._parse_config_dict(h_cfg)
                    except Exception:
                        continue
                        
                    # Compute reference prefix (e.g. /World/assembly/Line_S01)
                    c_path = prim.GetPath().pathString
                    
                    # --- Apply Scene Overrides if any ---
                    so_enabled = True
                    so_opt = False
                    for so in getattr(self, '_scene_overrides_models', []):
                        if so["path"].get_value_as_string() == c_path:
                            so_enabled = so["enabled"].get_value_as_bool()
                            so_opt = so["override"].get_value_as_bool()
                            so_spd = so["speed"].get_value_as_float()
                            so_dly = so["initial_delay"].get_value_as_float()
                            so_int = so["dispatch_interval"].get_value_as_float()
                            break
                            
                    if not so_enabled:
                        continue
                        
                    if so_opt:
                        h_cfg["speed"] = so_spd
                        h_cfg["initial_delay"] = so_dly
                        h_cfg["dispatch_interval"] = so_int
                        for m_cfg in h_cfg.get("multi_lines", []):
                            m_cfg["override"] = True
                            m_cfg["speed"] = so_spd
                            m_cfg["initial_delay"] = so_dly
                            m_cfg["dispatch_interval"] = so_int
                    # ------------------------------------
                    
                    prefix = prim.GetParent().GetPath().pathString
                    h_hash = str(abs(hash(c_path)))[:6]
                    
                    # Collect all multi-line paths first (for deduplication)
                    h_ml_all_paths = set()
                    for m_cfg in h_cfg.get("multi_lines", []):
                        if not m_cfg.get("enabled", True):
                            continue
                        for p in m_cfg.get("paths", "").replace(",", " ").split():
                            raw_p = p.strip()
                            if raw_p:
                                if prefix != "/" and raw_p.startswith("/World/"):
                                    raw_p = prefix + raw_p[6:]
                                h_ml_all_paths.add(raw_p)
                        
                    # 1. Inline Prim Paths from headless config (skip if already in multi-lines)
                    h_prim_paths_raw = h_cfg.get("prim_paths", "")
                    h_templates = [p.strip() for p in h_prim_paths_raw.replace(",", " ").split() if p.strip()]
                    h_dispatch = h_cfg.get("dispatch_interval", dispatch_interval)
                    h_base_delay = h_cfg.get("initial_delay", 0.0)
                    
                    for p_idx, tpl_path in enumerate(h_templates):
                        if prefix != "/" and tpl_path.startswith("/World/"):
                            tpl_path = prefix + tpl_path[6:]
                        if tpl_path in h_ml_all_paths:
                            continue  # Skip: already handled by multi-line
                        if _init_pool(f"HL_{h_hash}_Inl_{p_idx}", tpl_path, h_cfg, h_dispatch, h_base_delay):
                            success_count += 1
                        else:
                            failed_paths.append(tpl_path)
                            
                    # 2. Multi-Line Paths from headless config
                    for m_idx, m_cfg in enumerate(h_cfg.get("multi_lines", [])):
                        if not m_cfg.get("enabled", True):
                            continue
                        m_paths_raw = m_cfg.get("paths", "")
                        m_templates = [p.strip() for p in m_paths_raw.replace(",", " ").split() if p.strip()]
                        m_config_file = m_cfg.get("config_file", "")
                        
                        if not m_templates or not m_config_file: continue
                        
                        m_json_str = self._read_json_file(m_config_file)
                        if not m_json_str: continue
                        
                        try:
                            m_config_data = json.loads(m_json_str)
                            m_parsed_config = self._parse_config_dict(m_config_data)
                        except: continue
                        
                        if m_cfg.get("override", False):
                            m_parsed_config["speed"] = m_cfg.get("speed", 50.0)
                            m_parsed_config["initial_delay"] = m_cfg.get("initial_delay", 0.0)
                            m_parsed_config["dispatch_interval"] = m_cfg.get("dispatch_interval", dispatch_interval)
                            
                        m_base_delay_m = m_parsed_config.get("initial_delay", 0.0)
                        m_dispatch_m = m_parsed_config.get("dispatch_interval", dispatch_interval)
                        
                        for p_idx, tpl_path in enumerate(m_templates):
                            if prefix != "/" and tpl_path.startswith("/World/"):
                                tpl_path = prefix + tpl_path[6:]
                            if _init_pool(f"HL_{h_hash}_Mul_{m_idx}_{p_idx}", tpl_path, m_parsed_config, m_dispatch_m, m_base_delay_m):
                                success_count += 1
                            else:
                                failed_paths.append(tpl_path)
          except Exception as _he:
            carb.log_warn(f"[tw.zin.smart_conveyor] Headless config parsing error: {_he}")

        # --- Report status and Start Loop ---
        if success_count == 0:
            self._update_status("Error: No valid templates found!", 0xFFFF4444)
        else:
            self._spawner_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
                self._on_spawner_update, name="tw.zin.smart_conveyor.spawner"
            )
            msg = f"Status: Running ({success_count} Templates)"
            if failed_paths: msg += f" | Not found: {len(failed_paths)}"
            self._update_status(msg, 0xFF44CC44)

    def _on_spawner_update(self, e: carb.events.IEvent):
        dt = e.payload["dt"]
        # Overshoot protection: must match PCBConveyorController to prevent spacing desync
        dt = min(dt, 0.1)
        
        stage = omni.usd.get_context().get_stage()
        if not stage: return

        # 1. Garbage Collection & Object Pool Recycle
        active_ctrls = []
        for ctrl in self.controllers:
            if ctrl.state == "FINISHED":
                # Recycle the prim back into the inactive pool
                for sp in self._active_spawners:
                    # ctrl.prim_path starts with e.g. "/World/Spawned_PCBs/Inline_0_inst_000"
                    if ctrl.prim_path.startswith(f"/World/Spawned_PCBs/{sp['line_id']}_inst"):
                        # 如果遺失，嘗試執行回收邏輯重建它，確保物件池數量不會永久短缺
                        if not stage.GetPrimAtPath(ctrl.prim_path).IsValid():
                            carb.log_info(f"[tw.zin.smart_conveyor] 嘗試執行回收邏輯：重建遺失的 Prim {ctrl.prim_path}")
                            new_prim = stage.DefinePrim(ctrl.prim_path, "Xform")
                            new_prim.GetReferences().AddInternalReference(sp["template_path"])
                            
                            imageable = UsdGeom.Imageable(new_prim)
                            if not imageable:
                                imageable = UsdGeom.Imageable.Define(stage, ctrl.prim_path)
                            imageable.MakeInvisible()
                            
                        self._inactive_pools[sp["line_id"]].append(ctrl.prim_path)
                        break
                try: ctrl.stop()
                except: pass
            elif ctrl.prim and ctrl.prim.IsValid():
                active_ctrls.append(ctrl)
            else:
                try: ctrl.stop()
                except: pass
        self.controllers = active_ctrls

        # 2. Spawner Logic (Extract from Pool)
        for sp in self._active_spawners:
            sp["timer"] += dt
            if sp["timer"] >= sp["dispatch_interval"]:
                # Only spawn if there is an available instance in the pool
                pool = self._inactive_pools.get(sp["line_id"], [])
                if pool:
                    sp["timer"] -= sp["dispatch_interval"]
                    idle_path = pool.pop()
                    
                    cfg = dict(sp["config"])
                    cfg["prim_path"] = idle_path
                    # PCBConveyorController initialization resets position and calls MakeVisible()
                    ctrl = PCBConveyorController(cfg)
                    self.controllers.append(ctrl)
                    
                    # 確保計數器能與目前的物件池 Prim 列表實時同步，不要讓計數器跑得比實際物件數量快
                    if ctrl.state == "FINISHED":
                        sp["timer"] += sp["dispatch_interval"]
                else:
                    # If pool is empty, we wait until one is recycled. 
                    # Cap timer so it doesn't spiral out of control.
                    sp["timer"] = sp["dispatch_interval"]

    def stop_sim(self):
        # Stop Spawner Loop
        if hasattr(self, '_spawner_sub'):
            self._spawner_sub = None
            
        # Stop all active controllers
        for ctrl in self.controllers:
            try: ctrl.stop()
            except: pass
        self.controllers = []
        
        # Restore visibility of original templates
        if hasattr(self, '_hidden_templates'):
            stage = omni.usd.get_context().get_stage()
            if stage:
                for tpl_path in self._hidden_templates:
                    tpl_prim = stage.GetPrimAtPath(tpl_path)
                    if tpl_prim and tpl_prim.IsValid():
                        tpl_img = UsdGeom.Imageable(tpl_prim)
                        if tpl_img:
                            tpl_img.MakeVisible()
            self._hidden_templates.clear()
            
        # Destroy all spawned instances to clear the pool
        stage = omni.usd.get_context().get_stage()
        if stage and stage.GetPrimAtPath("/World/Spawned_PCBs").IsValid():
            stage.RemovePrim("/World/Spawned_PCBs")
            
        self._inactive_pools.clear()
        self._active_spawners.clear()
            
        self._update_status("Status: Stopped", 0xFFAAAAAA)
        carb.log_info("[tw.zin.smart_conveyor] All controllers stopped and spawned PCBs cleared.")

    # ------------------------------------------------------------------
    # Timeline Events: auto Start on Play, auto Stop on Stop
    # ------------------------------------------------------------------
    def _on_timeline_event(self, event):
        if SmartConveyorExtension._primary_instance is not None and SmartConveyorExtension._primary_instance is not self:
            return
        try:
            if _omni_timeline is None:
                return
            if event.type == int(_omni_timeline.TimelineEventType.PLAY):
                self.start_sim()
            elif event.type == int(_omni_timeline.TimelineEventType.STOP):
                self.stop_sim()
        except Exception as _e:
            carb.log_warn(f"[tw.zin.smart_conveyor] Timeline event error: {_e}")

    def _on_stage_event(self, event):
        # Stop simulation cleanly if the stage is being closed or changed
        try:
            if event.type == int(omni.usd.StageEventType.CLOSING):
                self.stop_sim()
            elif event.type == int(omni.usd.StageEventType.OPENED):
                self.stop_sim()
                self._reset_ui_to_defaults()
                self._usd_auto_load()
        except Exception as _e:
            carb.log_warn(f"[tw.zin.smart_conveyor] Stage event error: {_e}")

    # ------------------------------------------------------------------
    # FilePicker Callbacks & File Helpers
    # ------------------------------------------------------------------
    def _read_json_file(self, filepath: str) -> str:
        filepath = filepath.replace('\\', '/')
        try:
            result, _, content = omni.client.read_file(filepath)
            if result == omni.client.Result.OK:
                return memoryview(content).tobytes().decode("utf-8")
            else:
                with open(filepath, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception:
            return ""

    async def load_config_from_url_async(self, url: str):
        import omni.client
        import json
        import omni.kit.app
        try:
            result, entries = await omni.client.list_async(url)
            files_to_load = []
            if result == omni.client.Result.OK:
                for entry in entries:
                    if entry.relative_path.endswith(".json"):
                        files_to_load.append(url + ("/" if not url.endswith("/") else "") + entry.relative_path)
            else:
                if url.endswith(".json"):
                    files_to_load.append(url)
                    
            if not files_to_load:
                carb.log_warn(f"[tw.zin.smart_conveyor] No JSON files found at {url}")
                return
                
            self._save_ml_undo_snapshot()
            
            # Unconditionally clear existing models so we don't duplicate them
            self._multi_line_models.clear()
            if hasattr(self, '_scene_overrides_models'):
                self._scene_overrides_models.clear()
            
            loaded_count = 0
            for file_url in files_to_load:
                json_str = self._read_json_file(file_url)
                if not json_str: continue
                try:
                    data = json.loads(json_str)
                    parsed = self._parse_config_dict(data)
                    prim_paths = parsed.get("prim_paths", "")
                    
                    ml = self._make_multi_line_model(prim_paths, file_url)
                    ml["speed"].set_value(float(parsed.get("speed", 50.0)))
                    ml["initial_delay"].set_value(float(parsed.get("initial_delay", 0.0)))
                    ml["dispatch_interval"].set_value(float(parsed.get("dispatch_interval", 3.0)))
                        
                    self._multi_line_models.append(ml)
                    loaded_count += 1
                except Exception as e:
                    carb.log_warn(f"[tw.zin.smart_conveyor] Failed to parse {file_url}: {e}")
                    
            await omni.kit.app.get_app().next_update_async()
            self._rebuild_multi_line_ui()
            if hasattr(self, '_rebuild_scene_overrides_ui'):
                self._rebuild_scene_overrides_ui()
            carb.log_info(f"[tw.zin.smart_conveyor] Successfully loaded {loaded_count} JSONs from {url}")
        except Exception as e:
            carb.log_error(f"[tw.zin.smart_conveyor] Error loading from {url}: {e}")
    def _on_save_clicked(self):
        """Open a FilePicker dialog to save current config as a JSON file."""
        if not _HAS_FILEPICKER:
            self._update_status("FilePicker not available in this Kit version.", 0xFFFF6600)
            carb.log_warn("[tw.zin.smart_conveyor] omni.kit.window.filepicker not available.")
            return

        # Destroy any existing save dialog before creating a new one
        if self._filepicker_save is not None:
            self._filepicker_save.destroy()
            self._filepicker_save = None

        def _apply_save(filename: str, dirname: str):
            """Called when the user confirms the save location."""
            # Ensure the filename has a .json extension
            if not filename.lower().endswith(".json"):
                filename += ".json"
            filepath = os.path.join(dirname, filename)
            # Normalize path slashes for omni.client
            filepath = filepath.replace('\\', '/')
            try:
                json_str = self.export_config_to_json()
                content = json_str.encode("utf-8")
                
                # First try omni.client (Required for Nucleus 'omniverse://' URIs)
                result = omni.client.write_file(filepath, content)
                
                if result != omni.client.Result.OK:
                    # Fallback to standard Python I/O (For local paths 'C:/...', etc.)
                    carb.log_info(f"[tw.zin.smart_conveyor] omni.client failed ({result}), falling back to Python open().")
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(json_str)
                        
                self._update_status(f"JSON saved: {os.path.basename(filepath)}", 0xFF44CC44)
                carb.log_info(f"[tw.zin.smart_conveyor] Config exported to: {filepath}")
            except Exception as _e:
                self._update_status(f"JSON save failed: {_e}", 0xFFFF4444)
                carb.log_warn(f"[tw.zin.smart_conveyor] JSON export error: {_e}")
            # Hide the dialog after completion
            if self._filepicker_save:
                self._filepicker_save.hide()

        self._filepicker_save = FilePickerDialog(
            "Save Conveyor Config as JSON",
            allow_multi_selection=False,
            apply_button_label="Save",
            click_apply_handler=_apply_save,
            click_cancel_handler=lambda *_: self._filepicker_save.hide() if self._filepicker_save else None,
            file_extension_options=[("*.json", "JSON Config Files")],
        )
        self._filepicker_save.show()

    def _on_load_clicked(self):
        """Open a FilePicker dialog to load a JSON config file."""
        if not _HAS_FILEPICKER:
            self._update_status("FilePicker not available in this Kit version.", 0xFFFF6600)
            carb.log_warn("[tw.zin.smart_conveyor] omni.kit.window.filepicker not available.")
            return

        # Destroy any existing load dialog before creating a new one
        if self._filepicker_load is not None:
            self._filepicker_load.destroy()
            self._filepicker_load = None

        def _apply_load(filename: str, dirname: str):
            """Called when the user selects a file to load."""
            filepath = os.path.join(dirname, filename)
            # Normalize path slashes for omni.client
            filepath = filepath.replace('\\', '/')
            try:
                # First try omni.client (Required for Nucleus 'omniverse://' URIs)
                result, _, content = omni.client.read_file(filepath)
                
                if result == omni.client.Result.OK:
                    json_str = memoryview(content).tobytes().decode("utf-8")
                else:
                    # Fallback to standard Python I/O (For local paths 'C:/...', etc.)
                    carb.log_info(f"[tw.zin.smart_conveyor] omni.client failed ({result}), falling back to Python open().")
                    with open(filepath, "r", encoding="utf-8") as f:
                        json_str = f.read()
                        
                self.load_config_from_json(json_str)
                self._update_status(f"JSON loaded: {os.path.basename(filepath)}", 0xFF44AAFF)
                carb.log_info(f"[tw.zin.smart_conveyor] Config imported from: {filepath}")
            except Exception as _e:
                self._update_status(f"JSON load failed: {_e}", 0xFFFF4444)
                carb.log_warn(f"[tw.zin.smart_conveyor] JSON import error: {_e}")
            # Hide the dialog after completion
            if self._filepicker_load:
                self._filepicker_load.hide()

        self._filepicker_load = FilePickerDialog(
            "Load Conveyor Config from JSON",
            allow_multi_selection=False,
            apply_button_label="Load",
            click_apply_handler=_apply_load,
            click_cancel_handler=lambda *_: self._filepicker_load.hide() if self._filepicker_load else None,
            file_extension_options=[("*.json", "JSON Config Files")],
        )
        self._filepicker_load.show()

    # ------------------------------------------------------------------
    # JSON Config Export / Import
    # ------------------------------------------------------------------
    def export_config_to_json(self) -> str:
        """將目前 UI 設定序列化為 JSON 字串。"""
        cfg = self._build_config_from_ui()
        cfg["prim_paths"] = self._prim_path_model.get_value_as_string()
        cfg["dispatch_interval"] = self._dispatch_interval_model.get_value_as_float()
        cfg["waypoints"] = [
            {"name": wp.get("name", "WP"),
             "pos": [wp["pos"][0], wp["pos"][1], wp["pos"][2]],
             "rot": [wp["rot"][0], wp["rot"][1], wp["rot"][2]],
             "pause": wp["pause"]}
            for wp in cfg["waypoints"]
        ]
        cfg["multi_lines"] = [
            {
                "enabled": m.get("enabled", ui.SimpleBoolModel(True)).get_value_as_bool(),
                "show_settings": m["show_settings"].get_value_as_bool(),
                "override": m["override"].get_value_as_bool(),
                "speed": m["speed"].get_value_as_float(),
                "initial_delay": m["initial_delay"].get_value_as_float(),
                "dispatch_interval": m["dispatch_interval"].get_value_as_float(),
                "paths": m["paths"].get_value_as_string(),
                "config_file": m["config_file"].get_value_as_string()
            }
            for m in self._multi_line_models
        ]
        cfg["scene_overrides"] = [
            {
                "path": m["path"].get_value_as_string(),
                "enabled": m["enabled"].get_value_as_bool(),
                "override": m["override"].get_value_as_bool(),
                "speed": m["speed"].get_value_as_float(),
                "initial_delay": m["initial_delay"].get_value_as_float(),
                "dispatch_interval": m["dispatch_interval"].get_value_as_float(),
                "show_settings": m["show_settings"].get_value_as_bool(),
            }
            for m in getattr(self, '_scene_overrides_models', [])
        ]
        return json.dumps(cfg, indent=2, ensure_ascii=False)

    def _parse_config_dict(self, cfg: dict) -> dict:
        """Normalise nested format to flat keys."""
        out = dict(cfg)
        if "global_settings" in out:
            gs = out["global_settings"]
            out.setdefault("speed",             gs.get("speed", 50.0))
            out.setdefault("initial_delay",     gs.get("initial_delay", 1.0))
            out.setdefault("dispatch_interval", gs.get("dispatch_interval", 3.0))
        if "behavior" in out:
            bh = out["behavior"]
            out.setdefault("reverse",        bh.get("reverse", False))
            out.setdefault("loop",            bh.get("loop", False))
            out.setdefault("end_visibility",  bh.get("end_visibility", False))
        if "target_pcb_paths" in out and "prim_paths" not in out:
            out["prim_paths"] = ", ".join(out["target_pcb_paths"])
            
        if "waypoints" in out:
            from pxr import Gf
            converted = []
            for wp in out["waypoints"]:
                p = wp.get("pos", [0, 0, 0])
                r = wp.get("rot", [0, 0, 0])
                converted.append({
                    "pos": Gf.Vec3d(float(p[0]), float(p[1]), float(p[2])),
                    "rot": Gf.Vec3d(float(r[0]), float(r[1]), float(r[2])),
                    "pause": float(wp.get("pause", 0.0))
                })
            out["waypoints"] = converted
            
        return out

    def load_config_from_json(self, json_str: str):
        """Restore all UI models from a JSON string.
        Supports two formats:
        - Flat: keys at top level (prim_paths, speed, waypoints ...)
        - Nested: keys grouped under global_settings / behavior / target_pcb_paths
        """
        try:
            cfg = json.loads(json_str)
        except Exception as _e:
            carb.log_warn(f"[tw.zin.smart_conveyor] JSON parse error: {_e}")
            return
        try:
            cfg = self._parse_config_dict(cfg)

            # --- Apply to UI models ---
            if "prim_paths" in cfg:
                self._prim_path_model.set_value(str(cfg["prim_paths"]))
            if "speed" in cfg:
                self._speed_model.set_value(float(cfg["speed"]))
            if "initial_delay" in cfg:
                self._initial_delay_model.set_value(float(cfg["initial_delay"]))
            if "dispatch_interval" in cfg:
                self._dispatch_interval_model.set_value(float(cfg["dispatch_interval"]))
            if "reverse" in cfg:
                self._reverse_model.set_value(bool(cfg["reverse"]))
            if "loop" in cfg:
                self._loop_model.set_value(bool(cfg["loop"]))
            if "end_visibility" in cfg:
                self._visible_at_end_model.set_value(bool(cfg["end_visibility"]))
            if "waypoints" in cfg and cfg["waypoints"]:
                self._save_undo_snapshot()
                self._waypoint_models = []
                for wp in cfg["waypoints"]:
                    p = wp.get("pos", [0, 0, 0])
                    r = wp.get("rot", [0, 0, 0])
                    self._waypoint_models.append(
                        self._make_wp_model(p[0], p[1], p[2],
                                            r[0], r[1], r[2],
                                            wp.get("pause", 0.0),
                                            wp.get("name", f"WP_{len(self._waypoint_models)}"))
                    )
                self._rebuild_waypoints_ui()
            
            if "multi_lines" in cfg:
                self._multi_line_models = []
                for m in cfg["multi_lines"]:
                    ml = self._make_multi_line_model(m.get("paths", ""), m.get("config_file", ""))
                    if "enabled" in m:
                        if "enabled" not in ml: ml["enabled"] = ui.SimpleBoolModel(m["enabled"])
                        else: ml["enabled"].set_value(m["enabled"])
                    if "show_settings" in m: ml["show_settings"].set_value(m["show_settings"])
                    if "override" in m: ml["override"].set_value(m["override"])
                    if "speed" in m: ml["speed"].set_value(m["speed"])
                    if "initial_delay" in m: ml["initial_delay"].set_value(m["initial_delay"])
                    if "dispatch_interval" in m: ml["dispatch_interval"].set_value(m["dispatch_interval"])
                    self._multi_line_models.append(ml)
                self._rebuild_multi_line_ui()
                
            if "scene_overrides" in cfg:
                self._scene_overrides_models = []
                for m in cfg["scene_overrides"]:
                    mod = self._make_scene_override_model(m.get("path", ""))
                    mod["enabled"].set_value(m.get("enabled", True))
                    mod["override"].set_value(m.get("override", False))
                    mod["speed"].set_value(m.get("speed", 50.0))
                    mod["initial_delay"].set_value(m.get("initial_delay", 0.0))
                    mod["dispatch_interval"].set_value(m.get("dispatch_interval", 3.0))
                    mod["show_settings"].set_value(m.get("show_settings", False))
                    self._scene_overrides_models.append(mod)
                self._rebuild_scene_overrides_ui()
                
            carb.log_info("[tw.zin.smart_conveyor] Config loaded from JSON.")
        except Exception as _e:
            carb.log_warn(f"[tw.zin.smart_conveyor] Config apply error: {_e}")

    # ------------------------------------------------------------------
    # USD 持久化：儲存與讀取 /World/SmartConveyorConfig
    # ------------------------------------------------------------------
    _USD_CONFIG_PATH = "/World/SmartConveyorConfig"
    _USD_CONFIG_ATTR = "zin:conveyor_config"

    def _usd_save_config(self):
        """Write config JSON into a custom USD Prim attribute so it persists with the .usd file.

        This is intentionally separate from export_config_to_json(): one is for
        in-scene persistence (USD), the other is for external file management (JSON).
        """
        try:
            stage = omni.usd.get_context().get_stage()
            if not stage:
                self._update_status("No stage open!", 0xFFFF6600)
                return
            prim = stage.GetPrimAtPath(self._USD_CONFIG_PATH)
            if not prim.IsValid():
                prim = stage.DefinePrim(self._USD_CONFIG_PATH, "Xform")
            attr = prim.GetAttribute(self._USD_CONFIG_ATTR)
            if not attr.IsValid():
                attr = prim.CreateAttribute(
                    self._USD_CONFIG_ATTR, Sdf.ValueTypeNames.String)
            attr.Set(self.export_config_to_json())
            # Inform the user that config was written into the USD scene (not a JSON file)
            self._update_status("Config written to USD scene (saved with .usd file).", 0xFF44CC44)
            carb.log_info("[tw.zin.smart_conveyor] Config saved to USD prim attribute.")
        except Exception as _e:
            self._update_status(f"USD save failed: {_e}", 0xFFFF4444)
            carb.log_warn(f"[tw.zin.smart_conveyor] USD save error: {_e}")



    def _usd_auto_load(self):
        """啟動時嘗試從 USD 場景自動還原設定。若 Prim 不存在則靜默略過。"""
        try:
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return
            prim = stage.GetPrimAtPath(self._USD_CONFIG_PATH)
            if not prim or not prim.IsValid():
                return
            attr = prim.GetAttribute(self._USD_CONFIG_ATTR)
            if not attr or not attr.IsValid():
                return
            json_str = attr.Get()
            if json_str:
                self.load_config_from_json(str(json_str))
                self._update_status("Config restored from USD scene.", 0xFF44AAFF)
        except Exception as _e:
            carb.log_warn(f"[tw.zin.smart_conveyor] USD auto-load error: {_e}")

    def _reset_ui_to_defaults(self):
        """Reset all UI models to default when a new stage is opened."""
        if not hasattr(self, '_prim_path_model'): return
        
        self._prim_path_model.set_value("")
        if hasattr(self, '_enable_inline_model'): self._enable_inline_model.set_value(True)
        self._speed_model.set_value(50.0)
        self._initial_delay_model.set_value(1.0)
        self._dispatch_interval_model.set_value(3.0)
        self._reverse_model.set_value(False)
        self._loop_model.set_value(False)
        self._visible_at_end_model.set_value(False)
        
        self._waypoint_models = [
            self._make_wp_model(0,   0, 0, 0, 0, 0, 0.0, "S"),
            self._make_wp_model(200, 0, 0, 0, 0, 0, 0.0, "E"),
        ]
        
        self._multi_line_models = [self._make_multi_line_model() for _ in range(5)]
        
        import asyncio
        import omni.kit.app
        async def defer_rebuild():
            await omni.kit.app.get_app().next_update_async()
            self._rebuild_waypoints_ui()
            self._rebuild_multi_line_ui()
        asyncio.ensure_future(defer_rebuild())

    # ------------------------------------------------------------------
    # Lifecycle: fully release all resources to prevent memory leaks
    # ------------------------------------------------------------------
    def on_shutdown(self):
        # 1. Stop all active conveyor controllers and clean up spawned models
        self.stop_sim()

        # 2. Release event subscriptions
        self._timeline_sub = None
        self._stage_sub = None

        # 3. Destroy FilePickerDialog windows (they hold GPU/UI resources)
        if self._filepicker_save is not None:
            try:
                self._filepicker_save.destroy()
            except Exception:
                pass
            self._filepicker_save = None

        if self._filepicker_load is not None:
            try:
                self._filepicker_load.destroy()
            except Exception:
                pass
            self._filepicker_load = None

        # 4. Remove the menu entry from Zin_All_Tools menu
        if hasattr(self, "_menu") and self._menu is not None:
            omni.kit.menu.utils.remove_menu_items(self._menu, "Zin_All_Tools")
            self._menu = None

        # 5. Unregister the Workspace show-window callback
        ui.Workspace.set_show_window_fn("Smart Conveyor Panel", None)

        # 6. Destroy the main panel window
        if self._window is not None:
            self._window.set_visibility_changed_fn(None)
            self._window.destroy()
            self._window = None

        carb.log_info("[tw.zin.smart_conveyor] Extension shut down and all resources released.")