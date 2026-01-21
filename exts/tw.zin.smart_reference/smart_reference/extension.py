import omni.ext
import omni.ui as ui
import omni.usd
from pxr import Sdf, Usd

class SmartReferenceExtension(omni.ext.IExt):
    WINDOW_NAME = "Smart Reference"
    MENU_PATH = f"Zin Tools/{WINDOW_NAME}"

    def on_startup(self, ext_id):
        # 1. 初始化資料
        self._init_data()

        # 2. 建立選單 (Standalone 模式)
        self._menu_added = False
        self._build_menu()

        # 3. 建立視窗 (Standalone 模式)
        # 注意：這裡只建立 Window 物件，內容由 build_ui 填充
        self._window = ui.Window(self.WINDOW_NAME, width=400, height=450)
        self._window.set_visibility_changed_fn(self._on_visibility_changed)
        
        with self._window.frame:
            self.build_ui_layout()
            
        # 預設隱藏視窗 (等待選單開啟)
        self._window.visible = False

    def _init_data(self):
        """初始化內部變數"""
        if hasattr(self, "_field_prefix"):
            return
            
        self._field_prefix = None
        self._field_url = None
        self._lbl_status = None
        
        # 新增：掃描結果存放區
        self._found_paths = [] 
        self._field_results = None 

    def on_shutdown(self):
        self._remove_menu()
        if self._window:
            self._window.destroy()
            self._window = None

    # ========================================================
    #  UI 建構區 (All Tools 與 Standalone 共用)
    # ========================================================
    def build_ui_layout(self):
        """
        Zin All Tools 會呼叫此方法。
        """
        print("[SmartReference] build_ui_layout called")
        # 確保資料已初始化
        self._init_data()

        # 使用 ScrollingFrame 確保內容不會被切掉
        with ui.ScrollingFrame(
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
        ):
            # 內容靠上對齊
            with ui.VStack(spacing=10, padding=20, alignment=ui.Alignment.TOP):
                
                # --- Row 1: Target Prefix ---
                ui.Label("Target Prefix (Parent/Name):", height=20, style={"color": 0xFFDDDDDD, "font_size": 14})
                
                # Instruction (Translated & Moved Up)
                ui.Label("Please remove the suffix serial number, ex: Prim_001 >> Prim_", height=20, style={"color": 0xFF888888, "font_size": 12})
                
                self._field_prefix = ui.StringField(height=30)
                self._field_prefix.model.set_value("/World/Example")
                    
                ui.Spacer(height=5)
                
                # Scan Button (Moved Below)
                ui.Button(
                    "Scan", 
                    height=30,
                    clicked_fn=self._on_scan
                    # Match SmartAssetsBuilder style: fills width naturally in VStack or use width=ui.Fraction(1)
                )

                # --- Row 2: Asset URL ---
                ui.Label("Asset URL (.usd):", height=20, style={"color": 0xFFDDDDDD, "font_size": 14})
                self._field_url = ui.StringField(height=30)
                self._field_url.model.set_value("omniverse://localhost/Projects/Asset.usd")

                ui.Spacer(height=15)

                # --- Row 3: Status (Moved Up) ---
                ui.Label("Status:", height=20, style={"color": 0xFFAAAAAA, "font_size": 12})
                self._lbl_status = ui.Label(
                    "Ready", 
                    height=20, 
                    style={"color": 0xFFDDDDDD, "font_size": 14},
                    word_wrap=True
                )
                
                ui.Spacer(height=10)

                # --- Row 4: Results ---
                ui.Label("Scan Results:", height=20, style={"color": 0xFFAAAAAA, "font_size": 12})
                self._field_results = ui.StringField(height=100, multiline=True, read_only=True)
                
                ui.Spacer(height=10)
                ui.Separator(height=10)

                # --- Row 5: Action Buttons (Apply & Reset) ---
                with ui.HStack(height=40, spacing=10):
                    ui.Button(
                        "Apply Reference", 
                        clicked_fn=self._on_apply_reference,
                        style={"background_color": 0xFF225522}
                    )
                    
                    ui.Button(
                        "Reset", 
                        clicked_fn=self._on_reset,
                        style={"background_color": 0xFF552222} 
                    )

                ui.Spacer()

    # ========================================================
    #  邏輯處理區
    # ========================================================
    def _update_status(self, message, color=0xFFDDDDDD):
        """更新狀態標籤"""
        if self._lbl_status:
            self._lbl_status.text = message
            self._lbl_status.style = {"color": color, "font_size": 14}
        print(f"[SmartReference] {message}")

    def _on_reset(self):
        """重置部分欄位 (保留 Asset URL)"""
        print("[SmartReference] _on_reset called")
        self._found_paths = []
        
        if self._field_prefix:
            self._field_prefix.model.set_value("/World/Example")
        
        # [Modified] User requested to KEEP Asset URL
        # if self._field_url:
        #    self._field_url.model.set_value("omniverse://localhost/Projects/Asset.usd")

        if self._field_results:
            self._field_results.model.set_value("")
            
        self._update_status("Reset Complete (URL preserved).", 0xFFDDDDDD)

    def _on_scan(self):
        """執行掃描邏輯"""
        print("[SmartReference] _on_scan called")
        self._update_status("Scanning...", 0xFFFFFF00)
        self._found_paths = [] # Reset
        if self._field_results:
            self._field_results.model.set_value("")

        # 確保 UI 元件存在
        if not self._field_prefix:
            return

        prefix_input = self._field_prefix.model.get_value_as_string().strip()

        if not prefix_input:
            self._update_status("Error: Prefix field is empty.", 0xFF5555FF)
            return

        # 解析路徑
        if "/" in prefix_input:
            parent_path, prefix_name = prefix_input.rsplit("/", 1)
            if not parent_path: parent_path = "/"
        else:
            parent_path = "/World"
            prefix_name = prefix_input

        print(f"[SmartReference] Scanning {parent_path} for children starting with '{prefix_name}'")

        ctx = omni.usd.get_context()
        stage = ctx.get_stage()
        
        if not stage:
            self._update_status("Error: No stage opened.", 0xFF5555FF)
            return

        parent_prim = stage.GetPrimAtPath(parent_path)
        if not parent_prim.IsValid():
            self._update_status(f"Error: Parent '{parent_path}' not found.", 0xFF5555FF)
            return

        try:
            children = list(parent_prim.GetChildren())
            count = 0
            found_list_str = ""

            for child in children:
                if child.GetName().startswith(prefix_name):
                    path = str(child.GetPath())
                    self._found_paths.append(path)
                    found_list_str += f"{path}\n"
                    count += 1
            
            if self._field_results:
                self._field_results.model.set_value(found_list_str)

            if count > 0:
                self._update_status(f"Scan Complete: Found {count} items.", 0xFF76B900)
            else:
                self._update_status(f"Scan Finished: 0 matches for '{prefix_name}'", 0xFFFFAA00)

        except Exception as e:
            self._update_status(f"Exception during scan: {str(e)}", 0xFF5555FF)
            print(e)


    def _on_apply_reference(self):
        """執行 Applying 邏輯"""
        print("[SmartReference] _on_apply_reference called")
        
        if not self._found_paths:
            self._update_status("Warning: No targets found. Please Scan first.", 0xFFFFAA00)
            return

        if not self._field_url:
            return

        asset_url = self._field_url.model.get_value_as_string().strip()
        # [Fix] Sanitize path for Windows
        asset_url = asset_url.replace("\\", "/")

        if not asset_url:
            self._update_status("Error: Asset URL is empty.", 0xFF5555FF)
            return

        self._update_status(f"Applying reference to {len(self._found_paths)} items...", 0xFFFFFF00)

        ctx = omni.usd.get_context()
        stage = ctx.get_stage()
        
        if not stage:
            self._update_status("Error: Stage lost.", 0xFF5555FF)
            return

        success_count = 0
        try:
            for path in self._found_paths:
                prim = stage.GetPrimAtPath(path)
                if prim.IsValid():
                    print(f"[SmartReference] Applying to {path} -> {asset_url}")
                    refs = prim.GetReferences()
                    refs.ClearReferences()
                    refs.AddReference(asset_url)
                    success_count += 1
            
            self._update_status(f"Success: Updated {success_count} prims.", 0xFF76B900)

        except Exception as e:
            self._update_status(f"Exception during apply: {str(e)}", 0xFF5555FF)
            print(e)

    # ========================================================
    #  選單與視窗管理 (Standalone 模式)
    # ========================================================
    def _build_menu(self):
        try:
            m = omni.kit.ui.get_editor_menu()
            if m: 
                m.add_item(self.MENU_PATH, self._toggle_window, toggle=True, value=False)
            self._menu_added = True
        except: 
            pass

    def _remove_menu(self):
        try:
            m = omni.kit.ui.get_editor_menu()
            if m and m.has_item(self.MENU_PATH): 
                m.remove_item(self.MENU_PATH)
        except: 
            pass

    def _toggle_window(self, menu, value):
        if self._window:
            self._window.visible = bool(value)

    def _on_visibility_changed(self, visible):
        if self._menu_added:
            try: 
                omni.kit.ui.get_editor_menu().set_value(self.MENU_PATH, bool(visible))
            except: 
                pass