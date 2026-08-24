# Zin Pipeline: 3ds Max to Omniverse USD - AI Handoff Context

> **To the AI Agent reading this (e.g., Cursor, GitHub Copilot, Cline):**
> This document contains the architectural context, requirements history, and codebase logic for the "Zin Pipeline". Read this carefully before modifying scripts to ensure you don't break existing data flows or pipeline integrations.

## 1. Project Overview
This project is an automated asset pipeline bridging **3ds Max** (Data Preparation & Naming) and **NVIDIA Omniverse** (USD Generation & Material Binding).
The core workflow is:
1.  **3ds Max**: User selects a CAD part, uses `Zin_CAD_SelectSimilar` to find identical parts, and renames them to a standardized base name (e.g., `BlackPlastic_01`).
2.  **Export**: Meshes are exported from 3ds Max as `max_*.usd`.
3.  **Omniverse**: The `tw.zin.smart_assets_builder` extension scans `max_*.usd` files, builds `asset_*.usd` hierarchy, and **automatically binds MDL materials** based on a shared JSON mapping file.

## 2. Component A: 3ds Max Script (`Zin_CAD_SelectSimilar.mcr`)
*   **Path**: `D:\Inventec\Zin_All_Tools\max_script\Zin_CAD_SelectSimilar.mcr`
*   **Data Path**: `D:\Inventec\Zin_All_Tools\max_script\Zin_CAD_SelectSimilar\`
*   **Core Functionality**:
    *   **Selection Filters**: Matches Geometry or Helper based on Bounding Box size (`obj.max - obj.min`), Vertex/Face count (`GetTriMeshFaceCount`), or Base/Custom Name.
    *   **Quick Names CRUD**: A dropdown for rapid renaming. Users can Add, Edit, or Delete names. 
    *   **Dual File Output Mechanism**: 
        *   `QuickNames.ini`: Stores the UI state for 3ds Max across sessions.
        *   `QuickNames.json`: Automatically generated alongside the INI. It acts as the bridging dictionary for the Omniverse Python extension.
*   **Critical Rule**: When updating `QuickNames.json`, the MaxScript uses a custom string parser to preserve any existing `material_prim_path` strings filled in by the user. **DO NOT overwrite user-defined MDL paths when regenerating this JSON.**

## 3. Component B: JSON Mapping Schema
*   **Path**: `D:\Inventec\Zin_All_Tools\max_script\Zin_CAD_SelectSimilar\QuickNames.json`
*   **Structure**: Designed for O(1) dictionary lookup in Python.
```json
{
  "USD_Material_Library": "D:/Inventec/DigitalTwin/Library/Material_Collects.usd",
  "MaterialMappings": {
    "BlackPlastic": {
      "material_prim_path": "/World/Looks/Plastic/Pristine_Plastic_Grain_Fine_Point_Matte",
      "description": "Auto-generated from 3ds Max CAD Select Similar"
    }
  }
}
```

## 4. Component C: Omniverse Extension (`tw.zin.smart_assets_builder`)
*   **Path**: `D:\Inventec\Zin_All_Tools\exts\tw.zin.smart_assets_builder\smart_assets_builder\extension.py`
*   **Core Functionality**:
    *   Scans directories for `max_*.usd`.
    *   Generates `asset_*.usd` and `id_*.usd` using `pxr.UsdGeom`.
    *   **Auto Material Binding**: Reads `QuickNames.json`. If `USD_Material_Library` is defined, it adds it to the root layer's `subLayerPaths`. It then traverses the stage, finds `UsdGeom.Mesh` prims, extracts their base name (stripping `_XX` suffixes), looks up the JSON dictionary, and binds the material using `UsdShade.MaterialBindingAPI(prim).Bind(material)`.
*   **Known Edge Cases Resolved**:
    *   **Cross-Drive Absolute Paths**: A custom `_dotify_rel` function was updated to NOT prefix Windows absolute paths (like `D:/...`) with `./`, preventing fatal USD relative path resolution errors when source and destination are on different drives.

## 5. Guidelines for Future AI Development
1.  **Language**: All future scripts, variable names, and code comments must strictly use **English**.
2.  **3ds Max Compatibility**: Use `superclassof obj == GeometryClass` when filtering for CAD models. MaxScript `.mcr` macros must be maintained in the `usermacros` directory to reflect UI changes.
3.  **Omniverse Python (pxr)**: 
    *   Be cautious with `os.path.relpath` across Windows drives.
    *   When binding materials from a SubLayer, using `stage.OverridePrim(mat_path)` ensures `UsdShade.Material` has a valid prim to wrap, even if the payload hasn't fully computed in the scene graph yet.
    *   Handle empty `material_prim_path` gracefully (skip binding) to support gradual user workflow.
