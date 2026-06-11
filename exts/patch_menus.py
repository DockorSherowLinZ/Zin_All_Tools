import os

EXT_DIRS = [
    r"c:\Users\iec141194\Desktop\Inventec\Zin\Zin_All_Tools\exts\tools_box\tools_box\extension.py",
    r"c:\Users\iec141194\Desktop\Inventec\Zin\Zin_All_Tools\exts\tw.zin.smart_align\smart_align\extension.py",
    r"c:\Users\iec141194\Desktop\Inventec\Zin\Zin_All_Tools\exts\tw.zin.smart_assembly\smart_assembly\extension.py",
    r"c:\Users\iec141194\Desktop\Inventec\Zin\Zin_All_Tools\exts\tw.zin.smart_assets_builder\smart_assets_builder\extension.py",
    r"c:\Users\iec141194\Desktop\Inventec\Zin\Zin_All_Tools\exts\tw.zin.smart_exploded\smart_exploded\extension.py",
    r"c:\Users\iec141194\Desktop\Inventec\Zin\Zin_All_Tools\exts\tw.zin.smart_measure\smart_measure\extension.py",
    r"c:\Users\iec141194\Desktop\Inventec\Zin\Zin_All_Tools\exts\tw.zin.smart_physics_setup\smart_physics_setup\extension.py",
    r"c:\Users\iec141194\Desktop\Inventec\Zin\Zin_All_Tools\exts\tw.zin.smart_reference\smart_reference\extension.py",
]

REPLACE_BLOCK = """    def _build_menu(self):
        try:
            import omni.kit.menu.utils
            self._menu = omni.kit.menu.utils.add_menu_items([
                omni.kit.menu.utils.MenuItemDescription(
                    name=self.WINDOW_NAME,
                    onclick_fn=lambda *args: self._toggle_window(None, True)
                )
            ], "Zin_All_Tools")
            self._menu_added = True
        except Exception: pass

    def _remove_menu(self):
        try:
            import omni.kit.menu.utils
            if hasattr(self, '_menu') and self._menu:
                omni.kit.menu.utils.remove_menu_items(self._menu, "Zin_All_Tools")
                self._menu = None
        except Exception: pass"""

for file_path in EXT_DIRS:
    if not os.path.exists(file_path):
        continue
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    out_lines = []
    skip = False
    for line in lines:
        if line.startswith("    def _build_menu(self):"):
            skip = True
            out_lines.append(REPLACE_BLOCK + "\n")
            continue
        
        # Stop skipping if we hit the next function after _remove_menu
        # Wait, if we are skipping, we skip until we hit the next function definition 
        # (which is usually `def _toggle_window(self, menu, value):`)
        if skip and line.startswith("    def _toggle_window(self"):
            skip = False
        
        if not skip:
            out_lines.append(line)
            
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(out_lines)
    print(f"Patched {file_path}")
