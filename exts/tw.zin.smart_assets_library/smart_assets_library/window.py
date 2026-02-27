import os
import asyncio
import json

import omni.ui as ui
import omni.client

from .model import CategoryItem, CategoryModel, SmartAsset
from .smart_asset_delegate import SmartAssetPropertyDelegate

# ── 標籤雲生成器 (Tag Cloud) 升級為互動按鈕 ────────────────────────────────
class ZinTagCloud:
    def __init__(self, max_width=230, tag_click_fn=None):
        self.max_width = max_width
        self.container = ui.VStack(spacing=6)
        self.tag_click_fn = tag_click_fn

    def update_tags(self, tags: list):
        self.container.clear()
        if not tags:
            return

        with self.container:
            current_row = ui.HStack(height=ui.Pixel(22), spacing=6)
            current_w = 0

            for tag in tags:
                tag_w = len(tag) * 7 + 16 
                if current_w + tag_w > self.max_width and current_w > 0:
                    with current_row:
                        ui.Spacer() 
                    current_row = ui.HStack(height=ui.Pixel(22), spacing=6)
                    current_w = 0

                with current_row:
                    # 🔥 100% 還原官方：使用 ui.Button 達成 Hover 與點擊效果
                    ui.Button(
                        tag,
                        width=ui.Pixel(tag_w),
                        height=ui.Pixel(22),
                        style={
                            "background_color": 0xFF3A3A3A,
                            "background_color:hovered": 0xFF555555, # Hover 變亮
                            "background_color:pressed": 0xFF222222,
                            "border_radius": 4,
                            "color": 0xFFDDDDDD,
                            "font_size": 12,
                            "margin": 0,
                            "padding": 0
                        },
                        clicked_fn=lambda t=tag: self.tag_click_fn(t) if self.tag_click_fn else None
                    )
                current_w += (tag_w + 6)

            with current_row:
                ui.Spacer()

# ── Shared Button Helper ───────────────────────────────────────────────────
def _zin_btn(label: str, width: int, clicked_fn, color: int = 0xFF3A3A3A):
    btn = ui.Button(
        label,
        width=ui.Pixel(width),
        height=ui.Pixel(24),
        style={
            "background_color": color,
            "border_radius": 4,
            "color": 0xFFDDDDDD,
            "font_size": 12,
        },
        clicked_fn=clicked_fn,
    )
    return btn


# ── TreeView Delegate ─────────────────────────────────────────────────────────
class LibraryDelegate(ui.AbstractItemDelegate):
    ROW_H      = 22 
    INDENT_W   = 16 
    ICON_W     = 16 
    ICON_COLOR = 0xFFDDA830 
    ICON_OPEN  = 0xFFEECC66 

    def __init__(self):
        super().__init__()
        self._tree_view = None

    def set_tree_view(self, tv):
        self._tree_view = tv

    def build_widget(self, model, item, column_id, level, expanded):
        if column_id != 0 or item is None:
            return

        name         = item.name_model.as_string
        has_children = bool(model.get_item_children(item))
        icon_svg     = "${glyphs}/folder_open.svg" if expanded else "${glyphs}/folder.svg"
        icon_tint    = self.ICON_OPEN if expanded else self.ICON_COLOR

        with ui.HStack(height=ui.Pixel(self.ROW_H), spacing=6, alignment=ui.Alignment.CENTER):
            if level > 0:
                ui.Spacer(width=ui.Pixel(level * self.INDENT_W))

            if has_children:
                with ui.ZStack(width=ui.Pixel(16), height=ui.Pixel(16)):
                    with ui.Placer(offset_x=2, offset_y=2):
                        ui.Rectangle(width=ui.Pixel(12), height=ui.Pixel(12), style={"background_color": 0xFF808080, "border_radius": 2})
                    with ui.Placer(offset_x=4, offset_y=7):
                        ui.Rectangle(width=ui.Pixel(8), height=ui.Pixel(2), style={"background_color": 0xFF2A2A2A})
                    if not expanded:
                        with ui.Placer(offset_x=7, offset_y=4):
                            ui.Rectangle(width=ui.Pixel(2), height=ui.Pixel(8), style={"background_color": 0xFF2A2A2A})
                    click_area = ui.Rectangle(style={"background_color": 0x00000000})
                    click_area.set_mouse_pressed_fn(
                        lambda x, y, b, m, _i=item:
                            self._tree_view and b == 0 and
                            self._tree_view.set_expanded(_i, not self._tree_view.is_expanded(_i), False)
                    )
            else:
                ui.Spacer(width=ui.Pixel(16))

            ui.Image(icon_svg, width=ui.Pixel(self.ICON_W), height=ui.Pixel(self.ICON_W), alignment=ui.Alignment.CENTER, fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT, style={"color": icon_tint})
            ui.Label(name, alignment=ui.Alignment.LEFT_CENTER, style={"font_size": 13, "color": 0xFFCCCCCC})


