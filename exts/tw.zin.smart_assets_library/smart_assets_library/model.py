import omni.ui as ui

class CategoryItem(ui.AbstractItem):
    """代表樹狀圖中的單一節點"""
    def __init__(self, text, path):
        super().__init__()
        # 使用 SimpleStringModel 處理文字顯示
        self.name_model = ui.SimpleStringModel(text)
        self.full_path = path
        self.children = []

class CategoryModel(ui.AbstractItemModel):
    """管理樹狀圖資料的核心模型"""
    def __init__(self):
        super().__init__()
        self.root_nodes = []

    def set_nodes(self, nodes):
        """設定根節點並通知 UI 全面刷新"""
        self.root_nodes = nodes
        self._item_changed(None) # Rule: 通知根節點變更，觸發重繪

    def get_item_children(self, item):
        """Rule: 回傳子節點列表。若列表非空，UI 會自動顯示展開箭頭"""
        return item.children if item else self.root_nodes

    def get_item_value_model_count(self, item):
        """Rule 2: Kit 109 必備！告訴系統每一列有 1 個欄位"""
        return 1

    def get_item_value_model(self, item, column_id):
        """回傳指定欄位的模型"""
        if column_id == 0:
            return item.name_model
        return None