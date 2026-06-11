macroScript ResetModel_v1_6
category:"ZinAllTools"
tooltip:"ResetModel v1.6: Matrix Override, Clean, Optional Marker"
(
    rollout ResetModel_UI "ResetModel v1.6" width:300 height:145
    (
        -- 介面需求
        button btn_clean "Clean & Align" width:280 height:50 pos:[10,10]
        checkbox chk_createMarker "Create Bottom Center Marker" checked:true pos:[10,65]
        label lbl_status "Ready..." pos:[10,95] width:280
        progressBar pb_progress "" pos:[10,115] width:280 height:20 value:0

        -- 定義存放總數與進度的 Rollout 級別變數
        local totalNodesCount = 0
        local processedNodesCount = 0

        -- 預先計算本次即將處理的「節點總數」(包含幾何體與 Helper)
        fn getNodesCount node =
        (
            local c = 1
            for child in node.children do
            (
                c += getNodesCount child
            )
            return c
        )

        -- 核心遞迴處理函式 (由下而上處理)
        fn processHierarchy node =
        (
            if not isValidNode node do return ()

            -- 確保由下而上：先將子節點複製為陣列，避免處理過程中層級改變導致遞迴異常
            local childrenArr = for c in node.children collect c
            for c in childrenArr do
            (
                processHierarchy c
            )

            -- 每處理完一個節點(無論是否為幾何體)，皆推進計數器與更新 UI
            processedNodesCount += 1
            
            lbl_status.text = "Processing: " + node.name
            pb_progress.value = ((processedNodesCount as float) / totalNodesCount) * 100.0
            
            -- 極度重要：強制分配 UI 線程任務，確保在 with redraw off 中也能即時重繪
            windows.processPostedMessages() 

            -- 核心幾何體洗白與重建邏輯
            if superclassof node == GeometryClass do
            (
                -- 【新增】空殼過濾機制 (Empty Shell Filter)
                -- 檢查節點的 mesh 是否有面。若無，或是發生轉發報錯則代表為極端空殼，直接跳過處理。
                local hasFaces = false
                try (
                    if node.mesh.numfaces > 0 do hasFaces = true
                ) catch (
                    hasFaces = false
                )
                
                -- 當判定是有效的實體幾何體時，才執行 Step A ~ H 核心洗白
                if hasFaces then
                (
                    local originalParent = node.parent
                    
                    -- Step A [解除連結]
                    node.parent = undefined
                    
                    -- Step B [校正軸心] (底部中心)
                    local bMin = node.min
                    local bMax = node.max
                    node.pivot = [(bMin.x + bMax.x) / 2.0, (bMin.y + bMax.y) / 2.0, bMin.z]
                    
                    -- Step C [重置變換]
                    ResetXForm node
                    convertToMesh node
                    
                    -- Step D [優化法線]
                    try (
                        local wn = Weighted_Normals()
                        -- 根據不同的 Max 版本自動匹配參數名稱並開啟 
                        if hasProperty wn "useSmoothingGroups" do wn.useSmoothingGroups = on
                        if hasProperty wn "hardEdgeAngle" do wn.hardEdgeAngle = on
                        if hasProperty wn "useHardEdgeAngle" do wn.useHardEdgeAngle = on
                        addModifier node wn
                    ) catch (
                        format "Weighted Normals modifier failed on: %\n" node.name
                    )
                    
                    -- Step E [重置 UV]
                    -- maptype 4 為 Box 模式
                    local uvw = Uvwmap maptype:4 length:1.0 width:1.0 height:1.0 
                    addModifier node uvw
                    
                    -- Step F [最終塌陷與命名]
                    convertToMesh node
                    if originalParent != undefined do
                    (
                        -- uniqueName 會確保加上序號後綴防衝突
                        node.name = uniqueName originalParent.name 
                    )
                    
                    -- Step G [條件式建立標記]
                    local newPt = undefined
                    if chk_createMarker.checked do
                    (
                        -- 讀取現在的 Pivot 座標產生，並將名稱與 originalParent 相同
                        local ptName = node.name
                        if originalParent != undefined do ptName = originalParent.name
                        
                        newPt = Point centermarker:on axistripod:on cross:off box:off size:2.0 name:ptName pos:node.pivot
                    )
                    
                    -- Step H [矩陣覆寫與恢復連結]
                    if originalParent != undefined do
                    (
                        -- 宣告陣列收集 originalParent 目前所有的子物件
                        local oldChildren = for c in originalParent.children collect c
                        
                        -- 迴圈暫時解綁現存子物件 (安全解綁)
                        for c in oldChildren do c.parent = undefined
                        
                        -- 核心矩陣覆寫: 直接清空所有的旋轉、縮放與平移，強制對齊世界坐標系
                        originalParent.transform = matrix3 1
                        
                        -- 重定位: 將洗白後的父層移至與 Mesh 一樣的底部中心
                        originalParent.pos = node.pivot
                        
                        -- 將解綁的子物件重新 parent 回 originalParent
                        for c in oldChildren do c.parent = originalParent
                        
                        -- 最後恢復處理中的節點
                        if newPt != undefined do newPt.parent = originalParent
                        node.parent = originalParent
                    )
                )
                else
                (
                    -- 空殼節點，印出提示以利 Debug 追蹤 (可選)
                    format "Skipped Empty Shell Geometry: %\n" node.name
                )
            )
        )

        on btn_clean pressed do
        (
            -- 過濾選取集合，只取得 "最上層節點" 作為遞迴起點
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
                messageBox "Please select at least one root nodes (e.g., Parent Point Helper) to process." title:"No Selection"
                return false
            )

            -- 1. 計算總進度
            totalNodesCount = 0
            for rNode in rootNodes do totalNodesCount += getNodesCount rNode
            
            if totalNodesCount == 0 do return false

            -- 初始化計數器與 UI
            processedNodesCount = 0
            pb_progress.value = 0
            lbl_status.text = "Initializing..."
            windows.processPostedMessages()

            -- 執行核心洗白(包含防護機制)
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

            -- 收尾更新
            pb_progress.value = 100
            lbl_status.text = "Done!"
            windows.processMessages()
            messageBox "All objects processed successfully!" title:"Completed"
        )
    )

    on execute do
    (
        createDialog ResetModel_UI style:#(#style_toolwindow, #style_sysmenu, #style_titlebar)
    )
)
