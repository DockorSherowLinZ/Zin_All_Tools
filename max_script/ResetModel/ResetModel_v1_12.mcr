macroScript ResetModel_v1_12
category:"ZinAllTools"
tooltip:"ResetModel v1.12: Auto Detach by MatID, Strict Pivot, Clean"
(
    rollout ResetModel_UI "ResetModel v1.12" width:300 height:220
    (
        -- 介面需求
        button btn_clean "Clean & Align" width:280 height:50 pos:[10,10]
        checkbox chk_createMarker "Create Bottom Center Marker" checked:true pos:[10,65]
        checkbox chk_detachByMatID "Auto Detach by Material ID" checked:true pos:[10,85]
        checkbox chk_removeDuplicates "Auto Remove Duplicate Meshes" checked:true pos:[10,105]
        label lbl_status "Ready..." pos:[10,125] width:280
        progressBar pb_progress "" pos:[10,145] width:280 height:20 value:0
        button btn_openLog "Open Log File" width:280 height:30 pos:[10,180]

        -- 變數區
        local totalNodesCount = 0
        local processedNodesCount = 0
        local logFilePath = ""

        -- 幫助補零的函數 (用於時間格式)
        fn pad0 num =
        (
            if num < 10 then "0" + (num as string) else (num as string)
        )

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

        -- [新增起手式] 遞迴掃描並開啟群組
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

        -- [新增演算法] 嚴格幾何邊界計算函式 (排除所有 Helper 尺寸污染)
        fn getStrictGeomBounds nodeArray &minPt &maxPt =
        (
            for n in nodeArray do
            (
                if isValidNode n do
                (
                    if superclassof n == GeometryClass and classof n != TargetObject do
                    (
                        -- 僅計算非空殼的真實幾何體
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
                    
                    -- 若有子物件，遞迴深掘確保撈出最底層的 Mesh
                    if n.children.count > 0 do
                    (
                        local kids = for c in n.children collect c
                        getStrictGeomBounds kids &minPt &maxPt
                    )
                )
            )
        )

        -- [v1.12 新增] 浮點數精度工具：四捨五入至小數點後 4 位
        fn rnd val = (floor (val * 10000.0 + 0.5)) / 10000.0

        -- [v1.12 新增] 取得節點指紋：將 Transform 矩陣、面數、頂點數串接為字串
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

        -- [v1.12 新增] 遞迴收集所有有效幾何體
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

        -- [v1.12 新增] 重複偵測與移除主函式
        fn removeDuplicateMeshes rootNodesArr =
        (
            local geoArr = #()
            for rNode in rootNodesArr do collectGeometries rNode &geoArr
            
            if geoArr.count < 2 do return 0
            
            local fpKeys = #()
            local fpGroups = #()
            
            -- 建立指紋分組
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
            
            -- 對於有 2 個以上的群組，保留第一個，其餘刪除
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

        -- [v1.12 新增] 依 Material ID 自動拆分多材質模型
        -- 輸入：幾何體節點 (必須為 GeometryClass 且可轉為 mesh)
        -- 輸出：拆分後的零件陣列（若僅單一 ID 則回傳 #(原節點) 不拆分）
        fn detachByMaterialID node =
        (
            -- 先轉為 Mesh 以確保能存取 face ID
            convertToMesh node
            
            -- 1. 掃描所有面，收集使用中的 Material ID
            local numF = node.mesh.numfaces
            local uniqueIDs = #()
            for f = 1 to numF do
            (
                local mid = getFaceMatID node.mesh f
                if findItem uniqueIDs mid == 0 do append uniqueIDs mid
            )
            sort uniqueIDs

            -- 2. 若僅有 1 個 ID（或更少），不需拆分
            if uniqueIDs.count <= 1 do return #(node)

            -- 3. 取得原始材質以供命名
            local originalMat = node.material
            local originalName = node.name
            local detachedParts = #()

            writeLog ("Multi-Material detected on [" + originalName + "]: " + uniqueIDs.count as string + " IDs found: " + uniqueIDs as string)

            -- 4. 對每個 Material ID，複製原模型並刪除不屬於該 ID 的面
            for targetID in uniqueIDs do
            (
                -- 4a. 複製整個模型
                local partNode = copy node
                partNode.parent = undefined

                -- 4b. 收集不屬於目標 ID 的面並刪除
                local facesToRemove = #{}
                for f = 1 to partNode.mesh.numfaces do
                (
                    if getFaceMatID partNode.mesh f != targetID do
                        facesToRemove[f] = true
                )
                if not facesToRemove.isEmpty do
                    meshop.deleteFaces partNode facesToRemove

                -- 4c. 命名策略：優先使用子材質名稱，否則用備用格式
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

                -- 4d. 依據需求設定：僅命名，不指派材質，並將材質清空為 undefined
                partNode.material = undefined

                writeLog ("  Detached MatID " + targetID as string + " -> [" + partName + "] (" + partNode.mesh.numfaces as string + " faces)")
                append detachedParts partNode
            )

            -- 5. 刪除原始模型
            delete node

            return detachedParts
        )

        -- 核心遞迴處理 (由下而上)
        fn processHierarchy node =
        (
            if not isValidNode node do return ()

            -- 先將子節點複製為陣列，避免遞迴處理中結構改變產生異常
            local childrenArr = for c in node.children collect c
            for c in childrenArr do processHierarchy c

            processedNodesCount += 1
            
            lbl_status.text = "Processing: " + node.name
            pb_progress.value = ((processedNodesCount as float) / totalNodesCount) * 100.0
            windows.processPostedMessages() 

            -- ==========================================
            --  區塊 1: 幾何體 (Geometry) 核心洗白與自我對齊邏輯
            -- ==========================================
            if superclassof node == GeometryClass do
            (
                -- 空殼過濾機制
                local hasFaces = false
                try (
                    if node.mesh.numfaces > 0 do hasFaces = true
                ) catch (
                    hasFaces = false
                )
                
                if hasFaces then
                (
                    -- Step A [記錄父層]
                    local originalParent = node.parent
                    
                    -- 解除連結
                    node.parent = undefined
                    
                    -- [v1.12] 檢查是否啟用拆分且需要拆分
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
                        -- 原本的單材質路徑 (v1.11 行為)
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
                        -- [v1.12] 多材質路徑
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

                        -- 群組所有拆分出來的 Mesh
                        local grpName = if originalParent != undefined then originalParent.name else parts[1].name
                        select parts
                        local newGrp = group selection name:grpName

                        -- 設定 Group 軸心至底部中心
                        local gMin = newGrp.min
                        local gMax = newGrp.max
                        newGrp.pivot = [(gMin.x + gMax.x) / 2.0, (gMin.y + gMax.y) / 2.0, gMin.z]

                        -- Marker 建立於 Group
                        local newPt = undefined
                        if chk_createMarker.checked do
                        (
                            newPt = Point centermarker:on axistripod:on cross:off box:off size:2.0 name:grpName pos:newGrp.pivot
                            writeLog ("Created Marker for Group: " + grpName)
                        )

                        -- 恢復 Group 至原父層
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

            -- [v1.12 修正] 安全守衛：若 node 在區塊 1 中被多材質拆分流程刪除，
            -- 則不再繼續存取該節點，直接跳出
            if not isValidNode node do return ()

            -- ==========================================
            --  區塊 2: Helper (包含 Point 與群組頭) 結構全洗白與嚴格邊界框對齊
            -- ==========================================
            if superclassof node == Helper do
            (
                -- 1. 安全解綁：收集所有現存 children，將它們的 parent 設為 undefined
                local myKids = for c in node.children collect c
                for c in myKids do c.parent = undefined

                local currentPos = node.pos -- 紀錄原本位置防呆
                
                -- 2. 矩陣核彈：徹底洗白這個 Helper 的 Rotation 與 Scale 殘留
                node.transform = matrix3 1

                -- 3. 套用新算法計算嚴格幾何邊界框 (排除 Helper 尺寸)
                local minPt = undefined
                local maxPt = undefined
                
                getStrictGeomBounds myKids &minPt &maxPt

                -- 4. 重定位：恢復為純幾何邊界框的底部中心點
                if minPt != undefined and maxPt != undefined then
                (
                    node.pos = [(minPt.x + maxPt.x) / 2.0, (minPt.y + maxPt.y) / 2.0, minPt.z]
                )
                else
                (
                    -- 防呆機制：底下全空無實體幾何，恢復成原本的位置
                    node.pos = currentPos
                )

                -- 5. 重新連結：將 children 接回這個洗白並對齊好的 Helper
                for c in myKids do c.parent = node
                
                writeLog ("Neutralized Transform & Strict Geo Pivot set for: " + node.name)
            )
        )

        on btn_clean pressed do
        (
            local rootNodes = #()
            for obj in selection do
            (
                local isTopLvl = true
                local currNode = obj.parent
                while currNode != undefined do
                (
                    -- 也要考慮父層是否為開啟的群組
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
                messageBox "Please select at least one root nodes to process." title:"No Selection"
                return false
            )

            totalNodesCount = 0
            for rNode in rootNodes do totalNodesCount += getNodesCount rNode
            
            if totalNodesCount == 0 do return false

            processedNodesCount = 0
            pb_progress.value = 0
            lbl_status.text = "Initializing..."
            windows.processPostedMessages()

            -- 初始化 Log 並寫入開頭
            initLogFile()
            writeLog "=== ResetModel Auto Clean Started (v1.12) ==="

            with redraw off
            (
                undo "Reset Auto Clean Model" on
                (
                    -- 新增：執行群組預先解封 (掃描所有被選到的根節點樹狀結構)
                    for rNode in rootNodes do openAllGroups rNode
                    
                    -- [v1.12 新增] 前處理：重複 Mesh 偵測與移除
                    if chk_removeDuplicates.checked do
                    (
                        writeLog "--- Scanning for Duplicate Meshes ---"
                        local removedCount = removeDuplicateMeshes rootNodes
                        if removedCount > 0 do
                        (
                            -- 重新計算總節點數（刪除後數量已改變）
                            totalNodesCount = 0
                            for rNode in rootNodes do
                                if isValidNode rNode do
                                    totalNodesCount += getNodesCount rNode
                            writeLog ("Duplicate removal complete. " + removedCount as string + " duplicate meshes removed.")
                        )
                    )
                    
                    -- 開始由下而上的核心洗白處理
                    for rNode in rootNodes do processHierarchy rNode
                )
            )

            -- 寫入結尾 Log
            writeLog "=== ResetModel Auto Clean Completed ==="
            writeLog "" -- blank line

            pb_progress.value = 100
            lbl_status.text = "Done!"
            windows.processPostedMessages()
            messageBox "All objects processed successfully!\nCheck Log for details." title:"Completed"
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
