
-- ============================================================================
-- Zin_AIMaterialAssignerCore (Headless Logic)
-- ============================================================================
global Zin_AIMaterialAssignerCore

struct Zin_AIMaterialAssignerCoreStruct
(
    logFilePath = "",
    scriptDir = "",
    configPath = "",
    tempDir = "",
    pythonPath = "python",

    categoriesList = #(),
    uniqueKeys = #(),
    uniqueGroups = #(),

    fn pad0 num = (if num < 10 then "0" + (num as string) else (num as string)),
    fn rnd val = (floor (val * 10000.0 + 0.5)) / 10000.0,

    fn initLogFile =
    (
        if maxFilePath != "" then logFilePath = maxFilePath + "AI_MaterialAssigner_Log.txt"
        else logFilePath = sysInfo.tempdir + "AI_MaterialAssigner_Log.txt"
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

    fn loadConfig =
    (
        if not doesFileExist configPath do return false
        local catStr = getINISetting configPath "Categories" "list"
        if catStr != "" do categoriesList = filterString catStr ","
        local pyPath = getINISetting configPath "General" "python_path"
        if pyPath != "" do pythonPath = pyPath
        return true
    ),

    fn getShapeFingerprint node =
    (
        local bboxSize = node.max - node.min
        local w = this.rnd (abs bboxSize.x)
        local h = this.rnd (abs bboxSize.y)
        local d = this.rnd (abs bboxSize.z)
        local dims = sort #(w, h, d)
        local nf = node.mesh.numfaces as string
        local nv = node.mesh.numverts as string
        local fp = (dims[1] as string) + "|" + (dims[2] as string) + "|" + (dims[3] as string) + "|" + nf + "|" + nv
        return fp
    ),

    fn groupByFingerprint geoArr =
    (
        uniqueKeys = #()
        uniqueGroups = #()

        for n in geoArr do
        (
            local fp = this.getShapeFingerprint n
            local idx = findItem uniqueKeys fp
            if idx == 0 then
            (
                append uniqueKeys fp
                append uniqueGroups #(n)
            )
            else append uniqueGroups[idx] n
        )
    ),

    fn captureViewportResized targetSize =
    (
        local srcBmp = gw.getViewportDib()
        if srcBmp == undefined do return undefined
        local dstBmp = bitmap targetSize targetSize color:black
        local srcBox = box2 0 0 srcBmp.width srcBmp.height
        local dstBox = box2 0 0 targetSize targetSize
        pasteBitmap srcBmp dstBmp srcBox dstBox
        close srcBmp
        return dstBmp
    ),

    fn captureUniqueShapes captureSize =
    (
        for obj in objects do if isGroupHead obj do setGroupOpen obj true
        local allObjs = for obj in objects collect obj
        local origHidden = for obj in allObjs collect obj.isHidden
        for obj in allObjs do try (obj.isHidden = true) catch ()
        viewport.setType #view_persp_user

        local capturedPaths = #()

        for i = 1 to uniqueKeys.count do
        (
            local representative = uniqueGroups[i][1]
            if not isValidNode representative do ( append capturedPaths ""; continue )

            try (representative.isHidden = false) catch ()
            local p = representative.parent
            while p != undefined do
            (
                try (p.isHidden = false) catch ()
                if isGroupHead p do setGroupOpen p true
                p = p.parent
            )

            select representative
            max zoomext sel all
            completeRedraw()

            local bmp = this.captureViewportResized captureSize
            if bmp != undefined then
            (
                local imgPath = tempDir + "shape_" + (formattedPrint i format:"04d") + ".jpg"
                bmp.filename = imgPath
                save bmp
                close bmp
                append capturedPaths imgPath
                this.writeLog ("  Captured: " + imgPath)
            )
            else append capturedPaths ""

            try (representative.isHidden = true) catch ()
            p = representative.parent
            while p != undefined do ( try (p.isHidden = true) catch (); p = p.parent )
        )

        for i = 1 to allObjs.count do
            if isValidNode allObjs[i] do try (allObjs[i].isHidden = origHidden[i]) catch ()
        
        completeRedraw()
        return capturedPaths
    ),

    fn writeRequestFile capturedPaths apiKey model delaySec =
    (
        local reqPath = tempDir + "request.txt"
        local f = createFile reqPath
        if f == undefined do return ""

        format "API_KEY|%\n" apiKey to:f
        format "MODEL|%\n" model to:f
        
        local catStr = ""
        for i = 1 to categoriesList.count do ( catStr += categoriesList[i]; if i < categoriesList.count do catStr += "," )
        format "CATEGORIES|%\n" catStr to:f
        format "DELAY|%\n" (delaySec as string) to:f

        for i = 1 to capturedPaths.count do
            if capturedPaths[i] != "" do format "SHAPE|%|%\n" uniqueKeys[i] capturedPaths[i] to:f

        close f
        return reqPath
    ),

    fn runPythonClassifier reqPath =
    (
        local resPath = tempDir + "result.txt"
        local pyScript = scriptDir + "ai_vlm_classify.py"
        local args = "\"" + pyScript + "\" \"" + reqPath + "\" \"" + resPath + "\""

        local psi = dotNetObject "System.Diagnostics.ProcessStartInfo"
        psi.FileName = pythonPath
        psi.Arguments = args
        psi.UseShellExecute = false
        psi.CreateNoWindow = true
        psi.RedirectStandardOutput = true
        psi.RedirectStandardError = true

        local proc = (dotNetClass "System.Diagnostics.Process").Start psi
        proc.WaitForExit()
        local exitCode = proc.ExitCode
        local stdout = proc.StandardOutput.ReadToEnd()
        local stderr = proc.StandardError.ReadToEnd()
        proc.Close()

        if stdout != "" do this.writeLog ("Python stdout:\n" + stdout)
        if stderr != "" do this.writeLog ("Python stderr:\n" + stderr)
        if exitCode != 0 or not doesFileExist resPath do return ""
        return resPath
    ),

    fn readResultFile resPath =
    (
        local results = #()
        local f = openFile resPath
        if f == undefined do return results
        while not eof f do
        (
            local line = readLine f
            if line.count > 0 and line[1] != "#" do
            (
                local parts = filterString line "|"
                if parts.count >= 3 do
                (
                    local conf = 0
                    try (conf = parts[3] as integer) catch ()
                    append results #(parts[1], parts[2], conf)
                )
            )
        )
        close f
        return results
    ),

    fn getMaterialPreset label =
    (
        case label of
        (
            "ScanGreenLight":      #(color   0 255   0, 0.0, 0.30, 0.0, 1.0, color   0 255   0)
            "BlackPlastic":        #(color  30  30  30, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
            "GreenPlastic":        #(color  30 150  50, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
            "RedPlastic":          #(color 200  30  30, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
            "WhitePlastic":        #(color 240 240 240, 0.0, 0.40, 0.0, 0.0, color   0   0   0)
            "BluePlastic":         #(color  30  60 200, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
            "LockerMetal":         #(color 160 160 165, 1.0, 0.35, 0.0, 0.0, color   0   0   0)
            "RedClearPlastic":     #(color 200  30  30, 0.0, 0.15, 0.7, 0.0, color   0   0   0)
            "RedLight":            #(color 255   0   0, 0.0, 0.30, 0.0, 1.0, color 255   0   0)
            "OrangeLight":         #(color 255 140   0, 0.0, 0.30, 0.0, 1.0, color 255 140   0)
            "OrangeClearPlastic":  #(color 255 140   0, 0.0, 0.15, 0.7, 0.0, color   0   0   0)
            "GreenLight":          #(color   0 255   0, 0.0, 0.30, 0.0, 1.0, color   0 255   0)
            "GreenClearPlastic":   #(color  30 200  50, 0.0, 0.15, 0.7, 0.0, color   0   0   0)
            "Rubber":              #(color  40  40  40, 0.0, 0.85, 0.0, 0.0, color   0   0   0)
            "YellowPlastic":       #(color 240 220  30, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
            "ClearPlastic":        #(color 240 245 255, 0.0, 0.05, 0.85,0.0, color   0   0   0)
            "GrayPlastic":         #(color 140 140 140, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
            "ScanPlastic":         #(color  50  50  55, 0.0, 0.40, 0.0, 0.0, color   0   0   0)
            "Gold":                #(color 255 200  50, 1.0, 0.20, 0.0, 0.0, color   0   0   0)
            "BLueMetal":           #(color  60  80 180, 1.0, 0.30, 0.0, 0.0, color   0   0   0)
            "BlackMetal":          #(color  25  25  25, 1.0, 0.35, 0.0, 0.0, color   0   0   0)
            "Paper":               #(color 245 240 230, 0.0, 0.80, 0.0, 0.0, color   0   0   0)
            "CaseWhiteMetal":      #(color 230 230 235, 0.8, 0.30, 0.0, 0.0, color   0   0   0)
            "BlackSticker":        #(color  20  20  20, 0.0, 0.30, 0.0, 0.0, color   0   0   0)
            "Capacitor":           #(color  60  60  65, 0.3, 0.50, 0.0, 0.0, color   0   0   0)
            "PCBGreenPLastic":     #(color  20  80  40, 0.0, 0.55, 0.0, 0.0, color   0   0   0)
            "USD3BluePlastic":     #(color  40  70 180, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
            "PCBBluePlastic":      #(color  30  50 150, 0.0, 0.55, 0.0, 0.0, color   0   0   0)
            "Washer":              #(color 180 180 185, 1.0, 0.35, 0.0, 0.0, color   0   0   0)
            "RedMetal":            #(color 180  30  30, 1.0, 0.30, 0.0, 0.0, color   0   0   0)
            "GrayMetal":           #(color 150 150 155, 1.0, 0.35, 0.0, 0.0, color   0   0   0)
            "GraySticker":         #(color 160 160 160, 0.0, 0.30, 0.0, 0.0, color   0   0   0)
            "LightGreenPlastic":   #(color 120 220 120, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
            "LightYellowPlastic":  #(color 255 245 150, 0.0, 0.45, 0.0, 0.0, color   0   0   0)
            "CaseMetal":           #(color 170 170 175, 1.0, 0.30, 0.0, 0.0, color   0   0   0)
            "Brass":               #(color 180 150  50, 1.0, 0.25, 0.0, 0.0, color   0   0   0)
            "BKMetal":             #(color  30  30  35, 1.0, 0.35, 0.0, 0.0, color   0   0   0)
            "Die":                 #(color 190 190 195, 1.0, 0.25, 0.0, 0.0, color   0   0   0)
            "Zinc":                #(color 200 200 205, 1.0, 0.30, 0.0, 0.0, color   0   0   0)
            "Chip":                #(color  35  35  40, 0.2, 0.40, 0.0, 0.0, color   0   0   0)
            default:               #(color 128 128 128, 0.0, 0.50, 0.0, 0.0, color   0   0   0)
        )
    ),

    fn findOrCreateMaterial label =
    (
        for m in sceneMaterials do if m.name == label do return m
        local preset = this.getMaterialPreset label
        local mat = PhysicalMaterial()
        mat.name = label
        try (mat.base_color = preset[1]) catch ()
        try (mat.metalness = preset[2]) catch ()
        try (mat.roughness = preset[3]) catch ()
        try (mat.transparency = preset[4]) catch ()
        try (mat.emission = preset[5]) catch ()
        try (mat.emit_color = preset[6]) catch ()
        return mat
    ),

    fn applyClassificationResults results threshold doRename doMaterial =
    (
        local appliedCount = 0
        local resKeys = #()
        local resLabels = #()
        local resConfs = #()
        for r in results do ( append resKeys r[1]; append resLabels r[2]; append resConfs r[3] )

        for i = 1 to uniqueKeys.count do
        (
            local fpKey = uniqueKeys[i]
            local idx = findItem resKeys fpKey
            if idx == 0 do continue

            local label = resLabels[idx]
            local conf = resConfs[idx]

            if conf < threshold or label == "Unknown" do continue

            local mat = undefined
            if doMaterial do mat = this.findOrCreateMaterial label

            for j = 1 to uniqueGroups[i].count do
            (
                local node = uniqueGroups[i][j]
                if not isValidNode node do continue
                
                if doRename do
                (
                    if uniqueGroups[i].count > 1 then node.name = label + "_" + (formattedPrint j format:"03d")
                    else node.name = label
                )

                if doMaterial and mat != undefined do node.material = mat
                appliedCount += 1
                
                -- Update SimReady Tag
                try (
                    if Zin_SimReadyTagDef != undefined do
                    (
                        local ca = custAttributes.get node Zin_SimReadyTagDef
                        if ca != undefined do
                        (
                            ca.componentType = label
                            ca.materialClass = label
                            ca.aiClassified = true
                        )
                    )
                ) catch()
            )
        )
        return appliedCount
    )
)

Zin_AIMaterialAssignerCore = Zin_AIMaterialAssignerCoreStruct()

struct Zin_AIOptions
(
    apiKey = "",
    model = "gemini-2.0-flash-lite",
    delaySec = 0,
    confidence = 60,
    autoRename = true,
    autoMaterial = true
)

fn Zin_RunAIMaterialAssignerBatch nodeArray opts:(Zin_AIOptions()) =
(
    local core = Zin_AIMaterialAssignerCore
    core.scriptDir = "D:\\Zin_All_Tools\\max_script\\AI_MaterialAssigner\\"
    core.configPath = core.scriptDir + "config.ini"
    core.tempDir = core.scriptDir + "_temp\\"
    core.initLogFile()
    core.loadConfig()
    makeDir core.tempDir all:true

    core.writeLog "=== AI Material Assigner Headless Batch Started ==="
    
    local geoArr = #()
    for n in nodeArray do
    (
        if isValidNode n and superclassof n == GeometryClass and classof n != TargetObject do
        (
            local hasFaces = false
            try (if n.mesh.numfaces > 0 do hasFaces = true) catch ()
            if hasFaces do append geoArr n
        )
    )

    if geoArr.count > 0 do
    (
        core.groupByFingerprint geoArr
        local capturedPaths = core.captureUniqueShapes 512
        local reqPath = core.writeRequestFile capturedPaths opts.apiKey opts.model opts.delaySec
        if reqPath != "" do
        (
            local resPath = core.runPythonClassifier reqPath
            if resPath != "" do
            (
                local results = core.readResultFile resPath
                core.applyClassificationResults results opts.confidence opts.autoRename opts.autoMaterial
            )
        )
    )
    
    local tempFiles = getFiles (core.tempDir + "*.*")
    for tf in tempFiles do try (deleteFile tf) catch ()
    
    core.writeLog "=== AI Material Assigner Headless Batch Completed ==="
)
