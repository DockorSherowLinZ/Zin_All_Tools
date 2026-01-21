import omni.ui as ui
import omni.usd
import omni.ext
import omni.timeline
import omni.physx as physx
import asyncio
from pxr import Usd, UsdPhysics, UsdGeom, Sdf, Gf

# ========================================================
#  Smart Assembly Widget
# ========================================================
class SmartAssemblyWidget:
    def __init__(self):
        self.timeline = omni.timeline.get_timeline_interface()
        self.items = []
        self.current_step_index = 0
        self.status_dict = {} 
        self.failure_report = {} 
        self.last_error_val = {}
        self.home_positions = {}
        self.ui_list_frame = None
        self.progress_label = None
        self.slider_models = {} 
        self.pos_labels = {} 
        self.is_user_dragging = False 
        self.is_updating_ui = False
        self._update_task = None
        self._stage_listener = None

    def startup(self):
        stream = omni.usd.get_context().get_stage_event_stream()
        self._stage_listener = stream.create_subscription_to_pop(self._on_stage_event, name="smart_assembly_stage_event")
        asyncio.ensure_future(self._deferred_startup())

    def shutdown(self):
        if self._update_task: self._update_task.cancel(); self._update_task = None
        self._stage_listener = None
        self.slider_models.clear(); self.pos_labels.clear()

    async def _deferred_startup(self):
        await omni.kit.app.get_app().next_update_async()
        self.stage = omni.usd.get_context().get_stage()
        self.items = self.find_assembly_items()
        self.status_dict = {item: 0 for item in self.items} 
        self.last_error_val = {item: 0.0 for item in self.items}
        self.record_home_positions()
        if self._update_task: self._update_task.cancel()
        self._update_task = asyncio.ensure_future(self.update_sliders_loop())
        self.refresh_list_ui()

    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.OPENED): asyncio.ensure_future(self._deferred_startup())

    def build_ui_layout(self):
        main_frame = ui.ScrollingFrame(
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON
        )
        with main_frame:
            # 靠上對齊
            with ui.VStack(spacing=5, padding=10, alignment=ui.Alignment.TOP):
                with ui.HStack(height=30):
                    ui.Label("Assembly Sequence Manager (Fixed)", style={"font_size": 18, "color": 0xFFDDDDDD})
                    txt, clr = ("PHYSICS ON", 0xFF00FF00) if self.timeline and self.timeline.is_playing() else ("PHYSICS OFF", 0xFF0000AA)
                    ui.Label(txt, width=80, style={"color": clr, "font_size": 12})
                ui.Spacer(height=5)
                with ui.HStack(height=20):
                    ui.Label("Class", width=80, style={"color": 0xFFAAAAAA})
                    ui.Label("Part Name", width=120, style={"color": 0xFFAAAAAA})
                    ui.Label("Status", width=100, style={"color": 0xFFAAAAAA})
                    ui.Label("Slider / Controls", style={"color": 0xFFAAAAAA})
                self.ui_list_frame = ui.VStack(spacing=4)
                ui.Spacer(height=15)
                ui.Label("Master Controls", height=20, style={"color": 0xFFAAAAAA})
                with ui.HStack(height=40, spacing=10):
                    ui.Button("RESET ALL (Explode)", clicked_fn=self.reset_scene, style={"background_color": 0xFF442222})
                    ui.Button("STEP >> (Assemble)", clicked_fn=self.step_forward, style={"background_color": 0xFF225522})
                    ui.Button("RE-CALIBRATE", clicked_fn=lambda: asyncio.ensure_future(self.perform_homing_sequence()), style={"background_color": 0xFF222288})
                self.progress_label = ui.Label(f"Ready. Next Step: 1 / {len(self.items)}", height=20, alignment=ui.Alignment.CENTER)
                ui.Spacer()
        return main_frame

    def refresh_list_ui(self):
        if self.ui_list_frame is None: return
        self.ui_list_frame.clear(); self.slider_models.clear(); self.pos_labels.clear()
        with self.ui_list_frame:
            if not self.items:
                ui.Label("No Prismatic Joints found in stage.", style={"color": 0xFF888888}); return
            for i, item_path in enumerate(self.items):
                status = self.status_dict.get(item_path, 0)
                txt, color = ("OK", 0xFF00FF00) if status == 1 else ("Error", 0xFF0000FF) if status == -1 else (self.failure_report.get(item_path, "---"), 0xFF888888)
                name_color = 0xFFCCCCCC
                if status == 1: name_color = 0xFF88FF88
                elif status == -1: name_color = 0xFF5555FF
                elif i < self.current_step_index: name_color = 0xFFFFFF88
                bg = 0x33000000 if i % 2 == 0 else 0x00000000
                with ui.ZStack(height=32):
                    ui.Rectangle(style={"background_color": bg})
                    with ui.HStack(spacing=5):
                        ui.Label(self.get_semantic_info(item_path), width=80, style={"color": 0xFFAAAAAA})
                        ui.Label(self.get_display_name(item_path), width=120, style={"color": name_color})
                        lab = ui.Label(txt, width=100, style={"color": color, "font_weight": "bold" if status == -1 else "normal"})
                        self.pos_labels[item_path] = lab
                        model = ui.SimpleFloatModel(self.get_drive_target(item_path))
                        self.slider_models[item_path] = model
                        model.add_value_changed_fn(lambda m, p=item_path: self.on_slider_manual_change(m, p))
                        model.add_begin_edit_fn(lambda m: setattr(self, 'is_user_dragging', True))
                        model.add_end_edit_fn(lambda m: setattr(self, 'is_user_dragging', False))
                        s_style = {"color": 0xFF0000AA} if status == -1 else {"color": 0xFF00AA00}
                        with ui.HStack(): ui.FloatSlider(model, min=0.0, max=self.get_joint_limit(item_path), style=s_style)
                        ui.Button("Reset", width=40, clicked_fn=lambda idx=i: self.reset_single_item(idx), style={"background_color": 0xFF444444})
                        ui.Button("UP", width=30, clicked_fn=lambda idx=i: self.move_item(idx, -1))
                        ui.Button("DW", width=30, clicked_fn=lambda idx=i: self.move_item(idx, 1))

    # Helpers
    def get_prim_safe(self, path):
        try:
            p = omni.usd.get_context().get_stage().GetPrimAtPath(str(path))
            if p and p.IsValid(): return p
        except: pass
        return None

    def find_assembly_items(self):
        if not self.stage: return []
        return sorted([str(p.GetParent().GetPath()) for p in self.stage.Traverse() if p.IsA(UsdPhysics.PrismaticJoint)])

    def apply_physics_parameters(self):
        print("[Assembly] Applying Physics Parameters...")
        if not self.stage: return
        for p_str in self.items:
            prim = self.get_prim_safe(p_str)
            if not prim: continue
            for child in prim.GetChildren():
                if child.IsA(UsdPhysics.PrismaticJoint):
                    drive = UsdPhysics.DriveAPI.Get(child, "linear")
                    if not drive: drive = UsdPhysics.DriveAPI.Apply(child, "linear")
                    drive.GetStiffnessAttr().Set(10000.0); drive.GetDampingAttr().Set(1000.0)
                    if prim.GetAttribute("drive:linear:physics:maxForce"): prim.GetAttribute("drive:linear:physics:maxForce").Clear()

    def get_joint_limit(self, p):
        prim = self.get_prim_safe(p)
        if prim:
            for c in prim.GetChildren():
                if c.IsA(UsdPhysics.PrismaticJoint): return UsdPhysics.PrismaticJoint(c).GetUpperLimitAttr().Get() or 30.0
        return 30.0

    def record_home_positions(self):
        for item in self.items:
            self.home_positions[item] = self.get_current_joint_pos(item)
            if item in self.slider_models:
                self.is_updating_ui = True; self.slider_models[item].as_float = 0.0; self.is_updating_ui = False

    async def perform_homing_sequence(self):
        if not self.timeline.is_playing(): self.timeline.play()
        if self.progress_label: self.progress_label.text = "Calibrating..."; self.progress_label.style = {"color": 0xFFFFFF00}
        self.apply_physics_parameters()
        for item in self.items: self.set_joint_target(item, 0.0)
        for _ in range(60): await omni.kit.app.get_app().next_update_async()
        for item in self.items: self.home_positions[item] = self.get_current_joint_pos(item)
        self.reset_scene()
        if self.progress_label: self.progress_label.text = "Ready."; self.progress_label.style = {"color": 0xFFFFFFFF}
        self.refresh_list_ui()

    def get_semantic_info(self, p):
        prim = self.get_prim_safe(p)
        curr = prim
        for _ in range(3):
            if not curr or str(curr.GetPath()) == "/": break
            attr = curr.GetAttribute("semantics:labels:class") or curr.GetAttribute("semantic:class")
            if attr and attr.IsValid(): return str(attr.Get() or "[N/A]")
            curr = curr.GetParent()
        return "[N/A]"

    def get_display_name(self, p): parts = p.split("/"); return parts[-2] if len(parts) >= 2 else parts[-1]

    def detect_collision_object(self, item_path):
        prim = self.get_prim_safe(item_path)
        if not prim: return "Unknown"
        xf = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()).ExtractTranslation()
        iface = physx.get_physx_scene_query_interface()
        if not iface: return "PhysX Error"
        hits = []
        def report(h):
            hp = h.collision if hasattr(h, 'collision') else h.rigid_body if hasattr(h, 'rigid_body') else None
            if not hp: return True
            hp = str(hp)
            if item_path in hp or "Ground" in hp or ("MLB" in hp and "Slot" in hp): return True
            hits.append(hp.split("/")[-1])
            return True
        iface.overlap_sphere(5.0, (xf[0], xf[1], xf[2]), report, False)
        return list(set(hits))[0] if hits else "Unknown Block"

    async def update_sliders_loop(self):
        while True:
            await asyncio.sleep(0.05)
            if not self.slider_models or self.is_user_dragging: continue
            for p, m in self.slider_models.items():
                cur = self.get_current_joint_pos(p); home = self.home_positions.get(p, 0.0)
                val = abs(cur - home)
                if p in self.pos_labels and self.status_dict[p] == 0:
                    self.pos_labels[p].text = f"Pos: {val:.1f}"; self.pos_labels[p].style = {"color": 0xFFCCCCCC}
                if abs(m.as_float - val) > 0.1:
                    self.is_updating_ui = True; m.as_float = val; self.is_updating_ui = False

    def on_slider_manual_change(self, model, path):
        if self.is_updating_ui: return
        self.set_joint_target(path, model.as_float)
        if self.status_dict[path] != 0: self.status_dict[path] = 0; self.failure_report[path] = "---"

    def get_drive_target(self, p):
        prim = self.get_prim_safe(p)
        if prim:
            for c in prim.GetChildren():
                if c.IsA(UsdPhysics.PrismaticJoint):
                    d = UsdPhysics.DriveAPI.Get(c, "linear")
                    if d: return d.GetTargetPositionAttr().Get()
        return 0.0

    def move_item(self, idx, d):
        n = idx + d
        if 0 <= n < len(self.items):
            self.items[idx], self.items[n] = self.items[n], self.items[idx]
            self.status_dict[self.items[idx]] = 0; self.status_dict[self.items[n]] = 0
            asyncio.ensure_future(self._defer_refresh())

    async def _defer_refresh(self): await omni.kit.app.get_app().next_update_async(); self.refresh_list_ui()

    def set_joint_target(self, p, val):
        prim = self.get_prim_safe(p)
        if prim:
            for c in prim.GetChildren():
                if c.IsA(UsdPhysics.PrismaticJoint):
                    d = UsdPhysics.DriveAPI.Get(c, "linear")
                    if not d: d = UsdPhysics.DriveAPI.Apply(c, "linear")
                    d.GetTargetPositionAttr().Set(val); return

    def get_current_joint_pos(self, p):
        prim = self.get_prim_safe(p)
        if prim:
            val = prim.GetAttribute("xformOp:translate").Get()
            if val: return val[2]
        return 999.9

    def reset_single_item(self, idx):
        p = self.items[idx]; lim = self.get_joint_limit(p)
        self.set_joint_target(p, lim)
        if p in self.slider_models: self.is_updating_ui = True; self.slider_models[p].as_float = lim; self.is_updating_ui = False
        self.status_dict[p] = 0; self.failure_report[p] = "---"
        if idx < self.current_step_index:
            self.current_step_index = idx
            if self.progress_label: self.progress_label.text = f"Rewinding... Next: {self.current_step_index + 1}"
        asyncio.ensure_future(self._defer_refresh())

    def reset_scene(self):
        self.current_step_index = 0
        self.status_dict = {i: 0 for i in self.items}
        self.failure_report = {i: "---" for i in self.items}
        self.apply_physics_parameters()
        for i in self.items:
            lim = self.get_joint_limit(i); self.set_joint_target(i, lim)
            if i in self.slider_models: self.is_updating_ui = True; self.slider_models[i].as_float = lim; self.is_updating_ui = False
        if self.progress_label: self.progress_label.text = "Reset. Ready."
        asyncio.ensure_future(self._defer_refresh())

    def step_forward(self):
        if not self.timeline.is_playing(): self.timeline.play()
        while self.current_step_index < len(self.items):
            if self.status_dict[self.items[self.current_step_index]] == 0: break
            self.current_step_index += 1
        if self.current_step_index >= len(self.items):
            if self.progress_label: self.progress_label.text = "Assembly Complete!"; return
        target = self.items[self.current_step_index]
        self.set_joint_target(target, 0.0)
        if target in self.slider_models: self.is_updating_ui = True; self.slider_models[target].as_float = 0.0; self.is_updating_ui = False
        asyncio.ensure_future(self.monitor_assembly(target))
        self.current_step_index += 1
        if self.progress_label: self.progress_label.text = f"Assembling Step {self.current_step_index}..."
        asyncio.ensure_future(self._defer_refresh())

    async def monitor_assembly(self, p):
        for _ in range(90): await omni.kit.app.get_app().next_update_async()
        cur, tgt = self.get_current_joint_pos(p), self.home_positions.get(p, 0.0)
        if abs(cur - tgt) < 1.0:
            print("[Assembly] SUCCESS."); self.status_dict[p] = 1; self.failure_report[p] = "OK"
        else:
            obs = self.detect_collision_object(p); msg = f"Hit [{obs}]"
            print(f"[Assembly] {msg}"); self.status_dict[p] = -1; self.failure_report[p] = msg
        self.refresh_list_ui()


# ========================================================
#  Extension Wrapper
# ========================================================
class SmartAssemblyExtension(omni.ext.IExt):
    WINDOW_NAME = "Smart Assembly"
    MENU_PATH = f"Zin Tools/{WINDOW_NAME}"

    def __init__(self):
        super().__init__()
        # [關鍵修正] 在 __init__ 中就初始化 Widget
        # 這樣 Zin All Tools 呼叫 startup_logic 時，self._widget 就已經存在了
        self._widget = SmartAssemblyWidget()
        self._window = None
        self._menu_added = False

    def on_startup(self, ext_id):
        # 獨立啟動時才會呼叫這裡
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
                self._window = ui.Window(self.WINDOW_NAME, width=700, height=650)
                self._window.set_visibility_changed_fn(self._on_visibility_changed)
                with self._window.frame:
                    self._widget.build_ui_layout() # [重要] 呼叫的是 build_ui_layout
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
        if self._widget: self._widget.startup()
    
    def shutdown_logic(self): 
        if self._widget: self._widget.shutdown()
    
    def build_ui_layout(self): 
        # Zin All Tools 會呼叫此方法
        return self._widget.build_ui_layout()