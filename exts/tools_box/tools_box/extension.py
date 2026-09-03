import omni.ext
import omni.ui as ui
import weakref
import carb
from pxr import Gf
from zin_core.components import ZinButton
from zin_core.menu import ZinMenuMixin
from zin_core.style import ZIN_GLOBAL_STYLE

class ToolsBoxExtension(ZinMenuMixin, omni.ext.IExt):
    WINDOW_NAME = "Zin Tools Box"
    MENU_PATH = f"Zin_All_Tools/{WINDOW_NAME}"

    def on_startup(self, ext_id):
        carb.log_info("[Tools Box] Startup")
        self._window = None
        self._menu_added = False

        # --- Lazy Import Sub-tools to prevent circular import ---
        from smart_align.extension import SmartAlignExtension
        from smart_exploded.extension import ZinSmartExplodedExtension
        from web_dashboard.extension import ZinWebDashboardExtension
        from smart_assets_builder.extension import SmartAssetsBuilderExtension
        from smart_measure.extension import SmartMeasureExtension
        from smart_reference.extension import SmartReferenceExtension, SmartReferenceUI 
        from smart_assembly.extension import SmartAssemblyExtension
        from smart_physics_setup.extension import SmartPhysicsSetupExtension
        from smart_conveyor.extension import SmartConveyorExtension
        from smart_cad_convert.extension import SmartCadConvertUI
        from smart_information.extension import SmartInformationUI
        from smart_hud.extension import SmartHudUI

        # --- 1. Instantiate sub-tools ---
        self.tool_align = None
        self.tool_assets = None
        self.tool_measure = None
        self.tool_reference = None
        self.tool_reference_ui = None
        self.tool_assembly = None
        self.tool_physics = None
        self.tool_explode = None
        self.tool_conveyor = None
        self.tool_dashboard = None

        self.tool_align = SmartAlignExtension()
        if hasattr(self.tool_align, "startup_logic"):
            self.tool_align.startup_logic()

        self.tool_assets = SmartAssetsBuilderExtension()
        
        self.tool_measure = SmartMeasureExtension()
        self.tool_measure.startup_logic()
        
        # --- Smart Reference 整合修正 ---
        self.tool_reference = SmartReferenceExtension()
        # 建立 UI 實例，供 Tab 切換時呼叫 build_ui
        self.tool_reference_ui = SmartReferenceUI() 
        self.tool_cad_convert_ui = SmartCadConvertUI() 

        self.tool_assembly = SmartAssemblyExtension()
        self.tool_assembly.startup_logic()
        
        # --- Physics 工具 ---
        self.tool_physics = SmartPhysicsSetupExtension()
        if hasattr(self.tool_physics, "on_startup"):
            self.tool_physics.on_startup(ext_id)

        # --- Exploded View tool (persistent state across tab switches) ---
        self.tool_explode = ZinSmartExplodedExtension()
        if hasattr(self.tool_explode, "on_startup"):
            self.tool_explode.on_startup(ext_id)
            
        # --- Web Dashboard tool ---
        self.tool_dashboard = ZinWebDashboardExtension()
        if hasattr(self.tool_dashboard, "on_startup"):
            self.tool_dashboard.on_startup(ext_id)

        # --- Smart Conveyor tool (embedded mode) ---
        # startup_as_embedded() initializes Timeline subscription and USD auto-load
        # without creating a standalone 'Smart Conveyor Panel' window or menu item.
        self.tool_conveyor = SmartConveyorExtension()
        self.tool_conveyor.startup_as_embedded(ext_id)

        # --- Smart Information tool ---
        self.tool_info_ui = SmartInformationUI()
        self.tool_info_ui.startup()
        
        # --- Smart HUD tool ---
        self.tool_hud_ui = SmartHudUI()

        # 記錄當前啟用的 Tab 名稱
        self._current_tab = "Measure" 
        self._content_frame = None

        self._build_menu()

        # --- Explicitly register menus for all embedded sub-tools ---
        for tool in [
            self.tool_align, self.tool_assets, self.tool_measure, 
            self.tool_reference, self.tool_assembly, self.tool_physics, 
            self.tool_explode
        ]:
            if hasattr(tool, "_build_menu"):
                try:
                    tool._build_menu()
                except Exception as e:
                    carb.log_error(f"[Tools Box] Failed to build menu for {tool}: {e}")

        # --- Show the Zin Tools Box automatically on startup ---
        self._toggle_window(None, True)

    def _toggle_window(self, menu, value):
        if value:
            if not self._window:
                # --- 2. 建立主視窗 ---
                self._window = ui.Window(self.WINDOW_NAME, width=600, height=600, dockPreference=ui.DockPreference.RIGHT_BOTTOM)
                self._window.deferred_dock_in("Property")
                self._window.set_visibility_changed_fn(self._on_visibility_changed)

                with self._window.frame:
                    with ui.VStack(spacing=0, alignment=ui.Alignment.TOP, style=ZIN_GLOBAL_STYLE):
                        
                        # --- A. 頁籤列 (Tab Bar) ---
                        with ui.ScrollingFrame(height=ui.Pixel(45), vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF, horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED):
                            with ui.HStack(height=ui.Pixel(30), style={"margin": 5, "spacing": 5}):
                                self._btn_measure  = ZinButton("Measure",   height=ui.Pixel(30), clicked_fn=lambda: self._change_tab("Measure"))
                                self._btn_assets   = ZinButton("Builder",   height=ui.Pixel(30), clicked_fn=lambda: self._change_tab("Assets"))
                                self._btn_ref      = ZinButton("Reference", height=ui.Pixel(30), clicked_fn=lambda: self._change_tab("Reference"))
                                self._btn_align    = ZinButton("Align",     height=ui.Pixel(30), clicked_fn=lambda: self._change_tab("Align"))
                                self._btn_assembly = ZinButton("Assembly",  height=ui.Pixel(30), clicked_fn=lambda: self._change_tab("Assembly"))
                                self._btn_physics  = ZinButton("Physics",   height=ui.Pixel(30), clicked_fn=lambda: self._change_tab("Physics"))
                                self._btn_hud      = ZinButton("HUD",       height=ui.Pixel(30), clicked_fn=lambda: self._change_tab("HUD"))
                                self._btn_explode  = ZinButton("Explode",   height=ui.Pixel(30), clicked_fn=lambda: self._change_tab("Explode"))
                                self._btn_conveyor = ZinButton("Conveyor",  height=ui.Pixel(30), clicked_fn=lambda: self._change_tab("Conveyor"))
                                self._btn_cad      = ZinButton("CAD",       height=ui.Pixel(30), clicked_fn=lambda: self._change_tab("CAD"))
                                self._btn_dashboard = ZinButton("Dashboard", height=ui.Pixel(30), clicked_fn=lambda: self._change_tab("Dashboard"))
                                self._btn_info     = ZinButton("Info",      height=ui.Pixel(30), clicked_fn=lambda: self._change_tab("Info"))

                        # --- B. 內容顯示區 (Content Area) ---
                        self._content_frame = ui.Frame(padding=1)
                        
                        # 預設顯示分頁
                        self._refresh_content()
            self._window.visible = True
        else:
            if self._window:
                self._window.visible = False

    def _on_visibility_changed(self, visible):
        # We no longer call omni.kit.ui.get_editor_menu().set_value here
        # to prevent the "menu not found" warning in the console.
        pass

    def _change_tab(self, tab_name):
        if self._current_tab == tab_name:
            return
        self._hide_current_tab()
        self._current_tab = tab_name
        self._refresh_content()

    def _hide_current_tab(self):
        tab_tools = {
            "Align": self.tool_align,
            "Measure": self.tool_measure,
        }
        tool = tab_tools.get(self._current_tab)
        if tool and hasattr(tool, "on_ui_hidden"):
            tool.on_ui_hidden()

    def _refresh_content(self):
        """Clear and redraw the content area"""
        if not self._content_frame:
            return

        # 1. 清空舊內容
        self._content_frame.clear()

        # 2. 繪製新內容
        with self._content_frame:
            with ui.VStack(alignment=ui.Alignment.TOP):
                
                if self._current_tab == "Align":
                    self._highlight_tab(self._btn_align)
                    if self.tool_align and hasattr(self.tool_align, "build_ui_layout"):
                        self.tool_align.build_ui_layout()

                elif self._current_tab == "Assets":
                    self._highlight_tab(self._btn_assets)
                    if self.tool_assets and hasattr(self.tool_assets, "build_ui_layout"):
                        self.tool_assets.build_ui_layout()

                elif self._current_tab == "Measure":
                    self._highlight_tab(self._btn_measure)
                    if self.tool_measure and hasattr(self.tool_measure, "build_ui_layout"):
                        self.tool_measure.build_ui_layout()

                elif self._current_tab == "Reference":
                    self._highlight_tab(self._btn_ref)
                    # 關鍵：呼叫 SmartReferenceUI 的 build_ui() 嵌入內容
                    if self.tool_reference_ui:
                        self.tool_reference_ui.build_ui()

                elif self._current_tab == "Assembly":
                    self._highlight_tab(self._btn_assembly)
                    if self.tool_assembly and hasattr(self.tool_assembly, "build_ui_layout"):
                        self.tool_assembly.build_ui_layout()
                        
                elif self._current_tab == "Physics":
                    self._highlight_tab(self._btn_physics)
                    if self.tool_physics:
                        self.tool_physics.build_ui_layout()

                elif self._current_tab == "Explode":
                    self._highlight_tab(self._btn_explode)
                    if self.tool_explode:
                        self.tool_explode.build_ui()

                elif self._current_tab == "Conveyor":
                    self._highlight_tab(self._btn_conveyor)
                    if self.tool_conveyor:
                        self.tool_conveyor.build_ui_layout()

                elif self._current_tab == "CAD":
                    self._highlight_tab(self._btn_cad)
                    if self.tool_cad_convert_ui:
                        self.tool_cad_convert_ui.build_ui()
                        
                elif self._current_tab == "Dashboard":
                    self._highlight_tab(self._btn_dashboard)
                    if self.tool_dashboard:
                        self.tool_dashboard.build_ui_layout()
                        
                elif self._current_tab == "Info":
                    self._highlight_tab(self._btn_info)
                    if self.tool_info_ui:
                        self.tool_info_ui.build_ui()
                        
                elif self._current_tab == "HUD":
                    self._highlight_tab(self._btn_hud)
                    if self.tool_hud_ui:
                        self.tool_hud_ui.build_ui()

    def _highlight_tab(self, active_btn):
        """Tab button visual feedback via ZinButton.set_state()"""
        for btn in [
            self._btn_align, self._btn_assets, self._btn_measure,
            self._btn_ref, self._btn_assembly, self._btn_physics,
            self._btn_explode, self._btn_conveyor, self._btn_cad, self._btn_dashboard, self._btn_info, self._btn_hud
        ]:
            btn.set_state("default")
        active_btn.set_state("correct")

    def on_shutdown(self):
        self._remove_menu()
        if self._window:
            self._window.destroy()
            self._window = None
        
        if self.tool_measure:
            self.tool_measure.shutdown_logic()
            self.tool_measure = None

        if self.tool_assembly:
            self.tool_assembly.shutdown_logic()
            self.tool_assembly = None
            
        if self.tool_physics:
            if hasattr(self.tool_physics, "on_shutdown"):
                self.tool_physics.on_shutdown()
            self.tool_physics = None
            
        # 清理 Reference UI 引用
        self.tool_reference_ui = None
        self.tool_cad_convert_ui = None
        if hasattr(self, "tool_info_ui") and self.tool_info_ui:
            self.tool_info_ui.shutdown()
            self.tool_info_ui = None
            
        if hasattr(self, "tool_hud_ui") and self.tool_hud_ui:
            self.tool_hud_ui.shutdown()
            self.tool_hud_ui = None
            
        self.tool_reference = None
        self.tool_assets = None
        
        if self.tool_align:
            if hasattr(self.tool_align, "shutdown_logic"):
                self.tool_align.shutdown_logic()
            self.tool_align = None

        # Clean up Exploded View reference
        self.tool_explode = None

        # Stop and clean up Smart Conveyor (on_shutdown handles controllers list,
        # FilePicker dialogs, and Timeline subscription correctly)
        if self.tool_conveyor:
            if hasattr(self.tool_conveyor, "on_shutdown"):
                self.tool_conveyor.on_shutdown()
            self.tool_conveyor = None