
-- ============================================================================
-- Zin_GeomOptimizerCore (Headless Logic)
-- ============================================================================
global Zin_GeomOptimizerCore

struct Zin_GeomOptimizerCoreStruct
(
    logFilePath = "",

    fn pad0 num = (if num < 10 then "0" + (num as string) else (num as string)),
    fn rnd val = (floor (val * 10000.0 + 0.5)) / 10000.0,
    
    fn initLogFile =
    (
        if maxFilePath != "" then logFilePath = maxFilePath + "GeomOptimizer_Log.txt"
        else logFilePath = sysInfo.tempdir + "GeomOptimizer_Log.txt"
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

    fn isDigitChar ch = (findString "0123456789" ch != undefined),
    fn isSepChar ch = (ch == "_" or ch == "-" or ch == " "),

    fn getBaseName meshName =
    (
        local name = meshName
        while name.count > 0 and this.isDigitChar name[name.count] do name = substring name 1 (name.count - 1)
        while name.count > 0 and this.isSepChar name[name.count] do name = substring name 1 (name.count - 1)
        if name.count == 0 do return meshName
        return name
    ),

    fn collectAllGeometry nodeList &geoArr =
    (
        for n in nodeList do
        (
            if isValidNode n do
            (
                if superclassof n == GeometryClass and classof n != TargetObject do
                (
                    local hasFaces = false
                    try (if n.mesh.numfaces > 0 do hasFaces = true) catch ()
                    if hasFaces do append geoArr n
                )
                if n.children.count > 0 do
                (
                    local kids = for c in n.children collect c
                    this.collectAllGeometry kids &geoArr
                )
            )
        )
    ),

    fn getDupFingerprint node =
    (
        local tf = node.transform
        local fp = (this.rnd tf.row1.x) as string + "|" + (this.rnd tf.row1.y) as string + "|" + (this.rnd tf.row1.z) as string + "|" + \
                   (this.rnd tf.row2.x) as string + "|" + (this.rnd tf.row2.y) as string + "|" + (this.rnd tf.row2.z) as string + "|" + \
                   (this.rnd tf.row3.x) as string + "|" + (this.rnd tf.row3.y) as string + "|" + (this.rnd tf.row3.z) as string + "|" + \
                   (this.rnd tf.row4.x) as string + "|" + (this.rnd tf.row4.y) as string + "|" + (this.rnd tf.row4.z) as string + "|" + \
                   (node.mesh.numfaces as string) + "|" + (node.mesh.numverts as string)
        return fp
    ),

    fn runStep1_DeleteDuplicates &geoArr =
    (
        this.writeLog "  Step 1: Delete Duplicates"
        if geoArr.count < 2 do return 0

        local fpKeys = #()
        local fpGroups = #()
        for n in geoArr do
        (
            if isValidNode n do
            (
                local fp = this.getDupFingerprint n
                local idx = findItem fpKeys fp
                if idx == 0 then ( append fpKeys fp; append fpGroups #(n) )
                else append fpGroups[idx] n
            )
        )

        local nodesToDelete = #()
        local dupGroupCount = 0
        for i = 1 to fpGroups.count do
        (
            local grp = fpGroups[i]
            if grp.count > 1 do
            (
                dupGroupCount += 1
                for j = 2 to grp.count do append nodesToDelete grp[j]
            )
        )

        local removedCount = nodesToDelete.count
        if removedCount > 0 do for dNode in nodesToDelete do if isValidNode dNode do delete dNode
        
        local validArr = #()
        for n in geoArr do if isValidNode n do append validArr n
        geoArr = validArr
        
        return removedCount
    ),

    fn getIdenticalGroupKey node baseName =
    (
        local tf = node.transform
        local sx = this.rnd (length [tf.row1.x, tf.row1.y, tf.row1.z])
        local sy = this.rnd (length [tf.row2.x, tf.row2.y, tf.row2.z])
        local sz = this.rnd (length [tf.row3.x, tf.row3.y, tf.row3.z])
        local key = (toUpper baseName) + "|" + sx as string + "|" + sy as string + "|" + sz as string + "|" + (node.mesh.numfaces as string) + "|" + (node.mesh.numverts as string)
        return key
    ),

    fn runStep2_AttachIdentical geoArr =
    (
        this.writeLog "  Step 2: Attach Identical"
        if geoArr.count < 2 do return #(0, 0)

        local groupKeys = #()
        local groupNodes = #()
        local groupBaseNames = #()

        for n in geoArr do
        (
            if isValidNode n do
            (
                local bName = this.getBaseName n.name
                local gKey = this.getIdenticalGroupKey n bName
                local idx = findItem groupKeys gKey
                if idx == 0 then ( append groupKeys gKey; append groupNodes #(n); append groupBaseNames bName )
                else append groupNodes[idx] n
            )
        )

        local groupsDone = 0
        local totalMergedCount = 0

        undo off
        (
            with redraw off
            (
                for i = 1 to groupNodes.count do
                (
                    local grp = groupNodes[i]
                    if grp.count < 2 do continue

                    groupsDone += 1
                    local baseName = groupBaseNames[i]
                    for n in grp do if isValidNode n do n.parent = undefined
                    local target = grp[1]
                    convertToMesh target

                    local attachCount = 0
                    for j = 2 to grp.count do
                    (
                        if isValidNode grp[j] do
                        (
                            convertToMesh grp[j]
                            try ( meshop.attach target grp[j]; attachCount += 1 ) catch ()
                        )
                    )
                    target.pivot = [0, 0, 0]
                    target.name = baseName
                    totalMergedCount += attachCount
                )
            )
        )
        return #(groupsDone, totalMergedCount)
    )
)

Zin_GeomOptimizerCore = Zin_GeomOptimizerCoreStruct()

struct Zin_GeomOptimizerOptions
(
    doStep1 = true,
    doStep2 = true
)

fn Zin_RunGeomOptimizerBatch nodeArray opts:(Zin_GeomOptimizerOptions()) =
(
    local core = Zin_GeomOptimizerCore
    core.initLogFile()
    core.writeLog "=== GeomOptimizer Headless Batch Started ==="
    
    local geoArr = #()
    core.collectAllGeometry nodeArray &geoArr

    if opts.doStep1 do core.runStep1_DeleteDuplicates &geoArr
    if opts.doStep2 do core.runStep2_AttachIdentical geoArr
    
    core.writeLog "=== GeomOptimizer Headless Batch Completed ==="
)
