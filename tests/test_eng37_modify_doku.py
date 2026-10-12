"""ENG-37: der Abschnitt „Modify-Effekt" der Dimmer-Matrix-Anleitung stimmt
mit der Engine ueberein.

Die Tabelle „Durchgerechnet" wird Zeile fuer Zeile mit der echten Mischstelle
nachgerechnet (Dimmer-Effekt auf 40 %, Modify-Lauflicht mit zwei Laeufern auf
acht Lampen) — so kann die Anleitung nicht still von der Rechnung abweichen.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                               # noqa: E402

ANLEITUNG = ROOT / "docs" / "anleitung_dimmermatrix" / "ANLEITUNG_DIMMERMATRIX.md"
N = 8


def _abschnitt() -> str:
    text = ANLEITUNG.read_text(encoding="utf-8")
    m = re.search(r"^## 5\. Modify-Effekt.*?(?=^---$)", text, flags=re.M | re.S)
    assert m, "Abschnitt „## 5. Modify-Effekt …“ fehlt in der Dimmer-Matrix-Anleitung"
    return m.group(0)


def _tabelle() -> dict[str, list[int]]:
    zeilen = {}
    for z in _abschnitt().splitlines():
        teile = [t.strip() for t in z.strip().strip("|").split("|")]
        if len(teile) == N + 1 and all(re.fullmatch(r"\d+", t) for t in teile[1:]):
            zeilen[teile[0]] = [int(t) for t in teile[1:]]
    return zeilen


def test_abschnitt_nennt_bedienung_und_grenzen():
    a = _abschnitt()
    for wort in ("Modify-Effekt", "**Modify**", "Addieren", "Abziehen", "Abdunkeln",
                 "Stärke", "Modify-Stärke", "Stil Dimmer", "Start-Reihenfolge",
                 "Layer-Priorität", "Snap-Tasten", "Programmer", "Chaser-Schritt",
                 "Farbe und Dimmer bleiben getrennt"):
        assert wort in a, f"„{wort}“ fehlt im Abschnitt Modify-Effekt"


def test_abschnitt_listet_fehlende_bilder_und_bindet_keine_ein():
    a = _abschnitt()
    assert "### Noch aufzunehmende Bilder" in a
    assert "![" not in a, "Abschnitt bindet ein Bild ein, das es noch nicht gibt"
    liste = a.split("### Noch aufzunehmende Bilder", 1)[1]
    assert len(re.findall(r"^\d+\. ", liste, flags=re.M)) >= 5


def test_tabelle_hat_alle_zeilen():
    t = _tabelle()
    assert t["Effekt darunter"] == [40] * N
    assert sorted(t["Modify-Lauflicht (Betrag)"]) == [0] * 6 + [100] * 2
    for art in ("Addieren", "Abziehen", "Abdunkeln"):
        for st in (100, 50):
            assert f"{art}, Stärke {st} %" in t


@pytest.mark.parametrize("art, mode", [("Addieren", "add"), ("Abziehen", "sub"),
                                       ("Abdunkeln", "dim")])
@pytest.mark.parametrize("staerke", [100, 50])
def test_tabelle_stimmt_mit_der_engine(monkeypatch, art, mode, staerke):
    import src.core.app_state as A
    from src.core.dmx.universe import Universe
    from src.core.engine.function_manager import FunctionManager
    from src.core.engine.rgb_matrix import (MatrixStyle, RgbAlgorithm,
                                             RgbMatrixInstance)

    class _Ch:
        attribute, channel_number, default_value, ranges = "intensity", 1, 0, []

    class _Fx:
        def __init__(self, fid):
            self.fid, self.universe, self.address = fid, 1, fid

    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: [_Ch()])
    rig = [_Fx(f) for f in range(1, N + 1)]

    def matrix(name, algo):
        m = RgbMatrixInstance(name, cols=N, rows=1,
                              fixture_grid=list(range(1, N + 1)),
                              algorithm=algo, color1=(255, 255, 255))
        m.style = MatrixStyle.DIMMER
        m.tempo_bus_id = ""
        return m

    unten = matrix("unten", RgbAlgorithm.PLAIN)
    unten.intensity_min = unten.intensity_max = 102          # 40 %
    mod = matrix("modify", RgbAlgorithm.CHASE)
    mod.params.update({"runner_count": 2, "after_fade": 0.0, "fade": 0.0,
                       "movement": "normal"})
    mod.modify, mod.modify_mode, mod.modify_strength = True, mode, staerke
    betrag = {}
    orig = mod.write

    def write(universes, pc, dt, reg=None):
        orig(universes, pc, dt, reg)
        betrag["w"] = list(universes[1].get_all()[:N])
    mod.write = write

    fm = FunctionManager()
    for f in (unten, mod):
        fm.add(f)
        fm.start(f.id)
    t = _tabelle()
    soll_betrag = t["Modify-Lauflicht (Betrag)"]
    soll = t[f"{art}, Stärke {staerke} %"]
    for _ in range(600):
        u = Universe(1)
        fm.tick({1: u}, rig, 0.05)
        if [round(w * 100 / 255) for w in betrag["w"]] == soll_betrag:
            ist = [round(v * 100 / 255) for v in u.get_all()[:N]]
            assert ist == soll, (art, staerke, ist, soll)
            return
    pytest.fail(f"Das Lauflicht stand nie so wie in der Anleitung: {soll_betrag}")
