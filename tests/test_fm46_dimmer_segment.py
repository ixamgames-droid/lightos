"""FM-46 (Etappe 1): gespeicherte Zuordnung Dimmer -> Weiss-Segment.

Bei Geraeten mit EIGENER Weiss-Achse und MEHREREN Dimmern steht in der
Kanalliste nicht, welcher Dimmer welches Weiss-Segment dimmt. Bisher schrieb
die Matrix dann bewusst keinen Dimmer (Befund C; FM-54 dimmt das Weiss
seitdem wenigstens in der Matrix). Entscheidung des Projektinhabers vom 02.10.:
ein Mensch traegt die Zuordnung im Fixture-Editor/-Generator ein
(``FixtureChannel.segment``), und NUR diese gespeicherte Zuordnung wirkt —
zur Laufzeit wird weiterhin nicht geraten.

Geprueft wird hier der Kern (ohne Dialoge):

* Migration einer Alt-DB ohne die Spalte,
* ``segment_von`` ueber alle Kanalarten,
* ``channels_for_axis`` mit/ohne/widerspruechlicher Zuordnung,
* die Folgen: Matrix-Ausgabe nach dem echten Merge (wie FM-54),
  ``weiss_cell_values``, ``weiss_dimmer_key``/``weiss_programmer_key``,
* der Vorschlag aus der Kanalreihenfolge und die Hinweis-Bedingung.

Die Roundtrips der beiden Editoren stehen in
``tests/test_fm46_editoren_segment.py``.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from collections import namedtuple
from types import SimpleNamespace as N
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as AS                                  # noqa: E402
from src.core.dimmer_segmente import (DIMMER_ATTRS, segment_von,  # noqa: E402
                                      vorschlag_dimmer_segmente,
                                      zuordnung_fehlt)
from src.core.dmx.universe import Universe                       # noqa: E402
from src.core.engine.function_manager import FunctionManager    # noqa: E402
from src.core.engine.rgb_matrix import MatrixStyle, RgbMatrixInstance  # noqa: E402
from src.core.group_cells import ACHSE_WEISS                     # noqa: E402


def _ch(attr, nr, segment=None):
    return N(attribute=attr, channel_number=nr, default_value=0,
             highlight_value=255, ranges=[], name=attr, segment=segment)


def _geraet(segmente=(None, None)):
    """Zwei Dimmer (CH1, CH2), vier RGB-Koepfe, zwei eigene Weiss-Segmente —
    dasselbe Geraet wie ``test_fm54_weiss_intensitaet._geraet(2)``, nur dass
    die Dimmer eine Zuordnung tragen koennen."""
    kanaele = [_ch("intensity", i + 1, s) for i, s in enumerate(segmente)]
    nr = len(kanaele) + 1
    for _ in range(4):
        for a in ("color_r", "color_g", "color_b"):
            kanaele.append(_ch(a, nr))
            nr += 1
    kanaele += [_ch("color_w", nr), _ch("color_w", nr + 1)]
    return kanaele


def _nr(proj, attr):
    ch = proj.get(attr)
    return None if ch is None else ch.channel_number


class DieDefinitionenSindDieselben(unittest.TestCase):

    def test_dimmer_attribute_wie_app_state(self):
        self.assertEqual(DIMMER_ATTRS, AS._DIM_INTENSITY_ATTRS)


class MigrationTest(unittest.TestCase):
    """Eine fixtures.db von vor FM-46 hat keine Spalte ``channels.segment``.
    Das ORM fragt ALLE Modell-Spalten ab — ohne ALTER TABLE waere jede
    bestehende Bibliothek unladbar."""

    def test_alte_db_ohne_spalte_laeuft_weiter(self):
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from src.core.database.models import (FixtureChannel,
                                              create_all_idempotent,
                                              migrate_fixtures_db)
        d = tempfile.mkdtemp()
        pfad = os.path.join(d, "alt.db")
        con = sqlite3.connect(pfad)
        con.execute(
            "CREATE TABLE channels (id INTEGER PRIMARY KEY, mode_id INTEGER, "
            "channel_number INTEGER, name VARCHAR(80), attribute VARCHAR(40), "
            "default_value INTEGER, highlight_value INTEGER, invert BOOLEAN, "
            "resolution VARCHAR(20))")
        con.execute("INSERT INTO channels VALUES (1, 1, 1, 'Dimmer', "
                    "'intensity', 0, 255, 0, '8bit')")
        con.commit()
        con.close()
        eng = create_engine(f"sqlite:///{pfad}")
        create_all_idempotent(eng)
        migrate_fixtures_db(eng)
        migrate_fixtures_db(eng)        # idempotent
        with Session(eng) as s:
            ch = s.execute(select(FixtureChannel)).scalars().one()
            self.assertEqual(ch.name, "Dimmer")
            self.assertIsNone(ch.segment, "Alt-Kanal: keine Zuordnung")
            ch.segment = 1
            s.commit()
        with Session(eng) as s:
            self.assertEqual(s.execute(select(FixtureChannel)).scalars()
                             .one().segment, 1)
        eng.dispose()


class SegmentVonTest(unittest.TestCase):
    """Das Feld wird ueber JEDE Kanalart gelesen — und wo es fehlt oder kein
    echter Wert ist, heisst das „keine Zuordnung"."""

    def test_kanalarten(self):
        from src.core.database.models import FixtureChannel
        orm = FixtureChannel(attribute="intensity", channel_number=1,
                             name="D", segment=2)
        self.assertEqual(segment_von(orm), 2)
        self.assertIsNone(segment_von(FixtureChannel(attribute="intensity",
                                                     channel_number=1, name="D")))
        # Dual-Tilt-Proxy delegiert ans Original.
        self.assertEqual(segment_von(AS._AttrOverrideChannel(orm, "tilt")), 2)
        # Builtin-/Fremd-Tupel ohne das Feld.
        Alt = namedtuple("Alt", "attribute channel_number")
        self.assertIsNone(segment_von(Alt("intensity", 1)))
        self.assertIsNone(segment_von(N(attribute="intensity")))
        self.assertEqual(segment_von({"attribute": "intensity", "segment": 0}), 0)
        self.assertIsNone(segment_von({"attribute": "intensity"}))

    def test_keine_scheinwerte(self):
        # Ein Mock liefert fuer jedes Attribut ein Objekt mit __int__ == 1 —
        # das darf nicht als „Segment 1" durchgehen.
        self.assertIsNone(segment_von(mock.MagicMock()))
        self.assertIsNone(segment_von(N(segment=True)))
        self.assertIsNone(segment_von(N(segment=-1)))
        self.assertIsNone(segment_von(N(segment="1")))


