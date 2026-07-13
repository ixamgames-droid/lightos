"""Show-Linter: prüft ein ``show.json``-Dict (oder eine ``.lshow``) gegen die
reflektierten echten Bauteil-Sätze und macht jeden SILENT-SWALLOW-Punkt LAUT,
BEVOR ``save_show`` eine inerte/kaputte Show schreibt.

Bewusst rein über die DICTS (nicht über einen Headless-Roundtrip): ``load_show``
legt ``virtual_console`` roh ab und instanziiert die Widgets nie -> der
Widget-Skip-Pfad würde in einem Roundtrip nie getroffen. Jedes Finding zitiert
die echte ``file:line``, die den Fehler sonst still geschluckt hätte.

Verwendung:
    from src.core.capability.validate import assert_lshow, validate_show_dict
    save_show(OUT)
    assert_lshow(OUT)        # wirft, falls ein ERROR-Finding existiert
"""
from __future__ import annotations

import difflib
import json
import os
import zipfile
from dataclasses import dataclass

from .reflect import Capabilities, get_capabilities

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    severity: str            # "error" | "warning"
    code: str                # kurzer Code, z. B. "VC-TYPE", "MX-ALGO"
    where: str               # Pfad in der Show, z. B. "functions[3] 'MH Kreis'"
    message: str
    swallow_site: str = ""   # echte file:line, die das sonst still schluckt

    def __str__(self) -> str:
        tag = "ERROR" if self.severity == ERROR else "warn "
        loc = f"   ({self.swallow_site})" if self.swallow_site else ""
        return f"{tag} [{self.code}] {self.where}: {self.message}{loc}"


class ShowValidationError(Exception):
    """Wird von ``assert_*`` geworfen, wenn ein ERROR-Finding existiert."""

    def __init__(self, findings: list[Finding]):
        self.findings = findings
        errs = [f for f in findings if f.severity == ERROR]
        super().__init__(
            f"{len(errs)} Fehler in der Show:\n" + format_findings(errs))


def _suggest(value, valid) -> str:
    """`` (meintest du 'X'?)`` per difflib, sonst leer."""
    try:
        m = difflib.get_close_matches(str(value), [str(v) for v in valid], n=1, cutoff=0.7)
        return f" (meintest du '{m[0]}'?)" if m else ""
    except Exception:
        return ""


def _normalize_color_target(value):
    """Spiegelt die ASCII->Umlaut-Normalisierung des Loaders (vc_color), damit der
    statische Lint Alt-Shows nicht falsch meldet. Fällt auf Identität zurück, wenn
    das UI-Modul nicht importierbar ist."""
    try:
        from src.ui.virtualconsole.vc_color import normalize_color_target
        return normalize_color_target(value)
    except Exception:
        return value


def _functions_list(show: dict) -> list:
    block = show.get("functions")
    if isinstance(block, dict):
        return block.get("functions", []) or []
    if isinstance(block, list):
        return block
    return []


