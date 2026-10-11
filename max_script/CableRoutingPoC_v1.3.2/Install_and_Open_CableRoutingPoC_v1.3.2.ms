-- Keep this file beside CableRoutingPoC_v1.3.2.mcr.
-- Run via Scripting > Run Script, or drag into a viewport.
(
    local installerPath = getSourceFileName()
    local macroPath = (getFilenamePath installerPath) + "CableRoutingPoC_v1.3.2.mcr"
    try
    (
        if not doesFileExist macroPath do throw ("Missing MCR beside installer: " + macroPath)
        fileIn macroPath quiet:true
        macros.run "ZinAllTools" "CableRoutingPoC"
    )
    catch
    (
        local errorText = getCurrentException()
        format "Cable Routing installer error: %\n" errorText
        messageBox errorText title:"Cable Routing - Installation / Launch Error"
    )
)
