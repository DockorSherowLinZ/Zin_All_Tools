macroScript ZinAllTools_SmartMergePolygons
category:"ZinAllTools"
tooltip:"Smart merge of identical polygon objects"
buttonText:"SmartMergePolygons"
icon:#("ZinAllTools", 8)
(
    global Roll_SmartMerge

    rollout Roll_SmartMerge "SmartMergePolygons" width:300
    (
        checkbox chk_includeHidden "Include Hidden Objects" checked:false align:#center
        checkbox chk_enableTolerance "Enable Dimension Check" checked:true align:#center
        spinner spn_tolerance "Dimension Tolerance (cm):" range:[0,1,0.01] type:#float scale:0.001 fieldwidth:80 align:#center
        button btn_merge "Merge Now" width:280 height:30 align:#center

        on btn_merge pressed do
        (
            local objs = for obj in geometry where 
                ((chk_includeHidden.checked or not obj.isHidden) and (classOf obj == Editable_Mesh or classOf obj == Editable_Poly)) collect (
                    if classOf obj == Editable_Mesh then convertToPoly obj else obj
                )

            local visited = #()
            local groups = #()
            local tolerance = spn_tolerance.value
            local useTolerance = chk_enableTolerance.checked

            for i = 1 to objs.count do (
                if (findItem visited i) == 0 do (
                    local base = objs[i]
                    local group = #(base)
                    append visited i

                    for j = i+1 to objs.count do (
                        if (findItem visited j) == 0 do (
                            local other = objs[j]
                            local baseSize = distance base.max base.min
                            local otherSize = distance other.max other.min

                            local sizeMatch = true
                            if useTolerance do (
                                sizeMatch = (abs(baseSize - otherSize) <= tolerance)
                            )

                            if (
                                base.numverts == other.numverts and 
                                base.numfaces == other.numfaces and 
                                sizeMatch
                            ) then (
                                append group other
                                append visited j
                            )
                        )
                    )
                    if group.count > 1 do append groups group
                )
            )

            local totalMerged = 0
            for g = 1 to groups.count do (
                local baseObj = groups[g][1]
                for k = 2 to groups[g].count do (
                    try (
                        polyop.attach baseObj groups[g][k]
                        delete groups[g][k]
                    ) catch ()
                )
                totalMerged += 1
            )

            messageBox ("Done! Merged " + totalMerged as string + " group(s) of identical geometry.")
        )
    )

    on execute do (
        try (destroyDialog Roll_SmartMerge) catch()
        createDialog Roll_SmartMerge style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)
    )
)
