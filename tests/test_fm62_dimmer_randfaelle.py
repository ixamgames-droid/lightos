"""FM-62: Randfaelle der Dimmer->Weiss-Segment-Zuordnung (FM-46) aus den
Codex-Reviews zu #858, #861 und #864. Je Teilpunkt ein Test, der ohne den
Fix rot ist:

1. ``dimmer_key_setzen`` verankert die uebrigen Dimmer-Vorkommen auf ihrem
   WIRKSAMEN Vorwert (gespiegelter Basiswert bzw. Standardwert), nicht auf 0.
2. Mehrere mehrfache Dimmer-Attribute: eine ganz freie Gruppe neben einer
   zugeordneten wird gemeldet (``zuordnung_probleme``) — vorher schwiegen
   ``zuordnung_fehlt`` UND ``zuordnung_probleme``.
3. ``segmente_aus_heads``: ein mehrdeutiger Kopf macht das Segment auch fuer
   einen eindeutigen Kopf strittig (nie raten).
4. Generator-Import: verworfene QXF-Kanaele zaehlen bei der Ableitung nicht
   mit — gleiches Ergebnis wie der Bibliotheks-Import.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace as N

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import create_engine, select          # noqa: E402
from sqlalchemy.orm import Session                    # noqa: E402

import src.core.app_state as AS                       # noqa: E402
from src.core.database.models import Base, FixtureChannel  # noqa: E402
from src.core.database.qxf_import import QXF_NS, import_qxf_file  # noqa: E402
from src.core.dimmer_segmente import (segmente_aus_heads,  # noqa: E402
                                      zuordnung_fehlt, zuordnung_probleme)


def _ch(attr, nr, segment=None, default=0):
    return N(attribute=attr, channel_number=nr, default_value=default,
             highlight_value=255, ranges=[], name=attr, segment=segment)


def _geraet(segmente=(0, 1), defaults=(0, 0)):
    """Zwei Dimmer (CH1, CH2), vier RGB-Koepfe, zwei eigene Weiss-Segmente."""
    k = [_ch("intensity", i + 1, s, d)
         for i, (s, d) in enumerate(zip(segmente, defaults))]
    nr = len(k) + 1
    for _ in range(4):
        for a in ("color_r", "color_g", "color_b"):
            k.append(_ch(a, nr))
            nr += 1
    return k + [_ch("color_w", nr), _ch("color_w", nr + 1)]


class AnkerVorwertTest(unittest.TestCase):
    """(1) Codex #858."""

    def setUp(self):
        alt = AS.get_channels_for_patched
        self.addCleanup(setattr, AS, "get_channels_for_patched", alt)
        self.kanaele = _geraet()
        AS.get_channels_for_patched = lambda fx: self.kanaele
        fx = N(fid=1, universe=1, address=1, fixture_type="led_bar",
               fixture_profile_id=1, mode_name="m", head_mode="auto",
               channel_count=len(self.kanaele))
        self.st = AS.AppState.__new__(AS.AppState)
        self.st._patch_cache = [fx]
        self.st.programmer = {}
        self.st.set_programmer_value = (
            lambda fid, k, v: self.st.programmer.setdefault(fid, {})
            .__setitem__(k, int(v)))

    def _dmx(self):
        werte = {nr: v for nr, _k, v in AS.resolve_attr_channels(
            self.kanaele, self.st.programmer.get(1, {}))}
        return [werte.get(1, 0), werte.get(2, 0)]

    def test_gespiegelter_basiswert_bleibt(self):
        self.st.set_programmer_value(1, "intensity", 128)
        self.assertEqual(self._dmx(), [128, 128], "Spiegel vorher")
        self.assertTrue(self.st.weiss_dimmer_setzen(1, 0, 255))
        self.assertEqual(self._dmx(), [255, 128],
                         "Segment 2 behaelt seinen wirksamen Wert")

    def test_ohne_basiswert_der_standardwert(self):
        self.kanaele = _geraet(defaults=(0, 200))
        self.assertTrue(self.st.weiss_dimmer_setzen(1, 0, 255))
        self.assertEqual(self.st.programmer[1].get("intensity#1"), 200)

    def test_ohne_alles_weiter_0(self):
        self.assertTrue(self.st.weiss_dimmer_setzen(1, 0, 255))
        self.assertEqual(self._dmx(), [255, 0])


class JedeDimmerGruppeTest(unittest.TestCase):
    """(2) Codex #861: ``intensity`` voll zugeordnet, ``master`` gar nicht."""

    def _k(self):
        k = [{"attribute": c.attribute, "segment": c.segment}
             for c in _geraet((0, 1))]
        return k + [{"attribute": "master", "segment": None},
                    {"attribute": "master", "segment": None}]

    def test_freie_gruppe_wird_gemeldet(self):
        k = self._k()
        self.assertFalse(zuordnung_fehlt(k))
        p = zuordnung_probleme(k)
        self.assertEqual(p, [
            "Dimmer auf Kanal 17 hat kein Weiß-Segment — gewollt?",
            "Dimmer auf Kanal 18 hat kein Weiß-Segment — gewollt?"])

    def test_dimmer_check_warnt(self):
        """Dieselbe Praedikatkette wie ``dimmer_check``/Matrix-Editor."""
        k = self._k()
        self.assertTrue(zuordnung_fehlt(k) or zuordnung_probleme(k))

    def test_ohne_jede_zuordnung_bleibt_es_beim_hinweis(self):
        k = self._k()
        for c in k:
            c["segment"] = None
        self.assertTrue(zuordnung_fehlt(k))
        self.assertEqual(zuordnung_probleme(k), [])


