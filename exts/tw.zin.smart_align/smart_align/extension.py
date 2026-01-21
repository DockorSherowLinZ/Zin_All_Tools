import omni.ext
import omni.ui as ui
import omni.kit.viewport.utility
import omni.kit.app
import omni.usd
from pxr import Usd, UsdGeom, Gf

try:
    from omni.isaac.debug_draw import _debug_draw
except ImportError:
    _debug_draw = None

# ========================================================
#  Smart Align Widget
# ========================================================
class SmartAlignWidget:
    def __init__(self):
        self._usd_context = omni.usd.get_context()
        self._selection_sub = None
        self._target_layout = None
        self._combo_target = None
        self._lbl_anchor_info = None
        self._current_paths = []
        self._undo_stack = []
        self._btn_undo = None
        
        # Debug Draw
        self._debug_draw = None
        self._update_sub = None

    def startup(self):
        # 訂閱 Stage 事件 (包含選取變更)
        # 使用 get_stage_event_stream 較為穩健，可避免 Selection 物件 API 差異
        stage_event_stream = self._usd_context.get_stage_event_stream()
        self._selection_sub = stage_event_stream.create_subscription_to_pop(
            self._on_stage_event, name="SmartAlign Stage Event"
        )
        
        # Initialize Debug Draw
        if _debug_draw:
            self._debug_draw = _debug_draw.acquire_debug_draw_interface()
        else:
            print("[SmartAlign] Warning: omni.isaac.debug_draw not available. 3D Overlay disabled.")
            
        self._update_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
            self._on_update, name="SmartAlign Overlay Update"
        )
        
        # 初始化顯示
        self._update_selection_ui()

    def shutdown(self):
        if self._debug_draw:
            self._debug_draw.clear_lines()
            self._debug_draw = None
            
        self._update_sub = None
        self._selection_sub = None
        self._target_layout = None
        self._combo_target = None
        self._lbl_anchor_info = None
        self._current_paths = []
        self._undo_stack = []
        self._btn_undo = None
    
    def _on_target_changed(self, model):
        self._update_anchor_info()
        
        # Reorder Selection so Gizmo snaps to Target (Last Selected)
        if not self._current_paths: return
        
        # Guard against recursive updates if necessary (though UI rebuild should prevent it)
        # Using a simple check to see if we are currently reordering could be added if bugs arise.
        
        try:
            # Note: self._combo_target might be stale if called during destruction, 
            # but model passed in is valid.
            val_model = model # Use the model passed in
            idx = val_model.as_int
            
            # Must strictly use current cached paths to map index
            if idx < 0 or idx >= len(self._current_paths): return
            
            target_path = self._current_paths[idx]
            
            # If already last, skip to avoid unnecessary updates
            if target_path == self._current_paths[-1]: return
            
            # Reorder: Move target to the end
            new_paths = [p for p in self._current_paths if p != target_path]
            new_paths.append(target_path)
            
            # Apply to Stage
            self._usd_context.get_selection().set_selected_prim_paths(new_paths, False)
            
        except Exception as e:
            print(f"[SmartAlign] Selection reorder failed: {e}")

    def _on_update(self, e):
        # 使用 Isaac Debug Draw 繪製標籤 (每禎更新)
        if not self._debug_draw:
            return
            
        # 這裡不清除線條，避免閃爍，或者依賴 DebugDraw 的 Autoclear (通常是每禎清除)
        # 嘗試手動清除以防萬一，若閃爍則移除
        # self._debug_draw.clear_lines() 
        # *Isaac Debug Draw logic*: draw commands usually last one frame.
        
        stage = self._usd_context.get_stage()
        if not stage: return

        # Identify target
        target_path = None
        if self._combo_target and self._current_paths:
            try:
                idx = self._combo_target.model.get_item_value_model().as_int
                if 0 <= idx < len(self._current_paths):
                    target_path = self._current_paths[idx]
            except: pass
            
        if not target_path: return
            
        prim = stage.GetPrimAtPath(target_path)
        if not prim.IsValid(): return
            
        # Get Position
        xform = UsdGeom.Xformable(prim)
        world_matrix = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        trans = world_matrix.ExtractTranslation()
        
        # Check coordinates (adjust Z up a bit to float above)
        pos = [trans[0], trans[1], trans[2] + 1.0] # Offset 1.0 unit up (increased from 0.5)
        
        # Draw Text
        # color=(0, 1, 0, 1) -> Green
        self._debug_draw.draw_text(pos, f"Target: {prim.GetName()}", color=[0.2, 1.0, 0.2, 1.0], font_size=24) # Increased size

    def _on_stage_event(self, event):
        # 監聽選取變更事件
        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            self._update_selection_ui()

    def _update_selection_ui(self):
        # 如果 UI 尚未建立，則不執行
        if not self._target_layout:
            return

        self._current_paths = self._usd_context.get_selection().get_selected_prim_paths()
        
        # Prepare display names (basenames)
        if not self._current_paths:
            items = ["Selection Empty"]
            default_idx = 0
        else:
            items = [p.split("/")[-1] for p in self._current_paths]
            default_idx = len(items) - 1 # Default to last selected

        # Rebuild the Target Selector UI
        self._target_layout.clear()
        with self._target_layout:
            ui.Label("Target Object:", width=100, style={"color": 0xFFDDDDDD})
            # Recreate ComboBox using *items constructor to avoid Model complexity
            self._combo_target = ui.ComboBox(default_idx, *items)
            # Add listener for immediate feedback
            self._combo_target.model.get_item_value_model().add_value_changed_fn(self._on_target_changed)
            
        self._update_anchor_info()

    def _update_anchor_info(self):
        if not self._lbl_anchor_info: return
        
        target_name = "None"
        color = 0xFF888888
        
        if self._combo_target and self._current_paths:
            try:
                idx = self._combo_target.model.get_item_value_model().as_int
                if 0 <= idx < len(self._current_paths):
                    path = self._current_paths[idx]
                    target_name = path.split("/")[-1]
                    color = 0xFF00FF00 # Green
            except: pass
            
        self._lbl_anchor_info.text = f"Anchor: {target_name}"
        self._lbl_anchor_info.style = {"color": color, "font_size": 16}

    def _save_snapshot(self):
        """Save current translation of selected objects to undo stack"""
        paths = self._usd_context.get_selection().get_selected_prim_paths()
        if not paths: return
        
        stage = self._usd_context.get_stage()
        snapshot = {}
        for p in paths:
            prim = stage.GetPrimAtPath(p)
            if not prim.IsValid(): continue
            xform_api = UsdGeom.XformCommonAPI(prim)
            t, _, _, _, _ = xform_api.GetXformVectors(Usd.TimeCode.Default())
            snapshot[p] = t
            
        self._undo_stack.append(snapshot)
        self._update_undo_ui()

    def _on_undo(self):
        """Revert to last snapshot"""
        if not self._undo_stack: return
        
        snapshot = self._undo_stack.pop()
        stage = self._usd_context.get_stage()
        
        for path, pos in snapshot.items():
            prim = stage.GetPrimAtPath(path)
            if not prim.IsValid(): continue
            xform_api = UsdGeom.XformCommonAPI(prim)
            xform_api.SetTranslate(pos)
            
        self._update_undo_ui()
        
    def _update_undo_ui(self):
        if self._btn_undo:
            count = len(self._undo_stack)
            self._btn_undo.text = f"Undo ({count})"
            self._btn_undo.enabled = count > 0

    def build_ui_layout(self):
        scroll_frame = ui.ScrollingFrame(
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
        )
        with scroll_frame:
            # [修正] 靠上對齊
            with ui.VStack(spacing=10, padding=20, alignment=ui.Alignment.TOP):
                
                ui.Label("Align Selection", height=20, style={"color": 0xFFDDDDDD, "font_size": 14})
                # Instruction
                ui.Label("Please select more than two objects for the function to work.", height=20, style={"color": 0xFF888888, "font_size": 12})
                
                ui.Spacer(height=5)
                
                # Target Selector Dropdown Container
                self._target_layout = ui.HStack(height=24)
                
                # Trigger initial update 
                self._update_selection_ui()
                
                ui.Spacer(height=5)
                
                # Undo Button
                self._btn_undo = ui.Button("Undo (0)", height=30, clicked_fn=self._on_undo, enabled=False)
                
                ui.Spacer(height=5)
                
                # ... Action Buttons ...
                with ui.HStack(height=40, spacing=10):
                    ui.Button("Min X", clicked_fn=lambda: self._align_op(0, 'min'))
                    ui.Button("Center X", clicked_fn=lambda: self._align_op(0, 'center'))
                    ui.Button("Max X", clicked_fn=lambda: self._align_op(0, 'max'))

                with ui.HStack(height=40, spacing=10):
                    ui.Button("Min Y", clicked_fn=lambda: self._align_op(1, 'min'))
                    ui.Button("Center Y", clicked_fn=lambda: self._align_op(1, 'center'))
                    ui.Button("Max Y", clicked_fn=lambda: self._align_op(1, 'max'))

                with ui.HStack(height=40, spacing=10):
                    ui.Button("Min Z", clicked_fn=lambda: self._align_op(2, 'min'))
                    ui.Button("Center Z", clicked_fn=lambda: self._align_op(2, 'center'))
                    ui.Button("Max Z", clicked_fn=lambda: self._align_op(2, 'max'))

                ui.Spacer(height=10)
                ui.Button("Drop to Ground", height=40, clicked_fn=self._drop_to_ground, style={"background_color": 0xFF444444})
                
                ui.Spacer()
        return scroll_frame

    def _align_op(self, axis, mode):
        # Save state for Undo
        self._save_snapshot()
        
        stage = self._usd_context.get_stage()
        
        if len(self._current_paths) < 2: 
            return

        # Get Target from ComboBox
        if not self._combo_target: return
        
        idx = self._combo_target.model.get_item_value_model().as_int
        if idx < 0 or idx >= len(self._current_paths):
            return # Invalid selection
            
        target_path = self._current_paths[idx]
        target_prim = stage.GetPrimAtPath(target_path)
        if not target_prim.IsValid(): return
        
        target_xform = UsdGeom.Xformable(target_prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        target_trans = target_xform.ExtractTranslation()
        
        # Apply alignment to ALL OTHER selected objects
        for i, p in enumerate(self._current_paths):
            if i == idx: continue # Skip Target
            
            prim = stage.GetPrimAtPath(p)
            xform_api = UsdGeom.XformCommonAPI(prim)
            t, r, s, p_rot, r_ord = xform_api.GetXformVectors(Usd.TimeCode.Default())
            
            new_pos = Gf.Vec3d(t)
            new_pos[axis] = target_trans[axis] 
            
            xform_api.SetTranslate(new_pos)

    def _drop_to_ground(self):
        # Save state
        self._save_snapshot()
        
        # 簡單的落地邏輯
        stage = self._usd_context.get_stage()
        paths = self._usd_context.get_selection().get_selected_prim_paths()
        for p in paths:
            prim = stage.GetPrimAtPath(p)
            xform_api = UsdGeom.XformCommonAPI(prim)
            t, _, _, _, _ = xform_api.GetXformVectors(Usd.TimeCode.Default())
            new_pos = Gf.Vec3d(t)
            new_pos[2] = 0.0 # 假設 Z-up, 地板在 0
            xform_api.SetTranslate(new_pos)


# ========================================================
#  Extension Wrapper
# ========================================================
class SmartAlignExtension(omni.ext.IExt):
    WINDOW_NAME = "Smart Align"
    MENU_PATH = f"Zin Tools/{WINDOW_NAME}"

    def __init__(self):
        super().__init__()
        self._widget = SmartAlignWidget()
        self._window = None
        self._menu_added = False

    def on_startup(self, ext_id):
        self._build_menu()

    def on_shutdown(self):
        self._remove_menu()
        if self._widget: self._widget.shutdown()
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
                self._window = ui.Window(self.WINDOW_NAME, width=400, height=400)
                self._window.set_visibility_changed_fn(self._on_visibility_changed)
                with self._window.frame:
                    self._widget.build_ui_layout()
            self._window.visible = True
        else:
            if self._window: self._window.visible = False

    def _on_visibility_changed(self, visible):
        if self._menu_added:
            try: omni.kit.ui.get_editor_menu().set_value(self.MENU_PATH, bool(visible))
            except: pass

    # --- Bridge Methods ---
    def startup_logic(self): self._widget.startup()
    def shutdown_logic(self): self._widget.shutdown()
    def build_ui_layout(self): return self._widget.build_ui_layout()