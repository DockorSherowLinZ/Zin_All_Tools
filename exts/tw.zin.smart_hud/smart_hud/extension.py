import omni.ext
import omni.ui as ui
import omni.ui.scene as sc
import omni.usd
import omni.timeline
from pxr import Usd, UsdGeom, UsdSkel, Gf, Sdf
import asyncio
import random
import statistics

# ==============================================================================
# Kit USD Agents Integration
# ==============================================================================
class UsdSelectionAgent:
    """
    Agent class to handle USD interactions safely and decoupled from UI.
    Listens for stage selection events and queries the machine_type.
    """
    def __init__(self, callback, ui_instance):
        self._callback = callback
        self._ui_instance = ui_instance
        self._context = omni.usd.get_context()
        self._sub = self._context.get_stage_event_stream().create_subscription_to_pop(
            self._on_stage_event, name="DSX_HUD_Selection_Agent"
        )
    
    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            self._handle_selection()
            
    def _handle_selection(self):
        selected_paths = self._context.get_selection().get_selected_prim_paths()
        if not selected_paths:
            self._callback(None, None)
            return
            
        stage = self._context.get_stage()
        if not stage:
            return
            
        prim = stage.GetPrimAtPath(selected_paths[0])
        if not prim or not prim.IsValid():
            return
            
        # Check machine type attribute or aif attributes
        attr = prim.GetAttribute("machine_type")
        aif_attr = prim.GetAttribute("aif:core:assetClass")
        
        if (attr and attr.IsValid()) or (aif_attr and aif_attr.IsValid()):
            m_type = attr.Get() if (attr and attr.IsValid()) else ""
            
            sub_title_attr = prim.GetAttribute("hud_sub_title")
            sub_title = sub_title_attr.Get() if sub_title_attr and sub_title_attr.IsValid() else ""
            
            content_attr = prim.GetAttribute("hud_content")
            content = content_attr.Get() if content_attr and content_attr.IsValid() else ""
            
            # 讀取 aif:core 屬性以相容 smart_info_panel 的資料
            asset_class_attr = prim.GetAttribute("aif:core:assetClass")
            if asset_class_attr and asset_class_attr.IsValid() and not m_type:
                 m_type = asset_class_attr.Get()
                 
            model_num_attr = prim.GetAttribute("aif:core:modelNumber")
            if model_num_attr and model_num_attr.IsValid() and not sub_title:
                 sub_title = model_num_attr.Get()
                 
            desc_attr = prim.GetAttribute("aif:core:assetDescription")
            if desc_attr and desc_attr.IsValid() and not content:
                 content = desc_attr.Get()

            # 如果連 aif 屬性都沒有，且又沒有 machine_type，就直接跳出
            if not m_type:
                 self._callback(None, None)
                 return

            # Extract world transform and dimensions
            xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
            world_transform = xform_cache.GetLocalToWorldTransform(prim)
            
            # Use BBox to find top center for better placement
            purposes = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render]
            bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes)
            bbox = bbox_cache.ComputeWorldBound(prim)
            world_box = bbox.ComputeAlignedBox()
            
            if not world_box.IsEmpty():
                min_pt = world_box.GetMin()
                max_pt = world_box.GetMax()
                
                # Z-up environment
                top_center = (
                    (min_pt[0] + max_pt[0]) / 2.0,
                    (min_pt[1] + max_pt[1]) / 2.0,
                    max_pt[2]
                )
                translation = top_center
            else:
                translation = world_transform.ExtractTranslation()
            
            # Check visibility settings
            show_dynamic = True
            show_static = True
            if self._ui_instance:
                if hasattr(self._ui_instance, "cb_dynamic"):
                    show_dynamic = self._ui_instance.cb_dynamic.model.get_value_as_bool()
                if hasattr(self._ui_instance, "cb_static"):
                    show_static = self._ui_instance.cb_static.model.get_value_as_bool()

            self._callback({
                "type": m_type, 
                "sub": sub_title, 
                "content": content, 
                "show_dynamic": show_dynamic, 
                "show_static": show_static,
                "path": selected_paths[0]
            }, translation)
        else:
            self._callback(None, None)

    def destroy(self):
        self._sub = None


# ==============================================================================
# MVVM View Model
# ==============================================================================
class HUDViewModel:
    """MVVM View Model holding all the observable data."""
    def __init__(self):
        self.aoi_status = ui.SimpleStringModel("IDLE")
        self.aoi_defect_rate = ui.SimpleFloatModel(0.0)
        self.robot_state = ui.SimpleStringModel("STANDBY")
        self.manual_station_name = ui.SimpleStringModel("Manual Assembly #1")
        self.manual_takt_time_pct = ui.SimpleFloatModel(100.0)
        
        # Generic models for custom HUDs
        self.generic_title = ui.SimpleStringModel("Custom Item")
        self.generic_sub = ui.SimpleStringModel("Sub Title")
        self.generic_content = ui.SimpleStringModel("Status: Active")


