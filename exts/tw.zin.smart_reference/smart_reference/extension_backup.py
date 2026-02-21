import omni.ext
import omni.ui as ui
import omni.usd
import os
import carb.settings
import pandas as pd 
from pxr import Usd, UsdGeom, Sdf
from omni.kit.window.filepicker import FilePickerDialog

# ========================================================
# 1. 整合樣式表 (解決 Hover 失效問題)
# ========================================================
SMART_REFERENCE_STYLE = {
    # 基礎文字與輸入框
    "Label": {"font_size": 14},
    "StringField": {"background_color": 0xFF1A1A1A, "border_radius": 2, "color": 0xFFFFFFFF, "font_size": 14},
    
    # 一般功能按鈕 (name="action")
    "Button.action": {
        "background_color": 0xFF343432, 
        "border_radius": 3, 
        "color": 0xFFDDDDDD
    },
    "Button.action:hover": {"background_color": 0xFF444442},
    "Button.action:pressed": {"background_color": 0xFF222220},

    # 瀏覽按鈕 (name="browse")
    "Button.browse": {
        "background_color": 0xFF4A4A48, 
        "border_radius": 3, 
        "color": 0xFFFFFFFF
    },
    "Button.browse:hover": {"background_color": 0xFF5A5A58},
    "Button.browse:pressed": {"background_color": 0xFF3A3A38},

    # 執行按鈕 (name="execute")
    "Button.execute": {
        "background_color": 0xFF444442, 
        "border_radius": 4, 
        "color": 0xFF00BFFF, 
        "border_color": 0xFF00BFFF,
        "border_width": 0.5
    },
    "Button.execute:hover": {"background_color": 0xFF555552, "border_width": 1.0},
    "Button.execute:pressed": {"background_color": 0xFF333330},
}

TITLE_STYLE = {"color": 0xFF00BFFF, "font_size": 14, "font_weight": "bold"}
SUB_LABEL_STYLE = {"color": 0xFFAAAAAA, "font_size": 14}
INFO_BOX_STYLE = {"background_color": 0xFF101010, "border_radius": 4}

