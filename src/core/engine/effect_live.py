"""Gemeinsamer Dispatcher fuer Live-Programming (Phase 6).

Virtuelle Konsole (Slider/Button/Encoder/Color-Picker) UND MIDI nutzen genau
diese eine Stelle, um Effekt-Parameter live zu setzen oder Aktionen auszuloesen
— egal ob auf einem fest gebundenen Effekt (``function_id``) oder dem gerade
aktiven Effekt (zuletzt gestartet).

So bleibt das Wissen darueber, *welche* Parameter ein Effekt hat und *wie* man
sie setzt, ausschliesslich im Effekt (``list_params``/``set_param``/``do_action``)
— die Bedienelemente kennen nur einen Parameter-Key bzw. einen Aktions-Namen.
Dadurch koennen VC und MIDI (und spaeter andere Hardware) dieselben Parameter
und Aktionen steuern, ohne dass irgendwo hartkodiertes Effekt-Wissen liegt.
"""
from __future__ import annotations
from copy import deepcopy
from weakref import WeakKeyDictionary


# ── Live-Edit-Slots (benannte Bearbeitungsziele) ───────────────────────────────
# Idee „Live-Bearbeitung": ein Effekt-Pad macht seinen Effekt zum aktiven Ziel
# eines benannten Slots (z. B. "MH" oder "MX"); die Fader/Farb-Kacheln desselben
# Slots bearbeiten dann GENAU diesen Effekt — pro Quadrant/Slot unabhängig,
# ohne dass jeder Fader fest an eine function_id gebunden werden muss.
_edit_targets: dict[str, int] = {}

# Erster serialisierbarer Zustand vor einer Live-Aenderung. Die laufenden
# Effektobjekte duerfen fuer die direkte Vorschau weiter mutiert werden; beim
# Show-Save liefert ``serialization_dict`` jedoch diese Basis zurueck. So bleiben
# VC-/MIDI-Aenderungen auf die aktuelle Show-Sitzung begrenzt.
_live_baselines: WeakKeyDictionary = WeakKeyDictionary()


def set_edit_target(slot: str, function_id) -> None:
    """Merkt ``function_id`` als aktives Bearbeitungsziel für ``slot``."""
    if not slot:
        return
    if function_id is None:
        _edit_targets.pop(slot, None)
    else:
        try:
            _edit_targets[slot] = int(function_id)
        except (TypeError, ValueError):
            pass


def get_edit_target(slot: str):
    """function_id des aktuellen Bearbeitungsziels von ``slot`` (oder None)."""
    return _edit_targets.get(slot) if slot else None


def clear_edit_targets() -> None:
    """Alle Slots leeren (z. B. bei neuer Show)."""
    _edit_targets.clear()


def clear_live_overrides() -> None:
    """Vergisst alle Laufzeit-Baselines (beim Laden/Anlegen einer Show)."""
    _live_baselines.clear()


def resolve_target(function_id=None):
    """Ziel-Funktion bestimmen: feste ``function_id`` oder der aktive Effekt."""
    try:
        from .function_manager import get_function_manager
        fm = get_function_manager()
    except Exception:
        return None
    if function_id is not None:
        try:
            return fm.get(int(function_id))
        except (TypeError, ValueError):
            return None
    return fm.active_function()


def _supports(fn) -> bool:
    return fn is not None and hasattr(fn, "list_params") and hasattr(fn, "set_param")


def _spec_for(fn, key):
    for s in fn.list_params():
        if s.key == key:
            return s
    return None


def _serialized(fn) -> dict:
    """Tiefe Kopie, weil mehrere ``to_dict``-Implementierungen Listen/Dicts des
    lebenden Effekts direkt zurueckgeben."""
    return deepcopy(fn.to_dict())


def _apply_live_mutation(fn, mutation) -> bool:
    """Mutation ausfuehren und nur bei einer persistent sichtbaren Aenderung den
    Zustand DAVOR als Sitzungs-Baseline merken."""
    if fn in _live_baselines:
        return bool(mutation())
    before = _serialized(fn)
    changed = bool(mutation())
    if changed and _serialized(fn) != before:
        _live_baselines[fn] = before
    return changed


