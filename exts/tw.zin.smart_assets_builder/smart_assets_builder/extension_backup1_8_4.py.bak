# SmartAssetsBuilder — SmartAssetsBuilderExtension.py
# Version: v1.8.13 (Fix: Alignment Attribute Error)

import os
import fnmatch
import traceback
import posixpath
import shutil
import asyncio
from typing import List, Tuple

import omni.ext
import omni.ui as ui
import omni.kit.app
from pxr import Usd, UsdGeom, Sdf, Gf

# Optional Nucleus support
try:
    import omni.client
except Exception:
    omni = None


# ============================== Path / IO Utilities ============================
def _is_ov_url(url: str) -> bool:
    return url.startswith("omniverse://") or url.startswith("omni://")

def _dirname(p: str) -> str:
    if _is_ov_url(p):
        return p.rsplit("/", 1)[0] if "/" in p else p
    return os.path.dirname(p)

def _join(base: str, *more: str) -> str:
    if _is_ov_url(base):
        return "/".join([base.rstrip("/")] + [m.strip("/") for m in more])
    return os.path.join(base, *more)

def _abs(path_or_url: str) -> str:
    return path_or_url if _is_ov_url(path_or_url) else os.path.abspath(path_or_url)

def _ensure_usd_ext(p: str) -> str:
    if "." not in p:
        return p + ".usd"
    root, ext = p.rsplit(".", 1)
    return p if ext.lower() == "usd" else root + ".usd"