class MehrdeutigerKopfTest(unittest.TestCase):
    """(3) Codex #864: ``[d0, w0]`` + ``[d1, d2, w0]`` -> nichts fuer w0."""

    def _k(self):
        # Nr. 0-2 Dimmer, 3-5 ein RGB-Kopf, 6/7 zwei eigene Weiss.
        return [{"attribute": a, "segment": None} for a in
                ("intensity", "intensity", "intensity", "color_r",
                 "color_g", "color_b", "color_w", "color_w")]

    def test_strittiges_segment_wird_nicht_vergeben(self):
        self.assertEqual(segmente_aus_heads(self._k(), [[0, 6], [1, 2, 6]]),
                         {})

    def test_mehrere_weiss_im_kopf(self):
        # [d1, w0, w1] nennt w0 und w1 mit d1 -> beide strittig.
        self.assertEqual(
            segmente_aus_heads(self._k(), [[0, 6], [2, 7], [1, 6, 7]]), {})

    def test_eindeutiges_anderes_segment_bleibt(self):
        # Der mehrdeutige Kopf nennt nur w1 — w0 bleibt eindeutig.
        self.assertEqual(
            segmente_aus_heads(self._k(), [[0, 6], [1, 2, 7]]), {0: 0})


_PRESET = {"D": "IntensityDimmer", "R": "IntensityRed", "G": "IntensityGreen",
           "B": "IntensityBlue", "W": "IntensityWhite"}


def _qxf(refs, heads) -> str:
    defs = "\n".join(f' <Channel Name="{n}" Preset="{_PRESET[n[0]]}"/>'
                     for n, _num in refs)
    zeilen = "\n".join(f'  <Channel Number="{num}">{n}</Channel>'
                       for n, num in refs)
    koepfe = "\n".join(
        "  <Head>\n" + "\n".join(f"   <Channel>{x}</Channel>" for x in h)
        + "\n  </Head>" for h in heads)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Manufacturer>TestCo</Manufacturer>
 <Model>Verworfen</Model>
 <Type>LED Bar (Pixels)</Type>
{defs}
 <Mode Name="Test">
{zeilen}
{koepfe}
 </Mode>
</FixtureDefinition>
"""


def _datei(xml):
    fd, path = tempfile.mkstemp(suffix=".qxf")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(xml)
    return path


def _paare_bibliothek(xml):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    path = _datei(xml)
    try:
        with Session(engine) as s:
            assert import_qxf_file(path, s, {})
            s.commit()
            k = [(c.name, c.attribute, c.segment) for c in s.execute(
                select(FixtureChannel)
                .order_by(FixtureChannel.channel_number)).scalars().all()]
    finally:
        os.remove(path)
    weiss = [n for n, a, _s in k if a == "color_w"]
    return {n: weiss[seg] for n, _a, seg in k if seg is not None}


def _paare_generator(xml):
    from src.ui.widgets.fixture_generator import model_from_qxf
    path = _datei(xml)
    try:
        m = model_from_qxf(path)
    finally:
        os.remove(path)
    k = [(c.name, c.attribute, c.segment) for c in m.modes[0].channels]
    weiss = [n for n, a, _s in k if a == "color_w"]
    return {n: weiss[seg] for n, _a, seg in k if seg is not None}


class GeneratorVerworfeneKanaeleTest(unittest.TestCase):
    """(4) Codex #864: ein verworfener doppelter Rot-Kanal (Nummern-
    Kollision) machte fuer den Generator Rot- und Weiss-Zahl gleich -> keine
    eigene Weiss-Achse -> keine Zuordnung; die Bibliothek ordnete zu."""

    REFS = [("Da", "0"), ("Wa", "1"), ("Db", "2"), ("Wb", "3"),
            ("R", "4"), ("G", "5"), ("B", "6"), ("Rz", "4")]

    def test_beide_wege_gleich(self):
        xml = _qxf(self.REFS, [[0, 1], [2, 3]])
        erwartet = {"Da": "Wa", "Db": "Wb"}
        self.assertEqual(_paare_bibliothek(xml), erwartet)
        self.assertEqual(_paare_generator(xml), erwartet)

    def test_verworfenes_weiss_verschiebt_den_rang_nicht(self):
        # Ein verworfenes Weiss (Kollision mit Nr. 1) VOR Wb: der Generator
        # behaelt es in seiner Liste, der Rang muss dort trotzdem auf das
        # richtige Weiss zeigen.
        refs = [("Da", "0"), ("Wa", "1"), ("Wz", "1"), ("Db", "2"),
                ("Wb", "3"), ("R", "4"), ("G", "5"), ("B", "6")]
        xml = _qxf(refs, [[0, 1], [2, 3]])
        self.assertEqual(_paare_bibliothek(xml), {"Da": "Wa", "Db": "Wb"})
        self.assertEqual(_paare_generator(xml), {"Da": "Wa", "Db": "Wb"})


if __name__ == "__main__":
    unittest.main()
