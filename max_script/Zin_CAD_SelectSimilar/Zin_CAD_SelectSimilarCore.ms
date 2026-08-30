
-- ============================================================================
-- Zin_SelectSimilarCore (Headless Logic)
-- ============================================================================
global Zin_SelectSimilarCore

struct Zin_SelectSimilarCoreStruct
(
    fn padZero num =
    (
        local s = num as string
        if s.count < 2 then return ("0" + s) else return s
    ),
    
    fn getBaseName str =
    (
        local tokens = filterString str "_"
        if tokens.count > 1 then
        (
            local lastToken = tokens[tokens.count]
            local isNumeric = true
            for i = 1 to lastToken.count do
            (
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
)

Zin_SelectSimilarCore = Zin_SelectSimilarCoreStruct()

struct Zin_SelectSimilarOptions
(
    -- Filter options
    objType = 1, -- 1: Geometry, 2: Helper
    matchBBox = true,
    matchVertFace = true,
    matchBaseName = false,
    matchCustomName = false,
    customName = "*Name*",
    
    -- Processing options
    targetColor = (color 128 128 128),
    randomColor = false,
    renameTo = "",
    addSuffix = false,
    removeMat = true,
    removeUVW = false
)

struct Zin_Fingerprint ( pattern, bbox, faces, verts )

fn Zin_RunSelectSimilarBatch refNodes opts:(Zin_SelectSimilarOptions()) =
(
    local core = Zin_SelectSimilarCore
    local matchedNodes = #()
    local fingerprints = #()
    
    if opts.matchBaseName or opts.matchBBox or opts.matchVertFace do
    (
        if refNodes.count == 0 do return #()
        for obj in refNodes do
        (
            if isValidNode obj do
            (
                local fp = Zin_Fingerprint()
                if opts.matchBaseName do fp.pattern = (core.getBaseName obj.name) + "*"
                if opts.matchBBox do fp.bbox = (obj.max - obj.min)
                if opts.matchVertFace do
                (
                    local counts = GetTriMeshFaceCount obj
                    if counts != undefined then ( fp.faces = counts[1]; fp.verts = counts[2] )
                    else ( fp.faces = 0; fp.verts = 0 )
                )
                append fingerprints fp
            )
        )
    )
    
    for obj in objects do
    (
        if isValidNode obj do
        (
            local isTypeMatch = false
            if opts.objType == 1 then isTypeMatch = (superclassof obj == GeometryClass)
            else isTypeMatch = (superclassof obj == helper)
            
            if not obj.isHidden and not obj.isHiddenInVpt and isTypeMatch do
            (
                local isMatch = false
                local passCustom = true
                if opts.matchCustomName do
                (
                    if not (matchPattern obj.name pattern:opts.customName ignoreCase:true) do passCustom = false
                )
                
                if passCustom do
                (
                    if fingerprints.count > 0 then
                    (
                        local objBBox = obj.max - obj.min
                        local objCounts = GetTriMeshFaceCount obj
                        if objCounts == undefined do objCounts = #(0,0)
                        
                        for fp in fingerprints do
                        (
                            local matchThisFp = true
                            if opts.matchBaseName and not (matchPattern obj.name pattern:fp.pattern ignoreCase:true) do matchThisFp = false
                            if matchThisFp and opts.matchBBox do
                            (
                                if (abs(objBBox.x - fp.bbox.x) > 0.01 or abs(objBBox.y - fp.bbox.y) > 0.01 or abs(objBBox.z - fp.bbox.z) > 0.01) do matchThisFp = false
                            )
                            if matchThisFp and opts.matchVertFace do
                            (
                                if (objCounts[1] != fp.faces or objCounts[2] != fp.verts) do matchThisFp = false
                            )
                            if matchThisFp do ( isMatch = true; exit )
                        )
                    )
                    else isMatch = true
                )
                if isMatch do append matchedNodes obj
            )
        )
    )
    
    -- Processing
    if matchedNodes.count > 0 do
    (
        undo "Batch Process" on
        (
            for i = 1 to matchedNodes.count do
            (
                local obj = matchedNodes[i]
                if opts.randomColor then obj.wirecolor = color (random 0 255) (random 0 255) (random 0 255)
                else obj.wirecolor = opts.targetColor
                
                if opts.renameTo != "" do
                (
                    if opts.addSuffix then obj.name = opts.renameTo + "_" + core.padZero i
                    else obj.name = opts.renameTo
                )
                
                if opts.removeMat do obj.material = undefined
                if opts.removeUVW do try ( channelInfo.ClearChannel obj 1 ) catch ()
            )
        )
    )
    
    return matchedNodes
)
