macroScript ResetModel_v1_13
category:"ZinAllTools"
tooltip:"ResetModel v1.13: Batch STEP Import, Transform Preprocess, Prefix, Full Auto"
(
    rollout ResetModel_UI "ResetModel v1.13" width:420 height:370
    (
        -- ========== UI 元素 ==========
        label lbl_srcFolder "Source Folder (STEP):" pos:[10,10]
        edittext edt_srcFolder "" pos:[10,28] width:320
        button btn_browseSrc "Browse" pos:[340,26] width:70 height:24

        label lbl_outFolder "Output Folder:" pos:[10,58]
        edittext edt_outFolder "" pos:[10,76] width:320
        button btn_browseOut "Browse" pos:[340,74] width:70 height:24

        checkbox chk_createMarker "Create Bottom Center Marker" checked:false pos:[10,110]
        checkbox chk_detachByMatID "Auto Detach by Material ID" checked:true pos:[10,130]
        checkbox chk_removeDuplicates "Auto Remove Duplicate Meshes" checked:true pos:[10,150]
        checkbox chk_addPrefix "Add Prefix to Numeric Group Names" checked:true pos:[10,170]
        edittext edt_prefix "Prefix:" text:"P_" labelOnTop:false pos:[30,190] fieldWidth:80

        button btn_clean "Clean && Align" width:400 height:50 pos:[10,220]
        label lbl_status "Ready..." pos:[10,278] width:400
        progressBar pb_progress "" pos:[10,298] width:400 height:20 value:0
        button btn_openLog "Open Log File" width:400 height:30 pos:[10,328]

        -- ========== 變數區 ==========
        local totalNodesCount = 0
        local processedNodesCount = 0
        local logFilePath = ""

        -- ========== 工具函式 ==========

        -- 補零 (用於時間格式)
        fn pad0 num =
        (
            if num < 10 then "0" + (num as string) else (num as string)
        )

        -- 浮點數精度工具：四捨五入至小數點後 4 位
        fn rnd val = (floor (val * 10000.0 + 0.5)) / 10000.0

        -- Log 系統初始化
        fn initLogFile =
        (
            if maxFilePath != "" then
                logFilePath = maxFilePath + "ResetModel_Log.txt"
            else
                logFilePath = sysInfo.tempdir + "ResetModel_Log.txt"
        )

        -- 寫入 Log (+時間戳記)
        fn writeLog msg =
        (
            if logFilePath == "" do initLogFile()

            local f = openFile logFilePath mode:"a"
            if f == undefined do
            (
                f = createFile logFilePath
            )

            if f != undefined do
            (
                local t = getLocalTime()
                local timeStr = "[" + (pad0 t[5]) + ":" + (pad0 t[6]) + ":" + (pad0 t[7]) + "]"
                format "% %\n" timeStr msg to:f
                close f
            )
        )

        -- 計算節點數量
        fn getNodesCount node =
        (
            local c = 1
            for child in node.children do
            (
                c += getNodesCount child
            )
            return c
        )

        -- ========== 前掃描函式 ==========

        -- 遞迴掃描並開啟群組
        fn openAllGroups node =
        (
            if not isValidNode node do return ()

            if isGroupHead node do
            (
                setGroupOpen node true
                writeLog ("Opened Group: " + node.name)
            )

            local kidsArr = for c in node.children collect c
            for k in kidsArr do openAllGroups k
        )

        -- 嚴格幾何邊界計算函式 (排除所有 Helper 尺寸污染)
        fn getStrictGeomBounds nodeArray &minPt &maxPt =
        (
            for n in nodeArray do
            (
                if isValidNode n do
                (
                    if superclassof n == GeometryClass and classof n != TargetObject do
                    (
                        local hasFaces = false
                        try (
                            if n.mesh.numfaces > 0 do hasFaces = true
                        ) catch ()

                        if hasFaces do
                        (
                            if minPt == undefined then
                            (
                                minPt = [n.min.x, n.min.y, n.min.z]
                                maxPt = [n.max.x, n.max.y, n.max.z]
                            )
                            else
                            (
                                if n.min.x < minPt.x do minPt.x = n.min.x
                                if n.min.y < minPt.y do minPt.y = n.min.y
                                if n.min.z < minPt.z do minPt.z = n.min.z

                                if n.max.x > maxPt.x do maxPt.x = n.max.x
                                if n.max.y > maxPt.y do maxPt.y = n.max.y
                                if n.max.z > maxPt.z do maxPt.z = n.max.z
                            )
                        )
                    )

                    if n.children.count > 0 do
                    (
                        local kids = for c in n.children collect c
                        getStrictGeomBounds kids &minPt &maxPt
                    )
                )
            )
        )

        -- 遞迴收集所有有效幾何體
        fn collectGeometries node &geoArr =
        (
            if isValidNode node do
            (
                if superclassof node == GeometryClass and classof node != TargetObject do
                (
                    local hasFaces = false
                    try (
                        if node.mesh.numfaces > 0 do hasFaces = true
                    ) catch ()
                    if hasFaces do append geoArr node
                )
                for c in node.children do collectGeometries c &geoArr
            )
        )

        -- 取得節點指紋
        fn getNodeFingerprint node =
        (
            local tf = node.transform
            local fp = (rnd tf.row1.x as string) + "|" + (rnd tf.row1.y as string) + "|" + (rnd tf.row1.z as string) + "|" + \
                       (rnd tf.row2.x as string) + "|" + (rnd tf.row2.y as string) + "|" + (rnd tf.row2.z as string) + "|" + \
                       (rnd tf.row3.x as string) + "|" + (rnd tf.row3.y as string) + "|" + (rnd tf.row3.z as string) + "|" + \
                       (rnd tf.row4.x as string) + "|" + (rnd tf.row4.y as string) + "|" + (rnd tf.row4.z as string) + "|" + \
                       (node.mesh.numfaces as string) + "|" + (node.mesh.numverts as string)
            return fp
        )

        -- 重複偵測與移除
        fn removeDuplicateMeshes rootNodesArr =
        (
            local geoArr = #()
            for rNode in rootNodesArr do collectGeometries rNode &geoArr

            if geoArr.count < 2 do return 0

            local fpKeys = #()
            local fpGroups = #()

            for n in geoArr do
            (
                local fp = getNodeFingerprint n
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

            local nodesToDelete = #()

            for i = 1 to fpGroups.count do
            (
                local grp = fpGroups[i]
                if grp.count > 1 do
                (
                    writeLog ("Duplicate Match Found! FP: " + fpKeys[i])
                    writeLog ("  [KEPT] " + grp[1].name)

                    for j = 2 to grp.count do
                    (
                        local dNode = grp[j]
                        local pName = if dNode.parent != undefined then dNode.parent.name else "None"
                        writeLog ("  [DUPLICATE] Deleted: " + dNode.name + " (parent: " + pName + ")")
                        append nodesToDelete dNode
                    )
                )
            )

            local removedCount = nodesToDelete.count
            if removedCount > 0 do
            (
                for dNode in nodesToDelete do
                (
                    if isValidNode dNode do delete dNode
                )
            )

            return removedCount
        )

        -- ========== Material ID 拆分 ==========

        fn detachByMaterialID node =
        (
            convertToMesh node

            local numF = node.mesh.numfaces
            local uniqueIDs = #()
            for f = 1 to numF do
            (
                local mid = getFaceMatID node.mesh f
                if findItem uniqueIDs mid == 0 do append uniqueIDs mid
            )
            sort uniqueIDs

            if uniqueIDs.count <= 1 do return #(node)

            local originalMat = node.material
            local originalName = node.name
            local detachedParts = #()

            writeLog ("Multi-Material detected on [" + originalName + "]: " + uniqueIDs.count as string + " IDs found: " + uniqueIDs as string)

            for targetID in uniqueIDs do
            (
                local partNode = copy node
                partNode.parent = undefined

                local facesToRemove = #{}
                for f = 1 to partNode.mesh.numfaces do
                (
                    if getFaceMatID partNode.mesh f != targetID do
                        facesToRemove[f] = true
                )
                if not facesToRemove.isEmpty do
                    meshop.deleteFaces partNode facesToRemove

                local partName = originalName + "_MatID_" + (targetID as string)
                if originalMat != undefined and classof originalMat == Multimaterial do
                (
                    if targetID <= originalMat.numsubs do
                    (
                        local subMat = originalMat[targetID]
                        if subMat != undefined and subMat.name != "" and subMat.name != undefined do
                            partName = subMat.name
                    )
                )
                partNode.name = partName
                partNode.material = undefined

                writeLog ("  Detached MatID " + targetID as string + " -> [" + partName + "] (" + partNode.mesh.numfaces as string + " faces)")
                append detachedParts partNode
            )

            delete node
            return detachedParts
        )

        -- ========== 核心遞迴處理 (由下而上) ==========

        fn processHierarchy node =
        (
            if not isValidNode node do return ()

            local childrenArr = for c in node.children collect c
            for c in childrenArr do processHierarchy c

            processedNodesCount += 1

            try (lbl_status.text = "Processing: " + node.name) catch ()
            try (pb_progress.value = ((processedNodesCount as float) / totalNodesCount) * 100.0) catch ()
            try (windows.processPostedMessages()) catch ()

            -- ==========================================
            --  區塊 1: 幾何體 (Geometry) 核心洗白與自我對齊邏輯
            -- ==========================================
            if superclassof node == GeometryClass do
            (
                local hasFaces = false
                try (
                    if node.mesh.numfaces > 0 do hasFaces = true
                ) catch (
                    hasFaces = false
                )

                if hasFaces then
                (
                    local originalParent = node.parent
                    node.parent = undefined

                    local parts = #(node)
                    local isMultiMaterial = false

                    if chk_detachByMatID.checked do
                    (
                        local tempParts = detachByMaterialID node
                        if tempParts.count > 1 do
                        (
                            parts = tempParts
                            isMultiMaterial = true
                        )
                    )

                    if not isMultiMaterial then
                    (
                        local bMin = node.min
                        local bMax = node.max
                        node.pivot = [(bMin.x + bMax.x) / 2.0, (bMin.y + bMax.y) / 2.0, bMin.z]

                        ResetXForm node
                        convertToMesh node

                        try (
                            local wn = Weighted_Normals()
                            if hasProperty wn "useSmoothingGroups" do wn.useSmoothingGroups = on
                            if hasProperty wn "hardEdgeAngle" do wn.hardEdgeAngle = on
                            if hasProperty wn "useHardEdgeAngle" do wn.useHardEdgeAngle = on
                            addModifier node wn
                        ) catch ()

                        local uvw = Uvwmap maptype:4 length:1.0 width:1.0 height:1.0
                        addModifier node uvw

                        convertToMesh node
                        if originalParent != undefined do
                        (
                            node.name = originalParent.name
                        )

                        local newPt = undefined
                        if chk_createMarker.checked do
                        (
                            local ptName = node.name
                            if originalParent != undefined do ptName = originalParent.name
                            newPt = Point centermarker:on axistripod:on cross:off box:off size:2.0 name:ptName pos:node.pivot
                            writeLog ("Created Marker for: " + ptName)
                        )

                        if originalParent != undefined do
                        (
                            if newPt != undefined do newPt.parent = originalParent
                            node.parent = originalParent
                        )
                        writeLog ("Cleaned & Aligned Geometry: " + node.name)
                    )
                    else
                    (
                        for partNode in parts do
                        (
                            local pMin = partNode.min
                            local pMax = partNode.max
                            partNode.pivot = [(pMin.x + pMax.x) / 2.0, (pMin.y + pMax.y) / 2.0, pMin.z]

                            ResetXForm partNode
                            convertToMesh partNode

                            try (
                                local wn = Weighted_Normals()
                                if hasProperty wn "useSmoothingGroups" do wn.useSmoothingGroups = on
                                if hasProperty wn "hardEdgeAngle" do wn.hardEdgeAngle = on
                                if hasProperty wn "useHardEdgeAngle" do wn.useHardEdgeAngle = on
                                addModifier partNode wn
                            ) catch ()

                            local uvw = Uvwmap maptype:4 length:1.0 width:1.0 height:1.0
                            addModifier partNode uvw
                            convertToMesh partNode
                        )

                        local grpName = if originalParent != undefined then originalParent.name else parts[1].name
                        select parts
                        local newGrp = group selection name:grpName

                        local gMin = newGrp.min
                        local gMax = newGrp.max
                        newGrp.pivot = [(gMin.x + gMax.x) / 2.0, (gMin.y + gMax.y) / 2.0, gMin.z]

                        local newPt = undefined
                        if chk_createMarker.checked do
                        (
                            newPt = Point centermarker:on axistripod:on cross:off box:off size:2.0 name:grpName pos:newGrp.pivot
                            writeLog ("Created Marker for Group: " + grpName)
                        )

                        if originalParent != undefined do
                        (
                            if newPt != undefined do newPt.parent = originalParent
                            newGrp.parent = originalParent
                        )

                        writeLog ("Multi-Mat Group Created: [" + grpName + "] with " + parts.count as string + " parts")
                    )
                )
                else
                (
                    writeLog ("Skipped Empty Shell: " + node.name)
                )
            )

            -- 安全守衛
            if not isValidNode node do return ()

            -- ==========================================
            --  區塊 2: Helper 結構全洗白與嚴格邊界框對齊
            -- ==========================================
            if superclassof node == Helper do
            (
                local myKids = for c in node.children collect c
                for c in myKids do c.parent = undefined

                local currentPos = node.pos
                node.transform = matrix3 1

                local minPt = undefined
                local maxPt = undefined
                getStrictGeomBounds myKids &minPt &maxPt

                if minPt != undefined and maxPt != undefined then
                (
                    node.pos = [(minPt.x + maxPt.x) / 2.0, (minPt.y + maxPt.y) / 2.0, minPt.z]
                )
                else
                (
                    node.pos = currentPos
                )

                for c in myKids do c.parent = node

                writeLog ("Neutralized Transform & Strict Geo Pivot set for: " + node.name)
            )
        )

        -- ========== v1.13 新增函式 ==========

        -- [v1.13] 前處理：旋轉 + 歸零
        fn preprocessTransform allRoots =
        (
            -- 1. 對所有頂層物件旋轉 (90, 0, -90)，以世界原點為旋轉中心
            local rotMat = (eulerAngles 90 0 -90) as matrix3
            for rNode in allRoots do
                rNode.transform = rNode.transform * rotMat

            writeLog "Preprocess: Applied rotation (90, 0, -90) around world origin."

            -- 2. 計算旋轉後的整體嚴格幾何邊界
            local gMinPt = undefined
            local gMaxPt = undefined
            getStrictGeomBounds allRoots &gMinPt &gMaxPt

            -- 3. 移動模型使 BBox 底部中心 (center, center, min) 對齊世界原點
            if gMinPt != undefined and gMaxPt != undefined do
            (
                local bottomCenter = [(gMinPt.x + gMaxPt.x) / 2.0, (gMinPt.y + gMaxPt.y) / 2.0, gMinPt.z]
                for rNode in allRoots do
                    rNode.pos -= bottomCenter

                writeLog ("Preprocess: Moved BBox bottom center to origin. Offset: " + (-bottomCenter) as string)
            )
        )

        -- [v1.13] Group Name 數字開頭加 Prefix
        fn addPrefixToGroupNames node prefix =
        (
            if not isValidNode node do return ()

            if isGroupHead node do
            (
                local firstChar = node.name[1]
                -- 判斷首字元是否為數字 (ASCII "0"~"9")
                if firstChar >= "0" and firstChar <= "9" do
                (
                    local oldName = node.name
                    node.name = prefix + oldName
                    writeLog ("Prefixed Group: [" + oldName + "] -> [" + node.name + "]")
                )
            )

            local kids = for c in node.children collect c
            for k in kids do addPrefixToGroupNames k prefix
        )

        -- ========== UI 瀏覽按鈕事件 ==========

        on btn_browseSrc pressed do
        (
            local folderPath = getSavePath caption:"Select Source Folder (STEP files)"
            if folderPath != undefined do edt_srcFolder.text = folderPath
        )

        on btn_browseOut pressed do
        (
            local folderPath = getSavePath caption:"Select Output Folder"
            if folderPath != undefined do edt_outFolder.text = folderPath
        )

        -- Prefix 欄位跟隨 Checkbox 啟停
        on chk_addPrefix changed state do
        (
            edt_prefix.enabled = state
        )

        -- ========== 主流程 ==========

        on btn_clean pressed do
        (
            local srcPath = edt_srcFolder.text
            local outPath = edt_outFolder.text

            if srcPath != "" and srcPath != undefined then
            (
                -- ==========================================
                --  批次模式 (Batch Mode)
                -- ==========================================

                if not doesDirectoryExist srcPath do
                (
                    messageBox "Source folder does not exist!" title:"Error"
                    return false
                )

                if outPath == "" or outPath == undefined do
                (
                    messageBox "Please specify an output folder!" title:"Error"
                    return false
                )

                makeDir outPath all:true

                -- 收集所有 STEP 檔案
                local stepFiles = getFiles (srcPath + "\\*.stp")
                join stepFiles (getFiles (srcPath + "\\*.step"))

                if stepFiles.count == 0 do
                (
                    messageBox "No STEP files (.stp, .step) found in source folder!" title:"Error"
                    return false
                )

                -- Log 初始化到輸出資料夾
                logFilePath = outPath + "\\ResetModel_Log.txt"
                writeLog "============================================"
                writeLog "=== ResetModel Batch Processing Started (v1.13) ==="
                writeLog ("Source: " + srcPath)
                writeLog ("Output: " + outPath)
                writeLog ("Files to process: " + stepFiles.count as string)
                writeLog "============================================"

                -- 緩存 UI 設定值 (resetMaxFile 後仍可存取)
                local doMarker = chk_createMarker.checked
                local doDetach = chk_detachByMatID.checked
                local doRemoveDup = chk_removeDuplicates.checked
                local doPrefix = chk_addPrefix.checked
                local prefixStr = edt_prefix.text

                local successCount = 0
                local failCount = 0

                for fileIdx = 1 to stepFiles.count do
                (
                    local filePath = stepFiles[fileIdx]
                    local fileName = getFilenameFile filePath

                    writeLog ""
                    writeLog (">>> Processing file [" + fileIdx as string + "/" + stepFiles.count as string + "]: " + fileName + " <<<")

                    try (lbl_status.text = "File " + fileIdx as string + "/" + stepFiles.count as string + ": " + fileName) catch ()
                    try (pb_progress.value = ((fileIdx - 1) as float / stepFiles.count) * 100.0) catch ()
                    try (windows.processPostedMessages()) catch ()

                    try
                    (
                        -- Phase 0: 完全重置場景
                        resetMaxFile #noPrompt

                        -- Phase 1: 匯入 STEP
                        -- 使用 #noPrompt 套用最後一次手動設定的匯入參數
                        -- (Convert to Mesh: On, Resolution: 0, Z-Up, Use Groups, 不勾選 Options)
                        writeLog ("Importing: " + filePath)
                        importFile filePath #noPrompt

                        local allRoots = for obj in objects where obj.parent == undefined collect obj
                        if allRoots.count == 0 do
                        (
                            writeLog ("WARNING: No objects imported from " + fileName + ", skipping.")
                            failCount += 1
                            continue
                        )

                        writeLog ("Import complete. " + allRoots.count as string + " root objects found.")

                        with redraw off
                        (
                            -- Phase 2: 前處理旋轉 + 歸零
                            preprocessTransform allRoots

                            -- Phase 3: 開啟所有群組
                            allRoots = for obj in objects where obj.parent == undefined collect obj
                            for rNode in allRoots do openAllGroups rNode

                            -- Phase 4: 重複 Mesh 移除
                            if doRemoveDup do
                            (
                                writeLog "--- Scanning for Duplicate Meshes ---"
                                local removedCount = removeDuplicateMeshes allRoots
                                if removedCount > 0 do
                                    writeLog ("Duplicate removal complete. " + removedCount as string + " meshes removed.")
                            )

                            -- Phase 5: 核心洗白處理
                            allRoots = for obj in objects where obj.parent == undefined collect obj
                            totalNodesCount = 0
                            for rNode in allRoots do
                                if isValidNode rNode do
                                    totalNodesCount += getNodesCount rNode
                            processedNodesCount = 0

                            for rNode in allRoots do
                                if isValidNode rNode do
                                    processHierarchy rNode

                            -- Phase 6: Group Name Prefix (數字開頭加前綴)
                            if doPrefix and prefixStr != "" do
                            (
                                writeLog "--- Adding Prefix to Numeric Group Names ---"
                                allRoots = for obj in objects where obj.parent == undefined collect obj
                                for rNode in allRoots do
                                    if isValidNode rNode do
                                        addPrefixToGroupNames rNode prefixStr
                            )
                        )

                        -- Phase 7: 儲存 .max 檔案到輸出資料夾
                        local outFile = outPath + "\\" + fileName + ".max"
                        saveMaxFile outFile
                        writeLog ("Saved: " + outFile)
                        successCount += 1
                    )
                    catch
                    (
                        writeLog ("ERROR processing [" + fileName + "]: " + (getCurrentException()))
                        failCount += 1
                    )
                )

                writeLog ""
                writeLog "============================================"
                writeLog ("=== Batch Complete: " + successCount as string + " success, " + failCount as string + " failed ===")
                writeLog "============================================"

                try (pb_progress.value = 100) catch ()
                try (lbl_status.text = "Batch Done! " + successCount as string + "/" + stepFiles.count as string + " files.") catch ()
                try (windows.processPostedMessages()) catch ()

                messageBox ("Batch processing complete!\n\nSuccess: " + successCount as string + "\nFailed: " + failCount as string + "\n\nOutput: " + outPath + "\nLog: " + logFilePath) title:"Completed"
            )
            else
            (
                -- ==========================================
                --  手動模式 (Manual Mode - 原 v1.12 行為)
                -- ==========================================
                local rootNodes = #()
                for obj in selection do
                (
                    local isTopLvl = true
                    local currNode = obj.parent
                    while currNode != undefined do
                    (
                        if currNode.isSelected do
                        (
                            isTopLvl = false
                            exit
                        )
                        currNode = currNode.parent
                    )
                    if isTopLvl do append rootNodes obj
                )

                if rootNodes.count == 0 do
                (
                    messageBox "Manual Mode: Please select at least one root node to process.\n\nOr fill in Source Folder for Batch Mode." title:"No Selection"
                    return false
                )

                totalNodesCount = 0
                for rNode in rootNodes do totalNodesCount += getNodesCount rNode

                if totalNodesCount == 0 do return false

                processedNodesCount = 0
                pb_progress.value = 0
                lbl_status.text = "Initializing (Manual Mode)..."
                windows.processPostedMessages()

                initLogFile()
                writeLog "=== ResetModel Manual Clean Started (v1.13) ==="

                with redraw off
                (
                    undo "Reset Auto Clean Model" on
                    (
                        for rNode in rootNodes do openAllGroups rNode

                        if chk_removeDuplicates.checked do
                        (
                            writeLog "--- Scanning for Duplicate Meshes ---"
                            local removedCount = removeDuplicateMeshes rootNodes
                            if removedCount > 0 do
                            (
                                totalNodesCount = 0
                                for rNode in rootNodes do
                                    if isValidNode rNode do
                                        totalNodesCount += getNodesCount rNode
                                writeLog ("Duplicate removal complete. " + removedCount as string + " duplicate meshes removed.")
                            )
                        )

                        for rNode in rootNodes do processHierarchy rNode

                        -- [v1.13] 手動模式也支援 Prefix
                        if chk_addPrefix.checked and edt_prefix.text != "" do
                        (
                            writeLog "--- Adding Prefix to Numeric Group Names ---"
                            for rNode in rootNodes do
                                if isValidNode rNode do
                                    addPrefixToGroupNames rNode edt_prefix.text
                        )
                    )
                )

                writeLog "=== ResetModel Manual Clean Completed ==="
                writeLog ""

                pb_progress.value = 100
                lbl_status.text = "Done!"
                windows.processPostedMessages()
                messageBox "All objects processed successfully!\nCheck Log for details." title:"Completed"
            )
        )

        on btn_openLog pressed do
        (
            if logFilePath == "" do initLogFile()

            local f = openFile logFilePath
            if f != undefined then
            (
                close f
                shellLaunch logFilePath ""
            )
            else
            (
                messageBox "Log file does not exist yet!" title:"Error"
            )
        )
    )

    on execute do
    (
        createDialog ResetModel_UI style:#(#style_toolwindow, #style_sysmenu, #style_titlebar)
    )
)
