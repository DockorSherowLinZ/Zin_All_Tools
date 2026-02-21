import omni.ext
import omni.ui as ui
import omni.kit.ui
import omni.kit.actions.core
from .window import SmartAssetsLibraryWindow

class SmartAssetsLibraryExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        # 靜音 Isaac Sim 內建 Content Browser 的縮圖不匹配 Warning（上游 bug，無法修復）
        import logging
        logging.getLogger("omni.kit.browser.folder.core.models.folder_browser_data").setLevel(logging.ERROR)

        # 1. 儲存 extension_id (這是修復的關鍵)
        self._ext_id = ext_id

        self._window = SmartAssetsLibraryWindow("Smart Assets Library", width=1000, height=700)

        
        # 定義 ID
        self._action_id = "EMBridge_window_zintools_smart_assets_library"
        self._menu_path = "Window/ZinTools/Smart Assets Library"
        
        # 註冊選單
        editor_menu = omni.kit.ui.get_editor_menu()
        if editor_menu:
            self._menu = editor_menu.add_item(self._menu_path, self._toggle_window, True)

    def _toggle_window(self, menu, value):
        if self._window:
            self._window.visible = value

    def on_shutdown(self):
        # 1. 移除選單（若已被銷毀則靜默忽略）
        try:
            editor_menu = omni.kit.ui.get_editor_menu()
            if editor_menu:
                editor_menu.remove_item(self._menu_path)
        except Exception:
            pass

        # 2. 移除所有 Actions（一次清除，避免 reload 時重複註冊 Warning）
        try:
            import omni.kit.actions.core
            action_registry = omni.kit.actions.core.get_action_registry()

            # 2a. 明確移除 editor menu 用 base name 註冊的 action（無版本後綴）
            if hasattr(self, "_action_id"):
                action_registry.deregister_action("smart_assets_library", self._action_id)

            # 2b. 清除以完整 ext_id（含版本）註冊的其他 actions
            if hasattr(self, "_ext_id") and self._ext_id:
                action_registry.deregister_all_actions_for_extension(self._ext_id)
        except Exception:
            pass

        # 3. 銷毀視窗
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
