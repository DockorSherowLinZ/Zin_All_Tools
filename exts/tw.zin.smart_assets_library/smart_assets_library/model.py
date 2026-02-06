import omni.ui as ui
import omni.client

class CategoryItem(ui.AbstractItem):
    def __init__(self, text, path):
        super().__init__()
        self.name_model = ui.SimpleStringModel(text)
        self.full_path = path
        self.children = []

class CategoryModel(ui.AbstractItemModel):
    def __init__(self):
        super().__init__()
        self.root_nodes = []

    def set_nodes(self, nodes):
        """用於異步更新資料"""
        self.root_nodes = nodes
        self._item_changed(None)

    def get_item_children(self, item):
        return item.children if item else self.root_nodes

    def get_item_value_model(self, item, column_id):
        return item.name_model