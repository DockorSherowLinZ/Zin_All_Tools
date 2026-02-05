/*
[Zin All Tools - Asset Pipeline]
Script: Batch GLB Exporter
Version: 1.2.0
Last Updated: 2026.02.03
Description: Batch export .max files to .glb with recursive support and memory management.
*/

macroScript BatchGLBExporter
category:"ZinAllTools"
toolTip:"Batch Export MAX files to GLB v1.2.0"
buttonText:"Batch GLB v1.2"
(
    global batchGLBExport_Rollout
    try(destroyDialog batchGLBExport_Rollout) catch()

    -- Function: Recursive File Search
    fn getFilesRecursive root pattern = (
        local my_files = getFiles (root + pattern)
        local dirs = getDirectories (root + "*")
        for d in dirs do join my_files (getFilesRecursive d pattern)
        my_files
    )

    rollout batchGLBExport_Rollout "ZinAllTools - Batch GLB Exporter v1.2.0" width:400 height:440
    (
        group "Path Settings" (
            edittext edtSource "Source Dir:" width:300 align:#left
            button btnBrowseSource "Browse" align:#right offset:[0,-25]
            checkbox chkRecurse "Search Sub-folders (Recursive)" checked:true
            
            edittext edtDest "Export Dir:" width:300 align:#left
            button btnBrowseDest "Browse" align:#right offset:[0,-25]
        )
        
        group "File Naming" (
            edittext edtPrefix "Filename Prefix:" text:"Model_"
        )
        
        group "Export Configuration" (
            label lblNote "Note: v1.2 includes Auto-Tangents & RAM Clear." align:#left
            checkbox chkEmbed "Embed Media (Textures)" checked:true
            checkbox chkFlipY "Flip Y-Z Axis" checked:true
        )
        
        button btnRun "RUN BATCH EXPORT" width:350 height:45 style:#sysfixed
        progressbar pbar "Progress" width:350 height:20 color:green
        label lblStatus "Ready" align:#center
        
        on btnBrowseSource pressed do (
            local dir = getSavePath caption:"Select Source Folder"
            if dir != undefined do edtSource.text = dir + "\\"
        )
        
        on btnBrowseDest pressed do (
            local dir = getSavePath caption:"Select Output Folder"
            if dir != undefined do edtDest.text = dir + "\\"
        )
        
        on btnRun pressed do (
            if (edtSource.text == "" or edtDest.text == "") then (
                messageBox "Please select both Source and Export directories." title:"Warning"
            ) else (
                local sourceFiles = if chkRecurse.checked then 
                    (getFilesRecursive edtSource.text "*.max")
                else 
                    (getFiles (edtSource.text + "*.max"))
                
                if sourceFiles.count == 0 then (
                    messageBox "No .max files found!" title:"Error"
                ) else (
                    for i = 1 to sourceFiles.count do (
                        local f = sourceFiles[i]
                        pbar.value = (i as float / sourceFiles.count) * 100
                        lblStatus.text = ("Processing: " + (getFilenameFile f))
                        
                        -- Load File (Quiet mode)
                        loadMaxFile f useFileUnits:true quiet:true
                        
                        -- Export logic
                        local originalName = getFilenameFile f
                        local exportName = edtDest.text + edtPrefix.text + originalName + ".glb"
                        
                        if (IglTFExport != undefined) do (
                            IglTFExport.exportTangents = true
                        )
                        
                        exportFile exportName #noPrompt selectedOnly:false using:gltf_Export
                        
                        -- Stability Protection
                        freeSceneBitmaps() 
                        gc light:true      
                    )
                    pbar.value = 100
                    lblStatus.text = "Finished"
                    shellLaunch "explorer.exe" edtDest.text 
                    messageBox ("v1.2: Exported " + sourceFiles.count as string + " files successfully!") title:"Done"
                )
            )
        )
    )

    on execute do (
        createDialog batchGLBExport_Rollout
    )
)