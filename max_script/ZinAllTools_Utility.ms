-- Zin All Tools: Utilities Integration v1.0
-- 包含: Reset Model v1.2 & Batch GLB Exporter v1.2.0

utility ZinAllTools "Zin All Tools"
(
	-- ==========================================
	-- UI 介面設定 (寬度適配側邊欄)
	-- ==========================================
	
	group "Reset Model v1.2" (
		button btn_clean "Clean & Align (Selected)" width:140 height:40
		label lbl_reset_status "Ready..." align:#left
		progressBar pb_reset_progress "" width:140 height:10 value:0
	)
	
	group "Batch GLB Exporter" (
		button btn_open_glb "Open GLB Export Panel" width:140 height:30
		label lbl_glb_info "Version: 1.2.0" align:#center
	)

	-- ==========================================
	-- [模組 1] Reset Model 核心邏輯
	-- ==========================================
	local totalNodesCount = 0
	local processedNodesCount = 0

	fn getNodesCount node = (
		local c = 1
		for child in node.children do c += getNodesCount child
		return c
	)

	fn processHierarchy node = (
		if not isValidNode node do return ()
		local childrenArr = for c in node.children collect c
		for c in childrenArr do processHierarchy c
		
		processedNodesCount += 1
		lbl_reset_status.text = "Proc: " + (substring node.name 1 15) -- 截短名稱避免 UI 溢出
		pb_reset_progress.value = ((processedNodesCount as float) / totalNodesCount) * 100.0
		windows.processPostedMessages() 

		if superclassof node == GeometryClass do (
			local hasFaces = false
			try (if node.mesh.numfaces > 0 do hasFaces = true) catch (hasFaces = false)
			
			if hasFaces then (
				local originalParent = node.parent
				node.parent = undefined
				local bMin = node.min, bMax = node.max
				node.pivot = [(bMin.x + bMax.x) / 2.0, (bMin.y + bMax.y) / 2.0, bMin.z]
				ResetXForm node
				convertToMesh node
				try (
					local wn = Weighted_Normals()
					if hasProperty wn "useSmoothingGroups" do wn.useSmoothingGroups = on
					addModifier node wn
				) catch ()
				local uvw = Uvwmap maptype:4 length:1.0 width:1.0 height:1.0 
				addModifier node uvw
				convertToMesh node
				if originalParent != undefined do node.name = uniqueName originalParent.name 
				local ptName = if originalParent != undefined then originalParent.name else node.name
				local newPt = Point centermarker:on axistripod:on cross:off box:off size:2.0 name:ptName pos:node.pivot
				if originalParent != undefined do (
					newPt.parent = originalParent
					node.parent = originalParent 
				)
			)
		)
	)

	-- ==========================================
	-- 事件處理 (Event Handlers)
	-- ==========================================

	on btn_clean pressed do (
		local rootNodes = #()
		for obj in selection do (
			local isTopLvl = true
			local currNode = obj.parent
			while currNode != undefined do (
				if currNode.isSelected do ( isTopLvl = false; exit )
				currNode = currNode.parent
			)
			if isTopLvl do append rootNodes obj
		)

		if rootNodes.count == 0 then (
			messageBox "請選擇至少一個根節點！" title:"ZinTools"
		) else (
			totalNodesCount = 0
			for rNode in rootNodes do totalNodesCount += getNodesCount rNode
			processedNodesCount = 0
			with redraw off (
				undo "Reset Auto Clean" on (
					for rNode in rootNodes do processHierarchy rNode
				)
			)
			lbl_reset_status.text = "Done!"
			pb_reset_progress.value = 100
			messageBox "所有物件處理完成！" title:"ZinTools"
		)
	)

	-- GLB Exporter 因為 UI 較大，建議維持彈出視窗
	on btn_open_glb pressed do (
		macros.run "ZinAllTools" "BatchGLBExporter"
	)
)