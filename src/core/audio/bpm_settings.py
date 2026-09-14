"""BPM-Manager-Einstellungen: Laden/Migrieren/Speichern in ui_prefs.json + Anwenden.

EINE autoritative Quelle fuer Quelle/Geraet/Modus/Grenzen/Takt: ``DEFAULTS`` (v2).
Wird beim App-Start (``boot``) angewandt; der BPM-Tab liest danach den
Backend-Zustand und speichert Aenderungen (entprellt) hierher. Liegt wie die
uebrigen UI-Prefs in ``<app_data_dir>/ui_prefs.json``, Sektion ``bpm_settings``.

Persistenz v2 (BPM-07):
- ``version``-Feld; ``migrate()`` hebt v1 (ohne Feld) auf v2, prueft jeden Key
  auf Typ/Bereich (Rueckfall Default) und verwirft unbekannte Keys mit Log.
- ``version > VERSION`` (Datei einer neueren LightOS-Version): nicht anfassen,
  Defaults verwenden, ``save_settings`` schreibt die Sektion NICHT.
- Schreiben atomar (tmp im selben Ordner + flush + fsync + os.replace);
  Fremd-Sektionen (``live_view`` u. a.) bleiben (Read-Modify-Write).
- Das erste v2-Schreiben ueber einer v1-Sektion sichert die Datei einmalig als
  ``ui_prefs.json.v1.bak`` (Rueckfall = zuruecknennen).
"""
from __future__ import annotations
import json
import os
import shutil
import tempfile
from src.core.paths import app_data_dir

_PREFS_DIR = app_data_dir()
_PREFS_PATH = os.path.join(_PREFS_DIR, "ui_prefs.json")
_KEY = "bpm_settings"
VERSION = 2

# Reihenfolge = Schreibreihenfolge in der Datei (Migrationstabelle plan.md 3.).
DEFAULTS: dict = {
    "version": VERSION,
    "source": "loopback",        # loopback (PC-Audio) | input (Mikro/Line-In) | os2l | song | off
    "device": None,              # Geraetename (wird auch fuer PC-Audio gemerkt)
    "mode": "auto",              # Manager-Modus: auto | manual
    "min_bpm": 60,               # untere AUTO-Grenze („Tiefen")
    "max_bpm": 200,              # obere AUTO-Grenze („Hoehen")
    "beats_per_bar": 4,          # Schlaege pro Takt (4 = Viertakt, 16 = Sechzehntakt)
    "phase_accurate_beats": True,  # Lied-Analyse: Beats taktgenau aufs Beatgrid
    # v2 geduldet — fallen in S4 (v3) zusammen mit ihren Reglern:
    "sensitivity": 1.3,          # Detektor-Empfindlichkeit (seit S1 ohne Wirkung)
    "smoothing": 0.3,            # Detektor-Glaettung (seit S1 ohne Wirkung)
    "subdivision": 1,            # Sub-Ticks pro Beat (1 = aus)
}

SOURCES = ("loopback", "input", "os2l", "song", "off")
MODES = ("auto", "manual")
# Bereiche folgen den UI-Reglern (Spinboxen 20..400 bzw. 1..32), damit kein Wert,
# den der Tab schreiben kann, beim naechsten Laden auf den Default zurueckfaellt.
_BPM_RANGE = (20, 400)
_BPB_RANGE = (1, 32)
_SUBDIV_RANGE = (1, 16)
_V1_ONLY_KEYS = ("auto_default", "mode_default", "source_mode", "input_device")


def _log(msg: str) -> None:
    print(f"[bpm_settings] {msg}")


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check(key: str, v):
    """Typ-/Bereichspruefung EINES v2-Keys. Liefert (gueltig, normierter Wert)."""
    if key == "version":
        return _is_int(v) and v == VERSION, VERSION
    if key == "source":
        return isinstance(v, str) and v in SOURCES, v
    if key == "device":
        if v is None:
            return True, None
        return isinstance(v, str), (v or None)
    if key == "mode":
        return isinstance(v, str) and v in MODES, v
    if key in ("min_bpm", "max_bpm"):
        return _is_int(v) and _BPM_RANGE[0] <= v <= _BPM_RANGE[1], v
    if key == "beats_per_bar":
        return _is_int(v) and _BPB_RANGE[0] <= v <= _BPB_RANGE[1], v
    if key == "phase_accurate_beats":
        return isinstance(v, bool), v
    if key in ("sensitivity", "smoothing"):
        return _is_num(v), (float(v) if _is_num(v) else v)
    if key == "subdivision":
        return _is_int(v) and _SUBDIV_RANGE[0] <= v <= _SUBDIV_RANGE[1], v
    return False, v


