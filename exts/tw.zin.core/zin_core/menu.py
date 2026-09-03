"""Zin All Tools 共用的選單與視窗生命週期。

先前每個 extension 都各自複製一份 `_build_menu` / `_remove_menu` /
`_on_visibility_changed`，且全部以 `except Exception: pass` 靜默失敗。
集中在此可讓行為一致，並讓失敗以 carb 日誌呈現而非被吞掉。
"""

import carb

ZIN_MENU_GROUP = "Zin_All_Tools"


class ZinMenuMixin:
    """為 extension 提供 Zin_All_Tools 選單項目的註冊與移除。

    使用者需自行定義：
        WINDOW_NAME — 選單與視窗標題
        MENU_PATH   — 選單完整路徑
        _toggle_window(menu, value) — 開關視窗
    """

    WINDOW_NAME = "Zin Tool"
    MENU_PATH = f"{ZIN_MENU_GROUP}/Zin Tool"

    def _build_menu(self):
        self._menu = None
        self._menu_added = False
        try:
            import omni.kit.menu.utils

            self._menu = omni.kit.menu.utils.add_menu_items(
                [
                    omni.kit.menu.utils.MenuItemDescription(
                        name=self.WINDOW_NAME,
                        onclick_fn=lambda *args: self._toggle_window(None, True),
                    )
                ],
                ZIN_MENU_GROUP,
            )
            self._menu_added = True
        except Exception as exc:
            carb.log_warn(f"[{self.WINDOW_NAME}] Failed to register menu item: {exc}")

    def _remove_menu(self):
        if not getattr(self, "_menu", None):
            self._menu_added = False
            return
        try:
            import omni.kit.menu.utils

            omni.kit.menu.utils.remove_menu_items(self._menu, ZIN_MENU_GROUP)
        except Exception as exc:
            carb.log_warn(f"[{self.WINDOW_NAME}] Failed to remove menu item: {exc}")
        finally:
            self._menu = None
            self._menu_added = False

    def _on_visibility_changed(self, visible):
        if not getattr(self, "_menu_added", False):
            return
        try:
            import omni.kit.ui

            omni.kit.ui.get_editor_menu().set_value(self.MENU_PATH, bool(visible))
        except Exception as exc:
            carb.log_verbose(f"[{self.WINDOW_NAME}] Menu checkmark sync skipped: {exc}")
