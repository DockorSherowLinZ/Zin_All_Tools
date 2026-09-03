# =============================================================================
# extension.py
# Smart Info Panel — Extension 主程式
#
# 提供 3D 懸浮 metadata 面板功能：
#   - 監聽 Selection Changed 事件
#   - 讀取 AIF metadata / 計算 BBox 尺寸
#   - 在 Viewport 3D 空間中繪製懸浮面板
#   - Toggle 方案 A (Viewport Toolbar) + 方案 B (Tools Box 面板)
# =============================================================================

import omni.ext
import omni.ui as ui
import omni.usd
import carb

from pxr import Usd, UsdGeom

from zin_core.menu import ZinMenuMixin

from .info_panel_overlay import InfoPanelOverlay
from .metadata_reader import (
    read_aif_metadata, find_aif_prim, get_fallback_metadata,
    compute_bbox_dimensions,
)
from .style import (
    TOGGLE_ENABLED_STYLE, TOGGLE_DISABLED_STYLE,
    SLIDER_STYLE, INFO_LABEL_STYLE, VALUE_LABEL_STYLE,
)


# ========================================================
#  核心邏輯 Widget
# ========================================================
class SmartInfoPanelWidget:
    """Smart Info Panel 核心邏輯與 UI 元件。"""

    def __init__(self):
        self._usd_context = omni.usd.get_context()
        self._overlay = InfoPanelOverlay()
        self._bbox_cache = None
        self._stage_mpu = 1.0
        self._enabled = False
        self._stage_event_sub = None

        # 顯示控制
        self._show_core = True
        self._show_spec = True
        self._show_dims = True
        self._scale_model = ui.SimpleFloatModel(1.0)
        self._scale_model.add_value_changed_fn(self._on_scale_changed)

        # Toggle 同步回呼
        self._on_toggle_callbacks = []

        # UI 參考
        self._toggle_btn = None
        self._vp_toggle_btn = None
        self._vp_toggle_frame = None
        self._sel_path_label = None
        self._status_label = None

    # ── 生命週期 ──────────────────────────────

    def startup(self):
        """啟動（初始化 bbox cache，但不訂閱事件 — 等 toggle 開啟後才訂閱）。"""
        self._init_bbox_cache()

    def shutdown(self):
        """關閉（清理所有資源）。"""
        self._unsubscribe_events()
        self._overlay.destroy()
        self._destroy_viewport_toggle()
        self._bbox_cache = None
        self._on_toggle_callbacks.clear()

    # ── Toggle 管理 ──────────────────────────

    @property
    def is_enabled(self):
        return self._enabled

    def set_enabled(self, value: bool):
        """設定 Toggle 狀態，並通知所有監聽者。"""
        if self._enabled == value:
            return
        self._enabled = value

        if value:
            self._subscribe_events()
            self._create_viewport_toggle()
            # 立即檢查目前選取
            self._check_selection()
        else:
            self._unsubscribe_events()
            self._overlay.destroy()
            self._destroy_viewport_toggle()

        # 通知所有監聽者更新 UI
        for cb in self._on_toggle_callbacks:
            try:
                cb(value)
            except Exception as e:
                print(f"[SmartInfoPanel] Toggle callback error: {e}")

        # 更新自身的 UI 按鈕狀態
        self._update_toggle_ui()

    def register_toggle_callback(self, fn):
        """註冊 Toggle 狀態變化的回呼函數。"""
        if fn not in self._on_toggle_callbacks:
            self._on_toggle_callbacks.append(fn)

    def unregister_toggle_callback(self, fn):
        """移除 Toggle 回呼。"""
        if fn in self._on_toggle_callbacks:
            self._on_toggle_callbacks.remove(fn)

    # ── 事件訂閱 ──────────────────────────────

    def _subscribe_events(self):
        if self._stage_event_sub:
            return
        stream = self._usd_context.get_stage_event_stream()
        self._stage_event_sub = stream.create_subscription_to_pop(
            self._on_stage_event, name="smart_info_panel_stage"
        )

    def _unsubscribe_events(self):
        self._stage_event_sub = None

    def _on_stage_event(self, event):
        if not self._enabled:
            return

        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            self._check_selection()
        elif event.type == int(omni.usd.StageEventType.OPENED):
            self._init_bbox_cache()
            self._refresh_stage_info()
        elif event.type == int(omni.usd.StageEventType.CLOSING):
            self._overlay.destroy()
            self._update_sel_label(None)

    # ── 選取處理 ──────────────────────────────

    def _check_selection(self):
        """檢查目前選取的 prim 並更新 overlay。"""
        paths = self._usd_context.get_selection().get_selected_prim_paths()

        if not paths:
            self._overlay.destroy()
            self._update_sel_label(None)
            return

        stage = self._usd_context.get_stage()
        if not stage:
            self._overlay.destroy()
            return

        # 取第一個選取的 prim
        prim_path = paths[0]
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            self._overlay.destroy()
            self._update_sel_label(None)
            return

        self._update_sel_label(prim_path)

        # 讀取 metadata
        # 先從選取的 prim 找 AIF 屬性，找不到則向上遍歷
        aif_prim = find_aif_prim(prim)
        if aif_prim:
            metadata = read_aif_metadata(aif_prim)
        else:
            # 使用 GB300 測試資料
            metadata = get_fallback_metadata()

        # 計算 BBox 尺寸
        if not self._bbox_cache:
            self._init_bbox_cache()
        self._bbox_cache.Clear()
        self._refresh_stage_info()

        bbox_dims = compute_bbox_dimensions(prim, self._bbox_cache, self._stage_mpu)

        if not bbox_dims:
            # 如果 BBox 計算失敗，仍然顯示 metadata（只是沒有尺寸）
            # 使用 prim 的世界位置作為面板位置
            try:
                xformable = UsdGeom.Xformable(prim)
                world_transform = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                pos = world_transform.ExtractTranslation()
                position = (pos[0], pos[1], pos[2] + 100)  # 上方偏移
            except Exception:
                position = (0, 0, 100)
        else:
            position = bbox_dims["top_center"]

        # 取得 viewport window 並繪製 overlay
        try:
            from omni.kit.viewport.utility import get_active_viewport_window
            viewport_window = get_active_viewport_window()
            if viewport_window:
                self._overlay.build_overlay(
                    viewport_window, position, metadata, bbox_dims,
                    show_core=self._show_core,
                    show_spec=self._show_spec,
                    show_dims=self._show_dims,
                )
        except ImportError:
            carb.log_warn("[SmartInfoPanel] omni.kit.viewport.utility not available")

    # ── BBox / Stage 工具 ────────────────────

    def _init_bbox_cache(self):
        purposes = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render,
                     UsdGeom.Tokens.proxy, UsdGeom.Tokens.guide]
        self._bbox_cache = UsdGeom.BBoxCache(
            Usd.TimeCode.Default(), purposes, useExtentsHint=False
        )

    def _refresh_stage_info(self):
        stage = self._usd_context.get_stage()
        if stage:
            mpu = UsdGeom.GetStageMetersPerUnit(stage) or 1.0
            self._stage_mpu = float(mpu)

    # ── Viewport Toolbar Toggle（方案 A）──────

    def _create_viewport_toggle(self):
        """在 Viewport 上方建立一個 info toggle 按鈕。"""
        try:
            from omni.kit.viewport.utility import get_active_viewport_window
            viewport_window = get_active_viewport_window()
            if not viewport_window:
                return

            self._vp_toggle_frame = viewport_window.get_frame(
                "smart_info_panel_toggle"
            )
            if not self._vp_toggle_frame:
                return

            with self._vp_toggle_frame:
                with ui.VStack(height=0):
                    with ui.HStack(height=28, spacing=4):
                        ui.Spacer()
                        self._vp_toggle_btn = ui.Button(
                            "ℹ Info Panel: ON",
                            width=140, height=24,
                            style=TOGGLE_ENABLED_STYLE,
                            clicked_fn=self._on_vp_toggle_clicked,
                            tooltip="Toggle Equipment Info Panel",
                        )
                        ui.Spacer(width=8)
        except Exception as e:
            carb.log_info(f"[SmartInfoPanel] Viewport toggle creation: {e}")

    def _destroy_viewport_toggle(self):
        """清除 Viewport toolbar toggle。"""
        self._vp_toggle_btn = None
        if self._vp_toggle_frame:
            try:
                self._vp_toggle_frame.clear()
            except Exception:
                pass
            self._vp_toggle_frame = None

    def _on_vp_toggle_clicked(self):
        """Viewport toolbar 按鈕點擊 — 切換 toggle。"""
        self.set_enabled(not self._enabled)

    # ── 縮放控制 ──────────────────────────────

    def _on_scale_changed(self, model):
        """滑桿值變化時更新面板縮放並重繪。"""
        self._overlay.set_scale(model.as_float)
        if self._enabled:
            self._check_selection()

    # ── Tools Box 面板 UI（方案 B）────────────

    def build_ui_layout(self):
        """
        在 Tools Box 的 Tab 內繪製控制面板 UI。
        回傳 ScrollingFrame 供外部使用。
        """
        scroll_frame = ui.ScrollingFrame(
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
            height=ui.Fraction(1),
        )
        with scroll_frame:
            with ui.VStack(spacing=6, padding=8, alignment=ui.Alignment.TOP):

                # === Toggle 按鈕（方案 B）===
                with ui.HStack(height=36, spacing=4):
                    self._toggle_btn = ui.Button(
                        self._get_toggle_text(),
                        height=32,
                        style=TOGGLE_ENABLED_STYLE if self._enabled else TOGGLE_DISABLED_STYLE,
                        clicked_fn=self._on_panel_toggle_clicked,
                    )
                ui.Spacer(height=4)

                # === 面板縮放滑桿 ===
                with ui.CollapsableFrame("Panel Scale", collapsed=False, height=0):
                    with ui.VStack(spacing=4, padding=6):
                        with ui.HStack(height=22, spacing=6):
                            ui.Label("Size:", width=40, style=INFO_LABEL_STYLE)
                            ui.FloatSlider(
                                self._scale_model,
                                min=0.3, max=5.0, step=0.1,
                                style=SLIDER_STYLE,
                            )
                            ui.Label(
                                f"{self._scale_model.as_float:.1f}x",
                                width=40,
                                style=VALUE_LABEL_STYLE,
                            )

                ui.Spacer(height=4)

                # === 顯示區塊控制 ===
                with ui.CollapsableFrame("Display Sections", collapsed=False, height=0):
                    with ui.VStack(spacing=4, padding=6):
                        # Dimensions
                        with ui.HStack(height=22, spacing=6):
                            cb_dims = ui.CheckBox(width=18, height=18)
                            cb_dims.model.set_value(self._show_dims)
                            cb_dims.model.add_value_changed_fn(
                                lambda m: self._set_show_section("dims", m.get_value_as_bool())
                            )
                            ui.Label("📐 Dimensions (Smart Measure)", style=VALUE_LABEL_STYLE)

                        # Core
                        with ui.HStack(height=22, spacing=6):
                            cb_core = ui.CheckBox(width=18, height=18)
                            cb_core.model.set_value(self._show_core)
                            cb_core.model.add_value_changed_fn(
                                lambda m: self._set_show_section("core", m.get_value_as_bool())
                            )
                            ui.Label("🏭 Core Info", style=VALUE_LABEL_STYLE)

                        # Spec
                        with ui.HStack(height=22, spacing=6):
                            cb_spec = ui.CheckBox(width=18, height=18)
                            cb_spec.model.set_value(self._show_spec)
                            cb_spec.model.add_value_changed_fn(
                                lambda m: self._set_show_section("spec", m.get_value_as_bool())
                            )
                            ui.Label("⚡ Spec Info", style=VALUE_LABEL_STYLE)

                ui.Spacer(height=4)

                # === 當前選取資訊 ===
                with ui.CollapsableFrame("Selection", collapsed=False, height=0):
                    with ui.VStack(spacing=2, padding=6):
                        with ui.HStack(height=18):
                            ui.Label("Path:", width=40, style=INFO_LABEL_STYLE)
                            self._sel_path_label = ui.Label(
                                "None",
                                style={"color": 0xFFDDDDDD, "font_size": 12},
                                word_wrap=True,
                            )
                        with ui.HStack(height=18):
                            ui.Label("Status:", width=40, style=INFO_LABEL_STYLE)
                            self._status_label = ui.Label(
                                "Idle" if not self._enabled else "Listening...",
                                style={"color": 0xFF888888},
                            )

                ui.Spacer(height=10)

        # 訂閱事件（如果已啟用）
        if self._enabled and not self._stage_event_sub:
            self._subscribe_events()
            self._check_selection()

        return scroll_frame

    def _on_panel_toggle_clicked(self):
        """Tools Box 面板內的 Toggle 按鈕點擊。"""
        self.set_enabled(not self._enabled)

    def _get_toggle_text(self):
        if self._enabled:
            return "✦  Info Panel：已啟用"
        else:
            return "○  Info Panel：已關閉"

    def _update_toggle_ui(self):
        """更新所有 Toggle 按鈕的視覺狀態。"""
        # 方案 B：Tools Box 面板按鈕
        if self._toggle_btn:
            try:
                self._toggle_btn.text = self._get_toggle_text()
                self._toggle_btn.style = (
                    TOGGLE_ENABLED_STYLE if self._enabled else TOGGLE_DISABLED_STYLE
                )
            except Exception:
                pass

        # 方案 A：Viewport toolbar 按鈕
        if self._vp_toggle_btn:
            try:
                if self._enabled:
                    self._vp_toggle_btn.text = "ℹ Info Panel: ON"
                    self._vp_toggle_btn.style = TOGGLE_ENABLED_STYLE
                else:
                    self._vp_toggle_btn.text = "ℹ Info Panel: OFF"
                    self._vp_toggle_btn.style = TOGGLE_DISABLED_STYLE
            except Exception:
                pass

        # 更新 status label
        if self._status_label:
            try:
                self._status_label.text = "Listening..." if self._enabled else "Idle"
                self._status_label.style = (
                    {"color": 0xFF44AA44} if self._enabled else {"color": 0xFF888888}
                )
            except Exception:
                pass

    def _update_sel_label(self, path):
        """更新選取路徑顯示。"""
        if self._sel_path_label:
            try:
                self._sel_path_label.text = path if path else "None"
            except Exception:
                pass

    def _set_show_section(self, section, value):
        """設定顯示區塊開關並重繪。"""
        if section == "core":
            self._show_core = value
        elif section == "spec":
            self._show_spec = value
        elif section == "dims":
            self._show_dims = value
        if self._enabled:
            self._check_selection()


