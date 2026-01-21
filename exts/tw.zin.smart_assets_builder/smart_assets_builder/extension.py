# SmartAssetsBuilder — extension.py (USD Composer / Create 2023.2.5)
# Version: v1.10.5 (UI Cleaned: Removed Headers, Light Gray Lines, Compact, Async)

import os
import fnmatch
import traceback
import posixpath
import shutil
import asyncio
from typing import List, Tuple

import omni.ext
import omni.ui as ui
import omni.kit.ui 
import omni.kit.app
from pxr import Usd, UsdGeom, Sdf, Gf, Kind

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


def _norm_local(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


def _norm_ov(p: str) -> Tuple[str, str, str]:
    s, n, path = _split_ov(p)
    return s, n, posixpath.normpath(path)


def _is_same_path(a: str, b: str) -> bool:
    if _is_ov_url(a) and _is_ov_url(b):
        return _norm_ov(a) == _norm_ov(b)
    if (not _is_ov_url(a)) and (not _is_ov_url(b)):
        return _norm_local(a) == _norm_local(b)
    return False


def _is_inside(child: str, parent: str) -> bool:
    """True if `child` is strictly inside `parent` (not equal)."""
    if _is_ov_url(child) and _is_ov_url(parent):
        sc, nc, pc = _norm_ov(child)
        sp, np, pp = _norm_ov(parent)
        if sc != sp or nc != np:
            return False
        if pc == pp:
            return False
        return pc.startswith(pp + "/")
    if (not _is_ov_url(child)) and (not _is_ov_url(parent)):
        c = _norm_local(child)
        p = _norm_local(parent)
        if c == p:
            return False
        try:
            rel = os.path.relpath(c, start=p)
            return rel != "." and not rel.startswith("..")
        except Exception:
            return False
    return False


def _relref(from_file: str, to_file: str) -> str:
    """Relative reference if same Nucleus host; otherwise absolute. Local uses os.path.relpath."""
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
    """Make 'name.usd' -> './name.usd' for subLayers to match sample."""
    if not rel_path:
        return rel_path
    if rel_path.startswith(("omniverse://", "omni://", "/", "../", "./")):
        return rel_path
    return f"./{rel_path}"


# ======================= File IO (supports cross-scheme) =======================

def _read_bytes(path_or_url: str):
    if _is_ov_url(path_or_url):
        if omni is None:
            return None
        rc, content = omni.client.read_file(path_or_url)
        return bytes(content) if rc == omni.client.Result.OK else None
    else:
        try:
            with open(path_or_url, "rb") as f:
                return f.read()
        except Exception:
            return None


def _write_bytes(path_or_url: str, data: bytes) -> bool:
    if _is_ov_url(path_or_url):
        if omni is None:
            return False
        _ensure_dir_ov(_dirname(path_or_url))
        rc = omni.client.write_file(path_or_url, data)
        return rc == omni.client.Result.OK
    else:
        _ensure_dir_local(os.path.dirname(path_or_url))
        with open(path_or_url, "wb") as f:
            f.write(data)
        return True


def _copy_file_any_scheme(src: str, dst: str, overwrite: bool, log_fn) -> bool:
    """Copy src->dst even across local/Nucleus. Returns True if present at dst (copied or already there)."""
    if _is_same_path(src, dst):
        return True

    if _exists(dst):
        if not overwrite:
            log_fn("[INFO] Exists, skip copy.")
            return True
        if _is_ov_url(dst):
            try:
                omni.client.delete(dst)
            except Exception:
                pass

    # Same-scheme fast path
    if _is_ov_url(src) == _is_ov_url(dst):
        if _is_ov_url(src):
            rc = omni.client.copy(src, dst)[0] if hasattr(omni.client, "copy") else omni.client.Result.ERROR
            if rc != omni.client.Result.OK:
                log_fn(f"[ERROR] Nucleus copy failed ({rc})")
                return False
            return True
        else:
            _ensure_dir_local(os.path.dirname(dst))
            shutil.copy2(src, dst)
            return True

    # Cross-scheme: read then write
    data = _read_bytes(src)
    if data is None:
        log_fn("[ERROR] Read failed (cross-scheme).")
        return False
    ok = _write_bytes(dst, data)
    if not ok:
        log_fn("[ERROR] Write failed (cross-scheme).")
    return ok


def _copy_materials_any_scheme(src_core_dir: str, out_core_dir: str, overwrite: bool, log_fn) -> bool:
    """Recursively copy 'Materials' from src_core_dir to out_core_dir across local/Nucleus, loop-safe."""
    src_mat = _join(src_core_dir, "Materials") if _is_ov_url(src_core_dir) else os.path.join(src_core_dir, "Materials")
    dst_mat = _join(out_core_dir, "Materials") if _is_ov_url(out_core_dir) else os.path.join(out_core_dir, "Materials")

    # Existence check
    if _is_ov_url(src_mat):
        if omni is None:
            return False
        rc, info = omni.client.stat(src_mat)
        if rc != omni.client.Result.OK or not (info.flags & int(omni.client.ItemFlags.CAN_HAVE_CHILDREN)):
            return False
    else:
        if not os.path.isdir(src_mat):
            return False

    # Loop-safety (defensive; on_start already guards)
    if _is_same_path(out_core_dir, src_core_dir) or _is_inside(out_core_dir, src_core_dir) or _is_inside(src_core_dir, out_core_dir):
        log_fn("[WARN] Loop risk; skip Materials copy.")
        return False

    def _ensure_dir_any(d):
        (_ensure_dir_ov if _is_ov_url(d) else _ensure_dir_local)(d)

    # Nucleus -> Nucleus: per-file copy
    if _is_ov_url(src_mat) and _is_ov_url(dst_mat):
        def walk(u_src: str, u_dst: str):
            rc, entries = omni.client.list(u_src.rstrip("/"))
            if int(rc) != int(omni.client.Result.OK):
                return
            _ensure_dir_ov(u_dst)
            for e in entries:
                name = e.relative_path
                if not name or name in (".", ".."):
                    continue
                c_src = u_src.rstrip("/") + "/" + name
                c_dst = u_dst.rstrip("/") + "/" + name
                is_dir = bool(e.flags & int(omni.client.ItemFlags.CAN_HAVE_CHILDREN))
                if is_dir:
                    walk(c_src, c_dst)
                else:
                    if _exists(c_dst) and not overwrite:
                        continue
                    if _exists(c_dst) and overwrite:
                        try: omni.client.delete(c_dst)
                        except Exception: pass
                    rc2 = omni.client.copy(c_src, c_dst)[0] if hasattr(omni.client, "copy") else omni.client.Result.ERROR
                    if rc2 != omni.client.Result.OK:
                        log_fn(f"[ERROR] Copy failed: {c_src} → {c_dst} ({rc2})")
        walk(src_mat, dst_mat)
        return True

    # General cases (local<->local / cross-scheme): iterate and read->write
    def _iter_local_files(root_dir: str):
        for r, _dirs, files in os.walk(root_dir, topdown=True):
            yield r, files

    def _iter_ov_files(root_url: str):
        rc, entries = omni.client.list(root_url.rstrip("/"))
        if int(rc) != int(omni.client.Result.OK):
            return
        files_here = []
        dirs_here = []
        for e in entries:
            name = e.relative_path
            if not name or name in (".", ".."):
                continue
            is_dir = bool(e.flags & int(omni.client.ItemFlags.CAN_HAVE_CHILDREN))
            (dirs_here if is_dir else files_here).append(name)
        yield root_url, files_here
        for d in dirs_here:
            yield from _iter_ov_files(root_url.rstrip("/") + "/" + d)

    if _is_ov_url(src_mat):
        for parent, files in _iter_ov_files(src_mat):
            rel = posixpath.relpath(parent, start=src_mat)
            target_parent = dst_mat if rel == "." else (_join(dst_mat, rel) if _is_ov_url(dst_mat) else os.path.join(dst_mat, rel))
            _ensure_dir_any(target_parent)
            for f in files:
                s = parent.rstrip("/") + "/" + f
                d = (target_parent.rstrip("/") + "/" + f) if _is_ov_url(target_parent) else os.path.join(target_parent, f)
                if _exists(d) and not overwrite:
                    continue
                data = _read_bytes(s)
                if data is None:
                    log_fn(f"[ERROR] Read failed: {s}")
                    continue
                if not _write_bytes(d, data):
                    log_fn(f"[ERROR] Write failed: {d}")
        return True
    else:
        for parent, files in _iter_local_files(src_mat):
            rel = os.path.relpath(parent, start=src_mat)
            target_parent = dst_mat if rel == "." else (_join(dst_mat, rel) if _is_ov_url(dst_mat) else os.path.join(dst_mat, rel))
            _ensure_dir_any(target_parent)
            for f in files:
                s = os.path.join(parent, f)
                d = (target_parent.rstrip("/") + "/" + f) if _is_ov_url(target_parent) else os.path.join(target_parent, f)
                if _exists(d) and not overwrite:
                    continue
                data = _read_bytes(s)
                if data is None:
                    log_fn(f"[ERROR] Read failed: {s}")
                    continue
                if not _write_bytes(d, data):
                    log_fn(f"[ERROR] Write failed: {d}")
        return True


# ============================== USD Stage Helpers ==============================

def _create_file_backed_stage(out_path: str) -> Usd.Stage:
    out_path = _ensure_usd_ext(out_path)
    (_ensure_dir_ov if _is_ov_url(out_path) else _ensure_dir_local)(_dirname(out_path))
    root = Sdf.Layer.CreateNew(out_path)  # overwrite-friendly
    return Usd.Stage.Open(root)


def _save(stage: Usd.Stage) -> str:
    root = stage.GetRootLayer()
    root.Save()
    return root.identifier


def _set_stage_defaults(stage: Usd.Stage) -> None:
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 0.01)
    stage.SetTimeCodesPerSecond(60)
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(100)