def validate_show_dict(show: dict, caps: Capabilities | None = None) -> list[Finding]:
    """Validiert ein vollständiges ``show.json``-Dict. Liefert alle Findings
    (Errors + Warnings), nie eine Exception."""
    caps = caps or get_capabilities()
    findings: list[Finding] = []
    known_fids: set[int] = set()
    fid_to_fn: dict[int, dict] = {}

    # ── Funktionen ──────────────────────────────────────────────────────────────
    funcs = _functions_list(show)
    seen_ids: set[int] = set()
    for i, fd in enumerate(funcs):
        if not isinstance(fd, dict):
            continue
        name = fd.get("name", "")
        where = f"functions[{i}] '{name}'"
        fid = fd.get("id")
        if isinstance(fid, int):
            if fid in seen_ids:
                findings.append(Finding(
                    WARNING, "FN-DUP-ID", where,
                    f"doppelte Funktions-ID {fid} (überschreibt still die vorige)",
                    "function_manager.py:528"))
            seen_ids.add(fid)
            known_fids.add(fid)
            fid_to_fn[fid] = fd

        ftype = fd.get("type")
        if caps.function_types and ftype not in caps.function_types:
            findings.append(Finding(
                ERROR, "FN-TYPE", where,
                f"unbekannter Funktionstyp '{ftype}'"
                + _suggest(ftype, caps.function_types)
                + " — wird beim Laden still übersprungen",
                "function_manager.py:477-478"))
            continue

        if ftype == "RGBMatrix":
            findings += _check_matrix(fd, where, caps)
        elif ftype == "EFX":
            findings += _check_efx(fd, where, caps)

    # ── Virtuelle Konsole ───────────────────────────────────────────────────────
    vc = show.get("virtual_console") or {}
    widgets = vc.get("widgets", []) if isinstance(vc, dict) else []
    for j, w in enumerate(widgets):
        if isinstance(w, dict):
            findings += _check_widget(
                w, f"virtual_console.widgets[{j}]", caps, known_fids, fid_to_fn)

    return findings


def _function_param_keys(fd: dict, caps: Capabilities) -> frozenset | None:
    """Statisch aufgelöste Param-Key-Menge des KONKRETEN gebundenen Funktionstyps
    (spiegelt ``list_params`` der jeweiligen Function). ``None`` = Typ trägt keine
    reflektierten Param-Keys (dann greift nur der Union-Check). RGBMatrix nutzt die
    Union über alle Algorithmen (``params``/Bindungen akkumulieren über
    Algo-Wechsel — Typ-Präzision reicht, um die QA-05-Bugklasse zu fangen)."""
    ftype = fd.get("type")
    if ftype == "RGBMatrix":
        return caps.matrix_all_param_keys or None
    if ftype == "EFX":
        return caps.efx_param_keys or None
    return None


def _check_matrix(fd: dict, where: str, caps: Capabilities) -> list[Finding]:
    out: list[Finding] = []
    algo = fd.get("algorithm")
    if caps.matrix_algorithms and algo not in caps.matrix_algorithms \
            and algo not in caps.matrix_legacy_algorithms:
        out.append(Finding(
            ERROR, "MX-ALGO", where,
            f"unbekannter Matrix-Algorithmus '{algo}'"
            + _suggest(algo, caps.matrix_algorithms)
            + " — lädt still als flaches PLAIN",
            "rgb_matrix.py:1569-1572"))
    style = fd.get("style")
    if style is not None and caps.matrix_styles and style not in caps.matrix_styles:
        out.append(Finding(
            ERROR, "MX-STYLE", where,
            f"unbekannter Matrix-Style '{style}'"
            + _suggest(style, caps.matrix_styles)
            + " — wirft beim Laden, die ganze Matrix fällt weg",
            "rgb_matrix.py:1612"))
    params = fd.get("params") or {}
    # Gegen die globale Matrix-Param-Union prüfen (nicht pro Algo): `params`
    # akkumuliert über Algo-Wechsel, der Renderer liest pro Algo nur die
    # relevanten. So fangen wir echte Tippfehler/Halluzinationen, ohne inaktive
    # Cross-Algo-Keys fälschlich zu melden.
    valid = caps.matrix_all_param_keys
    if isinstance(params, dict) and valid:
        for key in params:
            if key not in valid:
                sugg = _suggest(key, valid)
                out.append(Finding(
                    ERROR if sugg else WARNING, "MX-PARAM", where,
                    f"Param-Key '{key}' ist kein bekannter Matrix-Parameter"
                    + sugg + " — der Renderer liest ihn nie (inert)",
                    "rgb_matrix.py:1405-1407"))
    return out


