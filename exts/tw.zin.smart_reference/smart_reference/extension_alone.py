import omni.ext
import omni.ui as ui
import omni.kit.commands
from pxr import Usd, Sdf

class SmartReferenceExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        print("[SmartReference] SmartReference startup")

        self._window = ui.Window("Smart Reference (Auto)", width=400, height=350)
        self.stage = omni.usd.get_context().get_stage()

        # --- 樣式定義 (修正：改用標準 Hex 色碼) ---
        # 格式：0xAABBGGRR (Alpha, Blue, Green, Red)
        # 0xFF282828 = 深灰色背景
        # 0xFFDDDDDD = 淺灰色文字
        
        FIELD_INPUT_STYLE = {
            "background_color": 0xFF282828, 
            "color": 0xFFDDDDDD,
            "font_size": 14,
            "padding": 6,
            "border_radius": 4.0,
        }
        FIELD_LABEL_STYLE = {
            "color": 0xFFB4B4B4, # 灰色標籤
            "font_size": 14,
            "margin_width": 10,
        }
        FIELD_TITLE_STYLE = {
            "color": 0xFFFFFFFF, # 純白標題
            "font_size": 16,
            "margin": 4,
        }
        FIELD_CONTEXT_STYLE = {
            "color": 0xFF76B900, # NVIDIA Green
            "font_size": 12,
        }
        LINE_STYLE = {"color": 0xFF505050, "margin": 8}
        
        # 結果文字顏色：黃色與紅色
        COLOR_YELLOW = 0xFF32C8FF 
        COLOR_RED = 0xFF5555FF
        COLOR_GREEN = 0xFF76B900

        # --- UI 建構 ---
        with self._window.frame:
            with ui.VStack(spacing=10, margin=10):
                
                ui.Label("Auto Reference Tool", style={"font_size": 18, "color": 0xFFFFFFFF})
                ui.Line(style=LINE_STYLE)

                # 1. 輸入區域
                ui.Label("Target Prefix (Parent/Name):", style=FIELD_TITLE_STYLE)
                self.prim_path_template_field = ui.StringField(style=FIELD_INPUT_STYLE)
                
                ui.Label("Asset URL (.usd):", style=FIELD_TITLE_STYLE)
                self.asset_url_field = ui.StringField(style=FIELD_INPUT_STYLE)

                ui.Line(style=LINE_STYLE)

                # 2. 結果顯示
                self.result_label = ui.Label("", style={"color": COLOR_YELLOW, "font_size": 13})

                def on_confirm():
                    target_input = self.prim_path_template_field.model.get_value_as_string()
                    asset_path = self.asset_url_field.model.get_value_as_string()

                    if not target_input or not asset_path:
                        self.result_label.text = "Error: Input cannot be empty."
                        self.result_label.style = {"color": COLOR_RED}
                        return

                    # 使用 Sdf.Path 自動解析父層級與前綴
                    target_sdf_path = Sdf.Path(target_input)
                    parent_path = target_sdf_path.GetParentPath()
                    prefix_name = target_sdf_path.name

                    parent_prim = self.stage.GetPrimAtPath(parent_path)

                    if not parent_prim.IsValid():
                        self.result_label.text = f"Error: Parent path '{parent_path}' not found."
                        self.result_label.style = {"color": COLOR_RED}
                        return

                    count = 0
                    
                    # 開始遍歷
                    try:
                        children = parent_prim.GetChildren()
                        if not children:
                            self.result_label.text = f"No children found under {parent_path}"
                            self.result_label.style = {"color": COLOR_YELLOW}
                            return

                        for child_prim in children:
                            child_name = child_prim.GetName()
                            
                            # 比對前綴 (例如 Box 符合 Box01, Box_Left)
                            if child_name.startswith(prefix_name):
                                # 清除舊的並添加新的 Reference
                                references = child_prim.GetReferences()
                                references.ClearReferences() 
                                references.AddReference(asset_path)
                                
                                print(f"[SmartReference] Processed: {child_prim.GetPath()}")
                                count += 1
                        
                        if count > 0:
                            self.result_label.text = f"Success! Updated {count} objects."
                            self.result_label.style = {"color": COLOR_GREEN}
                        else:
                            self.result_label.text = f"Found 0 objects starting with '{prefix_name}'."
                            self.result_label.style = {"color": COLOR_YELLOW}
                        
                    except Exception as e:
                        print(f"[SmartReference] Error: {e}")
                        self.result_label.text = f"System Error: {str(e)}"
                        self.result_label.style = {"color": COLOR_RED}

                with ui.HStack():
                    # 設定預設值
                    self.prim_path_template_field.model.set_value("/World/Example")
                    self.asset_url_field.model.set_value("omniverse://localhost/Projects/Asset.usd")

                # 按鈕
                ui.Button("Auto Find & Reference", 
                          clicked_fn=on_confirm, 
                          alignment=ui.Alignment.CENTER, 
                          height=40)

                ui.Label(
                    "Logic: Finds the parent folder from your input, then searches ALL children starting with that name prefix.", 
                    word_wrap=True, 
                    style=FIELD_CONTEXT_STYLE
                )

    def on_shutdown(self):
        print("[SmartReference] SmartReference shutdown")
        if hasattr(self, "_window"):
            self._window.destroy()
            self._window = None