"""FM-46 (Etappe 3): Dimmer -> Weiss-Segment beim QLC+-Import aus ``<Head>``.

Die 26 Modi der Bibliothek mit eigener Weiss-Achse und mehrfachem Dimmer
stammen alle aus QLC+-Importen. QLC+ fuehrt je Modus Kopf-Gruppen
(``<Head><Channel>n</Channel>…</Head>``, ``n`` = ``Number`` des Kanals im
Modus). Liegen ein Dimmer und ein Weiss in DEMSELBEN Kopf, sagt die Datei,
welcher Dimmer welches Weiss dimmt — das wird beim Import zu
``FixtureChannel.segment`` bzw. ``GenChannel.segment``.

Regel (``dimmer_segmente.segmente_aus_heads``), nie raten:

* nur Modi mit EIGENER Weiss-Achse und mehrfachem Dimmer;
* Koepfe ohne ``color_w`` zaehlen nicht;
* Kopf mit genau EINEM Dimmer und genau EINEM Weiss -> Segment = Rang dieses
  Weiss unter allen ``color_w`` des Modus;
* mehrdeutig (mehrere Dimmer/Weiss in einem Kopf, Dimmer in mehreren Koepfen,
  Segment doppelt) -> nichts;
* vorhandene Zuordnung bleibt.

Die XML-Texte hier sind eigene, minimale Nachbauten — keine fremden Dateien.
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
from src.core.database.models import (Base, FixtureChannel,  # noqa: E402
                                      FixtureMode)
from src.core.database.qxf_import import QXF_NS, import_qxf_file  # noqa: E402
from src.core.dimmer_segmente import segmente_aus_heads  # noqa: E402
from src.core.group_cells import ACHSE_WEISS          # noqa: E402

_PRESET = {"D": "IntensityDimmer", "R": "IntensityRed", "G": "IntensityGreen",
           "B": "IntensityBlue", "W": "IntensityWhite"}


def _qxf(kanaele: list[str], heads: list[list[int]], *,
         reihenfolge: list[int] | None = None, model: str = "Weissbar") -> str:
    """Ein Modus „Test“ mit den Kanaelen ``kanaele`` (Kuerzel D/R/G/B/W,
    Position = ``Number``) und den Koepfen ``heads`` (Nummern).
    ``reihenfolge`` schreibt die Kanal-Referenzen in anderer Dokument-
    Reihenfolge — die ``Number`` bleibt die Position in ``kanaele``."""
    defs = "\n".join(f' <Channel Name="{k}{i}" Preset="{_PRESET[k]}"/>'
                     for i, k in enumerate(kanaele))
    order = reihenfolge if reihenfolge is not None else range(len(kanaele))
    refs = "\n".join(f'  <Channel Number="{i}">{kanaele[i]}{i}</Channel>'
                     for i in order)
    koepfe = "\n".join(
        "  <Head>\n" + "\n".join(f"   <Channel>{n}</Channel>" for n in h)
        + "\n  </Head>" for h in heads)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Manufacturer>TestCo</Manufacturer>
 <Model>{model}</Model>
 <Type>LED Bar (Pixels)</Type>
{defs}
 <Mode Name="Test">
{refs}
{koepfe}
 </Mode>
</FixtureDefinition>
"""


# Zwei Dimmer (Nr. 0, 1), vier RGB-Koepfe (2..13), zwei eigene Weiss-
# Segmente (14, 15) — dasselbe Geraet wie test_fm46_dimmer_segment._geraet.
WEISSBAR = ["D", "D"] + ["R", "G", "B"] * 4 + ["W", "W"]
RGB_KOEPFE = [[2, 3, 4], [5, 6, 7], [8, 9, 10], [11, 12, 13]]
# Ueber Kreuz: Dimmer 0 sitzt beim ZWEITEN Weiss, Dimmer 1 beim ersten — so
# beweist der Test den Kopf und keine Reihenfolge.
KREUZ = RGB_KOEPFE + [[0, 15], [1, 14]]