def _check_efx(fd: dict, where: str, caps: Capabilities) -> list[Finding]:
    out: list[Finding] = []
    # Diskriminator: nur motion/speed_hz -> EfxInstance; layers -> LayeredEffect;
    # pattern -> Carousel; nichts davon -> still übersprungen.
    has_disc = bool(fd.get("motion")) or ("speed_hz" in fd) \
        or ("layers" in fd) or ("pattern" in fd)
    if not has_disc:
        out.append(Finding(
            ERROR, "EFX-DISC", where,
            "EFX-Dict ohne Diskriminator (motion/speed_hz/layers/pattern) — "
            "wird beim Laden still übersprungen",
            "function_manager.py:473-474"))
        return out
    # Nur die echte Pan/Tilt-EFX (motion/speed_hz) hat einen EfxAlgorithm; ein
    # falscher Wert wirft hart -> die ganze Funktion fällt weg.
    if bool(fd.get("motion")) or ("speed_hz" in fd):
        algo = fd.get("algorithm")
        if algo is not None and caps.efx_algorithms and algo not in caps.efx_algorithms:
            out.append(Finding(
                ERROR, "EFX-ALGO", where,
                f"unbekannter EFX-Algorithmus '{algo}'"
                + _suggest(algo, caps.efx_algorithms)
                + " — wirft beim Laden, die ganze EFX-Funktion fällt weg",
                "efx.py:882"))
    elif "pattern" in fd:
        pat = fd.get("pattern")
        if caps.carousel_patterns and pat not in caps.carousel_patterns:
            out.append(Finding(
                ERROR, "CAR-PATTERN", where,
                f"unbekanntes Carousel-Pattern '{pat}'"
                + _suggest(pat, caps.carousel_patterns),
                "carousel.py:189-192"))
    return out


# Map: Widget-Typ -> (Dict-Key des Enum-Felds, Capabilities-Attribut, Code,
#                     Default-bei-Unbekannt-Swallow-Site)
_WIDGET_ENUM_FIELDS = {
    "VCButton":   ("action",      "button_actions", "VC-ACTION",      "vc_button.py:1399-1404"),
    "VCSlider":   ("mode",        "slider_modes",   "VC-SLIDERMODE",  "vc_slider.py:816"),
    "VCColor":    ("target",      "color_targets",  "VC-COLORTARGET", "vc_color.py:537"),
    "VCSpeedDial":("target_mode", "speed_targets",  "VC-SPEEDTARGET", "vc_speedial.py:1009"),
}


