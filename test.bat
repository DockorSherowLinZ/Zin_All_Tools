@echo off
setlocal EnableExtensions EnableDelayedExpansion
 
set HOST=10.6.180.60
set PORTS=9901 9902 9903 9904
 
echo ==== Probe common endpoints ====
for %%P in (%PORTS%) do (
  echo.
  echo == PORT %%P ==
  for %%U in (/ /mcp /health /healthz /ready /readyz /sse /openapi.json /docs) do (
    set CODE=
    for /f "delims=" %%C in ('curl.exe -s -m 3 -o NUL -w "%%{http_code}" "http://%HOST%:%%P%%U"') do set CODE=%%C
    echo %%U ^> !CODE!
  )
)
 
echo.
echo ==== MCP initialize + tools/list count ====
 
set INIT_JSON=%TEMP%\mcp_init.json
set TOOLS_JSON=%TEMP%\mcp_tools_req.json
 
> "%INIT_JSON%" echo {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"diag-bat","version":"1.0.0"}}}
> "%TOOLS_JSON%" echo {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
 
for %%P in (%PORTS%) do (
  set HDR=%TEMP%\mcp_hdr_%%P.txt
  set TOOLS_BODY=%TEMP%\mcp_tools_body_%%P.txt
  set SID=
  set CNT=
 
  curl.exe -s -m 8 -D "!HDR!" ^
    -H "Content-Type: application/json" ^
    -H "Accept: application/json, text/event-stream" ^
    --data-binary "@%INIT_JSON%" ^
    "http://%HOST%:%%P/mcp" ^
    -o NUL
 
  for /f "usebackq delims=" %%S in (`powershell -NoProfile -Command "$h=Get-Content -Raw '!HDR!'; if($h -match '(?im)^mcp-session-id:\s*([^\r\n]+)'){ $matches[1].Trim() }"`) do set SID=%%S
 
  if not defined SID (
    echo PORT %%P ^> initialize failed (no mcp-session-id)
  ) else (
    curl.exe -s -m 8 ^
      -H "Content-Type: application/json" ^
      -H "Accept: application/json, text/event-stream" ^
      -H "mcp-session-id: !SID!" ^
      --data-binary "@%TOOLS_JSON%" ^
      "http://%HOST%:%%P/mcp" ^
      -o "!TOOLS_BODY!"
 
    for /f %%N in ('powershell -NoProfile -Command "$t=Get-Content -Raw '!TOOLS_BODY!'; [regex]::Matches($t,'\"name\":\"').Count"') do set CNT=%%N
    echo PORT %%P ^> session=!SID! tools=!CNT!
  )
)
 
del /q "%INIT_JSON%" "%TOOLS_JSON%" >NUL 2>NUL
echo.
echo Done.
endlocal