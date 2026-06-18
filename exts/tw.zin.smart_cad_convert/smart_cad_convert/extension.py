import omni.ext
import omni.ui as ui
import omni.usd
import omni.kit.commands
import omni.client
import os
import sys
import asyncio
import hashlib
from pxr import Usd, UsdGeom, Gf, Sdf, UsdShade, UsdPhysics, UsdUtils
from omni.kit.window.filepicker import FilePickerDialog
import omni.kit.asset_converter

try:
    from tools_box.zin_style import ZIN_GLOBAL_STYLE
    from tools_box.zin_components import ZinButton
except ImportError:
    ZIN_GLOBAL_STYLE = {}
    class ZinButton:
        def __init__(self, text, state="default", clicked_fn=None, **kwargs):
            self.widget = ui.Button(text, clicked_fn=clicked_fn, **kwargs)
        def set_state(self, state): pass

# Supported CAD file extensions (free + HOOPS-licensed)
SUPPORTED_CAD_EXTENSIONS = (
    ".fbx", ".obj", ".stl", ".gltf", ".glb",          # Free / built-in
    ".step", ".stp", ".iges", ".igs",                   # STEP / IGES (HOOPS)
    ".jt",                                              # JT - Siemens (HOOPS)
    ".x_t", ".x_b", ".xmt_txt",                         # Parasolid (HOOPS)
    ".catpart", ".catproduct",                           # CATIA (HOOPS)
    ".sldprt", ".sldasm",                                # SolidWorks (HOOPS)
    ".prt", ".asm",                                      # Creo / NX (HOOPS)
    ".3dxml", ".model", ".dlv", ".exp", ".session",      # Other CAD (HOOPS)
)

import re

def _strip_creo_version(filepath):
    """
    Strip Creo/Pro-E version suffix from filename.
    e.g. 'model.asm.1' -> 'model.asm'
         'part.prt.23' -> 'part.prt'
         'file.stp'    -> 'file.stp'  (unchanged)
    """
    # Match pattern: .ext.N where N is one or more digits at the end
    return re.sub(r'(\.[a-zA-Z_]+)\.[0-9]+$', r'\1', filepath)

def _get_cad_basename(filepath):
    """
    Get clean basename without extension or Creo version suffix.
    e.g. 'C:/path/model.asm.1' -> 'model'
         'C:/path/file.step'   -> 'file'
    """
    stripped = _strip_creo_version(os.path.basename(filepath))
    return os.path.splitext(stripped)[0]

def _is_omni_path(path):
    """Check if a path is an Omniverse Nucleus URL."""
    return path.startswith("omniverse://")

def _ensure_folder_exists(path):
    """
    Create folder for both local and Omniverse Nucleus paths.
    For omniverse:// paths, uses omni.client.
    For local paths, uses os.makedirs.
    """
    if _is_omni_path(path):
        result = omni.client.create_folder(path)
        # OK or ALREADY_EXISTS are both fine
        return True
    else:
        os.makedirs(path, exist_ok=True)
        return True

