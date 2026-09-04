macroScript Zin_USD_Export
category:"ZinAllTools"
buttonText:"Zin USD Export"
tooltip:"USD Export"
icon:#("ZinAllTools", 9)
(
    rollout Zin_USDExport_UI "Zin USD Export" width:300 height:120
    (
        label lbl_info "Export scene to USD and set defaultPrim to '/World'" pos:[10,10]
        
        edittext edt_usdPath "Path:" pos:[10,35] width:240 text:"C:\\temp\\output.usd"
        button btn_browse "..." pos:[255,33] width:30 height:20
        
        button btn_export "Export to USD" width:275 height:35 pos:[10,70]
        
        on btn_browse pressed do
        (
            local f = getSaveFileName caption:"Save USD" types:"USD (*.usd)|*.usd|USDA (*.usda)|*.usda|USDC (*.usdc)|*.usdc|All Files (*.*)|*.*|"
            if f != undefined do edt_usdPath.text = f
        )
        
        on btn_export pressed do
        (
            local usdPath = edt_usdPath.text
            if usdPath == "" do
            (
                messageBox "Please enter a valid path." title:"Warning"
                return ()
            )
            
            -- Ensure output directory exists
            local parentDir = getFilenamePath usdPath
            if parentDir != "" and not doesFileExist parentDir do makeDir parentDir all:true
            
            local exportOK = false
            
            -- Attempt 1: Let 3ds Max auto-detect exporter from .usd extension
            if not exportOK do try ( exportFile usdPath #noPrompt; if doesFileExist usdPath do exportOK = true ) catch ()
            
            -- Attempt 2: Try USDExporter class (3ds Max 2024+)
            if not exportOK do try ( exportFile usdPath #noPrompt using:USDExporter; if doesFileExist usdPath do exportOK = true ) catch ()
            
            -- Attempt 3: Try USD_Exporter class (older plugin versions)
            if not exportOK do try ( exportFile usdPath #noPrompt using:USD_Exporter; if doesFileExist usdPath do exportOK = true ) catch ()
            
            if exportOK then
            (
                local pyPath = substituteString usdPath "\\" "/"
                local tmpPy = sysInfo.tempdir + "fix_usd_root.py"
                local pf = createFile tmpPy
                format "from pxr import Sdf\n" to:pf
                format "def fix_paths(layer, old_name, new_name):\n" to:pf
                format "    old_p = '/' + old_name\n" to:pf
                format "    new_p = '/' + new_name\n" to:pf
                format "    def _traverse(prim):\n" to:pf
                format "        for prop in prim.properties:\n" to:pf
                format "            lst = None\n" to:pf
                format "            if isinstance(prop, Sdf.RelationshipSpec): lst = prop.targetPathList\n" to:pf
                format "            elif isinstance(prop, Sdf.AttributeSpec): lst = prop.connectionPathList\n" to:pf
                format "            if lst is not None:\n" to:pf
                format "                if lst.explicitItems: lst.explicitItems = [Sdf.Path(str(p).replace(old_p, new_p, 1)) if str(p) == old_p or str(p).startswith(old_p + '/') else p for p in lst.explicitItems]\n" to:pf
                format "                if lst.addedItems: lst.addedItems = [Sdf.Path(str(p).replace(old_p, new_p, 1)) if str(p) == old_p or str(p).startswith(old_p + '/') else p for p in lst.addedItems]\n" to:pf
                format "                if lst.prependedItems: lst.prependedItems = [Sdf.Path(str(p).replace(old_p, new_p, 1)) if str(p) == old_p or str(p).startswith(old_p + '/') else p for p in lst.prependedItems]\n" to:pf
                format "                if lst.appendedItems: lst.appendedItems = [Sdf.Path(str(p).replace(old_p, new_p, 1)) if str(p) == old_p or str(p).startswith(old_p + '/') else p for p in lst.appendedItems]\n" to:pf
                format "        for child in prim.nameChildren:\n" to:pf
                format "            _traverse(child)\n" to:pf
                format "    _traverse(layer.pseudoRoot)\n" to:pf
                format "layer = Sdf.Layer.FindOrOpen('%')\n" pyPath to:pf
                format "if layer and layer.defaultPrim:\n" to:pf
                format "    old_root = layer.defaultPrim\n" to:pf
                format "    if old_root != 'World':\n" to:pf
                format "        edit = Sdf.BatchNamespaceEdit()\n" to:pf
                format "        edit.Add(Sdf.Path('/' + old_root), Sdf.Path('/World'))\n" to:pf
                format "        if layer.Apply(edit):\n" to:pf
                format "            layer.defaultPrim = 'World'\n" to:pf
                format "            fix_paths(layer, old_root, 'World')\n" to:pf
                format "            layer.Save()\n" to:pf
                close pf
                
                try ( python.ExecuteFile tmpPy ) catch (
                    messageBox "USD exported, but could not rename root to World.\nThe USD file was exported but defaultPrim remains as 'root'." title:"USD Post-Process Warning"
                )
                
                messageBox ("USD Exported successfully to:\n\n" + usdPath) title:"Success"
                destroyDialog Zin_USDExport_UI
            )
            else
            (
                messageBox ("USD Export failed!\n\nPath: " + usdPath + "\n\nPossible causes:\n1. USD for 3ds Max plugin is not installed\n2. Output path contains special characters\n\nTry changing the output path to a simple path like:\nD:\\output\\model.usd") title:"USD Export Error"
            )
        )
    )
    
    on execute do
    (
        createDialog Zin_USDExport_UI
    )
)