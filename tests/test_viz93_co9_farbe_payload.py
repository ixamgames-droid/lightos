"""VIZ-93: CO9 V2 wirkt im 3D blass — Messung des Farbwegs bis zum Payload.

Befund (Nebenfund DEMO-07): in der Theater-Showcase (Cue 6) erscheint der
Horizont der vier CO9 V2 bei Abendrot (255/60/0, Weiss 0) im Strahl hellbeige,
das Amber der PAR56 wirkt satt.

Gemessen: der Python-Teil des Farbwegs ist sauber. Das Profil
``fixtures/bibliothek/ignition/co9-v2-led-flood-rgbw.json`` hat in allen
Gesamt-RGBW-Modi nur R/G/B/W (kein Amber/UV, kein zweiter Weiss-Kanal);
``visual_rgb`` mischt nichts hinzu und ``_build_fixture_payload`` schickt genau
255/60/0 mit der Dimmer-Helligkeit — wie fuer die PAR56. Beide Geraete laufen
im 3D als Render-Modell ``par`` durch denselben Pfad (``applyGenericColor``),
ohne geraetespezifische Farbe.

Die Blaesse entsteht in der Szene und betrifft ALLE Geraete: ``updateFixture``
(fixtures.js) nimmt r/255 ungewandelt als LINEARE Farbe, die sRGB-Ausgabe
(renderer.js) hebt G 60 damit schon ohne Tone-Mapping auf ~133 (Rot -> Orange);
ACES-Tone-Mapping (Belichtung 1,2) entsaettigt jede helle Farbe je Fragment
weiter (Abendrot voll ~ 245/170/46), danach addieren sich
die ueberlappenden Kegel/Flecken im 8-Bit-Bildpuffer und klemmen (s. Modulkopf
``fixtures/ausbrennen.js``). Das ist kein CO9-Fehler und wird nicht still an
einem Geraet geaendert — dieser Test haelt fest, dass der Farbweg bis zum
Payload satt bleibt (ein Regress hier waere ein echter Profil-/Mischfehler).
"""
import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

_REPO = Path(__file__).resolve().parents[1]
_CO9 = _REPO / "fixtures" / "bibliothek" / "ignition" / "co9-v2-led-flood-rgbw.json"
_PAR56 = _REPO / "fixtures" / "bibliothek" / "stairville" / "led-par56-mkii-rgbw.json"

ABENDROT = {"color_r": 255, "color_g": 60, "color_b": 0, "color_w": 0}
AMBER = {"color_r": 255, "color_g": 110, "color_b": 0, "color_w": 0}


def _modus(pfad: Path, name: str):
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    for m in daten["modi"]:
        if m["name"] == name:
            return m
    raise AssertionError(f"Modus {name!r} fehlt in {pfad.name}")


def _kanaele(modus):
    """Kanal-Attrappen mit Ranges (fuer Shutter-/Farbrad-Semantik)."""
    out = []
    for k in modus["kanaele"]:
        ranges = [SimpleNamespace(range_from=b["von"], range_to=b["bis"],
                                  name=b.get("name", ""), kind=b.get("art", ""))
                  for b in k.get("bereiche", ())]
        out.append(SimpleNamespace(attribute=k["attribut"], ranges=ranges))
    return out


def _attrs(modus, farbe, dimmer=204):
    """Alle Kanaele auf ihren Default, Dimmer + Farbe gesetzt, Shutter offen."""
    attrs = {}
    for k in modus["kanaele"]:
        if k["attribut"] == "raw" or k["attribut"] in attrs:
            continue
        attrs[k["attribut"]] = int(k.get("default", 0))
    if "intensity" in attrs:
        attrs["intensity"] = dimmer
    attrs.update(farbe)
    return attrs


@pytest.mark.parametrize("modus_name", ["6-Kanal", "13-Kanal", "4-Kanal"])
def test_co9_abendrot_bleibt_im_payload_satt(modus_name):
    from src.ui.visualizer.visualizer_service import _build_fixture_payload

    modus = _modus(_CO9, modus_name)
    attrs_namen = {k["attribut"] for k in modus["kanaele"]}
    # Kein Zusatz-Emitter, den visual_rgb einmischen koennte.
    assert not attrs_namen & {"color_a", "color_uv", "amber", "uv"}, attrs_namen
    payload = _build_fixture_payload(SimpleNamespace(fid=93), _attrs(modus, ABENDROT),
                                     _kanaele(modus))
    assert (payload["r"], payload["g"], payload["b"]) == (255, 60, 0), payload
    erwartet = 204 if "intensity" in attrs_namen else 255
    assert payload["intensity"] == erwartet, payload
    assert "heads" not in payload, payload


def test_co9_und_par56_nehmen_denselben_farbweg():
    """Gleiche Eingabe -> gleiche Payload-Farbe: der Unterschied im Bild kommt
    nicht aus dem Profil, sondern aus Farbe/Helligkeit/Lage in der Szene."""
    from src.ui.visualizer.visualizer_service import _build_fixture_payload

    co9 = _modus(_CO9, "6-Kanal")
    par = _modus(_PAR56, "8-Kanal")
    for farbe in (ABENDROT, AMBER):
        a = _build_fixture_payload(SimpleNamespace(fid=1), _attrs(co9, farbe),
                                   _kanaele(co9))
        b = _build_fixture_payload(SimpleNamespace(fid=2), _attrs(par, farbe),
                                   _kanaele(par))
        assert (a["r"], a["g"], a["b"]) == (b["r"], b["g"], b["b"]) == (
            farbe["color_r"], farbe["color_g"], farbe["color_b"])
        # Farbe zieht den Dimmer nie mit.
        assert a["intensity"] == b["intensity"] == 204
