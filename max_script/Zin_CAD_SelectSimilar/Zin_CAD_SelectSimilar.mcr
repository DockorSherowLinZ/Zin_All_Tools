macroScript Zin_CAD_SelectSimilar
category:"ZinAllTools"
tooltip:"CAD Select Similar"
(
-- ============================================================================
-- CAD Select Similar & Batch Process Workflows
-- ============================================================================

rollout CAD_SelectSimilar "CAD Select Similar & Process" width:270 height:435
(
    -- ============================================================================
    -- SECTION 1: SELECTION FILTERS
    -- ============================================================================
    groupBox grp_selOptions "Selection Filters (Match ANY selected)" pos:[10, 5] width:250 height:160
    
    checkbox chk_matchBBox "Match Bounding Box Size" checked:true pos:[20, 25]
    checkbox chk_matchVertFace "Match Vertex/Face Count" checked:true pos:[20, 45]
    
    checkbox chk_matchBaseName "Match Base Name (Auto)" checked:false pos:[20, 75]
    
    checkbox chk_matchCustomName "Match Custom Name:" checked:false pos:[20, 97]
    edittext edt_customName "" text:"*Name*" pos:[135, 95] width:115 enabled:false
    
    button btn_select "1. Select Similar" width:230 height:35 pos:[20, 120]
    
    -- ============================================================================
    -- SECTION 2: BATCH PROCESS
    -- ============================================================================
    groupBox grp_batchProc "Batch Process (Applies to Selection)" pos:[10, 175] width:250 height:250
    
    label lbl_color "Target Color:" pos:[20, 200]
    colorpicker cp_wirecolor "" color:(color 128 128 128) pos:[95, 197] width:50 height:20
    checkbox chk_randomColor "Random Color" checked:false pos:[150, 200]
    
    label lbl_rename "Rename To:" pos:[20, 230]
    edittext edt_rename "" text:"" pos:[95, 228] width:145
    
    label lbl_quickNames "Quick Names:" pos:[20, 255]
    dropdownlist ddl_quickNames "" items:#("--- Custom ---", "BlackPlastic", "Aluminum", "BKMetal", "Gold", "WhitePlastic", "RedPlastic", "BluePlastic", "PCBGreenPlastic", "Sticker", "Yellow Sticker", "Paper") pos:[95, 252] width:145
    
    checkbox chk_addSuffix "Add Numeric Suffix (_01, _02)" checked:false pos:[20, 280]
    
    checkbox chk_removeMat "Remove Materials" checked:true pos:[20, 305]
    checkbox chk_removeUVW "Remove UVWs (Map Channel 1)" checked:false pos:[20, 325]
    
    button btn_process "2. Apply Batch Process" width:230 height:35 pos:[20, 380]
    
    -- ============================================================================
    -- LOGIC
    -- ============================================================================
    
    on chk_matchCustomName changed state do
    (
        edt_customName.enabled = state
        if state do chk_matchBaseName.checked = false
    )
    
    on chk_matchBaseName changed state do
    (
        if state do chk_matchCustomName.checked = false
        edt_customName.enabled = chk_matchCustomName.checked
    )
    
    on chk_randomColor changed state do
    (
        cp_wirecolor.enabled = not state
    )
    
    on ddl_quickNames selected idx do
    (
        if idx > 1 do edt_rename.text = ddl_quickNames.items[idx]
    )
    
    fn getBaseName str =
    (
        local tokens = filterString str "_"
        if tokens.count > 1 then
        (
            local lastToken = tokens[tokens.count]
            local isNumeric = true
            for i = 1 to lastToken.count do (
                local charCode = bit.charAsInt lastToken[i]
                if charCode < 48 or charCode > 57 do (isNumeric = false; exit)
            )
            if isNumeric then
            (
                local bName = tokens[1]
                for i = 2 to (tokens.count - 1) do bName += "_" + tokens[i]
                return bName
            )
            else return str
        )
        else return str
    )
    
    fn padZero num =
    (
        local s = num as string
        if s.count < 2 then return ("0" + s)
        else return s
    )
    
    struct Fingerprint ( pattern, bbox, faces, verts )

    on btn_select pressed do
    (
        local matchedNodes = #()
        local fingerprints = #()
        
        -- If user checks any of the reference-based options, they MUST select at least one object
        if chk_matchBaseName.checked or chk_matchBBox.checked or chk_matchVertFace.checked do
        (
            if selection.count == 0 then ( messageBox "Please select at least one object as a reference!" title:"Error"; return () )
            
            for obj in selection do
            (
                local fp = Fingerprint()
                if chk_matchBaseName.checked do fp.pattern = (getBaseName obj.name) + "*"
                if chk_matchBBox.checked do fp.bbox = (obj.max - obj.min)
                if chk_matchVertFace.checked do
                (
                    local counts = GetTriMeshFaceCount obj
                    if counts != undefined then ( fp.faces = counts[1]; fp.verts = counts[2] )
                    else ( fp.faces = 0; fp.verts = 0 )
                )
                append fingerprints fp
            )
        )
        
        -- If ALL checkboxes are unchecked, we don't want to just select the entire scene, warn the user.
        if not chk_matchBaseName.checked and not chk_matchCustomName.checked and not chk_matchBBox.checked and not chk_matchVertFace.checked do
        (
            messageBox "Please enable at least one selection filter!" title:"Error"
            return ()
        )
        
        -- Scan scene
        for obj in objects do
        (
            -- Safety check: ignore hidden, ignore groups, ONLY SELECT GEOMETRY
            if not obj.isHidden and not obj.isHiddenInVpt and superclassof obj == GeometryClass do
            (
                local isMatch = false
                
                -- Global filter: Custom Name (if enabled, object MUST pass this first)
                local passCustom = true
                if chk_matchCustomName.checked do
                (
                    if not (matchPattern obj.name pattern:edt_customName.text ignoreCase:true) do passCustom = false
                )
                
                if passCustom do
                (
                    if fingerprints.count > 0 then
                    (
                        local objBBox = obj.max - obj.min
                        local objCounts = GetTriMeshFaceCount obj
                        if objCounts == undefined do objCounts = #(0,0)
                        
                        -- Match against any of the selected reference fingerprints
                        for fp in fingerprints do
                        (
                            local matchThisFp = true
                            
                            if chk_matchBaseName.checked and not (matchPattern obj.name pattern:fp.pattern ignoreCase:true) do matchThisFp = false
                            
                            if matchThisFp and chk_matchBBox.checked do
                            (
                                if (abs(objBBox.x - fp.bbox.x) > 0.01 or abs(objBBox.y - fp.bbox.y) > 0.01 or abs(objBBox.z - fp.bbox.z) > 0.01) do matchThisFp = false
                            )
                            
                            if matchThisFp and chk_matchVertFace.checked do
                            (
                                if (objCounts[1] != fp.faces or objCounts[2] != fp.verts) do matchThisFp = false
                            )
                            
                            if matchThisFp do ( isMatch = true; exit )
                        )
                    )
                    else
                    (
                        -- If fingerprints is empty, it means only Custom Name is checked, and we already passed it.
                        isMatch = true
                    )
                )
                
                if isMatch do append matchedNodes obj
            )
        )
        
        if matchedNodes.count > 0 then
        (
            select matchedNodes
            print ("CAD Select Similar: Successfully selected " + matchedNodes.count as string + " geometry objects.")
        )
        else ( messageBox "No matching geometry objects found in the scene!" title:"Result" )
    )
    
    on btn_process pressed do
    (
        if selection.count == 0 then
        (
            messageBox "Please select objects to process!" title:"Error"
            return ()
        )
        
        local selArray = getCurrentSelection()
        local rName = edt_rename.text
        local rColor = cp_wirecolor.color
        
        undo "Batch Process" on
        (
            for i = 1 to selArray.count do
            (
                local obj = selArray[i]
                
                -- Modify Color
                if chk_randomColor.checked then
                    obj.wirecolor = color (random 0 255) (random 0 255) (random 0 255)
                else
                    obj.wirecolor = rColor
                
                -- Rename 
                if rName != "" do
                (
                    if chk_addSuffix.checked then
                        obj.name = rName + "_" + padZero i
                    else
                        obj.name = rName
                )
                
                -- Remove Material
                if chk_removeMat.checked do
                (
                    obj.material = undefined
                )
                
                -- Remove UVW (Clear Map Channel 1)
                if chk_removeUVW.checked do
                (
                    try ( channelInfo.ClearChannel obj 1 ) catch ()
                )
            )
        )
        
        messageBox ("Successfully processed " + selArray.count as string + " objects!") title:"Success"
    )
)
createDialog CAD_SelectSimilar
)