# --------------------------- customLayerData presets ---------------------------

_RENDER_SETTINGS = {
    "rtx:debugView:pixelDebug:textColor":                  Gf.Vec3f(0.0, 1.0e18, 0.0),
    "rtx:fog:fogColor":                                    Gf.Vec3f(0.75, 0.75, 0.75),
    "rtx:index:regionOfInterestMax":                       Gf.Vec3f(0.0, 0.0, 0.0),
    "rtx:index:regionOfInterestMin":                       Gf.Vec3f(0.0, 0.0, 0.0),
    "rtx:iray:environment_dome_ground_position":           Gf.Vec3f(0.0, 0.0, 0.0),
    "rtx:iray:environment_dome_ground_reflectivity":       Gf.Vec3f(0.0, 0.0, 0.0),
    "rtx:iray:environment_dome_rotation_axis":             Gf.Vec3f(3.4028235e38, 3.4028235e38, 3.4028235e38),
    "rtx:post:backgroundZeroAlpha:backgroundDefaultColor": Gf.Vec3f(0.0, 0.0, 0.0),
    "rtx:post:colorcorr:contrast":                         Gf.Vec3f(1.0, 1.0, 1.0),
    "rtx:post:colorcorr:gain":                             Gf.Vec3f(1.0, 1.0, 1.0),
    "rtx:post:colorcorr:gamma":                            Gf.Vec3f(1.0, 1.0, 1.0),
    "rtx:post:colorcorr:offset":                           Gf.Vec3f(0.0, 0.0, 0.0),
    "rtx:post:colorcorr:saturation":                       Gf.Vec3f(1.0, 1.0, 1.0),
    "rtx:post:colorgrad:blackpoint":                       Gf.Vec3f(0.0, 0.0, 0.0),
    "rtx:post:colorgrad:contrast":                         Gf.Vec3f(1.0, 1.0, 1.0),
    "rtx:post:colorgrad:gain":                             Gf.Vec3f(1.0, 1.0, 1.0),
    "rtx:post:colorgrad:gamma":                            Gf.Vec3f(1.0, 1.0, 1.0),
    "rtx:post:colorgrad:lift":                             Gf.Vec3f(0.0, 0.0, 0.0),
    "rtx:post:colorgrad:multiply":                         Gf.Vec3f(1.0, 1.0, 1.0),
    "rtx:post:colorgrad:offset":                           Gf.Vec3f(0.0, 0.0, 0.0),
    "rtx:post:colorgrad:whitepoint":                       Gf.Vec3f(1.0, 1.0, 1.0),
    "rtx:post:lensDistortion:lensFocalLengthArray":        Gf.Vec3f(10.0, 30.0, 50.0),
    "rtx:post:lensFlares:anisoFlareFalloffX":              Gf.Vec3f(450.0, 475.0, 500.0),
    "rtx:post:lensFlares:anisoFlareFalloffY":              Gf.Vec3f(10.0, 10.0, 10.0),
    "rtx:post:tonemap:whitepoint":                         Gf.Vec3f(1.0, 1.0, 1.0),
    "rtx:raytracing:inscattering:singleScatteringAlbedo":  Gf.Vec3f(0.9, 0.9, 0.9),
    "rtx:raytracing:inscattering:transmittanceColor":      Gf.Vec3f(0.5, 0.5, 0.5),
    "rtx:sceneDb:ambientLightColor":                       Gf.Vec3f(0.1, 0.1, 0.1),
}