def _check_widget(w: dict, where: str, caps: Capabilities,
                  known_fids: set[int],
                  fid_to_fn: dict[int, dict] | None = None) -> list[Finding]:
    fid_to_fn = fid_to_fn or {}
    out: list[Finding] = []
    wtype = w.get("type")
    if caps.widget_types and wtype not in caps.widget_types:
        out.append(Finding(
            ERROR, "VC-TYPE", where,
            f"unbekannter Widget-Typ '{wtype}'"
            + _suggest(wtype, caps.widget_types)
            + " — verschwindet beim Laden ohne jede Meldung",
            "vc_canvas.py:1285-1287"))
        return out  # Typ unbekannt -> Felder nicht weiter prüfen

    label = f"{where} ({wtype})"

    # Enum-Feld des Widget-Typs prüfen
    spec = _WIDGET_ENUM_FIELDS.get(wtype)
    if spec:
        key, attr, code, site = spec
        valid = getattr(caps, attr)
        val = w.get(key)
        # ColorTarget: der Loader normalisiert ASCII-Alt-Werte (ue->ü) auf den
        # kanonischen Wert -> Validator spiegelt das, sonst falscher Alarm bei
        # Alt-Shows (siehe vc_color.normalize_color_target).
        check_val = _normalize_color_target(val) if wtype == "VCColor" else val
        if check_val is not None and valid and check_val not in valid:
            out.append(Finding(
                ERROR, code, label,
                f"ungültiger Wert '{val}' für '{key}'"
                + _suggest(val, valid)
                + " — fällt beim Laden still auf den Default zurück",
                site))

    # param_key (Slider/Encoder/Stepper): zuerst gegen die Union aller echten
    # Param-Keys (fängt Tippfehler/Halluzinationen). Ist er global gültig, aber die
    # Bindung (function_id) zeigt auf eine konkrete Funktion, deren Typ diesen Key
    # NICHT trägt -> QA-05-Bugklasse (global gültig, für DIESE Funktion inert):
    # statisch gegen die Param-Keys des gebundenen Funktionstyps prüfen.
    if wtype in ("VCSlider", "VCEncoder", "VCStepper"):
        pk = w.get("param_key")
        if pk and caps.all_param_keys and pk not in caps.all_param_keys:
            sugg = _suggest(pk, caps.all_param_keys)
            out.append(Finding(
                ERROR if sugg else WARNING, "VC-PARAMKEY", label,
                f"param_key '{pk}' ist kein bekannter Effekt-Parameter" + sugg
                + " — der Regler bleibt wirkungslos",
                "effect_live.py:100-102"))
        elif pk:
            fid = w.get("function_id")
            fd = fid_to_fn.get(fid) if isinstance(fid, int) else None
            fn_keys = _function_param_keys(fd, caps) if fd is not None else None
            if fn_keys is not None and pk not in fn_keys:
                out.append(Finding(
                    ERROR, "VC-PARAMKEY-FN", label,
                    f"param_key '{pk}' existiert nicht an der gebundenen Funktion "
                    f"{fid} ({fd.get('type')})" + _suggest(pk, fn_keys)
                    + " — global gültig, für DIESE Funktion aber wirkungslos",
                    "effect_live.py:100-102"))

    # tempo_bus_id (offener Satz) -> nur Warnung
    tb = w.get("tempo_bus_id")
    if tb and caps.tempo_bus_always_valid and tb not in caps.tempo_bus_always_valid:
        out.append(Finding(
            WARNING, "VC-TEMPOBUS", label,
            f"tempo_bus_id '{tb}' ist kein fest definierter Bus — "
            "wirkt nur, wenn die Show diesen Bus anlegt",
            "tempo_bus.py:573-576"))

    # Cross-Ref: gebundene Funktions-IDs müssen existieren
    for ref_key in ("function_id", "function_ids"):
        ref = w.get(ref_key)
        refs = ref if isinstance(ref, list) else ([ref] if ref is not None else [])
        for r in refs:
            if isinstance(r, int) and r > 0 and known_fids and r not in known_fids:
                out.append(Finding(
                    WARNING, "VC-DANGLING", label,
                    f"{ref_key} {r} zeigt auf keine existierende Funktion",
                    "vc_widget.py (function_id-Bindung)"))

    # Container-Kinder rekursiv prüfen (VCFrame/VCEffectEditor serialisieren ihre
    # Kinder unter "children" — vc_frame.py:271; nur diesen Key rekursieren, NICHT
    # jede beliebige Dict-Liste, sonst werden Nicht-Widget-Einträge wie
    # Cuelist-/Chaser-Schritte fälschlich als Widget-Typen gemeldet).
    children = w.get("children")
    if isinstance(children, list):
        for k, child in enumerate(children):
            if isinstance(child, dict):
                out += _check_widget(
                    child, f"{where}.children[{k}]", caps, known_fids, fid_to_fn)
    return out


