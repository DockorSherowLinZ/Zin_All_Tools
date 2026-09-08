<#
.SYNOPSIS
    Deploy the ZinAllTools macroscripts and icons from this repo into 3ds Max.

.DESCRIPTION
    3ds Max loads macros from %LOCALAPPDATA%\Autodesk\3dsMax\<ver>\ENU\usermacros
    as self-contained copies, so the repo and the install drift apart unless they
    are synced. Targets are matched by macroScript identity (category + name), not
    by filename, so an existing registration is overwritten instead of duplicated.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File max_script\deploy_to_max.ps1
    powershell -ExecutionPolicy Bypass -File max_script\deploy_to_max.ps1 -Execute
#>
param(
    [string]$MaxVersion = "2024",
    [switch]$Execute
)

$ErrorActionPreference = "Stop"

$repo     = Split-Path -Parent $MyInvocation.MyCommand.Path
$enu      = Join-Path $env:LOCALAPPDATA "Autodesk\3dsMax\$MaxVersion - 64bit\ENU"
$usermac  = Join-Path $enu "usermacros"
$usericon = Join-Path $enu "usericons"

if (-not (Test-Path $enu)) { throw "3ds Max $MaxVersion profile not found: $enu" }

# A running 3ds Max memory-maps the macro files, which makes writes fail.
if ($Execute -and (Get-Process 3dsmax -ErrorAction SilentlyContinue)) {
    throw "3ds Max is running. Close it first, then re-run with -Execute."
}

# Overwritten files are kept here so a bad deploy can be rolled back.
$backupDir = Join-Path $env:TEMP "zin_max_deploy_backup_$(Get-Date -Format yyyyMMdd_HHmmss)"

# MaxScript 'include' resolves at compile time and cannot take a computed path,
# so the repo root is baked in here instead of at runtime.
$canonPlain = 'D:\Inventec\Zin_All_Tools\max_script'
$canonEsc   = 'D:\\Inventec\\Zin_All_Tools\\max_script'

function Resolve-Content {
    param([string]$Path)
    $text = Get-Content -LiteralPath $Path -Raw
    # Escaped form first; rewriting the plain form first would corrupt it.
    $text = $text.Replace($canonEsc, $repo.Replace('\', '\\'))
    $text.Replace($canonPlain, $repo)
}

function Get-StringHash {
    param([string]$Text)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    -join ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") })
}

function Get-MacroId {
    param([string]$Path)
    $text = Get-Content -LiteralPath $Path -Raw
    $m = [regex]::Match($text, '(?im)^\s*macroScript\s+(\w+)')
    if (-not $m.Success) { return $null }
    $name = $m.Groups[1].Value
    $tail = $text.Substring($m.Index, [Math]::Min(400, $text.Length - $m.Index))
    $cat  = if ($tail -match 'category\s*:\s*"([^"]+)"') { $matches[1] } else { "ZinAllTools" }
    [pscustomobject]@{ Category = $cat; Name = $name; Key = "$cat/$name" }
}

# Existing registrations, keyed by macro identity.
$installed = @{}
Get-ChildItem $usermac -Filter *.mcr -ErrorAction SilentlyContinue | ForEach-Object {
    $id = Get-MacroId $_.FullName
    if ($id) { $installed[$id.Key] = $_.FullName }
}

$actions = @()
foreach ($src in Get-ChildItem $repo -Recurse -Filter *.mcr) {
    $id = Get-MacroId $src.FullName
    if (-not $id) { continue }

    $resolved = Resolve-Content $src.FullName

    if ($installed.ContainsKey($id.Key)) {
        $dest = $installed[$id.Key]
        $same = (Get-StringHash $resolved) -eq (Get-StringHash (Get-Content -LiteralPath $dest -Raw))
        $verb = if ($same) { "UP-TO-DATE" } else { "UPDATE" }
    } else {
        $dest = Join-Path $usermac "$($id.Category)-$($id.Name).mcr"
        $verb = "INSTALL"
    }
    $actions += [pscustomobject]@{ Verb = $verb; Key = $id.Key; Src = $src.FullName; Dest = $dest; Text = $resolved }
}

foreach ($a in $actions | Sort-Object Verb, Key) {
    "{0,-11} {1,-44} -> {2}" -f $a.Verb, $a.Key, (Split-Path $a.Dest -Leaf)
    if ($Execute -and $a.Verb -ne "UP-TO-DATE") {
        if (Test-Path $a.Dest) {
            $bak = Join-Path $backupDir (Split-Path $a.Dest -Leaf)
            New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
            Copy-Item -LiteralPath $a.Dest -Destination $bak -Force
        }
        [System.IO.File]::WriteAllText($a.Dest, $a.Text, (New-Object System.Text.UTF8Encoding($false)))
    }
}

$icons = Join-Path $repo "Icons"
if (Test-Path $icons) {
    Write-Output ""
    foreach ($i in Get-ChildItem $icons -File) {
        $dest = Join-Path $usericon $i.Name
        $same = (Test-Path $dest) -and ((Get-FileHash $i.FullName).Hash -eq (Get-FileHash $dest).Hash)
        "{0,-11} icon {1}" -f $(if ($same) { "UP-TO-DATE" } else { "UPDATE" }), $i.Name
        if ($Execute -and -not $same) {
            if (Test-Path $dest) {
                New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
                Copy-Item -LiteralPath $dest -Destination (Join-Path $backupDir $i.Name) -Force
            }
            Copy-Item -LiteralPath $i.FullName -Destination $dest -Force
        }
    }
}

Write-Output ""
if ($Execute) {
    if (Test-Path $backupDir) { "Previous versions backed up to: $backupDir" }
    "Done. Restart 3ds Max to pick up the changes."
}
else { "(dry run - nothing changed; re-run with -Execute)" }