def _make_custom_layer_data(persp_pos: Gf.Vec3d, persp_tgt: Gf.Vec3d) -> dict:
    return {
        "cameraSettings": {
            "Front": {"position": Gf.Vec3d(50000.0, 0.0, 0.0), "radius": 500.0},
            "Perspective": {"position": persp_pos, "target": persp_tgt},
            "Right": {"position": Gf.Vec3d(0.0, -50000.0, 0.0), "radius": 500.0},
            "Top":   {"position": Gf.Vec3d(0.0, 0.0, 50000.0), "radius": 500.0},
            "boundCamera": "/OmniverseKit_Persp",
        },
        "navmeshSettings": {"agentHeight": 180.0, "agentRadius": 20.0, "excludeRigidBodies": True, "ver": 1, "voxelCeiling": 460.0},
        "omni_layer": {"locked": {}, "muteness": {}},
        "renderSettings": dict(_RENDER_SETTINGS),
        "xrSettings": {},
    }

_ASSET_CAM = (Gf.Vec3d(468.23583907821103, 207.3167254218987, 136.30348999707007),
              Gf.Vec3d(1.8999877335081692, 0.000004266803131258712, 111.00506298576693))

_MAIN_CAM  = (Gf.Vec3d(438.24681779843604, 222.6747569439535, 257.21875304644374),
              Gf.Vec3d(10.307273578659249, -7.256348633949841, 98.82433171214586))

