from typing import Optional, Dict, Any, List
import omni.ext
import omni.ui as ui
import omni.usd

class SmartInformationUI:
    def __init__(self):
        self._usd_context = omni.usd.get_context()
        self._stage_event_sub = None
        self._target_prim = None
        
        # UI components
        self._target_label: Optional[ui.Label] = None
        self._status_label: Optional[ui.Label] = None
        self._api_vbox: Optional[ui.VStack] = None
        self._specs_vbox: Optional[ui.VStack] = None
        self._process_vbox: Optional[ui.VStack] = None

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
        with ui.VStack(spacing=5, padding=12, alignment=ui.Alignment.TOP):
            with ui.VStack(spacing=2, height=0):
                with ui.HStack(height=18):
                    ui.Label("Target Prim :", width=ui.Pixel(80), style={"color": 0x888888FF})
                    self._target_label = ui.Label("--", style={"color": 0xFFDDDDDD})
                with ui.HStack(height=18):
                    ui.Label("Status     :", width=ui.Pixel(80), style={"color": 0x888888FF})
                    self._status_label = ui.Label("--", style={"color": 0xFFDDDDDD})
            ui.Spacer(height=8)
            
            with ui.CollapsableFrame("Software API Commands", collapsed=False, height=0, style={"color": 0xFFFFA500}):
                with ui.Frame(style={"background_color": 0x33000000, "border_radius": 4}):
                    self._api_vbox = ui.VStack(spacing=4, padding=6, height=0)

            ui.Spacer(height=4)

            with ui.CollapsableFrame("Machine Specifications", collapsed=False, height=0, style={"color": 0xFFFFA500}):
                with ui.Frame(style={"background_color": 0x33000000, "border_radius": 4}):
                    self._specs_vbox = ui.VStack(spacing=4, padding=6, height=0)

            ui.Spacer(height=4)

            with ui.CollapsableFrame("Standard Working Process", collapsed=False, height=0, style={"color": 0xFFFFA500}):
                with ui.Frame(style={"background_color": 0x33000000, "border_radius": 4}):
                    self._process_vbox = ui.VStack(spacing=4, padding=6, height=0)
            
            ui.Spacer(height=5)
            
        self.refresh_data()

    def clear_ui(self):
        if self._target_label:
            self._target_label.text = "--"
        if self._status_label:
            self._status_label.text = "--"
            self._status_label.style = {"color": 0xFFDDDDDD}
            
        if self._api_vbox:
            self._api_vbox.clear()
        if self._specs_vbox:
            self._specs_vbox.clear()
        if self._process_vbox:
            self._process_vbox.clear()

    def refresh_data(self):
        stage = self._usd_context.get_stage()
        if not stage or not self._target_label:
            return
            
        paths = self._usd_context.get_selection().get_selected_prim_paths()
        target_prim = None
        
        if paths:
            for p in paths:
                prim = stage.GetPrimAtPath(p)
                if prim and prim.IsValid() and prim.GetCustomDataByKey("Inventec_Tester"):
                    target_prim = prim
                    break
        
        if not target_prim:
            self.clear_ui()
            return
            
        self._target_prim = target_prim
        self._target_label.text = target_prim.GetPath().name
        self._status_label.text = "Data Loaded"
        self._status_label.style = {"color": 0xFF00AA00}
        
        inventec_data = target_prim.GetCustomDataByKey("Inventec_Tester")
        if isinstance(inventec_data, dict):
            core_data = inventec_data.get("Inventec_Tester", {})
        else:
            core_data = {}
        
        self._build_api_ui(core_data.get("Software_API_Commands", {}))
        self._build_specs_ui(core_data.get("Specifications", {}))
        self._build_process_ui(core_data.get("Working_Process", []))

    def _build_api_ui(self, data: Dict[Any, Any]):
        if not self._api_vbox:
            return
        self._api_vbox.clear()
        with self._api_vbox:
            if not data:
                ui.Label("No API Commands available.", style={"color": 0xFF888888, "font_style": "italic"})
                return
            for k, v in data.items():
                with ui.HStack(height=18, spacing=4):
                    ui.Label(str(k) + ":", width=ui.Pixel(120), style={"color": 0xFF6AD7D9, "font_family": "Microsoft JhengHei"})
                    ui.Label(str(v).strip(), style={"color": 0xFFDDDDDD, "font_family": "Microsoft JhengHei"})

    def _build_specs_ui(self, data: Dict[Any, Any]):
        if not self._specs_vbox:
            return
        self._specs_vbox.clear()
        with self._specs_vbox:
            if not data:
                ui.Label("No Specifications available.", style={"color": 0xFF888888, "font_style": "italic"})
                return
                
            for k, v in data.items():
                if k == "Probes" and isinstance(v, dict):
                    ui.Spacer(height=4)
                    ui.Label("Probes List:", style={"color": 0xFFA07D4F})
                    for pk, pv in v.items():
                        with ui.HStack(height=18, spacing=4):
                            ui.Spacer(width=10)
                            ui.Label("- " + str(pk) + ":", width=ui.Pixel(110), style={"color": 0xFF76A371, "font_family": "Microsoft JhengHei"})
                            ui.Label(str(pv), style={"color": 0xFFDDDDDD, "font_family": "Microsoft JhengHei"})
                else:
                    with ui.HStack(height=18, spacing=4):
                        ui.Label(str(k) + ":", width=ui.Pixel(120), style={"color": 0xFF6060AA, "font_family": "Microsoft JhengHei"})
                        ui.Label(str(v), style={"color": 0xFFDDDDDD, "font_family": "Microsoft JhengHei"})

    def _build_process_ui(self, process_list: List[Any]):
        if not self._process_vbox:
            return
        self._process_vbox.clear()
        with self._process_vbox:
            if not process_list:
                ui.Label("No Working Process available.", style={"color": 0xFF888888, "font_style": "italic"})
                return
            for step in process_list:
                with ui.HStack(height=18):
                    ui.Label(str(step), style={"color": 0xFFDDDDDD, "font_family": "Microsoft JhengHei"}, word_wrap=True)

class SmartInformationExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        pass

    def on_shutdown(self):
        pass
