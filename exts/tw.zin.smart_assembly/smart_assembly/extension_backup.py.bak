import omni.ui as ui
import omni.usd
import omni.ext
import omni.timeline
import omni.physx as physx
import asyncio
from pxr import Usd, UsdPhysics, UsdGeom, Sdf, Gf

# ========================================================
#  核心邏輯 Widget (可被嵌入)
# ========================================================
class SmartAssemblyWidget:
    def __init__(self):
        # Data
        self.timeline = omni.timeline.get_timeline_interface()
        self.stage = omni.usd.get_context().get_stage()
        
        self.items = []
        self.current_step_index = 0
        self.status_dict = {} 
        self.failure_report = {} 
        self.last_error_val = {}
        self.home_positions = {}

        # UI Refs
        self.ui_list_frame = None
        self.progress_label = None
        self.slider_models = {} 
        self.pos_labels = {} 
        
        # Flags & Tasks
        self.is_user_dragging = False 
        self.is_updating_ui = False
        self._update_task = None

    def startup(self):
        """ 初始化與啟動 """
        # 使用 asyncio 延遲執行，確保 Stage 已完全載入
        asyncio.ensure_future(self._deferred_startup())

    async def _deferred_startup(self):
        self.stage = omni.usd.get_context().get_stage()
        self.items = self.find_assembly_items()
        self.status_dict = {item: 0 for item in self.items} 
        self.last_error_val = {item: 0.0 for item in self.items}
        
        self.apply_physics_parameters()
        self.record_home_positions()
        
        # 啟動背景更新 Task
        if self._update_task: self._update_task.cancel()
        self._update_task = asyncio.ensure_future(self.update_sliders_loop())
        
        # 刷新 UI
        self.refresh_list_ui()

    def shutdown(self):
        """ 清理資源 """
        if self._update_task:
            self._update_task.cancel()
            self._update_task = None
        self.slider_models.clear()
        self.pos_labels.clear()

    def build_ui(self):
        """ 建構 UI (回傳 Frame 供嵌入) """
        main_frame = ui.ScrollingFrame(
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON
        )
        
        with main_frame:
            # [修正] 靠上對齊
            with ui.VStack(spacing=5, padding=10, alignment=ui.Alignment.TOP):
                
                # --- Header ---
                with ui.HStack(height=30):
                    ui.Label("Assembly Sequence Manager (Fixed)", style={"font_size": 18, "color": 0xFFDDDDDD})
                    if self.timeline.is_playing():
                        ui.Label("● PHYSICS ON", width=80, style={"color": 0xFF00FF00, "font_size": 12})
                    else:
                        ui.Label("● PHYSICS OFF", width=80, style={"color": 0xFF0000AA, "font_size": 12})

                ui.Spacer(height=5)
                
                # --- List Header ---
                with ui.HStack(height=20):
                    ui.Label("#", width=30, style={"color": 0xFFAAAAAA})
                    ui.Label("Part Name", width=120, style={"color": 0xFFAAAAAA})
                    ui.Label("Status", width=100, style={"color": 0xFFAAAAAA})
                    ui.Label("Slider / Controls", style={"color": 0xFFAAAAAA})

                # --- Dynamic List Content ---
                # 這裡先建立一個空的 VStack，稍後 refresh_list_ui 會填充它
                self.ui_list_frame = ui.VStack(spacing=4)
                
                ui.Spacer(height=15)
                
                # --- Master Controls ---
                ui.Label("Master Controls", height=20, style={"color": 0xFFAAAAAA})
                with ui.HStack(height=40, spacing=10):
                    ui.Button("RESET ALL (Explode)", clicked_fn=self.reset_scene, style={"background_color": 0xFF442222})
                    ui.Button("STEP >> (Assemble)", clicked_fn=self.step_forward, style={"background_color": 0xFF225522})
                    ui.Button("RE-CALIBRATE", clicked_fn=lambda: asyncio.ensure_future(self.perform_homing_sequence()), style={"background_color": 0xFF222288})

                self.progress_label = ui.Label(f"Ready. Next Step: 1 / {len(self.items)}", height=20, alignment=ui.Alignment.CENTER)
                
                # 底部填充
                ui.Spacer()

        return main_frame

    # ---------------- Logic ----------------
    def refresh_list_ui(self):
        # 確保 ui_list_frame 已經被建立
        if self.ui_list_frame is None: return
        
        self.ui_list_frame.clear()
        self.slider_models.clear()
        self.pos_labels.clear()

        with self.ui_list_frame:
            if not self.items:
                ui.Label("No Prismatic Joints found in stage.", style={"color": 0xFF888888})
                return

            for i, item_path in enumerate(self.items):
                status = self.status_dict.get(item_path, 0)
                report_text = self.failure_report.get(item_path, "---")
                
                text_color = 0xFFCCCCCC
                if status == 1: text_color = 0xFF88FF88   
                elif status == -1: text_color = 0xFF5555FF 
                elif i < self.current_step_index: text_color = 0xFFFFFF88 
                
                bg_color = 0x33000000 if i % 2 == 0 else 0x00000000
                
                with ui.ZStack(height=32):
                    ui.Rectangle(style={"background_color": bg_color})
                    with ui.HStack(spacing=5):
                        ui.Label(f"{i+1}.", width=30, style={"color": 0xFFAAAAAA})
                        
                        name = self.get_display_name(item_path)
                        ui.Label(f"{name}", width=120, style={"color": text_color})

                        status_label = ui.Label(report_text, width=100, style={"color": 0xFF888888})
                        self.pos_labels[item_path] = status_label

                        if status == -1:
                            status_label.style = {"color": 0xFF0000FF, "font_weight": "bold"}
                        elif status == 1:
                            status_label.text = "OK"
                            status_label.style = {"color": 0xFF00FF00}

                        max_limit = self.get_joint_limit(item_path)
                        current_target = self.get_drive_target(item_path)
                        
                        model = ui.SimpleFloatModel(current_target)
                        self.slider_models[item_path] = model
                        
                        model.add_value_changed_fn(lambda m, path=item_path: self.on_slider_manual_change(m, path))
                        model.add_begin_edit_fn(lambda m: self.set_dragging(True))
                        model.add_end_edit_fn(lambda m: self.set_dragging(False))

                        with ui.HStack():
                            slider_style = {"color": 0xFF00AA00} 
                            if status == -1: slider_style = {"color": 0xFF0000AA} 
                            ui.FloatSlider(model, min=0.0, max=max_limit, style=slider_style)
                        
                        ui.Button("Reset", width=35, clicked_fn=lambda idx=i: self.reset_single_item(idx), style={"background_color": 0xFF444444})
                        ui.Button("Up", width=25, clicked_fn=lambda idx=i: self.move_item(idx, -1))
                        ui.Button("Dw", width=25, clicked_fn=lambda idx=i: self.move_item(idx, 1))

    # --- Helpers ---
    def get_prim_safe(self, path_str):
        if not self.stage: return None
        path_str = str(path_str)
        try:
            prim = self.stage.GetPrimAtPath(path_str)
            if prim and prim.IsValid(): return prim
        except: pass
        try:
            prim = self.stage.GetPrimAtPath(Sdf.Path(path_str))
            if prim and prim.IsValid(): return prim
        except: pass
        return None

    def find_assembly_items(self):
        items = []
        if not self.stage: return items
        for prim in self.stage.Traverse():
            if prim.IsA(UsdPhysics.PrismaticJoint):
                parent = prim.GetParent()
                items.append(str(parent.GetPath().pathString))
        items.sort()
        return items

    def apply_physics_parameters(self):
        print("[Assembly] Applying Physics Parameters...")
        for item_path in self.items:
            prim = self.get_prim_safe(item_path)
            if not prim: continue
            for child in prim.GetChildren():
                if child.IsA(UsdPhysics.PrismaticJoint):
                    drive = UsdPhysics.DriveAPI.Get(child, "linear")
                    if not drive: drive = UsdPhysics.DriveAPI.Apply(child, "linear")
                    drive.GetStiffnessAttr().Set(10000.0) 
                    drive.GetDampingAttr().Set(1000.0) 
                    if prim.GetAttribute("drive:linear:physics:maxForce"):
                        prim.GetAttribute("drive:linear:physics:maxForce").Clear() 

    def get_joint_limit(self, item_path):
        prim = self.get_prim_safe(item_path)
        if not prim: return 30.0
        for child in prim.GetChildren():
            if child.IsA(UsdPhysics.PrismaticJoint):
                joint = UsdPhysics.PrismaticJoint(child)
                limit = joint.GetUpperLimitAttr().Get()
                if limit: return limit
        return 30.0

    def record_home_positions(self):
        print("[Assembly] 🟢 Recording current positions as Home.")
        for item in self.items:
            current_z = self.get_current_joint_pos(item)
            self.home_positions[item] = current_z
            if item in self.slider_models:
                self.is_updating_ui = True
                self.slider_models[item].as_float = 0.0
                self.is_updating_ui = False

    async def perform_homing_sequence(self):
        if not self.timeline.is_playing():
            self.timeline.play()
            
        print("[Assembly] 🚀 Starting Re-Calibration...")
        if self.progress_label:
            self.progress_label.text = "Calibrating..."
            self.progress_label.style = {"color": 0xFFFFFF00}

        for item in self.items:
            self.set_joint_target(item, 0.0)
        
        for _ in range(60):
            await omni.kit.app.get_app().next_update_async()

        print("[Assembly] 🟢 Position Captured.")
        for item in self.items:
            current_z = self.get_current_joint_pos(item)
            self.home_positions[item] = current_z
            
        self.reset_scene()
        
        if self.progress_label:
            self.progress_label.text = "Ready."
            self.progress_label.style = {"color": 0xFFFFFFFF}
            
        self.refresh_list_ui()

    def get_semantic_info(self, prim_path):
        prim = self.get_prim_safe(prim_path)
        if not prim: return "[N/A]"
        search_depth = 3
        current_prim = prim
        for _ in range(search_depth):
            if not current_prim or str(current_prim.GetPath()) == "/": break     
            attr = current_prim.GetAttribute("semantics:labels:class")
            if attr and attr.IsValid():
                val = attr.Get()
                return str(val) if val else "[N/A]"
            current_prim = current_prim.GetParent()
        return "[N/A]"

    def get_display_name(self, item_path):
        parts = item_path.split("/")
        return parts[-2] if len(parts) >= 2 else parts[-1]

    def detect_collision_object(self, item_path):
        prim = self.get_prim_safe(item_path)
        if not prim: return "Unknown"

        xform = UsdGeom.Xformable(prim)
        world_transform = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        pos_gf = world_transform.ExtractTranslation()
        pos = (pos_gf[0], pos_gf[1], pos_gf[2])
        
        iface = physx.get_physx_scene_query_interface()
        if not iface: return "PhysX Error"

        detected_hits = []
        def report_hit(hit):
            hit_path = hit.rigid_body
            if not hit_path: return True 
            if item_path in hit_path: return True 
            if "MLB" in hit_path and "Slot" in hit_path: return True 
            if "Ground" in hit_path: return True
            detected_hits.append(hit_path.split("/")[-1])
            return True

        iface.overlap_sphere(5.0, pos, report_hit, False)
        if detected_hits:
            return list(set(detected_hits))[0]
        return "Unknown Block"

    def set_dragging(self, is_dragging):
        self.is_user_dragging = is_dragging

    async def update_sliders_loop(self):
        while True:
            await asyncio.sleep(0.05) 
            if not self.slider_models: continue
            if self.is_user_dragging: continue

            for item_path, model in self.slider_models.items():
                real_abs_z = self.get_current_joint_pos(item_path)
                home_z = self.home_positions.get(item_path, 0.0)
                real_val = abs(real_abs_z - home_z)
                
                if item_path in self.pos_labels and self.status_dict[item_path] == 0:
                    self.pos_labels[item_path].text = f"Pos: {real_val:.1f}"
                    self.pos_labels[item_path].style = {"color": 0xFFCCCCCC}

                if abs(model.as_float - real_val) > 0.1:
                    self.is_updating_ui = True
                    model.as_float = real_val
                    self.is_updating_ui = False

    def on_slider_manual_change(self, model, item_path):
        if self.is_updating_ui: return
        val = model.as_float
        self.set_joint_target(item_path, val)
        if self.status_dict[item_path] != 0:
             self.status_dict[item_path] = 0
             self.failure_report[item_path] = "---"

    def get_drive_target(self, prim_path):
        prim = self.get_prim_safe(prim_path)
        if not prim: return 0.0
        for child in prim.GetChildren():
            if child.IsA(UsdPhysics.PrismaticJoint):
                drive = UsdPhysics.DriveAPI.Get(child, "linear")
                if drive: return drive.GetTargetPositionAttr().Get()
        return 0.0

    def move_item(self, index, direction):
        new_index = index + direction
        if new_index < 0 or new_index >= len(self.items): return
        self.items[index], self.items[new_index] = self.items[new_index], self.items[index]
        self.status_dict[self.items[index]] = 0
        self.status_dict[self.items[new_index]] = 0
        asyncio.ensure_future(self.deferred_refresh())

    async def deferred_refresh(self):
        await omni.kit.app.get_app().next_update_async()
        self.refresh_list_ui()

    def set_joint_target(self, prim_path, target_value):
        prim = self.get_prim_safe(prim_path)
        if not prim: return
        for child in prim.GetChildren():
            if child.IsA(UsdPhysics.PrismaticJoint):
                drive = UsdPhysics.DriveAPI.Get(child, "linear")
                if not drive: drive = UsdPhysics.DriveAPI.Apply(child, "linear")
                drive.GetTargetPositionAttr().Set(target_value)
                return

    def get_current_joint_pos(self, prim_path):
        prim = self.get_prim_safe(prim_path)
        if not prim: return 999.9
        attr = prim.GetAttribute("xformOp:translate")
        if attr and attr.IsValid():
            val = attr.Get()
            if val: return val[2]
        return 999.9

    def reset_single_item(self, index):
        item_path = self.items[index]
        limit = self.get_joint_limit(item_path)
        self.set_joint_target(item_path, limit)
        if item_path in self.slider_models:
            self.is_updating_ui = True
            self.slider_models[item_path].as_float = limit
            self.is_updating_ui = False
            
        self.status_dict[item_path] = 0
        self.failure_report[item_path] = "---"
        
        if index < self.current_step_index:
            self.current_step_index = index
            if self.progress_label:
                self.progress_label.text = f"Rewinding... Next: {self.current_step_index + 1}"
        asyncio.ensure_future(self.deferred_refresh())

    def reset_scene(self):
        self.current_step_index = 0
        self.status_dict = {item: 0 for item in self.items}
        self.failure_report = {item: "---" for item in self.items}
        
        for item in self.items:
            limit = self.get_joint_limit(item)
            self.set_joint_target(item, limit)
            if item in self.slider_models:
                self.is_updating_ui = True
                self.slider_models[item].as_float = limit
                self.is_updating_ui = False
                
        if self.progress_label:
            self.progress_label.text = f"Reset. Ready."
        asyncio.ensure_future(self.deferred_refresh())

    def step_forward(self):
        if not self.timeline.is_playing():
            self.timeline.play()
            
        while self.current_step_index < len(self.items):
             item = self.items[self.current_step_index]
             if self.status_dict[item] == 0: 
                 break
             self.current_step_index += 1
             
        if self.current_step_index >= len(self.items):
             if self.progress_label: self.progress_label.text = "🎉 Assembly Complete!"
             return

        target_item = self.items[self.current_step_index]
        self.set_joint_target(target_item, 0.0)
        
        if target_item in self.slider_models:
            self.is_updating_ui = True
            self.slider_models[target_item].as_float = 0.0
            self.is_updating_ui = False
            
        asyncio.ensure_future(self.monitor_assembly(target_item))
        
        self.current_step_index += 1
        if self.progress_label:
            self.progress_label.text = f"Assembling Step {self.current_step_index}..."
        
        asyncio.ensure_future(self.deferred_refresh())

    async def monitor_assembly(self, item_path):
        for _ in range(90):
            await omni.kit.app.get_app().next_update_async()
            
        current_z = self.get_current_joint_pos(item_path)
        target_z = self.home_positions.get(item_path, 0.0)
        tolerance = 1.0 
        error = abs(current_z - target_z)
        self.last_error_val[item_path] = error
        
        if error < tolerance:
            print(f"[Assembly] SUCCESS.")
            self.status_dict[item_path] = 1 
            self.failure_report[item_path] = "OK"
        else:
            jam_time = self.timeline.get_current_time()
            obstacle = self.detect_collision_object(item_path)
            error_msg = f"⚠ Hit [{obstacle}]"
            print(f"[Assembly] {error_msg} at t={jam_time:.2f}")
            self.status_dict[item_path] = -1 
            self.failure_report[item_path] = error_msg
            
        self.refresh_list_ui()


# ========================================================
#  Extension Wrapper (獨立運作入口)
# ========================================================
class SmartAssemblyExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self._widget = SmartAssemblyWidget()
        self._window = ui.Window("Smart Assembly", width=700, height=650)
        
        with self._window.frame:
            # 在 Extension 模式下，直接顯示 Widget 建構的 UI
            self._widget.build_ui()
            
        self._widget.startup()

    def on_shutdown(self):
        if self._widget:
            self._widget.shutdown()
            self._widget = None
        if self._window:
            self._window.destroy()
            self._window = None