def _merge_checked(target: dict, src: dict) -> dict:
    """Uebernimmt gueltige v2-Werte aus ``src`` in ``target`` (Key fuer Key).
    Ungueltige Werte bleiben beim bisherigen Wert von ``target`` (Default bzw.
    Dateistand), unbekannte Keys werden verworfen — beides mit Log."""
    for k, v in src.items():
        if k == "version":
            continue
        if k not in DEFAULTS:
            _log(f"unbekannter Key verworfen: {k}={v!r}")
            continue
        ok, val = _check(k, v)
        if ok:
            target[k] = val
        else:
            _log(f"{k}={v!r} ungueltig → {target[k]!r}")
    if not target["min_bpm"] < target["max_bpm"]:
        _log(f"min_bpm={target['min_bpm']} >= max_bpm={target['max_bpm']} → "
             f"{DEFAULTS['min_bpm']}/{DEFAULTS['max_bpm']}")
        target["min_bpm"], target["max_bpm"] = DEFAULTS["min_bpm"], DEFAULTS["max_bpm"]
    target["version"] = VERSION
    return target


def _normalize(raw: dict) -> dict:
    """Vollstaendiges v2-Dict aus einem (ggf. teilweisen/fehlerhaften) Dict."""
    return _merge_checked(dict(DEFAULTS), raw or {})


def _v1_to_v2(raw: dict) -> dict:
    """Schluesselumbau v1 → v2 (Migrationstabelle plan.md 3.); die Typpruefung
    der uebernommenen Werte macht anschliessend ``_normalize``."""
    out = {k: v for k, v in raw.items() if k not in _V1_ONLY_KEYS and k != "version"}
    auto = raw.get("auto_default", True)
    if not isinstance(auto, bool):
        _log(f"v1→v2: auto_default={auto!r} ungueltig → True")
        auto = True
    src = raw.get("source_mode", "loopback")
    if not (isinstance(src, str) and src in SOURCES):
        _log(f"v1→v2: source_mode={src!r} ungueltig → loopback")
        src = "loopback"
    out["source"] = "off" if auto is False else src
    out["device"] = raw.get("input_device") if src == "input" else None
    out["mode"] = raw.get("mode_default", "auto")
    return out


def migrate(raw) -> dict:
    """Hebt eine gelesene ``bpm_settings``-Sektion auf v2.
    Fehlt ``version`` → v1. ``version > VERSION`` → Defaults (Datei bleibt fremd).
    Typpruefung je Key mit Rueckfall auf den Default; unbekannte Keys weg."""
    if not isinstance(raw, dict):
        if raw not in (None, {}):
            _log(f"Sektion ist kein Objekt ({type(raw).__name__}) → Defaults")
        return dict(DEFAULTS)
    ver = raw.get("version", 1)
    if not _is_int(ver) or ver < 1:
        _log(f"version={ver!r} ungueltig → als v1 behandelt")
        ver = 1
    if ver > VERSION:
        _log(f"version={ver} ist neuer als {VERSION} → Datei bleibt unangetastet, Defaults")
        return dict(DEFAULTS)
    if ver == 1:
        raw = _v1_to_v2(raw)
    return _normalize(raw)


