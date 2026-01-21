import omni.ext
import omni.ui as ui
import omni.usd
from pxr import UsdGeom, Usd, Gf

class SmartAlignExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self._usd_context = omni.usd.get_context()
        self._selection = self._usd_context.get_selection()
        # 監聽 selection 變化
        self._events = self._usd_context.get_stage_event_stream()
        self._stage_event_sub = self._events.create_subscription_to_pop(
            self._on_stage_event, name='align_extension')
        self._current_paths = []
        self._window = ui.Window("Align Prim Tools", width=350, height=190,
                                 flags=ui.WINDOW_FLAGS_NO_RESIZE | ui.WINDOW_FLAGS_NO_COLLAPSE)
        with self._window.frame:
            with ui.VStack():
                self._combo = ui.ComboBox()
                self._combo_model = self._combo.model
                with ui.HStack():
                    ui.Button("Left", clicked_fn=lambda: self._align_selected("left"))
                    ui.Button("Right", clicked_fn=lambda: self._align_selected("right"))
                    ui.Button("Center Horizon", clicked_fn=lambda: self._align_selected("center_horizon"))
                with ui.HStack():
                    ui.Button("Top", clicked_fn=lambda: self._align_selected("top"))
                    ui.Button("Bottom", clicked_fn=lambda: self._align_selected("bottom"))
                    ui.Button("Center Vertical", clicked_fn=lambda: self._align_selected("center_vertical"))
                with ui.HStack():
                    ui.Button("Pivot", clicked_fn=lambda: self._align_selected("pivot"))
                    ui.Button("Align Center", clicked_fn=lambda: self._align_selected("center"))
        self._update_combobox()

    def on_shutdown(self):
        self._window = None
        self._stage_event_sub = None

    def _on_stage_event(self, event):
        # 每當 SELECTION_CHANGED 事件發生時，更新 ComboBox
        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            self._update_combobox()

    def _update_combobox(self):
        sel_paths = self._selection.get_selected_prim_paths()
        self._current_paths = sel_paths if sel_paths else []
        for item in list(self._combo_model.get_item_children()):
            self._combo_model.remove_item(item)
        for path in self._current_paths:
            self._combo_model.append_child_item(None, ui.SimpleStringModel(path))
        if self._current_paths:
            self._combo_model.get_item_value_model().set_value(0)

    def _align_selected(self, mode):
        if not self._current_paths:
            return
        combo_index = self._combo_model.get_item_value_model().as_int
        if combo_index is None or combo_index < 0 or combo_index >= len(self._current_paths):
            return
        ref_path = self._current_paths[combo_index]
        stage = self._usd_context.get_stage()
        if stage is None:
            return
        up_axis = UsdGeom.GetStageUpAxis(stage)
        vert_index = 1 if up_axis == UsdGeom.Tokens.y else 2
        ref_bbox = self._usd_context.compute_path_world_bounding_box(ref_path)
        if not ref_bbox:
            return
        ref_min, ref_max = ref_bbox
        ref_min_x = ref_min[0]; ref_max_x = ref_max[0]
        ref_center_x = 0.5 * (ref_min_x + ref_max_x)
        ref_min_v = ref_min[vert_index]; ref_max_v = ref_max[vert_index]
        ref_center_v = 0.5 * (ref_min_v + ref_max_v)
        ref_center_3d = Gf.Vec3d(
            (ref_min[0] + ref_max[0]) * 0.5,
            (ref_min[1] + ref_max[1]) * 0.5,
            (ref_min[2] + ref_max[2]) * 0.5
        )
        # Pivot處理
        ref_prim = stage.GetPrimAtPath(ref_path)
        ref_pivot = None
        try:
            ref_xform = UsdGeom.Xformable(ref_prim)
            pivot_attr = ref_prim.GetAttribute("xformOp:translate:pivot")
            if pivot_attr and pivot_attr.HasAuthoredValue():
                ref_pivot = Gf.Vec3d(pivot_attr.Get())
        except Exception:
            pass

        for i, path in enumerate(self._current_paths):
            if i == combo_index:
                continue
            prim = stage.GetPrimAtPath(path)
            if not prim:
                continue
            bbox = self._usd_context.compute_path_world_bounding_box(path)
            if not bbox:
                continue
            cur_min, cur_max = bbox
            cur_min_x = cur_min[0]; cur_max_x = cur_max[0]
            cur_center_x = 0.5 * (cur_min_x + cur_max_x)
            cur_min_v = cur_min[vert_index]; cur_max_v = cur_max[vert_index]
            cur_center_v = 0.5 * (cur_min_v + cur_max_v)
            cur_center_3d = Gf.Vec3d(
                (cur_min[0] + cur_max[0]) * 0.5,
                (cur_min[1] + cur_max[1]) * 0.5,
                (cur_min[2] + cur_max[2]) * 0.5
            )
            xform = UsdGeom.XformCommonAPI(prim)
            current_translate, _, _, _, _ = xform.GetXformVectors(Usd.TimeCode.Default())
            translate_delta = [0.0, 0.0, 0.0]
            if mode == "left":
                translate_delta[0] = ref_min_x - cur_min_x
            elif mode == "right":
                translate_delta[0] = ref_max_x - cur_max_x
            elif mode == "center_horizon":
                translate_delta[0] = ref_center_x - cur_center_x
            elif mode == "top":
                translate_delta[vert_index] = ref_max_v - cur_max_v
            elif mode == "bottom":
                translate_delta[vert_index] = ref_min_v - cur_min_v
            elif mode == "center_vertical":
                translate_delta[vert_index] = ref_center_v - cur_center_v
            elif mode == "pivot" and ref_pivot is not None:
                pivot_attr = prim.GetAttribute("xformOp:translate:pivot")
                if pivot_attr and pivot_attr.HasAuthoredValue():
                    cur_pivot = Gf.Vec3d(pivot_attr.Get())
                    translate_delta = [
                        ref_pivot[0] - cur_pivot[0],
                        ref_pivot[1] - cur_pivot[1],
                        ref_pivot[2] - cur_pivot[2]
                    ]
                else:
                    continue
            elif mode == "center":
                # Align object's bounding box center to reference object's center (3D)
                translate_delta = [
                    ref_center_3d[0] - cur_center_3d[0],
                    ref_center_3d[1] - cur_center_3d[1],
                    ref_center_3d[2] - cur_center_3d[2]
                ]
            else:
                continue
            new_translate = (
                current_translate[0] + translate_delta[0],
                current_translate[1] + translate_delta[1],
                current_translate[2] + translate_delta[2]
            )
            xform.SetTranslate(new_translate)
