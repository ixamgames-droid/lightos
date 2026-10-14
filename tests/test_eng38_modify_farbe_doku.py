"""ENG-38: der Unterabschnitt „Modify im Stil Farbe" der Dimmer-Matrix-Anleitung
stimmt mit der Engine ueberein.

Die Tabelle (Rot/Gruen/Blau je Betriebsart und Staerke) wird Zeile fuer Zeile
mit der echten Mischstelle nachgerechnet — so kann die Anleitung nicht still
von der Rechnung abweichen.
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

ANLEITUNG = ROOT / "docs" / "anleitung_dimmermatrix" / "ANLEITUNG_DIMMERMATRIX.md"


def _abschnitt() -> str:
    text = ANLEITUNG.read_text(encoding="utf-8")
    m = re.search(r"^### Modify im Stil Farbe.*?(?=^### )", text,
                  flags=re.M | re.S)
    assert m, "Unterabschnitt „### Modify im Stil Farbe …“ fehlt in der Anleitung"
    return m.group(0)


def _tabelle() -> dict[str, tuple[int, int, int]]:
    zeilen = {}
    for z in _abschnitt().splitlines():
        teile = [t.strip() for t in z.strip().strip("|").split("|")]
        if len(teile) == 4 and all(re.fullmatch(r"\d+", t) for t in teile[1:]):
            zeilen[teile[0].replace("*", "")] = tuple(int(t) for t in teile[1:])
    return zeilen


def test_abschnitt_nennt_bedienung_und_grenzen():
    a = " ".join(_abschnitt().split())
    for wort in ("Modify-Effekt", "RGB", "RGBW", "jeder Farbkanal einzeln",
                 "Gekappt wird je Farbkanal einzeln",
                 "Der Dimmer wird nie angefasst", "Eine dunkle Lampe bleibt dunkel",
                 "Grundhelligkeit", "Weiß-Kanal", "Farbrad", "Master",
                 "Addieren", "Abziehen", "Abdunkeln", "Stärke"):
        assert wort in a, f"„{wort}“ fehlt im Unterabschnitt Farbe"


def test_grenzen_behaupten_nicht_mehr_nur_dimmer():
    text = " ".join(ANLEITUNG.read_text(encoding="utf-8").split())
    assert "bisher nur im **Stil Dimmer**" not in text
    assert "Bei RGB, RGBW und Shutter ist der Haken gesperrt" not in text
    assert "Beim Stil **Shutter** ist der Haken gesperrt" in text


def test_farb_tabelle_stimmt_mit_der_engine(monkeypatch):
    import src.core.app_state as A
    from src.core.dmx.universe import Universe
    from src.core.engine.function_manager import FunctionManager
    from src.core.engine.rgb_matrix import (MatrixStyle, RgbAlgorithm,
                                             RgbMatrixInstance)

    class _Ch:
        default_value, ranges = 0, []

        def __init__(self, attribute, nr):
            self.attribute, self.channel_number = attribute, nr

    class _Fx:
        fid, universe, address = 1, 1, 1

    kan = [_Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3),
           _Ch("color_b", 4)]
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: kan)
    t = _tabelle()
    assert set(t) >= {"darunter", "Modify-Effekt (Betrag)"}, t

    def matrix(name, farbe):
        m = RgbMatrixInstance(name, cols=1, rows=1, fixture_grid=[1],
                              algorithm=RgbAlgorithm.PLAIN, color1=farbe)
        m.style = MatrixStyle.RGB
        m.tempo_bus_id = ""
        return m

    geprueft = 0
    for art, mode in (("Addieren", "add"), ("Abziehen", "sub"),
                      ("Abdunkeln", "dim")):
        for staerke in (100, 50):
            unten = matrix("unten", t["darunter"])
            mod = matrix("modify", t["Modify-Effekt (Betrag)"])
            mod.modify, mod.modify_mode, mod.modify_strength = True, mode, staerke
            fm = FunctionManager()
            for f in (unten, mod):
                fm.add(f)
                fm.start(f.id)
            u = Universe(1)
            fm.tick({1: u}, [_Fx()], 0.02)
            roh = u.get_all()
            assert roh[0] == 0, "Farb-Modify hat den Dimmer geschrieben"
            assert tuple(roh[1:4]) == t[f"{art}, Stärke {staerke} %"], (art, staerke)
            geprueft += 1
    assert geprueft == 6
