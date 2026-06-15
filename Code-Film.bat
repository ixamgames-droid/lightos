@echo off
rem ============================================================
rem  LightOS "Code-Film" — Gource-Visualisierung des Projekts
rem  (die Animation aus den YouTube-Videos: Dateien = Punkte,
rem   Ordner = Aeste, jeder Commit laesst den Baum wachsen)
rem
rem  Bedienung:  Esc = beenden, Leertaste = Pause,
rem              Mausrad = Zoom, Ziehen = Kamera, Tab = Dateien
rem  Gource 0.53 (GPLv3, https://gource.io) liegt in tools\gource\
rem ============================================================
cd /d "%~dp0"
tools\gource\gource.exe ^
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
