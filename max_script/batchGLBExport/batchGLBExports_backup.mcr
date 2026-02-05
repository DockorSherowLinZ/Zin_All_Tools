macroScript BatchGLBExporter
category:"ZinAllTools"
toolTip:"Batch Export MAX files to GLB"
buttonText:"Batch GLB"
(
    global batchGLBExport_Rollout
    try(destroyDialog batchGLBExport_Rollout) catch()

    rollout batchGLBExport_Rollout "ZinAllTools - Batch GLB Exporter" width:400 height:360
    (
        -- Path Settings
        group "Path Settings" (
            edittext edtSource "Source Dir:" width:300 align:#left displaytext:true
            button btnBrowseSource "Browse" align:#right offset:[0,-25]
            
            edittext edtDest "Export Dir:" width:300 align:#left displaytext:true
            button btnBrowseDest "Browse" align:#right offset:[0,-25]
        )
        
        -- Naming Logic
        group "File Naming" (
            edittext edtPrefix "Filename Prefix:" text:"Model_"
        )
        
        -- Export Configuration
        group "Material & Export Settings" (
            label lblNote "Note: Uses built-in glTF Exporter plugin." align:#left
            checkbox chkEmbed "Embed Media (Textures)" checked:true
            checkbox chkFlipY "Flip Y-Z Axis" checked:true
        )
        
        button btnRun "RUN BATCH EXPORT" width:350 height:45 style:#sysfixed
        progressbar pbar "Progress" width:350 height:20 color:green
        
        -- Event: Browse Source
        on btnBrowseSource pressed do (
            local dir = getSavePath caption:"Select Source .max Folder"
            if dir != undefined do edtSource.text = dir + "\\"
        )
        
        -- Event: Browse Destination
        on btnBrowseDest pressed do (
            local dir = getSavePath caption:"Select Output Folder"
            if dir != undefined do edtDest.text = dir + "\\"
        )
        
        -- Execution Logic
        on btnRun pressed do (
            if (edtSource.text == "" or edtDest.text == "") then (
                messageBox "Please select both Source and Export directories." title:"Warning"
            ) else (
                local sourceFiles = getFiles (edtSource.text + "*.max")
                
                if sourceFiles.count == 0 then (
                    messageBox "No .max files found in the source directory!" title:"Error"
                ) else (
                    for i = 1 to sourceFiles.count do (
                        local f = sourceFiles[i]
                        
                        -- Update Progress
                        pbar.value = (i as float / sourceFiles.count) * 100
                        
                        -- Load Max File (Quiet mode)
                        loadMaxFile f useFileUnits:true quiet:true
                        
                        -- Construct Output Path
                        local originalName = getFilenameFile f
                        local exportName = edtDest.text + edtPrefix.text + originalName + ".glb"
                        
                        -- Execute Export
                        exportFile exportName #noPrompt selectedOnly:false using:gltf_Export
                    )
                    pbar.value = 100
                    messageBox "Batch Export Completed Successfully!" title:"Done"
                )
            )
        )
    )

    on execute do (
        createDialog batchGLBExport_Rollout
    )
)