def begin_live_edit(function_id=None) -> bool:
    """Baseline vor einer direkten Mutation eines verschachtelten Objekts sichern.

    Wird z. B. vom Farb-Swatch benutzt, das eine ``ColorSequence`` direkt aendert.
    """
    fn = resolve_target(function_id)
    if not _supports(fn):
        return False
    if fn not in _live_baselines:
        _live_baselines[fn] = _serialized(fn)
    return True


def serialization_dict(fn) -> dict:
    """Persistierbaren Zustand liefern: Preset-Basis statt laufendem Live-Override."""
    baseline = _live_baselines.get(fn)
    return deepcopy(baseline) if baseline is not None else fn.to_dict()


def commit_live_override(function_id=None) -> bool:
    """Aktuellen Live-Zustand wieder als normal speicherbar markieren."""
    fn = resolve_target(function_id)
    if fn is None:
        return False
    _live_baselines.pop(fn, None)
    return True


def discard_live_override_tracking(function_id=None) -> bool:
    """Tracking entfernen, nachdem ein Effekt selbst auf sein Preset zurueckfiel."""
    return commit_live_override(function_id)


def list_params(function_id=None) -> list:
    """ParamSpecs des Zieleffekts (fuer eine dynamische Bindungs-UI)."""
    fn = resolve_target(function_id)
    return list(fn.list_params()) if _supports(fn) else []


def get_param(key, function_id=None):
    fn = resolve_target(function_id)
    return fn.get_param(key) if _supports(fn) else None


def set_param(key, value, function_id=None) -> bool:
    """Absoluter Wert (z. B. Color-Picker, Select)."""
    fn = resolve_target(function_id)
    if not _supports(fn):
        return False
    ok = _apply_live_mutation(fn, lambda: fn.set_param(key, value))
    # Live-Bus-Wechsel taktgleich machen: aendert sich tempo_bus_id an einem
    # LAUFENDEN Effekt (VC-Bus-Selector, Command-Line, MIDI …), sofort sauber auf
    # das neue Beat-Raster re-ankern — sonst springt der Effekt mit stehengebliebenem
    # _beat_anchor auf eine zufaellige Phase, bis das naechste Sync kommt.
    if ok and key == "tempo_bus_id":
        try:
            if getattr(fn, "is_running", False) and hasattr(fn, "sync_phase"):
                fn.sync_phase()
        except Exception:
            pass
    return ok


def set_param_normalized(key, norm, function_id=None) -> bool:
    """0..1 (Fader / MIDI-CC) auf den Wertebereich der ParamSpec abbilden.

    bool → an/aus ab 0.5; select → gleichmaessig auf die Optionen; int/float →
    linear in [min, max]. Wirkt sofort, weil _render jeden Frame frisch liest."""
    fn = resolve_target(function_id)
    if not _supports(fn):
        return False
    norm = max(0.0, min(1.0, float(norm)))
    spec = _spec_for(fn, key)
    if spec is None:
        return _apply_live_mutation(fn, lambda: fn.set_param(key, norm))
    if spec.kind == "bool":
        return _apply_live_mutation(fn, lambda: fn.set_param(key, norm >= 0.5))
    if spec.kind == "select":
        opts = spec.options or ()
        if not opts:
            return False
        i = min(len(opts) - 1, int(norm * len(opts)))
        return _apply_live_mutation(fn, lambda: fn.set_param(key, opts[i]))
    lo, hi = float(spec.min), float(spec.max)
    if hi <= lo:
        hi = lo + 1.0
    val = lo + (hi - lo) * norm
    if spec.kind == "int":
        val = int(round(val))
    return _apply_live_mutation(fn, lambda: fn.set_param(key, val))


