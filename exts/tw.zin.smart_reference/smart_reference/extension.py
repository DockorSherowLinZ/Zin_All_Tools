import omni.ext
import omni.ui as ui
import omni.usd
import os
import carb.settings
import omni.kit.pipapi  # 新增：用於自動安裝套件
# import pandas as pd   # <--- 移除：不能放在這裡，否則會導致啟動崩潰
from pxr import Usd, UsdGeom, Sdf
from omni.kit.window.filepicker import FilePickerDialog

import sys
import os

import zin_core.ui_utils as zin_ui_utils
from zin_core.menu import ZinMenuMixin

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
        self._cb_instanceable = None
        self._file_picker = None 
        self._settings = carb.settings.get_settings()
        self._setting_excel = "/persistent/exts/tw.zin.smart_reference/last_excel_path"
        self._setting_assets = "/persistent/exts/tw.zin.smart_reference/last_assets_path"
        self._found_paths = []

    def build_ui(self):
        scroll_frame = ui.ScrollingFrame()
        with scroll_frame:
            # 關鍵點：將樣式表套用在最外層的容器上
            with ui.VStack(style=zin_ui_utils.ZIN_NATIVE_STYLE, spacing=zin_ui_utils.ZIN_V_SPACING, padding=6):
                
                # --- [Section 1] Quick Prefix Reference ---
                with ui.CollapsableFrame("Quick Prefix Reference", collapsed=False, height=0):
                    with ui.VStack(spacing=zin_ui_utils.ZIN_V_SPACING, padding=6):
                        def build_prefix():
                            with ui.HStack(spacing=zin_ui_utils.ZIN_ROW_SPACING):
                                self._field_prefix = ui.StringField()
                                self._field_prefix.model.set_value("/World/Assembly")
                                ui.Button("Scan", width=70, style=zin_ui_utils.STYLE_POSITIVE, clicked_fn=self._on_scan)
                        zin_ui_utils.build_property_row("Prefix:", build_prefix)
                        
                        def build_url():
                            with ui.HStack(spacing=zin_ui_utils.ZIN_ROW_SPACING):
                                self._field_url = ui.StringField()
                                with ui.HStack(spacing=4):
                                    self._cb_instanceable = ui.CheckBox(width=20)
                                    self._cb_instanceable.model.set_value(False)
                                    ui.Label("Instanceable", name="Description")
                                ui.Button("Apply", width=70, style=zin_ui_utils.STYLE_POSITIVE, clicked_fn=self._on_apply_reference)
                                ui.Button("Reset", width=70, style=zin_ui_utils.STYLE_NEGATIVE, clicked_fn=self._on_reset_quick)
                        zin_ui_utils.build_property_row("URL:", build_url)
                        
                        ui.Spacer(height=5)
                        self._lbl_results = ui.Label("Scan Results appear here...", word_wrap=True, style={"color": 0xFF00DD00})

                ui.Spacer(height=5)

                # --- [Section 2] BOM Generator ---
                with ui.CollapsableFrame("BOM Generator", collapsed=False, height=0):
                    with ui.VStack(spacing=zin_ui_utils.ZIN_V_SPACING, padding=6):
                        def build_excel():
                            with ui.HStack(spacing=zin_ui_utils.ZIN_ROW_SPACING):
                                self.excel_path_field = ui.StringField()
                                last_excel = self._settings.get(self._setting_excel) or "Select a file..."
                                self.excel_path_field.model.set_value(last_excel)
                                ui.Button("Browse", width=70, clicked_fn=self._on_browse_excel)
                                
                                with ui.HStack(spacing=4):
                                    self.remember_excel_model = ui.SimpleBoolModel(True)
                                    ui.CheckBox(model=self.remember_excel_model, width=20)
                                    ui.Label("Recent", name="Description", tooltip="Remember Path")
                        zin_ui_utils.build_property_row("Excel:", build_excel)

                        def build_assets():
                            with ui.HStack(spacing=zin_ui_utils.ZIN_ROW_SPACING):
                                self.asset_dir_field = ui.StringField()
                                last_assets = self._settings.get(self._setting_assets) or "omniverse://localhost/Assets"
                                self.asset_dir_field.model.set_value(last_assets)
                                ui.Button("Browse", width=70, clicked_fn=self._on_browse_folder)
                                
                                with ui.HStack(spacing=4):
                                    self.remember_assets_model = ui.SimpleBoolModel(True)
                                    ui.CheckBox(model=self.remember_assets_model, width=20)
                                    ui.Label("Recent", name="Description", tooltip="Remember Path")
                        zin_ui_utils.build_property_row("Assets:", build_assets)

                        zin_ui_utils.build_button_row("", "Execute BOM Import", self._on_import_execute, zin_ui_utils.STYLE_POSITIVE)

                        # --- Status Log ---
                        ui.Spacer(height=5)
                        with ui.HStack(spacing=zin_ui_utils.ZIN_ROW_SPACING):
                            ui.Label("STATUS:", width=ui.Percent(zin_ui_utils.ZIN_LABEL_WIDTH_PCT), style={"font_size": 12, "color": 0xFF888888, "font_weight": "bold"})
                            self.log_output = ui.Label("Ready", style={"color": 0xFF00BFFF})
                
                ui.Spacer()
                
                ui.Spacer() 
        return scroll_frame

    # 邏輯處理 (BOM Import)
    def _on_import_execute(self):
        excel_path = self.excel_path_field.model.get_value_as_string().strip()
        asset_folder = self.asset_dir_field.model.get_value_as_string().strip()
        
        self.log_output.text = "Loading Pandas & Processing..."
        
        # [關鍵修正] 在這裡才匯入 Pandas，避免啟動時崩潰
        try:
            import pandas as pd
            import openpyxl  # Excel 讀取需要這個
            
            df = pd.read_excel(excel_path)
            self._process_bom(df, asset_folder, pd) # 將 pd 傳入
            self.log_output.text = f"Success: {len(df)} items processed."
            self.log_output.style = {"color": 0xFF00FF00} # 成功變綠
            
        except ImportError:
            self.log_output.text = "Error: Pandas/OpenPyXL installing... try again in 5s."
            self.log_output.style = {"color": 0xFFFFAA00}
        except Exception as e:
            self.log_output.text = f"Error: {str(e)}"
            self.log_output.style = {"color": 0xFF0000FF} # 失敗變紅

    def _process_bom(self, df, asset_folder, pd): # 接收 pd 參數
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
        
        self._found_paths = []
        for p in stage.Traverse():
            path_str = str(p.GetPath())
            if path_str.startswith(prefix):
                # 過濾掉子物件：如果父節點已經符合 Prefix，就不加入子節點
                parent_path_str = str(p.GetParent().GetPath())
                if not parent_path_str.startswith(prefix):
                    self._found_paths.append(path_str)
                    
        self._lbl_results.text = f"Found {len(self._found_paths)} items."

    def _on_apply_reference(self):
        asset_url = self._field_url.model.get_value_as_string().strip()
        is_instanceable = self._cb_instanceable.model.get_value_as_bool() if self._cb_instanceable else False
        stage = omni.usd.get_context().get_stage()
        
        applied_count = 0
        for path in self._found_paths:
            prim = stage.GetPrimAtPath(path)
            if prim.IsValid():
                if prim.IsInstanceProxy():
                    continue # 略過 Instance Proxy，因為無法對其寫入
                # 解決 "authoring to an instance proxy" 錯誤：
                # 在修改 Reference 前，先暫時關閉 Instanceable，修改完再設回來
                prim.SetInstanceable(False)
                
                prim.GetReferences().ClearReferences()
                prim.GetReferences().AddReference(asset_url)
                
                # 套用新的 Instanceable 設定
                prim.SetInstanceable(is_instanceable)
                applied_count += 1
                
        success_msg = f"Successfully applied to {applied_count} items."
        if is_instanceable:
            success_msg += " (Instanceable: ON)"
        self._lbl_results.text = success_msg

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

