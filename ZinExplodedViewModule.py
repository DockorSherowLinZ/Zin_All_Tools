import omni.ui as ui
import omni.usd
import omni.kit.app
from pxr import Usd, UsdGeom, Gf
import asyncio
import time

class ZinExplodedViewModule:
    """
    ZinExplodedViewModule
    專為工業數位孿生檢查設計的爆炸圖管理模組
    適用於 USD Composer 109.0.2，提供具備專業緩動效果 (Ease-Out) 的非同步爆炸與合併功能。
    """
    def __init__(self):
        # 記錄每個 prim 的原始位移狀態，確保後續合併 (Merge) 能完美 1:1 重置
        # 字典格式: { prim_path (str): Gf.Vec3d }
        self._original_translations = {}
        
        # 動畫與邏輯狀態追蹤
        self._is_exploded = False
        self._animation_task = None
        
        # 控制面板 UI 參數模型
        self._distance_model = ui.SimpleFloatModel(100.0)
        self._duration_model = ui.SimpleFloatModel(1.0)
        
        # 預設爆炸方向 (預設為 X 軸)
        self._direction_vector = Gf.Vec3d(1.0, 0.0, 0.0)
        
        # 定義高階工業 CAD 介面風格字典
        self._style = {
            "Button": {
                "background_color": 0xFF444444, # 預設：深灰背景
                "color": 0xFFDDDDDD,
                "border_color": 0x00000000,
                "border_width": 1.0,
                "border_radius": 4.0,
                "padding": 5.0
            },
            "Button:hover": {
                "border_color": 0xFFFFA500, # 懸停：橘色邊框高亮
            },
            "Button:pressed": {
                "background_color": 0xFFFFA500, # 按下：品牌橘色
                "color": 0xFF000000,          # 按下：黑色文字
            },
            "Field": {
                "background_color": 0xFF222222,
                "color": 0xFFDDDDDD,
                "border_radius": 2.0,
            },
            "Label": {
                "color": 0xFFDDDDDD,
            }
        }
        
    def build_ui(self):
        """
        建立爆炸圖管理員的 UI 佈局
        採用 VStack 容器，並套用 15px 一致性邊距。
        """
        with ui.VStack(style=self._style, spacing=10, padding=15):
            # --- Header 區塊 ---
            with ui.VStack(spacing=5):
                ui.Label("Exploded View Manager", style={"font_size": 18, "color": 0xFFFFFFFF, "font_weight": "bold"})
                ui.Line(height=2, style={"color": 0xFFFFA500}) # 水平橘色分隔線
            
            ui.Spacer(height=5)
            
            # --- 控制參數區塊 ---
            with ui.HStack(height=24, spacing=10):
                ui.Label("Distance:", width=100)
                ui.FloatField(self._distance_model)
                
            with ui.HStack(height=24, spacing=10):
                ui.Label("Duration (Speed):", width=100)
                ui.FloatField(self._duration_model)
                
            ui.Spacer(height=5)
            
            # --- 方向預設值區塊 (2x3 網格) ---
            ui.Label("Direction Preset:")
            with ui.VGrid(column_count=3, row_height=30, spacing=5):
                # 利用閉包設定指定的方向向量
                def set_dir(x, y, z):
                    self._direction_vector = Gf.Vec3d(x, y, z)
                    
                ui.Button("X", clicked_fn=lambda: set_dir(1, 0, 0))
                ui.Button("Y", clicked_fn=lambda: set_dir(0, 1, 0))
                ui.Button("Z", clicked_fn=lambda: set_dir(0, 0, 1))
                ui.Button("XY", clicked_fn=lambda: set_dir(1, 1, 0))
                ui.Button("XZ", clicked_fn=lambda: set_dir(1, 0, 1))
                ui.Button("YZ", clicked_fn=lambda: set_dir(0, 1, 1))
                
            ui.Spacer(height=10)
            
            # --- 主要動作切換按鈕 ---
            self._action_button = ui.Button(
                "EXECUTE EXPLODE",
                height=40,
                clicked_fn=self._toggle_action,
                style={
                    "font_size": 16,
                    "font_weight": "bold",
                    "background_color": 0xFF444444,
                    "color": 0xFFFFFFFF,
                    "border_radius": 4.0
                }
            )

    def _toggle_action(self):
        """
        處理主要按鈕點擊事件，切換「爆炸」與「合併」狀態。
        """
        self._is_exploded = not self._is_exploded
        
        # 根據狀態更新按鈕的視覺與文字
        if self._is_exploded:
            self._action_button.text = "RESET TO MERGE"
            self._action_button.set_style({
                "font_size": 16,
                "font_weight": "bold",
                "background_color": 0xFFFFA500, # Active: 實心品牌橘色
                "color": 0xFF000000,          # Active: 黑色文字
                "border_radius": 4.0
            })
            self._start_animation(merge=False)
        else:
            self._action_button.text = "EXECUTE EXPLODE"
            self._action_button.set_style({
                "font_size": 16,
                "font_weight": "bold",
                "background_color": 0xFF444444, # 預設: 深灰色
                "color": 0xFFFFFFFF,
                "border_radius": 4.0
            })
            self._start_animation(merge=True)

    def _get_translation_op(self, xformable: UsdGeom.Xformable):
        """
        安全地取得或新增 xformOp:translate
        此設計不破壞現有 USD 的 Transform 堆疊 (Translate, Rotate, Scale 等順序)。
        
        Args:
            xformable (UsdGeom.Xformable): 目標 prim 的 Xformable 介面
        Returns:
            UsdGeom.XformOp: 處理位移的操作物件
        """
        ops = xformable.GetOrderedXformOps()
        for op in ops:
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                return op
                
        # 若堆疊中缺少 TranslateOp，則安全地為其新增一個
        return xformable.AddTranslateOp()

    def _start_animation(self, merge: bool):
        """
        啟動非同步動畫引擎。若有正在進行的動畫則將其取消以避免衝突。
        """
        if self._animation_task and not self._animation_task.done():
            self._animation_task.cancel()
            
        self._animation_task = asyncio.ensure_future(self._animate_prims(merge))

    async def _animate_prims(self, merge: bool):
        """
        核心動畫引擎：
        動態擷取當前選取物件，並套用 Ease-Out 緩動公式計算插值位移。
        運用 next_update_async() 確保 UI 不會被阻塞。
        """
        context = omni.usd.get_context()
        stage = context.get_stage()
        if not stage:
            return
            
        # 動態取得當前選取的 prim 路徑
        selection = context.get_selection().get_selected_prim_paths()
        if not selection:
            print("[ZinExplodedViewModule] 警告: 尚未選取任何物件。")
            return
            
        distance = self._distance_model.as_float
        duration = self._duration_model.as_float
        # 確保指定的方向向量為單位向量
        direction = self._direction_vector.GetNormalized()
        
        anim_data = []
        
        # 收集每個選取物件的動畫起點與終點
        for index, path in enumerate(selection):
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue
                
            xformable = UsdGeom.Xformable(prim)
            if not xformable:
                continue
                
            trans_op = self._get_translation_op(xformable)
            current_val = trans_op.Get()
            if current_val is None:
                current_val = Gf.Vec3d(0.0, 0.0, 0.0)
                
            # 若為初次互動，先將原始位置存檔，以便 Merge 時可以完美歸位
            if path not in self._original_translations:
                self._original_translations[path] = current_val
                
            start_pos = current_val
            if merge:
                # 合併 (Merge) 模式：目標位置為最初記錄的原始位置
                end_pos = self._original_translations.get(path, Gf.Vec3d(0.0, 0.0, 0.0))
            else:
                # 爆炸 (Explode) 模式：計算累加位移，防止零件重疊
                # 公式: BaseDistance * (Index + 1)
                orig_pos = self._original_translations.get(path, Gf.Vec3d(0.0, 0.0, 0.0))
                offset = direction * (distance * (index + 1))
                end_pos = orig_pos + offset
                
            anim_data.append((trans_op, start_pos, end_pos))
            
        if not anim_data:
            return
            
        # 執行非同步動畫迴圈
        start_time = time.time()
        while True:
            elapsed = time.time() - start_time
            # 防止除以零錯誤，若 duration <= 0 則瞬間完成
            t = elapsed / duration if duration > 0 else 1.0
            t = min(max(t, 0.0), 1.0)
            
            # 套用 Ease-Out 緩動公式: 1 - (1 - t)^2
            ease_t = 1.0 - (1.0 - t)**2
            
            # 更新所有選取物件的位置
            for trans_op, start_pos, end_pos in anim_data:
                current_pos = start_pos + (end_pos - start_pos) * ease_t
                trans_op.Set(current_pos)
                
            # 釋放控制權並等待下一個畫面更新，維持 UI 流暢
            await omni.kit.app.get_app().next_update_async()
            
            # 若動畫時間已滿，結束迴圈
            if t >= 1.0:
                break
