import omni.ext
import omni.ui as ui
import omni.usd
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Sdf, Gf

class SmartPhysicsSetupExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self._init_data()

    def on_shutdown(self):
        self._rigid_paths = []
        self._soft_paths = []

    # ----------------------------------------------------------------------
    #  UI Layout
    # ----------------------------------------------------------------------
    def build_ui_layout(self):
        if not hasattr(self, "_rigid_paths"):
            self._init_data()

        # [Bug Fix] 將 ScrollingFrame 存入變數，後面才能 return
        scroll_frame = ui.ScrollingFrame(
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
        )
        with scroll_frame:
            with ui.VStack(spacing=10, padding=10):
                
                # --- 1. Rigid Body ---
                with ui.CollapsableFrame("1. Rigid Body (Connectors)", height=0):
                    with ui.VStack(spacing=5, height=0):
                        ui.Button("Add Selected to Rigid List", clicked_fn=self._add_to_rigid, height=40)
                        
                        with ui.HStack(height=20):
                            ui.Label("Make Static (Kinematic):", width=ui.Pixel(150), tooltip="Check this if the plug should NOT fall.")
                            ui.CheckBox(model=self._kinematic_model)

                        ui.Label("Current List:", style={"color": 0xFFAAAAAA})
                        ui.StringField(model=self._rigid_list_str, height=60, multiline=True, read_only=True)

                # --- 2. Soft Body ---
                with ui.CollapsableFrame("2. Soft Body (Cable)", height=0):
                    with ui.VStack(spacing=5, height=0):
                        ui.Button("Add Selected to Soft List", clicked_fn=self._add_to_soft, height=40)
                        
                        ui.Label("Current List:", style={"color": 0xFFAAAAAA})
                        ui.StringField(model=self._soft_list_str, height=60, multiline=True, read_only=True)

                # --- 3. Params ---
                with ui.CollapsableFrame("3. Physics Parameters", height=0):
                    with ui.VStack(spacing=5, height=0):
                        with ui.HStack():
                            ui.Label("Contact Offset:", width=ui.Pixel(150))
                            ui.FloatDrag(model=self._contact_offset_model, min=0.0001, max=0.1, step=0.0001)
                        with ui.HStack():
                            ui.Label("Stiffness:", width=ui.Pixel(150))
                            ui.FloatDrag(model=self._stiffness_model, min=100.0, max=1000000.0, step=100.0)

                # --- 4. Attachment ---
                with ui.CollapsableFrame("4. Attachment (Auto-Bind)", height=0):
                    with ui.VStack(spacing=5, height=0):
                        ui.Label("Auto-bind Soft to Rigid objects.", style={"color": 0xFF888888})
                        with ui.HStack():
                            ui.Label("Attachment Range:", width=ui.Pixel(150))
                            ui.FloatDrag(model=self._attach_distance_model, min=0.001, max=0.1, step=0.001)

                ui.Separator(height=10)

                # --- Actions ---
                with ui.HStack(height=40, spacing=10):
                    btn_apply = ui.Button("Apply All (Fix Visibility)", clicked_fn=self._apply_physics_logic, style={"background_color": 0xFF225522})
                    self._setup_hover(btn_apply, 0xFF225522)
                    ui.Button("Reset Lists", clicked_fn=self._clear_lists)


                # --- Status ---
                ui.StringField(
                    model=self._status_model, 
                    height=30, 
                    read_only=True, 
                    alignment=ui.Alignment.CENTER,
                    style={"background_color": 0x00000000, "border_width": 0, "color": 0xFFFFFF00}
                )

        return scroll_frame  # [Bug Fix] 必須 return，否則 tools_box 嵌入時特此 tab 會顯示空白

    # ----------------------------------------------------------------------
    #  Initialization & Logic
    # ----------------------------------------------------------------------
    def _init_data(self):
        self._rigid_paths = []
        self._soft_paths = []
        
        self._default_contact_offset = 0.002
        self._default_stiffness = 10000.0
        self._default_attach_dist = 0.005
        self._particle_system_path = "/World/ParticleSystem"

        self._contact_offset_model = ui.SimpleFloatModel(self._default_contact_offset)
        self._stiffness_model = ui.SimpleFloatModel(self._default_stiffness)
        self._attach_distance_model = ui.SimpleFloatModel(self._default_attach_dist)
        self._kinematic_model = ui.SimpleBoolModel(False) 

        self._rigid_list_str = ui.SimpleStringModel("")
        self._soft_list_str = ui.SimpleStringModel("")
        self._status_model = ui.SimpleStringModel("Ready")

        self._status_model = ui.SimpleStringModel("Ready")

    # [UX] Hover Helper
    def _setup_hover(self, btn, base_color):
        if not btn: return
        
        # Calc brighter color (+40%)
        # Format: 0xAABBGGRR
        a = (base_color >> 24) & 0xFF
        b = (base_color >> 16) & 0xFF
        g = (base_color >> 8) & 0xFF
        r = base_color & 0xFF
        
        # Increase brightness
        b = min(255, int(b * 1.4))
        g = min(255, int(g * 1.4))
        r = min(255, int(r * 1.4))
        
        hover_color = (a << 24) | (b << 16) | (g << 8) | r
        
        def _on_hover(hovered):
            btn.style = {"background_color": hover_color if hovered else base_color}
            
        btn.set_mouse_hovered_fn(_on_hover)

    def _get_current_selection(self):
        ctx = omni.usd.get_context()
        return ctx.get_selection().get_selected_prim_paths()

    def _add_to_rigid(self):
        paths = self._get_current_selection()
        for path in paths:
            if path not in self._rigid_paths: self._rigid_paths.append(path)
            if path in self._soft_paths: self._soft_paths.remove(path)
        self._update_lists()

    def _add_to_soft(self):
        paths = self._get_current_selection()
        for path in paths:
            if path not in self._soft_paths: self._soft_paths.append(path)
            if path in self._rigid_paths: self._rigid_paths.remove(path)
        self._update_lists()

    def _clear_lists(self):
        self._rigid_paths = []
        self._soft_paths = []
        self._update_lists()
        self._status_model.as_string = "Lists Cleared"

    def _update_lists(self):
        self._rigid_list_str.as_string = "\n".join(self._rigid_paths) if self._rigid_paths else "(Empty)"
        self._soft_list_str.as_string = "\n".join(self._soft_paths) if self._soft_paths else "(Empty)"

    def _safe_set_attribute(self, prim, attr_name, value, type_name=Sdf.ValueTypeNames.Float):
        attr = prim.GetAttribute(attr_name)
        if not attr: attr = prim.CreateAttribute(attr_name, type_name)
        attr.Set(value)

    def _clean_physics_api(self, prim):
        # NUKE: Remove all physics APIs to reset state
        apis_to_remove = [
            UsdPhysics.RigidBodyAPI, UsdPhysics.CollisionAPI, UsdPhysics.MeshCollisionAPI, UsdPhysics.MassAPI,
            PhysxSchema.PhysxParticleClothAPI, PhysxSchema.PhysxAutoParticleClothAPI, 
            PhysxSchema.PhysxParticleSamplingAPI, PhysxSchema.PhysxParticleAPI,
            PhysxSchema.PhysxRigidBodyAPI, PhysxSchema.PhysxCollisionAPI
        ]
        for api in apis_to_remove:
            if prim.HasAPI(api): prim.RemoveAPI(api)

    def _create_attachment(self, stage, soft_path, rigid_path, distance):
        soft_name = Sdf.Path(soft_path).name
        rigid_name = Sdf.Path(rigid_path).name
        attach_path = f"/World/Attachments/Attach_{soft_name}_to_{rigid_name}"
        
        if not stage.GetPrimAtPath("/World/Attachments"):
            UsdGeom.Scope.Define(stage, "/World/Attachments")

        attachment = PhysxSchema.PhysxPhysicsAttachment.Define(stage, attach_path)
        attachment.GetActor0Rel().SetTargets([Sdf.Path(rigid_path)])
        attachment.GetActor1Rel().SetTargets([Sdf.Path(soft_path)])
        
        prim = attachment.GetPrim()
        self._safe_set_attribute(prim, "physxAttachment:filterType", "distance", Sdf.ValueTypeNames.Token)
        self._safe_set_attribute(prim, "physxAttachment:filterDistance", distance, Sdf.ValueTypeNames.Float)
        
        return attach_path

    def _apply_physics_logic(self):
        ctx = omni.usd.get_context()
        stage = ctx.get_stage()

        contact_offset = self._contact_offset_model.as_float
        rest_offset = contact_offset * 0.5
        stiffness = self._stiffness_model.as_float
        attach_dist = self._attach_distance_model.as_float
        is_kinematic = self._kinematic_model.as_bool
        
        self._status_model.as_string = "Processing..."
        print(f"--- Starting Physics Setup (v5.3 Stable) ---")

        try:
            # Step A: Particle System
            particle_sys_prim = stage.GetPrimAtPath(self._particle_system_path)
            if not particle_sys_prim.IsValid():
                particle_sys = PhysxSchema.PhysxParticleSystem.Define(stage, self._particle_system_path)
            else:
                particle_sys = PhysxSchema.PhysxParticleSystem(particle_sys_prim)
            
            particle_sys.CreateParticleContactOffsetAttr().Set(contact_offset)
            particle_sys.CreateRestOffsetAttr().Set(rest_offset)
            particle_sys.CreateEnableCCDAttr().Set(True)

            # Step B: Rigid Body (Connectors)
            for path in self._rigid_paths:
                prim = stage.GetPrimAtPath(path)
                if not prim.IsValid(): continue
                
                # Clean root to remove any invalid schemas (like MeshCollision on Xform)
                self._clean_physics_api(prim)
                
                # 1. Apply Rigid Body to Root (handles transform/physics)
                UsdPhysics.RigidBodyAPI.Apply(prim)
                if is_kinematic:
                    self._safe_set_attribute(prim, "physics:kinematicEnabled", True, Sdf.ValueTypeNames.Bool)

                # 2. Identify Meshes for Collision
                # If prim is Xform, we must apply collision to child meshes, NOT the Xform itself.
                collision_meshes = []
                if prim.IsA(UsdGeom.Mesh):
                    collision_meshes.append(prim)
                else:
                    # Recursive search for Meshes
                    for child in Usd.PrimRange(prim):
                        if child != prim and child.IsA(UsdGeom.Mesh):
                            collision_meshes.append(child)

                # 3. Apply Collision to Meshes
                for mesh_prim in collision_meshes:
                    # Ensure child meshes have collision enabled
                    UsdPhysics.CollisionAPI.Apply(mesh_prim)
                    mesh_collision = UsdPhysics.MeshCollisionAPI.Apply(mesh_prim)
                    mesh_collision.CreateApproximationAttr().Set("convexHull")

            # Step C: Soft Body
            for path in self._soft_paths:
                prim = stage.GetPrimAtPath(path)
                if not prim.IsValid(): continue

                self._clean_physics_api(prim)
                PhysxSchema.PhysxParticleClothAPI.Apply(prim)
                PhysxSchema.PhysxAutoParticleClothAPI.Apply(prim)
                PhysxSchema.PhysxParticleSamplingAPI.Apply(prim)

                self._safe_set_attribute(prim, "physxAutoParticleCloth:springStretchStiffness", stiffness)
                self._safe_set_attribute(prim, "physxAutoParticleCloth:springBendStiffness", 500.0)
                self._safe_set_attribute(prim, "physxAutoParticleCloth:springShearStiffness", 100.0)
                self._safe_set_attribute(prim, "physxAutoParticleCloth:enableRemeshing", False, Sdf.ValueTypeNames.Bool)
                self._safe_set_attribute(prim, "physxParticleSampling:samplingMode", "vertices", Sdf.ValueTypeNames.Token)
                self._safe_set_attribute(prim, "physxParticle:selfCollision", True, Sdf.ValueTypeNames.Bool)

                rel = prim.GetRelationship("physxParticle:particleSystem")
                if not rel: rel = prim.CreateRelationship("physxParticle:particleSystem")
                rel.SetTargets([Sdf.Path(self._particle_system_path)])

            # Step D: Attachments
            count = 0
            for soft in self._soft_paths:
                for rigid in self._rigid_paths:
                    self._create_attachment(stage, soft, rigid, attach_dist)
                    count += 1
            
            msg = f"Setup Complete. {count} attachments created."
            self._status_model.as_string = f"Success: {msg}"
            print(msg)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._status_model.as_string = f"Error: {str(e)}"
            print(f"Error: {e}")