class ZinSplitter:
    """Custom interactive splitter for resizing adjacent panels in omni.ui."""
    def __init__(self, is_left=True):
        self.target_frame = None
        self.is_left = is_left
        self.start_width = 0
        self.start_x = 0
        self.is_dragging = False

        # An invisible hitbox that renders a blue line when hovered/dragged
        self.hitbox = ui.Rectangle(
            width=ui.Pixel(4),
            style={
                "background_color": 0xFF333333,
                "background_color:hovered": 0xFFD7881F, # Omniverse Blue
                "cursor": "size_we"
            }
        )
        self.hitbox.set_mouse_pressed_fn(self._on_pressed)
        self.hitbox.set_mouse_moved_fn(self._on_moved)
        self.hitbox.set_mouse_released_fn(self._on_released)

    def set_target(self, frame):
        self.target_frame = frame

    def _on_pressed(self, x, y, b, m):
        if b == 0 and self.target_frame:
            self.is_dragging = True
            self.start_width = self.target_frame.computed_width
            self.start_x = x

    def _on_moved(self, x, y, b, m):
        if self.is_dragging and self.target_frame:
            if self.is_left:
                new_width = self.start_width + (x - self.start_x)
            else:
                new_width = self.start_width - (x - self.start_x)
            
            new_width = max(150, min(new_width, 800))
            self.target_frame.width = ui.Pixel(new_width)

    def _on_released(self, x, y, b, m):
        if b == 0:
            self.is_dragging = False


