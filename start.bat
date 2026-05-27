@echo off
REM LightOS Start-Script fuer Windows (CMD)
REM Funktioniert auf x64 und ARM64

setlocal

cd /d "%~dp0"

REM Hinweis, wenn auf ARM64 vermutlich ein emuliertes Python laeuft
set NATIVE_ARCH=%PROCESSOR_ARCHITECTURE%
if not "%PROCESSOR_ARCHITEW6432%"=="" set NATIVE_ARCH=%PROCESSOR_ARCHITEW6432%
if /I "%NATIVE_ARCH%"=="ARM64" (
    if /I not "%PROCESSOR_ARCHITECTURE%"=="ARM64" (
        echo [start] WARN: Python scheint emuliert zu laufen. Fuer beste Stabilitaet/Performance ARM64-Python nutzen.
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
