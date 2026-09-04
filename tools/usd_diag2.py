import os
import sys

PLUGIN = r"C:\ProgramData\Autodesk\ApplicationPlugins\USD for 3ds Max 2027\Contents"
os.add_dll_directory(os.path.join(PLUGIN, "bin"))
os.environ["PATH"] = os.path.join(PLUGIN, "bin") + os.pathsep + os.environ["PATH"]
os.environ["PXR_PLUGINPATH_NAME"] = os.path.join(PLUGIN, "lib", "usd")
sys.path.insert(0, os.path.join(PLUGIN, "bin", "python"))

from pxr import Sdf, Usd, UsdShade

USD_FILE = sys.argv[1]

layer = Sdf.Layer.FindOrOpen(USD_FILE)
print("=== LAYER INFO ===", USD_FILE)
print("defaultPrim:", layer.defaultPrim)
print("rootPrims:", list(layer.rootPrims.keys()))
print()

bad = []
good = []


def check(path, listop, kind):
    for attr in ("explicitItems", "addedItems", "prependedItems", "appendedItems", "deletedItems", "orderedItems"):
        for t in getattr(listop, attr, []):
            entry = (str(path), attr, str(t))
            (bad if not str(t).startswith("/World") else good).append(entry)


def visit(path):
    spec = layer.GetObjectAtPath(path)
    if isinstance(spec, Sdf.RelationshipSpec):
        check(path, spec.targetPathList, "rel")
    elif isinstance(spec, Sdf.AttributeSpec):
        check(path, spec.connectionPathList, "conn")


layer.Traverse(Sdf.Path("/"), visit)

print("=== TARGETS NOT UNDER /World ===", len(bad))
for p, a, t in bad[:25]:
    print("   ", p, f"[{a}]", "->", t)
print()
print("=== TARGETS UNDER /World ===", len(good))
for p, a, t in good[:15]:
    print("   ", p, f"[{a}]", "->", t)
print()

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
            if missing <= 15:
                print("   BROKEN BINDING:", prim.GetPath(), "->", t)
print("valid bindings:", okc, " broken bindings:", missing)
