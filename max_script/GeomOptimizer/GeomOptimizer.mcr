macroScript GeomOptimizer
category:"ZinAllTools"
tooltip:"Geometry Optimizer v1.0: Sequential Delete Duplicates + Attach Identical Meshes"
icon:#("ZinAllTools", 2)
(
    rollout GeomOptUI "Geometry Optimizer v1.0" width:460 height:480
    (
        -- ========== UI Elements ==========
        groupBox grp_scope "Scope" pos:[10,8] width:440 height:44
        radiobuttons rdo_scope labels:#("Process Entire Scene", "Process Selection Only") default:1 pos:[20,26]

        groupBox grp_steps "Operations (Strict Sequential Order)" pos:[10,56] width:440 height:72
        checkbox chk_step1 "Step 1: Delete Duplicates (same transform, overlapping)" checked:true pos:[20,74]
        checkbox chk_step2 "Step 2: Attach Identical (same shape, different position)" checked:true pos:[20,96]

        button btn_run "Run Optimization" width:440 height:40 pos:[10,134]

        progressBar pb_progress "" pos:[10,182] width:440 height:14 value:0
        label lbl_status "Ready." pos:[10,200] width:440

        edittext edt_log "" pos:[10,218] width:440 height:200 readOnly:true

        button btn_openLog "Open Log" width:215 height:26 pos:[10,424]
        button btn_exportJson "Export Report (JSON)" width:215 height:26 pos:[235,424]

        -- ========== Internal State ==========
        local scriptDir = ""
        local logFilePath = ""

        -- Report data (saved for JSON export)
        local reportValid = false
        local reportTotalBefore = 0
        local reportStep1Deleted = 0
        local reportStep2Groups = 0
        local reportStep2Merged = 0
        local reportTotalAfter = 0

        -- ========== Utility Functions ==========

        fn pad0 num = (if num < 10 then "0" + (num as string) else (num as string))

        -- Round to 4 decimal places (matching ResetModel convention)
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
            local current = edt_log.text
            if current.count > 4000 do
                current = substring current (current.count - 3000) 3000
            edt_log.text = current + msg + "\n"
        )

        fn logBoth msg = ( writeLog msg ; appendLog msg )

        fn updateStatus msg =
        (
            try (lbl_status.text = msg) catch ()
            try (windows.processPostedMessages()) catch ()
        )

        fn escapeJSON str =
        (
            local s = substituteString str "\\" "\\\\"
            s = substituteString s "\"" "\\\""
            s = substituteString s "\n" "\\n"
            s = substituteString s "\r" "\\r"
            s = substituteString s "\t" "\\t"
            return s
        )

        -- Character classification helpers
        fn isDigitChar ch = (findString "0123456789" ch != undefined)
        fn isSepChar ch = (ch == "_" or ch == "-" or ch == " ")

        -- ========== Base Name Extraction ==========
        -- Strips trailing numeric suffix and preceding separators.
        --
        -- Algorithm:
        --   "SCREW-M3X5_001" -> strip digits "001" -> "SCREW-M3X5_"
        --                    -> strip separator "_"  -> "SCREW-M3X5"
        --
        --   "FAN-HOLDER_010" -> strip digits "010"  -> "FAN-HOLDER_"
        --                    -> strip separator "_"  -> "FAN-HOLDER"
        --
        --   "HEATSINK" (no trailing digits)          -> "HEATSINK" (unchanged)
        --
        fn getBaseName meshName =
        (
            local name = meshName
            -- Phase 1: Strip trailing digits
            while name.count > 0 and isDigitChar name[name.count] do
                name = substring name 1 (name.count - 1)
            -- Phase 2: Strip trailing separators (_ - space)
            while name.count > 0 and isSepChar name[name.count] do
                name = substring name 1 (name.count - 1)
            -- Fallback: if everything was stripped, return original
            if name.count == 0 do return meshName
            return name
        )

        -- ========== Geometry Collection ==========
        -- Recursively collect all valid geometry nodes (has faces, is not Helper)
        fn collectAllGeometry nodeList &geoArr =
        (
            for n in nodeList do
            (
                if isValidNode n do
                (
                    if superclassof n == GeometryClass and classof n != TargetObject do
                    (
                        local hasFaces = false
                        try (if n.mesh.numfaces > 0 do hasFaces = true) catch ()
                        if hasFaces do append geoArr n
                    )
                    if n.children.count > 0 do
                    (
                        local kids = for c in n.children collect c
                        collectAllGeometry kids &geoArr
                    )
                )
            )
        )

        -- ========== Step 1: Delete Duplicates ==========
        --
        -- Definition: Meshes with EXACT SAME transform (position + rotation + scale)
        --             AND same topology (face count + vertex count).
        --             These are overlapping/co-planar geometry from bad CAD imports.
        --
        -- Fingerprint = full 3x4 transform matrix + numfaces + numverts
        -- (Identical to ResetModel v1.13 convention)

        fn getDupFingerprint node =
        (
            local tf = node.transform
            local fp = (rnd tf.row1.x) as string + "|" + (rnd tf.row1.y) as string + "|" + (rnd tf.row1.z) as string + "|" + \
                       (rnd tf.row2.x) as string + "|" + (rnd tf.row2.y) as string + "|" + (rnd tf.row2.z) as string + "|" + \
                       (rnd tf.row3.x) as string + "|" + (rnd tf.row3.y) as string + "|" + (rnd tf.row3.z) as string + "|" + \
                       (rnd tf.row4.x) as string + "|" + (rnd tf.row4.y) as string + "|" + (rnd tf.row4.z) as string + "|" + \
                       (node.mesh.numfaces as string) + "|" + (node.mesh.numverts as string)
            return fp
        )

        fn runStep1_DeleteDuplicates &geoArr =
        (
            logBoth ""
            logBoth "=========================================="
            logBoth "  Step 1: Delete Duplicates"
            logBoth "=========================================="

            if geoArr.count < 2 do
            (
                logBoth "  Skipped: fewer than 2 geometry nodes."
                return 0
            )

            logBoth ("  Scanning " + geoArr.count as string + " geometry nodes...")

            -- Build fingerprint groups
            local fpKeys = #()
            local fpGroups = #()

            for n in geoArr do
            (
                if isValidNode n do
                (
                    local fp = getDupFingerprint n
                    local idx = findItem fpKeys fp
                    if idx == 0 then
                    (
                        append fpKeys fp
                        append fpGroups #(n)
                    )
                    else
                    (
                        append fpGroups[idx] n
                    )
                )
            )

            -- Identify duplicates (groups with 2+ members)
            local nodesToDelete = #()
            local dupGroupCount = 0

            for i = 1 to fpGroups.count do
            (
                local grp = fpGroups[i]
                if grp.count > 1 do
                (
                    dupGroupCount += 1
                    logBoth ("  [DUP GROUP " + dupGroupCount as string + "] " + grp.count as string + " overlapping meshes:")
                    logBoth ("    [KEPT]    " + grp[1].name)
                    for j = 2 to grp.count do
                    (
                        logBoth ("    [DELETE]  " + grp[j].name)
                        append nodesToDelete grp[j]
                    )
                )
            )

            -- Delete
            local removedCount = nodesToDelete.count
            if removedCount > 0 do
            (
                for dNode in nodesToDelete do
                    if isValidNode dNode do delete dNode
            )

            -- Refresh geoArr: remove deleted nodes
            local validArr = #()
            for n in geoArr do
                if isValidNode n do append validArr n
            geoArr = validArr

            logBoth ""
            logBoth ("  Step 1 Summary: " + removedCount as string + " duplicates deleted from " + dupGroupCount as string + " groups")
            logBoth ("  Remaining geometry: " + geoArr.count as string + " nodes")
            return removedCount
        )

        -- ========== Step 2: Attach Identical ==========
        --
        -- Definition: Meshes that share the SAME base name (ignoring trailing
        --             numeric suffix), SAME scale, and SAME topology.
        --             They differ in position and rotation (e.g., 500 screws).
        --
        -- Grouping Key = toUpper(baseName) + scale + faceCount + vertCount
        --
        -- Performance: Uses undo off + redraw off to avoid O(N^2) undo buffer
        --              and viewport overhead. For extremely large groups, binary
        --              merge could be added but sequential is sufficient for
        --              typical industrial models (hundreds of instances).

        fn getIdenticalGroupKey node baseName =
        (
            local tf = node.transform
            -- Extract scale from transform row vectors
            local sx = rnd (length [tf.row1.x, tf.row1.y, tf.row1.z])
            local sy = rnd (length [tf.row2.x, tf.row2.y, tf.row2.z])
            local sz = rnd (length [tf.row3.x, tf.row3.y, tf.row3.z])
            -- Combine: baseName (case-insensitive) + scale + topology
            local key = (toUpper baseName) + "|" + \
                        sx as string + "|" + sy as string + "|" + sz as string + "|" + \
                        (node.mesh.numfaces as string) + "|" + (node.mesh.numverts as string)
            return key
        )

        fn runStep2_AttachIdentical geoArr =
        (
            logBoth ""
            logBoth "=========================================="
            logBoth "  Step 2: Attach Identical"
            logBoth "=========================================="

            if geoArr.count < 2 do
            (
                logBoth "  Skipped: fewer than 2 geometry nodes."
                return #(0, 0)
            )

            logBoth ("  Analyzing " + geoArr.count as string + " geometry nodes for identical shapes...")

            -- Build groups by baseName + scale + topology
            local groupKeys = #()
            local groupNodes = #()
            local groupBaseNames = #()

            for n in geoArr do
            (
                if isValidNode n do
                (
                    local bName = getBaseName n.name
                    local gKey = getIdenticalGroupKey n bName
                    local idx = findItem groupKeys gKey
                    if idx == 0 then
                    (
                        append groupKeys gKey
                        append groupNodes #(n)
                        append groupBaseNames bName
                    )
                    else
                    (
                        append groupNodes[idx] n
                    )
                )
            )

            -- Count attachable groups
            local attachableCount = 0
            local totalMergedCount = 0
            for i = 1 to groupNodes.count do
                if groupNodes[i].count > 1 do attachableCount += 1

            if attachableCount == 0 do
            (
                logBoth "  No identical mesh groups found to attach."
                return #(0, 0)
            )

            logBoth ("  Found " + attachableCount as string + " groups with identical meshes to attach.")
            logBoth ""

            -- Perform attach with performance optimization
            local groupsDone = 0

            undo off
            (
                with redraw off
                (
                    for i = 1 to groupNodes.count do
                    (
                        local grp = groupNodes[i]
                        if grp.count < 2 do continue

                        groupsDone += 1
                        local baseName = groupBaseNames[i]
                        local memberCount = grp.count

                        logBoth ("  [ATTACH GROUP " + groupsDone as string + "/" + attachableCount as string + "] \"" + baseName + "\" (" + memberCount as string + " meshes)")

                        -- Log first few members
                        local logLimit = amin memberCount 5
                        for j = 1 to logLimit do
                            logBoth ("    [" + j as string + "] " + grp[j].name)
                        if memberCount > 5 do
                            logBoth ("    ... and " + (memberCount - 5) as string + " more")

                        -- Unparent all nodes (detach from hierarchy)
                        for n in grp do
                            if isValidNode n do n.parent = undefined

                        -- Convert target to Editable Mesh
                        local target = grp[1]
                        convertToMesh target

                        -- Sequential attach (with undo off + redraw off for performance)
                        local attachCount = 0
                        for j = 2 to grp.count do
                        (
                            if isValidNode grp[j] do
                            (
                                convertToMesh grp[j]
                                try
                                (
                                    meshop.attach target grp[j]
                                    attachCount += 1
                                )
                                catch
                                (
                                    logBoth ("    WARNING: Failed to attach " + grp[j].name + ": " + (getCurrentException()))
                                )
                            )

                            -- Progress update every 100 attaches
                            if mod j 100 == 0 do
                            (
                                updateStatus ("Attaching group " + groupsDone as string + ": " + j as string + "/" + memberCount as string)
                            )
                        )

                        -- Post-attach: Set pivot to World Origin [0,0,0]
                        target.pivot = [0, 0, 0]

                        -- Post-attach: Rename to base name
                        target.name = baseName

                        totalMergedCount += attachCount

                        logBoth ("    -> Result: \"" + baseName + "\" (" + target.mesh.numfaces as string + " faces, " + target.mesh.numverts as string + " verts)")
                    )
                )
            )

            logBoth ""
            logBoth ("  Step 2 Summary: " + groupsDone as string + " groups attached, " + totalMergedCount as string + " meshes merged")

            -- Force viewport redraw
            try (redrawViews()) catch ()

            return #(groupsDone, totalMergedCount)
        )

        -- ========== Main Button Handler ==========

        on btn_run pressed do
        (
            local doStep1 = chk_step1.checked
            local doStep2 = chk_step2.checked

            if not doStep1 and not doStep2 do
            (
                messageBox "Please select at least one operation!" title:"Error"
                return ()
            )

            local processAll = (rdo_scope.state == 1)

            -- Collect geometry
            local geoArr = #()
            if processAll then
            (
                local roots = for obj in objects where obj.parent == undefined collect obj
                collectAllGeometry roots &geoArr
            )
            else
            (
                local sel = for obj in selection collect obj
                collectAllGeometry sel &geoArr
            )

            if geoArr.count == 0 do
            (
                messageBox ("No geometry meshes found!" + \
                    (if not processAll then "\n\nTip: Select meshes first, or switch to 'Process Entire Scene'." else "")) \
                    title:"No Meshes"
                return ()
            )

            logBoth ""
            logBoth "######################################################"
            logBoth "  Geometry Optimizer v1.0 - Run Started"
            logBoth "######################################################"
            logBoth ("  Scope: " + (if processAll then "Entire Scene" else "Selection Only"))
            logBoth ("  Total geometry nodes: " + geoArr.count as string)

            reportTotalBefore = geoArr.count
            reportStep1Deleted = 0
            reportStep2Groups = 0
            reportStep2Merged = 0
            pb_progress.value = 0

            -- ==========================================
            --  Step 1: Delete Duplicates (must run first)
            -- ==========================================
            if doStep1 do
            (
                updateStatus "Step 1: Deleting duplicates..."
                pb_progress.value = 10
                reportStep1Deleted = runStep1_DeleteDuplicates &geoArr
                pb_progress.value = 50
            )

            -- ==========================================
            --  Step 2: Attach Identical (must run second)
            -- ==========================================
            if doStep2 do
            (
                updateStatus "Step 2: Attaching identical meshes..."
                pb_progress.value = 55
                local step2Result = runStep2_AttachIdentical geoArr
                reportStep2Groups = step2Result[1]
                reportStep2Merged = step2Result[2]
                pb_progress.value = 95
            )

            -- Final count
            local finalGeo = #()
            if processAll then
            (
                local roots = for obj in objects where obj.parent == undefined collect obj
                collectAllGeometry roots &finalGeo
            )
            else
            (
                for obj in objects do
                    if isValidNode obj and superclassof obj == GeometryClass and classof obj != TargetObject do
                    (
                        local hf = false
                        try (if obj.mesh.numfaces > 0 do hf = true) catch ()
                        if hf do append finalGeo obj
                    )
            )
            reportTotalAfter = finalGeo.count
            reportValid = true

            pb_progress.value = 100

            -- Final report
            logBoth ""
            logBoth "======================================================"
            logBoth "  FINAL REPORT"
            logBoth "======================================================"
            logBoth ("  Before:           " + reportTotalBefore as string + " geometry nodes")
            if doStep1 do
                logBoth ("  Step 1 Deleted:   " + reportStep1Deleted as string + " overlapping duplicates")
            if doStep2 do
            (
                logBoth ("  Step 2 Attached:  " + reportStep2Groups as string + " groups (" + reportStep2Merged as string + " meshes merged)")
            )
            logBoth ("  After:            " + reportTotalAfter as string + " geometry nodes")
            logBoth ("  Reduction:        " + (reportTotalBefore - reportTotalAfter) as string + " nodes removed (" + \
                (if reportTotalBefore > 0 then (((reportTotalBefore - reportTotalAfter) as float / reportTotalBefore * 100.0) as integer) as string else "0") + "%)")
            logBoth "======================================================"

            updateStatus ("Done! Before: " + reportTotalBefore as string + " -> After: " + reportTotalAfter as string + " nodes")

            local summaryMsg = "Geometry Optimization Complete!\n\n" + \
                "Before: " + reportTotalBefore as string + " geometry nodes\n" + \
                (if doStep1 then ("Step 1: " + reportStep1Deleted as string + " duplicates deleted\n") else "") + \
                (if doStep2 then ("Step 2: " + reportStep2Groups as string + " groups attached (" + reportStep2Merged as string + " merged)\n") else "") + \
                "After: " + reportTotalAfter as string + " geometry nodes\n\n" + \
                "Reduction: " + (reportTotalBefore - reportTotalAfter) as string + " nodes (" + \
                (if reportTotalBefore > 0 then (((reportTotalBefore - reportTotalAfter) as float / reportTotalBefore * 100.0) as integer) as string else "0") + "%)"

            messageBox summaryMsg title:"Geometry Optimizer - Complete"
        )

        -- ========== Bottom Buttons ==========

        on btn_openLog pressed do
        (
            if doesFileExist logFilePath then
                shellLaunch logFilePath ""
            else
                messageBox "Log file does not exist yet." title:"Info"
        )

        on btn_exportJson pressed do
        (
            if not reportValid do
            (
                messageBox "Please run the optimization at least once first!" title:"Export Error"
                return ()
            )
            local fPath = getSaveFileName caption:"Export Optimization Report (JSON)" \
                filename:(scriptDir + "GeomOptimizer_Report.json") \
                types:"JSON Files (*.json)|*.json|All Files (*.*)|*.*|"
            if fPath != undefined do
            (
                local f = createFile fPath
                if f != undefined then
                (
                    format "{\n" to:f
                    format "  \"total_before\": %,\n" reportTotalBefore to:f
                    format "  \"step1_duplicates_deleted\": %,\n" reportStep1Deleted to:f
                    format "  \"step2_groups_attached\": %,\n" reportStep2Groups to:f
                    format "  \"step2_meshes_merged\": %,\n" reportStep2Merged to:f
                    format "  \"total_after\": %,\n" reportTotalAfter to:f
                    format "  \"reduction_count\": %,\n" (reportTotalBefore - reportTotalAfter) to:f
                    local pct = if reportTotalBefore > 0 then ((reportTotalBefore - reportTotalAfter) as float / reportTotalBefore * 100.0) else 0.0
                    format "  \"reduction_percent\": %\n" (rnd pct) to:f
                    format "}\n" to:f
                    close f
                    logBoth ("Exported JSON report: " + fPath)
                    shellLaunch fPath ""
                )
                else ( messageBox "Could not write JSON file!" title:"Error" )
            )
        )

        -- ========== Initialization ==========

        on GeomOptUI open do
        (
            scriptDir = "D:\\Zin_All_Tools\\max_script\\GeomOptimizer\\"

            if not doesDirectoryExist scriptDir do
            (
                local srcPath = getSourceFileName()
                if srcPath != undefined and srcPath != "" then
                    scriptDir = getFilenamePath srcPath
                else
                    scriptDir = sysInfo.tempdir
            )

            logFilePath = scriptDir + "GeomOptimizer_Log.txt"
            local testFile = undefined
            try (testFile = createFile logFilePath) catch ()
            if testFile != undefined then
                close testFile
            else
                logFilePath = sysInfo.tempdir + "GeomOptimizer_Log.txt"

            writeLog "=== Geometry Optimizer v1.0 opened ==="
        )
    )

    on execute do
    (
        createDialog GeomOptUI style:#(#style_toolwindow, #style_sysmenu, #style_titlebar)
    )
)