class ChannelsForAxisTest(unittest.TestCase):

    def test_ohne_zuordnung_wie_bisher(self):
        for seg in (0, 1):
            proj = AS.channels_for_axis(_geraet(), ACHSE_WEISS, seg)
            self.assertNotIn("intensity", proj)
            self.assertIn("color_w", proj)

    def test_mit_zuordnung_der_eingetragene_dimmer(self):
        # Ueber Kreuz eingetragen: CH1 dimmt Segment 2, CH2 Segment 1 — so
        # beweist der Test die gespeicherte Zuordnung und keine Reihenfolge.
        k = _geraet((1, 0))
        self.assertEqual(_nr(AS.channels_for_axis(k, ACHSE_WEISS, 0), "intensity"), 2)
        self.assertEqual(_nr(AS.channels_for_axis(k, ACHSE_WEISS, 1), "intensity"), 1)

    def test_teilweise_zuordnung(self):
        k = _geraet((None, 0))
        self.assertEqual(_nr(AS.channels_for_axis(k, ACHSE_WEISS, 0), "intensity"), 2)
        self.assertNotIn("intensity", AS.channels_for_axis(k, ACHSE_WEISS, 1))

    def test_widerspruch_faehrt_keinen(self):
        k = _geraet((0, 0))
        self.assertNotIn("intensity", AS.channels_for_axis(k, ACHSE_WEISS, 0))

    def test_kein_phantom_segment(self):
        k = _geraet((0, 5))
        self.assertEqual(AS.channels_for_axis(k, ACHSE_WEISS, 5), {})

    def test_farbachse_unberuehrt(self):
        k = _geraet((1, 0))
        self.assertEqual(AS.channels_for_axis(k, "rgb", 0),
                         AS.channels_for_head(k, 0))

    def test_ueber_dual_tilt_proxy(self):
        k = [AS._AttrOverrideChannel(c, c.attribute) for c in _geraet((1, 0))]
        self.assertEqual(_nr(AS.channels_for_axis(k, ACHSE_WEISS, 0), "intensity"), 2)


