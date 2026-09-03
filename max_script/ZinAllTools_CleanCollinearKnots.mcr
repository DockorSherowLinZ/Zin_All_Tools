macroScript ZinAllTools_CleanCollinearKnots
category:"ZinAllTools"
tooltip:"Clean Collinear Knots (Removes redundant straight-line vertices)"
buttonText:"Clean Splines"
icon:#("ZinAllTools", 8)
(
    on isVisible return (selection.count > 0)
    
    on execute do
    (
        undo "Clean Collinear Knots" on
        (
            local processedCount = 0
            for s in selection where superclassOf s == shape do
            (
                convertToSplineShape s
                local angleThreshold = 179.5
                local deletedAny = false
                
                for i = 1 to numSplines s do
                (
                    for k = (numKnots s i - 1) to 2 by -1 do
                    (
                        local p1 = getKnotPoint s i (k-1)
                        local p2 = getKnotPoint s i k
                        local p3 = getKnotPoint s i (k+1)
                        
                        local v1 = normalize (p1 - p2)
                        local v2 = normalize (p3 - p2)
                        local ang = acos (dot v1 v2)
                        
                        if ang != undefined and ang > angleThreshold do
                        (
                            deleteKnot s i k
                            deletedAny = true
                        )
                    )
                )
                if deletedAny do
                (
                    updateShape s
                    processedCount += 1
                )
            )
            messageBox ("Finished! Cleaned collinear knots on " + processedCount as string + " shapes.") title:"ZinAllTools"
        )
    )
)
