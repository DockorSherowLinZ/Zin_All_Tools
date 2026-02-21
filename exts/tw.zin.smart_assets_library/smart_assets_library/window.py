"""
tw.zin.smart_assets_library  ─  window.py
==========================================
3-pane SimReady-style asset browser:
  Left   : TreeView (folder navigation, 30 %)
  Middle : Asset Grid (responsive columns, scrollable)
  Right  : Detail Panel (MVVM, 260 px fixed)

Features
--------
* MVVM detail panel via ui.SimpleStringModel
* Drag-and-drop: set_drag_fn returns USD path string
  → triggers Omniverse's native UsdFileDropDelegate
* Double-click tree row to expand / collapse
* Responsive column count via computed_content_width
* Re-entry guard (_grid_building) prevents infinite resize loop
* PNG thumbnail existence + size check (avoids gpu.foundation spam)
"""

import os
import asyncio

import omni.ui as ui
import omni.client

from .model import CategoryItem, CategoryModel

# ── Shared Button Helper (inline, no external dep) ─────────────────────────
def _zin_btn(label: str, width: int, clicked_fn, color: int = 0xFF3A3A3A):
    """Minimal styled button."""
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
    """
    TreeView Delegate — 仿 Omniverse Content Browser 樣式。
    build_widget 整合縮排、展開鈕（ZStack Rectangle）、資料夾圖示、文字。
    """
    ROW_H      = 22          # 列高（px）
    INDENT_W   = 16          # 每層縮排（px）
    ICON_W     = 16          # 資料夾圖示大小（px）
    ICON_COLOR = 0xFFDDA830  # 琥珀色 folder tint
    ICON_OPEN  = 0xFFEECC66  # 展開時較亮

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

        with ui.HStack(height=ui.Pixel(self.ROW_H), spacing=6,
                       alignment=ui.Alignment.CENTER):

            # 1. Indentation
            if level > 0:
                ui.Spacer(width=ui.Pixel(level * self.INDENT_W))

            # 2. Expander (14×14 ZStack, only if has children)
            if has_children:
                with ui.ZStack(width=ui.Pixel(16), height=ui.Pixel(16)):
                    # 第一層：底層灰色方塊 (大小 12x12，放在 16x16 的正中間 -> 偏移量 2, 2)
                    with ui.Placer(offset_x=2, offset_y=2):
                        ui.Rectangle(
                            width=ui.Pixel(12), height=ui.Pixel(12),
                            style={"background_color": 0xFF808080, "border_radius": 2}
                        )
                    
                    # 第二層：減號橫線 (大小 8x2，放在 16x16 的正中間 -> 偏移量 4, 7)
                    with ui.Placer(offset_x=4, offset_y=7):
                        ui.Rectangle(
                            width=ui.Pixel(8), height=ui.Pixel(2),
                            style={"background_color": 0xFF2A2A2A}
                        )
                    
                    # 第三層：加號直線 (大小 2x8，放在 16x16 的正中間 -> 偏移量 7, 4)
                    if not expanded:
                        with ui.Placer(offset_x=7, offset_y=4):
                            ui.Rectangle(
                                width=ui.Pixel(2), height=ui.Pixel(8),
                                style={"background_color": 0xFF2A2A2A}
                            )
                    
                    # 頂層：透明點擊區 (滿版 16x16)
                    click_area = ui.Rectangle(style={"background_color": 0x00000000})
                    click_area.set_mouse_pressed_fn(
                        lambda x, y, b, m, _i=item:
                            self._tree_view and b == 0 and
                            self._tree_view.set_expanded(
                                _i, not self._tree_view.is_expanded(_i), False
                            )
                    )
            else:
                ui.Spacer(width=ui.Pixel(16))

            # 3. Folder Icon
            ui.Image(
                icon_svg,
                width=ui.Pixel(self.ICON_W), height=ui.Pixel(self.ICON_W),
                alignment=ui.Alignment.CENTER,
                fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                style={"color": icon_tint},
            )

            # 4. Text Label
            ui.Label(
                name,
                alignment=ui.Alignment.LEFT_CENTER,
                style={"font_size": 13, "color": 0xFFCCCCCC},
            )


