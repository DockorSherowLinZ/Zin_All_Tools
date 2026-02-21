# =============================================================================
# zin_components.py
# Zin All Tools — Custom UI Component Library
#
# 封裝可複用的 omni.ui 元件，統一狀態管理。
# =============================================================================

import omni.ui as ui


# ─────────────────────────────────────────────
#  ZinButton
#  包裝 omni.ui.Button，支援三種視覺狀態：
#    "default" → Button（深灰）
#    "correct" → Button.Correct（綠色）
#    "error"   → Button.Error（紅色）
#
#  狀態透過 omni.ui 的 name 屬性對應到
#  ZIN_GLOBAL_STYLE 中的對應 CSS 類別。
# ─────────────────────────────────────────────

class ZinButton:
    """
    可複用的 Zin 設計系統按鈕元件。

    用法範例：
        btn = ZinButton("Browse", state="default", clicked_fn=my_fn, width=60)
        btn_load = ZinButton("Load", state="correct", clicked_fn=my_load_fn, width=60)

        # 動態切換狀態（例如：在操作完成後變綠）
        btn.set_state("correct")
        btn.set_state("error")
        btn.set_state("default")

        # 取得底層 omni.ui.Button（如需進階操作）
        btn.widget.enabled = False
    """

    # state 字串 → omni.ui Button.name 屬性對應表
    # name="" 代表使用預設的 "Button" 樣式
    # name="Correct" 代表使用 "Button.Correct" 樣式
    _STATE_NAME_MAP = {
        "default": "",
        "correct": "Correct",
        "error":   "Error",
    }

    def __init__(
        self,
        text: str,
        state: str = "default",
        clicked_fn=None,
        **kwargs
    ):
        """
        初始化 ZinButton。

        Args:
            text (str): 按鈕顯示文字。
            state (str): 初始視覺狀態。可選 "default", "correct", "error"。
            clicked_fn (callable): 點擊回呼函數，與 omni.ui.Button 相同。
            **kwargs: 其餘參數直接傳給 omni.ui.Button（如 width, height 等）。
        """
        self._state = state
        name = self._STATE_NAME_MAP.get(state, "")
        self._btn = ui.Button(text, name=name, clicked_fn=clicked_fn, **kwargs)

    # 各狀態對應的直接樣式（確保 Kit 109 環境下強制刷新）
    _STATE_STYLE_MAP = {
        "default": {
            "Button": {"background_color": 0xFF343432, "border_radius": 4},
            "Button:hovered": {"background_color": 0xFF4A4A48},
            "Button:pressed": {"background_color": 0xFF5A5A58},
        },
        "correct": {
            "Button": {"background_color": 0xFF2A5E2A, "border_radius": 4},
            "Button:hovered": {"background_color": 0xFF33703A},
            "Button:pressed": {"background_color": 0xFF44AA44},
        },
        "error": {
            "Button": {"background_color": 0xFF5E2A2A, "border_radius": 4},
            "Button:hovered": {"background_color": 0xFF703333},
            "Button:pressed": {"background_color": 0xFFAA4444},
        },
    }

    def set_state(self, new_state: str):
        """
        動態切換按鈕的視覺狀態。

        同時設定 name（語意）和 style（強制覆蓋），
        確保在 Kit 109 中樣式繼承失效時仍能正確顯示顏色。

        Args:
            new_state (str): 目標狀態，可選 "default", "correct", "error"。
        """
        if new_state not in self._STATE_NAME_MAP:
            print(f"[ZinButton] Warning: unknown state '{new_state}', using 'default'.")
            new_state = "default"

        self._state = new_state
        self._btn.name = self._STATE_NAME_MAP[new_state]
        # 直接注入 style，強制 Kit 109 立即刷新顏色
        self._btn.style = self._STATE_STYLE_MAP[new_state]

    @property
    def state(self) -> str:
        """返回目前狀態字串。"""
        return self._state

    @property
    def widget(self) -> ui.Button:
        """返回底層 omni.ui.Button 實例，供進階操作使用。"""
        return self._btn

    # ── 轉接常用屬性，方便直接操作 ──────────────

    @property
    def text(self) -> str:
        return self._btn.text

    @text.setter
    def text(self, value: str):
        self._btn.text = value

    @property
    def enabled(self) -> bool:
        return self._btn.enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._btn.enabled = value

    @property
    def visible(self) -> bool:
        return self._btn.visible

    @visible.setter
    def visible(self, value: bool):
        self._btn.visible = value
