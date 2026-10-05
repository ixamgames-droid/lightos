@echo off
rem ============================================================
rem  LightOS "Code-Film" — Gource-Visualisierung des Projekts
rem  (die Animation aus den YouTube-Videos: Dateien = Punkte,
rem   Ordner = Aeste, jeder Commit laesst den Baum wachsen)
rem
rem  Bedienung:  Esc = beenden, Leertaste = Pause,
rem              Mausrad = Zoom, Ziehen = Kamera, Tab = Dateien
rem  Gource (GPLv3, https://gource.io) wird NICHT mehr mitgeliefert
rem  (TOOL-2: 17 MB Windows-Binaerdateien im oeffentlichen Repo).
rem  Einmal installieren, dann liegt gource.exe im PATH.
rem  Auf Linux: Code-Film.sh benutzen (Gource aus dem Paketmanager).
rem  Beide Skripte tragen dieselben Parameter: wer einen aendert,
rem  aendert bitte beide.
rem ============================================================
cd /d "%~dp0"
where gource >nul 2>nul
if errorlevel 1 (
  echo [Code-Film] 'gource' ist nicht installiert.
  echo             Windows-Installer: https://gource.io  ^(danach neues Fenster oeffnen^)
  echo             Linux: Code-Film.sh benutzen.
  pause
  exit /b 1
)
gource ^
  --title "LightOS - Entstehung des Codes" ^
  --seconds-per-day 4 ^
  --auto-skip-seconds 1 ^
  --file-idle-time 0 ^
  --max-file-lag 0.5 ^
  --bloom-multiplier 0.8 ^
  --bloom-intensity 0.9 ^
  --highlight-users ^
  --highlight-dirs ^
  --dir-name-depth 2 ^
  --font-size 18 ^
  --key ^
  -1280x800 ^
  .
