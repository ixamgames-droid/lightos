"""Manifest-Emitter: serialisiert die reflektierten Capabilities zu einem
maschinenlesbaren ``capability_manifest.json`` + einem menschenlesbaren
``CAPABILITIES.md`` (dem Agenten-Vertrag, den man VOR dem Show-Bau liest).

Beides wird aus dem Code generiert (``reflect`` + ``ALGO_META`` + die echten
``list_params()``), nie von Hand editiert. Ein Test (test_capability_manifest)
regeneriert + difft → schlägt fehl, sobald Code und committetes Manifest
auseinanderlaufen (neue/umbenannte Capability).

BEWUSST NICHT enthalten: die Fixture-Bibliothek (maschinenabhängig, 1764+ via
QXF-Import) — die wird zur Laufzeit über ``fixture_db.get_all_manufacturers()``
abgefragt, nicht ins reproduzierbare Manifest geschrieben.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from .reflect import get_capabilities

MANIFEST_JSON = "capability_manifest.json"
MANIFEST_MD = "CAPABILITIES.md"


def _spec_to_dict(spec) -> dict:
    """Serialisiert eine ParamSpec kompakt (key/label/kind/range/options)."""
    d: dict = {
        "key": getattr(spec, "key", None),
        "label": getattr(spec, "label", ""),
        "kind": getattr(spec, "kind", ""),
    }
    kind = d["kind"]
    if kind in ("int", "float"):
        lo, hi = getattr(spec, "min", 0.0), getattr(spec, "max", 0.0)
        if lo or hi:
            d["range"] = [lo, hi]
    opts = getattr(spec, "options", ()) or ()
    if opts:
        # options können (wert,) oder (wert,label) sein -> nur die Werte.
        d["options"] = [o[0] if isinstance(o, (list, tuple)) else o for o in opts]
    return d


def _matrix_algorithms() -> dict:
    """Pro Matrix-Algorithmus alle gueltigen rich ParamSpecs.

    ``RgbMatrixInstance.list_params()`` ist bewusst UI-dynamisch (Style + when).
    Das Manifest ist dagegen ein Bauvertrag und muss die UNION aller Styles und
    bedingten Parameter enthalten, damit legitime Show-Dateien nicht abgelehnt
    werden."""
    out: dict = {}
    try:
        from src.core.engine.rgb_matrix import (
            RgbAlgorithm, RgbMatrixInstance, MatrixStyle,
        )
        from src.core.engine.rgb_matrix_meta import ALGO_META
    except Exception:
        return out
    try:
        m = RgbMatrixInstance()
    except Exception:
        m = None
    for algo in RgbAlgorithm:
        entry: dict = {}
        meta = ALGO_META.get(algo)
        if meta is not None:
            entry["colors"] = int(getattr(meta, "colors", 0))
            entry["has_direction"] = bool(getattr(meta, "direction", False))
        if m is not None:
            try:
                m.algorithm = algo
                by_key = {}
                for style in MatrixStyle:
                    m.style = style
                    m.params = {}
                    for spec in m.list_params():
                        by_key.setdefault(spec.key, spec)
                ordered_keys = (
                    "speed", "intensity", "offset",
                    "intensity_min", "intensity_max",
                    "shutter_min", "shutter_max",
                    "tempo_bus_id", "tempo_multiplier", "phase_offset",
                    "env_fade_in", "env_fade_out", "env_fade",
                    "direction", "colors",
                )
                specs = [by_key[key] for key in ordered_keys if key in by_key]
                if meta is not None:
                    specs.extend(meta.params)
                entry["params"] = [_spec_to_dict(spec) for spec in specs]
            except Exception:
                entry["params"] = []
        out[algo.value] = entry
    return out


def _efx_params() -> list:
    try:
        from src.core.engine.efx import EfxInstance
        return [_spec_to_dict(s) for s in EfxInstance().list_params()]
    except Exception:
        return []


def build_manifest() -> dict:
    """Baut das deterministische Manifest-Dict (alles sortiert → diff-stabil)."""
    c = get_capabilities()

    def S(fs):
        return sorted(fs)

    return {
        "_about": "GENERATED — nicht von Hand editieren. Neu erzeugen mit "
                  "tools/gen_capabilities.py. Quelle: src/core/capability/reflect.py.",
        "show_version": c.show_version,
        "asymmetry_warnings": [
            "Falscher RGB-Matrix-Algorithmus -> laedt STILL als flaches PLAIN "
            "(rgb_matrix.py:1569). Falscher EFX-Algorithmus (efx.py:882) ODER "
            "Matrix-Style (rgb_matrix.py:1612) -> wirft beim Laden, die GANZE "
            "Funktion faellt weg. Gegensaetzlich, beide unsichtbar.",
            "Daher beim Bauen IMMER das echte Enum-Member konstruieren "
            "(RgbAlgorithm.FIRE, EfxAlgorithm.CIRCLE, MatrixStyle.RGBW) — ein "
            "falscher Enum-NAME wirft sofort AttributeError, bevor der stille "
            "Loader den Wert je sieht.",
        ],
        "widget_types": S(c.widget_types),
        "button_actions": S(c.button_actions),
        "slider_modes": S(c.slider_modes),
        "speed_targets": S(c.speed_targets),
        "color_targets": S(c.color_targets),
        "color_targets_note": "ColorTarget-Werte sind deutsche Anzeige-Strings "
                              "(z. B. 'Effekt Farbe 1'), NICHT die Attribut-Namen.",
        "encoder_modes": S(c.encoder_modes),
        "matrix_styles": S(c.matrix_styles),
        "matrix_algorithms": _matrix_algorithms(),
        "matrix_legacy_algorithms": S(c.matrix_legacy_algorithms),
        "efx_algorithms": S(c.efx_algorithms),
        "efx_params": _efx_params(),
        "carousel_patterns": S(c.carousel_patterns),
        "function_types": S(c.function_types),
        "run_orders": S(c.run_orders),
        "directions": S(c.directions),
        "cue_stack_modes": S(c.cue_stack_modes),
        "tempo_buses_always_valid": S(c.tempo_bus_always_valid),
        "curve_names": S(c.curve_names),
        "fixtures_note": "Die Fixture-Bibliothek ist maschinenabhaengig und NICHT "
                         "Teil dieses Manifests. Zur Laufzeit abfragen: "
                         "fixture_db.get_all_manufacturers() -> FixtureProfile."
                         "short_name/.modes[].channels[]. Patch via "
                         "state.add_fixture(PatchedFixture(...)).",
    }


# ── Markdown-Rendering (der menschenlesbare Agenten-Vertrag) ─────────────────────
def _md_list(values) -> str:
    return ", ".join(f"`{v}`" for v in values) if values else "_(keine)_"


def render_markdown(man: dict | None = None) -> str:
    man = man or build_manifest()
    L: list[str] = []
    L.append("# LightOS — Capability-Manifest (Agenten-Vertrag)")
    L.append("")
    L.append("> **GENERIERT — nicht von Hand editieren.** Neu erzeugen mit "
             "`tools/gen_capabilities.py`. Diese Datei listet, welche Bausteine in "
             "LightOS WIRKLICH existieren. Beim Bauen einer Show NUR diese nutzen — "
             "alles andere wird beim Laden still verschluckt (inert) oder droppt die "
             "ganze Funktion.")
    L.append(f"> Show-Version: `{man.get('show_version', '?')}`")
    L.append("")
    L.append("## ⚠️ Zuerst lesen — die zwei Asymmetrien")
    for w in man.get("asymmetry_warnings", []):
        L.append(f"- {w}")
    L.append("")
    L.append("## Virtuelle Konsole")
    L.append(f"- **Widget-Typen** ({len(man['widget_types'])}): {_md_list(man['widget_types'])}")
    L.append(f"- **ButtonAction** ({len(man['button_actions'])}): {_md_list(man['button_actions'])}")
    L.append(f"- **SliderMode** ({len(man['slider_modes'])}): {_md_list(man['slider_modes'])}")
    L.append(f"- **SpeedTarget** ({len(man['speed_targets'])}): {_md_list(man['speed_targets'])}")
    L.append(f"- **ColorTarget** ({len(man['color_targets'])}): {_md_list(man['color_targets'])}")
    L.append(f"  - _{man.get('color_targets_note', '')}_")
    L.append(f"- **EncoderMidiMode**: {_md_list(man['encoder_modes'])}")
    L.append("")
    L.append("## Funktionen")
    L.append(f"- **FunctionType** ({len(man['function_types'])}): {_md_list(man['function_types'])}")
    L.append(f"- **RunOrder**: {_md_list(man['run_orders'])} · **Direction**: {_md_list(man['directions'])}")
    L.append(f"- **CarouselPattern**: {_md_list(man['carousel_patterns'])}")
    L.append(f"- **CueStack-Modi**: {_md_list(man['cue_stack_modes'])}")
    L.append("")
    L.append("## RGB-Matrix")
    L.append(f"- **Styles**: {_md_list(man['matrix_styles'])}")
    L.append(f"- **Legacy-Algo-Aliase** (werden migriert): {_md_list(man['matrix_legacy_algorithms'])}")
    L.append("- **Algorithmen + gültige Parameter** (`params`-Keys; pro Algo gilt "
             "universell + algo-spezifisch):")
    L.append("")
    for algo, info in (man.get("matrix_algorithms") or {}).items():
        params = info.get("params", [])
        # nur die algo-spezifischen + select/range-tragenden Keys kompakt zeigen
        parts = []
        for p in params:
            seg = p["key"]
            if p.get("options"):
                seg += "(" + "/".join(str(o) for o in p["options"]) + ")"
            elif p.get("range"):
                seg += f"({p['range'][0]}–{p['range'][1]})"
            parts.append(seg)
        cflag = f" · Farben: {info.get('colors', 0)}" if "colors" in info else ""
        L.append(f"  - **{algo}**{cflag}: {_md_list_keys(parts)}")
    L.append("")
    L.append("## EFX (Pan/Tilt-Bewegung)")
    L.append(f"- **Algorithmen**: {_md_list(man['efx_algorithms'])}")
    efx_keys = [p["key"] for p in man.get("efx_params", [])]
    L.append(f"- **Live-Parameter** ({len(efx_keys)}): {_md_list(efx_keys)}")
    L.append("")
    L.append("## Tempo / Kurven")
    L.append(f"- **Tempo-Buses (immer gültig)**: {_md_list(man['tempo_buses_always_valid'])} "
             "(weitere via `ensure_bus` möglich — offener Satz)")
    L.append(f"- **Kurven (env_curve)**: {_md_list(man['curve_names'])}")
    L.append("")
    L.append("## Fixtures")
    L.append(f"- _{man.get('fixtures_note', '')}_")
    L.append("")
    return "\n".join(L)


def _md_list_keys(values) -> str:
    return ", ".join(f"`{v}`" for v in values) if values else "_(keine Extra-Params)_"


def write_manifest(out_dir: str) -> tuple[str, str]:
    """Schreibt JSON + MD nach ``out_dir``. Liefert (json_path, md_path)."""
    import json
    man = build_manifest()
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, MANIFEST_JSON)
    md_path = os.path.join(out_dir, MANIFEST_MD)
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(man))
    return json_path, md_path