class SmartReferenceExtension(ZinMenuMixin, omni.ext.IExt):
    WINDOW_NAME = "Smart Reference"
    MENU_PATH = f"Zin_All_Tools/{WINDOW_NAME}"

    def __init__(self):
        super().__init__()
        self._window = None
        self._menu_added = False
        self._ui = None

    def on_startup(self, ext_id):
        # [關鍵修正] 在 Extension 啟動時自動檢查並安裝 Pandas 與 OpenPyXL
        try:
            carb.log_info("[SmartReference] Checking dependencies...")
            omni.kit.pipapi.install("pandas")
            omni.kit.pipapi.install("openpyxl")
        except Exception as e:
            carb.log_warn(f"[SmartReference] Dependency install failed: {e}")
            
        self._build_menu()

    def on_shutdown(self):
        self._remove_menu()
        if self._window:
            self._window.destroy()
            self._window = None
        self._ui = None

    def _toggle_window(self, menu, value):
        if value:
            if not self._window:
                from omni.ui import DockPreference
                self._window = ui.Window(self.WINDOW_NAME, width=320, height=540, dockPreference=DockPreference.RIGHT)
                self._window.set_visibility_changed_fn(self._on_visibility_changed)
                if not self._ui:
                    self._ui = SmartReferenceUI()
                with self._window.frame:
                    self._ui.build_ui()
            self._window.visible = True
        else:
            if self._window:
                self._window.visible = False