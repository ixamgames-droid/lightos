"""BPM-Manager-Einstellungen: Laden/Migrieren/Speichern in ui_prefs.json + Anwenden.

EINE autoritative Quelle fuer Quelle/Geraet/Modus/Grenzen/Takt/Beat-Latenz: ``DEFAULTS`` (v3).
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
- Eine vorhandene, aber unlesbare ``ui_prefs.json`` (halbe Datei eines anderen,
  nicht atomaren Schreibers) wird vor dem ersten Ueberschreiben einmalig als
  ``ui_prefs.json.corrupt.bak`` gesichert — die Fremd-Sektionen darin sind
  sonst weg, ohne dass es jemand merkt.
- ``device`` ist bei ``source == "input"`` das Eingangsgeraet und bei PC-Audio
  (loopback) ab S5 die ``sink_id`` des Ausgabegeraets (None = Standard). Ein
  Mikrofonname wird fuer loopback NIE benutzt: der SourceController laesst nur
  aktuelle sink_ids durch (sonst naehme der Loopback das Mikrofon auf).

Persistenz v3 (BPM-09, S4): ``beat_latency_ms`` neu (int −300..300, Default 0);
``sensitivity``/``smoothing``/``subdivision`` entfallen mit ihren Reglern —
``migrate`` verwirft sie mit Log „v2->v3: verworfen …". ``apply_to_backend``
ruft ``mgr.set_subdivision(1)`` (Altwert neutralisieren) und
``det.set_beat_latency_ms``. Das erste v3-Schreiben ueber einer v2-Sektion
sichert die Datei einmalig als ``ui_prefs.json.v2.bak``. ACHTUNG Rueckfall:
v2-Code (Stand vor S4) liest eine v3-Datei NICHT — ``version > VERSION`` heisst
dort „Datei bleibt unangetastet, Defaults" und ``save_settings`` schreibt die
Sektion nicht mehr (gemessen mit origin/main). Rueckfall = revert +
``ui_prefs.json.v2.bak`` zuruecknennen, sonst bleibt Robin mit Defaults und ohne
Speichermoeglichkeit zurueck. Der Auto-Start (``start_auto_if_configured``)
laeuft ueber ``bpm_source_controller.get_source_controller().apply`` — dieselbe
Stelle wie die Quelle-Combo, damit der erste Klick auf den bereits aktiven
Eintrag nichts ein zweites Mal startet.
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
VERSION = 3

# Reihenfolge = Schreibreihenfolge in der Datei (Migrationstabelle plan.md 3.).
DEFAULTS: dict = {
    "version": VERSION,
    "source": "loopback",        # loopback (PC-Audio) | input (Mikro/Line-In) | os2l | song | off
    "device": None,              # input: Eingangsname; loopback: sink_id (S5); sonst None
    "mode": "auto",              # Manager-Modus: auto | manual
    "min_bpm": 60,               # untere AUTO-Grenze („Tiefen")
    "max_bpm": 200,              # obere AUTO-Grenze („Hoehen")
    "beats_per_bar": 4,          # Schlaege pro Takt (4 = Viertakt, 16 = Sechzehntakt)
    "phase_accurate_beats": True,  # Lied-Analyse: Beats taktgenau aufs Beatgrid
    "beat_latency_ms": 0,        # v3: Beat-Callback frueher (+) / spaeter (−), ms
}

SOURCES = ("loopback", "input", "os2l", "song", "off")
MODES = ("auto", "manual")
# Bereiche folgen den UI-Reglern (Spinboxen 20..400 bzw. 1..32), damit kein Wert,
# den der Tab schreiben kann, beim naechsten Laden auf den Default zurueckfaellt.
_BPM_RANGE = (20, 400)
_BPB_RANGE = (1, 32)
_LATENCY_RANGE = (-300, 300)
_V1_ONLY_KEYS = ("auto_default", "mode_default", "source_mode", "input_device")
# v2-Keys, die mit ihren Reglern in S4 gefallen sind (Migrationstabelle plan.md 3.).
_V2_DROPPED_KEYS = ("sensitivity", "smoothing", "subdivision")


def _log(msg: str) -> None:
    print(f"[bpm_settings] {msg}")


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check(key: str, v):
    """Typ-/Bereichspruefung EINES v3-Keys. Liefert (gueltig, normierter Wert)."""
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
    if key == "beat_latency_ms":
        return _is_int(v) and _LATENCY_RANGE[0] <= v <= _LATENCY_RANGE[1], v
    return False, v


def _merge_checked(target: dict, src: dict) -> dict:
    """Uebernimmt gueltige v3-Werte aus ``src`` in ``target`` (Key fuer Key).
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
    """Vollstaendiges v3-Dict aus einem (ggf. teilweisen/fehlerhaften) Dict."""
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


