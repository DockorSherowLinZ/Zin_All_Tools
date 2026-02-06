import omni.ext
from .window import SmartAssetsLibraryWindow

class SmartAssetsLibraryExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        # 建立獨立視窗實例
        self._window = SmartAssetsLibraryWindow(
            "Smart Assets Library", 
            width=1000, 
            height=700
        )
        # 確保視窗在啟動時是開啟狀態
        self._window.visible = True

    def on_shutdown(self):
        # 關閉時徹底銷毀 UI 資源防止內存洩漏
        if self._window:
            self._window.destroy()
            self._window = None