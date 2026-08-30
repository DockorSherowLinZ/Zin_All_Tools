macroScript DictMaterialAssigner
category:"ZinAllTools"
tooltip:"Dictionary Material Assigner v1.0: Keyword-Based Auto Material Assignment"
icon:#("ZinAllTools", 4)
(
    rollout DictMatUI "Dictionary Material Assigner v1.1" width:460 height:590
    (
        -- ========== UI Elements ==========
        groupBox grp_matLib "Material Library (.mat)" pos:[10,8] width:440 height:68
        edittext edt_matLibPath "" text:"D:\\Inventec\\DigitalTwin\\Library\\3dsMax_Standard_Material.mat" pos:[20,28] width:340
        button btn_browseMatLib "..." pos:[370,26] width:30 height:22
        button btn_loadMatLib "Load" pos:[410,26] width:30 height:22
        label lbl_matLibStatus "" pos:[20,54] width:420

        groupBox grp_dict "Keyword Dictionary (.txt)" pos:[10,80] width:440 height:68
        edittext edt_dictPath "" pos:[20,100] width:340
        button btn_browseDict "..." pos:[370,98] width:30 height:22
        button btn_loadDict "Load" pos:[410,98] width:30 height:22
        label lbl_dictStatus "" pos:[20,126] width:420

        groupBox grp_options "Options" pos:[10,152] width:440 height:70
        radiobuttons rdo_scope labels:#("Process Entire Scene", "Process Selection Only") default:1 pos:[20,170]
        checkbox chk_dryRun "Dry Run (Preview Only)" checked:true pos:[20,196]
        checkbox chk_skipAssigned "Skip Meshes with Materials" checked:false pos:[220,196]

        button btn_run "Run Material Assignment" width:440 height:42 pos:[10,228] enabled:false
        
        progressBar pb_progress "" pos:[10,278] width:440 height:16 value:0
        label lbl_status "Ready. Load library and dictionary first." pos:[10,298] width:440

        edittext edt_log "" pos:[10,318] width:440 height:200 readOnly:true

        button btn_openLog "Open Log" width:140 height:26 pos:[10,524]
        button btn_editDict "Edit Dictionary" width:140 height:26 pos:[160,524]
        button btn_listMatLib "List Materials" width:140 height:26 pos:[310,524]

        button btn_exportLogJson "Export Log (JSON)" width:140 height:26 pos:[10,554]
        button btn_exportDictJson "Export Dict (JSON)" width:140 height:26 pos:[160,554]
        button btn_exportMatJson "Export MatLib (JSON)" width:140 height:26 pos:[310,554]

        -- ========== Internal State ==========
        local scriptDir = ""
        local logFilePath = ""
        local matLib = undefined           -- loaded MaterialLibrary
        local matLibNames = #()            -- cached material names (lowercase)
        local dictRules = #()              -- #(#("KEYWORD_UPPER", "MaterialName"), ...)
        local matLibLoaded = false
        local dictLoaded = false

        local lastRunMode = ""
        local lastRunMatched = 0
        local lastRunSkipped = 0
        local lastRunUnmatched = 0
        local lastRunUnmatchedNames = #()
        local lastRunValid = false

        -- ========== Utility Functions ==========

        fn pad0 num = (if num < 10 then "0" + (num as string) else (num as string))

        fn escapeJSON str =
        (
            local s = substituteString str "\\" "\\\\"
            s = substituteString s "\"" "\\\""
            s = substituteString s "\n" "\\n"
            s = substituteString s "\r" "\\r"
            s = substituteString s "\t" "\\t"
            return s
        )

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
            local current = edt_log.text
            if current.count > 3000 do
                current = substring current (current.count - 2000) 2000
            edt_log.text = current + msg + "\n"
        )

        fn logBoth msg = ( writeLog msg ; appendLog msg )

        fn updateStatus msg =
        (
            try (lbl_status.text = msg) catch ()
            try (windows.processPostedMessages()) catch ()
        )

        fn checkReady =
        (
            btn_run.enabled = (matLibLoaded and dictLoaded)
            if btn_run.enabled then
                updateStatus "Ready. Press 'Run Material Assignment' to start."
            else
                updateStatus "Load both library and dictionary first."
        )

        -- ========== Material Library Loading ==========

        fn loadMaterialLibrary =
        (
            local libPath = edt_matLibPath.text
            if libPath == "" do
            (
                messageBox "Please enter a material library path!" title:"Error"
                return false
            )

            if not doesFileExist libPath do
            (
                messageBox ("Material library file not found:\n" + libPath) title:"Error"
                return false
            )

            logBoth ("Loading material library: " + libPath)

            try
            (
                matLib = loadTempMaterialLibrary libPath
                matLibNames = #()
                for i = 1 to matLib.count do
                    append matLibNames (toLower matLib[i].name)

                lbl_matLibStatus.text = "Loaded: " + matLib.count as string + " materials"
                logBoth ("  Successfully loaded " + matLib.count as string + " materials")
                matLibLoaded = true
                checkReady()
                return true
            )
            catch
            (
                logBoth ("ERROR loading material library: " + (getCurrentException()))
                lbl_matLibStatus.text = "ERROR: Could not load library"
                matLibLoaded = false
                checkReady()
                return false
            )
        )

        -- Find material in loaded library by name (case-insensitive)
        fn findMaterialByName matName =
        (
            if matLib == undefined do return undefined
            local lowerName = toLower matName
            local idx = findItem matLibNames lowerName
            if idx > 0 then
                return matLib[idx]
            else
                return undefined
        )

        -- ========== Dictionary Loading ==========

        fn compareDictRuleLength r1 r2 =
        (
            -- Sort by keyword length descending (longest first = highest priority)
            local l1 = r1[1].count
            local l2 = r2[1].count
            case of
            (
                (l1 > l2): -1
                (l1 < l2):  1
                default:    0
            )
        )

        fn loadDictionary =
        (
            local dictPath = edt_dictPath.text
            if dictPath == "" do
            (
                messageBox "Please enter a dictionary file path!" title:"Error"
                return false
            )

            if not doesFileExist dictPath do
            (
                messageBox ("Dictionary file not found:\n" + dictPath) title:"Error"
                return false
            )

            logBoth ("Loading keyword dictionary: " + dictPath)

            try
            (
                dictRules = #()
                local f = openFile dictPath
                if f == undefined do throw "Could not open file"

                local lineNum = 0
                while not eof f do
                (
                    local line = readLine f
                    lineNum += 1

                    -- Trim whitespace
                    local trimmed = trimLeft (trimRight line)

                    -- Skip empty lines and comments
                    if trimmed.count == 0 do continue
                    if trimmed[1] == "#" do continue

                    -- Parse KEY=VALUE
                    local eqPos = findString trimmed "="
                    if eqPos == undefined do
                    (
                        logBoth ("  WARNING: Invalid format at line " + lineNum as string + ": " + trimmed)
                        continue
                    )

                    local keyword = trimRight (substring trimmed 1 (eqPos - 1))
                    local matName = trimLeft (substring trimmed (eqPos + 1) -1)

                    if keyword.count > 0 and matName.count > 0 do
                        append dictRules #(toUpper keyword, matName)
                )
                close f

                -- Sort by keyword length (longest first for priority matching)
                qsort dictRules compareDictRuleLength

                lbl_dictStatus.text = "Loaded: " + dictRules.count as string + " rules"
                logBoth ("  Successfully loaded " + dictRules.count as string + " keyword rules")

                -- Validate: check if all referenced materials exist in library
                if matLibLoaded do
                (
                    local missing = #()
                    local checked = #()
                    for rule in dictRules do
                    (
                        if findItem checked rule[2] == 0 do
                        (
                            append checked rule[2]
                            if findMaterialByName rule[2] == undefined do
                                append missing rule[2]
                        )
                    )
                    if missing.count > 0 do
                    (
                        logBoth ("  WARNING: " + missing.count as string + " materials not found in library:")
                        for m in missing do logBoth ("    MISSING: " + m)
                    )
                )

                dictLoaded = true
                checkReady()
                return true
            )
            catch
            (
                logBoth ("ERROR loading dictionary: " + (getCurrentException()))
                lbl_dictStatus.text = "ERROR: Could not load dictionary"
                dictLoaded = false
                checkReady()
                return false
            )
        )

        -- ========== Keyword Matching Engine ==========

        -- Word-boundary-aware substring match
        -- Converts separators (- _ space) to a uniform delimiter
        -- and wraps with delimiters to enforce boundary matching
        fn matchKeyword meshName keywordUpper =
        (
            -- Normalize: replace all separators with "-", wrap with "-"
            local normName = toUpper meshName
            normName = substituteString normName "_" "-"
            normName = substituteString normName " " "-"
            normName = "-" + normName + "-"

            local normKW = "-" + keywordUpper + "-"

            return (findString normName normKW) != undefined
        )

        -- Find best matching rule for a mesh name
        -- Returns: #(keyword, materialName) or undefined
        fn findBestMatch meshName =
        (
            -- Priority 1: Check if mesh name EXACTLY matches a material in the library
            if matLibLoaded do
            (
                local directMatch = findMaterialByName meshName
                if directMatch != undefined do
                    return #(meshName, directMatch.name)
            )

            -- Priority 2: Dictionary keyword matching (longest match first)
            for rule in dictRules do
            (
                if matchKeyword meshName rule[1] do
                    return #(rule[1], rule[2])
            )

            return undefined
        )

        -- ========== Main Processing Pipeline ==========

        on btn_run pressed do
        (
            if not matLibLoaded or not dictLoaded do
            (
                messageBox "Please load both the material library and dictionary first!" title:"Error"
                return ()
            )

            local isDryRun = chk_dryRun.checked
            local skipAssigned = chk_skipAssigned.checked
            local processAll = (rdo_scope.state == 1)

            -- Collect target meshes
            local targetNodes = #()
            if processAll then
            (
                for obj in objects do
                (
                    if isValidNode obj and superclassof obj == GeometryClass and classof obj != TargetObject do
                    (
                        local hasFaces = false
                        try (if obj.mesh.numfaces > 0 do hasFaces = true) catch ()
                        if hasFaces do append targetNodes obj
                    )
                )
            )
            else
            (
                for obj in selection do
                (
                    if isValidNode obj and superclassof obj == GeometryClass and classof obj != TargetObject do
                    (
                        local hasFaces = false
                        try (if obj.mesh.numfaces > 0 do hasFaces = true) catch ()
                        if hasFaces do append targetNodes obj
                    )
                )
            )

            if targetNodes.count == 0 do
            (
                messageBox ("No geometry meshes found to process!" + \
                    (if not processAll then "\n\nTip: Select meshes first, or switch to 'Process Entire Scene'." else "")) \
                    title:"No Meshes"
                return ()
            )

            logBoth ""
            logBoth ("=== Dictionary Material Assignment " + (if isDryRun then "(DRY RUN) " else "") + "===")
            logBoth ("Target: " + targetNodes.count as string + " meshes (" + (if processAll then "entire scene" else "selection") + ")")

            pb_progress.value = 0
            local matchedCount = 0
            local skippedCount = 0
            local unmatchedCount = 0
            local unmatchedNames = #()  -- for reporting

            -- Material cache: avoid repeated library lookups
            local matCacheNames = #()
            local matCacheObjs = #()

            for i = 1 to targetNodes.count do
            (
                local node = targetNodes[i]
                if not isValidNode node do continue

                -- Update progress
                try (pb_progress.value = ((i as float) / targetNodes.count) * 100.0) catch ()
                if mod i 50 == 0 do
                    updateStatus ((if isDryRun then "[DRY RUN] " else "") + "Processing " + i as string + "/" + targetNodes.count as string)
                try (windows.processPostedMessages()) catch ()

                -- Skip if already has material assigned
                if skipAssigned and node.material != undefined do
                (
                    skippedCount += 1
                    continue
                )

                -- Find best match
                local result = findBestMatch node.name

                if result != undefined then
                (
                    local matchedKeyword = result[1]
                    local targetMatName = result[2]

                    -- Find material in library (inline cache lookup)
                    local mat = undefined
                    local cacheIdx = findItem matCacheNames targetMatName
                    if cacheIdx > 0 then
                    (
                        mat = matCacheObjs[cacheIdx]
                    )
                    else
                    (
                        mat = findMaterialByName targetMatName
                        if mat != undefined do
                        (
                            append matCacheNames targetMatName
                            append matCacheObjs mat
                        )
                    )

                    if mat != undefined then
                    (
                        if isDryRun then
                        (
                            logBoth ("  [MATCH] " + node.name + "  ->  keyword: [" + matchedKeyword + "]  ->  material: [" + targetMatName + "]")
                        )
                        else
                        (
                            node.material = mat
                            logBoth ("  [ASSIGNED] " + node.name + "  <-  [" + targetMatName + "]  (keyword: " + matchedKeyword + ")")
                        )
                        matchedCount += 1
                    )
                    else
                    (
                        logBoth ("  [WARNING] " + node.name + "  ->  keyword: [" + matchedKeyword + "]  ->  Material [" + targetMatName + "] NOT FOUND in library!")
                        unmatchedCount += 1
                    )
                )
                else
                (
                    unmatchedCount += 1
                    -- Track unique unmatched names for dictionary expansion
                    local uName = toUpper node.name
                    if findItem unmatchedNames uName == 0 do
                        append unmatchedNames uName
                )
            )

            -- Summary
            pb_progress.value = 100
            logBoth ""
            logBoth "=== Summary ==="
            logBoth ("  Matched:    " + matchedCount as string + " meshes" + (if isDryRun then " (dry run, not applied)" else ""))
            logBoth ("  Skipped:    " + skippedCount as string + " meshes (already had materials)")
            logBoth ("  Unmatched:  " + unmatchedCount as string + " meshes (no keyword found)")

            -- Report unmatched names for dictionary expansion
            if unmatchedNames.count > 0 do
            (
                logBoth ""
                logBoth ("--- Unmatched Mesh Names (" + unmatchedNames.count as string + " unique) ---")
                logBoth "Add these to your dictionary if needed:"
                for uName in unmatchedNames do
                    logBoth ("  " + uName)
            )

            logBoth ""
            logBoth "=== Complete ==="

            local modeStr = if isDryRun then "DRY RUN" else "APPLIED"

            -- Save state for JSON Export
            lastRunMode = modeStr
            lastRunMatched = matchedCount
            lastRunSkipped = skippedCount
            lastRunUnmatched = unmatchedCount
            lastRunUnmatchedNames = unmatchedNames
            lastRunValid = true

            updateStatus (modeStr + " | Matched: " + matchedCount as string + " | Unmatched: " + unmatchedCount as string)

            local summaryMsg = (if isDryRun then "DRY RUN Complete (no changes made)\n\n" else "Material Assignment Complete!\n\n") + \
                "Matched: " + matchedCount as string + " meshes\n" + \
                "Skipped: " + skippedCount as string + " meshes\n" + \
                "Unmatched: " + unmatchedCount as string + " meshes\n" + \
                (if unmatchedNames.count > 0 then ("\n" + unmatchedNames.count as string + " unique unmatched names listed in log.\nConsider adding them to your dictionary.") else "") + \
                (if isDryRun then "\n\nUncheck 'Dry Run' to apply for real." else "")

            messageBox summaryMsg title:("Dictionary Material Assigner - " + modeStr)
        )

        -- ========== Browse Buttons ==========

        on btn_browseMatLib pressed do
        (
            local f = getOpenFileName caption:"Select Material Library (.mat)" types:"Material Library (*.mat)|*.mat|All Files (*.*)|*.*|"
            if f != undefined do edt_matLibPath.text = f
        )

        on btn_browseDict pressed do
        (
            local f = getOpenFileName caption:"Select Keyword Dictionary (.txt)" types:"Text Files (*.txt)|*.txt|All Files (*.*)|*.*|"
            if f != undefined do edt_dictPath.text = f
        )

        -- ========== Load Buttons ==========

        on btn_loadMatLib pressed do ( loadMaterialLibrary() )
        on btn_loadDict pressed do ( loadDictionary() )

        -- ========== Bottom Buttons ==========

        on btn_openLog pressed do
        (
            if doesFileExist logFilePath then
                shellLaunch logFilePath ""
            else
                messageBox "Log file does not exist yet." title:"Info"
        )

        on btn_editDict pressed do
        (
            local dictPath = edt_dictPath.text
            if dictPath != "" and doesFileExist dictPath then
                shellLaunch dictPath ""
            else
                messageBox "Dictionary file not found.\nPlease set the path and load it first." title:"Info"
        )

        on btn_listMatLib pressed do
        (
            if not matLibLoaded do
            (
                messageBox "Please load the material library first!" title:"Info"
                return ()
            )

            logBoth ""
            logBoth ("=== Materials in Library (" + matLib.count as string + ") ===")
            for i = 1 to matLib.count do
                logBoth ("  [" + (formattedPrint i format:"3d") + "] " + matLib[i].name + "  (" + (classof matLib[i]) as string + ")")
            logBoth "=== End of List ==="
        )

        -- ========== JSON Export Handlers ==========

        on btn_exportLogJson pressed do
        (
            if not lastRunValid do
            (
                messageBox "Please run the Material Assignment at least once first!" title:"Export Error"
                return ()
            )
            local defaultFile = scriptDir + "Report_" + (if lastRunMode=="DRY RUN" then "DryRun" else "Applied") + ".json"
            local fPath = getSaveFileName caption:"Export Log JSON" filename:defaultFile types:"JSON Files (*.json)|*.json|All Files (*.*)|*.*|"
            if fPath != undefined do
            (
                local f = createFile fPath
                if f != undefined then
                (
                    format "{\n" to:f
                    format "  \"mode\": \"%\",\n" lastRunMode to:f
                    format "  \"matched_count\": %,\n" lastRunMatched to:f
                    format "  \"skipped_count\": %,\n" lastRunSkipped to:f
                    format "  \"unmatched_count\": %,\n" lastRunUnmatched to:f
                    format "  \"unmatched_unique_count\": %,\n" lastRunUnmatchedNames.count to:f
                    format "  \"unmatched_names\": [\n" to:f
                    for i = 1 to lastRunUnmatchedNames.count do
                    (
                        format "    \"%\"" (escapeJSON lastRunUnmatchedNames[i]) to:f
                        if i < lastRunUnmatchedNames.count then format ",\n" to:f else format "\n" to:f
                    )
                    format "  ]\n" to:f
                    format "}\n" to:f
                    close f
                    logBoth ("Exported JSON Report to: " + fPath)
                    shellLaunch fPath ""
                )
                else ( messageBox "Could not write JSON file!" title:"Error" )
            )
        )

        on btn_exportDictJson pressed do
        (
            if not dictLoaded do
            (
                messageBox "Please load the dictionary first!" title:"Export Error"
                return ()
            )
            local fPath = getSaveFileName caption:"Export Dictionary JSON" filename:(scriptDir + "Dictionary.json") types:"JSON Files (*.json)|*.json|All Files (*.*)|*.*|"
            if fPath != undefined do
            (
                local f = createFile fPath
                if f != undefined then
                (
                    format "[\n" to:f
                    for i = 1 to dictRules.count do
                    (
                        local rule = dictRules[i]
                        format "  {\"keyword\": \"%\", \"material\": \"%\"}" (escapeJSON rule[1]) (escapeJSON rule[2]) to:f
                        if i < dictRules.count then format ",\n" to:f else format "\n" to:f
                    )
                    format "]\n" to:f
                    close f
                    logBoth ("Exported Dictionary JSON to: " + fPath)
                    shellLaunch fPath ""
                )
                else ( messageBox "Could not write JSON file!" title:"Error" )
            )
        )

        on btn_exportMatJson pressed do
        (
            if not matLibLoaded do
            (
                messageBox "Please load the material library first!" title:"Export Error"
                return ()
            )
            local fPath = getSaveFileName caption:"Export Material Library JSON" filename:(scriptDir + "Materials.json") types:"JSON Files (*.json)|*.json|All Files (*.*)|*.*|"
            if fPath != undefined do
            (
                local f = createFile fPath
                if f != undefined then
                (
                    format "[\n" to:f
                    for i = 1 to matLib.count do
                    (
                        local m = matLib[i]
                        format "  {\"name\": \"%\", \"class\": \"%\"}" (escapeJSON m.name) ((classof m) as string) to:f
                        if i < matLib.count then format ",\n" to:f else format "\n" to:f
                    )
                    format "]\n" to:f
                    close f
                    logBoth ("Exported Material Library JSON to: " + fPath)
                    shellLaunch fPath ""
                )
                else ( messageBox "Could not write JSON file!" title:"Error" )
            )
        )

        -- ========== Initialization ==========

        on DictMatUI open do
        (
            -- Always use the known project directory (avoids write-protected Program Files)
            scriptDir = "D:\\Zin_All_Tools\\max_script\\DictMaterialAssigner\\"

            -- Fallback: if the project dir doesn't exist, try getSourceFileName
            if not doesDirectoryExist scriptDir do
            (
                local srcPath = getSourceFileName()
                if srcPath != undefined and srcPath != "" then
                    scriptDir = getFilenamePath srcPath
                else
                    scriptDir = sysInfo.tempdir
            )

            -- Log file: try script dir first, fall back to temp if not writable
            logFilePath = scriptDir + "DictMaterialAssigner_Log.txt"
            local testFile = undefined
            try (testFile = createFile logFilePath) catch ()
            if testFile != undefined then
            (
                close testFile
            )
            else
            (
                -- Script dir is not writable, use temp directory
                logFilePath = sysInfo.tempdir + "DictMaterialAssigner_Log.txt"
            )

            -- Auto-set dictionary path to same folder as script
            local defaultDict = scriptDir + "material_dictionary.txt"
            if doesFileExist defaultDict do
                edt_dictPath.text = defaultDict

            writeLog "=== DictMaterialAssigner v1.0 opened ==="
        )
    )

    on execute do
    (
        createDialog DictMatUI style:#(#style_toolwindow, #style_sysmenu, #style_titlebar)
    )
)