# ========================================================
#  Extension Wrapper
# ========================================================
class SmartInfoPanelExtension(ZinMenuMixin, omni.ext.IExt):
    WINDOW_NAME = "Smart Info Panel"
    MENU_PATH = f"Zin_All_Tools/{WINDOW_NAME}"

    def __init__(self):
        super().__init__()
        self._widget = SmartInfoPanelWidget()
        self._window = None
        self._menu_added = False

    def on_startup(self, ext_id):
        """獨立載入 Extension 時執行。"""
        self._build_menu()

    def on_shutdown(self):
        """Extension 卸載時執行。"""
        self._remove_menu()
        if self._widget:
            self._widget.shutdown()
            self._widget = None
        if self._window:
            self._window.destroy()
            self._window = None

    def _toggle_window(self, menu, value):
        if value:
            if not self._window:
                from omni.ui import DockPreference
                self._window = ui.Window(
                    self.WINDOW_NAME, width=360, height=450,
                    dockPreference=DockPreference.RIGHT,
                )
                self._window.set_visibility_changed_fn(self._on_visibility_changed)
                with self._window.frame:
                    self._widget.build_ui_layout()
                self._widget.startup()
            self._window.visible = True
        else:
            if self._window:
                self._window.visible = False

    # ========================================================
    #  橋接方法 (Bridge Methods) — 供 Tools Box 呼叫
    # ========================================================
    def startup_logic(self):
        if self._widget:
            self._widget.startup()

    def shutdown_logic(self):
        if self._widget:
            self._widget.shutdown()

    def build_ui_layout(self):
        if self._widget:
            return self._widget.build_ui_layout()

    def set_enabled(self, value: bool):
        if self._widget:
            self._widget.set_enabled(value)

    @property
    def is_enabled(self):
        if self._widget:
            return self._widget.is_enabled
        return False

    def register_toggle_callback(self, fn):
        if self._widget:
            self._widget.register_toggle_callback(fn)
