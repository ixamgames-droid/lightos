"""BPM-Manager-Einstellungen: Laden/Speichern in ui_prefs.json + Anwenden.

EINE autoritative Quelle fuer Grenzen/Sensitivity/Smoothing/Quelle/AUTO-Default.
Wird beim App-Start (``boot``) angewandt und vom BPM-Tab bei Aenderungen
gespeichert. Liegt wie die uebrigen UI-Prefs in ``%APPDATA%/LightOS/ui_prefs.json``.
"""
from __future__ import annotations
import json
import os
from src.core.paths import app_data_dir

_PREFS_DIR = app_data_dir()
_PREFS_PATH = os.path.join(_PREFS_DIR, "ui_prefs.json")
_KEY = "bpm_settings"

DEFAULTS: dict = {
    "auto_default": True,        # AUTO-Erkennung beim Start aktivieren
    "mode_default": "auto",      # auto | manual
    "min_bpm": 60,               # untere AUTO-Grenze („Tiefen")
    "max_bpm": 200,              # obere AUTO-Grenze („Hoehen")
    "sensitivity": 1.3,          # Detektor-Empfindlichkeit (0.5..3.0)
    "smoothing": 0.3,            # Detektor-Glaettung (0..1)
    "source_mode": "loopback",   # loopback (PC-Audio/Player) | input (Mikro/Line-In) | os2l (externer OS2L-Treiber)
    "input_device": None,        # Geraetename fuer source_mode=input
    "beats_per_bar": 4,          # Schlaege pro Takt (4 = Viertakt, 16 = Sechzehntakt)
    "subdivision": 1,            # Sub-Ticks pro Beat (1 = aus)
    "phase_accurate_beats": True,  # Lied-Analyse: Beats taktgenau aufs Beatgrid (statt nur BPM-Wert)
}


def load_settings() -> dict:
    """Liest die BPM-Einstellungen (mit Defaults aufgefuellt)."""
    raw = {}
    try:
        with open(_PREFS_PATH, encoding="utf-8") as f:
            raw = (json.load(f) or {}).get(_KEY, {}) or {}
    except Exception:
        raw = {}
    out = dict(DEFAULTS)
    for k in DEFAULTS:
        if k in raw:
            out[k] = raw[k]
    return out


def save_settings(settings: dict) -> None:
    """Schreibt die BPM-Einstellungen, ohne fremde ui_prefs-Keys zu verlieren."""
    try:
        os.makedirs(_PREFS_DIR, exist_ok=True)
        all_prefs = {}
        try:
            with open(_PREFS_PATH, encoding="utf-8") as f:
                all_prefs = json.load(f) or {}
        except Exception:
            all_prefs = {}
        cur = dict(DEFAULTS)
        cur.update(all_prefs.get(_KEY, {}) or {})
        for k in DEFAULTS:
            if k in settings:
                cur[k] = settings[k]
        all_prefs[_KEY] = cur
        with open(_PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(all_prefs, f, indent=2)
    except Exception as e:
        print(f"[bpm_settings] save error: {e}")


def apply_to_backend(settings: dict) -> None:
    """Spielt Sensitivity/Smoothing/Grenzen/Modus in Detektor + Manager.
    ``BPMManager.set_bounds`` spiegelt die Grenzen in den Detektor (eine Quelle)."""
    try:
        from src.core.engine.bpm_manager import get_bpm_manager
        from src.core.audio.beat_detector import get_beat_detector
        det = get_beat_detector()
        det.set_sensitivity(float(settings.get("sensitivity", 1.3)))
        det.set_smoothing(float(settings.get("smoothing", 0.3)))
        mgr = get_bpm_manager()
        mgr.set_bounds(int(settings.get("min_bpm", 60)),
                       int(settings.get("max_bpm", 200)))
        mgr.set_mode(settings.get("mode_default", "auto"))
        if hasattr(mgr, "set_beats_per_bar"):
            mgr.set_beats_per_bar(int(settings.get("beats_per_bar", 4)))
            mgr.set_subdivision(int(settings.get("subdivision", 1)))
        try:
            from src.core.audio.music_show import get_music_director
            get_music_director().set_phase_accurate(
                bool(settings.get("phase_accurate_beats", True)))
        except Exception:
            pass
    except Exception as e:
        print(f"[bpm_settings] apply error: {e}")


def start_auto_if_configured(settings: dict) -> bool:
    """Startet bei ``auto_default`` die Audio-Quelle (WASAPI-Loopback bzw.
    Eingang). In Tests/Headless via ``LIGHTOS_NO_AUDIO_AUTOSTART`` unterdrueckbar."""
    if os.environ.get("LIGHTOS_NO_AUDIO_AUTOSTART"):
        return False
    if not settings.get("auto_default", True):
        return False
    try:
        from src.core.engine.bpm_manager import get_bpm_manager
        mode = settings.get("source_mode", "loopback")
        if mode == "os2l":
            # OS2L ist der externe Treiber: KEIN Audio-Capture starten.
            get_bpm_manager().use_audio_source(False)
            from src.core.audio.os2l import get_os2l_server
            get_os2l_server().start()
            return True
        from src.core.audio.capture import get_audio_capture
        cap = get_audio_capture()
        cap.set_source_mode(mode, settings.get("input_device"))
        get_bpm_manager().use_audio_source(True)
        return True
    except Exception as e:
        print(f"[bpm_settings] auto-start error: {e}")
        return False


def boot() -> dict:
    """App-Start: laden, anwenden, ggf. AUTO-Capture starten. Gibt die geladenen
    Einstellungen zurueck (der BPM-Tab uebernimmt sie in seine Regler)."""
    s = load_settings()
    apply_to_backend(s)
    start_auto_if_configured(s)
    return s
