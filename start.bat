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
REM Emulation, alles geht, dazu kommt kein Hinweis. Natives ARM64-Python ist nicht
REM unterstuetzt: kein QtWebEngine und damit kein 3D-Visualizer (XPLAT-45/46), und
REM LightOS stuerzte damit in 6 von 12 Starts ab (XPLAT-51). Gestartet wird trotzdem.
REM PROCESSOR_IDENTIFIER zeigt auf ARM-Hardware stets "ARMv8", auch unter Emulation.
REM Gefragt wird das Python, das main.py startet - nicht die Shell: Exit-Code 3
REM heisst win-arm64.
echo %PROCESSOR_IDENTIFIER% | find /I "ARMv8" >nul
if errorlevel 1 goto :arch_fertig
"%PYTHON%" -c "import sys, sysconfig; sys.exit(3 if sysconfig.get_platform() == 'win-arm64' else 0)" >nul 2>&1
if errorlevel 4 goto :arch_fertig
if errorlevel 3 echo [start] WARNUNG: natives ARM64-Python ist nicht unterstuetzt - instabil, kein 3D. x64-Python nehmen: winget install Python.Python.3.12 --architecture x64 - Details in INSTALL.md.
:arch_fertig

REM Main starten
"%PYTHON%" main.py %*

endlocal