def _v2_to_v3(raw: dict) -> dict:
    """v2 → v3: ``sensitivity``/``smoothing``/``subdivision`` fallen (ihre Regler
    sind weg, der Detektor ist seit S1 selbstkalibrierend) — EIN Log nennt die
    verworfenen Werte. ``beat_latency_ms`` kommt ueber die Defaults hinzu."""
    dropped = [f"{k}={raw[k]!r}" for k in _V2_DROPPED_KEYS if k in raw]
    if dropped:
        _log("v2->v3: verworfen " + ", ".join(dropped))
    return {k: v for k, v in raw.items() if k not in _V2_DROPPED_KEYS}


def migrate(raw) -> dict:
    """Hebt eine gelesene ``bpm_settings``-Sektion auf v3 (v1 → v2 → v3).
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
    if ver <= 2:
        raw = _v2_to_v3(raw)
    return _normalize(raw)


class _Unreadable(Exception):
    """ui_prefs.json ist vorhanden, aber kein JSON-Objekt (halbe Datei o. ae.)."""


def _read_all_strict() -> dict:
    """Ganze ui_prefs.json (alle Sektionen); {} wenn fehlend, ``_Unreadable``
    wenn vorhanden-aber-kaputt — damit ``save_settings`` den Kaputt-Fall vom
    Fehlen unterscheiden und die Datei vor dem Ueberschreiben sichern kann."""
    try:
        with open(_PREFS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        raise _Unreadable(str(e)) from e
    if not isinstance(data, dict):
        raise _Unreadable(f"Wurzel ist {type(data).__name__}, kein Objekt")
    return data


def _read_all() -> dict:
    """Ganze ui_prefs.json (alle Sektionen); {} wenn fehlend/unlesbar."""
    try:
        return _read_all_strict()
    except _Unreadable as e:
        _log(f"ui_prefs.json unlesbar ({e}) → leer")
        return {}


def load_settings() -> dict:
    """Liest die BPM-Einstellungen als vollstaendiges v3-Dict."""
    return migrate(_read_all().get(_KEY))


def _is_v1_section(section) -> bool:
    return isinstance(section, dict) and "version" not in section


def _is_v2_section(section) -> bool:
    return isinstance(section, dict) and section.get("version") == 2


def _backup_once(tag: str) -> None:
    """Originaldatei einmalig als ``ui_prefs.json.<tag>.bak`` sichern — ``v1``
    beim ersten v2-Schreiben ueber einer v1-Sektion, ``v2`` beim ersten
    v3-Schreiben ueber einer v2-Sektion (v2-Code liest v3 nicht: Rueckfall =
    zuruecknennen), ``corrupt`` bevor eine unlesbare Datei ueberschrieben wird.
    Eine vorhandene Sicherung bleibt."""
    bak = f"{_PREFS_PATH}.{tag}.bak"
    if os.path.exists(bak) or not os.path.exists(_PREFS_PATH):
        return
    try:
        shutil.copyfile(_PREFS_PATH, bak)
        _log(f"{tag}-Sicherung angelegt: {os.path.basename(bak)}")
    except OSError as e:
        _log(f"{tag}-Sicherung fehlgeschlagen: {e}")


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
    """Schreibt die BPM-Einstellungen (v3, atomar), ohne fremde ui_prefs-Sektionen
    zu verlieren. ``settings`` darf teilweise sein — fehlende Keys behalten den
    Dateistand; ungueltige Werte werden mit Log verworfen."""
    try:
        os.makedirs(os.path.dirname(_PREFS_PATH) or _PREFS_DIR, exist_ok=True)
        try:
            all_prefs = _read_all_strict()
        except _Unreadable as e:
            # Nicht stillschweigend durch eine Nur-bpm_settings-Datei ersetzen:
            # die Fremd-Sektionen (remote_settings, live_view, …) haengen mit drin.
            _log(f"ui_prefs.json unlesbar ({e}) → Sicherung, dann neu geschrieben")
            _backup_once("corrupt")
            all_prefs = {}
        old = all_prefs.get(_KEY)
        if isinstance(old, dict):
            ver = old.get("version", 1)
            if _is_int(ver) and ver > VERSION:
                _log(f"version={ver} ist neuer als {VERSION} → nicht ueberschrieben")
                return
            if _is_v1_section(old):
                _backup_once("v1")
            elif _is_v2_section(old):
                _backup_once("v2")
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
    """Spielt Grenzen/Modus/Takt/Beat-Latenz in Detektor + Manager + MusicDirector.
    Jeder Key einzeln abgesichert: ein fehlender Setter laesst die uebrigen Werte
    nicht aus. ``BPMManager.set_bounds`` spiegelt die Grenzen in den Detektor
    (eine Quelle). Die Unterteilung hat seit v3 keinen Regler mehr und wird auf
    1 (aus) gesetzt, damit kein Altwert im Manager haengen bleibt."""
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
        _apply("beat_latency_ms", lambda: det.set_beat_latency_ms(s["beat_latency_ms"]))
    if mgr is not None:
        _apply("bounds", lambda: mgr.set_bounds(s["min_bpm"], s["max_bpm"]))
        _apply("mode", lambda: mgr.set_mode(s["mode"]))
        if hasattr(mgr, "set_beats_per_bar"):
            _apply("beats_per_bar", lambda: mgr.set_beats_per_bar(s["beats_per_bar"]))
            _apply("subdivision", lambda: mgr.set_subdivision(1))

    def _phase():
        from src.core.audio.music_show import get_music_director
        get_music_director().set_phase_accurate(s["phase_accurate_beats"])
    _apply("phase_accurate_beats", _phase)


def start_auto_if_configured(settings: dict) -> bool:
    """Startet die konfigurierte Audio-Quelle (``source``: Loopback, Eingang mit
    ``device`` bzw. OS2L-Server); ``off``/``song`` starten nichts. Laeuft ueber
    den ``SourceController`` (EINE Stelle fuer Capture/OS2L/Manager, S4): der
    merkt sich den Eintrag, damit der erste Klick auf denselben Eintrag im Tab
    „Erkennung" idempotent bleibt (sonst Doppelstart + Detektor-Reset an der
    Boot-Kante). ``device`` gilt fuer den Eingang und (als sink_id, S5) fuer
    PC-Audio; der Controller verwirft fuer loopback alles, was keine aktuelle
    sink_id ist — dann gilt das Standard-Ausgabegeraet. Der gespeicherte Manager-
    ``mode`` wird vor dem Schalten gesetzt und vom Controller nach
    ``use_audio_source(True)`` (erzwingt AUTO) wiederhergestellt — Capture haengt
    an der Quelle, der Modus am Manager. Ein bereits aktiver Eintrag (Tab war
    schneller) wird nicht erneut geschaltet; die Rueckgabe bleibt True.
    In Tests/Headless via ``LIGHTOS_NO_AUDIO_AUTOSTART`` unterdrueckbar."""
    if os.environ.get("LIGHTOS_NO_AUDIO_AUTOSTART"):
        return False
    s = _normalize(settings)
    source, device, mode = s["source"], s["device"], s["mode"]
    if source not in ("loopback", "input", "os2l"):
        return False
    try:
        from src.core.engine.bpm_manager import get_bpm_manager
        from src.ui.bpm_source_controller import get_source_controller
        mgr = get_bpm_manager()
        mgr.set_mode(mode)
        get_source_controller().apply(source, device if source in ("input", "loopback") else None)
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