_ID_CAM    = (Gf.Vec3d(563.6285775303645, 274.16293093872434, 178.3208850340164),
              Gf.Vec3d(1.8999929336483774, 0.00003321702774883306, 111.00497360562268))


# =============================== Builders / USD ================================

def _derive_names(src_path: str, id_suffix: str) -> Tuple[str, str, str, str]:
    base = src_path.rsplit("/", 1)[-1] if _is_ov_url(src_path) else os.path.basename(src_path)
    name, _, _ = base.partition(".")
    core = name[4:] if name.lower().startswith("max_") else name
    
    # [Logic Change] Handle empty suffix
    if id_suffix:
        id_filename = f"id_{core}_{id_suffix}.usd"
    else:
        id_filename = f"id_{core}.usd"

    return core, f"asset_{core}.usd", f"{core}.usd", id_filename


def _build_asset(out_path: str, sublayer_target: str, mat_path_override: str = "") -> str:
    stage = _create_file_backed_stage(out_path)
    _set_stage_defaults(stage)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())
    stage.GetRootLayer().customLayerData = _make_custom_layer_data(*_ASSET_CAM)
    
    # 1. Process max_{name}.usd (Base layer)
    rel_max = _dotify_rel(_relref(out_path, sublayer_target))
    
    # Prepare subLayer list
    layers = [rel_max]

    # 2. If material override path is specified, add it to the top (Index 0)
    if mat_path_override:
        raw_mat_path = _relref(out_path, mat_path_override)
        if ":" in raw_mat_path or raw_mat_path.startswith(("/", "\\")):
            rel_mat = raw_mat_path
        else:
            rel_mat = _dotify_rel(raw_mat_path)
        
        # Insert at the first position to ensure override
        layers.insert(0, rel_mat)

    # 3. Set subLayerPaths
    stage.GetRootLayer().subLayerPaths = layers
    
    _save(stage)
    return out_path


def _build_main(out_path: str, asset_path: str, core: str) -> str:
    stage = _create_file_backed_stage(out_path)
    _set_stage_defaults(stage)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())
    stage.GetRootLayer().customLayerData = _make_custom_layer_data(*_MAIN_CAM)
    UsdGeom.Scope.Define(stage, "/World/ASSET")
    prim = stage.DefinePrim(f"/World/ASSET/asset_{core}")
    prim.GetReferences().ClearReferences()
    prim.GetReferences().AddReference(_relref(out_path, asset_path))
    _save(stage)
    return out_path


