import omni.ui as ui
import omni.kit.undo
from pxr import Sdf, Usd
import ast

# 統一的樣式字典，用於保持 Omni.ui 原生質感
PROPERTY_STYLES = {
    "FieldLabel": {
        "color": 0xFFCCCCCC,
        "font_size": 12,
        "font_weight": "bold",
    },
    "FieldValue": {
        "color": 0xFFAAAAAA,
        "font_size": 12,
    },
    "ComboBox": {
        "font_size": 12,
    },
    "LoadingLabel": {
        "color": 0xFF888888,
        "font_size": 11,
    }
}

def get_style():
    return PROPERTY_STYLES

class SmartAssetPropertyDelegate:
    """
    資料驅動的 UI 委派器，專責將 SmartAsset 實體內的 USD 屬性動態繪製至 Detail Panel。
    此模式借鑑自 omni.simready.explorer 的 BrowserPropertyDelegate。
    """
    def __init__(self, tag_cloud=None):
        self._tag_cloud = tag_cloud

    def show_asset(self, asset):
        """根據 SmartAsset 的 Metadata 動態重繪畫面"""
        if not asset:
            return

        with ui.VStack(spacing=10, style=get_style()):
            # 1. Asset Info 區塊
            with ui.CollapsableFrame("Asset Info", collapsed=False):
                with ui.VStack(spacing=6, padding=6):
                    self._build_row("Name", asset.name)
                    self._build_row("Path", asset.main_url)
                    
                    if asset.user_properties:
                        ui.Separator(height=2, style={"color": 0x33FFFFFF})
                        for key, val in asset.user_properties.items():
                            self._build_row(key, str(val))

            # 2. Behaviors 區塊 (顯示 VariantSets 如 PhysicsVariant, LoD 等)
            if asset.variant_sets:
                with ui.CollapsableFrame("Behaviors", collapsed=False):
                    with ui.VStack(spacing=6, padding=6):
                        for vset_name, data in asset.variant_sets.items():
                            self._build_variant_row(vset_name, data["options"], data["current"], asset)
            elif not asset.metadata_loaded:
                # 若仍在非同步讀取中
                with ui.CollapsableFrame("Behaviors", collapsed=False):
                    with ui.VStack(spacing=6, padding=6, alignment=ui.Alignment.CENTER):
                        ui.Label("Loading USD Metadata...", name="LoadingLabel", alignment=ui.Alignment.CENTER)
            else:
                # 讀取完成但沒有特殊行為
                with ui.CollapsableFrame("Behaviors", collapsed=False):
                    with ui.VStack(spacing=6, padding=6, alignment=ui.Alignment.CENTER):
                        ui.Label("No behavior variants found.", name="LoadingLabel", alignment=ui.Alignment.CENTER)

            # 3. Tags 區塊
            with ui.CollapsableFrame("Tags", collapsed=False):
                with ui.VStack(spacing=8, padding=6):
                    if self._tag_cloud:
                        # 將之前初始化好的 Tag Cloud 容器掛載到這裡
                        self._tag_cloud.container

    def _build_row(self, label_text, value_text):
        with ui.HStack(height=0, spacing=4):
            ui.Label(f"{label_text}:", width=ui.Pixel(80), alignment=ui.Alignment.LEFT_TOP, name="FieldLabel")
            ui.Label(value_text, word_wrap=True, name="FieldValue")

    def _build_variant_row(self, vset_name, options, current, asset):
        with ui.HStack(height=ui.Pixel(20), spacing=4):
            ui.Label(vset_name, width=ui.Percent(45), name="FieldLabel")
            
            # 對齊當前選中的 Index
            current_idx = 0
            if current in options:
                current_idx = options.index(current)
            else:
                # 預防未載入或未知情況
                if current:
                    options.append(current)
                    current_idx = len(options) - 1
                
            combo = ui.ComboBox(current_idx, *options, name="ComboBox")
            model = combo.model
            
            def on_variant_changed(m, item, var=vset_name, opts=options, ast=asset):
                idx = m.get_item_value_model().as_int
                selected_opt = opts[idx]
                print(f"[SmartAsset Explorer] Applying variant '{selected_opt}' for '{var}' to {ast.name}")
                
                # 若需要真實修改對應的實體 USD 檔案，需透過 Undo Group 包裝
                with omni.kit.undo.group():
                    try:
                        import omni.client
                        formatted_url = omni.client.normalize_url(ast.main_url)
                        stage = Usd.Stage.Open(formatted_url)
                        if stage:
                            prim = stage.GetDefaultPrim() or stage.GetPseudoRoot()
                            if prim.HasVariantSets():
                                vsets = prim.GetVariantSets()
                                vset = vsets.GetVariantSet(var)
                                vset.SetVariantSelection(selected_opt)
                                stage.Save()
                                # 同步更新 Asset 的記憶體狀態
                                ast.variant_sets[var]["current"] = selected_opt
                                print(f"[SmartAsset Explorer] Successfully updated USD file {ast.main_url}")
                    except Exception as e:
                        print(f"[SmartAsset Explorer] Failed to save variant {e}")

            model.add_item_changed_fn(on_variant_changed)