# ── Main Window ─────────────────────────────────────────────────────────────
class SmartAssetsLibraryWindow(ui.Window):
    """
    Smart Assets Library – master-detail asset browser.
    """

    # ── Construction ──────────────────────────────────────────────────────
    def __init__(self, title: str, **kwargs):
        super().__init__(title, **kwargs)

        # Data
        self.mixed_root_paths: list[str] = []

        # TreeView
        self._category_model = CategoryModel()
        self._delegate = LibraryDelegate()
        self._file_picker = None

        # Asset grid state
        self._asset_grid_container = None   # VStack rebuilt on folder select
        self._grid_building = False          # re-entry guard
        self._current_usd_files: list = []  # cache for resize rebuild

        # Detail Panel widget refs (updated directly on card click)
        self._detail_name_lbl  = None   # ui.Label ref
        self._detail_path_lbl  = None   # ui.Label ref
        self._detail_thumb_img = None   # ui.Image model (SimpleStringModel)
        self._detail_thumbnail_url = ui.SimpleStringModel("")  # for ui.Image

        self._setup_ui()
        self._refresh_library()

    # ── UI Construction ────────────────────────────────────────────────────
    def _setup_ui(self):
        with self.frame:
            with ui.VStack(spacing=0):

                # ── Top Bar ──────────────────────────────────────────────
                with ui.HStack(height=36, spacing=6, padding=6):
                    ui.Label(
                        "Zin Library",
                        width=ui.Pixel(72),
                        style={"color": 0xFF888888, "font_size": 13,
                               "font_weight": "bold"},
                    )
                    self._path_field = ui.StringField(
                        style={"background_color": 0xFF1A1A1A,
                               "border_radius": 4, "font_size": 13},
                    )
                    _zin_btn("Browse", 56, self._on_browse)
                    _zin_btn("Load",   56, self._on_load, color=0xFF1F5C2E)

                ui.Separator(height=1, style={"color": 0x33FFFFFF})

                # ── Main Content (3 panes) ────────────────────────────────
                with ui.HStack():

                    # ── LEFT: Tree View (30 %) ────────────────────────────
                    with ui.ScrollingFrame(
                        width=ui.Percent(30),
                        style={"background_color": 0xFF1E1E1E},
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    ):
                        self._tree_view = ui.TreeView(
                            self._category_model,
                            delegate=self._delegate,
                            root_visible=False,
                            header_visible=False,
                            column_widths=[ui.Fraction(1)],
                        )
                        self._tree_view.set_selection_changed_fn(
                            self._on_selection_changed
                        )
                        self._tree_view.set_mouse_double_clicked_fn(
                            self._on_tree_double_click
                        )

                    self._delegate.set_tree_view(self._tree_view)

                    # separator
                    ui.Rectangle(width=1, style={"background_color": 0xFF333333})

                    # ── MIDDLE: Asset Grid ────────────────────────────────
                    self._grid_scroll = ui.ScrollingFrame(
                        style={"background_color": 0xFF181818},
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    )
                    self._grid_scroll.set_computed_content_size_changed_fn(
                        self._on_grid_resized
                    )
                    with self._grid_scroll:
                        self._asset_grid_container = ui.VStack(
                            spacing=10, padding=10
                        )
                        with self._asset_grid_container:
                            self._grid_placeholder("Select a folder")

                    # separator
                    ui.Rectangle(width=1, style={"background_color": 0xFF333333})

                    # ── RIGHT: Detail Panel (MVVM) ────────────────────────
                    with ui.ScrollingFrame(
                        width=ui.Pixel(260),
                        style={"background_color": 0xFF232323},
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    ):
                        with ui.VStack(spacing=10, padding=10):

                            # Thumbnail — ui.Image supports model= keyword
                            ui.Image(
                                model=self._detail_thumbnail_url,
                                height=ui.Pixel(200),
                                fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                style={"color": 0xFF888888},
                            )

                            ui.Separator(height=1, style={"color": 0x33FFFFFF})

                            # Asset name — store ref, update via .text
                            self._detail_name_lbl = ui.Label(
                                "Select an asset",
                                word_wrap=True,
                                alignment=ui.Alignment.CENTER,
                                style={"font_size": 15, "color": 0xFFDDDDDD,
                                       "font_weight": "bold"},
                            )

                            # Asset Info collapsable
                            with ui.CollapsableFrame("Asset Info", collapsed=False, height=0):
                                with ui.VStack(spacing=4, padding=6):
                                    self._detail_path_lbl = ui.Label(
                                        "",
                                        word_wrap=True,
                                        style={"color": 0xFFAAAAAA, "font_size": 11},
                                    )

                            ui.Spacer()

    # ── Helpers ────────────────────────────────────────────────────────────
    @staticmethod
    def _grid_placeholder(text: str):
        with ui.VStack(alignment=ui.Alignment.CENTER):
            ui.Spacer()
            ui.Label(
                text,
                alignment=ui.Alignment.CENTER,
                style={"color": 0xFF555555, "font_size": 13},
            )
            ui.Spacer()

    # ── Top Bar Events ─────────────────────────────────────────────────────
    def _on_browse(self):
        try:
            from omni.kit.widget.filebrowser import FileBrowserWidget  # noqa
            from omni.kit.window.filepicker import FilePickerDialog

            def _apply(filename, path):
                self._path_field.model.set_value(path.replace("\\", "/"))
                self._file_picker.hide()
                self._on_load()          # ← 按 OK 後自動載入，無需再按 Load

            self._file_picker = FilePickerDialog(
                "Select Folder", click_apply_handler=_apply
            )
            self._file_picker.show()
        except Exception as e:
            print(f"[SmartAssetsLibrary] Browse error: {e}")

    def _on_load(self):
        raw = self._path_field.model.get_value_as_string().strip()
        path = raw.replace("\\", "/").rstrip("/")
        if path and path not in self.mixed_root_paths:
            self.mixed_root_paths.append(path)
            self._refresh_library()

    # ── Library Refresh ────────────────────────────────────────────────────
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
        if result != omni.client.Result.OK:
            return
        for entry in entries:
            if (entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN) and \
               not entry.relative_path.startswith("."):
                full = f"{path}/{entry.relative_path}"
                child = CategoryItem(entry.relative_path, full)
                parent.children.append(child)
                await self._build_tree_recursive(full, child, loop)

    # ── Tree Selection ─────────────────────────────────────────────────────
    def _on_selection_changed(self, selections):
        if selections:
            asyncio.ensure_future(
                self._load_folder_assets_async(selections[0].full_path)
            )

    def _on_tree_double_click(self, x, y, button, modifier):
        if button != 0:
            return
        sels = self._tree_view.selection
        if sels:
            item = sels[0]
            self._tree_view.set_expanded(item, not self._tree_view.is_expanded(item), False)

    # ── Async Folder Scan ──────────────────────────────────────────────────
    async def _load_folder_assets_async(self, folder_path: str):
        """Scan folder, collect USD files, rebuild the grid."""
        loop      = asyncio.get_event_loop()
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

    # ── Asset Grid (Responsive) ─────────────────────────────────────────────
    def _on_grid_resized(self):
        """Called when the scrolling frame changes size; rebuilds grid."""
        if self._grid_building or not self._current_usd_files:
            return
        self._build_asset_grid(self._current_usd_files)

    def _build_asset_grid(self, usd_files: list):
        if self._asset_grid_container is None or self._grid_building:
            return
        self._grid_building = True
        try:
            self._asset_grid_container.clear()

            # Responsive column calculation
            CARD_W   = 140
            CARD_H   = 160
            IMG_SIZE = 110
            PADDING  = 10
            SPACING  = 10
            grid_w = self._grid_scroll.computed_content_width
            if grid_w < CARD_W:
                grid_w = 480
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
                        # Fill empty slots at the end of a partial row
                        for _ in range(COLS - len(row)):
                            ui.Spacer(width=CARD_W)
        finally:
            self._grid_building = False

    # ── Asset Card ─────────────────────────────────────────────────────────
    def _build_asset_card(self, fname: str, fpath: str,
                          card_w: int, card_h: int, img_size: int):
        base       = os.path.splitext(fname)[0]
        parent_dir = os.path.dirname(fpath)

        # ── Thumbnail resolution ──────────────────────────────────────────
        candidate  = f"{parent_dir}/{base}.png"
        is_local   = ":" in parent_dir or parent_dir.startswith("/")
        if is_local and os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
            thumb = candidate
        else:
            thumb = "${glyphs}/file.svg"

        # ── Drag payload: return path string ─────────────────────────────
        def _drag_fn(p=fpath):
            return p

        # ── Click: update detail panel directly ──────────────────────────
        def _click_fn(x, y, btn, mod, n=fname, p=fpath, t=thumb, bd=base):
            if btn == 0:
                if self._detail_name_lbl:
                    self._detail_name_lbl.text = bd
                if self._detail_path_lbl:
                    self._detail_path_lbl.text = p
                # ui.Image model= (SimpleStringModel) does work in this Kit
                self._detail_thumbnail_url.set_value(t)

        # ── Card Widget ───────────────────────────────────────────────────
        with ui.Frame(width=card_w, height=card_h):
            with ui.ZStack():
                # Background
                ui.Rectangle(
                    style={
                        "background_color": 0xFF2A2A2A,
                        "border_radius": 4,
                        "border_width": 1,
                        "border_color": 0xFF3A3A3A,
                    }
                )
                # Hover overlay
                ui.Rectangle(
                    style={
                        "background_color": 0x00000000,
                        "background_color:hovered": 0x18FFFFFF,
                        "border_radius": 4,
                    }
                )
                # Content
                with ui.VStack(spacing=4, padding=6,
                               alignment=ui.Alignment.CENTER):
                    with ui.Frame(
                        width=img_size, height=img_size,
                        alignment=ui.Alignment.CENTER,
                    ):
                        ui.Image(
                            thumb,
                            width=img_size, height=img_size,
                            fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                            style={"color": 0xFFAAAAAA},
                        )
                    ui.Label(
                        base,
                        alignment=ui.Alignment.CENTER,
                        word_wrap=True,
                        style={"color": 0xFFCCCCCC, "font_size": 12},
                    )

                # Transparent hit-box (top layer) — click + drag
                hitbox = ui.Rectangle(style={"background_color": 0x00000000})
                hitbox.set_mouse_pressed_fn(_click_fn)
                hitbox.set_drag_fn(_drag_fn)