class _MatrixBasis(unittest.TestCase):

    def setUp(self):
        alt = AS.get_channels_for_patched
        self.addCleanup(setattr, AS, "get_channels_for_patched", alt)

    def _lauf(self, segmente, drive, *, inten=0.5):
        """Vollweiss-Frame auf beiden Weiss-Segmenten durch den ECHTEN Merge
        (``FunctionManager.tick``) — gemessen wird das Endergebnis."""
        kanaele = _geraet(segmente)
        AS.get_channels_for_patched = lambda fx, k=kanaele: k
        fx = N(fid=1, universe=1, address=1, fixture_type="led_bar",
               fixture_profile_id=1, mode_name="m", channel_count=len(kanaele))
        mx = RgbMatrixInstance(name="FM46")
        mx.style = MatrixStyle.RGB
        mx.cols, mx.rows = 2, 1
        mx.fixture_grid = [None, None]
        mx.head_grid = [None, None]
        mx.weiss_grid = [(1, 0), (1, 1)]
        mx.drive_intensity = drive
        mx.intensity = inten
        mx._render = lambda phase: [(255, 255, 255)] * 2
        fm = FunctionManager()
        fm.add(mx)
        fm.start(mx.id)
        uni = Universe(1)
        fm.tick({1: uni}, [fx], 0.02)
        dimmer = [uni.get_channel(c.channel_number) for c in kanaele
                  if c.attribute == "intensity"]
        weiss = [uni.get_channel(c.channel_number) for c in kanaele
                 if c.attribute == "color_w"]
        return dimmer, weiss


class MatrixMitZuordnungTest(_MatrixBasis):

    def test_dimmer_wird_getrieben_und_weiss_nicht_doppelt_gedimmt(self):
        """Mit Zuordnung zieht die Matrix die Dimmer auf, der Merge halbiert
        SIE — das Weiss bleibt im Wert voll (sonst stuende es physisch auf
        einem Viertel, FM-41 „quadratisch")."""
        dimmer, weiss = self._lauf((1, 0), drive=True)
        self.assertEqual(dimmer, [127, 127])
        self.assertEqual(weiss, [255, 255])

    def test_teilweise_zuordnung(self):
        """Segment 1 hat seinen Dimmer (CH2), Segment 2 keinen. Der Rueckfall
        (FM-46 Etappe 2) oeffnet fuer Segment 2 nur Dimmer, die an den
        Abschnitt seines Weiss grenzen — das ist allein CH2, und der gehoert
        Segment 1. Also faehrt dort keiner, und die Matrix dimmt das Weiss
        selbst (FM-54) — lieber zu wenig als einen fremden Dimmer."""
        dimmer, weiss = self._lauf((None, 0), drive=True)
        self.assertEqual(dimmer, [0, 127])
        self.assertEqual(weiss, [255, 127])

    def test_ohne_mit_treiben_gehoert_der_dimmer_dem_nutzer(self):
        dimmer, weiss = self._lauf((1, 0), drive=False)
        self.assertEqual(dimmer, [0, 0])
        self.assertEqual(weiss, [127, 127])

    def test_ohne_zuordnung_rueckfall(self):
        """Gegenprobe = ``test_fm54::test_zwei_dimmer_dimmer_mit_treiben``.
        Seit FM-46 Etappe 2 faehrt ohne Zuordnung der freie Dimmer, der an
        den Abschnitt des Weiss grenzt (CH2; CH1 grenzt nur an Leeres und an
        CH2). Vorher ``[0, 0]`` / ``[127, 127]`` — am Geraet dunkel, sobald
        die Dimmer auf 0 stehen."""
        dimmer, weiss = self._lauf((None, None), drive=True)
        self.assertEqual(dimmer, [0, 127])
        self.assertEqual(weiss, [255, 255])


