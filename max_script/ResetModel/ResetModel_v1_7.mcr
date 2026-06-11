macroScript ResetModel_v1_7
category:"ZinAllTools"
tooltip:"ResetModel v1.7: Matrix Override, Clean, Log System"
(
    rollout ResetModel_UI "ResetModel v1.7" width:300 height:175
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
                    
                    -- Step B [校正軸心]
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
                    
                    -- Step F [最終塌陷與命名]
                    convertToMesh node
                    if originalParent != undefined do
                    (
                        node.name = uniqueName originalParent.name 
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
                    
                    -- Step H [矩陣核彈與安全恢復]
                    if originalParent != undefined do
                    (
                        -- 收集並解除子物件
                        local oldChildren = for c in originalParent.children collect c
                        for c in oldChildren do c.parent = undefined
                        
                        -- 強制覆寫矩陣洗白父層，並移動到底部中心點
                        originalParent.transform = matrix3 1
                        originalParent.pos = node.pivot
                        
                        -- 重組原有子物件
                        for c in oldChildren do c.parent = originalParent
                        
                        -- 恢復 Mesh 與新生成的 Point Marker
                        if newPt != undefined do newPt.parent = originalParent
                        node.parent = originalParent
                    )
                    
                    writeLog ("Cleaned & Aligned Successfully: " + node.name)
                )
                else
                (
                    writeLog ("Skipped Empty Shell: " + node.name)
                )
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
            writeLog "=== ResetModel Auto Clean Started ==="

            with redraw off
            (
                undo "Reset Auto Clean Model" on
                (
                    for rNode in rootNodes do
                    (
                        processHierarchy rNode
                    )
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
