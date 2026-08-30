macroScript ResetModel_v1_21
category:"ZinAllTools"
tooltip:"ResetModel v1.21"
icon:#("ZinAllTools", 1)
(
    rollout ResetModel_UI "ResetModel v1.21" width:420 height:630
    (
    fn getPolyElementVolume polyObj elemFaces =
    (
        local minPt = [1e9, 1e9, 1e9]
        local maxPt = [-1e9, -1e9, -1e9]
        for f in elemFaces do
        (
            local faceVerts = polyOp.getFaceVerts polyObj f
            for v in faceVerts do
            (
                local pt = polyOp.getVert polyObj v
                if pt.x < minPt.x do minPt.x = pt.x
                if pt.y < minPt.y do minPt.y = pt.y
                if pt.z < minPt.z do minPt.z = pt.z
                if pt.x > maxPt.x do maxPt.x = pt.x
                if pt.y > maxPt.y do maxPt.y = pt.y
                if pt.z > maxPt.z do maxPt.z = pt.z
            )
        )
        local centerPt = (minPt + maxPt) / 2.0
        local dims = maxPt - minPt
        local maxDim = amax #(dims.x, dims.y, dims.z)
        local bboxVol = maxDim * maxDim * maxDim
        if bboxVol < 1e-12 do bboxVol = 1e-12
        local vol = 0.0
        for f in elemFaces do
        (
            local faceVerts = polyOp.getFaceVerts polyObj f
            local v1 = (polyOp.getVert polyObj faceVerts[1]) - centerPt
            for i = 2 to (faceVerts.count - 1) do
            (
                local v2 = (polyOp.getVert polyObj faceVerts[i]) - centerPt
                local v3 = (polyOp.getVert polyObj faceVerts[i+1]) - centerPt
                vol += dot v1 (cross v2 v3) / 6.0
            )
        )
        return (vol / bboxVol)
    )

        -- ========== UI 元素 ==========
        
        -- [Group 1: File Paths]
        groupBox grp_files "1. Batch Processing Paths (Leave Source empty for Manual)" pos:[10, 10] width:400 height:95
        label lbl_srcFolder "Source (STEP):" pos:[20,32]
        edittext edt_srcFolder "" pos:[100,30] width:230
        button btn_browseSrc "Browse" pos:[335,28] width:65 height:24

        label lbl_outFolder "Output (.MAX):" pos:[20,62]
        edittext edt_outFolder "" pos:[100,60] width:230
        button btn_browseOut "Browse" pos:[335,58] width:65 height:24

        -- [Group 2: Preprocess Transform]
        groupBox grp_preprocess "2. Preprocess Transform (Batch Mode Only)" pos:[10, 115] width:400 height:105
        checkbox chk_doPreprocess "Enable" checked:true pos:[20, 135]
        radiobuttons rdo_upAxis "Output Target:" labels:#("Z-Up", "Y-Up") default:1 pos:[180, 135] columns:2

        label lbl_pos "Pos:" pos:[20, 165]
        spinner spn_posX "X:" range:[-999999,999999,0] pos:[50, 165] width:65 type:#float
        spinner spn_posY "Y:" range:[-999999,999999,0] pos:[135, 165] width:65 type:#float
        spinner spn_posZ "Z:" range:[-999999,999999,0] pos:[220, 165] width:65 type:#float

        label lbl_rot "Rot:" pos:[20, 190]
        spinner spn_rotX "X:" range:[-360,360,90] pos:[50, 190] width:65 type:#float
        spinner spn_rotY "Y:" range:[-360,360,0] pos:[135, 190] width:65 type:#float
        spinner spn_rotZ "Z:" range:[-360,360,90] pos:[220, 190] width:65 type:#float

        -- [Group 3: Geometry Cleanup & Optimization]
        groupBox grp_geometry "3. Geometry Cleanup & Optimization" pos:[10, 230] width:400 height:150
        checkbox chk_detachByMatID "Auto Detach by Material ID" checked:true pos:[20,250]
        checkbox chk_removeDuplicates "Step 1: Auto Remove Duplicate Meshes" checked:true pos:[20,270]
        checkbox chk_attachIdentical "Step 2: Auto Attach Identical (Different Pos/Rot)" checked:false pos:[20,290]
        checkbox chk_attachIgnoreHidden "  L Ignore Hidden Models when Attaching" checked:true pos:[20,310]
        checkbox chk_createMarker "Create Bottom Center Marker (Point Helper)" checked:false pos:[20,330]
        checkbox chk_autoFlip "Auto Repair Inverted CAD Normals" checked:true pos:[20,350]
        spinner spn_weld "Weld Dist:" range:[0.0001, 10.0, 0.001] type:#float pos:[300, 350] width:90

        -- [Group 4: Naming & Hierarchy]
        groupBox grp_naming "4. Naming & Hierarchy" pos:[10, 390] width:400 height:50
        checkbox chk_addPrefix "Add Prefix to Numeric Group Names" checked:true pos:[20,412]
        edittext edt_prefix "Prefix:" text:"iec_" labelOnTop:false pos:[280, 410] fieldWidth:90

        -- [Execution & Status]
        button btn_clean "Clean && Align (Execute)" width:400 height:50 pos:[10, 455]
        label lbl_status "Ready..." pos:[10, 515] width:400
        progressBar pb_progress "" pos:[10, 535] width:400 height:20 value:0
        button btn_openLog "Open Log File" width:400 height:30 pos:[10, 565]

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


        -- ========== Attach Identical 核心邏輯 ==========

        -- [新增] 提取 Base Name (過濾掉尾部的數字與底線/連字號)
        -- 例如: "SCREW-M3X5_001" -> "SCREW-M3X5"
        fn getBaseName meshName =
        (
            local name = meshName
            -- 步驟 1: 移除尾部數字
            while name.count > 0 and (findString "0123456789" name[name.count] != undefined) do
                name = substring name 1 (name.count - 1)
            -- 步驟 2: 移除尾部分隔符號
            while name.count > 0 and (name[name.count] == "_" or name[name.count] == "-" or name[name.count] == " ") do
                name = substring name 1 (name.count - 1)
            
            if name.count == 0 do return meshName
            return name
        )

        -- [新增] 遞迴取得整條血脈的 Base Name，作為絕對邏輯路徑
        fn getFullPathBaseName node =
        (
            if node == undefined do return "ROOT"
            
            local currentBase = getBaseName node.name
            if node.parent != undefined then
            (
                return (getFullPathBaseName node.parent) + "|" + currentBase
            )
            else
            (
                return currentBase
            )
        )

        -- [新增] 提取 Identical 特徵指紋 (忽略 Position/Rotation)
        fn getIdenticalGroupKey node baseName =
        (
            local tf = node.transform
            -- 僅計算 Scale (XYZ 縮放比例)，忽略 Pos/Rot
            local sx = rnd (length [tf.row1.x, tf.row1.y, tf.row1.z])
            local sy = rnd (length [tf.row2.x, tf.row2.y, tf.row2.z])
            local sz = rnd (length [tf.row3.x, tf.row3.y, tf.row3.z])
            
            -- [v1.16] 使用全路徑防呆，確保只在同一個邏輯組件樹內 Attach
            local parentKey = getFullPathBaseName node.parent
            
            -- 指紋 = 大寫BaseName + FullPathParent + XYZ縮放 + 總面數 + 總頂點數
            local key = (toUpper baseName) + "|" + parentKey + "|" + \
                        sx as string + "|" + sy as string + "|" + sz as string + "|" + \
                        (node.mesh.numfaces as string) + "|" + (node.mesh.numverts as string)
            return key
        )

        -- [新增] 執行 Attach Identical
        fn attachIdenticalMeshes rootNodesArr ignoreHidden =
        (
            local geoArr = #()
            for rNode in rootNodesArr do collectGeometries rNode &geoArr

            -- [v1.17] 如果有勾選忽略隱藏，則過濾清單
            local filteredGeoArr = #()
            if ignoreHidden then
            (
                for n in geoArr do
                    if not n.isHiddenInVpt do append filteredGeoArr n
            )
            else
            (
                filteredGeoArr = geoArr
            )

            if filteredGeoArr.count < 2 do return #(0, 0)

            local groupKeys = #()
            local groupNodes = #()
            local groupBaseNames = #()

            -- 建立分組
            for n in filteredGeoArr do
            (
                local bName = getBaseName n.name
                local gKey = getIdenticalGroupKey n bName
                local idx = findItem groupKeys gKey
                
                if idx == 0 then (
                    append groupKeys gKey
                    append groupNodes #(n)
                    append groupBaseNames bName
                ) else (
                    append groupNodes[idx] n
                )
            )

            local groupsDone = 0
            local totalMerged = 0

            -- [效能核心] 關閉 Undo 緩衝與視口重繪，避免 Attach 幾百個物件時卡死
            undo off 
            (
                with redraw off 
                (
                    for i = 1 to groupNodes.count do
                    (
                        local grp = groupNodes[i]
                        if grp.count > 1 do
                        (
                            groupsDone += 1
                            local baseName = groupBaseNames[i]
                            
                            local targetNode = grp[1]
                            local targetParent = targetNode.parent
                            
                            -- [v1.16] 將保留下來的父節點，更名為乾淨的 Base Name
                            if targetParent != undefined do
                            (
                                targetParent.name = getBaseName targetParent.name
                            )
                            
                            local emptyParents = #()
                            convertToMesh targetNode
                            
                            for j = 2 to grp.count do
                            (
                                if isValidNode grp[j] do
                                (
                                    local p = grp[j].parent
                                    convertToMesh grp[j]
                                    try (
                                        meshop.attach targetNode grp[j]
                                        totalMerged += 1
                                        
                                        -- 記錄那些被拔走子物件的「其他父節點」
                                        if p != undefined and p != targetParent do
                                        (
                                            appendIfUnique emptyParents p
                                        )
                                    ) catch (
                                        writeLog ("    WARNING: Failed to attach " + grp[j].name)
                                    )
                                )
                            )
                            
                            -- [v1.16] 自動清理：如果那些父節點被掏空了，就把它們刪除
                            for p in emptyParents do
                            (
                                if isValidNode p and p.children.count == 0 do
                                (
                                    writeLog ("    Deleted empty parent group: " + p.name)
                                    delete p
                                )
                            )
                            
                            -- 核心約束 A: 將新生成的物件 Pivot 對齊世界原點 [0,0,0]
                            targetNode.pivot = [0, 0, 0]
                            
                            -- 核心約束 B: 移除數字後綴，重新命名為 Base Name
                            targetNode.name = baseName
                            
                            writeLog ("Attached Identical Group: [" + baseName + "] (" + grp.count as string + " meshes merged)")
                        )
                    )
                )
            )
            return #(groupsDone, totalMerged)
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
                        convertTo node Editable_Poly

                        if chk_autoFlip.checked do
                        (
                            local vw = Vertex_Weld threshold:spn_weld.value
                            addModifier node vw
                            collapseStack node
                            if classof node != Editable_Poly do convertTo node Editable_Poly

                            local numFaces = polyOp.getNumFaces node
                            local processedFaces = #{}
                            local facesToFlip = #{}

                            for i = 1 to numFaces do
                            (
                                if not processedFaces[i] do
                                (
                                    local elemFaces = polyOp.getElementsUsingFace node #{i}
                                    local normVol = getPolyElementVolume node elemFaces
                                    
                                    if normVol < -0.001 do
                                    (
                                        facesToFlip += elemFaces
                                    )
                                    
                                    processedFaces += elemFaces
                                )
                            )

                            if not facesToFlip.isEmpty do
                            (
                                local tempName = uniqueName "TempFlipped_"
                                polyOp.detachFaces node facesToFlip asNode:true name:tempName
                                local tempObj = getNodeByName tempName
                                
                                if isValidNode tempObj do
                                (
                                    local normMod = Normalmodifier flip:true
                                    addModifier tempObj normMod
                                    collapseStack tempObj
                                    
                                    polyOp.attach node tempObj
                                )
                            )
                        )

                        try (
                            local wn = Weighted_Normals()
                            if hasProperty wn "useSmoothingGroups" do wn.useSmoothingGroups = false
                            if hasProperty wn "useHardEdgeAngle" do wn.useHardEdgeAngle = true
                            if hasProperty wn "hardEdgeAngle" do wn.hardEdgeAngle = 30.0
                            addModifier node wn
                        ) catch ()

                        local uvw = Uvwmap maptype:4 length:0.1 width:0.1 height:0.1
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
                            convertTo partNode Editable_Poly

                            if chk_autoFlip.checked do
                            (
                                local vw = Vertex_Weld threshold:spn_weld.value
                                addModifier partNode vw
                                collapseStack partNode
                                if classof partNode != Editable_Poly do convertTo partNode Editable_Poly

                                local numFaces = polyOp.getNumFaces partNode
                                local processedFaces = #{}
                                local facesToFlip = #{}

                                for i = 1 to numFaces do
                                (
                                    if not processedFaces[i] do
                                    (
                                        local elemFaces = polyOp.getElementsUsingFace partNode #{i}
                                        local normVol = getPolyElementVolume partNode elemFaces
                                        
                                        if normVol < -0.001 do
                                        (
                                            facesToFlip += elemFaces
                                        )
                                        
                                        processedFaces += elemFaces
                                    )
                                )

                                if not facesToFlip.isEmpty do
                                (
                                    local tempName = uniqueName "TempFlipped_"
                                    polyOp.detachFaces partNode facesToFlip asNode:true name:tempName
                                    local tempObj = getNodeByName tempName
                                    
                                    if isValidNode tempObj do
                                    (
                                        local normMod = Normalmodifier flip:true
                                        addModifier tempObj normMod
                                        collapseStack tempObj
                                        
                                        polyOp.attach partNode tempObj
                                    )
                                )
                            )

                            try (
                                local wn = Weighted_Normals()
                                if hasProperty wn "useSmoothingGroups" do wn.useSmoothingGroups = false
                                if hasProperty wn "useHardEdgeAngle" do wn.useHardEdgeAngle = true
                                if hasProperty wn "hardEdgeAngle" do wn.hardEdgeAngle = 30.0
                                addModifier partNode wn
                            ) catch ()

                            local uvw = Uvwmap maptype:4 length:0.1 width:0.1 height:0.1
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

        -- [v1.18] 前處理：依據 UI 數值旋轉與位移
        fn preprocessTransform allRoots =
        (
            if not chk_doPreprocess.checked do return ()

            -- 1. 對所有頂層物件旋轉
            local rx = spn_rotX.value
            local ry = spn_rotY.value
            local rz = spn_rotZ.value
            local rotMat = (eulerAngles rx ry rz) as matrix3
            for rNode in allRoots do
                rNode.transform = rNode.transform * rotMat

            writeLog ("Preprocess: Applied rotation (" + (rx as string) + ", " + (ry as string) + ", " + (rz as string) + ")")

            -- 2. 計算旋轉後的整體嚴格幾何邊界
            local gMinPt = undefined
            local gMaxPt = undefined
            getStrictGeomBounds allRoots &gMinPt &gMaxPt

            -- 3. 移動模型使 BBox 底部中心對齊目標座標
            if gMinPt != undefined and gMaxPt != undefined do
            (
                local targetPos = [spn_posX.value, spn_posY.value, spn_posZ.value]
                local bottomCenter = [(gMinPt.x + gMaxPt.x) / 2.0, (gMinPt.y + gMaxPt.y) / 2.0, gMinPt.z]
                local offset = targetPos - bottomCenter
                for rNode in allRoots do
                    rNode.pos += offset

                writeLog ("Preprocess: Moved BBox bottom center to " + (targetPos as string) + " Offset: " + (offset as string))
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

        on rdo_upAxis changed state do
        (
            if state == 1 then -- Z-Up
            (
                spn_rotX.value = 90
                spn_rotY.value = 0
                spn_rotZ.value = 90
            )
            else -- Y-Up
            (
                spn_rotX.value = 0
                spn_rotY.value = 0
                spn_rotZ.value = 0
            )
        )

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
                writeLog "=== ResetModel Batch Processing Started (v1.20) ==="
                writeLog ("Source: " + srcPath)
                writeLog ("Output: " + outPath)
                writeLog ("Files to process: " + stepFiles.count as string)
                writeLog "============================================"

                -- 緩存 UI 設定值 (resetMaxFile 後仍可存取)
                local doMarker = chk_createMarker.checked
                local doDetach = chk_detachByMatID.checked
                local doRemoveDup = chk_removeDuplicates.checked
                local doAttachIdentical = chk_attachIdentical.checked
                local doAttachIgnoreHidden = chk_attachIgnoreHidden.checked
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
                            
                            -- [v1.15] Phase 7: Scope-based Attach Identical (移到最後執行)
                            if doAttachIdentical do
                            (
                                writeLog "--- Scanning for Identical Meshes to Attach (Scope-based) ---"
                                allRoots = for obj in objects where obj.parent == undefined collect obj
                                local attachResult = attachIdenticalMeshes allRoots doAttachIgnoreHidden
                                if attachResult[1] > 0 do
                                    writeLog ("Attach identical complete. " + attachResult[1] as string + " groups attached (" + attachResult[2] as string + " meshes merged).")
                            )
                        )

                        -- Phase 8: 儲存 .max 檔案到輸出資料夾
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
                writeLog "=== ResetModel Manual Clean Started (v1.20) ==="

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
                        
                        -- [v1.15] 移到最後執行
                        if chk_attachIdentical.checked do
                        (
                            writeLog "--- Scanning for Identical Meshes to Attach (Scope-based) ---"
                            local validRoots = #()
                            for rNode in rootNodes do if isValidNode rNode do append validRoots rNode
                            local attachResult = attachIdenticalMeshes validRoots chk_attachIgnoreHidden.checked
                            if attachResult[1] > 0 do
                            (
                                totalNodesCount = 0
                                for rNode in validRoots do
                                    if isValidNode rNode do
                                        totalNodesCount += getNodesCount rNode
                                writeLog ("Attach identical complete. " + attachResult[1] as string + " groups attached (" + attachResult[2] as string + " meshes merged).")
                            )
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
