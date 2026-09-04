import os
import sys

PLUGIN = r"C:\ProgramData\Autodesk\ApplicationPlugins\USD for 3ds Max 2027\Contents"
os.add_dll_directory(os.path.join(PLUGIN, "bin"))
os.environ["PATH"] = os.path.join(PLUGIN, "bin") + os.pathsep + os.environ["PATH"]
os.environ["PXR_PLUGINPATH_NAME"] = os.path.join(PLUGIN, "lib", "usd")
sys.path.insert(0, os.path.join(PLUGIN, "bin", "python"))

from pxr import Sdf, Usd, UsdShade

USD_FILE = r"D:/Inventec/DigitalTwin/Collected/Collected_demo_pcba_GTC2026_IMX_Factory_v2/Projects/Factory/IMX/IMX_1F/Building/Floor_1F/max_IMX_Building_1F.usd"

layer = Sdf.Layer.FindOrOpen(USD_FILE)
print("=== LAYER INFO ===")
print("defaultPrim:", layer.defaultPrim)
print("rootPrims:", list(layer.rootPrims.keys()))
print()

bad = []
good = []
rel_count = 0
conn_count = 0


def visit(path):
    global rel_count, conn_count
    spec = layer.GetObjectAtPath(path)
    if isinstance(spec, Sdf.RelationshipSpec):
        rel_count += 1
        for t in spec.targetPathList.explicitItems:
            (bad if str(t).startswith("/root") else good).append((str(path), str(t)))
    elif isinstance(spec, Sdf.AttributeSpec):
        for t in spec.connectionPathList.explicitItems:
            conn_count += 1
            (bad if str(t).startswith("/root") else good).append((str(path), str(t)))


layer.Traverse(Sdf.Path("/"), visit)

print("=== RELATIONSHIP / CONNECTION SCAN ===")
print("relationships:", rel_count, " connections:", conn_count)
print("DANGLING (/root...) targets:", len(bad))
for p, t in bad[:15]:
    print("   ", p, "->", t)
print("OK targets:", len(good))
for p, t in good[:10]:
    print("   ", p, "->", t)
print()

print("=== MATERIAL BINDING CHECK (stage level) ===")
stage = Usd.Stage.Open(USD_FILE)
missing = 0
okc = 0
for prim in stage.Traverse():
    api = UsdShade.MaterialBindingAPI(prim)
    rel = api.GetDirectBindingRel()
    if not rel or not rel.GetTargets():
        continue
    for t in rel.GetTargets():
        if stage.GetPrimAtPath(t).IsValid():
            okc += 1
        else:
            missing += 1
            if missing <= 10:
                print("   BROKEN:", prim.GetPath(), "->", t)
print("valid bindings:", okc, " broken bindings:", missing)
