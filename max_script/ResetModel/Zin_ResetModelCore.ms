
-- ============================================================================
-- Zin_ResetModelCore (Headless Logic)
-- ============================================================================
global Zin_ResetModelCore

struct Zin_ResetModelCoreStruct
(
    logFilePath = "",
    
    fn pad0 num = ( if num < 10 then "0" + (num as string) else (num as string) ),
    fn rnd val = (floor (val * 10000.0 + 0.5)) / 10000.0,
    
    fn initLogFile =
    (
        if maxFilePath != "" then logFilePath = maxFilePath + "ResetModel_Log.txt"
        else logFilePath = sysInfo.tempdir + "ResetModel_Log.txt"
    ),
    
    fn writeLog msg =
    (
        if logFilePath == "" do initLogFile()
        local f = openFile logFilePath mode:"a"
        if f == undefined do f = createFile logFilePath
        if f != undefined do
        (
            local t = getLocalTime()
            local timeStr = "[" + (this.pad0 t[5]) + ":" + (this.pad0 t[6]) + ":" + (this.pad0 t[7]) + "]"
            format "% %
" timeStr msg to:f
            close f
        )
    ),

    fn getNodesCount node =
    (
        local c = 1
        for child in node.children do c += this.getNodesCount child
        return c
    ),

    fn openAllGroups node =
    (
        if not isValidNode node do return ()
        if isGroupHead node do
        (
            setGroupOpen node true
            this.writeLog ("Opened Group: " + node.name)
        )
        local kidsArr = for c in node.children collect c
        for k in kidsArr do this.openAllGroups k
    ),

    fn getStrictGeomBounds nodeArray &minPt &maxPt =
    (
        for n in nodeArray do
        (
            if isValidNode n do
            (
                if superclassof n == GeometryClass and classof n != TargetObject do
                (
                    local hasFaces = false
                    try ( if n.mesh.numfaces > 0 do hasFaces = true ) catch ()
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
                    this.getStrictGeomBounds kids &minPt &maxPt
                )
            )
        )
    ),

    fn collectGeometries node &geoArr =
    (
        if isValidNode node do
        (
            if superclassof node == GeometryClass and classof node != TargetObject do
            (
                local hasFaces = false
                try ( if node.mesh.numfaces > 0 do hasFaces = true ) catch ()
                if hasFaces do append geoArr node
            )
            for c in node.children do this.collectGeometries c &geoArr
        )
    ),

    fn getNodeFingerprint node =
    (
        local tf = node.transform
        local fp = (this.rnd tf.row1.x as string) + "|" + (this.rnd tf.row1.y as string) + "|" + (this.rnd tf.row1.z as string) + "|" +                    (this.rnd tf.row2.x as string) + "|" + (this.rnd tf.row2.y as string) + "|" + (this.rnd tf.row2.z as string) + "|" +                    (this.rnd tf.row3.x as string) + "|" + (this.rnd tf.row3.y as string) + "|" + (this.rnd tf.row3.z as string) + "|" +                    (this.rnd tf.row4.x as string) + "|" + (this.rnd tf.row4.y as string) + "|" + (this.rnd tf.row4.z as string) + "|" +                    (node.mesh.numfaces as string) + "|" + (node.mesh.numverts as string)
        return fp
    ),

    fn removeDuplicateMeshes rootNodesArr =
    (
        local geoArr = #()
        for rNode in rootNodesArr do this.collectGeometries rNode &geoArr
        if geoArr.count < 2 do return 0

        local fpKeys = #()
        local fpGroups = #()

        for n in geoArr do
        (
            local fp = this.getNodeFingerprint n
            local idx = findItem fpKeys fp
            if idx == 0 then
            (
                append fpKeys fp
                append fpGroups #(n)
            )
            else append fpGroups[idx] n
        )

        local nodesToDelete = #()
        for i = 1 to fpGroups.count do
        (
            local grp = fpGroups[i]
            if grp.count > 1 do
            (
                this.writeLog ("Duplicate Match Found! FP: " + fpKeys[i])
                this.writeLog ("  [KEPT] " + grp[1].name)
                for j = 2 to grp.count do
                (
                    local dNode = grp[j]
                    local pName = if dNode.parent != undefined then dNode.parent.name else "None"
                    this.writeLog ("  [DUPLICATE] Deleted: " + dNode.name + " (parent: " + pName + ")")
                    append nodesToDelete dNode
                )
            )
        )

        local removedCount = nodesToDelete.count
        if removedCount > 0 do for dNode in nodesToDelete do if isValidNode dNode do delete dNode
        return removedCount
    ),

    fn getBaseName meshName =
    (
        local name = meshName
        while name.count > 0 and (findString "0123456789" name[name.count] != undefined) do name = substring name 1 (name.count - 1)
        while name.count > 0 and (name[name.count] == "_" or name[name.count] == "-" or name[name.count] == " ") do name = substring name 1 (name.count - 1)
        if name.count == 0 do return meshName
        return name
    ),

    fn getFullPathBaseName node =
    (
        if node == undefined do return "ROOT"
        local currentBase = this.getBaseName node.name
        if node.parent != undefined then return (this.getFullPathBaseName node.parent) + "|" + currentBase
        else return currentBase
    ),

    fn getIdenticalGroupKey node baseName =
    (
        local tf = node.transform
        local sx = this.rnd (length [tf.row1.x, tf.row1.y, tf.row1.z])
        local sy = this.rnd (length [tf.row2.x, tf.row2.y, tf.row2.z])
        local sz = this.rnd (length [tf.row3.x, tf.row3.y, tf.row3.z])
        local parentKey = this.getFullPathBaseName node.parent
        local key = (toUpper baseName) + "|" + parentKey + "|" + sx as string + "|" + sy as string + "|" + sz as string + "|" + (node.mesh.numfaces as string) + "|" + (node.mesh.numverts as string)
        return key
    ),

    fn attachIdenticalMeshes rootNodesArr ignoreHidden =
    (
        local geoArr = #()
        for rNode in rootNodesArr do this.collectGeometries rNode &geoArr
        local filteredGeoArr = #()
        if ignoreHidden then ( for n in geoArr do if not n.isHiddenInVpt do append filteredGeoArr n ) else filteredGeoArr = geoArr
        if filteredGeoArr.count < 2 do return #(0, 0)

        local groupKeys = #()
        local groupNodes = #()
        local groupBaseNames = #()

        for n in filteredGeoArr do
        (
            local bName = this.getBaseName n.name
            local gKey = this.getIdenticalGroupKey n bName
            local idx = findItem groupKeys gKey
            if idx == 0 then ( append groupKeys gKey; append groupNodes #(n); append groupBaseNames bName )
            else append groupNodes[idx] n
        )

        local groupsDone = 0
        local totalMerged = 0

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
                        if targetParent != undefined do targetParent.name = this.getBaseName targetParent.name
                        
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
                                    if p != undefined and p != targetParent do appendIfUnique emptyParents p
                                ) catch ( this.writeLog ("    WARNING: Failed to attach " + grp[j].name) )
                            )
                        )
                        for p in emptyParents do if isValidNode p and p.children.count == 0 do ( this.writeLog ("    Deleted empty parent group: " + p.name); delete p )
                        targetNode.pivot = [0, 0, 0]
                        targetNode.name = baseName
                        this.writeLog ("Attached Identical Group: [" + baseName + "] (" + grp.count as string + " meshes merged)")
                    )
                )
            )
        )
        return #(groupsDone, totalMerged)
    ),

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
        this.writeLog ("Multi-Material detected on [" + originalName + "]: " + uniqueIDs.count as string + " IDs found")

        for targetID in uniqueIDs do
        (
            local partNode = copy node
            partNode.parent = undefined
            local facesToRemove = #{}
            for f = 1 to partNode.mesh.numfaces do if getFaceMatID partNode.mesh f != targetID do facesToRemove[f] = true
            if not facesToRemove.isEmpty do meshop.deleteFaces partNode facesToRemove
            
            local partName = originalName + "_MatID_" + (targetID as string)
            if originalMat != undefined and classof originalMat == Multimaterial do
            (
                if targetID <= originalMat.numsubs do
                (
                    local subMat = originalMat[targetID]
                    if subMat != undefined and subMat.name != "" and subMat.name != undefined do partName = subMat.name
                )
            )
            partNode.name = partName
            partNode.material = undefined
            this.writeLog ("  Detached MatID " + targetID as string + " -> [" + partName + "]")
            append detachedParts partNode
        )
        delete node
        return detachedParts
    ),

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
    ),

    fn processHierarchy node opts =
    (
        if not isValidNode node do return ()
        local childrenArr = for c in node.children collect c
        for c in childrenArr do this.processHierarchy c opts

        if superclassof node == GeometryClass do
        (
            local hasFaces = false
            try ( if node.mesh.numfaces > 0 do hasFaces = true ) catch ( hasFaces = false )

            if hasFaces then
            (
                local originalParent = node.parent
                node.parent = undefined
                local parts = #(node)
                local isMultiMaterial = false

                if opts.detachByMatID do
                (
                    local tempParts = this.detachByMaterialID node
                    if tempParts.count > 1 do ( parts = tempParts; isMultiMaterial = true )
                )

                if not isMultiMaterial then
                (
                    local bMin = node.min
                    local bMax = node.max
                    node.pivot = [(bMin.x + bMax.x) / 2.0, (bMin.y + bMax.y) / 2.0, bMin.z]

                    ResetXForm node
                    convertTo node Editable_Poly

                    if opts.autoFlip do
                    (
                        local vw = Vertex_Weld threshold:opts.weldDist
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
                                local normVol = this.getPolyElementVolume node elemFaces
                                if normVol < -0.001 do facesToFlip += elemFaces
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
                    if originalParent != undefined do node.name = originalParent.name

                    local newPt = undefined
                    if opts.createMarker do
                    (
                        local ptName = node.name
                        if originalParent != undefined do ptName = originalParent.name
                        newPt = Point centermarker:on axistripod:on cross:off box:off size:2.0 name:ptName pos:node.pivot
                        this.writeLog ("Created Marker for: " + ptName)
                    )

                    if originalParent != undefined do
                    (
                        if newPt != undefined do newPt.parent = originalParent
                        node.parent = originalParent
                    )
                    this.writeLog ("Cleaned & Aligned Geometry: " + node.name)
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

                        if opts.autoFlip do
                        (
                            local vw = Vertex_Weld threshold:opts.weldDist
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
                                    local normVol = this.getPolyElementVolume partNode elemFaces
                                    if normVol < -0.001 do facesToFlip += elemFaces
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
                    if opts.createMarker do
                    (
                        newPt = Point centermarker:on axistripod:on cross:off box:off size:2.0 name:grpName pos:newGrp.pivot
                        this.writeLog ("Created Marker for Group: " + grpName)
                    )

                    if originalParent != undefined do
                    (
                        if newPt != undefined do newPt.parent = originalParent
                        newGrp.parent = originalParent
                    )
                    this.writeLog ("Multi-Mat Group Created: [" + grpName + "]")
                )
            )
            else this.writeLog ("Skipped Empty Shell: " + node.name)
        )

        if not isValidNode node do return ()

        if superclassof node == Helper do
        (
            local myKids = for c in node.children collect c
            for c in myKids do c.parent = undefined
            local currentPos = node.pos
            node.transform = matrix3 1

            local minPt = undefined
            local maxPt = undefined
            this.getStrictGeomBounds myKids &minPt &maxPt

            if minPt != undefined and maxPt != undefined then node.pos = [(minPt.x + maxPt.x) / 2.0, (minPt.y + maxPt.y) / 2.0, minPt.z]
            else node.pos = currentPos

            for c in myKids do c.parent = node
            this.writeLog ("Neutralized Transform & Strict Geo Pivot set for: " + node.name)
        )
        
        -- 更新 SimReady 標籤
        try (
            if Zin_SimReadyTagDef != undefined do
            (
                local ca = custAttributes.get node Zin_SimReadyTagDef
                if ca != undefined do
                (
                    ca.pivotFixed = true
                    ca.normalsFixed = true
                    ca.uvwAssigned = true
                )
            )
        ) catch()
    ),

    fn preprocessTransform allRoots opts =
    (
        if not opts.doPreprocess do return ()

        local rx = opts.rotX
        local ry = opts.rotY
        local rz = opts.rotZ
        local rotMat = (eulerAngles rx ry rz) as matrix3
        for rNode in allRoots do rNode.transform = rNode.transform * rotMat
        this.writeLog ("Preprocess: Applied rotation (" + (rx as string) + ", " + (ry as string) + ", " + (rz as string) + ")")

        local gMinPt = undefined
        local gMaxPt = undefined
        this.getStrictGeomBounds allRoots &gMinPt &gMaxPt

        if gMinPt != undefined and gMaxPt != undefined do
        (
            local targetPos = [opts.posX, opts.posY, opts.posZ]
            local bottomCenter = [(gMinPt.x + gMaxPt.x) / 2.0, (gMinPt.y + gMaxPt.y) / 2.0, gMinPt.z]
            local offset = targetPos - bottomCenter
            for rNode in allRoots do rNode.pos += offset
            this.writeLog ("Preprocess: Moved BBox bottom center to " + (targetPos as string) + " Offset: " + (offset as string))
        )
    ),

    fn addPrefixToGroupNames node prefix =
    (
        if not isValidNode node do return ()
        if isGroupHead node do
        (
            local firstChar = node.name[1]
            if firstChar >= "0" and firstChar <= "9" do
            (
                local oldName = node.name
                node.name = prefix + oldName
                this.writeLog ("Prefixed Group: [" + oldName + "] -> [" + node.name + "]")
            )
        )
        local kids = for c in node.children collect c
        for k in kids do this.addPrefixToGroupNames k prefix
    )
)

Zin_ResetModelCore = Zin_ResetModelCoreStruct()

-- ============================================================================
-- Global Entry Point for Master Pipeline
-- ============================================================================
struct Zin_ResetModelOptions
(
    doPreprocess = true,
    rotX = 90.0, rotY = 0.0, rotZ = 90.0,
    posX = 0.0, posY = 0.0, posZ = 0.0,
    
    detachByMatID = true,
    removeDuplicates = true,
    attachIdentical = true,
    attachIgnoreHidden = true,
    createMarker = false,
    autoFlip = true,
    weldDist = 0.001,
    
    addPrefix = true,
    prefixStr = "iec_"
)

fn Zin_RunResetModelBatch nodeArray opts:(Zin_ResetModelOptions()) =
(
    local core = Zin_ResetModelCore
    core.initLogFile()
    core.writeLog "=== ResetModel Headless Batch Started ==="
    
    local allRoots = #()
    for obj in nodeArray do
    (
        local isTopLvl = true
        local currNode = obj.parent
        while currNode != undefined do
        (
            if findItem nodeArray currNode != 0 do ( isTopLvl = false; exit )
            currNode = currNode.parent
        )
        if isTopLvl do appendIfUnique allRoots obj
    )

    with redraw off
    (
        core.preprocessTransform allRoots opts
        for rNode in allRoots do core.openAllGroups rNode
        
        if opts.removeDuplicates do
        (
            core.writeLog "--- Scanning for Duplicate Meshes ---"
            local removedCount = core.removeDuplicateMeshes allRoots
            if removedCount > 0 do core.writeLog ("Duplicate removal complete. " + removedCount as string + " meshes removed.")
        )

        allRoots = for obj in objects where obj.parent == undefined collect obj
        for rNode in allRoots do if isValidNode rNode do core.processHierarchy rNode opts

        if opts.addPrefix and opts.prefixStr != "" do
        (
            core.writeLog "--- Adding Prefix to Numeric Group Names ---"
            allRoots = for obj in objects where obj.parent == undefined collect obj
            for rNode in allRoots do if isValidNode rNode do core.addPrefixToGroupNames rNode opts.prefixStr
        )
        
        if opts.attachIdentical do
        (
            core.writeLog "--- Scanning for Identical Meshes to Attach ---"
            allRoots = for obj in objects where obj.parent == undefined collect obj
            local attachResult = core.attachIdenticalMeshes allRoots opts.attachIgnoreHidden
            if attachResult[1] > 0 do core.writeLog ("Attach identical complete. " + attachResult[1] as string + " groups attached.")
        )
    )
    core.writeLog "=== ResetModel Headless Batch Completed ==="
)
