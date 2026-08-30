
-- ============================================================================
-- Zin_DictMaterialAssignerCore (Headless Logic)
-- ============================================================================
global Zin_DictMaterialAssignerCore

struct Zin_DictMaterialAssignerCoreStruct
(
    logFilePath = "",
    matLib = undefined,
    matLibNames = #(),
    dictRules = #(),
    
    fn pad0 num = (if num < 10 then "0" + (num as string) else (num as string)),
    
    fn initLogFile =
    (
        if maxFilePath != "" then logFilePath = maxFilePath + "DictMaterialAssigner_Log.txt"
        else logFilePath = sysInfo.tempdir + "DictMaterialAssigner_Log.txt"
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
            format "% %\n" timeStr msg to:f
            close f
        )
    ),

    fn loadMaterialLibrary libPath =
    (
        if not doesFileExist libPath do return false
        try
        (
            matLib = loadTempMaterialLibrary libPath
            matLibNames = #()
            for i = 1 to matLib.count do append matLibNames (toLower matLib[i].name)
            return true
        )
        catch ( return false )
    ),

    fn findMaterialByName matName =
    (
        if matLib == undefined do return undefined
        local lowerName = toLower matName
        local idx = findItem matLibNames lowerName
        if idx > 0 then return matLib[idx] else return undefined
    ),

    fn compareDictRuleLength r1 r2 =
    (
        local l1 = r1[1].count
        local l2 = r2[1].count
        case of
        (
            (l1 > l2): -1
            (l1 < l2):  1
            default:    0
        )
    ),

    fn loadDictionary dictPath =
    (
        if not doesFileExist dictPath do return false
        try
        (
            dictRules = #()
            local f = openFile dictPath
            if f == undefined do return false
            while not eof f do
            (
                local line = readLine f
                local trimmed = trimLeft (trimRight line)
                if trimmed.count == 0 or trimmed[1] == "#" do continue
                local eqPos = findString trimmed "="
                if eqPos == undefined do continue
                local keyword = trimRight (substring trimmed 1 (eqPos - 1))
                local matName = trimLeft (substring trimmed (eqPos + 1) -1)
                if keyword.count > 0 and matName.count > 0 do append dictRules #(toUpper keyword, matName)
            )
            close f
            qsort dictRules this.compareDictRuleLength
            return true
        )
        catch ( return false )
    ),

    fn matchKeyword meshName keywordUpper =
    (
        local normName = toUpper meshName
        normName = substituteString normName "_" "-"
        normName = substituteString normName " " "-"
        normName = "-" + normName + "-"
        local normKW = "-" + keywordUpper + "-"
        return (findString normName normKW) != undefined
    ),

    fn findBestMatch meshName =
    (
        local directMatch = this.findMaterialByName meshName
        if directMatch != undefined do return #(meshName, directMatch.name)
        for rule in dictRules do if this.matchKeyword meshName rule[1] do return #(rule[1], rule[2])
        return undefined
    )
)

Zin_DictMaterialAssignerCore = Zin_DictMaterialAssignerCoreStruct()

struct Zin_DictOptions
(
    matLibPath = "D:\\Inventec\\DigitalTwin\\Library\\3dsMax_Standard_Material.mat",
    dictPath = "D:\\Zin_All_Tools\\max_script\\DictMaterialAssigner\\material_dictionary.txt",
    skipAssigned = false,
    dryRun = false
)

fn Zin_RunDictMaterialAssignerBatch nodeArray opts:(Zin_DictOptions()) =
(
    local core = Zin_DictMaterialAssignerCore
    core.initLogFile()
    core.writeLog "=== DictMaterialAssigner Headless Batch Started ==="
    
    if not core.loadMaterialLibrary opts.matLibPath do
    (
        core.writeLog ("Failed to load Material Library: " + opts.matLibPath)
        return false
    )
    if not core.loadDictionary opts.dictPath do
    (
        core.writeLog ("Failed to load Dictionary: " + opts.dictPath)
        return false
    )

    local targetNodes = #()
    for n in nodeArray do
    (
        if isValidNode n and superclassof n == GeometryClass and classof n != TargetObject do
        (
            local hasFaces = false
            try (if n.mesh.numfaces > 0 do hasFaces = true) catch ()
            if hasFaces do append targetNodes n
        )
    )

    local matchedCount = 0
    local skippedCount = 0
    local unmatchedCount = 0
    local matCacheNames = #()
    local matCacheObjs = #()

    for node in targetNodes do
    (
        if opts.skipAssigned and node.material != undefined do
        (
            skippedCount += 1
            continue
        )
        
        local result = core.findBestMatch node.name
        if result != undefined then
        (
            local matchedKeyword = result[1]
            local targetMatName = result[2]
            
            local mat = undefined
            local cacheIdx = findItem matCacheNames targetMatName
            if cacheIdx > 0 then mat = matCacheObjs[cacheIdx]
            else
            (
                mat = core.findMaterialByName targetMatName
                if mat != undefined do ( append matCacheNames targetMatName; append matCacheObjs mat )
            )
            
            if mat != undefined then
            (
                if not opts.dryRun do
                (
                    node.material = mat
                    -- Update SimReady Tag
                    try (
                        if Zin_SimReadyTagDef != undefined do
                        (
                            local ca = custAttributes.get node Zin_SimReadyTagDef
                            if ca != undefined do ca.materialClass = targetMatName
                        )
                    ) catch()
                )
                matchedCount += 1
            )
            else unmatchedCount += 1
        )
        else unmatchedCount += 1
    )

    core.writeLog ("Matched: " + matchedCount as string + ", Skipped: " + skippedCount as string + ", Unmatched: " + unmatchedCount as string)
    core.writeLog "=== DictMaterialAssigner Headless Batch Completed ==="
    return true
)
