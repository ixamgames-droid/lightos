"""Phase 6: optionaler Strict-Loader-Modus (LIGHTOS_STRICT).

Default (Flag aus): kaputte Show lädt degradiert (tolerantes Verhalten, 1:1 wie
bisher). Flag an: dieselbe kaputte Show scheitert LAUT beim Laden — Schutz auch
für Shows, die nicht über die Validierungs-Ebene entstanden sind.
"""
from __future__ import annotations

import json
import zipfile

import pytest

# Eine EFX-Funktion mit ungültigem Algorithmus -> EfxInstance.from_dict wirft
# ValueError (efx.py:882) -> wird in function_manager.from_dict gefangen
# (tolerant gedroppt) bzw. im Strict-Modus re-raised.
_BROKEN = {"type": "EFX", "motion": True, "algorithm": "GIBTSNICHT_ALGO",
           "id": 1, "name": "kaputt"}


def _write_lshow(path: str, show: dict) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("show.json", json.dumps(show, ensure_ascii=False))


def test_strict_mode_flag(monkeypatch):
    from src.core.strict import strict_mode
    monkeypatch.delenv("LIGHTOS_STRICT", raising=False)
    assert not strict_mode()
    for v in ("1", "true", "yes", "on", "Ja"):
        monkeypatch.setenv("LIGHTOS_STRICT", v)
        assert strict_mode(), v
    for v in ("0", "false", "", "no", "off"):
        monkeypatch.setenv("LIGHTOS_STRICT", v)
        assert not strict_mode(), v


def test_from_dict_tolerant_then_strict(monkeypatch):
    """function_manager.from_dict: tolerant droppt die kaputte Funktion still;
    im Strict-Modus wirft sie."""
    from src.core.show.show_file import reset_show
    from src.core.engine.function_manager import get_function_manager

    monkeypatch.delenv("LIGHTOS_STRICT", raising=False)
    reset_show()
    fm = get_function_manager()

    fm.from_dict({"functions": [dict(_BROKEN)]})
    assert fm.get(1) is None          # tolerant: still gedroppt

    monkeypatch.setenv("LIGHTOS_STRICT", "1")
    with pytest.raises(Exception):
        fm.from_dict({"functions": [dict(_BROKEN)]})


def test_load_show_tolerant_then_strict(tmp_path, monkeypatch):
    """load_show: tolerant lädt die Show degradiert (ok=True); im Strict-Modus
    scheitert dieselbe Datei LAUT."""
    from src.core.show.show_file import load_show

    show = {"version": "1.1", "name": "Broken",
            "functions": {"functions": [dict(_BROKEN)]}}
    p = str(tmp_path / "broken.lshow")
    _write_lshow(p, show)

    monkeypatch.delenv("LIGHTOS_STRICT", raising=False)
    ok, msg = load_show(p)
    assert ok, msg                    # tolerant: lädt trotz kaputter Funktion

    monkeypatch.setenv("LIGHTOS_STRICT", "1")
    with pytest.raises(Exception):
        load_show(p)                  # strict: wirft


def test_load_show_strict_clean_ok(tmp_path, monkeypatch):
    """Eine SAUBERE Show lädt auch im Strict-Modus ohne Fehler (kein Fehlalarm)."""
    from src.core.show.showbuilder import ShowBuilder
    from src.core.engine.rgb_matrix import RgbAlgorithm
    from src.core.show.show_file import load_show

    b = ShowBuilder()
    b.matrix("M", algorithm=RgbAlgorithm.PLAIN, style="RGB")
    p = str(tmp_path / "clean.lshow")
    b.save(p)

    monkeypatch.setenv("LIGHTOS_STRICT", "1")
    ok, msg = load_show(p)
    assert ok, msg