# ==============================================================================
# HUD Engine
# ==============================================================================
class GrayboxHUDEngine:
    def __init__(self, ui_instance):
        self.view_model = HUDViewModel()
        self.ui_pool = {} 
        self.scene_view = None
        self._running = True
        self._telemetry_task = None
        self._selection_agent = None
        self._color_sub = None
        self._ui_instance = ui_instance
        self._cycle_start_frame = 0.0
        self._cycle_end_frame = 100.0
        
        self._build_ui()
        self._start_telemetry()
        
        # Initialize Kit USD Selection Agent
        self._selection_agent = UsdSelectionAgent(self.on_selection_changed, self._ui_instance)

    def _build_ui(self):
        import omni.kit.viewport.utility
        self.viewport_window = omni.kit.viewport.utility.get_active_viewport_window()
        
        if not self.viewport_window:
            self.viewport_window = ui.Window("DSX AI Factory - Phase 7 Graybox HUD", width=800, height=600)

        with self.viewport_window.get_frame("DSX_Phase7_HUD_Overlay"):
            self.scene_view = sc.SceneView()
            
            if hasattr(self.viewport_window, "viewport_api"):
                self.viewport_window.viewport_api.add_scene_view(self.scene_view)
                
            with self.scene_view.scene:
                self.ui_pool["AOI"] = self._create_pooled_widget("AOI", self._build_aoi_ui)
                self.ui_pool["Robot"] = self._create_pooled_widget("Robot", self._build_robot_ui)
                self.ui_pool["ManualStation"] = self._create_pooled_widget("ManualStation", self._build_manual_station_ui)

    def _create_pooled_widget(self, name, ui_builder_func):
        transform = sc.Transform(look_at=sc.Transform.LookAt.CAMERA, visible=False)
        with transform:
            # 增加 widget 高度以容納整合後的面板
            widget = sc.Widget(width=300, height=240)
            widget.frame.set_build_fn(ui_builder_func)
        return {"transform": transform, "widget": widget}

    def _build_aoi_ui(self):
        with ui.ZStack():
            ui.Rectangle(style={"background_color": 0xCC1A1E24, "border_color": 0xCC00FFFF, "border_width": 2, "border_radius": 5})
            with ui.HStack():
                ui.Spacer(width=25)
                with ui.VStack(spacing=5):
                    ui.Spacer(height=15)
                    ui.Label("AOI Inspection", style={"color": 0xFFFFFFFF, "font_size": 20})
                    with ui.HStack():
                        ui.Label("Status:", width=80, style={"color": 0xFFAAAAAA})
                        ui.Label("", model=self.view_model.aoi_status, style={"color": 0xFFFFFFFF})
                    with ui.HStack():
                        ui.Label("Defect %:", width=80, style={"color": 0xFFAAAAAA})
                        ui.FloatField(model=self.view_model.aoi_defect_rate, read_only=True, style={"color": 0xFFFFFFFF})
                    ui.Spacer(height=15)
                ui.Spacer(width=25)

    def _build_robot_ui(self):
        with ui.ZStack():
            ui.Rectangle(style={"background_color": 0xCC1A1E24, "border_color": 0xCC00FFFF, "border_width": 2, "border_radius": 5})
            with ui.HStack():
                ui.Spacer(width=25)
                with ui.VStack(spacing=5):
                    ui.Spacer(height=15)
                    ui.Label("Robot Arm", style={"color": 0xFFFFFFFF, "font_size": 20})
                    with ui.HStack():
                        ui.Label("State:", width=80, style={"color": 0xFFAAAAAA})
                        ui.Label("", model=self.view_model.robot_state, style={"color": 0xFFFFFFFF})
                    ui.Spacer(height=15)
                ui.Spacer(width=25)

    def _build_manual_station_ui(self):
        with ui.ZStack():
            ui.Rectangle(style={"background_color": ui.color(0.05, 0.05, 0.12, 0.85), "border_color": 0xCC00FFFF, "border_width": 2, "border_radius": 5})
            with ui.HStack():
                ui.Spacer(width=25)
                with ui.VStack(spacing=10):
                    ui.Spacer(height=15)
                    ui.Label("", model=self.view_model.manual_station_name, style={"color": 0xFFFFFFFF, "font_size": 22, "alignment": ui.Alignment.CENTER})
                    ui.Label("Takt Time Remaining:", style={"color": 0xFFAAAAAA, "font_size": 14})
                    with ui.ZStack(height=20):
                        ui.Rectangle(style={"background_color": 0x44000000, "border_radius": 3})
                        self.progress_fill = ui.Rectangle(
                            style={"background_color": ui.color(0.0, 1.0, 0.0, 1.0), "border_radius": 3},
                            width=ui.Percent(100) 
                        )
                    ui.Spacer(height=15)
                ui.Spacer(width=25)

        self._color_sub = self.view_model.manual_takt_time_pct.add_value_changed_fn(self._on_takt_time_changed)

    def _on_takt_time_changed(self, model):
        pct = model.as_float
        pct = max(0.0, min(100.0, pct))
        self.progress_fill.width = ui.Percent(pct)
        ratio = pct / 100.0
        r = 1.0 - ratio
        g = ratio
        b = 0.0
        self.progress_fill.style = {
            "background_color": ui.color(r, g, b, 1.0),
            "border_radius": 3
        }

    def _build_generic_ui(self):
        pass

    def _create_generic_widget(self, name):
        transform = sc.Transform(look_at=sc.Transform.LookAt.CAMERA, visible=False)
        pool_item_dict = {"transform": transform, "dynamic_hud_vbox": None, "static_hud_frame": None, "bg_rect": None}
        
        with transform:
            widget = sc.Widget(width=300, height=240)
            
            def build_ui():
                with ui.ZStack():
                    pool_item_dict["bg_rect"] = ui.Rectangle(style={"background_color": ui.color(0.1, 0.1, 0.15, 0.85), "border_color": 0xCC00FFFF, "border_width": 2, "border_radius": 5})
                    with ui.HStack():
                        ui.Spacer(width=15)
                        with ui.VStack(spacing=5):
                            ui.Spacer(height=10)
                            
                            # ── 動態 HUD 區塊 ──
                            pool_item_dict["dynamic_hud_vbox"] = ui.VStack(spacing=2, height=0)
                            with pool_item_dict["dynamic_hud_vbox"]:
                                ui.Label("", height=22, model=self.view_model.generic_title, style={"color": 0xFFFFFFFF, "font_size": 20, "weight": "bold"})
                                ui.Label("", height=16, model=self.view_model.generic_sub, style={"color": 0xFFFFAA00, "font_size": 14})
                                ui.Label("", height=16, model=self.view_model.generic_content, style={"color": 0xFFAAAAAA, "font_size": 14})
                                
                                ui.Spacer(height=5)
                                # 這裡的 Line 也被包在 dynamic_hud_vbox 裡面，所以當它隱藏時，這條線也會一起隱藏
                                ui.Line(style={"color": 0xFF444444, "border_width": 1})
                                ui.Spacer(height=5)
                            
                            # ── 靜態 AIF Metadata 區塊 (移植自 Smart Info Panel) ──
                            # 為了避免在 3D 場景中點擊 CollapsableFrame 觸發 Omniverse 預設的射線點擊 (Raycast/Selection) 
                            # 導致選取焦點亂跑，這裡改用普通的 Frame 或是 Vstack 來代替。
                            pool_item_dict["static_hud_frame"] = ui.VStack(spacing=2, height=0)
                            with pool_item_dict["static_hud_frame"]:
                                ui.Label("Factory Info", height=16, style={"color": 0xFF00AAFF, "font_size": 14, "weight": "bold"})
                                ui.Spacer(height=3)
                                with ui.HStack(height=16):
                                    ui.Label("Asset Class:", width=90, style={"color": 0xFF888888, "font_size": 12})
                                    ui.Label("", model=self.view_model.generic_title, style={"color": 0xFFDDDDDD, "font_size": 12})
                                with ui.HStack(height=16):
                                    ui.Label("Model No:", width=90, style={"color": 0xFF888888, "font_size": 12})
                                    ui.Label("", model=self.view_model.generic_sub, style={"color": 0xFFDDDDDD, "font_size": 12})
                                with ui.HStack(height=16):
                                    ui.Label("Status:", width=90, style={"color": 0xFF888888, "font_size": 12})
                                    ui.Label("Active", style={"color": 0xFF44AA44, "font_size": 12})
                            
                            ui.Spacer(height=10)
                        ui.Spacer(width=15)
            
            widget.frame.set_build_fn(build_ui)
            pool_item_dict["widget"] = widget
            
        return pool_item_dict

    def _get_anim_cycle_frames(self, stage, prim_path):
        """
        Detects the actual animation cycle frame range on the subtree rooted at prim_path.
        Uses a priority-based strategy designed to handle Unreal Engine baked USDs:

          P0:   UsdSkel.Animation prims (proper skeletal animation)
          P1:   xformOp bounds — only accepted if range is "reasonable" (<2000 frames)
          P1.5: Autocorrelation on xformOp:transform values — detects the true
                repeating cycle even when UE bakes thousands of linear frames
          P2:   All authored TimeSamples with outlier rejection

        Returns (start_frame, end_frame). Falls back to stage time range.
        """
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            print(f"[Smart HUD] ⚠️ Prim not found or invalid: {prim_path}")
            return (stage.GetStartTimeCode(), stage.GetEndTimeCode())

        # --- P0: SkelAnimation prims (highest priority) ---
        skel_bounds = []
        try:
            for p in Usd.PrimRange(prim):
                if p.IsA(UsdSkel.Animation):
                    for attr_name in ["rotations", "translations", "scales", "blendShapeWeights"]:
                        attr = p.GetAttribute(attr_name)
                        if attr and attr.HasAuthoredValue():
                            samples = attr.GetTimeSamples()
                            if samples and len(samples) >= 2:
                                skel_bounds.append((float(samples[0]), float(samples[-1])))
                                print(f"[Smart HUD]   P0 found {attr_name} on {p.GetPath()}: "
                                      f"[{samples[0]}, {samples[-1]}] ({len(samples)} keys)")
        except Exception as e:
            print(f"[Smart HUD] ⚠️ SkelAnimation scan error: {e}")

        if skel_bounds:
            start = min(b[0] for b in skel_bounds)
            end = max(b[1] for b in skel_bounds)
            if 0 < (end - start) < 50000:  # Reject if suspiciously large
                print(f"[Smart HUD] 🎯 P0 SkelAnimation bounds: [{start}, {end}] ({end - start} frames)")
                return (start, end)
            else:
                print(f"[Smart HUD] ⚠️ P0 SkelAnimation bounds [{start}, {end}] look like UE sentinels, skipping")

        # --- Collect all xformOp data (shared between P1 and P1.5) ---
        xform_bounds = []
        xform_transform_attrs = []  # For autocorrelation in P1.5
        try:
            for p in Usd.PrimRange(prim):
                xformable = UsdGeom.Xformable(p)
                if xformable:
                    for op in xformable.GetOrderedXformOps():
                        attr = op.GetAttr()
                        if attr and attr.HasAuthoredValue():
                            samples = attr.GetTimeSamples()
                            if samples and len(samples) >= 2:
                                xform_bounds.append((float(samples[0]), float(samples[-1]), len(samples), attr.GetName()))
                                # Collect xformOp:transform attrs for autocorrelation
                                if attr.GetName() == "xformOp:transform":
                                    xform_transform_attrs.append({
                                        "prim_path": str(p.GetPath()),
                                        "attr": attr,
                                        "samples": samples,
                                    })
        except Exception as e:
            print(f"[Smart HUD] ⚠️ xformOp scan error: {e}")

        # Log what we found
        if xform_bounds:
            print(f"[Smart HUD]   P1 found {len(xform_bounds)} xformOp attributes with TimeSamples")
            # Show the range distribution
            spans = [b[1] - b[0] for b in xform_bounds]
            min_span = min(spans)
            max_span = max(spans)
            print(f"[Smart HUD]   P1 span range: [{min_span}, {max_span}] frames")

        # --- P1: xformOp bounds — only accept if the range is reasonable ---
        # UE-baked animations often have bounds of [0, 9999+], which is NOT the true loop length
        if xform_bounds:
            start = min(b[0] for b in xform_bounds)
            end = max(b[1] for b in xform_bounds)
            total_span = end - start
            if 0 < total_span <= 2000:
                # Reasonable range — likely a proper short animation
                print(f"[Smart HUD] 🎯 P1 xformOp bounds: [{start}, {end}] ({total_span} frames)")
                return (start, end)
            else:
                print(f"[Smart HUD] ⚠️ P1 xformOp bounds [{start}, {end}] = {total_span} frames — "
                      f"too large, likely UE linear bake. Trying autocorrelation...")

        # --- P1.5: Autocorrelation-based cycle detection (FULL MATRIX) ---
        # For UE-baked USDs: animation is written as thousands of linear frames.
        # The actual motion REPEATS, but may be purely rotational (zero translation delta).
        # We compare the FULL 4x4 matrix (Frobenius norm) to detect the true loop.
        if xform_transform_attrs:
            # Pick the transform attribute with the most keyframes (densest sampling)
            best_attr_info = max(xform_transform_attrs, key=lambda x: len(x["samples"]))
            attr = best_attr_info["attr"]
            sample_times = list(best_attr_info["samples"])
            prim_name = best_attr_info["prim_path"].split("/")[-1]

            print(f"[Smart HUD]   P1.5 Autocorrelation on '{prim_name}' "
                  f"({len(sample_times)} samples, range [{sample_times[0]}, {sample_times[-1]}])")

            # Find the sample index closest to stage start time (skip pre-roll frames)
            stage_start = stage.GetStartTimeCode()
            ref_idx = 0
            for idx, t in enumerate(sample_times):
                if t >= stage_start:
                    ref_idx = idx
                    break
            print(f"[Smart HUD]   P1.5 Reference starts at sample index {ref_idx} "
                  f"(time {sample_times[ref_idx]}, stage start={stage_start})")

            check_count = min(len(sample_times), 3000)
            cycle_frame_idx = None

            try:
                # Get reference matrix at the effective playback start
                ref_matrix = attr.Get(sample_times[ref_idx])
                ref_next_matrix = attr.Get(sample_times[ref_idx + 1]) if ref_idx + 1 < len(sample_times) else None

                if ref_matrix is not None and hasattr(ref_matrix, 'GetRow'):
                    # Log what the reference matrix looks like
                    r3 = ref_matrix.GetRow(3)
                    r0 = ref_matrix.GetRow(0)
                    print(f"[Smart HUD]   P1.5 Ref matrix row0 (X-axis): "
                          f"({r0[0]:.4f}, {r0[1]:.4f}, {r0[2]:.4f})")
                    print(f"[Smart HUD]   P1.5 Ref matrix row3 (translate): "
                          f"({r3[0]:.4f}, {r3[1]:.4f}, {r3[2]:.4f})")

                    # Search forward for where the FULL matrix recurs
                    # Start at ref_idx + 15 to skip initial transition frames
                    min_search_idx = ref_idx + 15
                    for i in range(min_search_idx, check_count):
                        val = attr.Get(sample_times[i])
                        if val is None or not hasattr(val, 'GetRow'):
                            continue

                        # Frobenius norm of (val - ref_matrix) across all 4 rows × 4 cols
                        dist_sq = 0.0
                        for row_idx in range(4):
                            row_ref = ref_matrix.GetRow(row_idx)
                            row_val = val.GetRow(row_idx)
                            for col_idx in range(4):
                                diff = float(row_val[col_idx]) - float(row_ref[col_idx])
                                dist_sq += diff * diff
                        dist = dist_sq ** 0.5

                        if dist < 0.02:  # Near-exact full matrix match
                            # Double-verify: does the NEXT frame also match ref+1?
                            verified = False
                            if ref_next_matrix is not None and i + 1 < check_count:
                                val_next = attr.Get(sample_times[i + 1])
                                if val_next is not None and hasattr(val_next, 'GetRow'):
                                    dist_sq_next = 0.0
                                    for row_idx in range(4):
                                        row_r = ref_next_matrix.GetRow(row_idx)
                                        row_v = val_next.GetRow(row_idx)
                                        for col_idx in range(4):
                                            diff = float(row_v[col_idx]) - float(row_r[col_idx])
                                            dist_sq_next += diff * diff
                                    if dist_sq_next ** 0.5 < 0.02:
                                        verified = True
                            else:
                                verified = True  # Can't verify, accept single match

                            if verified:
                                cycle_frame_idx = i
                                print(f"[Smart HUD]   P1.5 Match at sample {i} "
                                      f"(time {sample_times[i]}), matrix dist={dist:.6f}")
                                break

            except Exception as e:
                print(f"[Smart HUD] ⚠️ P1.5 autocorrelation error: {e}")

            if cycle_frame_idx is not None:
                cycle_start = float(sample_times[ref_idx])
                cycle_end = float(sample_times[cycle_frame_idx])
                cycle_len = cycle_end - cycle_start
                fps = stage.GetTimeCodesPerSecond()
                print(f"[Smart HUD] 🎯 P1.5 Autocorrelation DETECTED cycle!")
                print(f"[Smart HUD]   Cycle: [{cycle_start}, {cycle_end}] = {cycle_len} frames "
                      f"({cycle_len / fps:.2f}s at {fps}fps)")
                print(f"[Smart HUD]   Pattern repeats at sample index {cycle_frame_idx} of {len(sample_times)}")
                return (cycle_start, cycle_end)
            else:
                print(f"[Smart HUD] ⚠️ P1.5 No repeating pattern found in first {check_count} samples")

        # --- P2: All authored attributes with outlier rejection ---
        all_starts = []
        all_ends = []
        try:
            for p in Usd.PrimRange(prim):
                for attr in p.GetAuthoredAttributes():
                    samples = attr.GetTimeSamples()
                    if samples and len(samples) >= 2:
                        all_starts.append(float(samples[0]))
                        all_ends.append(float(samples[-1]))
        except Exception as e:
            print(f"[Smart HUD] ⚠️ TimeSamples scan error: {e}")

        if all_ends:
            median_end = statistics.median(all_ends)
            threshold = max(median_end * 10.0, 1000.0)
            filtered_ends = [e for e in all_ends if e <= threshold]
            filtered_starts = [s for s in all_starts if s <= threshold]

            if filtered_ends:
                start = min(filtered_starts) if filtered_starts else 0.0
                end = max(filtered_ends)
                if (end - start) > 0:
                    print(f"[Smart HUD] 🎯 P2 Filtered TimeSamples bounds: [{start}, {end}] "
                          f"({end - start} frames, rejected {len(all_ends) - len(filtered_ends)} outliers)")
                    return (start, end)

        # --- Final fallback: stage global time range ---
        fallback_start = stage.GetStartTimeCode()
        fallback_end = stage.GetEndTimeCode()
        print(f"[Smart HUD] ⚠️ No animation data found, using stage range: [{fallback_start}, {fallback_end}]")
        return (fallback_start, fallback_end)

    def on_selection_changed(self, hud_data, translation):
        for key, pool_item in self.ui_pool.items():
            pool_item["transform"].visible = False
            
        if hud_data and translation is not None:
            m_type = hud_data.get("type", "")
            
            # --- Dynamically detect animation cycle from the selected prim's subtree ---
            if m_type == "ManualStation":
                stage = omni.usd.get_context().get_stage()
                scan_path = hud_data.get("path", "")
                print(f"[Smart HUD] 🔍 ManualStation selected: {scan_path}")
                
                # Check if the prim has an explicit animation target override
                if scan_path and stage:
                    scan_prim = stage.GetPrimAtPath(scan_path)
                    if scan_prim and scan_prim.IsValid():
                        anim_target_attr = scan_prim.GetAttribute("aif:core:animationTarget")
                        if anim_target_attr and anim_target_attr.IsValid():
                            explicit_target = anim_target_attr.Get()
                            print(f"[Smart HUD] 🔍 Found animationTarget attr, value={repr(explicit_target)}")
                            if explicit_target and str(explicit_target).strip():
                                redirect_path = str(explicit_target).strip()
                                # Verify the target prim actually exists in the stage
                                target_prim = stage.GetPrimAtPath(redirect_path)
                                if target_prim and target_prim.IsValid():
                                    scan_path = redirect_path
                                    print(f"[Smart HUD] 🔗 Redirected to animationTarget: {scan_path}")
                                else:
                                    print(f"[Smart HUD] ⚠️ animationTarget prim not found: {redirect_path}")
                        else:
                            print(f"[Smart HUD] 🔍 No 'aif:core:animationTarget' attribute on {scan_path}")
                
                print(f"[Smart HUD] 🔍 Scanning for animation data at: {scan_path}")
                if scan_path and stage:
                    start_f, end_f = self._get_anim_cycle_frames(stage, scan_path)
                    cycle_len = end_f - start_f
                    
                    if cycle_len > 0:
                        self._cycle_start_frame = start_f
                        self._cycle_end_frame = end_f
                        print(f"[Smart HUD] ✅ Animation cycle: [{start_f}, {end_f}] = {cycle_len} frames")
                    else:
                        # Fallback to safe defaults
                        self._cycle_start_frame = stage.GetStartTimeCode()
                        self._cycle_end_frame = stage.GetEndTimeCode()
                        if (self._cycle_end_frame - self._cycle_start_frame) <= 0:
                            self._cycle_end_frame = self._cycle_start_frame + 100.0
                        print(f"[Smart HUD] ⚠️ No valid cycle detected, using stage range")
            # ------------------------------------

            # 檢查是否為預設的 UI，如果不是則使用 generic_ui
            if m_type not in ["AOI", "Robot", "ManualStation"]:
                m_type = "Generic"  # 將所有自訂的屬性都歸類為使用 Generic UI

            # Create a generic widget pool item if not a preset
            if m_type not in self.ui_pool:
                if self.scene_view and self.scene_view.scene:
                    with self.scene_view.scene:
                        # 呼叫新的建立函式，它會返回完整的字典
                        self.ui_pool[m_type] = self._create_generic_widget(m_type)
                else:
                    return # Safe check if scene is destroyed
                
            # Update generic models if it's a generic type
            if m_type == "Generic":
                self.view_model.generic_title.set_value(hud_data.get("type", ""))
                self.view_model.generic_sub.set_value(hud_data.get("sub", ""))
                self.view_model.generic_content.set_value(hud_data.get("content", ""))

            item = self.ui_pool[m_type]
            
            # Sync Checkbox state from the UI instance to the Engine
            # By passing the state when updating the visibility
            if "dynamic_hud_vbox" in item and item["dynamic_hud_vbox"]:
                item["dynamic_hud_vbox"].visible = hud_data.get("show_dynamic", True)
            if "static_hud_frame" in item and item["static_hud_frame"]:
                item["static_hud_frame"].visible = hud_data.get("show_static", True)
                
            # 處理全不勾選時隱藏整個背景框
            if not hud_data.get("show_dynamic", True) and not hud_data.get("show_static", True):
                if "bg_rect" in item and item["bg_rect"]:
                    item["bg_rect"].visible = False
            else:
                if "bg_rect" in item and item["bg_rect"]:
                    item["bg_rect"].visible = True

            transform_matrix = [
                1, 0, 0, 0,
                0, 1, 0, 0,
                0, 0, 1, 0,
                translation[0], translation[1], translation[2] + 80.0, 1  # 調整高度偏移
            ]
            item["transform"].transform = transform_matrix
            item["transform"].visible = True

    def _start_telemetry(self):
        self._telemetry_task = asyncio.ensure_future(self._telemetry_loop())

    async def _telemetry_loop(self):
        """Async telemetry loop injecting mock data safely into MVVM models.
           Synchronizes Manual Station Takt Time with the local animation cycle
           using frame-range-based modulo for continuous looping.
        """
        while self._running:
            context = omni.usd.get_context()
            stage = context.get_stage()
            
            if stage:
                timeline = omni.timeline.get_timeline_interface()
                fps = stage.GetTimeCodesPerSecond()
                
                # Convert current playback time (seconds) to frame number
                current_frame = timeline.get_current_time() * fps
                
                # Calculate progress using the detected animation cycle bounds
                cycle_start = self._cycle_start_frame
                cycle_end = self._cycle_end_frame
                
                # Fallback to stage bounds if no valid cycle is set
                if cycle_end <= cycle_start:
                    cycle_start = stage.GetStartTimeCode()
                    cycle_end = stage.GetEndTimeCode()
                    
                cycle_len = cycle_end - cycle_start
                
                if cycle_len > 0.0:
                    # Map global frame into local cycle's [0, cycle_len) range
                    # Subtract cycle_start to handle animations that don't begin at frame 0
                    local_frame = (current_frame - cycle_start) % cycle_len
                    ratio = local_frame / cycle_len  # 0.0 → 1.0 over one cycle
                    
                    # Invert: bar shrinks from 100% (cycle start) to 0% (cycle end)
                    progress_pct = max(0.0, min(100.0, (1.0 - ratio) * 100.0))
                else:
                    progress_pct = 100.0
                    
                # Bind the computed progress to the ManualStation UI model
                self.view_model.manual_takt_time_pct.set_value(progress_pct)
            else:
                self.view_model.manual_takt_time_pct.set_value(100.0)

            # Keep AOI and Robot mock data for visual demonstration
            self.view_model.aoi_status.set_value(random.choice(["INSPECTING", "PASS", "FAIL"]))
            self.view_model.aoi_defect_rate.set_value(random.uniform(0.0, 5.0))
            self.view_model.robot_state.set_value(random.choice(["MOVING", "WELDING", "IDLE"]))
            
            # Update at ~20 FPS — no blocking calls, safe for the Omniverse UI thread
            await asyncio.sleep(0.05)

    def destroy(self):
        self._running = False
        if self._selection_agent:
            self._selection_agent.destroy()
            self._selection_agent = None
        self._telemetry_task = None
        self._color_sub = None
        
        # Clear UI Pool completely to ensure no detached widgets remain
        self.ui_pool.clear()
        
        # Safe cleanup of Viewport Overlay
        if self.viewport_window:
            if hasattr(self.viewport_window, "viewport_api") and self.scene_view:
                try:
                    self.viewport_window.viewport_api.remove_scene_view(self.scene_view)
                except:
                    pass
            # Clear the frame to destroy the UI elements
            frame = self.viewport_window.get_frame("DSX_Phase7_HUD_Overlay")
            if frame:
                frame.clear()
        
        self.scene_view = None
        self.viewport_window = None