def _bibliothek(xml_text: str) -> list[tuple[str, int | None]]:
    """Bibliotheks-Import in eine Speicher-DB; ``[(attribut, segment)]`` des
    Modus in Kanalreihenfolge, dazu ``channels_for_axis`` auf ORM-Kanaelen."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    fd, path = tempfile.mkstemp(suffix=".qxf")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(xml_text)
        with Session(engine) as s:
            assert import_qxf_file(path, s, {})
            s.commit()
            mode = s.execute(select(FixtureMode)).scalars().one()
            chans = s.execute(
                select(FixtureChannel).where(FixtureChannel.mode_id == mode.id)
                .order_by(FixtureChannel.channel_number)).scalars().all()
            _bibliothek.achse = {
                seg: (lambda p: None if p.get("intensity") is None
                      else p["intensity"].channel_number)(
                    AS.channels_for_axis(chans, ACHSE_WEISS, seg))
                for seg in (0, 1)}
            return [(c.attribute, c.segment) for c in chans]
    finally:
        os.remove(path)


def _generator(xml_text: str) -> list[tuple[str, int | None]]:
    from src.ui.widgets.fixture_generator import model_from_qxf
    fd, path = tempfile.mkstemp(suffix=".qxf")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(xml_text)
        m = model_from_qxf(path)
    finally:
        os.remove(path)
    return [(c.attribute, c.segment) for c in m.modes[0].channels]


def _segmente(kanaele) -> dict[int, int]:
    return {i: s for i, (_a, s) in enumerate(kanaele) if s is not None}


class EindeutigeKoepfeTest(unittest.TestCase):

    def test_bibliothek_setzt_zuordnung(self):
        k = _bibliothek(_qxf(WEISSBAR, KREUZ))
        self.assertEqual(_segmente(k), {0: 1, 1: 0})

    def test_channels_for_axis_liefert_den_richtigen_dimmer(self):
        _bibliothek(_qxf(WEISSBAR, KREUZ))
        # Segment 0 (erstes Weiss, Nr. 14) gehoert zu Dimmer Nr. 1 = CH2.
        self.assertEqual(_bibliothek.achse, {0: 2, 1: 1})

    def test_generator_setzt_zuordnung(self):
        self.assertEqual(_segmente(_generator(_qxf(WEISSBAR, KREUZ))),
                         {0: 1, 1: 0})

    def test_head_meint_number_nicht_dokumentposition(self):
        """Die Referenzen stehen rueckwaerts in der Datei; ``<Head>`` nennt die
        ``Number``. Beide Importer muessen dasselbe ergeben."""
        xml = _qxf(WEISSBAR, KREUZ, reihenfolge=list(range(15, -1, -1)))
        self.assertEqual(_segmente(_bibliothek(xml)), {0: 1, 1: 0})
        # Der Generator haelt die Dokumentreihenfolge: Dimmer Nr. 0 steht an
        # Position 15, sein Weiss (Nr. 15) ist dort das ERSTE Weiss (Rang 0).
        # Der Rang zaehlt in der Kanalliste, die gespeichert wird.
        gen = _generator(xml)
        self.assertEqual(_segmente(gen), {15: 0, 14: 1})
        self.assertEqual([gen[i][0] for i in (14, 15)], ["intensity"] * 2)


def _qxf_roh(refs: list[tuple[str, str | None]], heads: list[list[int]]) -> str:
    """Modus aus ``(name, Number)`` in Dokumentreihenfolge; ``None`` = ohne
    ``Number``. Der erste Buchstabe des Namens ist das Kuerzel (D/R/G/B/W)."""
    defs = "\n".join(f' <Channel Name="{n}" Preset="{_PRESET[n[0]]}"/>'
                     for n, _num in refs)
    zeilen = "\n".join(
        f'  <Channel Number="{num}">{n}</Channel>' if num is not None
        else f"  <Channel>{n}</Channel>" for n, num in refs)
    koepfe = "\n".join(
        "  <Head>\n" + "\n".join(f"   <Channel>{x}</Channel>" for x in h)
        + "\n  </Head>" for h in heads)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Manufacturer>TestCo</Manufacturer>
 <Model>Nummern</Model>
 <Type>LED Bar (Pixels)</Type>
{defs}
 <Mode Name="Test">
{zeilen}
{koepfe}
 </Mode>
</FixtureDefinition>
"""


def _paare(xml: str, weg) -> dict[str, str]:
    """``{dimmer_name: weiss_name}`` — die PHYSISCHE Aussage der Zuordnung,
    unabhaengig davon, in welcher Reihenfolge ein Importer die Kanaele
    ablegt."""
    if weg == "bibliothek":
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        fd, path = tempfile.mkstemp(suffix=".qxf")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(xml)
            with Session(engine) as s:
                assert import_qxf_file(path, s, {})
                s.commit()
                k = [(c.name, c.attribute, c.segment) for c in s.execute(
                    select(FixtureChannel)
                    .order_by(FixtureChannel.channel_number)).scalars().all()]
        finally:
            os.remove(path)
    else:
        from src.ui.widgets.fixture_generator import model_from_qxf
        fd, path = tempfile.mkstemp(suffix=".qxf")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(xml)
            m = model_from_qxf(path)
        finally:
            os.remove(path)
        k = [(c.name, c.attribute, c.segment) for c in m.modes[0].channels]
    weiss = [n for n, a, _s in k if a == "color_w"]
    return {n: weiss[seg] for n, _a, seg in k if seg is not None}


