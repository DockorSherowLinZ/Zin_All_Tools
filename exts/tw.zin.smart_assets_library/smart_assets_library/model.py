import carb
import omni.ui as ui

class CategoryItem(ui.AbstractItem):
    """Represents a single node in the tree"""
    def __init__(self, text, path):
        super().__init__()
        # 使用 SimpleStringModel 處理文字顯示
        self.name_model = ui.SimpleStringModel(text)
        self.full_path = path
        self.children = []

class CategoryModel(ui.AbstractItemModel):
    """Core model managing tree data"""
    def __init__(self):
        super().__init__()
        self.root_nodes = []

    def set_nodes(self, nodes):
        """Set root node and notify UI to refresh completely"""
        self.root_nodes = nodes
        self._item_changed(None) # Rule: 通知根節點變更，觸發重繪

    def get_item_children(self, item):
        """Rule: Return child nodes list. If not empty, UI automatically shows expand arrow"""
        return item.children if item else self.root_nodes

    def get_item_value_model_count(self, item):
        """Rule 2: Essential for Kit 109! Tell system each row has 1 column"""
        return 1

    def get_item_value_model(self, item, column_id):
        """Return the model for the specified column"""
        if column_id == 0:
            return item.name_model
        return None

import asyncio
from pxr import Usd
import omni.client

class SmartAsset:
    """
    Data-driven 智慧資產模型，封裝實體 USD 以提供非同步讀取與屬性提取。
    """
    def __init__(self, main_url: str, thumbnail: str, name: str):
        self.main_url = main_url
        self.thumbnail = thumbnail
        self.name = name
        
        self.metadata_loaded = False
        self.variant_sets = {}
        self.user_properties = {}
        self.on_metadata_loaded_callbacks = []

    def load_metadata_async(self):
        """Trigger async read of USD properties, preventing multiple calls"""
        if self.metadata_loaded:
            return
        asyncio.ensure_future(self._extract_usd_data_async())

    async def _extract_usd_data_async(self):
        loop = asyncio.get_event_loop()
        try:
            # 1. Pre-check: Verify if the file exists using omni.client
            result, _ = await omni.client.stat_async(self.main_url)
            if result != omni.client.Result.OK:
                carb.log_warn(f"[SmartAsset Explorer] Skip loading, file not found or inaccessible: {self.main_url}")
                return

            def _open_stage():
                # 2. Fix USD Space Issue: explicitly encode spaces for Usd.Stage.Open
                safe_url = self.main_url.replace(" ", "%20")
                return Usd.Stage.Open(safe_url, Usd.Stage.LoadNone)
            
            stage = await loop.run_in_executor(None, _open_stage)
            
            if stage:
                root_prim = stage.GetDefaultPrim() or stage.GetPseudoRoot()
                if root_prim:
                    if root_prim.HasVariantSets():
                        vsets = root_prim.GetVariantSets()
                        for vset_name in vsets.GetNames():
                            vset = vsets.GetVariantSet(vset_name)
                            self.variant_sets[vset_name] = {
                                "options": vset.GetVariantNames(),
                                "current": vset.GetVariantSelection()
                            }
                    
                    for prop in root_prim.GetAuthoredProperties():
                        if prop.IsCustom():
                            self.user_properties[prop.GetName()] = prop.Get()
                            
        except Exception as e:
            # 3. Graceful degradation without spamming raw tracebacks as Errors
            carb.log_warn(f"[SmartAsset Explorer] Cannot extract USD metadata for {self.main_url} (File may be empty, invalid syntax, or locked). Message: {e}")
            
        finally:
            self.metadata_loaded = True
            for cb in self.on_metadata_loaded_callbacks:
                cb(self)

    def add_loaded_callback(self, cb):
        if self.metadata_loaded:
            cb(self)
        else:
            self.on_metadata_loaded_callbacks.append(cb)