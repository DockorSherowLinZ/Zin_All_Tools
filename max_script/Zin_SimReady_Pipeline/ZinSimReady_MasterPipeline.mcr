macroScript ZinSimReady_MasterPipeline
category:"ZinAllTools"
tooltip:"SimReady Asset Standardization Pipeline"
icon:#("ZinAllTools", 8)
(
    include "D:\\Inventec\\Zin_All_Tools\\max_script\\Zin_SimReady_Pipeline\\Zin_SimReady_Tags.ms"
    include "D:\\Inventec\\Zin_All_Tools\\max_script\\ResetModel\\Zin_ResetModelCore.ms"
    include "D:\\Inventec\\Zin_All_Tools\\max_script\\GeomOptimizer\\Zin_GeomOptimizerCore.ms"
    include "D:\\Inventec\\Zin_All_Tools\\max_script\\AI_MaterialAssigner\\Zin_AIMaterialAssignerCore.ms"
    include "D:\\Inventec\\Zin_All_Tools\\max_script\\DictMaterialAssigner\\Zin_DictMaterialAssignerCore.ms"
    include "D:\\Inventec\\Zin_All_Tools\\max_script\\Zin_CAD_SelectSimilar\\Zin_CAD_SelectSimilarCore.ms"

    rollout SimReadyMasterUI "Zin SimReady Master Pipeline" width:340 height:800
    (
        groupBox grp_batch "1. Batch Paths (Leave Source empty for Scene Mode)" pos:[10,10] width:320 height:80
        edittext edt_source "Source (STEP):" pos:[20,30] width:240
        button btn_browseSrc "..." pos:[270,28] width:40 height:20
        edittext edt_output "Output (.MAX):" pos:[20,55] width:240
        button btn_browseOut "..." pos:[270,53] width:40 height:20

        groupBox grp_steps "2. Pipeline Steps" pos:[10,100] width:320 height:170
        checkbox chk_step1 "1. Tag All Geometry (SimReady)" checked:true pos:[20,120]
        checkbox chk_step2 "2. Reset Model (Preprocess, Cleanup)" checked:true pos:[20,150]
        checkbox chk_step3 "3. GeomOptimizer (Del Dups, Attach)" checked:true pos:[20,180]
        checkbox chk_step4 "4. Dict Material Assigner (Keyword)" checked:true pos:[20,210]
        checkbox chk_step5 "5. AI Material Assigner (VLM Check)" checked:true pos:[20,240]

        groupBox grp_rm "3. ResetModel & Optimization Options" pos:[10,280] width:320 height:280
        
        checkbox chk_doPreprocess "Preprocess Transform (Rotate/Move)" checked:true pos:[20,300]
        spinner spn_rotX "Rot X:" range:[-360,360,90] type:#float width:80 pos:[30,320]
        spinner spn_rotY "Y:" range:[-360,360,0] type:#float width:70 pos:[120,320]
        spinner spn_rotZ "Z:" range:[-360,360,90] type:#float width:70 pos:[200,320]
        
        spinner spn_posX "Pos X:" range:[-1e9,1e9,0] type:#float width:80 pos:[30,340]
        spinner spn_posY "Y:" range:[-1e9,1e9,0] type:#float width:70 pos:[120,340]
        spinner spn_posZ "Z:" range:[-1e9,1e9,0] type:#float width:70 pos:[200,340]
        
        checkbox chk_detachMat "Auto Detach by Material ID" checked:true pos:[20,370]
        checkbox chk_remDups "Auto Remove Duplicate Meshes" checked:true pos:[20,390]
        checkbox chk_attIdentical "Auto Attach Identical" checked:true pos:[20,410]
        checkbox chk_ignoreHid "Ignore Hidden Models when Attaching" checked:true pos:[40,430]
        checkbox chk_marker "Create Bottom Center Marker" checked:false pos:[20,450]
        checkbox chk_autoFlip "Auto Repair Inverted Normals" checked:true pos:[20,470]
        spinner spn_weldDist "Weld Dist:" range:[0,10,0.001] type:#float scale:0.001 width:110 pos:[210,470]
        
        checkbox chk_addPrefix "Add Prefix to Numeric Group Names" checked:true pos:[20,500]
        edittext edt_prefix "Prefix:" text:"iec_" width:180 pos:[40,520]
        
        groupBox grp_usd "4. USD Export (Optional)" pos:[10,570] width:320 height:80
        checkbox chk_usd "Export to USD after Pipeline" checked:false pos:[20,590]
        edittext edt_usdPath "File/Dir:" pos:[20,610] width:240 text:"C:\\temp\\SimReadyAsset.usd" tooltip:"In Manual mode, specifies file. In Batch mode, specifies base directory."
        button btn_browseUsd "..." pos:[270,608] width:40 height:22
        
        button btn_run "Run SimReady Pipeline" width:300 height:40 pos:[20,670]
        
        progressBar pb_progress "" pos:[20,725] width:300 height:15 value:0
        label lbl_status "Ready." pos:[20,750] width:300
        button btn_log "Open Log File" width:300 height:25 pos:[20,770]
        
        on btn_browseSrc pressed do
        (
            local d = getSavePath caption:"Select Source Folder (STEPs)"
            if d != undefined do edt_source.text = d
        )
        
        on btn_browseOut pressed do
        (
            local d = getSavePath caption:"Select Output Folder (.MAX)"
            if d != undefined do edt_output.text = d
        )
        
        on btn_browseUsd pressed do
        (
            -- If batch mode is implied by source text, select folder, else select file
            if edt_source.text != "" then (
                local d = getSavePath caption:"Select USD Output Folder"
                if d != undefined do edt_usdPath.text = d
            ) else (
                local f = getSaveFileName caption:"Save USD" types:"USD (*.usd)|*.usd|USDA (*.usda)|*.usda|USDC (*.usdc)|*.usdc|All Files (*.*)|*.*|"
                if f != undefined do edt_usdPath.text = f
            )
        )
        
        on btn_log pressed do
        (
            local logP1 = sysInfo.tempdir + "ResetModel_Log.txt"
            local logP2 = if maxFilePath != "" then (maxFilePath + "ResetModel_Log.txt") else ""
            
            if logP2 != "" and doesFileExist logP2 then shellLaunch "notepad.exe" logP2
            else if doesFileExist logP1 then shellLaunch "notepad.exe" logP1
            else messageBox ("Log file not found!\n\nSearched:\n" + logP1 + (if logP2 != "" then ("\n" + logP2) else "")) title:"Info"
        )
        
        fn ExecutePipeline targetNodes currentFileName:"" =
        (
            if targetNodes.count == 0 do return false
            
            pb_progress.value = 0
            
            -- Step 1: Tagging
            if chk_step1.checked do
            (
                lbl_status.text = "Step 1: Tagging Geometry... " + currentFileName
                windows.processPostedMessages()
                for n in targetNodes do try(Zin_AttachSimReadyTag n)catch()
                pb_progress.value = 20
            )
            
            -- Step 2 & 3: ResetModel 
            if chk_step2.checked do
            (
                lbl_status.text = "Step 2: Reset Model & Opt... " + currentFileName
                windows.processPostedMessages()
                local rmOpts = Zin_ResetModelOptions()
                rmOpts.doPreprocess = chk_doPreprocess.checked
                rmOpts.rotX = spn_rotX.value
                rmOpts.rotY = spn_rotY.value
                rmOpts.rotZ = spn_rotZ.value
                rmOpts.posX = spn_posX.value
                rmOpts.posY = spn_posY.value
                rmOpts.posZ = spn_posZ.value
                
                rmOpts.detachByMatID = chk_detachMat.checked
                rmOpts.removeDuplicates = chk_remDups.checked
                rmOpts.attachIdentical = chk_attIdentical.checked
                rmOpts.attachIgnoreHidden = chk_ignoreHid.checked
                rmOpts.createMarker = chk_marker.checked
                rmOpts.autoFlip = chk_autoFlip.checked
                rmOpts.weldDist = spn_weldDist.value
                
                rmOpts.addPrefix = chk_addPrefix.checked
                rmOpts.prefixStr = edt_prefix.text
                
                Zin_RunResetModelBatch targetNodes opts:rmOpts
                pb_progress.value = 40
            )
            
            targetNodes = #()
            for obj in objects do
                if isValidNode obj and superclassof obj == GeometryClass and classof obj != TargetObject do append targetNodes obj
                
            -- Step 3: GeomOptimizer
            if chk_step3.checked do
            (
                lbl_status.text = "Step 3: GeomOptimizer pass... " + currentFileName
                windows.processPostedMessages()
                local goOpts = Zin_GeomOptimizerOptions()
                goOpts.doStep1 = chk_remDups.checked
                goOpts.doStep2 = chk_attIdentical.checked
                Zin_RunGeomOptimizerBatch targetNodes opts:goOpts
                pb_progress.value = 60
            )
            
            targetNodes = #()
            for obj in objects do
                if isValidNode obj and superclassof obj == GeometryClass and classof obj != TargetObject do append targetNodes obj
            
            -- Step 4: DictMaterialAssigner
            if chk_step4.checked do
            (
                lbl_status.text = "Step 4: Dict Material Assigner... " + currentFileName
                windows.processPostedMessages()
                local dmOpts = Zin_DictOptions()
                dmOpts.skipAssigned = false
                try(Zin_RunDictMaterialAssignerBatch targetNodes opts:dmOpts)catch()
                pb_progress.value = 80
            )
            
            -- Step 5: AI Material Assigner
            if chk_step5.checked do
            (
                lbl_status.text = "Step 5: AI Material Assigner... " + currentFileName
                windows.processPostedMessages()
                local aiOpts = Zin_AIOptions()
                try(Zin_RunAIMaterialAssignerBatch targetNodes opts:aiOpts)catch()
                pb_progress.value = 95
            )
            
            -- USD Export
            if chk_usd.checked do
            (
                lbl_status.text = "Exporting to USD... " + currentFileName
                windows.processPostedMessages()
                
                local usdPath = edt_usdPath.text
                if currentFileName != "" then
                (
                    -- Batch mode: usdPath is treated as a directory
                    local usdDir = usdPath
                    if not doesFileExist usdDir do makeDir usdDir all:true
                    usdPath = usdDir + "\\" + currentFileName + ".usd"
                )
                
                if usdPath != "" do
                (
                    -- Ensure output directory exists
                    local parentDir = getFilenamePath usdPath
                    if parentDir != "" and not doesFileExist parentDir do makeDir parentDir all:true
                    
                    local exportOK = false
                    
                    -- Attempt 1: Let 3ds Max auto-detect exporter from .usd extension
                    if not exportOK do
                    (
                        try (
                            exportFile usdPath #noPrompt
                            if doesFileExist usdPath do exportOK = true
                        ) catch ()
                    )
                    
                    -- Attempt 2: Try USDExporter class (3ds Max 2024+)
                    if not exportOK do
                    (
                        try (
                            exportFile usdPath #noPrompt using:USDExporter
                            if doesFileExist usdPath do exportOK = true
                        ) catch ()
                    )
                    
                    -- Attempt 3: Try USD_Exporter class (older plugin versions)
                    if not exportOK do
                    (
                        try (
                            exportFile usdPath #noPrompt using:USD_Exporter
                            if doesFileExist usdPath do exportOK = true
                        ) catch ()
                    )
                    
                    if exportOK then
                    (
                        -- Post-process: Rename /root to /World as defaultPrim
                        lbl_status.text = "USD post-process: Setting defaultPrim=World..."
                        windows.processPostedMessages()
                        
                        local pyPath = substituteString usdPath "\\" "/"
                        local tmpPy = sysInfo.tempdir + "fix_usd_root.py"
                        local pf = createFile tmpPy
                        format "from pxr import Sdf\n" to:pf
                        format "layer = Sdf.Layer.FindOrOpen('%')\n" pyPath to:pf
                        format "if layer and layer.defaultPrim:\n" to:pf
                        format "    old_root = layer.defaultPrim\n" to:pf
                        format "    if old_root != 'World':\n" to:pf
                        format "        edit = Sdf.BatchNamespaceEdit()\n" to:pf
                        format "        edit.Add(Sdf.Path('/' + old_root), Sdf.Path('/World'))\n" to:pf
                        format "        if layer.Apply(edit):\n" to:pf
                        format "            layer.defaultPrim = 'World'\n" to:pf
                        format "            layer.Save()\n" to:pf
                        format "            print('USD defaultPrim set to World from', old_root)\n" to:pf
                        format "        else:\n" to:pf
                        format "            print('USD rename failed')\n" to:pf
                        close pf
                        
                        try ( python.ExecuteFile tmpPy ) catch (
                            messageBox "USD post-process warning:\nCould not rename root to World.\nThe USD file was exported but defaultPrim remains as 'root'." title:"USD Post-Process"
                        )
                        
                        lbl_status.text = "USD exported: " + (getFilenameFile usdPath)
                    )
                    else
                        messageBox ("USD Export failed!\n\nPath: " + usdPath + "\n\nPossible causes:\n1. USD for 3ds Max plugin is not installed\n2. Output path contains special characters\n\nTry changing the output path to a simple path like:\nD:\\output\\model.usd") title:"USD Export Error"
                )
            )
            
            pb_progress.value = 100
            return true
        )
        
        on btn_run pressed do
        (
            local srcDir = edt_source.text
            local outDir = edt_output.text
            local isBatch = (srcDir != "" and doesFileExist srcDir)
            
            if isBatch then
            (
                -- BATCH MODE
                if outDir == "" or not (doesFileExist outDir) do
                (
                    messageBox "Please specify a valid Output directory for batch mode!" title:"Error"
                    return ()
                )
                
                local stpFiles = getFiles (srcDir + "\\*.stp")
                join stpFiles (getFiles (srcDir + "\\*.step"))
                
                if stpFiles.count == 0 do
                (
                    messageBox "No STEP files found in the source directory!" title:"Error"
                    return ()
                )
                
                for i = 1 to stpFiles.count do
                (
                    local f = stpFiles[i]
                    local baseName = getFilenameFile f
                    
                    lbl_status.text = "Importing: " + baseName
                    windows.processPostedMessages()
                    
                    resetMaxFile #noPrompt
                    importFile f #noPrompt
                    
                    local targetNodes = #()
                    for obj in objects do
                        if isValidNode obj and superclassof obj == GeometryClass and classof obj != TargetObject do append targetNodes obj
                        
                    if targetNodes.count > 0 do
                    (
                        ExecutePipeline targetNodes currentFileName:baseName
                        
                        -- Save Max File
                        local maxPath = outDir + "\\" + baseName + ".max"
                        lbl_status.text = "Saving MAX: " + baseName
                        windows.processPostedMessages()
                        saveMaxFile maxPath quiet:true
                    )
                )
                lbl_status.text = "Batch Pipeline Complete!"
                messageBox "Batch Pipeline execution completed!" title:"Success"
            )
            else
            (
                -- MANUAL MODE (Current Scene)
                local targetNodes = #()
                for obj in objects do
                    if isValidNode obj and superclassof obj == GeometryClass and classof obj != TargetObject do append targetNodes obj
                    
                if targetNodes.count == 0 do
                (
                    messageBox "No geometry found in scene!" title:"Error"
                    return ()
                )
                
                ExecutePipeline targetNodes
                lbl_status.text = "Pipeline Complete!"
                messageBox "SimReady Pipeline execution completed!" title:"Success"
            )
        )
    )
    
    on execute do
    (
        createDialog SimReadyMasterUI style:#(#style_toolwindow, #style_sysmenu, #style_titlebar)
    )
)
