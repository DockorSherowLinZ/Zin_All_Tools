import omni.ui as ui
import omni.usd
import omni.ext
import omni.timeline
import omni.physx as physx
import asyncio
import json
import re
import time
import omni.kit.notification_manager as nm
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
        # New State for Multi-Config
        self.configs = [] 
        self.current_config_index = 0
        self.ui_model_combo = None
        self.ui_field_name = None
        self.ui_model_combo = None
        self.ui_field_name = None
        self.ui_combo_box = None
        self._ui_window = None
        self.ui_root_frame = None 
        self._temp_message = None 
        self._delete_confirm_time = 0.0 # [New] For verify delete
        self.ui_btn_delete = None
        self.ui_btn_step = None
        self.ui_btn_calibrate = None

    def set_window(self, window):
        self._ui_window = window

    def startup(self):
        stream = omni.usd.get_context().get_stage_event_stream()
        self._stage_listener = stream.create_subscription_to_pop(self._on_stage_event, name="smart_assembly_stage_event")
        asyncio.ensure_future(self._deferred_startup())

    def shutdown(self):
        if self._update_task: self._update_task.cancel(); self._update_task = None
        self._stage_listener = None
        self.slider_models.clear(); self.pos_labels.clear()
        if self.ui_list_frame:
            self.ui_list_frame.clear()
            self.ui_list_frame = None

    async def _deferred_startup(self):
        await omni.kit.app.get_app().next_update_async()
        self.stage = omni.usd.get_context().get_stage()
        self.items = self.find_assembly_items()
        self.status_dict = {item: 0 for item in self.items} 
        self.last_error_val = {item: 0.0 for item in self.items}
        self.record_home_positions()
        # [Lifecycle] Do NOT start loop here. Loop starts only when UI is built.
        # if self._update_task: self._update_task.cancel()
        # self._update_task = asyncio.ensure_future(self.update_sliders_loop())
        self.refresh_list_ui()

    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.OPENED): asyncio.ensure_future(self._deferred_startup())

    def build_ui_layout(self):
        # [Refactor] Store root frame to allow self-rebuild without window reference
        self.ui_root_frame = ui.ScrollingFrame(
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON
        )
        self._build_content()
        return self.ui_root_frame

    def _build_content(self):
        # Clears existing children if we are rebuilding inside the same frame
        # But `with frame:` appends? No, we should ensure it's empty if rebuilding.
        # But `build_ui_layout` creates new frame. 
        # `_defer_refresh_full` will clear it.
        
        if not self.ui_root_frame: return

        with self.ui_root_frame:
            # 靠上對齊
            with ui.VStack(spacing=5, padding=10, alignment=ui.Alignment.TOP):
                with ui.HStack(height=30):
                    ui.Label("Assembly Sequence Manager (Fixed)", style={"font_size": 18, "color": 0xFFDDDDDD})
                    txt, clr = ("PHYSICS ON", 0xFF00FF00) if self.timeline and self.timeline.is_playing() else ("PHYSICS OFF", 0xFF3D3DF5)
                    ui.Label(txt, width=80, style={"color": clr, "font_size": 12})
                ui.Spacer(height=5)
                ui.Spacer(height=5)
                
                # [UI] Config Manager Section
                ui.Label("Configuration Manager", height=20, style={"color": 0xFFAAAAAA})
                
                # Row 1: Selection & Name
                with ui.HStack(height=30, spacing=10):
                    # Use a rebuildable container for the combo
                    self.ui_combo_box = ui.ComboBox(self.current_config_index, *[c["name"] for c in self.configs])
                    self.ui_model_combo = self.ui_combo_box.model
                    self.ui_combo_box.model.add_item_changed_fn(self.on_config_selected)
                    
                    self.ui_field_name = ui.StringField(height=24)
                    # We remove auto-save on end_edit to rely on explicit Rename button, 
                    # but we could keep it if desired. For safety, let's just let the button do it.
                    # self.ui_field_name.model.add_end_edit_fn(self.on_config_renamed) 
                    if self.configs: self.ui_field_name.model.as_string = self.configs[self.current_config_index]["name"]

                # Row 2: Actions
                with ui.HStack(height=30, spacing=10):
                    # [Style] Remove custom colors to match Min X (Standard)
                    ui.Button("RENAME", clicked_fn=self.rename_current_config, tooltip="Rename current config to text in field")
                    ui.Button("SAVE NEW", clicked_fn=self.save_current_as_new, tooltip="Save current state as a NEW config")
                    # [UX] Delete is now Red-ish (Swapped from Blue)
                    self.ui_btn_delete = ui.Button("DELETE", clicked_fn=self.delete_current_config, style={"background_color": 0xFF222288}, tooltip="Delete current config (Double Click)")
                    self._setup_hover(self.ui_btn_delete, 0xFF222288)

                ui.Spacer(height=10)
                with ui.HStack(height=20):
                    ui.Label("Class", width=80, style={"color": 0xFFAAAAAA})
                    ui.Label("Part Name", width=120, style={"color": 0xFFAAAAAA})
                    ui.Label("Status", width=100, style={"color": 0xFFAAAAAA})
                    ui.Label("Slider / Controls", style={"color": 0xFFAAAAAA})
                self.ui_list_frame = ui.VStack(spacing=4)
                ui.Spacer(height=15)
                ui.Label("Master Controls", height=20, style={"color": 0xFFAAAAAA})
                with ui.HStack(height=40, spacing=10):
                    self.ui_btn_step = ui.Button("STEP >> (Assemble)", clicked_fn=self.step_forward, style={"background_color": 0xFF225522})
                    self._setup_hover(self.ui_btn_step, 0xFF225522)
                    # [Style] Remove custom color for RESET ALL to match Min X
                    ui.Button("RESET ALL (Explode)", clicked_fn=self.reset_scene)
                    # [Smart UX] Calibrate button changes if error detected
                    # Swapped: Normal is Standard (None), Error (Auto Fix) is Red (0xFF222288) based on recent swap request?
                    # User asked to make RESET ALL, RENAME, SAVE NEW, RE-CALIBRATE same as Min X (Standard Dark).
                    # So we remove background color for the NORMAL state.
                    # Use style default. 
                    
                    any_error = any(v == -1 for v in self.status_dict.values())
                    cal_txt = "AUTO FIX (Calibrate)" if any_error else "RE-CALIBRATE"
                    # If error, keep warning color (Red: 0xFF222288 from swap?). 
                    # If normal, use default (None).
                    cal_style = {"background_color": 0xFF222288} if any_error else {}
                    
                    self.ui_btn_calibrate = ui.Button(cal_txt, clicked_fn=lambda: asyncio.ensure_future(self.perform_homing_sequence()), style=cal_style)
                self.progress_label = ui.Label(f"Ready. Next Step: 1 / {len(self.items)}", height=20, alignment=ui.Alignment.CENTER)
                # [New] Apply persistent message if exists
                if self._temp_message:
                    self.progress_label.text = self._temp_message
                    self.progress_label.style = {"color": 0xFF00FF00}
                    self._temp_message = None # Clear after consuming
                ui.Spacer()
        
        # [Lifecycle] Ensure List is populated and Loop is active
        self.refresh_list_ui()
        
        if self._update_task: self._update_task.cancel()
        self._update_task = asyncio.ensure_future(self.update_sliders_loop())

    def refresh_list_ui(self):
        if self.ui_list_frame is None: return
        self.ui_list_frame.clear(); self.slider_models.clear(); self.pos_labels.clear()
        with self.ui_list_frame:
            if not self.items:
                ui.Label("No Prismatic Joints found in stage.", style={"color": 0xFF888888}); return
            for i, item_path in enumerate(self.items):
                status = self.status_dict.get(item_path, 0)
                txt, color = ("OK", 0xFF00FF00) if status == 1 else ("Error", 0xFF3D3DF5) if status == -1 else (self.failure_report.get(item_path, "---"), 0xFF888888)
                name_color = 0xFFCCCCCC
                if status == 1: name_color = 0xFF88FF88
                elif status == -1: name_color = 0xFF3D3DF5
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
                        s_style = {"color": 0xFF3D3DF5} if status == -1 else {"color": 0xFF00AA00}
                        with ui.HStack(): ui.FloatSlider(model, min=0.0, max=self.get_joint_limit(item_path), style=s_style)
                        ui.Button("Reset", width=40, clicked_fn=lambda idx=i: self.reset_single_item(idx))
                        ui.Button("UP", width=30, clicked_fn=lambda idx=i: self.move_item(idx, -1))
                        ui.Button("DW", width=30, clicked_fn=lambda idx=i: self.move_item(idx, 1))

    # [UX] Hover Helper
    def _setup_hover(self, btn, base_color):
        if not btn: return
        
        # Calc brighter color (+20%)
        # Format: 0xAABBGGRR
        a = (base_color >> 24) & 0xFF
        b = (base_color >> 16) & 0xFF
        g = (base_color >> 8) & 0xFF
        r = base_color & 0xFF
        
        # Increase brightness
        b = min(255, int(b * 1.4))
        g = min(255, int(g * 1.4))
        r = min(255, int(r * 1.4))
        
        hover_color = (a << 24) | (b << 16) | (g << 8) | r
        
        def _on_hover(hovered):
            btn.style = {"background_color": hover_color if hovered else base_color}
            
        btn.set_mouse_hovered_fn(_on_hover)

    # Helpers
    def get_prim_safe(self, path):
        try:
            p = omni.usd.get_context().get_stage().GetPrimAtPath(str(path))
            if p and p.IsValid(): return p
        except: pass
        return None

    def find_assembly_items(self):
        if not self.stage: return []
        # [Defensive] Ensure state exists if hot-reload preserved old instance
        if not hasattr(self, 'current_config_index'): self.current_config_index = 0
        if not hasattr(self, 'configs'): self.configs = []
        
        # Find all current prismatic items in scene as baseline
        found_items = sorted([str(p.GetParent().GetPath()) for p in self.stage.Traverse() if p.IsA(UsdPhysics.PrismaticJoint)])
        
        # Load Configs from RootLayer CustomData
        saved_configs = []
        try:
            layer = self.stage.GetRootLayer()
            if layer and layer.customLayerData:
                data = layer.customLayerData.get("smart_assembly_configs")
                if data and isinstance(data, str):
                    saved_configs = json.loads(data)
        except: pass

        # Init configs if empty
        if not saved_configs:
            saved_configs = [{"name": "config 1", "sequence": list(found_items)}]

        # [Sanitize] Ensure unique names
        seen_names = {}
        sanitized = []
        for c in saved_configs:
            name = c.get("name", "config")
            if name in seen_names:
                # Rename duplicate
                count = seen_names[name]
                new_name = f"{name}_{count}"
                seen_names[name] += 1
                c["name"] = new_name
            else:
                seen_names[name] = 1
            sanitized.append(c)
        self.configs = sanitized
        
        # Validate Current Index
        if self.current_config_index >= len(self.configs):
            self.current_config_index = 0
            
        # Apply current config sequence
        # We need to intersect with currently existing items to avoid orphans
        target_seq = self.configs[self.current_config_index]["sequence"]
        
        # Reconstruct list: items in target_seq (order matters) + items NOT in target_seq (appended)
        final_list = []
        # 1. Add items present in config
        for path in target_seq:
            if path in found_items:
                final_list.append(path)
        # 2. Add remaining new items
        existing_set = set(final_list)
        for path in found_items:
            if path not in existing_set:
                final_list.append(path)
                
        # Update UI ComboBox
        self.update_combo_items()
        
        return final_list

    def update_combo_items(self):
        if not self.ui_model_combo: return
        # Re-populate combo
        items = [c["name"] for c in self.configs]
        # This is a bit hacky for omni.ui, we likely need to replace the valid items
        # But simple way: get items list reference? No, omni.ui.AbstractItemModel is different.
        # Standard omni.ui.ComboBox doesn't easily support dynamic replacement without custom model.
        # Let's try to just set the child items if it's a SimpleStringModel (default for ComboBox(primitive)).
        # Actually `ui.ComboBox(0, ...)` creates an internal model.
        # We will assume standard usage. We might need to recreate the combo or use a proper listener.
        # Wait, omni.ui ComboBox constructor: `ComboBox(default_index, *items)`
        # To update, we usually need to replace the model OR if we use the simple constructor, it's hard.
        # Let's use a trick: If we can't easily update valid items, we might need to rely on `refresh_list_ui` logic 
        # but `find_assembly_items` is called at startup.
        # Let's implement a safe way: Create a NEW model and assign it.
        pass # Handle in refresh_list_ui or specific update method involving model replacement
        
    def _refresh_combo_full(self):
         # Helper to sync ComboBox items with self.configs
         if not self.ui_model_combo: return
         # We can't clear items easily on default model. 
         # Best approach: We should have used `ui.SimpleStringModel`.
         # Let's assume we modify the code above to pass a model if needed. 
         # BUT easier fix: manipulate the `AbstractItemModel` if possible.
         # Re-building the whole UI frame or just the combo is cleaner. 
         # Let's just update the internal items if possible.
         
         # For simplicity in this edit, let's just make sure `on_config_selected` works.
         # Actually, we need to rebuild the combo items. 
         # Let's do this: we will store the reference to the *ComboBox* itself, not just the model, 
         # and we might need to set a new model.
         pass 

    def on_config_selected(self, model, item):
        idx = model.get_item_value_model().as_int
        if 0 <= idx < len(self.configs):
            self.current_config_index = idx
            self.items = self.sync_sequence(self.configs[idx]["sequence"])
            # Update the text field to match selection
            if self.ui_field_name:
                self.ui_field_name.model.as_string = self.configs[idx]["name"]
            self.refresh_list_ui()

    def rename_current_config(self):
        new_name = self.ui_field_name.model.as_string.strip()
        if not new_name: return
        
        if 0 <= self.current_config_index < len(self.configs):
            old_name = self.configs[self.current_config_index]["name"]
            if old_name == new_name: return # No change

            self.configs[self.current_config_index]["name"] = new_name
            self.persist_configs()
            self._temp_message = f"Renamed: '{old_name}' -> '{new_name}'"
            asyncio.ensure_future(self._defer_refresh_full())

    def delete_current_config(self):
        if not self.configs: return
        
        # [UX] Double Click Confirmation
        now = time.time()
        if now - self._delete_confirm_time > 3.0:
            # First click
            self._delete_confirm_time = now
            if self.ui_btn_delete:
                self.ui_btn_delete.text = "CONFIRM?"
                # [UX] User requested Confirm color to be same as Delete (Reddish: 0xFF222288)
                self.ui_btn_delete.style = {"background_color": 0xFF222288}
                # Optional: Auto-reset after 3s (visual only, requires task)
            return

        # Second click (Confirmed)
        self._delete_confirm_time = 0.0 # Reset
        
        # Prevent deleting the last one? Or allow and reset to default?
        # Let's allow, but if empty, recreate default.
        deleted_name = self.configs[self.current_config_index]["name"]
        
        del self.configs[self.current_config_index]
        
        if not self.configs:
            # Re-init default
            self.configs = [{"name": "config 1", "sequence": list(self.items)}]
            self.current_config_index = 0
            self._temp_message = "Reset to default config 1"
        else:
            # Shift index safely
            if self.current_config_index >= len(self.configs):
                self.current_config_index = len(self.configs) - 1
            self._temp_message = f"Deleted: {deleted_name}"
            
        # Sync items to new selection
        self.items = self.sync_sequence(self.configs[self.current_config_index]["sequence"])
        self.persist_configs()
        asyncio.ensure_future(self._defer_refresh_full())

    async def _defer_refresh_full(self):
        # Full rebuild using root frame, works even if embedded in Zin All Tools
        await omni.kit.app.get_app().next_update_async()
        if self.ui_root_frame:
            self.ui_root_frame.clear()
            self._build_content()
            
    def update_combo_items(self):
        # This is handled by _defer_refresh_full mostly, 
        # but if we want to just update model without rebuild:
        if not self.ui_model_combo: return
        # Validating index
        if self.current_config_index >= len(self.configs): self.current_config_index = 0

    def _refresh_combo_full(self):
         pass 

    def sync_sequence(self, stored_seq):
        # Same logic as find_assembly_items merge
        current_in_stage = set([str(p.GetParent().GetPath()) for p in self.stage.Traverse() if p.IsA(UsdPhysics.PrismaticJoint)])
        final = []
        for p in stored_seq:
            if p in current_in_stage: final.append(p)
        for p in sorted(list(current_in_stage)):
            if p not in final: final.append(p)
        return final

    def save_current_as_new(self):
        # Logic Update: 
        # 1. Check if user typed a custom name in the field.
        # 2. If user typed something NEW (different from current loaded config name), use that.
        # 3. If user kept the same name, assume they want a sequential auto-save (config N+1).
        
        current_loaded_name = self.configs[self.current_config_index]["name"]
        current_loaded_seq = self.configs[self.current_config_index]["sequence"]
        
        # [Global Check] Block if sequence is identical to ANY existing config
        # This replaces the previous "local check" against current_loaded_seq, covering it implicitly.
        for c in self.configs:
            if self.items == c["sequence"]:
                conflict_name = c["name"]
                print(f"[SmartAssembly] Sequence matches existing config '{conflict_name}'. Save aborted.")
                self._temp_message = f"Error: Same sequence as '{conflict_name}'!"
                self.progress_label.style = {"color": 0xFF3D3DF5}
                asyncio.ensure_future(self._defer_refresh_full())
                return

        input_name = self.ui_field_name.model.as_string.strip()
        
        new_name = ""
        existing_names = set(c["name"] for c in self.configs)

        # Case A: User typed a custom name
        if input_name and input_name != current_loaded_name:
            candidate = input_name
            # [Strict Check] If name exists, BLOCK.
            if candidate in existing_names:
                print(f"[SmartAssembly] Name '{candidate}' already exists. Save aborted.")
                self._temp_message = f"Error: Name '{candidate}' exists!"
                self.progress_label.style = {"color": 0xFF3D3DF5}
                asyncio.ensure_future(self._defer_refresh_full())
                return
            new_name = candidate
            
        else:
            # Case B: User didn't change name -> Auto Increment logic
            # Logic: Parse all "config N", find Max N.
            max_n = 0
            
            import re
            pattern = re.compile(r"config\s+(\d+)")
            
            for name in existing_names:
                m = pattern.match(name)
                if m:
                    val = int(m.group(1))
                    if val > max_n: max_n = val
            
            next_n = max_n + 1
            while True:
                candidate = f"config {next_n}"
                if candidate not in existing_names:
                    new_name = candidate
                    break
                next_n += 1
        
        new_entry = {"name": new_name, "sequence": list(self.items)}
        self.configs.append(new_entry)
        self.current_config_index = len(self.configs) - 1
        
        self.persist_configs()
        
        print(f"[SmartAssembly] Saved New Config: {new_name}")
        self._temp_message = f"Saved: {new_name}"
            
        asyncio.ensure_future(self._defer_refresh_full())
        
        self.persist_configs()
        
        print(f"[SmartAssembly] Saved New Config: {new_name}")
        self._temp_message = f"Saved: {new_name}"
            
        asyncio.ensure_future(self._defer_refresh_full())

    def persist_configs(self):
        try:
            stage = omni.usd.get_context().get_stage()
            if not stage: return
            layer = stage.GetRootLayer()
            if not layer: return
            
            data_str = json.dumps(self.configs)
            current_data = layer.customLayerData
            current_data["smart_assembly_configs"] = data_str
            layer.customLayerData = current_data
        except Exception as e:
            print(f"Persist Failed: {e}")

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
            # [Lifecycle] Throttled Loop & Auto-Termination
            await asyncio.sleep(0.2)
            
            # Check if UI is alive
            try:
                # If frame is None or destroyed, stop.
                if not self.ui_list_frame:
                    break
                # Optional: Check if we are still the active tab? 
                # If ToolsBox cleared us, ui_list_frame might still be a valid Python object but logically dead.
                # Checking visibility might help if parent is gone?
                # For now, let's assume we rely on manual cancellation OR garbage collection eventually?
                # Actually, wait. ToolsBox clears the parent. 
                # Does self.ui_list_frame become invalid? 
                # Let's add a check for a property that would fail.
                _ = self.ui_list_frame.visible 
            except:
                break

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
            if self.progress_label: self.progress_label.text = "Assembly Complete!"; self.progress_label.style = {"color": 0xFF00FF00}
            # [UX] Toast Notification
            nm.post_notification(nm.Notification("Assembly Sequence Complete!", duration=3))
            return
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
                # [Fix] Inject window reference for refresh logic
                self._widget.set_window(self._window)
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