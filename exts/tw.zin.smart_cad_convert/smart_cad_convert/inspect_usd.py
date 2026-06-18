from pxr import Usd, UsdGeom
import sys

file_path = "D:/Inventec/Asset/Product/Server/P9000IG7/PoC/CARDS_STEP/Collected_max_1395a3705801_asm/max_1395a3705801_asm.usd"
stage = Usd.Stage.Open(file_path)

if not stage:
    print("Failed to open stage")
    sys.exit(1)

print("--- Root Prims ---")
for p in stage.GetPseudoRoot().GetChildren():
    print(f"  - {p.GetName()}")

print("\n--- Payloads & Physics info (first 20 matches) ---")
count = 0
for p in stage.Traverse():
    has_payload = p.HasAuthoredPayloads()
    physics_apis = [api for api in p.GetAppliedSchemas() if "Physics" in api]
    kind = Usd.ModelAPI(p).GetKind()
    
    if has_payload or physics_apis:
        print(f"Path: {p.GetPath()}")
        print(f"  Payload: {has_payload}")
        print(f"  Physics APIs: {physics_apis}")
        print(f"  Kind: {kind}")
        count += 1
        if count >= 20:
            break
            
print("\n--- Summary ---")
print(f"Total payload prims: {sum(1 for p in stage.Traverse() if p.HasAuthoredPayloads())}")
