from pxr import Usd, Sdf
stage = Usd.Stage.CreateInMemory()
p = stage.DefinePrim("/World/A", "Xform")
stage.DefinePrim("/World/A/B", "Sphere")
print("Before:", stage.GetRootLayer().ExportToString())

Sdf.CopySpec(stage.GetRootLayer(), "/World/A", stage.GetRootLayer(), "/World/Payload")
stage.RemovePrim("/World/A")

print("After:", stage.GetRootLayer().ExportToString())