def _build_id(out_path: str, main_path: str, core: str) -> str:
    stage = _create_file_backed_stage(out_path)
    _set_stage_defaults(stage)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())
    stage.GetRootLayer().customLayerData = _make_custom_layer_data(*_ID_CAM)
    
    # Create Prim
    prim = stage.DefinePrim(f"/World/{core}")
    
    # [Logic] Set Kind = component
    Usd.ModelAPI(prim).SetKind(Kind.Tokens.component)
    
    prim.GetReferences().ClearReferences()
    prim.GetReferences().AddReference(_relref(out_path, main_path))
    _save(stage)
    return out_path


# ================================== UI / Ext ==================================

class SmartAssetsBuilderExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self._ext_id = ext_id
        
        # [Safe Init] Ensure these are initialized here for standalone mode
        self._init_data()

        # Styles for log lines
        self._STYLE_HEAD  = {"font_size": 18, "color": 0xFFDDDDDD}
        self._STYLE_LABEL = {"color": 0xFFAAAAAA}   # Dimmed labels

        # Default behavior: build the floating window
        self._menu = None
        self._window = None
        
        # Add Menu Item under "Window" -> "SmartAssetsBuilder"
        try:
            editor_menu = omni.kit.ui.get_editor_menu()
            if editor_menu:
                self._menu = editor_menu.add_item(
                    "Window/SmartAssetsBuilder", 
                    self._on_menu_click, 
                    toggle=True, 
                    value=False
                )
        except Exception:
            pass

    def on_shutdown(self):
        if self._menu:
            try:
                omni.kit.ui.get_editor_menu().remove_item(self._menu)
                self._menu = None
            except:
                pass

        if getattr(self, "_window", None):
            self._window.destroy()
            self._window = None

    def _init_data(self):
        """Helper to initialize data structures if they don't exist."""
        if not hasattr(self, '_found'):
            self._found: List[str] = []
        if not hasattr(self, '_scan_root'):
            self._scan_root: str = ""
        if not hasattr(self, '_progress_bar'):
            self._progress_bar = None
        if not hasattr(self, '_progress_label'):
            self._progress_label = None
        if not hasattr(self, '_count_label'):
            self._count_label = None

    # ---------- Internal Listing Methods (Fix for NameError) ----------
    def _list_local(self, folder: str, pattern: str, recursive: bool) -> List[str]:
        if not os.path.isdir(folder):
            return []
        if not recursive:
            return sorted([os.path.join(folder, f) for f in os.listdir(folder) if fnmatch.fnmatch(f.lower(), pattern.lower())])
        out = []
        for root, _dirs, files in os.walk(folder):
            for f in files:
                if fnmatch.fnmatch(f.lower(), pattern.lower()):
                    out.append(os.path.join(root, f))
        return sorted(out)

    def _list_nucleus(self, url: str, pattern: str, recursive: bool) -> List[str]:
        if omni is None:
            return []
        result: List[str] = []

        def walk(u: str):
            rc, entries = omni.client.list(u.rstrip("/"))
            if int(rc) != int(omni.client.Result.OK):
                return
            for e in entries:
                name = e.relative_path
                if not name or name in (".", ".."):
                    continue
                child = u.rstrip("/") + "/" + name
                is_dir = bool(e.flags & int(omni.client.ItemFlags.CAN_HAVE_CHILDREN))
                if is_dir:
                    if recursive:
                        walk(child)
                else:
                    if fnmatch.fnmatch(name.lower(), pattern.lower()):
                        result.append(child)

        walk(url)
        return sorted(result)

    # ---------- UI Architecture ----------
    
    def _on_menu_click(self, menu, value):
        """Toggle window visibility from Menu"""
        if value:
            self._build_ui()
            self._window.visible = True
        else:
            if self._window:
                self._window.visible = False

    def _build_ui(self):
        """Creates the floating window. Used for standalone mode."""
        if not getattr(self, "_window", None):
            self._window = ui.Window("SmartAssetsBuilder", width=680, height=450, dockPreference=ui.DockPreference.LEFT_BOTTOM)
            self._window.set_visibility_changed_fn(self._on_window_visibility_changed)
            with self._window.frame:
                self.build_ui_layout()
    
    def _on_window_visibility_changed(self, visible):
        if self._menu:
            omni.kit.ui.get_editor_menu().set_value(self._menu, visible)

    def build_ui_layout(self):
        """
        [Public Method] Creates the actual UI content.
        Zin All Tools calls this method to embed the UI.
        """
        self._init_data()
        
        self._STYLE_HEAD  = {"font_size": 18, "color": 0xFFDDDDDD}
        self._STYLE_LABEL = {"color": 0xFFAAAAAA}
        COMPACT_STYLE = {"font_size": 14, "padding": 2}

        # [Important] Use a VStack as root container with height=0 to auto-shrink
        # [UI Polish] Increased padding to 20 for more breathing room
        with ui.VStack(spacing=0, height=0, style={"padding": 20}):
            
            # --- Header Removed ---
            # [Mod v1.10.5] No Title or flowchart text here

            # --- Source Section ---
            with ui.VStack(spacing=8):
                ui.Label("Source Folder URL", style=self._STYLE_LABEL)
                # [UI Polish] Height 26px
                self._folder_field = ui.StringField(height=ui.Pixel(26), width=ui.Fraction(1), style=COMPACT_STYLE)

                # Filter Row
                with ui.HStack(spacing=15, height=ui.Pixel(26)):
                    ui.Label("Filename filter", width=0, style=self._STYLE_LABEL)
                    self._filter_field = ui.StringField(width=ui.Fraction(1), style=COMPACT_STYLE)
                    self._filter_field.model.set_value("max_*.usd")
                
                # Recurse Row
                with ui.HStack(height=ui.Pixel(26), spacing=5):
                    self._recurse_cb = ui.CheckBox(width=20)
                    self._recurse_cb.model.set_value(True) # Default Checked
                    ui.Label("Recurse", width=0, style=self._STYLE_LABEL)
                    ui.Label("(Search inside sub-folders)", style={"color": 0xFF666666, "font_size": 12})

                # ID Suffix / Overwrite Row
                with ui.HStack(spacing=10, height=ui.Pixel(26)):
                    ui.Label("ID Suffix", width=0, style=self._STYLE_LABEL)
                    self._id_field = ui.StringField(width=ui.Fraction(1), style=COMPACT_STYLE)
                    self._id_field.model.set_value("") # Default Empty
                    
                    ui.Spacer(width=20)
                    
                    with ui.HStack(width=0, spacing=5):
                        self._overwrite_cb = ui.CheckBox(width=20)
                        self._overwrite_cb.model.set_value(False)
                        ui.Label("Overwrite", style=self._STYLE_LABEL)

                # Scan Button (Inline with Count Label)
                with ui.HStack(height=40, style={"margin_top": 5}):
                    ui.Button("Scan", clicked_fn=self._on_scan, width=ui.Fraction(1))
                    ui.Spacer(width=10)
                    self._count_label = ui.Label("Ready to scan...", width=ui.Fraction(1), alignment=ui.Alignment.CENTER, style={"color": 0xFF888888})

            ui.Spacer(height=5)
            # [Mod v1.10.5] Light gray line
            ui.Line(height=1, style={"color": 0xFF555555})
            ui.Spacer(height=5)

            # --- Output Section ---
            with ui.VStack(spacing=12):
                ui.Label("Output Root URL (local or omniverse://)", style=self._STYLE_LABEL)
                self._out_root_field = ui.StringField(height=ui.Pixel(26), width=ui.Fraction(1), style=COMPACT_STYLE)
                
                ui.Label("Material Overlay Path (Optional)", style=self._STYLE_LABEL)
                self._mat_field = ui.StringField(height=ui.Pixel(26), width=ui.Fraction(1), style=COMPACT_STYLE)
                self._mat_field.model.set_value(r"C:\Users\iec141194\Desktop\Inventec\Library\Material\mat_Product_v2.usd")

                # In-place Row
                with ui.HStack(spacing=5, height=ui.Pixel(26)):
                    self._inplace_cb = ui.CheckBox(width=20)
                    self._inplace_cb.model.set_value(False)
                    ui.Label("Allow Same Root (in-place) - skips Materials copy", style={"color": 0xFFDDDDDD})

            ui.Spacer(height=10)
            # [Mod v1.10.5] Light gray line
            ui.Line(height=1, style={"color": 0xFF555555})
            ui.Spacer(height=10)

            # --- Footer (Compactly Stacked) ---
            with ui.HStack(height=40, spacing=15):
                ui.Button("Start (build trio)", clicked_fn=self._on_start_clicked, width=150)
                
                # Real Progress Bar
                with ui.ZStack(height=40): 
                    self._progress_bar = ui.ProgressBar(width=ui.Fraction(1), height=40)
                    self._progress_bar.model.set_value(0.0)
                    
                    # Overlay Text
                    self._progress_label = ui.Label("0/0", alignment=ui.Alignment.CENTER, style={"color": 0xFFFFFFFF})

    # ---------- Logging (Console Only) ----------
    def _log_to_console(self, level: str, text: str):
        print(f"[SmartAssetsBuilder] [{level}] {text}")

    def _info(self, msg: str):  self._log_to_console("INFO", msg)
    def _warn(self, msg: str):  self._log_to_console("WARN", msg)
    def _error(self, msg: str): self._log_to_console("ERROR", msg)

    # Helper for functions that pass in pre-tagged strings
    def _styled(self, msg: str):
        txt = msg.strip()
        lvl = "INFO"
        if txt.startswith("[ERROR]"):
            lvl, txt = "ERROR", txt[7:].lstrip()
        elif txt.startswith("[WARN]"):
            lvl, txt = "WARN", txt[6:].lstrip()
        elif txt.startswith("[INFO]"):
            lvl, txt = "INFO", txt[6:].lstrip()
        self._log_to_console(lvl, txt)

    def _progress(self, i: int, n: int):
        # Update text label
        if self._progress_label:
            self._progress_label.text = f"{i}/{n}"
        
        # Update progress bar (0.0 to 1.0)
        if self._progress_bar and n > 0:
            self._progress_bar.model.set_value(float(i) / float(n))
        elif self._progress_bar:
            self._progress_bar.model.set_value(0.0)

    # ---------- UI actions ----------
    def _on_scan(self):
        self._progress(0, 0)
        if self._count_label:
            self._count_label.text = "Scanning..."
            self._count_label.style = {"color": 0xFFFFFF00} # Yellow while scanning

        url = self._folder_field.model.get_value_as_string().strip()
        pattern = (self._filter_field.model.get_value_as_string().strip() or "max_*.usd").lower()
        recurse = (self._recurse_cb.model.get_value_as_bool()
                   if hasattr(self._recurse_cb.model, "get_value_as_bool")
                   else bool(self._recurse_cb.model.get_value_as_int()))

        if not url:
            self._error("Please enter a Source Folder URL")
            if self._count_label: 
                self._count_label.text = "Error: Missing URL"
                self._count_label.style = {"color": 0xFFFF5555}
            return

        try:
            # [Fix] Use self._list_... methods
            files = self._list_nucleus(url, pattern, recurse) if _is_ov_url(url) else self._list_local(url, pattern, recurse)
            self._found = files
            self._scan_root = url
            
            # Update Counter
            if self._count_label:
                count = len(files)
                if count > 0:
                    self._count_label.text = f"Found: {count} items"
                    self._count_label.style = {"color": 0xFF55FF55} # Green on success
                    self._info(f"Found {count} files")
                else:
                    self._count_label.text = f"Found: 0 items (check filter/path)"
                    self._count_label.style = {"color": 0xFFFFCC00}
                    self._warn(f"No files matched '{pattern}'")

        except Exception as e:
            self._error(f"Scan failed: {e}")
            if self._count_label: 
                self._count_label.text = "Scan Error (check console)"
                self._count_label.style = {"color": 0xFFFF5555}
            traceback.print_exc()

    def _on_start_clicked(self):
        # Wrapper to fire the async task
        asyncio.ensure_future(self._on_start_async())

    async def _on_start_async(self):
        if not self._found:
            self._warn("Nothing to process: please scan first")
            if self._count_label: 
                self._count_label.text = "Please Scan First!"
                self._count_label.style = {"color": 0xFFFF5555}
            return

        out_root = self._out_root_field.model.get_value_as_string().strip()
        if not out_root:
            self._error("Please enter an Output Root URL")
            return

        id_suffix = self._id_field.model.get_value_as_string().strip() or "TEMP00000001"
        overwrite = (self._overwrite_cb.model.get_value_as_bool()
                     if hasattr(self._overwrite_cb.model, "get_value_as_bool")
                     else bool(self._overwrite_cb.model.get_value_as_int()))

        # Read material override path
        mat_path_override = self._mat_field.model.get_value_as_string().strip()

        n = len(self._found); done = 0; skipped = 0
        self._progress(0, n)

        for i, src in enumerate(self._found, start=1):
            try:
                core, asset_name, main_name, id_name = _derive_names(src, id_suffix)
                src_core_dir = _dirname(src)
                out_core_dir = _join(out_root, core)

                # Loop-safety & in-place mode
                inplace_ok = (self._inplace_cb.model.get_value_as_bool()
                              if hasattr(self._inplace_cb.model, "get_value_as_bool")
                              else bool(self._inplace_cb.model.get_value_as_int()))
                same_dir = _is_same_path(out_core_dir, src_core_dir)
                overlap  = _is_inside(out_core_dir, src_core_dir) or _is_inside(src_core_dir, out_core_dir)

                if overlap or (same_dir and not inplace_ok):
                    self._error("Invalid Output Root: it must NOT be inside/contain the source <CORE> folder. "
                                "If you want to build in-place, enable 'Allow Same Root (in-place)'. Skipped.")
                    self._progress(i, n)
                    await omni.kit.app.get_app().next_update_async()
                    continue

                inplace_mode = same_dir and inplace_ok

                # Prepare output dirs
                (_ensure_dir_ov if _is_ov_url(out_core_dir) else _ensure_dir_local)(out_core_dir)
                (_ensure_dir_ov if _is_ov_url(out_root) else _ensure_dir_local)(out_root)

                # File paths
                asset_path = _ensure_usd_ext(_join(out_core_dir, asset_name))
                main_path  = _ensure_usd_ext(_join(out_core_dir, main_name))
                id_path    = _ensure_usd_ext(_join(out_root, id_name))

                # Overwrite guard
                if not overwrite and (_exists(asset_path) or _exists(main_path) or _exists(id_path)):
                    self._info(f"Skipped (exists): {src}")
                    skipped += 1
                    self._progress(i, n)
                    await omni.kit.app.get_app().next_update_async()
                    continue

                self._info(f"Processing: {src}")
                self._info(f"  CORE src : {src_core_dir}")
                self._info(f"  CORE out : {out_core_dir}")
                self._info(f"  id out   : {out_root}")
                self._info(f"  in-place : {'ON' if inplace_mode else 'OFF'}")

                # max_<CORE>.usd
                if inplace_mode:
                    max_dst = src
                    self._info("  max: in-place mode - no copy (using original)")
                else:
                    max_dst = _join(out_core_dir, os.path.basename(src))
                    copied = _copy_file_any_scheme(src, max_dst, overwrite, self._styled)
                    if not copied and not _exists(max_dst):
                        self._progress(i, n)
                        await omni.kit.app.get_app().next_update_async()
                        continue

                # Materials/
                if inplace_mode:
                    self._info("  Materials: in-place mode - skip copy (already alongside max).")
                else:
                    _mat_ok = _copy_materials_any_scheme(src_core_dir, out_core_dir, overwrite, self._styled)
                    if not _mat_ok:
                        self._warn("Materials not copied or not found. If max references './Materials/...', textures may miss.")

                # Build trio: asset -> main -> id
                try:
                    self._info(f"  [1/3] asset -> {asset_path}")
                    # Pass the material path override here
                    a_path = _build_asset(asset_path, max_dst, mat_path_override)
                    self._info(f"      asset done: {a_path}")
                except Exception as e_asset:
                    self._error(f"      asset failed: {e_asset}")
                    self._progress(i, n)
                    await omni.kit.app.get_app().next_update_async()
                    continue

                try:
                    self._info(f"  [2/3] main  -> {main_path}")
                    m_path = _build_main(main_path, a_path, core)
                    self._info(f"      main done: {m_path}")
                except Exception as e_main:
                    self._error(f"      main failed: {e_main}")
                    self._progress(i, n)
                    await omni.kit.app.get_app().next_update_async()
                    continue

                try:
                    self._info(f"  [3/3] id    -> {id_path}")
                    i_path = _build_id(id_path, m_path, core)
                    self._info(f"      id done: {i_path}")
                except Exception as e_id:
                    self._error(f"      id failed: {e_id}")
                    self._progress(i, n)
                    await omni.kit.app.get_app().next_update_async()
                    continue

                done += 1
            except Exception as e:
                self._error(f"Failed: {src} -> {e}")
                traceback.print_exc()
            finally:
                self._progress(i, n)
                # Yield control to let UI redraw!
                await omni.kit.app.get_app().next_update_async()

        self._info(f"Done {done}/{n}; Skipped: {skipped} (exists & overwrite=off)")