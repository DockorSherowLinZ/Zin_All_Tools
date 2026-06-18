from pxr import Usd, UsdShade, UsdGeom
import sys, os

file_path = "D:/Inventec/Asset/Product/Server/P9000IG7/PoC/CARDS_STEP/max_1395a3705801_asm_Pre_iec.usd"
stage = Usd.Stage.Open(file_path)

if not stage:
    print("Failed to open master USD")
    sys.exit(1)

print(f"--- Inspecting Master USD: {os.path.basename(file_path)} ---")

# Find a sample reference node
ref_nodes = [p for p in stage.Traverse() if p.GetName().startswith("Payload")]

if not ref_nodes:
    print("No nodes starting with 'Payload' found.")
else:
    sample_node = ref_nodes[0]
    print(f"\nFound sample reference node: {sample_node.GetPath()}")
    
    # Check bindings on the ref node
    api = UsdShade.MaterialBindingAPI(sample_node)
    print(f"  Material Bindings on {sample_node.GetName()}:")
    if api.GetDirectBinding().GetMaterialPath():
        print(f"    Direct: {api.GetDirectBinding().GetMaterialPath()}")
    else:
        print("    None")
        
    print("\n  Children:")
    for child in sample_node.GetChildren():
        print(f"    {child.GetName()} ({child.GetTypeName()})")
        c_api = UsdShade.MaterialBindingAPI(child)
        if c_api.GetDirectBinding().GetMaterialPath():
            print(f"      Material Binding: {c_api.GetDirectBinding().GetMaterialPath()}")
            
        for grandchild in child.GetChildren():
            print(f"      {grandchild.GetName()} ({grandchild.GetTypeName()})")
            g_api = UsdShade.MaterialBindingAPI(grandchild)
            if g_api.GetDirectBinding().GetMaterialPath():
                print(f"        Material Binding: {g_api.GetDirectBinding().GetMaterialPath()}")

    # Check payload file
    refs = sample_node.GetMetadata("references")
    if refs:
        payload_rel_path = refs.prependedItems[0].assetPath
        payload_abs_path = os.path.join(os.path.dirname(file_path), payload_rel_path)
        print(f"\n--- Inspecting Payload USD: {os.path.basename(payload_abs_path)} ---")
        p_stage = Usd.Stage.Open(payload_abs_path)
        if p_stage:
            for p in p_stage.Traverse():
                p_api = UsdShade.MaterialBindingAPI(p)
                binding = p_api.GetDirectBinding().GetMaterialPath()
                if binding:
                    print(f"  {p.GetPath()} -> Binding: {binding}")
            print("  (If nothing printed above, payload has no bindings)")
        else:
            print("Failed to open payload USD")