class FolgestellenTest(unittest.TestCase):
    """Die Stellen, die ``channels_for_axis`` lesen, nutzen die Zuordnung
    ohne eigenen Code."""

    def setUp(self):
        alt = AS.get_channels_for_patched
        self.addCleanup(setattr, AS, "get_channels_for_patched", alt)
        self.kanaele = _geraet((1, 0))
        AS.get_channels_for_patched = lambda fx: self.kanaele
        self.fx = N(fid=1, universe=1, address=1, fixture_type="led_bar",
                    fixture_profile_id=1, mode_name="m", head_mode="auto",
                    channel_count=len(self.kanaele))

    def test_weiss_cell_values(self):
        from src.core.matrix_pattern import weiss_cell_values
        werte = weiss_cell_values(self.fx, 0, (255, 255, 255))
        self.assertEqual(werte.get(2), 255, "CH2 dimmt Segment 1")
        self.assertNotIn(1, werte)
        werte = weiss_cell_values(self.fx, 1, (255, 255, 255))
        self.assertEqual(werte.get(1), 255)
        self.assertNotIn(2, werte)
        self.assertNotIn(1, weiss_cell_values(self.fx, 1, (255, 255, 255),
                                              drive_intensity=False))

    def test_weiss_cell_values_ohne_zuordnung(self):
        """FM-46 Etappe 2: ohne Zuordnung der angrenzende freie Dimmer —
        derselbe Rueckfall wie im Renderer; ohne ``drive_intensity`` keiner."""
        from src.core.matrix_pattern import weiss_cell_values
        self.kanaele = _geraet()
        werte = weiss_cell_values(self.fx, 0, (255, 255, 255))
        self.assertEqual(werte.get(2), 255)
        self.assertNotIn(1, werte)
        werte = weiss_cell_values(self.fx, 0, (255, 255, 255),
                                  drive_intensity=False)
        self.assertNotIn(1, werte)
        self.assertNotIn(2, werte)

    def test_programmer_schluessel(self):
        st = N(_patch_cache=[self.fx])
        self.assertEqual(AS.AppState.weiss_dimmer_key(st, 1, 0), "intensity#1")
        self.assertEqual(AS.AppState.weiss_dimmer_key(st, 1, 1), "intensity")
        self.assertEqual(AS.AppState.weiss_programmer_key(st, 1, 0), "color_w")
        self.assertEqual(AS.AppState.weiss_programmer_key(st, 1, 1), "color_w#1")
        self.kanaele = _geraet()
        self.assertIsNone(AS.AppState.weiss_dimmer_key(st, 1, 0))


I, W, R, G, B = "intensity", "color_w", "color_r", "color_g", "color_b"


def _k(*attrs):
    return [{"attribute": a} for a in attrs]


class VorschlagTest(unittest.TestCase):

    def test_dimmer_vor_weiss(self):
        self.assertEqual(vorschlag_dimmer_segmente(_k(I, W, I, W)), {0: 0, 2: 1})

    def test_dimmer_nach_weiss(self):
        self.assertEqual(vorschlag_dimmer_segmente(_k(W, I, W, I)), {1: 0, 3: 1})

    def test_bloecke_gleicher_groesse(self):
        self.assertEqual(
            vorschlag_dimmer_segmente(_k(I, R, G, B, W, I, R, G, B, W)),
            {0: 0, 5: 1})

    def test_mit_vorspann_und_objekten(self):
        k = [N(attribute=a) for a in ("shutter", I, W, I, W, I, W)]
        self.assertEqual(vorschlag_dimmer_segmente(k), {1: 0, 3: 1, 5: 2})

    def test_uneindeutig_leer(self):
        for name, attrs in (
                ("Dimmer am Stueck", (I, I, R, G, B, W, W)),
                ("gemischt vor/nach", (I, W, W, I)),
                ("ungleiche Bloecke", (I, R, W, I, R, G, W)),
                ("Weiss am Stueck", (W, W, I, R, I, R)),
        ):
            with self.subTest(name):
                self.assertEqual(vorschlag_dimmer_segmente(_k(*attrs)), {})

    def test_ungleiche_anzahl_leer(self):
        self.assertEqual(vorschlag_dimmer_segmente(_k(I, W, I, W, I)), {})
        self.assertEqual(vorschlag_dimmer_segmente(_k(I, W, W, W)), {})
        self.assertEqual(vorschlag_dimmer_segmente(_k(I, W)), {})
        self.assertEqual(vorschlag_dimmer_segmente(_k(I, W, I, W, "dimmer", "dimmer")), {})
        self.assertEqual(vorschlag_dimmer_segmente([]), {})