def _read_all() -> dict:
    """Ganze ui_prefs.json (alle Sektionen); {} wenn fehlend/unlesbar."""
    try:
        with open(_PREFS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        _log(f"ui_prefs.json unlesbar ({e}) → leer")
        return {}
    return data if isinstance(data, dict) else {}


def load_settings() -> dict:
    """Liest die BPM-Einstellungen als vollstaendiges v2-Dict."""
    return migrate(_read_all().get(_KEY))


def _is_v1_section(section) -> bool:
    return isinstance(section, dict) and "version" not in section


def _backup_v1_once() -> None:
    """Erstes v2-Schreiben ueber einer v1-Sektion: Originaldatei einmalig sichern."""
    bak = f"{_PREFS_PATH}.v1.bak"
    if os.path.exists(bak) or not os.path.exists(_PREFS_PATH):
        return
    try:
        shutil.copyfile(_PREFS_PATH, bak)
        _log(f"v1-Sicherung angelegt: {os.path.basename(bak)}")
    except OSError as e:
        _log(f"v1-Sicherung fehlgeschlagen: {e}")


def _write_atomic(all_prefs: dict) -> None:
    """tmp im selben Ordner + flush + fsync + os.replace — nie eine halbe Datei
    (Vorlage src/web/remote_settings.py). Bei Abbruch bleibt die alte Datei,
    die tmp wird entfernt."""
    prefs_dir = os.path.dirname(_PREFS_PATH) or "."
    fd, tmp = tempfile.mkstemp(prefix=".ui_prefs-", suffix=".json.tmp", dir=prefs_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(all_prefs, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _PREFS_PATH)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def save_settings(settings: dict) -> None:
    """Schreibt die BPM-Einstellungen (v2, atomar), ohne fremde ui_prefs-Sektionen
    zu verlieren. ``settings`` darf teilweise sein — fehlende Keys behalten den
    Dateistand; ungueltige Werte werden mit Log verworfen."""
    try:
        os.makedirs(os.path.dirname(_PREFS_PATH) or _PREFS_DIR, exist_ok=True)
        all_prefs = _read_all()
        old = all_prefs.get(_KEY)
        if isinstance(old, dict):
            ver = old.get("version", 1)
            if _is_int(ver) and ver > VERSION:
                _log(f"version={ver} ist neuer als {VERSION} → nicht ueberschrieben")
                return
            if _is_v1_section(old):
                _backup_v1_once()
        all_prefs[_KEY] = _merge_checked(migrate(old), settings or {})
        _write_atomic(all_prefs)
    except Exception as e:
        _log(f"save error: {e}")


def _apply(what: str, fn) -> None:
    """Ein Schritt von apply_to_backend — ein Fehler ueberspringt nur diesen."""
    try:
        fn()
    except Exception as e:
        _log(f"apply {what}: {e}")


def apply_to_backend(settings: dict) -> None:
    """Spielt Grenzen/Modus/Takt (+ geduldet Sensitivity/Smoothing/Subdivision) in
    Detektor + Manager + MusicDirector. Jeder Key einzeln abgesichert: ein
    fehlender Setter laesst die uebrigen Werte nicht aus.
    ``BPMManager.set_bounds`` spiegelt die Grenzen in den Detektor (eine Quelle)."""
    s = _normalize(settings)
    det = mgr = None
    try:
        from src.core.audio.beat_detector import get_beat_detector
        det = get_beat_detector()
    except Exception as e:
        _log(f"apply: kein Detektor ({e})")
    try:
        from src.core.engine.bpm_manager import get_bpm_manager
        mgr = get_bpm_manager()
    except Exception as e:
        _log(f"apply: kein Manager ({e})")
    if det is not None:
        _apply("sensitivity", lambda: det.set_sensitivity(s["sensitivity"]))
        _apply("smoothing", lambda: det.set_smoothing(s["smoothing"]))
    if mgr is not None:
        _apply("bounds", lambda: mgr.set_bounds(s["min_bpm"], s["max_bpm"]))
        _apply("mode", lambda: mgr.set_mode(s["mode"]))
        if hasattr(mgr, "set_beats_per_bar"):
            _apply("beats_per_bar", lambda: mgr.set_beats_per_bar(s["beats_per_bar"]))
            _apply("subdivision", lambda: mgr.set_subdivision(s["subdivision"]))

    def _phase():
        from src.core.audio.music_show import get_music_director
        get_music_director().set_phase_accurate(s["phase_accurate_beats"])
    _apply("phase_accurate_beats", _phase)


def start_auto_if_configured(settings: dict) -> bool:
    """Startet die konfigurierte Audio-Quelle (``source``: Loopback/Eingang mit
    ``device`` bzw. OS2L-Server); ``off``/``song`` starten nichts. Danach wird der
    gespeicherte Manager-``mode`` erneut gesetzt, weil ``use_audio_source(True)``
    AUTO erzwingt — Capture haengt an der Quelle, der Modus am Manager.
    In Tests/Headless via ``LIGHTOS_NO_AUDIO_AUTOSTART`` unterdrueckbar."""
    if os.environ.get("LIGHTOS_NO_AUDIO_AUTOSTART"):
        return False
    s = _normalize(settings)
    source, device, mode = s["source"], s["device"], s["mode"]
    if source not in ("loopback", "input", "os2l"):
        return False
    try:
        from src.core.engine.bpm_manager import get_bpm_manager
        mgr = get_bpm_manager()
        if source == "os2l":
            # OS2L ist der externe Treiber: KEIN Audio-Capture starten.
            mgr.use_audio_source(False)
            from src.core.audio.os2l import get_os2l_server
            get_os2l_server().start()
        else:
            from src.core.audio.capture import get_audio_capture
            get_audio_capture().set_source_mode(source, device)
            mgr.use_audio_source(True)
        mgr.set_mode(mode)
        return True
    except Exception as e:
        _log(f"auto-start error: {e}")
        return False


def boot() -> dict:
    """App-Start: laden, anwenden, ggf. Audio-Quelle starten. Gibt die geladenen
    Einstellungen zurueck; der BPM-Tab liest danach den Backend-Zustand."""
    s = load_settings()
    apply_to_backend(s)
    start_auto_if_configured(s)
    return s
