import omni.ext
import omni.ui as ui
import omni.usd
import omni.kit.app
from pxr import Usd, UsdGeom, Gf

class ZinSmartExplodedExtension(omni.ext.IExt):
    """
    Zin Smart Exploded View Extension - Interactive Displacement Workflow
    專為工業數位孿生檢查設計的互動式零件位移模組，支援即時拖曳、多選位移與狀態記憶。
    """
    WINDOW_NAME = "Smart Explode"
    MENU_PATH = f"Zin_All_Tools/{WINDOW_NAME}"
    
    def on_startup(self, ext_id):
        print("[Zin Smart Exploded View] 擴充模組已啟動 (Interactive Workflow)")
        self._window = None
        self._menu_added = False

        # 記錄每個 prim 的原始位移狀態與累計的位移量
        # 確保即時拖曳不會導致誤差累積，並支援完美 1:1 重置
        self._original_translations = {} # 字典格式: { prim_path (str): Gf.Vec3d }
        self._offsets = {}               # 字典格式: { prim_path (str): [x, y, z] }

        # 當前操作軸向: 0=X, 1=Y, 2=Z
        self._current_axis = 0
        self._ignore_slider_event = False

        # 定義高階工業 CAD 介面風格字典 (遵循 Zin_Tools_Box 規範)
        self._style = {
            "Button": {
                "background_color": 0xFF444444, # Default: 深灰背景
                "color": 0xFFDDDDDD,
                "border_color": 0x00000000,
                "border_width": 1.0,
                "border_radius": 4.0,
                "padding": 5.0
            },
            "Button:hover": {
                "border_color": 0xFFFFA500,     # Hover: 品牌橘色邊框高亮
            },
            "Button:pressed": {
                "background_color": 0xFFFFA500, # Pressed: 品牌橘色
                "color": 0xFF000000,          
            },
            "Button.Active": {
                "background_color": 0xFFFFA500, # Active (作用中): 實心品牌橘色
                "color": 0xFF000000,
                "border_radius": 4.0
            },
            "FloatSlider": {
                "background_color": 0xFF222222,
                "color": 0xFFFFA500,            # 滑桿進度條: 品牌橘色
                "border_radius": 4.0
            },
            "Label": {
                "color": 0xFFDDDDDD,
            }
        }

        # 註冊 USD 選取事件監聽器 (Selection Subscription)
        self._events = omni.usd.get_context().get_selection().get_selection_event_stream()
        self._selection_sub = self._events.create_subscription_to_pop(self._on_selection_changed)
        
        self._build_menu()

    def _build_menu(self):
        try:
            import omni.kit.menu.utils
            self._menu = omni.kit.menu.utils.add_menu_items([
                omni.kit.menu.utils.MenuItemDescription(
                    name=self.WINDOW_NAME,
                    onclick_fn=lambda *args: self._toggle_window(None, True)
                )
            ], "Zin_All_Tools")
            self._menu_added = True
        except Exception: pass

    def _remove_menu(self):
        try:
            import omni.kit.menu.utils
            if hasattr(self, '_menu') and self._menu:
                omni.kit.menu.utils.remove_menu_items(self._menu, "Zin_All_Tools")
                self._menu = None
        except Exception: pass
    def _toggle_window(self, menu, value):
        if value:
            if not self._window:
                self._window = ui.Window(self.WINDOW_NAME, width=400, height=350, dockPreference=ui.DockPreference.RIGHT_BOTTOM)
                self._window.set_visibility_changed_fn(self._on_visibility_changed)
                self.build_ui()
            self._window.visible = True
        else:
            if self._window:
                self._window.visible = False

    def _on_visibility_changed(self, visible):
        if self._menu_added:
            try:
                import omni.kit.ui
                omni.kit.ui.get_editor_menu().set_value(self.MENU_PATH, bool(visible))
            except Exception:
                pass

    def build_ui(self):
        """
        建立互動式位移管理員的 UI 佈局
        """
        with self._window.frame:
            with ui.VStack(style=self._style, spacing=10, padding=15):
                # --- Header 區塊 ---
                with ui.VStack(spacing=5):
                    ui.Label("Interactive Part Displacement", style={"font_size": 18, "color": 0xFFFFFFFF, "font_weight": "bold"})
                    ui.Line(height=2, style={"color": 0xFFFFA500}) # 水平品牌橘色分隔線
                
                ui.Spacer(height=5)
                
                # --- Axis Toggles (軸向切換區塊) ---
                ui.Label("Axis (方向):")
                with ui.HStack(height=30, spacing=10):
                    self._btn_x = ui.Button("X 軸", clicked_fn=lambda: self._set_axis(0))
                    self._btn_y = ui.Button("Y 軸", clicked_fn=lambda: self._set_axis(1))
                    self._btn_z = ui.Button("Z 軸", clicked_fn=lambda: self._set_axis(2))
                
                ui.Spacer(height=10)

                # --- Large Displacement Slider (即時拖曳滑桿) ---
                ui.Label("Displacement (位移量):")
                
                # 建立浮點數模型並設定範圍 -500 到 500
                self._displacement_model = ui.SimpleFloatModel(0.0)
                self._displacement_model.set_min(-500.0)
                self._displacement_model.set_max(500.0)
                self._displacement_model.add_value_changed_fn(self._on_slider_changed)
                
                self._slider = ui.FloatSlider(
                    self._displacement_model, 
                    height=30, 
                    style={"draw_mode": ui.SliderDrawMode.DRAG}
                )
                self._slider.enabled = False # 預設停用，待選取物件後啟用
                
                ui.Spacer(height=15)

                # --- Action Buttons (底部操作按鈕) ---
                with ui.HStack(height=40, spacing=10):
                    ui.Button("Reset All (復原歸位)", clicked_fn=self._reset_all)
                    ui.Button("Commit (清除紀錄)", clicked_fn=self._clear_history)

        # 初始化預設軸向為 X 軸
        self._set_axis(0)

    def _set_axis(self, axis_idx):
        """
        設定當前操作的軸向，並更新按鈕樣式與滑桿位置。
        """
        self._current_axis = axis_idx
        
        # 更新按鈕的 Active 樣式 (利用 Button.Active)
        self._btn_x.name = "Active" if axis_idx == 0 else ""
        self._btn_y.name = "Active" if axis_idx == 1 else ""
        self._btn_z.name = "Active" if axis_idx == 2 else ""

        # 切換軸向時，同步更新滑桿以反映該軸的當前位移量
        self._sync_slider_to_selection()

    def _get_translation_op(self, xformable: UsdGeom.Xformable):
        """
        安全地取得或新增 xformOp:translate
        確保附加式的位移 (Additive Displacement) 不破壞模型既有的階層與旋轉結構。
        """
        ops = xformable.GetOrderedXformOps()
        for op in ops:
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                return op
        return xformable.AddTranslateOp()

    def _on_selection_changed(self, event):
        """
        選取改變事件處理器：
        動態啟用/停用滑桿，並為新選取的物件記錄其原始位置 (Original Position)。
        """
        selection = omni.usd.get_context().get_selection().get_selected_prim_paths()
        stage = omni.usd.get_context().get_stage()
        
        if not selection or not stage:
            self._slider.enabled = False
            return
            
        self._slider.enabled = True

        for path in selection:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue
                
            xformable = UsdGeom.Xformable(prim)
            if not xformable:
                continue

            # 若為首次選取該物件，則記錄其初始狀態
            if path not in self._original_translations:
                trans_op = self._get_translation_op(xformable)
                current_val = trans_op.Get()
                if current_val is None:
                    current_val = Gf.Vec3d(0.0, 0.0, 0.0)
                
                self._original_translations[path] = current_val
                self._offsets[path] = [0.0, 0.0, 0.0]

        # 根據首個選取物件，對齊滑桿當前進度
        self._sync_slider_to_selection()

    def _sync_slider_to_selection(self):
        """
        當選取改變或軸向改變時，讓滑桿數值自動 Snap 到物件現有的位移量。
        """
        selection = omni.usd.get_context().get_selection().get_selected_prim_paths()
        if not selection:
            return

        # 基準以第一個選取的物件為準
        first_path = selection[0]
        if first_path in self._offsets:
            val = self._offsets[first_path][self._current_axis]
            
            # 暫時阻擋滑桿改變事件，避免觸發多餘的場景更新
            self._ignore_slider_event = True
            self._displacement_model.as_float = val
            self._ignore_slider_event = False

    def _on_slider_changed(self, model):
        """
        滑桿拖曳事件處理器：
        即時更新選取物件的變形矩陣。當使用者放開滑桿時，物件會自然停留在最後的位置 (Hover/Stay State)。
        """
        if self._ignore_slider_event:
            return
            
        val = model.as_float
        selection = omni.usd.get_context().get_selection().get_selected_prim_paths()
        stage = omni.usd.get_context().get_stage()
        
        if not stage:
            return

        for path in selection:
            if path in self._offsets and path in self._original_translations:
                # 更新該物件在當前操作軸向的相對位移量
                self._offsets[path][self._current_axis] = val
                
                orig = self._original_translations[path]
                offset = self._offsets[path]
                
                # 相加得出最終世界座標 (Additive Transform)
                new_pos = Gf.Vec3d(orig[0] + offset[0], orig[1] + offset[1], orig[2] + offset[2])

                prim = stage.GetPrimAtPath(path)
                if prim and prim.IsValid():
                    xformable = UsdGeom.Xformable(prim)
                    if xformable:
                        trans_op = self._get_translation_op(xformable)
                        trans_op.Set(new_pos)

    def _reset_all(self):
        """
        復原歸位：將所有曾經移動過的物件重置回原始座標。
        """
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return

        for path, orig_pos in self._original_translations.items():
            prim = stage.GetPrimAtPath(path)
            if prim and prim.IsValid():
                xformable = UsdGeom.Xformable(prim)
                if xformable:
                    trans_op = self._get_translation_op(xformable)
                    trans_op.Set(orig_pos)

        # 清空紀錄
        self._original_translations.clear()
        self._offsets.clear()
        self._sync_slider_to_selection()

    def _clear_history(self):
        """
        清除紀錄 (Commit)：將當前所有物件的位置確認為「新的原始狀態」。
        清除先前的位移歷程，使得下次拖曳將以目前所在位置作為新的起點。
        """
        self._original_translations.clear()
        self._offsets.clear()
        
        # 強制重新紀錄當前選取物件的新位置
        self._on_selection_changed(None)

    def on_shutdown(self):
        """
        清理資源：關閉視窗、解除事件監聽、清空快取
        """
        print("[Zin Smart Exploded View] 擴充模組已關閉")
        self._remove_menu()
        self._selection_sub = None
        
        if self._window:
            self._window.destroy()
            self._window = None
            
        self._original_translations.clear()
        self._offsets.clear()
