"""Cache fuer Offline-BPM-Analysen: (Datei + Analyse-Parameter) → Timeline + Wellenform.

Damit ein bereits analysierter Song beim erneuten Laden **sofort** da ist (kein
Dekodieren/Analysieren noetig) und die Ordner-Stapelanalyse Ergebnisse persistiert.
Liegt user-global in ``%APPDATA%/LightOS/bpm_analysis_cache.json``. Der Schluessel
enthaelt Datei-mtime+groesse + Engine/Genre/Takt → aendert sich die Datei oder ein
Parameter, wird neu analysiert.
"""
from __future__ import annotations
import os
import json

_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS")
_PATH = os.path.join(_DIR, "bpm_analysis_cache.json")
_MAX_ENTRIES = 400


def _key(path: str, engine: str, genre: str, takt) -> str:
    try:
        st = os.stat(path)
        return f"{os.path.abspath(path)}|{int(st.st_mtime)}|{st.st_size}|{engine}|{genre}|{takt}"
    except Exception:
        return ""


def _load() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save(d: dict) -> None:
    try:
        os.makedirs(_DIR, exist_ok=True)
        if len(d) > _MAX_ENTRIES:                 # aelteste (Einfuege-Reihenfolge) raus
            for k in list(d.keys())[:len(d) - _MAX_ENTRIES]:
                d.pop(k, None)
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception as e:
        print(f"[bpm_cache] save error: {e}")


def get(path: str, engine: str, genre: str, takt) -> dict | None:
    """Cache-Treffer als ``{"timeline": {...}, "peaks": [...]}`` oder None."""
    k = _key(path, engine, genre, takt)
    if not k:
        return None
    entry = _load().get(k)
    return entry if isinstance(entry, dict) and entry.get("timeline") else None


def put(path: str, engine: str, genre: str, takt, timeline_dict: dict, peaks) -> None:
    k = _key(path, engine, genre, takt)
    if not k or not timeline_dict:
        return
    d = _load()
    d[k] = {"timeline": timeline_dict, "peaks": [round(float(p), 3) for p in (peaks or [])]}
    _save(d)


def clear() -> None:
    try:
        os.remove(_PATH)
    except Exception:
        pass
