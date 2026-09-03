macroScript ZinAllTools_MergeByName
category:"ZinAllTools"
toolTip:"Merge By Name Tool"
icon:#("ZinAllTools", 8)
(
    global MergeByNameUI
    
    rollout MergeByNameUI "Merge By Name" width:240 height:170
    (
        editText nameInput "Object Name:" width:220 align:#left
        checkBox ignoreSuffixChk "Ignore Suffix (_001, _002...)" checked:false align:#left
        button mergeBtn "Merge Objects" width:220 align:#left
        label resultLabel "" align:#left

        fn stripSuffix name =
        (
            local tokens = filterString name "_"
            if tokens.count > 1 then
                return (tokens[1])
            else
                return name
        )

        fn mergeObjectsByName objName ignoreSuffix =
        (
            if objName == "" do
            (
                resultLabel.text = "Please enter a name."
                return()
            )

            local matchedObjs = for o in objects where (
                (isKindOf o Editable_Poly or isKindOf o Editable_Mesh) and (
                    if ignoreSuffix then
                        (stripSuffix o.name == stripSuffix objName)
                    else
                        (matchPattern o.name pattern:objName)
                )
            ) collect o

            if matchedObjs.count < 2 do
            (
                resultLabel.text = "Less than two matching objects found."
                return()
            )

            local base = matchedObjs[1]
            select base
            convertTo base Editable_Poly

            for i = 2 to matchedObjs.count do
            (
                local target = matchedObjs[i]
                if isValidNode target do
                (
                    convertTo target Editable_Poly
                    select target
                    polyop.attach base target
                )
            )
            select base
            resultLabel.text = ("Merged " + matchedObjs.count as string + " objects.")
        )

        on mergeBtn pressed do
        (
            mergeObjectsByName nameInput.text ignoreSuffixChk.checked
        )
    )

    on execute do
    (
        try (destroyDialog MergeByNameUI) catch()
        createDialog MergeByNameUI
    )
)
