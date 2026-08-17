macroScript Zin_CAD_SelectSimilar
category:"ZinAllTools"
tooltip:"CAD Select Similar"
(
-- ============================================================================
-- CAD Select Similar & Batch Process Workflows
-- With Quick Names CRUD + INI/JSON Dual Output for USD Composer Pipeline
-- ============================================================================

-- Data directory path (persistent storage for Quick Names)
global ZinCAD_DataDir = @"D:\Inventec\Zin_All_Tools\max_script\Zin_CAD_SelectSimilar\"
global ZinCAD_IniFile = ZinCAD_DataDir + "QuickNames.ini"
global ZinCAD_JsonFile = ZinCAD_DataDir + "QuickNames.json"
global ZinCAD_UsdLibrary = @"D:\Inventec\DigitalTwin\Library\Material_Collects.usd"

-- Default Quick Names list (used on first run)
global ZinCAD_DefaultNames = #("BlackPlastic", "Aluminum", "BKMetal", "Gold", "WhitePlastic", "RedPlastic", "BluePlastic", "PCBGreenPlastic", "Sticker", "Yellow Sticker", "Paper")

-- ============================================================================
-- FILE I/O FUNCTIONS (defined outside rollout for global access)
-- ============================================================================

-- Ensure data directory exists
fn ZinCAD_ensureDataDir = (
    makeDir ZinCAD_DataDir all:true
)

-- Load Quick Names from INI file; returns string array
fn ZinCAD_loadFromIni = (
    local names = #()
    if doesFileExist ZinCAD_IniFile then (
        local count = getINISetting ZinCAD_IniFile "QuickNames" "Count"
        if count != "" then (
            local n = count as integer
            for i = 1 to n do (
                local val = getINISetting ZinCAD_IniFile "QuickNames" ("Name" + i as string)
                if val != "" do append names val
            )
        )
    )
    return names
)

-- Save Quick Names array to INI file
fn ZinCAD_saveToIni namesArr = (
    ZinCAD_ensureDataDir()
    -- Clear old file by overwriting
    setINISetting ZinCAD_IniFile "QuickNames" "Count" (namesArr.count as string)
    for i = 1 to namesArr.count do (
        setINISetting ZinCAD_IniFile "QuickNames" ("Name" + i as string) namesArr[i]
    )
)

-- Read existing JSON and extract previously saved mdl paths (preserve user edits)
fn ZinCAD_readExistingJsonPaths = (
    local pathMap = #()  -- array of #(name, path, desc) triples
    if doesFileExist ZinCAD_JsonFile then (
        local f = openFile ZinCAD_JsonFile mode:"r"
        if f != undefined then (
            local content = ""
            while not (eof f) do content += readLine f + "\n"
            close f

            -- Simple JSON parser: find "key": { "material_prim_path": "value" }
            -- We look for patterns like:  "SomeName": {
            --                                "material_prim_path": "/some/path",
            --                                "description": "some desc"
            local inMappings = false
            local currentName = ""
            local currentPath = ""
            local currentDesc = ""
            local lines = filterString content "\n"

            for line in lines do (
                local trimmed = trimLeft (trimRight line)

                -- Detect MaterialMappings block
                if findString trimmed "\"MaterialMappings\"" != undefined do inMappings = true

                if inMappings do (
                    -- Look for a key like "BlackPlastic": {
                    local colonBrace = findString trimmed ": {"
                    if colonBrace != undefined and findString trimmed "\"MaterialMappings\"" == undefined do (
                        -- Extract the key name between quotes
                        local q1 = findString trimmed "\""
                        if q1 != undefined do (
                            local sub = substring trimmed (q1 + 1) -1
                            local q2 = findString sub "\""
                            if q2 != undefined do (
                                currentName = substring sub 1 (q2 - 1)
                                currentPath = ""
                                currentDesc = ""
                            )
                        )
                    )

                    -- Look for material_prim_path value
                    if findString trimmed "\"material_prim_path\"" != undefined and currentName != "" do (
                        local cPos = findString trimmed ": \""
                        if cPos != undefined do (
                            local valStart = cPos + 3
                            local sub = substring trimmed valStart -1
                            local qEnd = findString sub "\""
                            if qEnd != undefined do currentPath = substring sub 1 (qEnd - 1)
                        )
                    )

                    -- Look for description value
                    if findString trimmed "\"description\"" != undefined and currentName != "" do (
                        local cPos = findString trimmed ": \""
                        if cPos != undefined do (
                            local valStart = cPos + 3
                            local sub = substring trimmed valStart -1
                            local qEnd = findString sub "\""
                            if qEnd != undefined do currentDesc = substring sub 1 (qEnd - 1)
                        )
                    )

                    -- Closing brace for this entry
                    if trimmed == "}" or trimmed == "}," do (
                        if currentName != "" do (
                            append pathMap #(currentName, currentPath, currentDesc)
                            currentName = ""
                        )
                    )
                )
            )
        )
    )
    return pathMap
)

-- Save Quick Names array to JSON with USD Material Library mapping
fn ZinCAD_saveToJson namesArr = (
    ZinCAD_ensureDataDir()

    -- Read existing paths to preserve user-edited mdl_path values
    local existingPaths = ZinCAD_readExistingJsonPaths()

    -- Helper: find existing path for a given name
    fn findExistingPath existPaths nameStr = (
        for entry in existPaths do (
            if entry[1] == nameStr do return entry[2]
        )
        return ""
    )

    -- Helper: find existing description for a given name
    fn findExistingDesc existPaths nameStr = (
        for entry in existPaths do (
            if entry[1] == nameStr do return entry[3]
        )
        return "Auto-generated from 3ds Max CAD Select Similar"
    )

    -- Escape backslashes for JSON output
    local usdPath = ""
    for i = 1 to ZinCAD_UsdLibrary.count do (
        local c = ZinCAD_UsdLibrary[i]
        if c == "\\" then usdPath += "/"
        else usdPath += c
    )

    local f = createFile ZinCAD_JsonFile
    if f != undefined then (
        format "{\n" to:f
        format "  \"USD_Material_Library\": \"%\",\n" usdPath to:f
        format "  \"MaterialMappings\": {\n" to:f

        for i = 1 to namesArr.count do (
            local mName = namesArr[i]
            local mPath = findExistingPath existingPaths mName
            local mDesc = findExistingDesc existingPaths mName
            local comma = if i < namesArr.count then "," else ""

            format "    \"%\": {\n" mName to:f
            format "      \"material_prim_path\": \"%\",\n" mPath to:f
            format "      \"description\": \"%\"\n" mDesc to:f
            format "    }%\n" comma to:f
        )

        format "  }\n" to:f
        format "}\n" to:f
        close f
    )
)

-- Master save function: writes both INI and JSON
fn ZinCAD_saveAll namesArr = (
    ZinCAD_saveToIni namesArr
    ZinCAD_saveToJson namesArr
)

-- Initialize: load from INI or create defaults
fn ZinCAD_initQuickNames = (
    ZinCAD_ensureDataDir()
    local names = ZinCAD_loadFromIni()
    if names.count == 0 then (
        -- First run: use defaults and save
        names = ZinCAD_DefaultNames
        ZinCAD_saveAll names
    )
    return names
)

fn ZinCAD_getUserInput prompt:"" title:"Input" default:"" = (
    rollout ro_Input title (
        label lbl_prompt "" align:#left offset:[0,5] width:230
        edittext edt_input "" text:"" align:#left offset:[-4,5] width:230
        button btn_ok "OK" width:70 across:2 align:#center offset:[0,10]
        button btn_cancel "Cancel" width:70 align:#center offset:[0,10]
        
        local result = undefined
        
        on ro_Input open do (
            lbl_prompt.text = prompt
            edt_input.text = default
            setFocus edt_input
        )
        on btn_ok pressed do ( result = edt_input.text; destroyDialog ro_Input )
        on btn_cancel pressed do ( destroyDialog ro_Input )
        on edt_input entered txt do ( result = txt; destroyDialog ro_Input )
    )
    createDialog ro_Input 250 110 modal:true
    return ro_Input.result
)


rollout CAD_SelectSimilar "CAD Select Similar & Process" width:270 height:490
(
    -- ============================================================================
    -- SECTION 1: SELECTION FILTERS
    -- ============================================================================
    groupBox grp_selOptions "Selection Filters (Match ANY selected)" pos:[10, 5] width:250 height:185
    
    label lbl_objType "Target Type:" pos:[20, 25]
    radiobuttons rdo_objType labels:#("Geometry", "Helper") pos:[90, 25] default:1
    
    checkbox chk_matchBBox "Match Bounding Box Size" checked:true pos:[20, 50]
    checkbox chk_matchVertFace "Match Vertex/Face Count" checked:true pos:[20, 70]
    
    checkbox chk_matchBaseName "Match Base Name (Auto)" checked:false pos:[20, 100]
    
    checkbox chk_matchCustomName "Match Custom Name:" checked:false pos:[20, 122]
    edittext edt_customName "" text:"*Name*" pos:[135, 120] width:115 enabled:false
    
    button btn_select "1. Select Similar" width:230 height:35 pos:[20, 145]
    
    -- ============================================================================
    -- SECTION 2: BATCH PROCESS
    -- ============================================================================
    groupBox grp_batchProc "Batch Process (Applies to Selection)" pos:[10, 200] width:250 height:280
    
    label lbl_color "Target Color:" pos:[20, 225]
    colorpicker cp_wirecolor "" color:(color 128 128 128) pos:[95, 222] width:50 height:20
    checkbox chk_randomColor "Random Color" checked:false pos:[150, 225]
    
    label lbl_rename "Rename To:" pos:[20, 255]
    edittext edt_rename "" text:"" pos:[95, 253] width:145
    
    label lbl_quickNames "Quick Names:" pos:[20, 280]
    dropdownlist ddl_quickNames "" items:#("--- Custom ---") pos:[95, 277] width:145
    
    button btn_addName "+" width:25 height:20 pos:[95, 302] tooltip:"Add a new Quick Name"
    button btn_editName "E" width:25 height:20 pos:[122, 302] tooltip:"Edit selected Quick Name"
    button btn_deleteName "-" width:25 height:20 pos:[149, 302] tooltip:"Delete selected Quick Name"
    
    checkbox chk_addSuffix "Add Numeric Suffix (_01, _02)" checked:false pos:[20, 330]
    
    checkbox chk_removeMat "Remove Materials" checked:true pos:[20, 355]
    checkbox chk_removeUVW "Remove UVWs (Map Channel 1)" checked:false pos:[20, 375]
    
    button btn_process "2. Apply Batch Process" width:230 height:35 pos:[20, 435]
    
    -- ============================================================================
    -- LOGIC
    -- ============================================================================
    
    -- Refresh dropdown from the current INI data
    fn refreshDropdown = (
        local names = ZinCAD_loadFromIni()
        local items = #("--- Custom ---")
        for n in names do append items n
        ddl_quickNames.items = items
        ddl_quickNames.selection = 1
    )
    
    on CAD_SelectSimilar open do
    (
        -- Initialize Quick Names on rollout open
        ZinCAD_initQuickNames()
        refreshDropdown()
    )
    
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
    
    -- ADD: Prompt user for a new name and append it
    on btn_addName pressed do
    (
        local newName = ZinCAD_getUserInput prompt:"Enter new Quick Name:" title:"Add Quick Name"
        if newName != undefined and classof newName == String and newName != "" then (
            local names = ZinCAD_loadFromIni()
            -- Check for duplicates
            local isDuplicate = false
            for n in names do if n == newName do (isDuplicate = true; exit)
            if isDuplicate then (
                messageBox ("\"" + newName + "\" already exists!") title:"Duplicate"
            ) else (
                append names newName
                ZinCAD_saveAll names
                refreshDropdown()
                -- Select the newly added item
                ddl_quickNames.selection = ddl_quickNames.items.count
                edt_rename.text = newName
                messageBox ("\"" + newName + "\" added successfully!") title:"Success"
            )
        )
    )
    
    -- EDIT: Modify the currently selected Quick Name
    on btn_editName pressed do
    (
        local idx = ddl_quickNames.selection
        if idx <= 1 then (
            messageBox "Cannot edit '--- Custom ---'.\nPlease select a Quick Name to edit." title:"Info"
            return ()
        )
        local oldName = ddl_quickNames.items[idx]
        local newName = ZinCAD_getUserInput prompt:("Rename \"" + oldName + "\" to:") title:"Edit Quick Name" default:oldName
        if newName != undefined and classof newName == String and newName != "" and newName != oldName then (
            local names = ZinCAD_loadFromIni()
            -- Find and replace
            local dataIdx = idx - 1  -- offset for "--- Custom ---"
            if dataIdx >= 1 and dataIdx <= names.count do (
                names[dataIdx] = newName
                ZinCAD_saveAll names
                refreshDropdown()
                ddl_quickNames.selection = idx
                edt_rename.text = newName
                messageBox ("Renamed to \"" + newName + "\" successfully!") title:"Success"
            )
        )
    )
    
    -- DELETE: Remove the currently selected Quick Name
    on btn_deleteName pressed do
    (
        local idx = ddl_quickNames.selection
        if idx <= 1 then (
            messageBox "Cannot delete '--- Custom ---'.\nPlease select a Quick Name to delete." title:"Info"
            return ()
        )
        local delName = ddl_quickNames.items[idx]
        if queryBox ("Delete \"" + delName + "\" from Quick Names?") title:"Confirm Delete" then (
            local names = ZinCAD_loadFromIni()
            local dataIdx = idx - 1
            if dataIdx >= 1 and dataIdx <= names.count do (
                deleteItem names dataIdx
                ZinCAD_saveAll names
                refreshDropdown()
                messageBox ("\"" + delName + "\" deleted successfully!") title:"Success"
            )
        )
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
            local isTypeMatch = false
            if rdo_objType.state == 1 then
                isTypeMatch = (superclassof obj == GeometryClass)
            else
                isTypeMatch = (superclassof obj == helper)
                
            -- Safety check: ignore hidden, MUST match selected Object Type
            if not obj.isHidden and not obj.isHiddenInVpt and isTypeMatch do
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
            local typeName = if rdo_objType.state == 1 then "geometry" else "helper"
            print ("CAD Select Similar: Successfully selected " + matchedNodes.count as string + " " + typeName + " objects.")
        )
        else ( messageBox "No matching objects found in the scene!" title:"Result" )
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
