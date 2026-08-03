macroScript AI_MaterialAssigner
category:"ZinAllTools"
tooltip:"AI Material Assigner v1.0: VLM-Powered Automatic Material Classification"
(
    rollout AI_MatUI "AI Material Assigner v1.0" width:450 height:560
    (
        -- ========== UI Elements ==========
        groupBox grp_config "Gemini API Configuration" pos:[10,8] width:430 height:88
        label lbl_apiKey "API Key:" pos:[20,28]
        edittext edt_apiKey "" pos:[75,26] width:290
        button btn_saveKey "Save" pos:[375,24] width:55 height:22

        label lbl_model "Model:" pos:[20,54]
        dropdownList ddl_model "" items:#("gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-lite") \
            pos:[75,52] width:180 height:20
        label lbl_delay "Delay(s):" pos:[270,54]
        spinner spn_delay "" range:[0,30,4] type:#integer pos:[330,54] width:60

        label lbl_catCount "" pos:[20,78] width:200

        groupBox grp_options "Options" pos:[10,100] width:430 height:50
        checkbox chk_rename "Auto Rename Meshes" checked:true pos:[20,118]
        checkbox chk_material "Auto Assign Materials" checked:true pos:[200,118]
        spinner spn_confidence "Min Confidence %:" range:[0,100,60] type:#integer pos:[20,138] width:160

        button btn_analyze "Step 1: Analyze Scene  (Fingerprint Scan)" width:430 height:36 pos:[10,158]
        label lbl_stats "" pos:[10,198] width:430 height:30

        button btn_classify "Step 2: Run AI Classification" width:430 height:44 pos:[10,230] enabled:false
        
        progressBar pb_progress "" pos:[10,282] width:430 height:18 value:0
        label lbl_status "Ready." pos:[10,305] width:430

        edittext edt_log "" pos:[10,325] width:430 height:170 readOnly:true

        button btn_openLog "Open Log File" width:210 height:26 pos:[10,500]
        button btn_editConfig "Edit config.ini" width:210 height:26 pos:[230,500]
        label lbl_footer "ZinAllTools | AI Material Assigner v1.0" pos:[10,535] width:430

        -- ========== Internal State ==========
        local scriptDir = ""
        local configPath = ""
        local tempDir = ""
        local logFilePath = ""
        local pythonPath = "python"

        local uniqueKeys = #()
        local uniqueGroups = #()
        local categoriesList = #()
        local analysisComplete = false

        -- ========== Utility Functions ==========

        fn pad0 num =
        (
            if num < 10 then "0" + (num as string) else (num as string)
        )

        fn rnd val = (floor (val * 10000.0 + 0.5)) / 10000.0

        fn writeLog msg =
        (
            if logFilePath == "" do return ()

            local f = openFile logFilePath mode:"a"
            if f == undefined do f = createFile logFilePath
            if f != undefined do
            (
                local t = getLocalTime()
                local timeStr = "[" + (pad0 t[5]) + ":" + (pad0 t[6]) + ":" + (pad0 t[7]) + "]"
                format "% %\n" timeStr msg to:f
                close f
            )
        )

        fn appendLog msg =
        (
            -- Append to the UI log textbox (keep last ~2000 chars)
            local current = edt_log.text
            if current.count > 2000 do
                current = (substring current (current.count - 1500) 1500)
            edt_log.text = current + msg + "\n"
        )

        fn logBoth msg =
        (
            writeLog msg
            appendLog msg
        )

        fn updateStatus msg =
        (
            try (lbl_status.text = msg) catch ()
            try (windows.processPostedMessages()) catch ()
        )

        -- ========== Config I/O ==========

        fn loadConfig =
        (
            if not doesFileExist configPath do
            (
                logBoth ("WARNING: config.ini not found at: " + configPath)
                return false
            )

            local key = getINISetting configPath "General" "api_key"
            if key != "" do edt_apiKey.text = key

            local model = getINISetting configPath "General" "model"
            if model != "" do
            (
                local idx = findItem ddl_model.items model
                if idx > 0 do ddl_model.selection = idx
            )

            local pyPath = getINISetting configPath "General" "python_path"
            if pyPath != "" do pythonPath = pyPath

            local confThreshold = getINISetting configPath "General" "confidence_threshold"
            if confThreshold != "" do
                try (spn_confidence.value = confThreshold as integer) catch ()

            local delaySec = getINISetting configPath "General" "request_delay_sec"
            if delaySec != "" do
                try (spn_delay.value = delaySec as integer) catch ()

            local catStr = getINISetting configPath "Categories" "list"
            if catStr != "" do
            (
                categoriesList = filterString catStr ","
                lbl_catCount.text = "Categories loaded: " + (categoriesList.count as string) + " types"
            )

            local autoRename = getINISetting configPath "Options" "auto_rename"
            if autoRename == "0" do chk_rename.checked = false

            local autoMat = getINISetting configPath "Options" "auto_assign_material"
            if autoMat == "0" do chk_material.checked = false

            logBoth ("Config loaded from: " + configPath)
            return true
        )

        fn saveConfig =
        (
            setINISetting configPath "General" "api_key" edt_apiKey.text
            setINISetting configPath "General" "model" ddl_model.items[ddl_model.selection]
            setINISetting configPath "General" "confidence_threshold" (spn_confidence.value as string)
            setINISetting configPath "General" "request_delay_sec" (spn_delay.value as string)
            setINISetting configPath "Options" "auto_rename" (if chk_rename.checked then "1" else "0")
            setINISetting configPath "Options" "auto_assign_material" (if chk_material.checked then "1" else "0")
            logBoth "Config saved."
        )

        -- ========== Phase 1: Geometry Fingerprinting ==========

        -- Position & rotation independent fingerprint
        -- Uses sorted BBox dimensions + face count + vertex count
        fn getShapeFingerprint node =
        (
            local bboxSize = node.max - node.min
            local w = rnd (abs bboxSize.x)
            local h = rnd (abs bboxSize.y)
            local d = rnd (abs bboxSize.z)
            -- Sort dimensions so rotated objects produce same fingerprint
            local dims = sort #(w, h, d)
            local nf = node.mesh.numfaces as string
            local nv = node.mesh.numverts as string
            local fp = (dims[1] as string) + "|" + (dims[2] as string) + "|" + (dims[3] as string) + "|" + nf + "|" + nv
            return fp
        )

        fn collectAllGeometries &geoArr =
        (
            for obj in objects do
            (
                if isValidNode obj and superclassof obj == GeometryClass and classof obj != TargetObject do
                (
                    local hasFaces = false
                    try (if obj.mesh.numfaces > 0 do hasFaces = true) catch ()
                    if hasFaces do append geoArr obj
                )
            )
        )

        fn groupByFingerprint geoArr &keys &groups =
        (
            keys = #()
            groups = #()

            for n in geoArr do
            (
                local fp = getShapeFingerprint n
                local idx = findItem keys fp
                if idx == 0 then
                (
                    append keys fp
                    append groups #(n)
                )
                else
                (
                    append groups[idx] n
                )
            )
        )

        -- ========== Phase 2: Viewport Capture ==========

        fn captureViewportResized targetSize =
        (
            local srcBmp = gw.getViewportDib()
            if srcBmp == undefined do return undefined

            local dstBmp = bitmap targetSize targetSize color:black
            local srcBox = box2 0 0 srcBmp.width srcBmp.height
            local dstBox = box2 0 0 targetSize targetSize
            pasteBitmap srcBmp dstBmp srcBox dstBox
            close srcBmp
            return dstBmp
        )

        fn captureUniqueShapes captureSize =
        (
            -- Open all groups first
            for obj in objects do
                if isGroupHead obj do setGroupOpen obj true

            -- Store original hidden states
            local allObjs = for obj in objects collect obj
            local origHidden = for obj in allObjs collect obj.isHidden

            -- Hide everything
            for obj in allObjs do
                try (obj.isHidden = true) catch ()

            -- Set viewport to perspective
            viewport.setType #view_persp_user

            local capturedPaths = #()

            for i = 1 to uniqueKeys.count do
            (
                local representative = uniqueGroups[i][1]

                if not isValidNode representative do
                (
                    append capturedPaths ""
                    continue
                )

                -- Unhide representative and all its parents
                try (representative.isHidden = false) catch ()
                local p = representative.parent
                while p != undefined do
                (
                    try (p.isHidden = false) catch ()
                    if isGroupHead p do setGroupOpen p true
                    p = p.parent
                )

                -- Frame and capture
                select representative
                max zoomext sel all
                completeRedraw()

                local bmp = captureViewportResized captureSize
                if bmp != undefined then
                (
                    local imgPath = tempDir + "shape_" + (formattedPrint i format:"04d") + ".jpg"
                    bmp.filename = imgPath
                    save bmp
                    close bmp
                    append capturedPaths imgPath
                    logBoth ("  Captured: shape_" + (formattedPrint i format:"04d") + ".jpg <- " + representative.name)
                )
                else
                (
                    append capturedPaths ""
                    logBoth ("  WARNING: Failed to capture shape " + i as string)
                )

                -- Re-hide representative
                try (representative.isHidden = true) catch ()
                p = representative.parent
                while p != undefined do
                (
                    try (p.isHidden = true) catch ()
                    p = p.parent
                )

                -- Update progress
                try (pb_progress.value = ((i as float) / uniqueKeys.count) * 50.0) catch ()
                updateStatus ("Capturing " + i as string + "/" + uniqueKeys.count as string + ": " + representative.name)
            )

            -- Restore original hidden states
            for i = 1 to allObjs.count do
            (
                if isValidNode allObjs[i] do
                    try (allObjs[i].isHidden = origHidden[i]) catch ()
            )

            completeRedraw()
            return capturedPaths
        )

        -- ========== Phase 3: VLM Classification ==========

        fn writeRequestFile capturedPaths =
        (
            local reqPath = tempDir + "request.txt"
            local f = createFile reqPath
            if f == undefined do
            (
                logBoth "ERROR: Could not create request file!"
                return ""
            )

            format "API_KEY|%\n" edt_apiKey.text to:f
            format "MODEL|%\n" ddl_model.items[ddl_model.selection] to:f

            local catStr = ""
            for i = 1 to categoriesList.count do
            (
                catStr += categoriesList[i]
                if i < categoriesList.count do catStr += ","
            )
            format "CATEGORIES|%\n" catStr to:f
            format "DELAY|%\n" (spn_delay.value as string) to:f

            for i = 1 to capturedPaths.count do
            (
                if capturedPaths[i] != "" do
                    format "SHAPE|%|%\n" uniqueKeys[i] capturedPaths[i] to:f
            )

            close f
            return reqPath
        )

        fn runPythonClassifier reqPath =
        (
            local resPath = tempDir + "result.txt"
            local pyScript = scriptDir + "ai_vlm_classify.py"

            local args = "\"" + pyScript + "\" \"" + reqPath + "\" \"" + resPath + "\""

            logBoth ("Launching Python classifier...")
            logBoth ("  Python: " + pythonPath)
            logBoth ("  Script: " + pyScript)

            -- Run Python as hidden .NET Process (no console flash)
            local psi = dotNetObject "System.Diagnostics.ProcessStartInfo"
            psi.FileName = pythonPath
            psi.Arguments = args
            psi.UseShellExecute = false
            psi.CreateNoWindow = true
            psi.RedirectStandardOutput = true
            psi.RedirectStandardError = true

            local proc = (dotNetClass "System.Diagnostics.Process").Start psi

            updateStatus "Waiting for AI classification (this may take several minutes)..."
            windows.processPostedMessages()

            proc.WaitForExit()

            local exitCode = proc.ExitCode
            local stdout = proc.StandardOutput.ReadToEnd()
            local stderr = proc.StandardError.ReadToEnd()
            proc.Close()

            if stdout != "" do logBoth ("Python stdout:\n" + stdout)
            if stderr != "" do logBoth ("Python stderr:\n" + stderr)

            if exitCode != 0 do
            (
                logBoth ("ERROR: Python process exited with code " + exitCode as string)
                return ""
            )

            if not doesFileExist resPath do
            (
                logBoth "ERROR: Result file was not created by Python."
                return ""
            )

            return resPath
        )

        fn readResultFile resPath =
        (
            local results = #()  -- #(#(fpKey, label, confidence), ...)
            local f = openFile resPath
            if f == undefined do return results

            while not eof f do
            (
                local line = readLine f
                if line.count > 0 and line[1] != "#" do
                (
                    local parts = filterString line "|"
                    if parts.count >= 3 do
                    (
                        local conf = 0
                        try (conf = parts[3] as integer) catch ()
                        append results #(parts[1], parts[2], conf)
                    )
                )
            )
            close f
            return results
        )

        -- ========== Phase 4: Material Assignment ==========

        -- Material preset database: returns #(baseColor, metalness, roughness, transparency, emission, emitColor)
        fn getMaterialPreset label =
        (
            case label of
            (
                "ScanGreenLight":      #(color   0 255   0, 0.0, 0.30, 0.0, 1.0, color   0 255   0)
                "BlackPlastic":        #(color  30  30  30, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
                "GreenPlastic":        #(color  30 150  50, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
                "RedPlastic":          #(color 200  30  30, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
                "WhitePlastic":        #(color 240 240 240, 0.0, 0.40, 0.0, 0.0, color   0   0   0)
                "BluePlastic":         #(color  30  60 200, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
                "LockerMetal":         #(color 160 160 165, 1.0, 0.35, 0.0, 0.0, color   0   0   0)
                "RedClearPlastic":     #(color 200  30  30, 0.0, 0.15, 0.7, 0.0, color   0   0   0)
                "RedLight":            #(color 255   0   0, 0.0, 0.30, 0.0, 1.0, color 255   0   0)
                "OrangeLight":         #(color 255 140   0, 0.0, 0.30, 0.0, 1.0, color 255 140   0)
                "OrangeClearPlastic":  #(color 255 140   0, 0.0, 0.15, 0.7, 0.0, color   0   0   0)
                "GreenLight":          #(color   0 255   0, 0.0, 0.30, 0.0, 1.0, color   0 255   0)
                "GreenClearPlastic":   #(color  30 200  50, 0.0, 0.15, 0.7, 0.0, color   0   0   0)
                "Rubber":              #(color  40  40  40, 0.0, 0.85, 0.0, 0.0, color   0   0   0)
                "YellowPlastic":       #(color 240 220  30, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
                "ClearPlastic":        #(color 240 245 255, 0.0, 0.05, 0.85,0.0, color   0   0   0)
                "GrayPlastic":         #(color 140 140 140, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
                "ScanPlastic":         #(color  50  50  55, 0.0, 0.40, 0.0, 0.0, color   0   0   0)
                "Gold":                #(color 255 200  50, 1.0, 0.20, 0.0, 0.0, color   0   0   0)
                "BLueMetal":           #(color  60  80 180, 1.0, 0.30, 0.0, 0.0, color   0   0   0)
                "BlackMetal":          #(color  25  25  25, 1.0, 0.35, 0.0, 0.0, color   0   0   0)
                "Paper":               #(color 245 240 230, 0.0, 0.80, 0.0, 0.0, color   0   0   0)
                "CaseWhiteMetal":      #(color 230 230 235, 0.8, 0.30, 0.0, 0.0, color   0   0   0)
                "BlackSticker":        #(color  20  20  20, 0.0, 0.30, 0.0, 0.0, color   0   0   0)
                "Capacitor":           #(color  60  60  65, 0.3, 0.50, 0.0, 0.0, color   0   0   0)
                "PCBGreenPLastic":     #(color  20  80  40, 0.0, 0.55, 0.0, 0.0, color   0   0   0)
                "USD3BluePlastic":     #(color  40  70 180, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
                "PCBBluePlastic":      #(color  30  50 150, 0.0, 0.55, 0.0, 0.0, color   0   0   0)
                "Washer":              #(color 180 180 185, 1.0, 0.35, 0.0, 0.0, color   0   0   0)
                "RedMetal":            #(color 180  30  30, 1.0, 0.30, 0.0, 0.0, color   0   0   0)
                "GrayMetal":           #(color 150 150 155, 1.0, 0.35, 0.0, 0.0, color   0   0   0)
                "GraySticker":         #(color 160 160 160, 0.0, 0.30, 0.0, 0.0, color   0   0   0)
                "LightGreenPlastic":   #(color 120 220 120, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
                "LightYellowPlastic":  #(color 255 245 150, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
                "CaseMetal":           #(color 170 170 175, 1.0, 0.30, 0.0, 0.0, color   0   0   0)
                "Brass":               #(color 180 150  50, 1.0, 0.25, 0.0, 0.0, color   0   0   0)
                "BKMetal":             #(color  30  30  35, 1.0, 0.35, 0.0, 0.0, color   0   0   0)
                "Die":                 #(color 190 190 195, 1.0, 0.25, 0.0, 0.0, color   0   0   0)
                "Zinc":                #(color 200 200 205, 1.0, 0.30, 0.0, 0.0, color   0   0   0)
                "Chip":                #(color  35  35  40, 0.2, 0.40, 0.0, 0.0, color   0   0   0)
                default:               #(color 128 128 128, 0.0, 0.50, 0.0, 0.0, color   0   0   0)
            )
        )

        -- Search existing scene materials first, create if not found
        fn findOrCreateMaterial label =
        (
            -- 1. Search in existing scene materials
            for m in sceneMaterials do
            (
                if m.name == label do return m
            )

            -- 2. Create new PhysicalMaterial
            local preset = getMaterialPreset label
            local mat = PhysicalMaterial()
            mat.name = label
            try (mat.base_color = preset[1]) catch ()
            try (mat.metalness = preset[2]) catch ()
            try (mat.roughness = preset[3]) catch ()
            try (mat.transparency = preset[4]) catch ()
            try (mat.emission = preset[5]) catch ()
            try (mat.emit_color = preset[6]) catch ()

            logBoth ("  Created new PhysicalMaterial: " + label)
            return mat
        )

        fn applyClassificationResults results =
        (
            local appliedCount = 0
            local skippedCount = 0
            local threshold = spn_confidence.value
            local doRename = chk_rename.checked
            local doMaterial = chk_material.checked

            -- Build a lookup: fpKey -> #(label, confidence)
            local resKeys = #()
            local resLabels = #()
            local resConfs = #()
            for r in results do
            (
                append resKeys r[1]
                append resLabels r[2]
                append resConfs r[3]
            )

            for i = 1 to uniqueKeys.count do
            (
                local fpKey = uniqueKeys[i]
                local idx = findItem resKeys fpKey
                if idx == 0 do continue

                local label = resLabels[idx]
                local conf = resConfs[idx]

                if conf < threshold or label == "Unknown" do
                (
                    logBoth ("  SKIPPED group " + i as string + " (label=" + label + ", confidence=" + conf as string + "% < " + threshold as string + "%)")
                    skippedCount += uniqueGroups[i].count
                    continue
                )

                -- Find or create the material
                local mat = undefined
                if doMaterial do mat = findOrCreateMaterial label

                -- Apply to all nodes in this fingerprint group
                for j = 1 to uniqueGroups[i].count do
                (
                    local node = uniqueGroups[i][j]
                    if not isValidNode node do continue

                    if doRename do
                    (
                        if uniqueGroups[i].count > 1 then
                            node.name = label + "_" + (formattedPrint j format:"03d")
                        else
                            node.name = label
                    )

                    if doMaterial and mat != undefined do
                        node.material = mat

                    appliedCount += 1
                )

                logBoth ("  Applied [" + label + "] (" + conf as string + "%) to " + uniqueGroups[i].count as string + " meshes")

                -- Update progress (50% to 100% range for this phase)
                try (pb_progress.value = 50 + ((i as float) / uniqueKeys.count) * 50.0) catch ()
                updateStatus ("Applying " + i as string + "/" + uniqueKeys.count as string + ": " + label)
            )

            return #(appliedCount, skippedCount)
        )

        -- ========== Temp Directory Management ==========

        fn cleanupTemp =
        (
            if doesDirectoryExist tempDir do
            (
                local tempFiles = getFiles (tempDir + "*.*")
                for tf in tempFiles do
                    try (deleteFile tf) catch ()
            )
        )

        fn ensureTempDir =
        (
            makeDir tempDir all:true
            cleanupTemp()
        )

        -- ========== UI Event Handlers ==========

        on AI_MatUI open do
        (
            -- Determine script directory from source path
            local srcPath = getSourceFileName()
            if srcPath != undefined and srcPath != "" then
                scriptDir = getFilenamePath srcPath
            else
                scriptDir = "D:\\Inventec\\Zin_All_Tools\\max_script\\AI_MaterialAssigner\\"

            configPath = scriptDir + "config.ini"
            tempDir = scriptDir + "_temp\\"
            logFilePath = scriptDir + "AI_MaterialAssigner_Log.txt"

            loadConfig()
            writeLog "=== AI Material Assigner v1.0 opened ==="
        )

        on btn_saveKey pressed do
        (
            saveConfig()
            appendLog "API Key and settings saved."
        )

        on btn_editConfig pressed do
        (
            if doesFileExist configPath then
                shellLaunch configPath ""
            else
                messageBox ("Config file not found:\n" + configPath) title:"Error"
        )

        -- ========== Step 1: Analyze Scene ==========

        on btn_analyze pressed do
        (
            logBoth ""
            logBoth "=== Phase 1: Scene Analysis (Fingerprinting) ==="

            pb_progress.value = 0
            updateStatus "Scanning geometry..."
            analysisComplete = false
            btn_classify.enabled = false

            local geoArr = #()
            collectAllGeometries &geoArr

            if geoArr.count == 0 do
            (
                lbl_stats.text = "No geometry found in the scene!"
                logBoth "No geometry found."
                return ()
            )

            logBoth ("Total geometry nodes: " + geoArr.count as string)
            updateStatus ("Grouping " + geoArr.count as string + " meshes by shape fingerprint...")

            groupByFingerprint geoArr &uniqueKeys &uniqueGroups

            -- Calculate stats
            local totalMeshes = geoArr.count
            local uniqueCount = uniqueKeys.count
            local largestGroup = 0
            for grp in uniqueGroups do
                if grp.count > largestGroup do largestGroup = grp.count

            local estTime = uniqueCount * (spn_delay.value + 3)  -- delay + ~3s per API call
            local estMin = estTime / 60

            lbl_stats.text = "Found " + uniqueCount as string + " unique shapes in " + totalMeshes as string + \
                             " meshes. Est. time: ~" + (formattedPrint estMin format:".1f") + " min"

            logBoth ("Unique shapes: " + uniqueCount as string)
            logBoth ("Largest group: " + largestGroup as string + " identical meshes")
            logBoth ("API calls needed: " + uniqueCount as string)
            logBoth ("Estimated time: ~" + (formattedPrint estMin format:".1f") + " minutes")

            -- Log top 10 largest groups
            local sortedIdx = #()
            local sortedCounts = #()
            for i = 1 to uniqueGroups.count do
            (
                append sortedIdx i
                append sortedCounts uniqueGroups[i].count
            )
            -- Simple selection sort for top 10
            for i = 1 to (amin #(10, sortedIdx.count)) do
            (
                local maxIdx = i
                for j = (i+1) to sortedIdx.count do
                    if sortedCounts[j] > sortedCounts[maxIdx] do maxIdx = j
                if maxIdx != i do
                (
                    swap sortedIdx[i] sortedIdx[maxIdx]
                    swap sortedCounts[i] sortedCounts[maxIdx]
                )
            )
            logBoth "--- Top groups by instance count ---"
            for i = 1 to (amin #(10, sortedIdx.count)) do
            (
                local gi = sortedIdx[i]
                logBoth ("  [" + sortedCounts[i] as string + " meshes] Representative: " + uniqueGroups[gi][1].name)
            )

            pb_progress.value = 100
            updateStatus "Analysis complete. Ready for classification."
            analysisComplete = true
            btn_classify.enabled = true
        )

        -- ========== Step 2: Run AI Classification ==========

        on btn_classify pressed do
        (
            if not analysisComplete do
            (
                messageBox "Please run Step 1 (Analyze) first!" title:"Error"
                return ()
            )

            if edt_apiKey.text == "" do
            (
                messageBox "Please enter your Gemini API Key!" title:"Error"
                return ()
            )

            if categoriesList.count == 0 do
            (
                messageBox "No material categories loaded from config.ini!" title:"Error"
                return ()
            )

            -- Confirm with user
            local msg = "Ready to classify " + uniqueKeys.count as string + " unique shapes.\n\n" + \
                        "This will make " + uniqueKeys.count as string + " Gemini API calls.\n" + \
                        "Estimated time: ~" + ((uniqueKeys.count * (spn_delay.value + 3)) / 60.0) as string + " minutes.\n\n" + \
                        "The viewport will flash during capture.\nDo not interact with 3ds Max until complete.\n\n" + \
                        "Continue?"
            if not (queryBox msg title:"Confirm AI Classification") do return ()

            logBoth ""
            logBoth "=== Phase 2: Viewport Capture ==="

            pb_progress.value = 0
            ensureTempDir()

            local captureSize = 512
            try (captureSize = (getINISetting configPath "General" "capture_size") as integer) catch ()

            logBoth ("Capture resolution: " + captureSize as string + "x" + captureSize as string)
            logBoth ("Capturing " + uniqueKeys.count as string + " unique shapes...")

            local capturedPaths = captureUniqueShapes captureSize

            -- Count valid captures
            local validCaptures = 0
            for p in capturedPaths do if p != "" do validCaptures += 1
            logBoth ("Capture complete: " + validCaptures as string + "/" + uniqueKeys.count as string + " images")

            if validCaptures == 0 do
            (
                logBoth "ERROR: No images were captured!"
                updateStatus "Capture failed."
                return ()
            )

            -- Write request file
            logBoth ""
            logBoth "=== Phase 3: VLM Classification ==="
            local reqPath = writeRequestFile capturedPaths
            if reqPath == "" do return ()

            logBoth ("Request file written: " + reqPath)

            -- Run Python classifier
            local resPath = runPythonClassifier reqPath
            if resPath == "" do
            (
                updateStatus "Classification failed."
                return ()
            )

            -- Read results
            local results = readResultFile resPath
            logBoth ("Results received: " + results.count as string + " classifications")

            -- Apply results
            logBoth ""
            logBoth "=== Phase 4: Applying Results ==="

            local stats = applyClassificationResults results

            -- Cleanup temp files
            cleanupTemp()

            pb_progress.value = 100

            local summaryMsg = "Classification complete!\n\n" + \
                               "Applied: " + stats[1] as string + " meshes\n" + \
                               "Skipped (low confidence): " + stats[2] as string + " meshes\n\n" + \
                               "Check the log for details."
            updateStatus ("Done! Applied: " + stats[1] as string + ", Skipped: " + stats[2] as string)
            logBoth ""
            logBoth ("=== Complete: Applied=" + stats[1] as string + " Skipped=" + stats[2] as string + " ===")

            messageBox summaryMsg title:"AI Material Assigner - Complete"
        )

        on btn_openLog pressed do
        (
            if doesFileExist logFilePath then
                shellLaunch logFilePath ""
            else
                messageBox "Log file does not exist yet." title:"Info"
        )
    )

    on execute do
    (
        createDialog AI_MatUI style:#(#style_toolwindow, #style_sysmenu, #style_titlebar)
    )
)
