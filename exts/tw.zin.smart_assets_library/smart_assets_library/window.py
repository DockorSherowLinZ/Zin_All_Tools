import asyncio
import omni.ui as ui
import omni.client
from .model import CategoryModel, CategoryItem

class SmartAssetsLibraryWindow(ui.Window):
    def __init__(self, title, **kwargs):
        super().__init__(title, **kwargs)
        
        # 1. 設定混合讀取路徑 (可依需求修改)
        self.mixed_root_paths = [
            "C:/Your/Local/Assets",                      # 本機路徑
            "omniverse://localhost/Library/Assets"      # Nucleus 路徑
        ]
        
        # 2. 初始化 UI 與模型
        self._category_model = CategoryModel()
        self._setup_ui()
        
        # 3. 啟動異步載入任務
        asyncio.ensure_future(self._load_categories_async())

    def _setup_ui(self):
        """構建視窗布局"""
        with self.frame:
            with ui.HStack():
                # --- 左側：分類導覽列 ---
                with ui.ScrollingFrame(width=250, name="left_panel", style={"background_color": 0xFF232323}):
                    with ui.VStack(spacing=5):
                        ui.Label("  LIBRARY", height=40, style={"font_size": 16, "color": 0xFF888888})
                        
                        # TreeView 設置
                        self._tree_view = ui.TreeView(
                            self._category_model,
                            root_visible=False,
                            header_visible=False,
                            style={"TreeView.Item:selected": {"background_color": 0x44FFFFFF}}
                        )
                        # 綁定選取事件
                        self._tree_view.set_selection_changed_fn(self._on_selection_changed)

                # --- 右側：預覽與屬性區 (暫留位置) ---
                with ui.Frame(name="right_panel"):
                    with ui.VStack():
                        self.path_label = ui.Label("請選擇左側分類", alignment=ui.Alignment.CENTER)
                        ui.Spacer()

    async def _load_categories_async(self):
        """異步讀取資料夾的核心邏輯"""
        all_root_nodes = []
        loop = asyncio.get_event_loop()
        
        for path in self.mixed_root_paths:
            source_tag = "[LOCAL]" if ":" in path else "[NUCLEUS]"
            root_node = CategoryItem(f"{source_tag} ALL", path)
            all_root_nodes.append(root_node)
            
            # 在背景線程執行同步的 omni.client.list 以免卡住 UI
            result, entries = await loop.run_in_executor(None, omni.client.list, path)
            
            if result == omni.client.Result.OK:
                for entry in entries:
                    # 檢查是否為資料夾
                    if entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
                        if not entry.relative_path.startswith("."):
                            full_path = f"{path.rstrip('/')}/{entry.relative_path}"
                            # 建立子節點並存入 root_node
                            node = CategoryItem(entry.relative_path.upper(), full_path)
                            root_node.children.append(node)
            
            # 沒讀完一個 root 就通知 UI 更新一次 (漸進式顯示)
            self._category_model.set_nodes(all_root_nodes)

    def _on_selection_changed(self, selections):
        """點擊 TreeView 項目時的回呼"""
        if not selections:
            return
        
        selected_item = selections[0]
        self.path_label.text = f"當前路徑: {selected_item.full_path}"
        print(f"Zin Asset Library - Selected: {selected_item.full_path}")

    def destroy(self):
        """清理資源"""
        super().destroy()