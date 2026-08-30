-- ============================================================================
-- Zin SimReady Tags Definition
-- ============================================================================

global Zin_SimReadyTagDef = attributes SimReadyTag
(
    parameters SimReadyParams rollout:SimReadyRollout
    (
        componentType type:#string default:"Unknown"
        materialClass type:#string default:"Unassigned"
        sourceFile    type:#string default:""
        pivotFixed    type:#boolean default:false
        normalsFixed  type:#boolean default:false
        uvwAssigned   type:#boolean default:false
        aiClassified  type:#boolean default:false
        usdReady      type:#boolean default:false
        assetVersion  type:#string default:"v1.0"
    )
    
    rollout SimReadyRollout "SimReady 標籤"
    (
        edittext et_type "元件類型:" fieldWidth:150
        edittext et_mat "材質分類:" fieldWidth:150
        checkbox cb_pivot "Pivot已重置" checked:false
        checkbox cb_normals "法線已修復" checked:false
        checkbox cb_uvw "UVW已賦予" checked:false
        checkbox cb_ai "AI已分類" checked:false
        checkbox cb_usd "USD已檢驗" checked:false
        
        on SimReadyRollout open do
        (
            et_type.text = componentType
            et_mat.text = materialClass
            cb_pivot.checked = pivotFixed
            cb_normals.checked = normalsFixed
            cb_uvw.checked = uvwAssigned
            cb_ai.checked = aiClassified
            cb_usd.checked = usdReady
        )

        on et_type changed txt do componentType = txt
        on et_mat changed txt do materialClass = txt
        on cb_pivot changed state do pivotFixed = state
        on cb_normals changed state do normalsFixed = state
        on cb_uvw changed state do uvwAssigned = state
        on cb_ai changed state do aiClassified = state
        on cb_usd changed state do usdReady = state
    )
)

-- 為單一物件附加標籤
fn Zin_AttachSimReadyTag obj =
(
    if isValidNode obj do
    (
        if (custAttributes.get obj Zin_SimReadyTagDef) == undefined do
        (
            custAttributes.add obj Zin_SimReadyTagDef
        )
    )
)

-- 批次為物件陣列附加標籤
fn Zin_AttachSimReadyTagsBatch objArr =
(
    for o in objArr do Zin_AttachSimReadyTag o
)

-- 取得物件的 SimReady 標籤資料 (供匯出報表使用)
fn Zin_GetSimReadyData obj =
(
    if not isValidNode obj do return undefined
    local ca = custAttributes.get obj Zin_SimReadyTagDef
    if ca != undefined then
    (
        return #(obj.name, ca.componentType, ca.materialClass, ca.pivotFixed, ca.normalsFixed, ca.uvwAssigned, ca.aiClassified, ca.usdReady, ca.assetVersion)
    )
    else
    (
        return undefined
    )
)

-- 匯出場景中所有標籤為 JSON 報表
fn Zin_ExportSimReadyReport jsonPath =
(
    local f = createFile jsonPath
    if f != undefined then
    (
        format "[\n" to:f
        local validObjs = for o in objects where (custAttributes.get o Zin_SimReadyTagDef) != undefined collect o
        for i = 1 to validObjs.count do
        (
            local o = validObjs[i]
            local ca = custAttributes.get o Zin_SimReadyTagDef
            
            format "  {\n" to:f
            format "    \"NodeName\": \"%\",\n" o.name to:f
            format "    \"ComponentType\": \"%\",\n" ca.componentType to:f
            format "    \"MaterialClass\": \"%\",\n" ca.materialClass to:f
            format "    \"PivotFixed\": %,\n" (if ca.pivotFixed then "true" else "false") to:f
            format "    \"NormalsFixed\": %,\n" (if ca.normalsFixed then "true" else "false") to:f
            format "    \"UvwAssigned\": %,\n" (if ca.uvwAssigned then "true" else "false") to:f
            format "    \"AiClassified\": %,\n" (if ca.aiClassified then "true" else "false") to:f
            format "    \"UsdReady\": %\n" (if ca.usdReady then "true" else "false") to:f
            if i < validObjs.count then
                format "  },\n" to:f
            else
                format "  }\n" to:f
        )
        format "]\n" to:f
        close f
        print ("SimReady Report Exported to: " + jsonPath)
    )
)
