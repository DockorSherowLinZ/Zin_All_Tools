from pxr import Usd, UsdShade
import sys

def check_materials(file_path):
    print(f"\n--- Checking {file_path} ---")
    stage = Usd.Stage.Open(file_path)
    if not stage:
        print("Failed to open")
        return
        
    looks = [p.GetPath() for p in stage.Traverse() if "Looks" in p.GetName() or "Material" in p.GetTypeName()]
    print(f"Material Prims: {len(looks)}")
    for l in looks[:5]:
        print(f"  - {l}")
        
    bindings = 0
    for p in stage.Traverse():
        if p.HasAPI(UsdShade.MaterialBindingAPI):
            bindings += 1
    print(f"Total material bindings: {bindings}")

check_materials("D:/Inventec/Asset/Product/Server/P9000IG7/PoC/CARDS_STEP/max_1395a3705801_asm_Pre_iec_ov.usd")
check_materials("D:/Inventec/Asset/Product/Server/P9000IG7/PoC/CARDS_STEP/max_1395a3705801_asm_Pre_iec.usd")
