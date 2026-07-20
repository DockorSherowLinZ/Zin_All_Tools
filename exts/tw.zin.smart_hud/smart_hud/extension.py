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
    def __init__(self, callback, ui_instance):
        self._callback = callback
        self._ui_instance = ui_instance
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
            
        # Check machine type attribute or aif attributes
        attr = prim.GetAttribute("machine_type")
        aif_attr = prim.GetAttribute("aif:core:assetClass")
        
        if (attr and attr.IsValid()) or (aif_attr and aif_attr.IsValid()):
            m_type = attr.Get() if (attr and attr.IsValid()) else ""
            
            sub_title_attr = prim.GetAttribute("hud_sub_title")
            sub_title = sub_title_attr.Get() if sub_title_attr and sub_title_attr.IsValid() else ""
            
            content_attr = prim.GetAttribute("hud_content")
            content = content_attr.Get() if content_attr and content_attr.IsValid() else ""
            
            # 讀取 aif:core 屬性以相容 smart_info_panel 的資料
            asset_class_attr = prim.GetAttribute("aif:core:assetClass")
            if asset_class_attr and asset_class_attr.IsValid() and not m_type:
                 m_type = asset_class_attr.Get()
                 
            model_num_attr = prim.GetAttribute("aif:core:modelNumber")
            if model_num_attr and model_num_attr.IsValid() and not sub_title:
                 sub_title = model_num_attr.Get()
                 
            desc_attr = prim.GetAttribute("aif:core:assetDescription")
            if desc_attr and desc_attr.IsValid() and not content:
                 content = desc_attr.Get()

            # 如果連 aif 屬性都沒有，且又沒有 machine_type，就直接跳出
            if not m_type:
                 self._callback(None, None)
                 return

            # Extract world transform and dimensions
            xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
            world_transform = xform_cache.GetLocalToWorldTransform(prim)
            
            # Use BBox to find top center for better placement
            purposes = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render]
            bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes)
            bbox = bbox_cache.ComputeWorldBound(prim)
            world_box = bbox.ComputeAlignedBox()
            
            if not world_box.IsEmpty():
                min_pt = world_box.GetMin()
                max_pt = world_box.GetMax()
                
                # Z-up environment
                top_center = (
                    (min_pt[0] + max_pt[0]) / 2.0,
                    (min_pt[1] + max_pt[1]) / 2.0,
                    max_pt[2]
                )
                translation = top_center
            else:
                translation = world_transform.ExtractTranslation()
            
            # Check visibility settings
            show_dynamic = True
            show_static = True
            if self._ui_instance:
                if hasattr(self._ui_instance, "cb_dynamic"):
                    show_dynamic = self._ui_instance.cb_dynamic.model.get_value_as_bool()
                if hasattr(self._ui_instance, "cb_static"):
                    show_static = self._ui_instance.cb_static.model.get_value_as_bool()

            self._callback({"type": m_type, "sub": sub_title, "content": content, "show_dynamic": show_dynamic, "show_static": show_static}, translation)
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
        
        # Generic models for custom HUDs
        self.generic_title = ui.SimpleStringModel("Custom Item")
        self.generic_sub = ui.SimpleStringModel("Sub Title")
        self.generic_content = ui.SimpleStringModel("Status: Active")