# ── .lshow / Datei-Ebene ────────────────────────────────────────────────────────
def _load_show_json(path: str) -> dict:
    path = os.fspath(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            with zf.open("show.json") as fh:
                return json.load(fh)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_lshow(path: str, caps: Capabilities | None = None) -> list[Finding]:
    """Validiert eine ``.lshow`` (ZIP mit show.json) oder eine rohe show.json."""
    return validate_show_dict(_load_show_json(path), caps)


def format_findings(findings) -> str:
    return "\n".join(str(f) for f in findings) if findings else "(keine Findings)"


def assert_show_dict(show: dict, caps: Capabilities | None = None) -> None:
    """Wirft ``ShowValidationError``, falls ein ERROR-Finding existiert."""
    findings = validate_show_dict(show, caps)
    if any(f.severity == ERROR for f in findings):
        raise ShowValidationError(findings)


def assert_lshow(path: str, caps: Capabilities | None = None) -> None:
    """Wie ``assert_show_dict``, aber für eine ``.lshow``-Datei."""
    findings = validate_lshow(path, caps)
    if any(f.severity == ERROR for f in findings):
        raise ShowValidationError(findings)


# ── Bindungs-BEWUSSTE Live-Checks (gegen die laufende Engine, nach load_show) ────
# Ergänzen die statischen Dict-Checks: prüfen param_key / effect_action_key gegen
# die ECHTEN list_params/list_actions der GEBUNDENEN Funktion (#5/#16). Braucht
# einen geladenen FunctionManager (effect_live), daher getrennt vom statischen Teil.
def _live_check_widgets(widgets, effect_live) -> list[Finding]:
    out: list[Finding] = []
    for j, w in enumerate(widgets):
        if not isinstance(w, dict):
            continue
        where = f"vc.widget[{j}] ({w.get('type')})"
        fid = w.get("function_id")
        if isinstance(fid, int) and fid > 0:
            if w.get("type") in ("VCSlider", "VCEncoder", "VCStepper"):
                pk = w.get("param_key")
                if pk:
                    keys = {getattr(s, "key", None) for s in effect_live.list_params(fid)}
                    keys.discard(None)
                    if keys and pk not in keys:
                        out.append(Finding(
                            ERROR, "VC-PARAMKEY-LIVE", where,
                            f"param_key '{pk}' existiert NICHT an der gebundenen "
                            f"Funktion {fid}" + _suggest(pk, keys)
                            + " — der Regler bleibt wirkungslos",
                            "effect_live.py:100-102"))
            if w.get("type") == "VCButton" and w.get("action") == "EffectAction":
                ak = w.get("effect_action_key")
                if ak:
                    actions = {k for k, _ in effect_live.list_actions(fid)}
                    if actions and ak not in actions:
                        out.append(Finding(
                            ERROR, "VC-ACTION-LIVE", where,
                            f"effect_action_key '{ak}' ist an Funktion {fid} keine "
                            f"gültige Aktion" + _suggest(ak, actions)
                            + " — der Button löst nichts aus",
                            "vc_button.py:723-734"))
        children = w.get("children")
        if isinstance(children, list):
            out += _live_check_widgets(children, effect_live)
    return out


def validate_show_live(state=None) -> list[Finding]:
    """Bindungs-bewusste Checks gegen die LAUFENDE Engine (nach ``load_show`` bzw.
    in einem Build-Skript mit geladenem ``FunctionManager``): prüft param_key /
    effect_action_key der VC-Widgets gegen die ECHTEN ``effect_live.list_params`` /
    ``list_actions`` der gebundenen Funktion. Liefert Findings, nie eine Exception.

    Anders als ``validate_show_dict`` (statisch über die Union aller Param-Keys)
    ist das hier BINDUNGS-präzise: ein für die gebundene Funktion/Algo inerter,
    aber global existierender Param-Key wird hier gefangen (#5), ebenso eine an den
    falschen Funktionstyp gebundene Effekt-Aktion (#16)."""
    findings: list[Finding] = []
    try:
        from src.core.engine import effect_live
    except Exception:
        return findings
    if state is None:
        try:
            from src.core.app_state import get_state
            state = get_state()
        except Exception:
            return findings
    vc = getattr(state, "_vc_layout", {}) or {}
    widgets = vc.get("widgets", []) if isinstance(vc, dict) else []
    return _live_check_widgets(widgets, effect_live)
