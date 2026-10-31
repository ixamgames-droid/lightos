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
                 "**Stufe**", "Snap-Tasten", "Programmer", "Chaser-Schritt",
                 "Farbe und Dimmer bleiben getrennt",
                 # Stand „fertiges Bild“: Regel, Master, Schrittweite
                 "fertige Bild", "Grundhelligkeit", "Grand Master", "Blackout",
                 "NOT-AUS", "Schrittweite", "wie Breite", "Läufer-Breite",
                 "Läufer-Anzahl", "gesperrt"):
        assert wort in a, f"„{wort}“ fehlt im Abschnitt Modify-Effekt"


def test_ueberholte_grenzen_stehen_nicht_mehr_drin():
    """Was seit dem spaeten Rechengang nicht mehr stimmt, darf die Anleitung
    nicht mehr behaupten."""
    a = " ".join(_abschnitt().split())
    for satz in ("werden nicht verrechnet. - **Addieren ohne",
                 "gehen alle Lampen, die im Lauflicht gerade nicht dran sind, **aus**",
                 "Snaps und Programmer-Helligkeit werden nie abgedunkelt",
                 "läuft ein Modify-Effekt wie ein normaler Effekt"):
        assert satz not in a, f"ueberholter Satz steht noch in der Anleitung: {satz}"


def test_schrittweite_tabelle_stimmt_mit_der_engine(monkeypatch):
    """Die Tabelle „Schritt 1 … 4“ (Breite 2, Schrittweite „wie Breite“,
    Addieren 100 % ueber 40 %) gegen die echte Mischstelle."""
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
        m.matrix_speed = 1.0
        return m

    unten = matrix("unten", RgbAlgorithm.PLAIN)
    unten.intensity_min = unten.intensity_max = 102          # 40 %
    mod = matrix("modify", RgbAlgorithm.CHASE)
    mod.params.update({"runner_count": 1, "runner_width": 2, "runner_step": 0,
                       "after_fade": 0.0, "movement": "normal"})
    mod.modify, mod.modify_mode, mod.modify_strength = True, "add", 100
    fm = FunctionManager()
    for f in (unten, mod):
        fm.add(f)
        fm.start(f.id)
    folge = []
    for _ in range(20):                       # 5 Schritte zu je 4 Frames
        u = Universe(1)
        fm.tick({1: u}, rig, 0.25)
        bild = [round(v * 100 / 255) for v in u.get_all()[:N]]
        if not folge or folge[-1] != bild:
            folge.append(bild)
    t = _tabelle()
    assert folge[:4] == [t[f"Schritt {k}"] for k in (1, 2, 3, 4)]
    assert folge[4] == t["Schritt 1"]


def test_abschnitt_bindet_seine_bilder_ein_und_alle_gibt_es():
    """DOC-73: die Bilder zu Abschnitt 5 sind aufgenommen — die frühere Liste
    „Noch aufzunehmende Bilder“ ist weg, jedes eingebundene Bild existiert."""
    a = _abschnitt()
    assert "### Noch aufzunehmende Bilder" not in a
    bilder = re.findall(r"!\[[^\]]+\]\(([^)]+)\)", a)
    assert len(bilder) >= 12, bilder
    for pfad in bilder:
        assert (ANLEITUNG.parent / pfad).is_file(), pfad


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


def test_nur_per_fader_bedienen_steht_drin_und_stimmt():
    """Der Absatz „Nur per Fader bedienen“: drei Schritte, der Haken mit dem
    Wortlaut aus dem Fader-Dialog, und die Tabelle gegen die Rechnung."""
    from src.core.engine.modify import modify_wert
    from src.ui.virtualconsole import vc_slider

    a = _abschnitt()
    m = re.search(r"^### Nur per Fader bedienen$.*?(?=^### )", a, flags=re.M | re.S)
    assert m, "Absatz „### Nur per Fader bedienen“ fehlt"
    t = m.group(0)
    for schritt in ("1. ", "2. ", "3. "):
        assert re.search(rf"^{re.escape(schritt)}", t, flags=re.M)
    haken = "Effekt An/Aus (EFFECT-Modi): bei 0 wirklich stoppen"
    assert haken in t
    quelle = Path(vc_slider.__file__).read_text(encoding="utf-8")
    # Im Dialog: Zeilen-Beschriftung + Text des Hakens.
    for teil in ('"Effekt An/Aus (EFFECT-Modi):"', '"bei 0 wirklich stoppen'):
        assert teil in quelle, (
            f"der Haken heisst im Fader-Dialog anders als in der Anleitung: {teil}")
    assert "Effekt-Helligkeit" in t and '"Effekt-Helligkeit"' in quelle
    for wort in ("Show laden", "erste Bewegung", "Pickup", "Modify-Stärke",
                 "Ohne den Haken", "Taste leuchtet"):
        assert wort in t, f"„{wort}“ fehlt im Absatz „Nur per Fader bedienen“"

    zeilen = {}
    for z in t.splitlines():
        teile = [x.strip() for x in z.strip().strip("|").split("|")]
        if len(teile) == 5 and all(re.fullmatch(r"\d+ %", x) for x in teile[2:]):
            zeilen[teile[0]] = [int(x.split()[0]) for x in teile[2:]]
    assert set(zeilen) == {"0", "50 %", "100 %"}
    for name, fader in (("0", 0), ("50 %", 128), ("100 %", 255)):
        soll = [round(modify_wert(mode, 102, 255, fader / 255.0) * 100 / 255)
                for mode in ("sub", "dim", "add")]
        assert zeilen[name] == soll, f"Zeile „{name}“: {zeilen[name]} statt {soll}"