class SmartCadConvertUI:
    def __init__(self):
        self._file_picker = None
        self._cad_path_field = None
        self._output_path_field = None
        
        self._move_to_origin = None
        self._auto_physics = None
        
        self._batch_export = None
        self._props_path = None
        self._kind_dropdown = None
        
        self._use_payload = None
        self._preset_path_field = None
        
        self._execute_btn = None
        self._log_output = None

    def build_ui(self):
        scroll_frame = ui.ScrollingFrame()
        with scroll_frame:
            with ui.VStack(style=ZIN_GLOBAL_STYLE, spacing=5, padding=10):
                
                # CAD Source Input
                with ui.HStack(height=28, spacing=8):
                    ui.Label("Input CAD:", width=ui.Pixel(70))
                    self._cad_path_field = ui.StringField()
                    ZinButton("Browse", clicked_fn=self._on_browse_cad, width=ui.Pixel(70))

                # Output Folder
                with ui.HStack(height=28, spacing=8):
                    ui.Label("Output:", width=ui.Pixel(70))
                    self._output_path_field = ui.StringField()
                    self._output_path_field.model.set_value("")
                    ZinButton("Browse", clicked_fn=self._on_browse_output, width=ui.Pixel(70))
                ui.Label("Leave empty = auto (same folder as input)", height=16, style={"font_size": 11, "color": 0xFF666666})

                # Collapsable General
                with ui.CollapsableFrame("General", collapsed=False):
                    with ui.VStack(spacing=4, padding=4):
                        with ui.HStack(height=24):
                            ui.Label("Move to Origin", width=ui.Fraction(0.4))
                            self._move_to_origin = ui.CheckBox()
                            

                            
                # Collapsable File Output
                with ui.CollapsableFrame("File Output", collapsed=False):
                    with ui.VStack(spacing=4, padding=4):
                        with ui.HStack(height=24):
                            ui.Label("Enable Batch Export", width=ui.Fraction(0.4))
                            self._batch_export = ui.CheckBox()
                            self._batch_export.model.set_value(True)

                        with ui.HStack(height=24):
                            ui.Label("Props", width=ui.Fraction(0.4))
                            self._props_path = ui.StringField()
                            self._props_path.model.set_value("/Props")
                            
                # Collapsable Kind
                with ui.CollapsableFrame("Kind", collapsed=False):
                    with ui.VStack(spacing=4, padding=4):
                        with ui.HStack(height=24):
                            ui.Label("Kind", width=ui.Fraction(0.4))
                            self._kind_dropdown = ui.ComboBox(0, " (Empty)", "group", "subcomponent", "component", "assembly").model
                            
                # Collapsable SimReady (Physics)
                with ui.CollapsableFrame("SimReady (Physics)", collapsed=False):
                    with ui.VStack(spacing=4, padding=4):
                        with ui.HStack(height=24):
                            ui.Label("Auto-Compute Physics", width=ui.Fraction(0.4))
                            self._auto_physics = ui.CheckBox()
                            self._auto_physics.model.set_value(True)

                # Collapsable Asset Optimization & Architecture
                with ui.CollapsableFrame("Asset Optimization & Architecture", collapsed=False):
                    with ui.VStack(spacing=4, padding=4):
                        with ui.HStack(height=24):
                            ui.Label("Use Payload Architecture", width=ui.Fraction(0.4))
                            self._use_payload = ui.CheckBox()
                            self._use_payload.model.set_value(True)
                        ui.Spacer(height=4)
                        ui.Label("Scene Optimizer Preset (.json):", height=20, style={"font_size": 12, "color": 0xFF888888})
                        with ui.HStack(height=28, spacing=8):
                            self._preset_path_field = ui.StringField()
                            self._preset_path_field.model.set_value("")
                            ZinButton("Browse", clicked_fn=self._on_browse_preset, width=ui.Pixel(70))
                ui.Spacer(height=10)
                self._execute_btn = ZinButton("Execute Convert", state="correct", clicked_fn=self._on_execute_click)
                self._execute_btn.widget.height = ui.Pixel(36)
                
                # STATUS LOG
                with ui.ZStack(height=120):
                    ui.Rectangle(style={"background_color": 0xFF101010, "border_radius": 4})
                    with ui.VStack(padding=6):
                        ui.Label("STATUS LOG:", height=20, style={"font_size": 12, "color": 0xFF888888, "font_weight": "bold"})
                        self._log_output = ui.Label("Ready.", word_wrap=True)

        return scroll_frame

    def log(self, message, is_error=False, is_success=False):
        self._log_output.text = message
        if is_error:
            self._log_output.style = {"color": 0xFFFF5555}
        elif is_success:
            self._log_output.style = {"color": 0xFF55FF55}
        else:
            self._log_output.style = {"color": 0xFF00BFFF}

    def _on_browse_cad(self):
        def on_selected(filename, path):
            self._cad_path_field.model.set_value(f"{path}/{filename}".replace("\\", "/"))
            self._file_picker.hide()
        self._file_picker = FilePickerDialog("Select CAD File", click_apply_handler=on_selected)
        self._file_picker.show()

    def _on_browse_output(self):
        def on_selected(filename, path):
            self._output_path_field.model.set_value(path.replace("\\", "/"))
            self._output_picker.hide()
        self._output_picker = FilePickerDialog("Select Output Folder", click_apply_handler=on_selected)
        self._output_picker.show()

    def _on_browse_preset(self):
        def on_selected(filename, path):
            self._preset_path_field.model.set_value(f"{path}/{filename}".replace("\\", "/"))
            self._preset_picker.hide()
        self._preset_picker = FilePickerDialog("Select SO Preset JSON", click_apply_handler=on_selected)
        self._preset_picker.show()

    def _on_execute_click(self):
        cad_path = self._cad_path_field.model.get_value_as_string().strip()
        
        # Strip Creo version suffix before checking extension
        check_path = _strip_creo_version(cad_path.lower())
        if not check_path.endswith(SUPPORTED_CAD_EXTENSIONS):
            supported = ', '.join(SUPPORTED_CAD_EXTENSIONS)
            self.log(f"Error: Unsupported file format.\nSupported: {supported}", is_error=True)
            return
            
        if not os.path.exists(cad_path):
            self.log("Error: CAD file does not exist.", is_error=True)
            return

        self._execute_btn.widget.enabled = False
        asyncio.ensure_future(self._run_pipeline_async(cad_path))

    async def _run_pipeline_async(self, cad_path):
        try:
            base_dir = os.path.dirname(cad_path)
            basename = _get_cad_basename(cad_path)
            
            # Use custom output path if provided, otherwise auto-generate
            custom_output = self._output_path_field.model.get_value_as_string().strip()
            if custom_output:
                out_folder = custom_output.replace("\\", "/")
            else:
                out_folder = os.path.join(base_dir, f"{basename}_USD").replace("\\", "/")
            os.makedirs(out_folder, exist_ok=True) if not _is_omni_path(out_folder) else _ensure_folder_exists(out_folder)
            
            # --- Config ---
            batch_export = self._batch_export.model.get_value_as_bool()
            move_to_origin = self._move_to_origin.model.get_value_as_bool()
            props_folder_name = self._props_path.model.get_value_as_string().strip("/")
            auto_physics = self._auto_physics.model.get_value_as_bool()
            use_payload = self._use_payload.model.get_value_as_bool()
            preset_path = self._preset_path_field.model.get_value_as_string().strip()
            
            kind_idx = self._kind_dropdown.get_item_value_model().as_int
            kinds = ["", "group", "subcomponent", "component", "assembly"]
            selected_kind = kinds[kind_idx] if kind_idx < len(kinds) else ""

            # --- Step 1: Base Convert ---
            stripped_path = _strip_creo_version(cad_path)
            file_ext = os.path.splitext(stripped_path)[1].lower()
            self.log(f"Converting {file_ext.upper()} to USD...")
            await asyncio.sleep(0.1)
            
            master_usd = f"{out_folder}/{basename}.usd"
            task_manager = omni.kit.asset_converter.get_instance()
            context = omni.kit.asset_converter.AssetConverterContext()
            context.ignore_materials = False
            
            task = task_manager.create_converter_task(cad_path, master_usd, None, context)
            success = await task.wait_until_finished()
            if not success:
                self.log("Error: Asset Converter failed.", is_error=True)
                self._execute_btn.widget.enabled = True
                return

            if not batch_export:
                self.log(f"Conversion complete! (Batch Export disabled)\nOutput: {master_usd}", is_success=True)
                self._execute_btn.widget.enabled = True
                return

            # --- Step 2: Batch Export Props ---
            self.log("Batch Exporting Props...")
            await asyncio.sleep(0.1)
            
            stage = Usd.Stage.Open(master_usd)
            props_dir_path = f"{out_folder}/{props_folder_name}"
            _ensure_folder_exists(props_dir_path)
            
            mesh_hashes = {} # hash -> prop file name
            
            # First pass: identify unique meshes
            for prim in stage.TraverseAll():
                if prim.IsA(UsdGeom.Mesh):
                    mesh = UsdGeom.Mesh(prim)
                    pts = mesh.GetPointsAttr().Get()
                    if not pts: continue
                    
                    hash_str = hashlib.sha256(str(pts).encode('utf-8')).hexdigest()[:8]
                    
                    if hash_str not in mesh_hashes:
                        mesh_name = prim.GetName()
                        prop_name = f"Prop_{hash_str}"
                        
                        self.log(f"Extracting {prop_name}...")
                        await asyncio.sleep(0.01)
                        
                        # --- Determine file paths based on Payload Architecture ---
                        if use_payload:
                            # SimReady Payload Architecture:
                            #   Props/Prop_xxxx/payload/Prop_xxxx_payload.usd  (geometry + physics)
                            #   Props/Prop_xxxx/Prop_xxxx.usd                 (wrapper with payload ref)
                            prop_component_dir = f"{props_dir_path}/{prop_name}"
                            payload_dir = f"{prop_component_dir}/payload"
                            _ensure_folder_exists(payload_dir)
                            
                            payload_filename = f"{prop_name}_payload.usd"
                            payload_filepath = f"{payload_dir}/{payload_filename}"
                            wrapper_filename = f"{prop_name}.usd"
                            wrapper_filepath = f"{prop_component_dir}/{wrapper_filename}"
                            
                            # The reference path used in master USD
                            prop_ref_for_master = f"./{props_folder_name}/{prop_name}/{wrapper_filename}"
                        else:
                            # Legacy flat structure: Props/Prop_xxxx.usd
                            prop_filename_flat = f"{prop_name}.usd"
                            payload_filepath = f"{props_dir_path}/{prop_filename_flat}"
                            prop_ref_for_master = f"./{props_folder_name}/{prop_filename_flat}"
                        
                        # --- Create the geometry/physics stage (payload or flat) ---
                        prop_stage = Usd.Stage.CreateNew(payload_filepath)
                        UsdGeom.SetStageUpAxis(prop_stage, UsdGeom.GetStageUpAxis(stage))
                        
                        prop_root = UsdGeom.Xform.Define(prop_stage, "/World")
                        prop_stage.SetDefaultPrim(prop_root.GetPrim())
                        
                        if selected_kind:
                            Usd.ModelAPI(prop_root.GetPrim()).SetKind(selected_kind)
                        
                        # Copy mesh to prop
                        target_path = "/World/Geometry"
                        Sdf.CopySpec(stage.GetRootLayer(), prim.GetPath(), prop_stage.GetRootLayer(), target_path)
                        
                        # [Material Fix] Strip material bindings from payload to allow master stage to override
                        for p in prop_stage.Traverse():
                            if p.HasProperty("material:binding"):
                                p.RemoveProperty("material:binding")
                        
                        # [Reset XForm] 徹底清除殘留的任何變形矩陣 (旋轉、縮放、位移)
                        prop_mesh = UsdGeom.Mesh.Get(prop_stage, target_path)
                        xformable = UsdGeom.Xformable(prop_mesh)
                        xformable.ClearXformOpOrder()
                        
                        # [SimReady Physics] 自動計算碰撞體與質量
                        if auto_physics:
                            UsdPhysics.CollisionAPI.Apply(prop_mesh.GetPrim())
                            mesh_collision = UsdPhysics.MeshCollisionAPI.Apply(prop_mesh.GetPrim())
                            mesh_collision.CreateApproximationAttr().Set("convexHull")
                            UsdPhysics.RigidBodyAPI.Apply(prop_root.GetPrim())
                            UsdPhysics.MassAPI.Apply(prop_root.GetPrim())
                        
                        if move_to_origin:
                            prop_mesh = UsdGeom.Mesh.Get(prop_stage, target_path)
                            bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default'])
                            bound = bbox_cache.ComputeWorldBound(prop_root.GetPrim())
                            range_box = bound.ComputeAlignedBox()
                            
                            range_min = range_box.GetMin()
                            range_max = range_box.GetMax()
                            center = (range_min + range_max) / 2.0
                            offset = Gf.Vec3f(-center[0], -center[1], -range_min[2])
                            
                            op = xformable.AddTranslateOp(UsdGeom.XformOp.PrecisionFloat)
                            op.Set(offset)
                            
                            compensation_offset = -offset
                        else:
                            compensation_offset = Gf.Vec3f(0,0,0)
                        
                        # [Scene Optimizer] 套用最佳化配方 (減面、清整、法線重建等)
                        if preset_path and os.path.exists(preset_path):
                            self.log(f"Optimizing {prop_name} with Scene Optimizer...")
                            await asyncio.sleep(0.01)
                            try:
                                from omni.scene.optimizer.core import ExecutionContext
                                optimizer_ctx = ExecutionContext()
                                optimizer_ctx.usdStageId = UsdUtils.StageCache.Get().Insert(prop_stage).ToLongInt()
                                optimizer_ctx.generateReport = 0
                                optimizer_ctx.captureStats = 0
                                so_args = {"jsonFile": str(preset_path)}
                                omni.kit.commands.execute("SceneOptimizerJsonParser", context=optimizer_ctx, args=so_args)
                            except Exception as opt_err:
                                self.log(f"Warning: Scene Optimizer skipped for {prop_name}: {opt_err}")
                        
                        prop_stage.Save()
                        
                        # --- Create wrapper USD for Payload Architecture ---
                        if use_payload:
                            wrapper_stage = Usd.Stage.CreateNew(wrapper_filepath)
                            UsdGeom.SetStageUpAxis(wrapper_stage, UsdGeom.GetStageUpAxis(stage))
                            wrapper_root = UsdGeom.Xform.Define(wrapper_stage, "/World")
                            wrapper_stage.SetDefaultPrim(wrapper_root.GetPrim())
                            if selected_kind:
                                Usd.ModelAPI(wrapper_root.GetPrim()).SetKind(selected_kind)
                            # Add payload reference to the geometry file
                            wrapper_root.GetPrim().GetPayloads().AddPayload(
                                f"./payload/{payload_filename}"
                            )
                            wrapper_stage.Save()
                        
                        mesh_hashes[hash_str] = (prop_ref_for_master, compensation_offset)

            # Second pass: replace master meshes with References
            self.log("Replacing meshes with References...")
            await asyncio.sleep(0.1)
            
            # To avoid traversal issues when renaming, collect all meshes first
            mesh_prims = [prim for prim in stage.TraverseAll() if prim.IsA(UsdGeom.Mesh)]
            
            for prim in mesh_prims:
                if not prim.IsValid(): continue
                
                mesh = UsdGeom.Mesh(prim)
                pts = mesh.GetPointsAttr().Get()
                if not pts: continue
                    
                hash_str = hashlib.sha256(str(pts).encode('utf-8')).hexdigest()[:8]
                if hash_str in mesh_hashes:
                    ref_path, offset = mesh_hashes[hash_str]
                    
                    # Clear local geometry attributes
                    prim.SetTypeName("Xform")
                    prim.RemoveProperty("points")
                    prim.RemoveProperty("faceVertexCounts")
                    prim.RemoveProperty("faceVertexIndices")
                    prim.RemoveProperty("normals")
                    prim.RemoveProperty("extent")
                    prim.RemoveProperty("primvars:st")
                    
                    # Add reference (path already includes payload wrapper or flat)
                    prim.GetReferences().AddReference(ref_path)
                    prim.SetInstanceable(True)
                    
                    # Apply compensation offset if moved to origin
                    if move_to_origin and offset != Gf.Vec3f(0,0,0):
                        xform = UsdGeom.Xformable(prim)
                        attr = prim.GetAttribute("xformOp:translate")
                        if attr.IsValid():
                            op = UsdGeom.XformOp(attr)
                            current_val = op.Get() or Gf.Vec3f(0,0,0)
                            if isinstance(current_val, Gf.Vec3d):
                                op.Set(current_val + Gf.Vec3d(offset[0], offset[1], offset[2]))
                            else:
                                op.Set(current_val + offset)
                        else:
                            op = xform.AddTranslateOp(UsdGeom.XformOp.PrecisionFloat)
                            op.Set(offset)
                            
                    # Rename the node in the master stage to prevent long hashed names
                    parent_path = prim.GetParent().GetPath()
                    new_name = "Payload"
                    new_path = parent_path.AppendChild(new_name)
                    counter = 1
                    while stage.GetPrimAtPath(new_path):
                        new_name = f"Payload_{counter}"
                        new_path = parent_path.AppendChild(new_name)
                        counter += 1
                    
                    try:
                        # Sdf CopySpec is required for offline stage manipulation
                        Sdf.CopySpec(stage.GetRootLayer(), prim.GetPath(), stage.GetRootLayer(), new_path)
                        stage.RemovePrim(prim.GetPath())
                        
                        # [Material Fix] Move GeomSubsets to match the Payload's internal structure
                        renamed_prim = stage.GetPrimAtPath(new_path)
                        if renamed_prim:
                            geom_path = new_path.AppendChild("Geometry")
                            stage.OverridePrim(geom_path)
                            for child in renamed_prim.GetChildren():
                                if "Subset" in child.GetTypeName():
                                    subset_old = child.GetPath()
                                    subset_new = geom_path.AppendChild(child.GetName())
                                    Sdf.CopySpec(stage.GetRootLayer(), subset_old, stage.GetRootLayer(), subset_new)
                                    stage.RemovePrim(subset_old)
                    except Exception as e:
                        self.log(f"Warning: failed to rename/move children for {prim.GetName()}: {e}")

            stage.GetRootLayer().Export(master_usd)
            self.log(f"Pipeline Complete!\nOutput saved to:\n{master_usd}", is_success=True)
            self._execute_btn.widget.enabled = True
            
        except Exception as e:
            self.log(f"Pipeline Error: {e}", is_error=True)
            self._execute_btn.widget.enabled = True


