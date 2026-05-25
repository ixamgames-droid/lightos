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

REM Main starten
"%PYTHON%" main.py %*

endlocal
