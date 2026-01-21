import omni.ext
import omni.ui as ui
import weakref

# --- 匯入既有的五個子工具 (維持不變) ---
from smart_align.extension import SmartAlignExtension
from smart_assets_builder.extension import SmartAssetsBuilderExtension
from smart_measure.extension import SmartMeasureExtension
from smart_reference.extension import SmartReferenceExtension
from smart_assembly.extension import SmartAssemblyExtension
from smart_physics_setup.extension import SmartPhysicsSetupExtension

class ToolsBoxExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        print("[Tools Box] Startup")

        # --- 1. 實例化子工具 ---
        self.tool_align = SmartAlignExtension()
        if hasattr(self.tool_align, "startup_logic"):
            self.tool_align.startup_logic()

        self.tool_assets = SmartAssetsBuilderExtension()
        
        self.tool_measure = SmartMeasureExtension()
        self.tool_measure.startup_logic()
        
        self.tool_reference = SmartReferenceExtension()

        self.tool_assembly = SmartAssemblyExtension()
        self.tool_assembly.startup_logic()

        self.tool_physics = SmartPhysicsSetupExtension()
        if hasattr(self.tool_physics, "_init_data"):
            self.tool_physics._init_data()
        
        # --- [NEW] 實例化 Physics 工具 ---
        # 由於是本地模組，不需要 try-except 也不用擔心 extension 沒載入
        self.tool_physics = SmartPhysicsSetupExtension()
        # 如果你的 Physics 類別保留了 on_startup，可以手動呼叫它 (看你的需求)
        if hasattr(self.tool_physics, "on_startup"):
            self.tool_physics.on_startup(ext_id)

        # 記錄當前啟用的 Tab 名稱
        self._current_tab = "Measure" 
        self._content_frame = None

        # --- 定義按鈕樣式 (Style) ---
        self._STYLE_TAB_ACTIVE = {
            "background_color": 0xFF44AA44,  # Green
            "border_radius": 4,
            "margin": 2,
            "font_size": 16
        }

        self._STYLE_TAB_INACTIVE = {
            "background_color": 0xFF343432,  # Dark Gray
            "border_radius": 4,
            "margin": 2,
            "font_size": 16
        }

        # --- 2. 建立主視窗 ---
        self._window = ui.Window("Tools Box", width=600, height=600)

        with self._window.frame:
            with ui.VStack(spacing=0, alignment=ui.Alignment.TOP):
                
                # --- A. 頁籤列 (Tab Bar) ---
                with ui.HStack(height=40, style={"margin": 5, "spacing": 5}):
                    self._btn_measure = ui.Button("Measure", height=30, clicked_fn=lambda: self._change_tab("Measure"))
                    self._btn_assets = ui.Button("Builder", height=30, clicked_fn=lambda: self._change_tab("Assets"))
                    self._btn_ref = ui.Button("Reference", height=30, clicked_fn=lambda: self._change_tab("Reference"))
                    self._btn_align = ui.Button("Align", height=30, clicked_fn=lambda: self._change_tab("Align"))
                    self._btn_assembly = ui.Button("Assembly", height=30, clicked_fn=lambda: self._change_tab("Assembly"))
                    self._btn_physics = ui.Button("Physics", height=30, clicked_fn=lambda: self._change_tab("Physics"))

                # --- B. 內容顯示區 (Content Area) ---
                self._content_frame = ui.Frame(padding=1)
                
                # 預設顯示分頁
                self._refresh_content()

    def _change_tab(self, tab_name):
        if self._current_tab == tab_name:
            return
        self._current_tab = tab_name
        self._refresh_content()

    def _refresh_content(self):
        """清空並重新繪製內容區域"""
        if not self._content_frame:
            return

        # 1. 清空舊內容
        self._content_frame.clear()

        # 2. 繪製新內容
        with self._content_frame:
            # 包裹一層 VStack(TOP) 確保所有子工具都靠上對齊
            with ui.VStack(alignment=ui.Alignment.TOP):
                
                if self._current_tab == "Align":
                    self._highlight_tab(self._btn_align)
                    if hasattr(self.tool_align, "build_ui_layout"):
                        self.tool_align.build_ui_layout()

                elif self._current_tab == "Assets":
                    self._highlight_tab(self._btn_assets)
                    if hasattr(self.tool_assets, "build_ui_layout"):
                        self.tool_assets.build_ui_layout()

                elif self._current_tab == "Measure":
                    self._highlight_tab(self._btn_measure)
                    if hasattr(self.tool_measure, "build_ui_layout"):
                        self.tool_measure.build_ui_layout()

                elif self._current_tab == "Reference":
                    self._highlight_tab(self._btn_ref)
                    if hasattr(self.tool_reference, "build_ui_layout"):
                        self.tool_reference.build_ui_layout()

                elif self._current_tab == "Assembly":
                    self._highlight_tab(self._btn_assembly)
                    if hasattr(self.tool_assembly, "build_ui_layout"):
                        self.tool_assembly.build_ui_layout()
                        
                # --- [NEW] Physics UI ---
                elif self._current_tab == "Physics":
                    self._highlight_tab(self._btn_physics)
                    # 直接呼叫 build_ui_layout，因為現在確定它一定存在
                    if self.tool_physics:
                        self.tool_physics.build_ui_layout()

    def _highlight_tab(self, active_btn):
        """按鈕視覺回饋：切換樣式"""
        self._btn_align.style = self._STYLE_TAB_INACTIVE
        self._btn_assets.style = self._STYLE_TAB_INACTIVE
        self._btn_measure.style = self._STYLE_TAB_INACTIVE
        self._btn_ref.style = self._STYLE_TAB_INACTIVE
        self._btn_assembly.style = self._STYLE_TAB_INACTIVE 
        self._btn_physics.style = self._STYLE_TAB_INACTIVE

        active_btn.style = self._STYLE_TAB_ACTIVE

    def on_shutdown(self):
        if self._window:
            self._window.destroy()
            self._window = None
        
        # 釋放子工具並停止監聽
        if self.tool_measure:
            self.tool_measure.shutdown_logic()
            self.tool_measure = None

        if self.tool_assembly:
            self.tool_assembly.shutdown_logic()
            self.tool_assembly = None
            
        # --- [NEW] 清理 Physics ---
        if self.tool_physics:
            if hasattr(self.tool_physics, "on_shutdown"):
                self.tool_physics.on_shutdown()
            self.tool_physics = None
            
        self.tool_reference = None
        self.tool_assets = None
        
        if self.tool_align:
            if hasattr(self.tool_align, "shutdown_logic"):
                self.tool_align.shutdown_logic()
            self.tool_align = None