class HinweisTest(unittest.TestCase):

    def test_erscheint_und_verschwindet(self):
        k = [{"attribute": c.attribute, "segment": c.segment} for c in _geraet()]
        self.assertTrue(zuordnung_fehlt(k))
        k[1]["segment"] = 0
        self.assertFalse(zuordnung_fehlt(k))

    def test_nicht_ohne_grund(self):
        # ein Dimmer -> geteilt, faehrt ohnehin mit
        self.assertFalse(zuordnung_fehlt(_k(I, R, G, B, R, G, B, W)))
        # Weiss im Pixel (2 Koepfe, 2 Weiss) -> keine eigene Achse
        self.assertFalse(zuordnung_fehlt(_k(I, R, G, B, W, I, R, G, B, W)))
        # kein Weiss
        self.assertFalse(zuordnung_fehlt(_k(I, R, G, B, I, R, G, B)))


class DimmerAnkerTest(unittest.TestCase):
    """Review-Befund (1): ist der zugeordnete Dimmer das ERSTE Vorkommen,
    heisst sein Schluessel ``intensity`` — und den spiegelt der DMX-Flush
    (``resolve_attr_channels``) auf jedes weitere Vorkommen ohne eigenen Wert.
    Gemessen: „Weiss 1 hell" zog den Dimmer von Segment 2 mit auf 255.

    Gemessen wird ueber ``resolve_attr_channels`` — dieselbe Spiegelregel wie
    der Flush (Docstring dort)."""

    def setUp(self):
        alt = AS.get_channels_for_patched
        self.addCleanup(setattr, AS, "get_channels_for_patched", alt)
        self.kanaele = _geraet((0, 1))
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

    def test_segment_1_dimmer_ist_basis_schluessel(self):
        self.assertEqual(self.st.weiss_dimmer_key(1, 0), "intensity")
        self.assertTrue(self.st.weiss_dimmer_setzen(1, 0, 255))
        self.assertEqual(self._dmx(), [255, 0],
                         "der Dimmer von Segment 2 darf nicht mitgehen")

    def test_segment_2(self):
        self.assertTrue(self.st.weiss_dimmer_setzen(1, 1, 255))
        self.assertEqual(self._dmx(), [0, 255])

    def test_ueber_kreuz(self):
        self.kanaele = _geraet((1, 0))
        self.assertTrue(self.st.weiss_dimmer_setzen(1, 1, 255))
        self.assertEqual(self._dmx(), [255, 0])

    def test_geteilter_master_bleibt_geteilt(self):
        """Ein EINZELNER Dimmer ist geteilt — keine Anker."""
        self.kanaele = [_ch("intensity", 1), _ch("color_r", 2),
                        _ch("color_w", 3), _ch("color_w", 4)]
        self.assertEqual(self.st.weiss_dimmer_anker_keys(1, "intensity"), [])

    def test_scope_nimmt_anker_mit(self):
        """Snapshot-Scope: mit dem Basis-Dimmer gehoeren die Anker in die
        Aufnahme, sonst fuehre der Abruf beide Dimmer."""
        keys = self.st._weiss_scope_keys(1, [1])
        self.assertIn("intensity#1", keys)
        keys = self.st._weiss_scope_keys(1, [0])
        self.assertTrue({"intensity", "intensity#1"} <= keys, keys)


class ZuordnungProblemeTest(unittest.TestCase):
    """Review-Befund (3)."""

    @staticmethod
    def _k(segmente):
        return [{"attribute": c.attribute, "segment": c.segment}
                for c in _geraet(segmente)]

    def test_saubere_zuordnung(self):
        from src.core.dimmer_segmente import zuordnung_probleme
        self.assertEqual(zuordnung_probleme(self._k((1, 0))), [])
        self.assertEqual(zuordnung_probleme(self._k((None, None))), [],
                         "das Fehlen meldet zuordnung_fehlt")

    def test_doppelt_unvollstaendig_ausserhalb(self):
        from src.core.dimmer_segmente import zuordnung_probleme
        p = zuordnung_probleme(self._k((0, 0)))
        self.assertEqual(len(p), 1)
        self.assertIn("Weiß-Segment 1 ist mehrfach vergeben (Kanal 1, 2)", p[0])
        p = zuordnung_probleme(self._k((None, 0)))
        self.assertEqual(p, ["Dimmer auf Kanal 1 hat kein Weiß-Segment — gewollt?"])
        p = zuordnung_probleme(self._k((0, 7)))
        self.assertIn("Weiß-Segment 8 gibt es nicht", p[0])


if __name__ == "__main__":
    unittest.main()
