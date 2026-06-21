"""Hält den committeten Agenten-Vertrag mit dem Code synchron.

- Diff-Test: das frisch reflektierte Manifest MUSS dem committeten
  docs/capability_manifest.json entsprechen. Fügt jemand eine neue/umbenannte
  Capability hinzu (Widget/Enum/Algo/Param), schlägt dieser Test fehl, bis
  `tools/gen_capabilities.py` neu gelaufen ist. Das ist die Garantie, dass der
  Agent nie gegen einen veralteten Vertrag baut.
- Drift-Test Enum↔Dispatch: jeder FunctionType-Wert muss in der hand-
  geschriebenen if/elif-Ladder von function_manager.from_dict vorkommen — sonst
  würde das Manifest einen Typ als gültig listen, den der Loader still droppt.
"""
from __future__ import annotations

import inspect
import json
import os

from src.core.capability.manifest import build_manifest, MANIFEST_JSON

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COMMITTED = os.path.join(_ROOT, "docs", MANIFEST_JSON)


def _normalize(obj):
    """Über JSON normalisieren (Tupel→Liste, Typen angleichen) für stabilen Vergleich."""
    return json.loads(json.dumps(obj, ensure_ascii=False))


def test_manifest_matches_committed():
    assert os.path.exists(_COMMITTED), (
        "docs/capability_manifest.json fehlt — einmal "
        "`python tools/gen_capabilities.py` laufen lassen.")
    with open(_COMMITTED, "r", encoding="utf-8") as fh:
        committed = json.load(fh)
    fresh = _normalize(build_manifest())
    assert fresh == committed, (
        "Capability-Manifest ist veraltet (Code != docs/capability_manifest.json). "
        "Neu erzeugen mit: python tools/gen_capabilities.py")


def test_function_type_enum_matches_dispatch():
    """Jeder FunctionType-Wert muss in from_dict dispatchbar sein (sonst Manifest-Lüge)."""
    from src.core.engine.function import FunctionType
    from src.core.engine.function_manager import FunctionManager
    src = inspect.getsource(FunctionManager.from_dict)
    missing = [ft.value for ft in FunctionType if ft.value not in src]
    assert not missing, (
        f"FunctionType(s) {missing} haben keinen Dispatch-Zweig in "
        f"function_manager.from_dict — würden beim Laden still gedroppt.")


def test_manifest_has_core_sets():
    """Spot-Checks: der Vertrag enthält die erwarteten echten Werte."""
    m = build_manifest()
    assert "VCButton" in m["widget_types"]
    assert "Toggle" in m["button_actions"]
    assert "Schachbrett" in m["matrix_algorithms"]
    assert "RGBMatrix" in m["function_types"]
    # ColorTarget trägt die deutschen Umlaut-Strings
    assert "Effekt (Farbe hinzufügen)" in m["color_targets"]
    # Matrix-Algo trägt rich param specs
    chase = m["matrix_algorithms"]["Chase"]["params"]
    keys = {p["key"] for p in chase}
    assert {"axis", "runner_count", "movement"} <= keys