class SmartReferenceUI:
    def __init__(self):
        self._file_picker = None 
        self._settings = carb.settings.get_settings()
        self._setting_excel = "/persistent/exts/tw.zin.smart_reference/last_excel_path"
        self._setting_assets = "/persistent/exts/tw.zin.smart_reference/last_assets_path"
        self._found_paths = []

    def build_ui(self):
        scroll_frame = ui.ScrollingFrame()
        with scroll_frame:
            # 關鍵點：將樣式表套用在最外層的容器上
            with ui.VStack(spacing=10, padding=12, alignment=ui.Alignment.TOP, style=SMART_REFERENCE_STYLE):
                
                # --- [Section 1] Quick Prefix Reference ---
                ui.Label("Quick Prefix Reference", height=20, style=TITLE_STYLE)
                with ui.VStack(spacing=6):
                    with ui.HStack(height=28, spacing=8):
                        ui.Label("Prefix:", width=50, style=SUB_LABEL_STYLE)
                        self._field_prefix = ui.StringField()
                        self._field_prefix.model.set_value("/World/Assembly")
                        # 指定 name 以對應樣式
                        ui.Button("Scan", width=70, name="action", clicked_fn=self._on_scan)
                        ui.Spacer(width=85)
                    
                    with ui.HStack(height=28, spacing=8):
                        ui.Label("URL:", width=50, style=SUB_LABEL_STYLE)
                        self._field_url = ui.StringField()
                        ui.Button("Apply", width=70, name="action", clicked_fn=self._on_apply_reference)
                        ui.Button("Reset", width=70, name="action", clicked_fn=self._on_reset_quick)
                    
                    with ui.ZStack(height=45):
                        ui.Rectangle(style=INFO_BOX_STYLE)
                        with ui.HStack(padding=6, alignment=ui.Alignment.CENTER): 
                            self._lbl_results = ui.Label("Scan Results appear here...", word_wrap=True, style={"color": 0xFF00DD00})

                ui.Separator(height=8, style={"color": 0x22FFFFFF})

                # --- [Section 2] BOM Generator ---
                ui.Label("BOM Generator", height=22, style=TITLE_STYLE)
                with ui.VStack(spacing=8):
                    with ui.HStack(height=28, spacing=8):
                        ui.Label("Excel:", width=50, style=SUB_LABEL_STYLE)
                        self.excel_path_field = ui.StringField()
                        last_excel = self._settings.get(self._setting_excel) or "Select a file..."
                        self.excel_path_field.model.set_value(last_excel)
                        # 指定 name="browse"
                        ui.Button("Browse", width=70, name="browse", clicked_fn=self._on_browse_excel)
                        
                        with ui.HStack(width=85, spacing=4, alignment=ui.Alignment.CENTER):
                            self.remember_excel_model = ui.SimpleBoolModel(True)
                            ui.CheckBox(model=self.remember_excel_model)
                            ui.Label("Recent", style=SUB_LABEL_STYLE, tooltip="Remember Path")

                    with ui.HStack(height=28, spacing=8):
                        ui.Label("Assets:", width=50, style=SUB_LABEL_STYLE)
                        self.asset_dir_field = ui.StringField()
                        last_assets = self._settings.get(self._setting_assets) or "omniverse://localhost/Assets"
                        self.asset_dir_field.model.set_value(last_assets)
                        # 指定 name="browse"
                        ui.Button("Browse", width=70, name="browse", clicked_fn=self._on_browse_folder)
                        
                        with ui.HStack(width=85, spacing=4, alignment=ui.Alignment.CENTER):
                            self.remember_assets_model = ui.SimpleBoolModel(True)
                            ui.CheckBox(model=self.remember_assets_model)
                            ui.Label("Recent", style=SUB_LABEL_STYLE, tooltip="Remember Path")

                    # 指定 name="execute"
                    ui.Button("Execute BOM Import", height=36, name="execute", clicked_fn=self._on_import_execute)

                # --- Status Log ---
                with ui.ZStack(height=40):
                    ui.Rectangle(style=INFO_BOX_STYLE)
                    with ui.HStack(spacing=8, padding=6, alignment=ui.Alignment.CENTER):
                        ui.Label("STATUS:", width=65, style={"font_size": 12, "color": 0xFF888888, "font_weight": "bold"})
                        # 動態顏色邏輯
                        self.log_output = ui.Label("Ready", style={"color": 0xFF00BFFF})
                
                ui.Spacer() 
        return scroll_frame

    # 邏輯處理 (BOM Import)
    def _on_import_execute(self):
        excel_path = self.excel_path_field.model.get_value_as_string().strip()
        asset_folder = self.asset_dir_field.model.get_value_as_string().strip()
        try:
            df = pd.read_excel(excel_path)
            self._process_bom(df, asset_folder)
            self.log_output.text = f"Success: {len(df)} items processed."
            self.log_output.style = {"color": 0xFF00FF00} # 成功變綠
        except Exception as e:
            self.log_output.text = f"Error: {str(e)}"
            self.log_output.style = {"color": 0xFF0000FF} # 失敗變紅

    def _process_bom(self, df, asset_folder):
        stage = omni.usd.get_context().get_stage()
        clean_folder = asset_folder.rstrip("/\\")
        for _, row in df.iterrows():
            p_name = str(row['Part_Number']).strip()
            sub_path = str(row['Asset_Sub_Path']).strip().lstrip("/\\")
            parent_path = str(row['Parent_Path']).strip()
            f_id = str(int(row['Instance_ID'])).zfill(2)
            final_path = f"{clean_folder}/{sub_path}"

            if not stage.GetPrimAtPath(parent_path):
                omni.kit.commands.execute('CreatePrim', prim_type='Xform', prim_path=parent_path)

            prim_path = f"{parent_path}/{p_name}_{f_id}"
            prim = stage.DefinePrim(prim_path, "Xform")
            prim.GetReferences().ClearReferences()
            prim.GetReferences().AddReference(final_path)
            
            xform = UsdGeom.Xformable(prim)
            xform.ClearXformOpOrder()
            xform.AddTranslateOp().Set((row['Pos_X'], row['Pos_Y'], row['Pos_Z']))
            xform.AddRotateXYZOp().Set((row['Rot_X'], row['Rot_Y'], row['Rot_Z']))
            
            sx, sy, sz = row.get('Scale_X', 1.0), row.get('Scale_Y', 1.0), row.get('Scale_Z', 1.0)
            sx = 1.0 if pd.isna(sx) else sx
            sy = 1.0 if pd.isna(sy) else sy
            sz = 1.0 if pd.isna(sz) else sz
            xform.AddScaleOp().Set((sx, sy, sz))

    def _on_scan(self):
        prefix = self._field_prefix.model.get_value_as_string().strip()
        if not prefix: return
        stage = omni.usd.get_context().get_stage()
        self._found_paths = [str(p.GetPath()) for p in stage.Traverse() if str(p.GetPath()).startswith(prefix)]
        self._lbl_results.text = f"Found {len(self._found_paths)} items."

    def _on_apply_reference(self):
        asset_url = self._field_url.model.get_value_as_string().strip()
        stage = omni.usd.get_context().get_stage()
        for path in self._found_paths:
            prim = stage.GetPrimAtPath(path)
            if prim.IsValid():
                prim.GetReferences().ClearReferences()
                prim.GetReferences().AddReference(asset_url)

    def _on_reset_quick(self):
        self._lbl_results.text = ""
        self._found_paths = []

    def _on_browse_excel(self):
        def on_selected(filename, path):
            full_path = f"{path}/{filename}".replace("\\", "/")
            self.excel_path_field.model.set_value(full_path)
            if self.remember_excel_model.as_bool:
                self._settings.set(self._setting_excel, full_path)
            self._file_picker.hide()
        self._file_picker = FilePickerDialog("Select Excel", click_apply_handler=on_selected)
        self._file_picker.show()

    def _on_browse_folder(self):
        def on_selected(filename, path):
            full_path = path.replace("\\", "/")
            self.asset_dir_field.model.set_value(full_path)
            if self.remember_assets_model.as_bool:
                self._settings.set(self._setting_assets, full_path)
            self._file_picker.hide()
        self._file_picker = FilePickerDialog("Select Assets", click_apply_handler=on_selected)
        self._file_picker.show()

class SmartReferenceExtension(omni.ext.IExt):
    def on_startup(self, ext_id): pass
    def on_shutdown(self): pass