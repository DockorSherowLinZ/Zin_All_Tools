# =============================================================================
# style.py
# Smart Info Panel — 3D Overlay 樣式常數
# =============================================================================

import omni.ui as ui

# ─────────────────────────────────────────────
#  3D 面板色碼（RGBA float）
# ─────────────────────────────────────────────
# 背景
PANEL_BG_COLOR      = ui.color(0.08, 0.08, 0.12, 0.88)   # 深色半透明
PANEL_BORDER_COLOR  = ui.color(0.3, 0.6, 0.9, 0.6)       # 藍色邊框
HEADER_BG_COLOR     = ui.color(0.1, 0.2, 0.35, 0.95)     # 深藍標題背景

# 文字
TITLE_COLOR         = ui.color(0.4, 0.85, 1.0, 1.0)      # 亮青色標題
SECTION_HEADER_COLOR= ui.color(0.9, 0.75, 0.3, 1.0)      # 金色區塊標題
LABEL_COLOR         = ui.color(0.65, 0.65, 0.7, 1.0)     # 灰藍色 key
VALUE_COLOR         = ui.color(0.95, 0.95, 0.95, 1.0)    # 白色 value
DIM_LABEL_COLOR     = ui.color(0.3, 0.9, 0.5, 1.0)       # 綠色（尺寸數值）

# 面板尺寸 (scene 座標)
PANEL_LINE_HEIGHT   = 18       # 每行高度 (scene pixels)
PANEL_PADDING       = 12       # 內邊距
PANEL_TITLE_SIZE    = 22       # 標題字體大小
PANEL_SECTION_SIZE  = 18       # 區塊標題字體大小
PANEL_TEXT_SIZE     = 15       # 內容文字字體大小
PANEL_OFFSET_Z      = 50      # 面板在機台頂部上方的 Z 偏移（場景單位）

# ─────────────────────────────────────────────
#  2D 控制面板樣式 (Tools Box 內)
# ─────────────────────────────────────────────
TOGGLE_ENABLED_STYLE = {
    "Button": {"background_color": 0xFF2A5E2A, "border_radius": 6, "font_size": 14},
    "Button:hovered": {"background_color": 0xFF33703A},
    "Button:pressed": {"background_color": 0xFF44AA44},
}

TOGGLE_DISABLED_STYLE = {
    "Button": {"background_color": 0xFF343432, "border_radius": 6, "font_size": 14},
    "Button:hovered": {"background_color": 0xFF4A4A48},
    "Button:pressed": {"background_color": 0xFF5A5A58},
}

SLIDER_STYLE = {
    "FloatSlider": {
        "background_color": 0xFF1A1A1A,
        "secondary_color": 0xFF2A5E8A,
        "border_radius": 4,
    }
}

INFO_LABEL_STYLE = {"color": 0xFFAAAAAA, "font_size": 13}
VALUE_LABEL_STYLE = {"color": 0xFFDDDDDD, "font_size": 13}