# ==============================================================================
# Zin Tools Box UI Interface
# ==============================================================================
class SmartHudUI:
    """
    UI Class managed by Zin Tools Box.
    Handles the toggle logic for the HUD Engine and Metadata configuration.
    """
    
    # Define styles locally to ensure they render correctly even inside nested frames
    _STYLE_DEFAULT = {
        "Button": {"background_color": 0xFF343432, "border_radius": 4, "margin": 2},
        "Button:hovered": {"background_color": 0xFF4A4A48},
        "Button:pressed": {"background_color": 0xFF5A5A58},
    }
    _STYLE_CORRECT = {
        "Button": {"background_color": 0xFF2A5E2A, "border_radius": 4, "margin": 2},
        "Button:hovered": {"background_color": 0xFF33703A},
        "Button:pressed": {"background_color": 0xFF44AA44},
    }
    _STYLE_ERROR = {
        "Button": {"background_color": 0xFF5E2A2A, "border_radius": 4, "margin": 2},
        "Button:hovered": {"background_color": 0xFF703333},
        "Button:pressed": {"background_color": 0xFFAA4444},
    }

    def __init__(self):
        self.engine = None
        self.is_enabled = False

    def build_ui(self):
        """Builds the 2D control panel inside the Zin Tools Box."""
        with ui.VStack(spacing=2):
            
            with ui.HStack(height=30, spacing=10):
                # Toggle Button
                button_text = "Turn OFF" if self.is_enabled else "Turn ON"
                button_style = self._STYLE_ERROR if self.is_enabled else self._STYLE_CORRECT
                
                self.toggle_btn = ui.Button(
                    button_text, 
                    style=button_style,
                    clicked_fn=self._on_toggle_clicked
                )
                
                ui.Button(
                    "Generate Test Graybox Scene",
                    style=self._STYLE_DEFAULT,
                    clicked_fn=self._create_test_scene,
                    tooltip="Creates 3 Graybox test machines with 'machine_type' attributes properly configured."
                )

            ui.Spacer(height=10)
            
            with ui.CollapsableFrame("Add / Edit HUD Metadata", collapsed=False, style={"font_size": 16, "color": 0xFFFFFFFF}):
                with ui.VStack(spacing=2, padding=6):
                    ui.Label("Add custom attributes to make selected models compatible with HUD and Info Panel:", 
                             style={"color": 0xFFAAAAAA, "font_size": 14})
                    
                    with ui.HStack(height=24, spacing=10):
                        ui.Label("Topic (Machine Type):", width=140, style={"color": 0xFFDDDDDD}, tooltip="Will be written to 'aif:core:assetClass' and displayed as 'Asset Class' in Factory Info.")
                        self.topic_field = ui.StringField(style={"color": 0xFFDDDDDD})
                        self.topic_field.model.set_value("ManualStation")
                        
                    with ui.HStack(height=24, spacing=10):
                        ui.Label("Subject (Sub Title):", width=140, style={"color": 0xFFDDDDDD}, tooltip="Will be written to 'aif:core:modelNumber' and displayed as 'Model No' in Factory Info.")
                        self.subject_field = ui.StringField(style={"color": 0xFFDDDDDD})
                        self.subject_field.model.set_value("S01")
                        
                    with ui.HStack(height=24, spacing=10):
                        ui.Label("Content:", width=140, style={"color": 0xFFDDDDDD}, tooltip="Will be written to 'aif:core:assetDescription'. Status is hardcoded to 'Active' for demo.")
                        self.content_field = ui.StringField(style={"color": 0xFFDDDDDD})
                        self.content_field.model.set_value("Chassis")
                    
                    ui.Spacer(height=5)
                    with ui.HStack(spacing=10, height=30):
                        ui.Button(
                            "Add / Update",
                            style=self._STYLE_CORRECT,
                            clicked_fn=self._apply_attributes_to_selected,
                            tooltip="Adds or updates HUD and AIF metadata attributes for selected models."
                        )
                        ui.Button(
                            "Remove",
                            style=self._STYLE_ERROR,
                            clicked_fn=self._remove_attributes_from_selected,
                            tooltip="Removes HUD attributes from selected models."
                        )
                        
            ui.Spacer(height=10)
            with ui.CollapsableFrame("Animation Binding", collapsed=False, style={"font_size": 16, "color": 0xFFFFFFFF}):
                with ui.VStack(spacing=2, padding=6):
                    ui.Label("Bind HUD progress to a specific animated character (optional):", style={"color": 0xFFAAAAAA, "font_size": 13})
                    with ui.HStack(height=24, spacing=10):
                        ui.Label("Anim Target:", width=90, style={"color": 0xFFDDDDDD}, tooltip="Absolute path to the animated prim. Used to sync the progress bar.")
                        self.anim_target_field = ui.StringField(style={"color": 0xFFDDDDDD})
                        self.anim_target_field.model.set_value("/World/IMX_Factory_After/ASSET/asset_IMX_Factory_After_v2/Lifting_4/Scene1")
                    ui.Button(
                        "Bind to Selected",
                        height=24,
                        style=self._STYLE_DEFAULT,
                        clicked_fn=self._bind_animation_target,
                        tooltip="Writes 'aif:core:animationTarget' to the selected prims."
                    )

            ui.Spacer(height=10)
            with ui.CollapsableFrame("Display Settings", collapsed=False, style={"font_size": 16, "color": 0xFFFFFFFF}):
                with ui.VStack(spacing=2, padding=6):
                    ui.Label("Select information to display on the HUD overlay:", style={"color": 0xFFAAAAAA, "font_size": 13})
                    
                    with ui.HStack(height=22, spacing=6):
                        self.cb_dynamic = ui.CheckBox(width=18, height=18)
                        self.cb_dynamic.model.set_value(True)
                        self.cb_dynamic.model.add_value_changed_fn(self._on_display_setting_changed)
                        ui.Label("Dynamic HUD Status", style={"color": 0xFFDDDDDD, "font_size": 13})

                    with ui.HStack(height=22, spacing=6):
                        self.cb_static = ui.CheckBox(width=18, height=18)
                        self.cb_static.model.set_value(True)
                        self.cb_static.model.add_value_changed_fn(self._on_display_setting_changed)
                        ui.Label("Factory Info (Metadata)", style={"color": 0xFFDDDDDD, "font_size": 13})

            ui.Spacer()
        # Notify the UsdSelectionAgent to re-evaluate and trigger on_selection_changed
        if self.is_enabled and self.engine and self.engine._selection_agent:
             self.engine._selection_agent._handle_selection()

    def _bind_animation_target(self):
        context = omni.usd.get_context()
        stage = context.get_stage()
        if not stage: return
        selection = context.get_selection().get_selected_prim_paths()
        if not selection: return
        
        target_path = self.anim_target_field.model.get_value_as_string()
        if not target_path: return
        
        for path in selection:
            prim = stage.GetPrimAtPath(path)
            if prim and prim.IsValid():
                attr = prim.GetAttribute("aif:core:animationTarget")
                if not attr:
                    attr = prim.CreateAttribute("aif:core:animationTarget", Sdf.ValueTypeNames.String)
                attr.Set(target_path)
                attr.SetDocumentation("Path to the animated character driving this station's progress [AIF-MANAGED]")
                attr.SetCustomData({'omni': {'kit': {'locked': True}}})
                print(f"[Smart HUD] 🔗 Bound animation target {target_path} to {path}")

    def _apply_attributes_to_selected(self):
        import omni.usd
        from pxr import Sdf
        
        context = omni.usd.get_context()
        stage = context.get_stage()
        if not stage:
            print("[Smart HUD] ❌ Error: No USD stage is currently open.")
            return

        selection = context.get_selection().get_selected_prim_paths()
        if not selection:
            print("[Smart HUD] ⚠️ No models selected. Please select a model in the stage first.")
            return

        topic = self.topic_field.model.get_value_as_string()
        subject = self.subject_field.model.get_value_as_string()
        content = self.content_field.model.get_value_as_string()

        for path in selection:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue

            # 1. Add smart_hud attributes
            attr_type = prim.GetAttribute("machine_type")
            if not attr_type: attr_type = prim.CreateAttribute("machine_type", Sdf.ValueTypeNames.String)
            attr_type.Set(topic)
            
            attr_sub = prim.GetAttribute("hud_sub_title")
            if not attr_sub: attr_sub = prim.CreateAttribute("hud_sub_title", Sdf.ValueTypeNames.String)
            attr_sub.Set(subject)
            
            attr_cont = prim.GetAttribute("hud_content")
            if not attr_cont: attr_cont = prim.CreateAttribute("hud_content", Sdf.ValueTypeNames.String)
            attr_cont.Set(content)

            # 2. Add smart_info_panel attributes (aif:core and aif:spec)
            # 遵循 AIF Pipeline Samples 綁定規範 (AIF-MANAGED, Locked)
            aif_attrs = {
                "aif:core:assetClass": {
                    "value": topic, 
                    "doc": "Class of AI Factory Equipment"
                },
                "aif:core:modelNumber": {
                    "value": subject, 
                    "doc": "Equipment model number"
                },
                "aif:core:manufacturer": {
                    "value": "Inventec", 
                    "doc": "Equipment manufacturer name"
                },
                "aif:core:assetDescription": {
                    "value": content, 
                    "doc": "Human Readable Description of Asset"
                },
                "aif:spec:status": {
                    "value": "Active", 
                    "doc": "Current status of the equipment"
                }
            }

            for attr_name, attr_info in aif_attrs.items():
                attr = prim.GetAttribute(attr_name)
                if not attr:
                    attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.String)
                attr.Set(attr_info["value"])
                
                # 遵循 AIF 規範：加入 [AIF-MANAGED] 標籤與鎖定屬性
                managed_doc = f"{attr_info['doc']} [AIF-MANAGED]"
                attr.SetDocumentation(managed_doc)
                
                custom_data = {
                    'omni': {
                        'kit': {
                            'locked': True
                        }
                    }
                }
                attr.SetCustomData(custom_data)
                
            print(f"[Smart HUD] ✅ Applied HUD and AIF-MANAGED attributes to {path}")

    def _remove_attributes_from_selected(self):
        import omni.usd
        
        context = omni.usd.get_context()
        stage = context.get_stage()
        if not stage: return

        selection = context.get_selection().get_selected_prim_paths()
        if not selection: return

        attrs_to_remove = [
            "machine_type", "hud_sub_title", "hud_content",
            "aif:core:assetClass", "aif:core:modelNumber", 
            "aif:core:manufacturer", "aif:core:assetDescription", 
            "aif:spec:status"
        ]

        for path in selection:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid(): continue
            
            for attr_name in attrs_to_remove:
                prim.RemoveProperty(attr_name)
                
            print(f"[Smart HUD] 🗑️ Removed HUD and Info Panel attributes from {path}")

    def _create_test_scene(self):
        import omni.usd
        from pxr import UsdGeom, Sdf, Gf
        
        stage = omni.usd.get_context().get_stage()
        if not stage:
            print("[Smart HUD] ❌ Error: No USD stage is currently open. Please create or open a stage first.")
            return

        machines = {
            "AOI": Gf.Vec3d(0, 0, 100),
            "Robot": Gf.Vec3d(300, 0, 100),
            "ManualStation": Gf.Vec3d(-300, 0, 100)
        }

        world_path = "/World"
        if not stage.GetPrimAtPath(world_path):
            UsdGeom.Xform.Define(stage, world_path)

        for m_type, pos in machines.items():
            path = f"{world_path}/Graybox_{m_type}"
            cube = UsdGeom.Cube.Define(stage, path)
            
            # Set realistic size (e.g., 200 cm)
            cube.GetSizeAttr().Set(200.0)
            
            # Set position using XformCommonAPI to avoid appending multiple ops
            xform_api = UsdGeom.XformCommonAPI(cube)
            xform_api.SetTranslate(pos)
            
            # Add the custom 'machine_type' attribute
            prim = cube.GetPrim()
            attr = prim.GetAttribute("machine_type")
            if not attr:
                attr = prim.CreateAttribute("machine_type", Sdf.ValueTypeNames.String)
            attr.Set(m_type)
            
            print(f"[Smart HUD] Created {m_type} at {path}")

    def _on_toggle_clicked(self):
        self.is_enabled = not self.is_enabled
        
        if self.is_enabled:
            self.toggle_btn.text = "Turn OFF"
            self.toggle_btn.set_style(self._STYLE_ERROR)
            if not self.engine:
                self.engine = GrayboxHUDEngine(self)
        else:
            self.toggle_btn.text = "Turn ON"
            self.toggle_btn.set_style(self._STYLE_CORRECT)
            if self.engine:
                self.engine.destroy()
                self.engine = None

    def shutdown(self):
        """Called by ToolsBox on extension shutdown"""
        if self.engine:
            self.engine.destroy()
            self.engine = None
        self.is_enabled = False
