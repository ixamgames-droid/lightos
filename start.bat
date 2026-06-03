@echo off
REM LightOS Start-Script fuer Windows (CMD)
REM Funktioniert auf x64 und ARM64

setlocal

cd /d "%~dp0"

REM Native Hardware ueber CPU-Identifier erkennen (robust auch unter Emulation).
REM PROCESSOR_IDENTIFIER zeigt auf ARM-Hardware stets "ARMv8" - unabhaengig davon,
REM ob der aktuelle Prozess emuliert laeuft.
echo %PROCESSOR_IDENTIFIER% | find /I "ARMv8" >nul
if %ERRORLEVEL%==0 (
    if /I not "%PROCESSOR_ARCHITECTURE%"=="ARM64" (
        echo [start] WARN: ARM64-Hardware, aber Shell/Python laeuft emuliert. Fuer beste Stabilitaet/Performance ARM64-Python nutzen.
    )
)

REM venv pruefen
if exist "venv\Scripts\python.exe" (
    set PYTHON=venv\Scripts\python.exe
) else (
    echo [start] Kein venv gefunden - nutze System-Python
    set PYTHON=python
)

echo [start] Verwende Python: %PYTHON%

REM Main starten
"%PYTHON%" main.py %*

endlocal
