import os
import json
import datetime
from typing import Optional, Dict, Any, List
import omni.ext
import omni.ui as ui
import omni.usd
from urllib.parse import unquote

import sys
import os

import zin_core.ui_utils as zin_ui_utils

class SmartInformationUI:
    def __init__(self):
        self._usd_context = omni.usd.get_context()
        self._stage_event_sub = None
        self._target_prim = None
        
        # UI components
        self._target_label: Optional[ui.Label] = None
        self._status_label: Optional[ui.Label] = None
        self._dynamic_vbox: Optional[ui.VStack] = None
        
        # Edit fields
        self._edit_topic: Optional[ui.StringField] = None
        self._edit_subject: Optional[ui.StringField] = None
        self._edit_content: Optional[ui.StringField] = None

    def startup(self):
        if not self._stage_event_sub:
            stream = self._usd_context.get_stage_event_stream()
            self._stage_event_sub = stream.create_subscription_to_pop(self._on_stage_event, name="smart_info_ui_stage")

    def shutdown(self):
        self._stage_event_sub = None
        self._target_prim = None

    def _on_stage_event(self, event):
        if event.type in [int(omni.usd.StageEventType.OPENED), int(omni.usd.StageEventType.SELECTION_CHANGED)]:
            self.refresh_data()
        elif event.type == int(omni.usd.StageEventType.CLOSING):
            self.clear_ui()

    def build_ui(self):
        with ui.VStack(style=zin_ui_utils.ZIN_NATIVE_STYLE, spacing=zin_ui_utils.ZIN_V_SPACING, padding=6, alignment=ui.Alignment.TOP):
            with ui.VStack(spacing=2, height=0):
                def build_target():
                    self._target_label = ui.Label("--", name="Description")
                zin_ui_utils.build_property_row("Target Prim:", build_target)
                
                def build_status():
                    self._status_label = ui.Label("--", name="Description")
                zin_ui_utils.build_property_row("Status:", build_status)
            
            ui.Spacer(height=5)
            
            # Add / Edit Section
            with ui.CollapsableFrame("Add / Edit Metadata", collapsed=False, height=0):
                with ui.VStack(spacing=zin_ui_utils.ZIN_V_SPACING, padding=6):
                    def build_topic():
                        self._edit_topic = ui.StringField()
                    zin_ui_utils.build_property_row("Topic:", build_topic)
                    
                    def build_subject():
                        self._edit_subject = ui.StringField()
                    zin_ui_utils.build_property_row("Subject:", build_subject)
                    
                    def build_content():
                        self._edit_content = ui.StringField()
                    zin_ui_utils.build_property_row("Content:", build_content)
                    
                    with ui.HStack(height=24, spacing=zin_ui_utils.ZIN_ROW_SPACING):
                        ui.Button("Add / Update", style=zin_ui_utils.STYLE_POSITIVE, clicked_fn=self._on_add_metadata_clicked)
                        ui.Button("Remove", style=zin_ui_utils.STYLE_NEGATIVE, clicked_fn=self._on_remove_metadata_clicked)

            ui.Spacer(height=5)
            # Export Section
            zin_ui_utils.build_button_row("", "Export to JSON", self._on_export_json_clicked, zin_ui_utils.STYLE_POSITIVE)
            
            ui.Spacer(height=5)
            
            # Dynamic Content Area
            with ui.ScrollingFrame(height=ui.Fraction(1), style={"background_color": 0x00000000}):
                self._dynamic_vbox = ui.VStack(spacing=5)
            
        self.refresh_data()

    def clear_ui(self):
        if getattr(self, '_target_label', None):
            self._target_label.text = "--"
        if getattr(self, '_status_label', None):
            self._status_label.text = "--"
            self._status_label.style = {"color": 0xFFDDDDDD}
        if getattr(self, '_dynamic_vbox', None):
            self._dynamic_vbox.clear()

    def refresh_data(self):
        stage = self._usd_context.get_stage()
        if not stage or not self._target_label:
            return
            
        paths = self._usd_context.get_selection().get_selected_prim_paths()
        target_prim = None
        
        if paths:
            for p in paths:
                prim = stage.GetPrimAtPath(p)
                if prim and prim.IsValid() and prim.HasCustomDataKey("Inventec_Tester"):
                    target_prim = prim
                    break
                    
        # If not found by key, just use the first selected prim so user can ADD data to it
        if not target_prim and paths:
            prim = stage.GetPrimAtPath(paths[0])
            if prim and prim.IsValid():
                target_prim = prim
        
        if not target_prim:
            self.clear_ui()
            return
            
        self._target_prim = target_prim
        self._target_label.text = target_prim.GetPath().name
        
        inventec_data = target_prim.GetCustomDataByKey("Inventec_Tester")
        if isinstance(inventec_data, dict):
            core_data = inventec_data.get("Inventec_Tester", inventec_data)
            self._status_label.text = "Data Loaded"
            self._status_label.style = {"color": 0xFF00AA00}
        else:
            core_data = {}
            self._status_label.text = "No Metadata (Ready to Add)"
            self._status_label.style = {"color": 0xFF888888}
        
        if self._dynamic_vbox:
            self._dynamic_vbox.clear()
            with self._dynamic_vbox:
                if not core_data:
                    ui.Label("No Data Available.", style={"color": 0xFF888888, "font_style": "italic"})
                else:
                    for topic, content in core_data.items():
                        if topic == "Inventec_Tester": continue # Skip nested root if malformed
                        with ui.CollapsableFrame(str(topic), collapsed=False, style={"color": 0xFFFFA500}):
                            with ui.Frame(style={"background_color": 0x33000000, "border_radius": 4}):
                                vbox = ui.VStack(spacing=4, padding=6)
                                with vbox:
                                    self._render_dict(content, indent=0)

    def _render_dict(self, data, indent=0):
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict) or isinstance(v, list):
                    with ui.HStack(height=18):
                        ui.Spacer(width=indent)
                        ui.Label(str(k) + ":", style={"color": 0xFFA07D4F})
                    self._render_dict(v, indent + 10)
                else:
                    with ui.HStack(height=18, spacing=4):
                        ui.Spacer(width=indent)
                        ui.Label(str(k) + ":", width=ui.Pixel(120), style={"color": 0xFF6AD7D9, "font_family": "Microsoft JhengHei"})
                        ui.Label(str(v).strip(), style={"color": 0xFFDDDDDD, "font_family": "Microsoft JhengHei"})
        elif isinstance(data, list):
            for item in data:
                with ui.HStack(height=18):
                    ui.Spacer(width=indent)
                    ui.Label("- " + str(item), style={"color": 0xFFDDDDDD, "font_family": "Microsoft JhengHei"}, word_wrap=True)
        else:
            with ui.HStack(height=18):
                ui.Spacer(width=indent)
                ui.Label(str(data), style={"color": 0xFFDDDDDD, "font_family": "Microsoft JhengHei"}, word_wrap=True)

    def _on_add_metadata_clicked(self):
        if not self._target_prim or not self._target_prim.IsValid():
            return
            
        topic = self._edit_topic.model.get_value_as_string().strip()
        subject = self._edit_subject.model.get_value_as_string().strip()
        content = self._edit_content.model.get_value_as_string().strip()
        
        if not topic or not content:
            print("[SmartInformation] Topic and Content are required.")
            return
            
        inventec_data = self._target_prim.GetCustomDataByKey("Inventec_Tester") or {}
        if not isinstance(inventec_data, dict):
            inventec_data = {}
            
        # Standardize nested structure if needed without creating circular reference
        if "Inventec_Tester" in inventec_data:
            core_data = inventec_data["Inventec_Tester"]
        else:
            # Prevent circular reference by creating a separate nested dict
            core_data = {}
            for k in list(inventec_data.keys()):
                core_data[k] = inventec_data.pop(k)
            inventec_data["Inventec_Tester"] = core_data
            
        if topic not in core_data:
            core_data[topic] = {} if subject else []
            
        if subject:
            if not isinstance(core_data[topic], dict):
                # Convert list to dict if needed (fallback)
                core_data[topic] = {"_items": core_data[topic]}
            core_data[topic][subject] = content
        else:
            if not isinstance(core_data[topic], list):
                # Convert dict to list if needed
                core_data[topic] = [core_data[topic]]
            core_data[topic].append(content)
            
        self._target_prim.SetCustomDataByKey("Inventec_Tester", inventec_data)
        
        # Clear fields
        self._edit_subject.model.set_value("")
        self._edit_content.model.set_value("")
        
        self.refresh_data()

    def _on_remove_metadata_clicked(self):
        if not self._target_prim or not self._target_prim.IsValid():
            return
            
        topic = self._edit_topic.model.get_value_as_string().strip()
        subject = self._edit_subject.model.get_value_as_string().strip()
        
        if not topic:
            return
            
        inventec_data = self._target_prim.GetCustomDataByKey("Inventec_Tester") or {}
        if "Inventec_Tester" in inventec_data:
            core_data = inventec_data["Inventec_Tester"]
        else:
            core_data = inventec_data
            
        if topic in core_data:
            if subject and isinstance(core_data[topic], dict) and subject in core_data[topic]:
                del core_data[topic][subject]
            elif not subject:
                del core_data[topic]
                
        self._target_prim.SetCustomDataByKey("Inventec_Tester", inventec_data)
        self.refresh_data()

    def _on_export_json_clicked(self):
        if not self._target_prim or not self._target_prim.IsValid():
            print("[SmartInformation] No target prim selected for export.")
            return
            
        inventec_data = self._target_prim.GetCustomDataByKey("Inventec_Tester")
        if not inventec_data:
            print("[SmartInformation] No metadata to export.")
            return
            
        try:
            # Default to the stage's directory
            stage_url = self._usd_context.get_stage_url()
            if stage_url:
                stage_url = unquote(stage_url)
                if stage_url.startswith("file:"):
                    stage_url = stage_url[5:]
                # strip leading slashes on windows if needed, e.g. /c:/ -> c:/
                if os.name == 'nt' and stage_url.startswith('/') and len(stage_url) > 2 and stage_url[2] == ':':
                    stage_url = stage_url[1:]
                export_dir = os.path.dirname(stage_url)
            else:
                export_dir = os.path.expanduser("~")
                
            prim_name = self._target_prim.GetName()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = os.path.join(export_dir, f"{prim_name}_metadata_{timestamp}.json")
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(inventec_data, f, ensure_ascii=False, indent=4)
                
            print(f"[SmartInformation] Successfully exported metadata to: {export_path}")
            
            # Show a brief UI confirmation (optional, could just rely on console)
            if self._status_label:
                self._status_label.text = f"Exported to {os.path.basename(export_path)}"
                self._status_label.style = {"color": 0xFF00AAFF}
                
        except Exception as e:
            print(f"[SmartInformation] Export failed: {e}")

class SmartInformationExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self._ui = SmartInformationUI()
        self._ui.startup()
        self._window = None
        self._build_menu()

    def on_shutdown(self):
        if hasattr(self, '_ui') and self._ui:
            self._ui.shutdown()
            self._ui = None
        if getattr(self, '_window', None) is not None:
            self._window.destroy()
            self._window = None
        self._remove_menu()

    def _build_menu(self):
        try:
            import omni.kit.menu.utils
            self._menu = omni.kit.menu.utils.add_menu_items([
                omni.kit.menu.utils.MenuItemDescription(
                    name="Smart Information",
                    onclick_fn=lambda *args: self._toggle_window(None, True)
                )
            ], "Zin_All_Tools")
        except Exception: pass

    def _remove_menu(self):
        try:
            import omni.kit.menu.utils
            if hasattr(self, '_menu') and self._menu:
                omni.kit.menu.utils.remove_menu_items(self._menu, "Zin_All_Tools")
                self._menu = None
        except Exception: pass

    def _toggle_window(self, menu, value):
        import omni.ui as ui
        if value:
            if getattr(self, '_window', None) is None:
                self._window = ui.Window("Smart Information", width=400, height=500)
                with self._window.frame:
                    self._ui.build_ui()
            else:
                self._window.visible = True
        else:
            if getattr(self, '_window', None) is not None:
                self._window.visible = False