# ==============================================================================
# HUD Engine
# ==============================================================================
class GrayboxHUDEngine:
    def __init__(self, ui_instance):
        self.view_model = HUDViewModel()
        self.ui_pool = {} 
        self.scene_view = None
        self._running = True
        self._telemetry_task = None
        self._selection_agent = None
        self._color_sub = None
        self._ui_instance = ui_instance
        
        self._build_ui()
        self._start_telemetry()
        
        # Initialize Kit USD Selection Agent
        self._selection_agent = UsdSelectionAgent(self.on_selection_changed, self._ui_instance)

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
            # 增加 widget 高度以容納整合後的面板
            widget = sc.Widget(width=300, height=240)
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

    def _build_generic_ui(self):
        pass

    def _create_generic_widget(self, name):
        transform = sc.Transform(look_at=sc.Transform.LookAt.CAMERA, visible=False)
        pool_item_dict = {"transform": transform, "dynamic_hud_vbox": None, "static_hud_frame": None, "bg_rect": None}
        
        with transform:
            widget = sc.Widget(width=300, height=240)
            
            def build_ui():
                with ui.ZStack():
                    pool_item_dict["bg_rect"] = ui.Rectangle(style={"background_color": ui.color(0.1, 0.1, 0.15, 0.85), "border_color": 0xCC00FFFF, "border_width": 2, "border_radius": 5})
                    with ui.HStack():
                        ui.Spacer(width=15)
                        with ui.VStack(spacing=5):
                            ui.Spacer(height=10)
                            
                            # ── 動態 HUD 區塊 ──
                            pool_item_dict["dynamic_hud_vbox"] = ui.VStack(spacing=2)
                            with pool_item_dict["dynamic_hud_vbox"]:
                                ui.Label("", model=self.view_model.generic_title, style={"color": 0xFFFFFFFF, "font_size": 20, "weight": "bold"})
                                ui.Label("", model=self.view_model.generic_sub, style={"color": 0xFFFFAA00, "font_size": 14})
                                ui.Label("", model=self.view_model.generic_content, style={"color": 0xFFAAAAAA, "font_size": 14})
                                
                                ui.Spacer(height=5)
                                ui.Line(style={"color": 0xFF444444, "border_width": 1})
                                ui.Spacer(height=5)
                            
                            # ── 靜態 AIF Metadata 區塊 (移植自 Smart Info Panel) ──
                            # 為了避免在 3D 場景中點擊 CollapsableFrame 觸發 Omniverse 預設的射線點擊 (Raycast/Selection) 
                            # 導致選取焦點亂跑，這裡改用普通的 Frame 或是 Vstack 來代替。
                            pool_item_dict["static_hud_frame"] = ui.VStack(spacing=2)
                            with pool_item_dict["static_hud_frame"]:
                                ui.Label("Factory Info", style={"color": 0xFF00AAFF, "font_size": 14, "weight": "bold"})
                                ui.Spacer(height=3)
                                with ui.HStack(height=16):
                                    ui.Label("Asset Class:", width=90, style={"color": 0xFF888888, "font_size": 12})
                                    ui.Label("", model=self.view_model.generic_title, style={"color": 0xFFDDDDDD, "font_size": 12})
                                with ui.HStack(height=16):
                                    ui.Label("Model No:", width=90, style={"color": 0xFF888888, "font_size": 12})
                                    ui.Label("", model=self.view_model.generic_sub, style={"color": 0xFFDDDDDD, "font_size": 12})
                                with ui.HStack(height=16):
                                    ui.Label("Status:", width=90, style={"color": 0xFF888888, "font_size": 12})
                                    ui.Label("Active", style={"color": 0xFF44AA44, "font_size": 12})
                            
                            ui.Spacer(height=10)
                        ui.Spacer(width=15)
            
            widget.frame.set_build_fn(build_ui)
            pool_item_dict["widget"] = widget
            
        return pool_item_dict

    def on_selection_changed(self, hud_data, translation):
        for key, pool_item in self.ui_pool.items():
            pool_item["transform"].visible = False
            
        if hud_data and translation is not None:
            m_type = hud_data.get("type", "")
            
            # 檢查是否為預設的 UI，如果不是則使用 generic_ui
            if m_type not in ["AOI", "Robot", "ManualStation"]:
                m_type = "Generic"  # 將所有自訂的屬性都歸類為使用 Generic UI

            # Create a generic widget pool item if not a preset
            if m_type not in self.ui_pool:
                if self.scene_view and self.scene_view.scene:
                    with self.scene_view.scene:
                        # 呼叫新的建立函式，它會返回完整的字典
                        self.ui_pool[m_type] = self._create_generic_widget(m_type)
                else:
                    return # Safe check if scene is destroyed
                
            # Update generic models if it's a generic type
            if m_type == "Generic":
                self.view_model.generic_title.set_value(hud_data.get("type", ""))
                self.view_model.generic_sub.set_value(hud_data.get("sub", ""))
                self.view_model.generic_content.set_value(hud_data.get("content", ""))

            item = self.ui_pool[m_type]
            
            # Sync Checkbox state from the UI instance to the Engine
            # By passing the state when updating the visibility
            if "dynamic_hud_vbox" in item and item["dynamic_hud_vbox"]:
                item["dynamic_hud_vbox"].visible = hud_data.get("show_dynamic", True)
            if "static_hud_frame" in item and item["static_hud_frame"]:
                item["static_hud_frame"].visible = hud_data.get("show_static", True)
                
            # 處理全不勾選時隱藏整個背景框
            if not hud_data.get("show_dynamic", True) and not hud_data.get("show_static", True):
                if "bg_rect" in item and item["bg_rect"]:
                    item["bg_rect"].visible = False
            else:
                if "bg_rect" in item and item["bg_rect"]:
                    item["bg_rect"].visible = True

            transform_matrix = [
                1, 0, 0, 0,
                0, 1, 0, 0,
                0, 0, 1, 0,
                translation[0], translation[1], translation[2] + 80.0, 1  # 調整高度偏移
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
        
        # Clear UI Pool completely to ensure no detached widgets remain
        self.ui_pool.clear()
        
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

    def build_ui(self):
        """Builds the control panel inside the Zin Tools Box 'HUD' tab."""
        with ui.VStack(spacing=10):
            ui.Spacer(height=10)
            
            with ui.CollapsableFrame("Add / Edit HUD Metadata", collapsed=False, style={"font_size": 16, "color": 0xFFFFFFFF}):
                with ui.VStack(spacing=8):
                    ui.Spacer(height=5)
                    ui.Label("Add custom attributes to make selected models compatible with HUD and Info Panel:", 
                             style={"color": 0xFFAAAAAA, "font_size": 14})
                    
                    with ui.HStack(height=24, spacing=10):
                        ui.Label("Topic (Machine Type):", width=140, style={"color": 0xFFDDDDDD}, tooltip="Will be written to 'aif:core:assetClass' and displayed as 'Asset Class' in Factory Info.")
                        self.topic_field = ui.StringField(style={"color": 0xFFDDDDDD})
                        self.topic_field.model.set_value("Conveyor")
                        
                    with ui.HStack(height=24, spacing=10):
                        ui.Label("Subject (Sub Title):", width=140, style={"color": 0xFFDDDDDD}, tooltip="Will be written to 'aif:core:modelNumber' and displayed as 'Model No' in Factory Info.")
                        self.subject_field = ui.StringField(style={"color": 0xFFDDDDDD})
                        self.subject_field.model.set_value("Industrial Component")
                        
                    with ui.HStack(height=24, spacing=10):
                        ui.Label("Content:", width=140, style={"color": 0xFFDDDDDD}, tooltip="Will be written to 'aif:core:assetDescription'. Status is hardcoded to 'Active' for demo.")
                        self.content_field = ui.StringField(style={"color": 0xFFDDDDDD})
                        self.content_field.model.set_value("Status: Active")
                    
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
                        
            ui.Spacer(height=20)
            with ui.CollapsableFrame("Display Settings", collapsed=False, style={"font_size": 16, "color": 0xFFFFFFFF}):
                with ui.VStack(spacing=8, padding=6):
                    ui.Label("Select information to display on the HUD overlay:", style={"color": 0xFFAAAAAA, "font_size": 13})
                    
                    with ui.HStack(height=22, spacing=6):
                        self.cb_dynamic = ui.CheckBox(width=18, height=18)
                        self.cb_dynamic.model.set_value(True)
                        self.cb_dynamic.model.add_value_changed_fn(self._on_display_setting_changed)
                        ui.Label("⚡ Dynamic HUD Status", style={"color": 0xFFDDDDDD, "font_size": 13})

                    with ui.HStack(height=22, spacing=6):
                        self.cb_static = ui.CheckBox(width=18, height=18)
                        self.cb_static.model.set_value(True)
                        self.cb_static.model.add_value_changed_fn(self._on_display_setting_changed)
                        ui.Label("🏭 Factory Info (Metadata)", style={"color": 0xFFDDDDDD, "font_size": 13})

            ui.Spacer(height=20)
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

    def _on_display_setting_changed(self, model):
        # Notify the UsdSelectionAgent to re-evaluate and trigger on_selection_changed
        if self.is_enabled and self.engine and self.engine._selection_agent:
             self.engine._selection_agent._handle_selection()

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

        topic = self.topic_field.model.get_value_as_string()
        subject = self.subject_field.model.get_value_as_string()
        content = self.content_field.model.get_value_as_string()

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
                if not attr:
                    attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.String)
                attr.Set(attr_info["value"])
                
                # 遵循 AIF 規範：加入 [AIF-MANAGED] 標籤與鎖定屬性
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

    def _remove_attributes_from_selected(self):
        import omni.usd
        
        context = omni.usd.get_context()
        stage = context.get_stage()
        if not stage: return

        selection = context.get_selection().get_selected_prim_paths()
        if not selection: return

        attrs_to_remove = [
            "machine_type", "hud_sub_title", "hud_content",
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
