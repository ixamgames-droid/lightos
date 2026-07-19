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
import tempfile
import threading
from src.core.paths import app_data_dir

_DIR = app_data_dir()
_PATH = os.path.join(_DIR, "bpm_analysis_cache.json")
_MAX_ENTRIES = 400

# Serialisiert das Read-modify-write in put() gegen parallele Schreiber im selben
# Prozess (z. B. Stapelanalyse aus mehreren Threads) → kein Lost-Update. Jeder put()
# liest zudem frisch von der Platte (_load), sodass das Fenster fuer prozess-uebergreifende
# Konflikte minimal bleibt; der eigentliche Schreibvorgang ist per temp+os.replace atomar.
_lock = threading.Lock()


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
        # Atomar schreiben: ERST vollstaendig in eine Temp-Datei im SELBEN Verzeichnis,
        # DANN per os.replace() ueber den Zielpfad ziehen (atomic rename). Ein Crash /
        # voller Datentraeger / paralleler Schreiber hinterlaesst so nie eine halbe oder
        # 0-Byte-grosse Ziel-Datei — entweder die alte oder die neue vollstaendige Version.
        fd, tmp_path = tempfile.mkstemp(prefix=".bpm_cache-", suffix=".json.tmp", dir=_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(d, f)
            os.replace(tmp_path, _PATH)
        except BaseException:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        print(f"[bpm_cache] save error: {e}")


def get(path: str, engine: str, genre: str, takt) -> dict | None:
    """Cache-Treffer als ``{"timeline": {...}, "peaks": [...]}`` oder None."""
    k = _key(path, engine, genre, takt)
    if not k:
        return None
    # BPM-03b (Review): unter _lock lesen. Sonst kann ein paralleler
    # put()->_save()->os.replace() auf Windows eine Sharing-Violation
    # (PermissionError) werfen, während dieser Reader die Datei offen hält — der
    # Schreibvorgang wird dann still verworfen (Cache-Verlust). Der Writer hält
    # _lock über den gesamten _save(); durch dasselbe Lock hier liest kein Reader
    # mehr, während die Zieldatei ersetzt wird.
    with _lock:
        entry = _load().get(k)
    return entry if isinstance(entry, dict) and entry.get("timeline") else None


def put(path: str, engine: str, genre: str, takt, timeline_dict: dict, peaks) -> None:
    k = _key(path, engine, genre, takt)
    if not k or not timeline_dict:
        return
    entry = {"timeline": timeline_dict, "peaks": [round(float(p), 3) for p in (peaks or [])]}
    # Read-modify-write unter Lock: frisch von der Platte laden, mergen, atomar schreiben
    # → kein Lost-Update, wenn parallele Schreiber (z. B. Stapelanalyse) gleichzeitig
    # unterschiedliche Songs cachen.
    with _lock:
        d = _load()
        d[k] = entry
        _save(d)


def clear() -> None:
    try:
        os.remove(_PATH)
    except Exception:
        pass
