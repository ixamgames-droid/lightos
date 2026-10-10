@echo off
REM LightOS Start-Script fuer Windows (CMD)
REM Funktioniert auf x64 und ARM64

setlocal

cd /d "%~dp0"

REM venv pruefen
if exist "venv\Scripts\python.exe" (
    set PYTHON=venv\Scripts\python.exe
) else (
    echo [start] Kein venv gefunden - nutze System-Python
    set PYTHON=python
)

echo [start] Verwende Python: %PYTHON%

REM XPLAT-50: Auf Windows-ARM ist x64-Python der empfohlene Weg - es laeuft per
REM Emulation, alles geht, dazu kommt kein Hinweis. Natives ARM64-Python hat kein
REM QtWebEngine und damit keinen 3D-Visualizer, siehe XPLAT-45 und XPLAT-46.
REM PROCESSOR_IDENTIFIER zeigt auf ARM-Hardware stets "ARMv8", auch unter Emulation.
REM Gefragt wird das Python, das main.py startet - nicht die Shell: Exit-Code 3
REM heisst win-arm64.
echo %PROCESSOR_IDENTIFIER% | find /I "ARMv8" >nul
if errorlevel 1 goto :arch_fertig
"%PYTHON%" -c "import sys, sysconfig; sys.exit(3 if sysconfig.get_platform() == 'win-arm64' else 0)" >nul 2>&1
if errorlevel 4 goto :arch_fertig
if errorlevel 3 echo [start] HINWEIS: natives ARM64-Python - LightOS laeuft ohne 3D-Visualizer. x64-Python empfohlen: winget install Python.Python.3.12 --architecture x64 - Details in INSTALL.md.
:arch_fertig

REM Main starten
"%PYTHON%" main.py %*

endlocal