class NummernWieDieBibliothekTest(unittest.TestCase):
    """Review: der Generator las fehlende ``Number`` als Dokumentposition und
    liess bei doppelter ``Number`` den letzten gewinnen; die Bibliothek
    nummeriert fehlende auf die naechste freie Nummer und verwirft
    Kollisionen. Dann bekamen beide Wege VERSCHIEDENE Dimmer zugeordnet."""

    RGB = [("R", "4"), ("G", "5"), ("B", "6")]

    def _gleich(self, xml, erwartet):
        self.assertEqual(_paare(xml, "bibliothek"), erwartet)
        self.assertEqual(_paare(xml, "generator"), erwartet)

    def test_fehlende_number(self):
        refs = [("Db", "2"), ("Wb", "3"), ("Dx", None), ("Da", "0"),
                ("Wa", "1")] + self.RGB
        self._gleich(_qxf_roh(refs, [[0, 1], [2, 3]]),
                     {"Da": "Wa", "Db": "Wb"})

    def test_doppelte_number(self):
        refs = [("Da", "0"), ("Wa", "1"), ("Db", "2"), ("Wb", "3"),
                ("Dz", "2")] + self.RGB
        self._gleich(_qxf_roh(refs, [[0, 1], [2, 3]]),
                     {"Da": "Wa", "Db": "Wb"})


class NichtsSetzenTest(unittest.TestCase):

    def _leer(self, xml):
        self.assertEqual(_segmente(_bibliothek(xml)), {})
        self.assertEqual(_segmente(_generator(xml)), {})

    def test_ohne_head(self):
        self._leer(_qxf(WEISSBAR, []))

    def test_nur_koepfe_ohne_weiss(self):
        self._leer(_qxf(WEISSBAR, RGB_KOEPFE + [[0, 2], [1, 5]]))

    def test_zwei_dimmer_in_einem_kopf(self):
        self._leer(_qxf(WEISSBAR, [[0, 1, 14], [15]]))

    def test_zwei_weiss_in_einem_kopf(self):
        self._leer(_qxf(WEISSBAR, [[0, 14, 15]]))

    def test_dimmer_in_mehreren_weiss_koepfen(self):
        """Ein Master-Dimmer, den QLC+ in jeden Kopf legt, ist kein Segment-
        Dimmer — so in echten Profilen gesehen."""
        k = _bibliothek(_qxf(WEISSBAR, [[0, 14], [0, 15], [1, 15]]))
        # Dimmer 0 faellt heraus; Dimmer 1 ist eindeutig bei Segment 1.
        self.assertEqual(_segmente(k), {1: 1})

    def test_ohne_eigene_weiss_achse(self):
        """Zwei RGBW-Koepfe mit je einem Dimmer: Weiss gehoert zum Farbkopf,
        es gibt keine eigene Weiss-Achse -> keine Zuordnung."""
        kan = ["D", "R", "G", "B", "W", "D", "R", "G", "B", "W"]
        self._leer(_qxf(kan, [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]]))


class ReineFunktionTest(unittest.TestCase):

    @staticmethod
    def _chans(segmente=(None, None)):
        k = [N(attribute="intensity", segment=s) for s in segmente]
        k += [N(attribute=a) for a in ("color_r", "color_g", "color_b") * 4]
        return k + [N(attribute="color_w"), N(attribute="color_w")]

    def test_segment_doppelt_vergeben(self):
        self.assertEqual(segmente_aus_heads(self._chans(), [[0, 14], [1, 14]]),
                         {})

    def test_vorhandene_zuordnung_bleibt(self):
        self.assertEqual(segmente_aus_heads(self._chans((0, None)), KREUZ),
                         {})
        self.assertEqual(segmente_aus_heads(self._chans((1, None)), KREUZ),
                         {1: 0})

    def test_unsinnige_indizes(self):
        self.assertEqual(segmente_aus_heads(self._chans(), [[0, 99, -1, True]]),
                         {})
        self.assertEqual(segmente_aus_heads([], KREUZ), {})


if __name__ == "__main__":
    unittest.main()
