#!/usr/bin/env bash
# ============================================================
#  LightOS "Code-Film" — Gource-Visualisierung des Projekts
#  (die Animation aus den YouTube-Videos: Dateien = Punkte,
#   Ordner = Aeste, jeder Commit laesst den Baum wachsen)
#
#  Bedienung:  Esc = beenden, Leertaste = Pause,
#              Mausrad = Zoom, Ziehen = Kamera, Tab = Dateien
#
#  Linux-Pendant zu Code-Film.bat. Gource kommt hier aus der
#  Distribution (seit TOOL-2 liegt auch fuer Windows keine Fassung mehr
#  im Repo). Dieselben Parameter, damit beide Seiten denselben Film
#  erzeugen — wer einen aendert, aendert bitte beide.
# ============================================================
set -u
cd "$(dirname "$0")" || exit 2

if ! command -v gource >/dev/null 2>&1; then
    echo "[Code-Film] 'gource' ist nicht installiert."
    echo "            Debian/Ubuntu/Mint:  sudo apt install gource"
    echo "            Fedora:              sudo dnf install gource"
    echo "            Arch:                sudo pacman -S gource"
    exit 1
fi

exec gource \
  --title "LightOS - Entstehung des Codes" \
  --seconds-per-day 4 \
  --auto-skip-seconds 1 \
  --file-idle-time 0 \
  --max-file-lag 0.5 \
  --bloom-multiplier 0.8 \
  --bloom-intensity 0.9 \
  --highlight-users \
  --highlight-dirs \
  --dir-name-depth 2 \
  --font-size 18 \
  --key \
  -1280x800 \
  .