# ── Main Window ─────────────────────────────────────────────────────────────
class SmartAssetsLibraryWindow(ui.Window):
    def __init__(self, title: str, **kwargs):
        super().__init__(title, **kwargs)

        self.mixed_root_paths: list[str] = []
        self._category_model = CategoryModel()
        self._delegate = LibraryDelegate()
        self._file_picker = None

        self._asset_grid_container = None 
        self._grid_building = False 
        self._current_usd_files: list = [] 
        self._filtered_usd_files: list = [] # 搜尋過濾用

        self._detail_name_lbl  = None 
        self._detail_thumb_img = None 
        
        # 動態生成的面板容器與委派
        self._tag_cloud = None 
        self._property_view_container = None
        self._property_delegate = None

        self._setup_ui()
        self._refresh_library()

    def _setup_ui(self):
        with self.frame:
            with ui.VStack(spacing=0):
                # Top Bar
                with ui.HStack(height=36, spacing=6, padding=6):
                    ui.Label("Zin Library", width=ui.Pixel(72), style={"color": 0xFF888888, "font_size": 13, "font_weight": "bold"})
                    
                    self._path_field = ui.StringField(style={"background_color": 0xFF1A1A1A, "border_radius": 4, "font_size": 13})
                    
                    ui.Spacer(width=6)
                    self._search_field = ui.StringField(style={"background_color": 0xFF2A2A2A, "border_radius": 4, "font_size": 13, "color": 0xFFDDDDDD})
                    self._search_field.model.set_value("")
                    self._search_field.model.add_value_changed_fn(self._on_search_changed)
                    # 加入一點提示文字的效果
                    ui.Label("Search", width=0, style={"color": 0xFF666666, "font_size": 12})
                    
                    ui.Spacer(width=6)
                    _zin_btn("Browse", 56, self._on_browse)
                    _zin_btn("Load",   56, self._on_load, color=0xFF1F5C2E)

                ui.Separator(height=1, style={"color": 0x33FFFFFF})

                # Main Content
                with ui.HStack():
                    # LEFT: Tree View
                    self._left_panel = ui.ScrollingFrame(width=ui.Percent(30), style={"background_color": 0xFF1E1E1E}, horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF)
                    with self._left_panel:
                        self._tree_view = ui.TreeView(self._category_model, delegate=self._delegate, root_visible=False, header_visible=False, column_widths=[ui.Fraction(1)])
                        self._tree_view.set_selection_changed_fn(self._on_selection_changed)
                        self._tree_view.set_mouse_double_clicked_fn(self._on_tree_double_click)
                    self._delegate.set_tree_view(self._tree_view)

                    # --- Left Splitter ---
                    left_splitter = ZinSplitter(is_left=True)
                    left_splitter.set_target(self._left_panel)

                    # MIDDLE: Asset Grid
                    self._grid_scroll = ui.ScrollingFrame(style={"background_color": 0xFF181818}, horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF)
                    self._grid_scroll.set_computed_content_size_changed_fn(self._on_grid_resized)
                    with self._grid_scroll:
                        self._asset_grid_container = ui.VStack(spacing=10, padding=10)
                        with self._asset_grid_container:
                            self._grid_placeholder("Select a folder")

                    # --- Right Splitter ---
                    right_splitter = ZinSplitter(is_left=False)

                    # RIGHT: Detail Panel
                    self._right_panel = ui.ScrollingFrame(width=ui.Pixel(260), style={"background_color": 0xFF232323}, horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF)
                    with self._right_panel:
                        with ui.VStack(spacing=10, padding=10):
                            self._detail_thumb_img = ui.Image("", height=ui.Pixel(200), fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT, style={"color": 0xFF888888})
                            
                            ui.Separator(height=1, style={"color": 0x33FFFFFF})
                            self._detail_name_lbl = ui.Label("Select an asset", word_wrap=True, alignment=ui.Alignment.CENTER, style={"font_size": 14, "color": 0xFFDDDDDD, "font_weight": "bold"})
                            
                            with ui.CollapsableFrame("Behaviors", collapsed=False, height=0):
                                self._behaviors_container = ui.VStack(spacing=8, padding=6)
                            
                            with ui.CollapsableFrame("Asset info", collapsed=False, height=0):
                                self._asset_info_container = ui.VStack(spacing=6, padding=6)

                            with ui.CollapsableFrame("Tags", collapsed=False, height=0):
                                with ui.VStack(spacing=8, padding=6):
                                    self._tag_cloud = ZinTagCloud(max_width=230)
                                    
                            ui.Spacer()
                    
                    # Bind right panel target after creation
                    right_splitter.set_target(self._right_panel)

    # ── Search & Filter ───────────────────────────────────────────────────
    def _on_tag_click(self, tag_text):
        self._search_field.model.set_value(tag_text)

    def _on_search_changed(self, model):
        search_text = model.get_value_as_string().lower().strip()
        if not search_text:
            self._filtered_usd_files = self._current_usd_files
        else:
            self._filtered_usd_files = [
                (fname, fpath) for (fname, fpath) in self._current_usd_files
                if search_text in fname.lower()
            ]
        self._build_asset_grid(self._filtered_usd_files)

    @staticmethod
    def _grid_placeholder(text: str):
        with ui.VStack(alignment=ui.Alignment.CENTER):
            ui.Spacer()
            ui.Label(text, alignment=ui.Alignment.CENTER, style={"color": 0xFF555555, "font_size": 13})
            ui.Spacer()

    def _on_browse(self):
        try:
            from omni.kit.widget.filebrowser import FileBrowserWidget  # noqa
            from omni.kit.window.filepicker import FilePickerDialog
            def _apply(filename, path):
                self._path_field.model.set_value(path.replace("\\", "/"))
                self._file_picker.hide()
                self._on_load()
            self._file_picker = FilePickerDialog("Select Folder", click_apply_handler=_apply)
            self._file_picker.show()
        except Exception as e:
            pass

    def _on_load(self):
        raw = self._path_field.model.get_value_as_string().strip()
        path = raw.replace("\\", "/").rstrip("/")
        if path and path not in self.mixed_root_paths:
            self.mixed_root_paths.append(path)
            self._refresh_library()

    def _refresh_library(self):
        asyncio.ensure_future(self._load_categories_async())

    async def _load_categories_async(self):
        all_roots = []
        loop = asyncio.get_event_loop()
        for path in self.mixed_root_paths:
            clean = path.replace("\\", "/").rstrip("/")
            name  = os.path.basename(clean)
            node  = CategoryItem(name, clean)
            all_roots.append(node)
            await self._build_tree_recursive(clean, node, loop)
        self._category_model.set_nodes(all_roots)

    async def _build_tree_recursive(self, path: str, parent: CategoryItem, loop):
        result, entries = await loop.run_in_executor(None, omni.client.list, path)
        if result != omni.client.Result.OK: return
        for entry in entries:
            if (entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN) and not entry.relative_path.startswith("."):
                full = f"{path}/{entry.relative_path}"
                child = CategoryItem(entry.relative_path, full)
                parent.children.append(child)
                await self._build_tree_recursive(full, child, loop)

    def _on_selection_changed(self, selections):
        if selections: asyncio.ensure_future(self._load_folder_assets_async(selections[0].full_path))

    def _on_tree_double_click(self, x, y, button, modifier):
        if button != 0: return
        sels = self._tree_view.selection
        if sels:
            item = sels[0]
            self._tree_view.set_expanded(item, not self._tree_view.is_expanded(item), False)

    async def _load_folder_assets_async(self, folder_path: str):
        loop = asyncio.get_event_loop()
        result, entries = await loop.run_in_executor(None, omni.client.list, folder_path)
        usd_ext   = {".usd", ".usda", ".usdc", ".usdz"}
        usd_files = []
        if result == omni.client.Result.OK:
            for entry in entries:
                name = entry.relative_path
                if os.path.splitext(name)[1].lower() in usd_ext:
                    usd_files.append((name, f"{folder_path}/{name}"))
        self._current_usd_files = usd_files
        self._build_asset_grid(usd_files)

    def _on_grid_resized(self):
        if self._grid_building or not self._current_usd_files: return
        self._build_asset_grid(self._current_usd_files)

    def _build_asset_grid(self, usd_files: list):
        if self._asset_grid_container is None or self._grid_building: return
        self._grid_building = True
        try:
            self._asset_grid_container.clear()
            CARD_W, CARD_H, IMG_SIZE, PADDING, SPACING = 140, 160, 110, 10, 10
            grid_w = self._grid_scroll.computed_content_width
            if grid_w < CARD_W: grid_w = 480
            COLS = max(1, int((grid_w - PADDING * 2 + SPACING) / (CARD_W + SPACING)))

            with self._asset_grid_container:
                if not usd_files:
                    self._grid_placeholder("No USD assets found")
                    return
                rows = [usd_files[i:i + COLS] for i in range(0, len(usd_files), COLS)]
                for row in rows:
                    with ui.HStack(height=CARD_H, spacing=SPACING):
                        for fname, fpath in row:
                            self._build_asset_card(fname, fpath, CARD_W, CARD_H, IMG_SIZE)
                        for _ in range(COLS - len(row)):
                            ui.Spacer(width=CARD_W)
        finally:
            self._grid_building = False

    def _build_asset_card(self, fname: str, fpath: str, card_w: int, card_h: int, img_size: int):
        base       = os.path.splitext(fname)[0]
        parent_dir = os.path.dirname(fpath)

        candidate  = f"{parent_dir}/{base}.png"
        is_local   = ":" in parent_dir or parent_dir.startswith("/")
        thumb = candidate if is_local and os.path.isfile(candidate) and os.path.getsize(candidate) > 0 else "${glyphs}/file.svg"

        def _drag_fn(p=fpath):
            return p

        def _click_fn(x, y, btn, mod, n=fname, p=fpath, t=thumb, bd=base):
            if btn == 0:
                if self._detail_name_lbl: self._detail_name_lbl.text = bd
                if self._detail_thumb_img: self._detail_thumb_img.source_url = t 

                # Instantiate the Data-Driven SmartAsset
                asset = SmartAsset(main_url=p, thumbnail=t, name=bd)

                json_path = f"{parent_dir}/{bd}.json"
                tags_data = []
                
                if is_local and os.path.exists(json_path):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            json_data = json.load(f)
                            tags_data = json_data.pop("tags", [])
                            # Add JSON custom properties directly to asset for the delegate to render
                            display_keys = {"version": "Version", "author": "Author", "description": "Desc"}
                            for j_key, label_name in display_keys.items():
                                val = json_data.get(j_key, "")
                                if val:
                                    asset.user_properties[label_name] = val
                    except Exception:
                        pass

                # Pre-update Tag Cloud so the delegate displays the latest tags 
                if self._tag_cloud:
                    self._tag_cloud.update_tags(tags_data)

                # Callback triggered when USD metadata is loaded asynchronously
                def _on_metadata_loaded(loaded_asset):
                    if self._property_view_container:
                        self._property_view_container.clear()
                        with self._property_view_container:
                            if self._property_delegate:
                                self._property_delegate.show_asset(loaded_asset)

                # Show Loading State immediately
                if self._property_view_container:
                    self._property_view_container.clear()
                    with self._property_view_container:
                        if self._property_delegate:
                            self._property_delegate.show_asset(asset)

                # Begin async extraction
                asset.add_loaded_callback(_on_metadata_loaded)
                asset.load_metadata_async()

        with ui.Frame(width=card_w, height=card_h):
            with ui.ZStack():
                ui.Rectangle(style={"background_color": 0xFF2A2A2A, "border_radius": 4, "border_width": 1, "border_color": 0xFF3A3A3A})
                ui.Rectangle(style={"background_color": 0x00000000, "background_color:hovered": 0x18FFFFFF, "border_radius": 4})
                with ui.VStack(spacing=4, padding=6, alignment=ui.Alignment.CENTER):
                    with ui.Frame(width=img_size, height=img_size, alignment=ui.Alignment.CENTER):
                        ui.Image(thumb, width=img_size, height=img_size, fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT, style={"color": 0xFFAAAAAA})
                    ui.Label(base, alignment=ui.Alignment.CENTER, word_wrap=True, style={"color": 0xFFCCCCCC, "font_size": 12})
                hitbox = ui.Rectangle(style={"background_color": 0x00000000})
                hitbox.set_mouse_pressed_fn(_click_fn)
                hitbox.set_drag_fn(_drag_fn)