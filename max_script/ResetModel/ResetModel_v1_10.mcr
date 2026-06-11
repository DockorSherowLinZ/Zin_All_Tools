macroScript ResetModel_v1_10
category:"ZinAllTools"
tooltip:"ResetModel v1.10: Collective Pivot, Group Unlock, Exact Naming"
(
    rollout ResetModel_UI "ResetModel v1.10" width:300 height:175
    (
        -- 介面需求
        button btn_clean "Clean & Align" width:280 height:50 pos:[10,10]
        checkbox chk_createMarker "Create Bottom Center Marker" checked:true pos:[10,65]
        label lbl_status "Ready..." pos:[10,85] width:280
        progressBar pb_progress "" pos:[10,105] width:280 height:20 value:0
        button btn_openLog "Open Log File" width:280 height:30 pos:[10,135]

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
                    
                    -- Step B [校正軸心] (Geometry 僅對齊自我邊界框)
                    local bMin = node.min
                    local bMax = node.max
                    node.pivot = [(bMin.x + bMax.x) / 2.0, (bMin.y + bMax.y) / 2.0, bMin.z]
                    
                    -- Step C [重置變換]
                    ResetXForm node
                    convertToMesh node
                    
                    -- Step D [優化法線]
                    try (
                        local wn = Weighted_Normals()
                        if hasProperty wn "useSmoothingGroups" do wn.useSmoothingGroups = on
                        if hasProperty wn "hardEdgeAngle" do wn.hardEdgeAngle = on
                        if hasProperty wn "useHardEdgeAngle" do wn.useHardEdgeAngle = on
                        addModifier node wn
                    ) catch ()
                    
                    -- Step E [重置 UV]
                    local uvw = Uvwmap maptype:4 length:1.0 width:1.0 height:1.0 
                    addModifier node uvw
                    
                    -- Step F [最終塌陷與精準命名]
                    convertToMesh node
                    if originalParent != undefined do
                    (
                        -- 強制同名以符合 BOM 料號
                        node.name = originalParent.name 
                    )
                    
                    -- Step G [條件式建立標記]
                    local newPt = undefined
                    if chk_createMarker.checked do
                    (
                        local ptName = node.name
                        if originalParent != undefined do ptName = originalParent.name
                        
                        newPt = Point centermarker:on axistripod:on cross:off box:off size:2.0 name:ptName pos:node.pivot
                        
                        writeLog ("Created Marker for: " + ptName)
                    )
                    
                    -- Step H 徹底精簡化 (移除所有對 originalParent 的移動與矩陣覆寫)
                    -- 只單純恢復 Mesh 與 Point Marker 到原始結構底下
                    if originalParent != undefined do
                    (
                        if newPt != undefined do newPt.parent = originalParent
                        node.parent = originalParent
                    )
                    
                    writeLog ("Cleaned & Aligned Geometry: " + node.name)
                )
                else
                (
                    writeLog ("Skipped Empty Shell: " + node.name)
                )
            )

            -- ==========================================
            --  區塊 2: Helper (包含 Point) 結構全洗白與整體邊界框對齊
            -- ==========================================
            if superclassof node == Helper do
            (
                -- 1. 安全解綁：收集所有現存 children，將它們的 parent 設為 undefined
                local myKids = for c in node.children collect c
                for c in myKids do c.parent = undefined

                -- 2. 計算整體邊界框 (Collective Bounds)
                local bboxMin = undefined
                local bboxMax = undefined
                local currentPos = node.pos -- 紀錄原本位置防呆
                
                for c in myKids do
                (
                    if isValidNode c do
                    (
                        local cMin = c.min
                        local cMax = c.max
                        
                        if bboxMin == undefined then
                        (
                            bboxMin = [cMin.x, cMin.y, cMin.z]
                            bboxMax = [cMax.x, cMax.y, cMax.z]
                        )
                        else
                        (
                            if cMin.x < bboxMin.x do bboxMin.x = cMin.x
                            if cMin.y < bboxMin.y do bboxMin.y = cMin.y
                            if cMin.z < bboxMin.z do bboxMin.z = cMin.z
                            
                            if cMax.x > bboxMax.x do bboxMax.x = cMax.x
                            if cMax.y > bboxMax.y do bboxMax.y = cMax.y
                            if cMax.z > bboxMax.z do bboxMax.z = cMax.z
                        )
                    )
                )

                -- 3. 矩陣核彈：徹底洗白這個 Helper 的 Rotation 與 Scale 殘留
                node.transform = matrix3 1

                -- 4. 恢復為整體邊界框的底部中心點
                if bboxMin != undefined and bboxMax != undefined then
                (
                    node.pos = [(bboxMin.x + bboxMax.x) / 2.0, (bboxMin.y + bboxMax.y) / 2.0, bboxMin.z]
                )
                else
                (
                    -- 防呆機制：如果是空資料夾，矩陣核彈後恢復成原本的位置
                    node.pos = currentPos
                )

                -- 5. 重新連結：將 children 接回這個洗白並對齊好的 Helper
                for c in myKids do c.parent = node
                
                writeLog ("Neutralized Transform & Computed Collective Pivot for: " + node.name)
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
            writeLog "=== ResetModel Auto Clean Started (v1.10) ==="

            with redraw off
            (
                undo "Reset Auto Clean Model" on
                (
                    -- 新增：執行群組預先解封 (掃描所有被選到的根節點樹狀結構)
                    for rNode in rootNodes do openAllGroups rNode
                    
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
