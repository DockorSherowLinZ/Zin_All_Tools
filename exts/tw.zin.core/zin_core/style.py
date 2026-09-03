# =============================================================================
# zin_style.py
# Zin All Tools — Unified Design System
#
# 集中管理所有 UI 元件的色碼與樣式。
# 使用 omni.ui Style Dictionary 語法。
# =============================================================================

# ─────────────────────────────────────────────
#  色碼設計 Token（ARGB 格式：0xAARRGGBB）
# ─────────────────────────────────────────────

# 背景層
ARGB_PANEL_BG       = 0xFF232323  # 主要 Panel 背景
ARGB_SIDEBAR_BG     = 0xFF1E1E1E  # 側邊欄 / TreeView 背景
ARGB_INPUT_BG       = 0xFF1A1A1A  # 輸入框背景
ARGB_SEPARATOR      = 0xFF333333  # 分隔線

# 按鈕狀態
ARGB_DEFAULT_BG     = 0xFF343432  # 一般按鈕預設背景（深灰）
ARGB_HOVER_BG       = 0xFF4A4A48  # 滑鼠懸停（中灰）
ARGB_PRESSED_BG     = 0xFF5A5A58  # 點擊瞬間

# 正確 / 啟動 / 成功（綠色系）
ARGB_CORRECT_BG     = 0xFF2A5E2A  # 深綠背景
ARGB_CORRECT_HOVER  = 0xFF33703A  # 懸停亮綠
ARGB_CORRECT_LABEL  = 0xFF44AA44  # 亮綠（文字 / 指示器）

# 錯誤 / 警告（紅色系）
ARGB_ERROR_BG       = 0xFF5E2A2A  # 深紅背景
ARGB_ERROR_HOVER    = 0xFF703333  # 懸停亮紅
ARGB_ERROR_LABEL    = 0xFFAA4444  # 亮紅（文字 / 指示器）

# 文字層
ARGB_TEXT_PRIMARY   = 0xFFDDDDDD  # 主要文字（亮灰）
ARGB_TEXT_SECONDARY = 0xFFAAAAAA  # 次要文字（中灰）
ARGB_TEXT_MUTED     = 0xFF888888  # 說明文字（暗灰）
ARGB_TEXT_WHITE     = 0xFFFFFFFF  # 純白（反色文字）

# 強調 / 圖示
ARGB_ICON_FOLDER    = 0xFFDCA550  # 資料夾圖示（金色）
ARGB_ICON_ROOT      = 0xFF50A5DC  # 根目錄圖示（藍色）
ARGB_TREE_SELECTED  = 0xFF44AA44  # TreeView 選取高亮


# ─────────────────────────────────────────────
#  ZIN_GLOBAL_STYLE — 全局樣式字典
#  用法：將此 dict 傳給最外層容器的 style 參數
#  例如：with ui.VStack(style=ZIN_GLOBAL_STYLE):
# ─────────────────────────────────────────────
ZIN_GLOBAL_STYLE = {

    # ── Button：預設狀態 ──────────────────
    "Button": {
        "background_color": ARGB_DEFAULT_BG,
        "border_radius": 4,
        "margin": 2,
    },
    "Button:hovered": {
        "background_color": ARGB_HOVER_BG,
    },
    "Button:pressed": {
        "background_color": ARGB_PRESSED_BG,
    },

    # ── Button.Correct：啟動 / 成功狀態（綠色） ──
    "Button.Correct": {
        "background_color": ARGB_CORRECT_BG,
        "border_radius": 4,
        "margin": 2,
    },
    "Button.Correct:hovered": {
        "background_color": ARGB_CORRECT_HOVER,
    },
    "Button.Correct:pressed": {
        "background_color": ARGB_CORRECT_LABEL,
    },

    # ── Button.Error：錯誤 / 警告狀態（紅色） ──
    "Button.Error": {
        "background_color": ARGB_ERROR_BG,
        "border_radius": 4,
        "margin": 2,
    },
    "Button.Error:hovered": {
        "background_color": ARGB_ERROR_HOVER,
    },
    "Button.Error:pressed": {
        "background_color": ARGB_ERROR_LABEL,
    },

    # ── ProgressBar ──────────────────────
    "ProgressBar": {
        "color": ARGB_CORRECT_LABEL,
        "background_color": ARGB_PANEL_BG,
    },

    # ── Label：訊息類型 ───────────────────
    "Label.Message": {
        "color": ARGB_TEXT_PRIMARY,
        "font_size": 13,
    },
    "Label.MessageError": {
        "color": ARGB_ERROR_LABEL,
        "font_size": 13,
    },
}
