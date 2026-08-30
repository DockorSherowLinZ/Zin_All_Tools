macroScript ZinAllTools_Utility
category:"ZinAllTools"
tooltip:"Zin All Tools Integration"
icon:#("ZinAllTools", 7)
(
-- ============================================================================
-- Zin All Tools: Utilities Integration v1.0
-- Includes: Reset Model v1.2 & Batch GLB Exporter v1.2.0 launcher
-- ============================================================================

try(destroyDialog ZinAllTools) catch()

rollout ZinAllTools "Zin All Tools Integration" width:180
(
	-- ==========================================
	-- UI Setup
	-- ==========================================
	
	groupBox grp_reset "Reset Model v1.2" pos:[10, 5] width:160 height:90
	button btn_clean "Clean & Align (Selected)" width:140 height:30 pos:[20, 25]
	label lbl_reset_status "Ready..." align:#left pos:[20, 60]
	progressBar pb_reset_progress "" width:140 height:10 value:0 pos:[20, 75]
	
	groupBox grp_glb "Batch GLB Exporter" pos:[10, 105] width:160 height:70
	button btn_open_glb "Open GLB Export Panel" width:140 height:30 pos:[20, 125]
	label lbl_glb_info "Version: 1.2.0" align:#center pos:[20, 158]

	-- ==========================================
	-- [Module 1] Reset Model Core Logic
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
		lbl_reset_status.text = "Proc: " + (substring node.name 1 15)
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
	-- Event Handlers
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
			messageBox "Please select at least one root node!" title:"ZinAllTools"
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
			messageBox "All objects processed successfully!" title:"ZinAllTools"
		)
	)

	on btn_open_glb pressed do (
		macros.run "ZinAllTools" "BatchGLBExporter"
	)
)

createDialog ZinAllTools
)
