# =============================================================================
# info_panel_overlay.py
# Smart Info Panel — 3D SceneView Overlay 繪製邏輯
#
# 在 Viewport 上以 omni.ui.scene 繪製懸浮 metadata 面板。
# =============================================================================

import omni.ui as ui
import carb

try:
    import omni.ui.scene as sc
except ImportError:
    sc = None

from .style import (
    TITLE_COLOR, SECTION_HEADER_COLOR, LABEL_COLOR,
    VALUE_COLOR, DIM_LABEL_COLOR, PANEL_BG_COLOR, PANEL_BORDER_COLOR,
    PANEL_TITLE_SIZE, PANEL_SECTION_SIZE, PANEL_TEXT_SIZE,
    PANEL_OFFSET_Z,
)
from .metadata_reader import format_value


class InfoPanelOverlay:
    """管理 3D 空間內的 metadata 懸浮面板繪製。"""

    def __init__(self):
        self._scene_view = None
        self._scene_frame = None
        self._scale = 1.0

    def set_scale(self, scale: float):
        """設定面板縮放比例。"""
        self._scale = max(0.3, min(5.0, scale))

    @property
    def scale(self):
        return self._scale

    def build_overlay(self, viewport_window, position, metadata, bbox_dims,
                      show_core=True, show_spec=True, show_dims=True):
        """
        在 viewport 上方建立 3D 懸浮面板。

        Args:
            viewport_window: Viewport window 實例
            position: (x, y, z) 面板的世界座標位置（通常是機台頂部中心）
            metadata: {"core": {...}, "spec": {...}} AIF metadata
            bbox_dims: {"x_cm": float, "y_cm": float, "z_cm": float} 或 None
            show_core: 是否顯示 Core 資訊
            show_spec: 是否顯示 Spec 資訊
            show_dims: 是否顯示尺寸資訊
        """
        if not sc:
            carb.log_warn("[SmartInfoPanel] omni.ui.scene not available")
            return

        # 先清除舊的 overlay
        self.destroy()

        try:
            # 取得 viewport overlay frame
            self._scene_frame = viewport_window.get_frame("smart_info_panel_overlay")
            if not self._scene_frame:
                carb.log_warn("[SmartInfoPanel] Could not get overlay frame")
                return

            # 準備顯示文字行
            lines = self._build_text_lines(metadata, bbox_dims,
                                           show_core, show_spec, show_dims)

            with self._scene_frame:
                self._scene_view = sc.SceneView(
                    aspect_ratio_policy=sc.AspectRatioPolicy.STRETCH
                )
                with self._scene_view.scene:
                    # 面板位置：機台頂部上方偏移
                    panel_pos = [
                        position[0],
                        position[1],
                        position[2] + PANEL_OFFSET_Z * self._scale,
                    ]

                    with sc.Transform(
                        transform=sc.Matrix44.get_translation_matrix(
                            panel_pos[0], panel_pos[1], panel_pos[2]
                        ),
                        look_at=sc.Transform.LookAt.CAMERA,
                    ):
                        # 縮放
                        with sc.Transform(
                            transform=sc.Matrix44.get_scale_matrix(
                                self._scale, self._scale, self._scale
                            )
                        ):
                            self._draw_panel(lines)

            # 綁定 camera model
            if self._scene_view:
                self._bind_scene_view_camera(viewport_window)

        except Exception as e:
            carb.log_warn(f"[SmartInfoPanel] Overlay build error: {e}")
            import traceback
            traceback.print_exc()

    def _build_text_lines(self, metadata, bbox_dims,
                          show_core, show_spec, show_dims):
        """
        建構顯示文字行列表。
        每個項目為 (text, color, font_size, is_separator)
        """
        lines = []

        if not metadata:
            metadata = {"core": {}, "spec": {}}

        # --- 標題 ---
        model_name = "Unknown Equipment"
        if "modelNumber" in metadata.get("core", {}):
            val = metadata["core"]["modelNumber"]
            model_name = val[0] if isinstance(val, tuple) else val
        lines.append((f"★  {model_name}", TITLE_COLOR, PANEL_TITLE_SIZE, False))
        lines.append(("", None, 6, True))  # separator

        # --- 尺寸區 (Smart Measure) ---
        if show_dims and bbox_dims:
            lines.append(("📐  Dimensions", SECTION_HEADER_COLOR, PANEL_SECTION_SIZE, False))
            lines.append((f"    X:  {bbox_dims['x_cm']:.2f} cm", DIM_LABEL_COLOR, PANEL_TEXT_SIZE, False))
            lines.append((f"    Y:  {bbox_dims['y_cm']:.2f} cm", DIM_LABEL_COLOR, PANEL_TEXT_SIZE, False))
            lines.append((f"    Z:  {bbox_dims['z_cm']:.2f} cm", DIM_LABEL_COLOR, PANEL_TEXT_SIZE, False))
            lines.append(("", None, 4, True))  # separator

        # --- Core 資訊 ---
        if show_core and metadata.get("core"):
            lines.append(("🏭  Core Info", SECTION_HEADER_COLOR, PANEL_SECTION_SIZE, False))
            # 精選顯示的欄位（按重要性排序）
            core_display = [
                ("assetClass",    "Class"),
                ("manufacturer",  "Manufacturer"),
                ("width",         "Width (mm)"),
                ("depth",         "Depth (mm)"),
                ("height",        "Height (mm)"),
                ("weight",        "Weight (kg)"),
                ("assetVersion",  "Version"),
                ("assetCreationDate", "Created"),
            ]
            for key, label in core_display:
                if key in metadata["core"]:
                    raw = metadata["core"][key]
                    val = raw[0] if isinstance(raw, tuple) else raw
                    lines.append((f"    {label}:  {format_value(val)}", VALUE_COLOR, PANEL_TEXT_SIZE, False))
            lines.append(("", None, 4, True))

        # --- Spec 資訊 ---
        if show_spec and metadata.get("spec"):
            lines.append(("⚡  Spec Info", SECTION_HEADER_COLOR, PANEL_SECTION_SIZE, False))
            spec_display = [
                ("numGPUs",           "GPUs"),
                ("maxPowerDcTdp",     "Max Power DC TDP (kW)"),
                ("maxPowerAcEdpp1",   "Max Power AC (kW)"),
                ("liquidCooling",     "Liquid Cooling (kW)"),
                ("airCooling",        "Air Cooling (kW)"),
                ("heatCaptureRatio",  "Heat Capture (%)"),
                ("namePlatePower",    "UPS Rating (W)"),
            ]
            for key, label in spec_display:
                if key in metadata["spec"]:
                    raw = metadata["spec"][key]
                    val = raw[0] if isinstance(raw, tuple) else raw
                    lines.append((f"    {label}:  {format_value(val)}", VALUE_COLOR, PANEL_TEXT_SIZE, False))

        return lines

    def _draw_panel(self, lines):
        """在 scene 中繪製面板背景和文字行。"""
        if not lines:
            return

        # 計算面板尺寸（使用固定的字元寬度估算）
        max_chars = max(len(line[0]) for line in lines if line[0])
        panel_width = max(max_chars * 7.5 + 30, 200)
        line_spacing = 20
        panel_height = len(lines) * line_spacing + 24

        # --- 背景半透明矩形 ---
        # 位置微調：讓文字從上方開始排列
        bg_offset_y = panel_height / 2.0

        with sc.Transform(
            transform=sc.Matrix44.get_translation_matrix(0, bg_offset_y, 0)
        ):
            # 背景
            sc.Rectangle(
                width=panel_width,
                height=panel_height,
                color=PANEL_BG_COLOR,
                wireframe=False,
            )
            # 邊框
            sc.Rectangle(
                width=panel_width,
                height=panel_height,
                color=PANEL_BORDER_COLOR,
                wireframe=True,
                thickness=1.5,
            )

        # --- 文字行 ---
        y_offset = panel_height - 16  # 從頂部開始
        for text, color, font_size, is_sep in lines:
            if is_sep:
                y_offset -= font_size
                continue
            if not text:
                continue

            with sc.Transform(
                transform=sc.Matrix44.get_translation_matrix(
                    -panel_width / 2.0 + 12,  # 左對齊
                    y_offset,
                    0.1  # 稍微在背景前面
                )
            ):
                sc.Label(
                    text,
                    color=color if color else VALUE_COLOR,
                    size=font_size,
                    alignment=ui.Alignment.LEFT_TOP,
                )
            y_offset -= line_spacing

    def _bind_scene_view_camera(self, viewport_window):
        """
        將 SceneView 的 camera model 綁定到 viewport 的 camera。
        相容多版本 Kit (105~109)。
        （複用 Smart Measure 的經過驗證的方式）
        """
        vp_api = viewport_window.viewport_api

        # 方法 1 (Kit 109)：使用 ViewportAPI 的 __scene_camera_model
        try:
            camera_model = getattr(vp_api, '_ViewportAPI__scene_camera_model', None)
            if camera_model:
                self._scene_view.model = camera_model
                return
        except Exception as exc:
            carb.log_verbose(f"[SmartInfoPanel] Camera model probe (method 1) failed: {exc}")

        # 方法 2 (Kit 109)：從 ViewportAPI.__scene_views 列表取得
        try:
            scene_views = getattr(vp_api, '_ViewportAPI__scene_views', None)
            if scene_views and len(scene_views) > 0:
                for sv_ref in scene_views:
                    sv = sv_ref() if callable(sv_ref) else sv_ref
                    if sv and hasattr(sv, 'model') and sv.model:
                        self._scene_view.model = sv.model
                        return
        except Exception as exc:
            carb.log_verbose(f"[SmartInfoPanel] Camera model probe (method 2) failed: {exc}")

        # 方法 3 (Kit 106+)：直接從 viewport_api.scene_view 取得
        try:
            if hasattr(vp_api, 'scene_view') and vp_api.scene_view:
                self._scene_view.model = vp_api.scene_view.model
                return
        except Exception as exc:
            carb.log_verbose(f"[SmartInfoPanel] Camera model probe (method 3) failed: {exc}")

        # 方法 4：使用 add_scene_view API
        try:
            vp_api.add_scene_view(self._scene_view)
            return
        except Exception as exc:
            carb.log_verbose(f"[SmartInfoPanel] Camera model probe (method 4) failed: {exc}")

        carb.log_info("[SmartInfoPanel] Could not auto-bind camera model")

    def destroy(self):
        """安全清除 Scene overlay 資源。"""
        self._scene_view = None
        if self._scene_frame:
            try:
                self._scene_frame.clear()
            except Exception as exc:
                carb.log_verbose(f"[SmartInfoPanel] Scene frame already destroyed: {exc}")
            self._scene_frame = None

    @property
    def is_visible(self):
        return self._scene_view is not None