def _ensure_dir_local(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def _ensure_dir_ov(url: str) -> None:
    if omni is None:
        return
    u = url.rstrip("/")
    if "://" in u:
        scheme, rest = u.split("://", 1)
        netloc, *segs = rest.split("/")
        cur = f"{scheme}://{netloc}"
        for s in segs:
            if not s:
                continue
            cur = f"{cur}/{s}"
            rc, _ = omni.client.stat(cur)
            if rc != omni.client.Result.OK:
                omni.client.create_folder(cur)
    else:
        rc, _ = omni.client.stat(u)
        if rc != omni.client.Result.OK:
            omni.client.create_folder(u)

def _exists(p: str) -> bool:
    if _is_ov_url(p):
        if omni is None:
            return False
        rc, info = omni.client.stat(p)
        return rc == omni.client.Result.OK and not (info.flags & int(omni.client.ItemFlags.CAN_HAVE_CHILDREN))
    return os.path.isfile(p)

def _split_ov(url: str):
    scheme, rest = url.split("://", 1)
    netloc, *path_parts = rest.split("/")
    return scheme, netloc, "/" + "/".join(path_parts)

def _relref(from_file: str, to_file: str) -> str:
    if _is_ov_url(from_file) and _is_ov_url(to_file):
        try:
            sf, sfn, sp = _split_ov(from_file)
            st, stn, tp = _split_ov(to_file)
            if sf == st and sfn == stn:
                from_dir = posixpath.dirname(sp)
                return posixpath.relpath(tp, start=from_dir)
        except Exception:
            pass
        return to_file
    from_dir = os.path.dirname(_abs(from_file))
    tgt_abs = _abs(_ensure_usd_ext(to_file))
    try:
        rel = os.path.relpath(tgt_abs, start=from_dir)
    except Exception:
        return tgt_abs
    return rel.replace("\\", "/")

def _dotify_rel(rel_path: str) -> str:
    if not rel_path:
        return rel_path
    if rel_path.startswith(("omniverse://", "omni://", "/", "../", "./")):
        return rel_path
    return f"./{rel_path}"

# ======================= File IO =======================
def _read_bytes(path_or_url: str):
    if _is_ov_url(path_or_url):
        if omni is None: return None
        rc, content = omni.client.read_file(path_or_url)
        return bytes(content) if rc == omni.client.Result.OK else None
    else:
        try:
            with open(path_or_url, "rb") as f: return f.read()
        except Exception: return None

def _write_bytes(path_or_url: str, data: bytes) -> bool:
    if _is_ov_url(path_or_url):
        if omni is None: return False
        _ensure_dir_ov(_dirname(path_or_url))
        rc = omni.client.write_file(path_or_url, data)
        return rc == omni.client.Result.OK
    else:
        _ensure_dir_local(os.path.dirname(path_or_url))
        with open(path_or_url, "wb") as f: f.write(data)
        return True

def _copy_file_any_scheme(src: str, dst: str, overwrite: bool, log_fn) -> bool:
    if _abs(src) == _abs(dst): return True
    if _exists(dst):
        if not overwrite: return True
        if _is_ov_url(dst):
            try: omni.client.delete(dst)
            except: pass
    if _is_ov_url(src) == _is_ov_url(dst):
        if _is_ov_url(src):
            rc = omni.client.copy(src, dst)[0] if hasattr(omni.client, "copy") else omni.client.Result.ERROR
            return rc == omni.client.Result.OK
        else:
            _ensure_dir_local(os.path.dirname(dst))
            shutil.copy2(src, dst)
            return True
    data = _read_bytes(src)
    if data is None: return False
    return _write_bytes(dst, data)

def _copy_materials_any_scheme(src_core_dir: str, out_core_dir: str, overwrite: bool, log_fn) -> bool:
    src_mat = _join(src_core_dir, "Materials")
    dst_mat = _join(out_core_dir, "Materials")
    if _is_ov_url(src_mat):
        if omni is None: return False
        rc, info = omni.client.stat(src_mat)
        if rc != omni.client.Result.OK or not (info.flags & int(omni.client.ItemFlags.CAN_HAVE_CHILDREN)): return False
    else:
        if not os.path.isdir(src_mat): return False

    def walk_and_copy(u_src, u_dst):
        if _is_ov_url(u_src):
            rc, entries = omni.client.list(u_src.rstrip("/"))
            if int(rc) != int(omni.client.Result.OK): return
            _ensure_dir_ov(u_dst)
            for e in entries:
                name = e.relative_path
                if not name or name in (".", ".."): continue
                s, d = u_src.rstrip("/") + "/" + name, u_dst.rstrip("/") + "/" + name
                if bool(e.flags & int(omni.client.ItemFlags.CAN_HAVE_CHILDREN)): walk_and_copy(s, d)
                else: _copy_file_any_scheme(s, d, overwrite, log_fn)
        else:
            os.makedirs(u_dst, exist_ok=True)
            for f in os.listdir(u_src):
                s, d = os.path.join(u_src, f), os.path.join(u_dst, f)
                if os.path.isdir(s): walk_and_copy(s, d)
                else: _copy_file_any_scheme(s, d, overwrite, log_fn)
    walk_and_copy(src_mat, dst_mat)
    return True

# ============================== USD Helpers ==============================
def _create_file_backed_stage(out_path: str) -> Usd.Stage:
    out_path = _ensure_usd_ext(out_path)
    (_ensure_dir_ov if _is_ov_url(out_path) else _ensure_dir_local)(_dirname(out_path))
    if _exists(out_path):
        if _is_ov_url(out_path): omni.client.delete(out_path)
        else: os.remove(out_path)
    root = Sdf.Layer.CreateNew(out_path)
    return Usd.Stage.Open(root)

def _save(stage: Usd.Stage) -> str:
    stage.GetRootLayer().Save()
    return stage.GetRootLayer().identifier

def _derive_names(src_path: str, id_suffix: str) -> Tuple[str, str, str, str]:
    base = src_path.rsplit("/", 1)[-1] if _is_ov_url(src_path) else os.path.basename(src_path)
    name, _, _ = base.partition(".")
    core = name[4:] if name.lower().startswith("max_") else name
    id_f = f"id_{core}_{id_suffix}.usd" if id_suffix else f"id_{core}.usd"
    return core, f"asset_{core}.usd", f"{core}.usd", id_f

def _list_local(folder: str, pattern: str, recurse: bool) -> List[str]:
    if not os.path.isdir(folder): return []
    out = []
    if recurse:
        for r, d, files in os.walk(folder):
            for f in files:
                if fnmatch.fnmatch(f.lower(), pattern.lower()): out.append(os.path.join(r, f))
    else:
        out = [os.path.join(folder, f) for f in os.listdir(folder) if fnmatch.fnmatch(f.lower(), pattern.lower())]
    return sorted(out)

def _list_nucleus(url: str, pattern: str, recurse: bool) -> List[str]:
    if omni is None: return []
    res = []
    def walk(u):
        rc, entries = omni.client.list(u.rstrip("/"))
        if int(rc) != int(omni.client.Result.OK): return
        for e in entries:
            name = e.relative_path
            if not name or name in (".", ".."): continue
            child = u.rstrip("/") + "/" + name
            if bool(e.flags & int(omni.client.ItemFlags.CAN_HAVE_CHILDREN)):
                if recurse: walk(child)
            elif fnmatch.fnmatch(name.lower(), pattern.lower()): res.append(child)
    walk(url)
    return sorted(res)


# ========================================================
#  SmartAssetsBuilder Widget
# ========================================================
class SmartAssetsBuilderWidget:
    def __init__(self):
        self._found = []
        self._STYLE_HEAD  = {"font_size": 18, "color": 0xFFDDDDDD}
        self._STYLE_LABEL = {"color": 0xFFAAAAAA}
        self._build_task = None

    def startup(self): self._found = []
    def shutdown(self):
        if self._build_task: self._build_task.cancel()

    def build_ui_layout(self):
        scroll_frame = ui.ScrollingFrame(
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON,
            style={"padding": 15}
        )
        COMPACT_STYLE = {"font_size": 14, "padding": 2}

        with scroll_frame:
            with ui.VStack(spacing=10, height=0, alignment=ui.Alignment.TOP):
                ui.Label("SmartAssetsBuilder (v1.8.13)", style=self._STYLE_HEAD)
                ui.Label("Source > Scan > List > Output Root > Start", style={"color": 0xFF888888})
                ui.Spacer(height=5)

                with ui.VStack(spacing=6):
                    ui.Label("Source Folder URL", style=self._STYLE_LABEL)
                    self._folder_field = ui.StringField(height=22, style=COMPACT_STYLE)
                    with ui.HStack(spacing=10, height=22):
                        ui.Label("Filename filter", width=0, style=self._STYLE_LABEL)
                        self._filter_field = ui.StringField(style=COMPACT_STYLE)
                        self._filter_field.model.set_value("max_*.usd")
                    with ui.HStack(height=22, spacing=5):
                        self._recurse_cb = ui.CheckBox(width=20); self._recurse_cb.model.set_value(True)
                        ui.Label("Recurse (Search inside sub-folders)", style=self._STYLE_LABEL)
                    with ui.HStack(spacing=10, height=22):
                        ui.Label("ID Suffix", width=0, style=self._STYLE_LABEL)
                        self._id_field = ui.StringField(style=COMPACT_STYLE)
                        ui.Spacer(width=15)
                        self._overwrite_cb = ui.CheckBox(width=20); self._overwrite_cb.model.set_value(False)
                        ui.Label("Overwrite", style=self._STYLE_LABEL)
                    
                    # [修正] 使用 V_CENTER 代替 CENTER_VERTICAL
                    with ui.HStack(spacing=10, height=30, alignment=ui.Alignment.V_CENTER):
                        ui.Button("Scan", clicked_fn=self._on_scan, width=120, height=30)
                        self._count_label = ui.Label("Ready to scan...", style={"color": 0xFF888888})

                ui.Spacer(height=5)
                with ui.VStack(spacing=6):
                    ui.Label("Output Root URL", style=self._STYLE_LABEL)
                    self._out_root_field = ui.StringField(height=22, style=COMPACT_STYLE)
                    ui.Label("Material Overlay Path (Optional)", style=self._STYLE_LABEL)
                    self._mat_field = ui.StringField(height=22, style=COMPACT_STYLE)
                    with ui.HStack(spacing=5, height=22):
                        self._inplace_cb = ui.CheckBox(width=20); self._inplace_cb.model.set_value(False)
                        ui.Label("Allow Same Root (in-place)", style={"color": 0xFFDDDDDD})

                ui.Spacer(height=10)
                
                # [修正] 使用 V_CENTER 代替 CENTER_VERTICAL
                with ui.HStack(spacing=10, height=36, alignment=ui.Alignment.V_CENTER):
                    ui.Button("Start Build", clicked_fn=self._on_start, width=120, height=30)
                    with ui.HStack(spacing=8, alignment=ui.Alignment.V_CENTER):
                        self._progress_label = ui.Label("Ready", width=45, style={"color": 0xFFAAAAAA})
                        with ui.ZStack(width=200, height=22):
                            self._progress_model = ui.SimpleFloatModel(0.0)
                            self._progress_bar = ui.ProgressBar(self._progress_model, style={"color": 0xFF44AA44, "background_color": 0xFF333333, "font_size": 0})
                            self._progress_overlay_label = ui.Label("0%", alignment=ui.Alignment.CENTER, style={"color": 0xFFFFFFFF, "font_size": 12})
        return scroll_frame

    def _on_scan(self):
        url = self._folder_field.model.get_value_as_string().strip()
        pattern = self._filter_field.model.get_value_as_string().strip()
        recurse = self._recurse_cb.model.get_value_as_bool()
        if not url: return
        self._found = (_list_nucleus(url, pattern, recurse) if _is_ov_url(url) else _list_local(url, pattern, recurse))
        self._count_label.text = f"Found: {len(self._found)} items"

    def _on_start(self):
        if self._build_task: self._build_task.cancel()
        self._build_task = asyncio.ensure_future(self._run_build())

    async def _run_build(self):
        n = len(self._found)
        if n == 0: return
        out_root = self._out_root_field.model.get_value_as_string().strip()
        suffix = self._id_field.model.get_value_as_string().strip()
        over = self._overwrite_cb.model.get_value_as_bool()
        mat = self._mat_field.model.get_value_as_string().strip().strip('"')
        
        for i, src in enumerate(self._found, 1):
            core, asset, main, id_f = _derive_names(src, suffix)
            out_dir = _join(out_root, core)
            asset_p, main_p, id_p = _ensure_usd_ext(_join(out_dir, asset)), _ensure_usd_ext(_join(out_dir, main)), _ensure_usd_ext(_join(out_root, id_f))
            
            if not over and _exists(id_p): continue
            
            (_ensure_dir_ov(out_dir) if _is_ov_url(out_dir) else _ensure_dir_local(out_dir))
            max_dst = _join(out_dir, os.path.basename(src))
            _copy_file_any_scheme(src, max_dst, over, print)
            _copy_materials_any_scheme(_dirname(src), out_dir, over, print)
            
            # 此處呼叫原本的 USD 建構邏輯...
            # 由於邏輯簡化，請確保 _build_asset 等函式存在於上方
            try:
                stage_a = _create_file_backed_stage(asset_p)
                UsdGeom.SetStageUpAxis(stage_a, UsdGeom.Tokens.z)
                UsdGeom.SetStageMetersPerUnit(stage_a, 0.01)
                stage_a.SetDefaultPrim(UsdGeom.Xform.Define(stage_a, "/World").GetPrim())
                rel_max = _dotify_rel(_relref(asset_p, max_dst))
                layers = [rel_max]
                if mat: layers.insert(0, _dotify_rel(_relref(asset_p, mat)))
                stage_a.GetRootLayer().subLayerPaths = layers
                _save(stage_a)

                stage_m = _create_file_backed_stage(main_p)
                UsdGeom.SetStageUpAxis(stage_m, UsdGeom.Tokens.z)
                UsdGeom.SetStageMetersPerUnit(stage_m, 0.01)
                stage_m.SetDefaultPrim(UsdGeom.Xform.Define(stage_m, "/World").GetPrim())
                prim_m = stage_m.DefinePrim(f"/World/ASSET/asset_{core}")
                prim_m.GetReferences().AddReference(_relref(main_p, asset_p))
                _save(stage_m)

                stage_i = _create_file_backed_stage(id_p)
                UsdGeom.SetStageUpAxis(stage_i, UsdGeom.Tokens.z)
                UsdGeom.SetStageMetersPerUnit(stage_i, 0.01)
                stage_i.SetDefaultPrim(UsdGeom.Xform.Define(stage_i, "/World").GetPrim())
                prim_i = stage_i.DefinePrim(f"/World/{core}")
                prim_i.GetReferences().AddReference(_relref(id_p, main_p))
                _save(stage_i)
            except Exception as e:
                print(f"Error building {core}: {e}")

            pct = int((i/n)*100)
            self._progress_model.as_float = float(pct)
            self._progress_overlay_label.text = f"{pct}%"
            self._progress_label.text = f"{pct}%"
            await omni.kit.app.get_app().next_update_async()
        
        self._progress_label.text = "Done"

# ========================================================
#  Extension Wrapper
# ========================================================
class SmartAssetsBuilderExtension(omni.ext.IExt):
    WINDOW_NAME = "SmartAssetsBuilder"
    MENU_PATH = f"Zin Tools/{WINDOW_NAME}"

    def __init__(self):
        super().__init__()
        self._widget = SmartAssetsBuilderWidget()
        self._window = None
        self._menu_added = False

    def on_startup(self, ext_id): self._build_menu()
    def on_shutdown(self):
        self._remove_menu()
        if self._widget: self._widget.shutdown()
        if self._window: self._window.destroy()

    def _build_menu(self):
        m = omni.kit.ui.get_editor_menu()
        if m: m.add_item(self.MENU_PATH, self._toggle_window, toggle=True, value=False); self._menu_added = True

    def _remove_menu(self):
        if self._menu_added:
            m = omni.kit.ui.get_editor_menu()
            if m: m.remove_item(self.MENU_PATH)

    def _toggle_window(self, menu, value):
        if value:
            if not self._window:
                self._window = ui.Window(self.WINDOW_NAME, width=680, height=620)
                self._window.set_visibility_changed_fn(lambda v: m.set_value(self.MENU_PATH, v) if (m:=omni.kit.ui.get_editor_menu()) else None)
                with self._window.frame: self._widget.build_ui_layout()
            self._window.visible = True
        elif self._window: self._window.visible = False

    def startup_logic(self): self._widget.startup()
    def shutdown_logic(self): self._widget.shutdown()
    def build_ui_layout(self): return self._widget.build_ui_layout()