class SmartCadConvertExtension(omni.ext.IExt):
    WINDOW_NAME = "Smart CAD Convert"
    MENU_PATH = f"Zin_All_Tools/{WINDOW_NAME}"

    def __init__(self):
        super().__init__()
        self._window = None
        self._menu_added = False
        self._ui = None

    def on_startup(self, ext_id):
        self._build_menu()

    def on_shutdown(self):
        self._remove_menu()
        if self._window:
            self._window.destroy()
            self._window = None
        self._ui = None

    def _build_menu(self):
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
        except Exception: pass

    def _toggle_window(self, menu, value):
        if value:
            if not self._window:
                from omni.ui import DockPreference
                self._window = ui.Window(self.WINDOW_NAME, width=320, height=800, dockPreference=DockPreference.RIGHT)
                self._window.set_visibility_changed_fn(self._on_visibility_changed)
                if not self._ui:
                    self._ui = SmartCadConvertUI()
                with self._window.frame:
                    self._ui.build_ui()
            self._window.visible = True
        else:
            if self._window:
                self._window.visible = False

    def _on_visibility_changed(self, visible):
        if self._menu_added:
            try:
                import omni.kit.ui
                omni.kit.ui.get_editor_menu().set_value(self.MENU_PATH, bool(visible))
            except Exception:
                pass
