"""ENG-40: der Unterabschnitt „Nur bestimmte Kanäle verändern: „Wirkt auf““ der
Dimmer-Matrix-Anleitung stimmt mit der Engine ueberein.

Die Tabelle (Dimmer/Rot/Gruen/Blau/Weiss je Auswahl, Betriebsart und Staerke)
wird Zeile fuer Zeile mit dem echten FunctionManager nachgerechnet.
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

_KANAL = {"Rot": "r", "Grün": "g", "Blau": "b", "Weiß": "w",
          "Amber": "a", "UV": "uv"}
_ART = {"Addieren": "add", "Abziehen": "sub", "Abdunkeln": "dim"}


def _abschnitt() -> str:
    text = ANLEITUNG.read_text(encoding="utf-8")
    m = re.search(r"^### Nur bestimmte Kanäle verändern.*?(?=^### )", text,
                  flags=re.M | re.S)
    assert m, "Unterabschnitt „### Nur bestimmte Kanäle verändern …“ fehlt"
    return m.group(0)


def _tabelle() -> dict[str, tuple[int, ...]]:
    zeilen = {}
    for z in _abschnitt().splitlines():
        teile = [t.strip() for t in z.strip().strip("|").split("|")]
        if len(teile) == 6 and all(re.fullmatch(r"\d+", t) for t in teile[1:]):
            zeilen[teile[0].replace("*", "")] = tuple(int(t) for t in teile[1:])
    return zeilen


def test_abschnitt_nennt_bedienung_und_grenzen():
    a = " ".join(_abschnitt().split())
    for wort in ("**Wirkt auf**", "**Kanäle der Modify-Farbe**", "Vorgabe",
                 "Rot, Grün, Blau, Weiß, Amber", "UV", "nur diese Kanäle",
                 "**Helligkeit** des Effekts", "Farbton",
                 "Lampen ohne einen angekreuzten Kanal bleiben unberührt",
                 "nichts umgerechnet", "RGB-Strahler ohne Weiß-Kanal",
                 "Der Dimmer steht nicht in der Auswahl",
                 "**Stil Dimmer**", "Verwerfen", "Kopieren",
                 "Virtuellen Konsole"):
        assert wort in a, f"„{wort}“ fehlt im Unterabschnitt „Wirkt auf“"


def test_anleitung_behauptet_nicht_mehr_amber_und_uv_gingen_nie():
    text = " ".join(ANLEITUNG.read_text(encoding="utf-8").split())
    assert "also auch nicht als Modify." not in text
    assert "Amber und UV lassen sich über **Wirkt auf**" in text


def test_bilderliste_ist_fortlaufend_nummeriert():
    text = ANLEITUNG.read_text(encoding="utf-8")
    liste = text.split("### Noch aufzunehmende Bilder", 1)[1].split("---", 1)[0]
    nummern = [int(n) for n in re.findall(r"^(\d+)\. ", liste, flags=re.M)]
    assert nummern == list(range(1, len(nummern) + 1)), nummern
    assert "**Wirkt auf**" in liste


def test_tabelle_stimmt_mit_der_engine(monkeypatch):
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
           _Ch("color_b", 4), _Ch("color_w", 5)]
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: kan)
    t = _tabelle()
    unten = t.pop("darunter")
    assert len(t) >= 5, t
    geprueft = 0
    for kopf, erwartet in t.items():
        m_ = re.fullmatch(r"nur (.+?), (\w+), Stärke (\d+) %", kopf) or \
            re.fullmatch(r"(.+?), (\w+), Stärke (\d+) %", kopf)
        assert m_, kopf
        namen = re.split(r", | und ", m_.group(1))
        wahl = tuple(_KANAL[n] for n in namen)
        for stil in (MatrixStyle.RGB, MatrixStyle.RGBW):
            mod = RgbMatrixInstance("modify", cols=1, rows=1, fixture_grid=[1],
                                    algorithm=RgbAlgorithm.PLAIN,
                                    color1=(255, 255, 255))
            mod.style = stil
            mod.tempo_bus_id = ""
            mod.modify, mod.modify_mode = True, _ART[m_.group(2)]
            mod.modify_strength = int(m_.group(3))
            mod.modify_channels = wahl
            fm = FunctionManager()
            fm.add(mod)
            fm.start(mod.id)
            u = Universe(1)
            for c, w in zip(kan, unten):
                u.set_channel(c.channel_number, w)
            fm.tick({1: u}, [_Fx()], 0.02)
            assert tuple(u.get_all()[:5]) == erwartet, (kopf, stil)
            geprueft += 1
    assert geprueft == 2 * len(t)