def adjust_param(key, delta_norm, function_id=None) -> bool:
    """Relativ (Encoder/Speed-Dial): aktueller Wert ± delta·Bereich, geklemmt."""
    fn = resolve_target(function_id)
    if not _supports(fn):
        return False
    spec = _spec_for(fn, key)
    if spec is None or spec.kind in ("bool", "select", "color", "color_sequence", "action"):
        return False
    lo, hi = float(spec.min), float(spec.max)
    if hi <= lo:
        hi = lo + 1.0
    try:
        cur = float(fn.get_param(key))
    except (TypeError, ValueError):
        cur = lo
    val = max(lo, min(hi, cur + (hi - lo) * float(delta_norm)))
    if spec.kind == "int":
        val = int(round(val))
    return _apply_live_mutation(fn, lambda: fn.set_param(key, val))


def do_action(action, function_id=None, **kw) -> bool:
    """Aktion ausloesen (Buttons): addColor/nextColor/toggleBounce/clear_live_override …"""
    fn = resolve_target(function_id)
    if fn is None or not hasattr(fn, "do_action"):
        return False
    return _apply_live_mutation(fn, lambda: fn.do_action(action, **kw))


def list_actions(function_id=None) -> list:
    """(key, label)-Paare der Live-Aktionen des Zieleffekts.

    Funktionen, die ``list_actions`` implementieren (EFX, Matrix), liefern ihre
    eigene Liste — die Bindungs-UI zeigt damit nur sinnvolle Aktionen an."""
    fn = resolve_target(function_id)
    if fn is None or not hasattr(fn, "list_actions"):
        return []
    try:
        return [(str(k), str(lbl)) for k, lbl in fn.list_actions()]
    except Exception:
        return []


def default_param_key(function_id=None) -> str | None:
    """Erster sinnvoll live-steuerbarer Parameter eines Effekts fuer Drag&Drop
    auf einen Slider.

    Bevorzugt algo-spezifische float/int-Parameter (live_editable=True) vor den
    universellen 'speed' und 'intensity'; Fallback 'speed'; None wenn kein
    unterstuetzter Effekt gefunden wurde.
    """
    fn = resolve_target(function_id)
    if not _supports(fn):
        return None
    preferred: str | None = None   # erster algo-spezifischer Key
    fallback:  str | None = None   # 'speed' als Reserve
    for spec in fn.list_params():
        if spec.kind not in ("int", "float"):
            continue
        if not getattr(spec, "live_editable", True):
            continue
        if spec.key in ("speed", "intensity"):
            if fallback is None:
                fallback = spec.key
        else:
            if preferred is None:
                preferred = spec.key
    return preferred or fallback


def color_is_effect_driven() -> bool:
    """True, wenn ein laufender Effekt gerade die Farbkanaele (color_r/g/b)
    „besitzt" — dann wirkt eine manuelle Farb-Kachel (Ziel Programmer/Alle) nicht
    sichtbar (APC-Probier To-Do #9). Erkannt wird eine laufende RGB-/RGBW-Matrix
    (der klare, eindeutige Fall — z. B. „Mtx Regenbogen"). Dimmer-/Shutter-Style-
    Matrizen fassen die Farbe NICHT an und zaehlen daher nicht."""
    try:
        from .function_manager import get_function_manager
        from .rgb_matrix import RgbMatrixInstance, MatrixStyle
    except Exception:
        return False
    try:
        for f in get_function_manager().all():
            if (isinstance(f, RgbMatrixInstance) and f.is_running
                    and f.style in (MatrixStyle.RGB, MatrixStyle.RGBW)):
                return True
    except Exception:
        return False
    return False


def set_selected_color(rgb, function_id=None) -> bool:
    """Color-Picker: setzt die aktuell ausgewaehlte Farbe der Color-Sequence
    (oder legt die erste an), damit ein VC-Color-Picker live in den Effekt faerbt."""
    fn = resolve_target(function_id)
    if not _supports(fn) or not hasattr(fn, "colors"):
        return False
    def _set_color():
        seq = fn.colors
        if len(seq) == 0:
            seq.add(tuple(rgb))
        else:
            seq.set_color(seq.active_index, tuple(rgb))
        return True
    return _apply_live_mutation(fn, _set_color)
