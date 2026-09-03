"""FM-41 Scheibe 1 — die Weiss-Leiste ist eine zweite ACHSE, kein 49. Kopf.

Robins ZQ06121 traegt 48 RGB-Zonen (4x12) **und** 8 eigene Warmweiss-Segmente,
die mittig zwischen Reihe 2 und 3 sitzen und je anderthalb RGB-Spalten abdecken.
Die Bibliothek sagt es selbst vorher: „die beiden Raster fallen also NICHT
zusammen."

Bis 2026-09-03 kannte das Zellformat nur EINEN Kopfindex — und der adressierte
alle Achsen zugleich. Gemessen liefert ``channels_for_head(chans, 3)``
``color_r = CH12 'Zone 4 Rot'`` **und** ``color_w = CH150 'Weiss-Zone 4'``: die
Zellen K1..K8 fuhren acht willkuerliche Weiss-Segmente mit, K9..K48 hatten gar
keins. Das ist der „Zuordnungs-Salat" aus der Rig-Meldung.

**Die Entscheidung des Betreibers (03.09.2026):** ein solches Geraet zeigt beim
Gruppenbauen **zwei** ansprechbare Saetze — „einmal die RGB-Variante und einmal
die, die nur weiss kann" — damit eine Gruppe nur aus Weiss, nur aus RGB oder aus
beidem gebaut werden kann. Ausdrueckliche Auflage: **generisch aus den Kanaelen
abgeleitet, kein Geraete-Sonderfall.**

**Diese Scheibe ist der KERN und aendert bewusst kein Verhalten:** Zellformat,
Parser und Projektion koennen die Achse, aber noch ruft sie niemand auf. Der
Gruppen-Editor und der Renderer folgen in Scheibe 2. Ein rein additiver Kern ist
gefahrlos — anders als „Gate scharf, Verdrahtung folgt" (AGENTS.md Regel 5).
"""
from __future__ import annotations
import os
import unittest

from src.core.group_cells import ACHSE_FARBE, ACHSE_WEISS
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.group_cells import (ACHSE_FARBE, ACHSE_WEISS, achsen_zellen,
                                  parse_group_cell, parse_zelle, zelle_fuer)


def _ch(attr: str, nr: int):
    return SimpleNamespace(attribute=attr, channel_number=nr)


class ZellFormatTest(unittest.TestCase):

    def test_ganzes_geraet_unveraendert(self):
        self.assertEqual(parse_zelle(5), (5, None, None))
        self.assertEqual(parse_zelle("5"), (5, None, None))

    def test_farb_kopf_unveraendert(self):
        """Bestandsformat: `"5:2"` bleibt exakt, was es war — sonst laedt keine
        einzige gespeicherte Gruppe mehr richtig."""
        self.assertEqual(parse_zelle("5:2"), (5, ACHSE_FARBE, 2))

    def test_weiss_segment(self):
        self.assertEqual(parse_zelle("5:w3"), (5, ACHSE_WEISS, 3))
        self.assertEqual(parse_zelle("5:w0"), (5, ACHSE_WEISS, 0))

    def test_negativer_index_ist_unparsbar__auf_BEIDEN_achsen(self):
        """Dieselbe Regel wie FM-45 fuer Kopf-Zellen — der Fehler darf im neuen
        Format nicht wiederholt werden."""
        self.assertEqual(parse_zelle("5:-1"), (None, None, None))
        self.assertEqual(parse_zelle("5:w-1"), (None, None, None))

    def test_unbekannte_achse_ist_unparsbar(self):
        for v in ("5:x9", "w3", "", "5:", ":3"):
            with self.subTest(wert=v):
                self.assertEqual(parse_zelle(v), (None, None, None))

    def test_hin_und_zurueck(self):
        """`zelle_fuer` ist die EINE Stelle, an der ein Zellwert entsteht —
        sonst steht in einem Jahr das zweite `f"{fid}:w{n}"` im Baum."""
        for fid, achse, index in ((5, None, None), (5, ACHSE_FARBE, 2),
                                  (5, ACHSE_WEISS, 3)):
            with self.subTest(achse=achse):
                self.assertEqual(parse_zelle(zelle_fuer(fid, achse, index)),
                                 (fid, achse, index))

    def test_unbekannte_achse_beim_bauen_wirft(self):
        """Still einen kaputten Zellwert zu erzeugen waere schlimmer als ein
        Fehler an der Stelle, an der jemand ihn baut."""
        with self.assertRaises(ValueError):
            zelle_fuer(5, "gibtsnicht", 0)


class DieAlteFassadeBleibtVerlustbehaftetTest(unittest.TestCase):
    """★★ Der wichtigste Test dieser Datei.

    `parse_group_cell` liefert fuer eine Weiss-Zelle ``(None, None)`` — „kenne
    ich nicht" — und ausdruecklich NICHT ``(5, None)``. Letzteres waere die
    stille Befoerderung eines Weiss-Segments zum GANZEN Geraet, also genau in
    die gefaehrliche Richtung (dieselbe Ueberlegung wie bei FM-45s negativem
    Kopfindex).

    Daran haengt die Groesse dieser Aenderung: 61 Aufrufstellen in 12 Dateien
    behalten ihren 2-Tupel-Vertrag und sehen eine Weiss-Zelle schlicht **nicht**,
    statt sie **falsch** zu sehen.
    """

    def test_weiss_zelle_ist_fuer_die_alte_fassade_unbekannt(self):
        self.assertEqual(parse_group_cell("5:w3"), (None, None))

    def test_und_wird_NICHT_zum_ganzen_geraet_befoerdert(self):
        fid, head = parse_group_cell("5:w3")
        self.assertIsNone(fid, "ein Weiss-Segment wurde zum ganzen Geraet")
        self.assertIsNone(head)

    def test_bestandsformate_unveraendert(self):
        self.assertEqual(parse_group_cell("5"), (5, None))
        self.assertEqual(parse_group_cell("5:2"), (5, 2))


class AchsenZellenTest(unittest.TestCase):

    def test_je_achse_getrennt(self):
        zellen = ["1", "1:0", "1:w3", "2:w0", "2:1"]
        self.assertEqual(achsen_zellen(zellen, ACHSE_WEISS), {1: {3}, 2: {0}})
        self.assertEqual(achsen_zellen(zellen, ACHSE_FARBE), {1: {0}, 2: {1}})

    def test_ganz_geraet_zaehlt_fuer_keine_achse(self):
        """`"1"` meint das ganze Geraet und damit alles — es auf eine Achse zu
        zaehlen waere eine Einschraenkung, die niemand gewaehlt hat."""
        self.assertEqual(achsen_zellen(["1"], ACHSE_WEISS), {})
        self.assertEqual(achsen_zellen(["1"], ACHSE_FARBE), {})


class ProjektionTest(unittest.TestCase):
    """Die Kanaele EINES Emitters — an einem Nachbau der ZQ06121-Bauform:
    geteilter Dimmer + Shutter, 4 RGB-Zonen, 2 Weiss-Segmente."""

    def setUp(self):
        self.chans = [_ch("intensity", 1), _ch("shutter", 2)]
        nr = 3
        for _ in range(4):
            for a in ("color_r", "color_g", "color_b"):
                self.chans.append(_ch(a, nr)); nr += 1
        for _ in range(2):
            self.chans.append(_ch("color_w", nr)); nr += 1

    def _nummern(self, d):
        return {k: v.channel_number for k, v in d.items()}

    def test_weiss_segment_trifft_nur_seinen_kanal(self):
        from src.core.app_state import channels_for_axis
        self.assertEqual(self._nummern(channels_for_axis(self.chans, ACHSE_WEISS, 0)),
                         {"color_w": 15, "intensity": 1, "shutter": 2})
        self.assertEqual(self._nummern(channels_for_axis(self.chans, ACHSE_WEISS, 1)),
                         {"color_w": 16, "intensity": 1, "shutter": 2})

    def test_die_geteilten_master_kommen_mit(self):
        """★ Ohne sie ist das Segment richtig adressiert und trotzdem dunkel —
        der gemeinsame Dimmer steht davor auf 0. Genau diese Falle steht in
        `matrix_pattern` als beim ersten Live-Test passiert dokumentiert."""
        from src.core.app_state import channels_for_axis
        d = channels_for_axis(self.chans, ACHSE_WEISS, 0)
        self.assertIn("intensity", d)
        self.assertIn("shutter", d)

    def test_kein_phantom_emitter(self):
        """Dieselbe Grenze wie FM-45: gibt es das Segment nicht, kommt {} —
        und NICHT die geteilten Kanaele allein, die den Master-Dimmer des ganzen
        Geraets hochzoegen."""
        from src.core.app_state import channels_for_axis
        self.assertEqual(channels_for_axis(self.chans, ACHSE_WEISS, 2), {})
        self.assertEqual(channels_for_axis(self.chans, ACHSE_WEISS, 99), {})

    def test_weiss_achse_bringt_KEINE_farbkanaele_mit(self):
        """Der Kern der Trennung: ein Weiss-Segment ist kein Farbkopf."""
        from src.core.app_state import channels_for_axis
        d = channels_for_axis(self.chans, ACHSE_WEISS, 0)
        self.assertNotIn("color_r", d)
        self.assertNotIn("color_g", d)
        self.assertNotIn("color_b", d)

    def test_farb_achse_delegiert_unveraendert(self):
        """`achse="rgb"` muss byte-gleich zu `channels_for_head` sein — die
        Regel darf nicht ein zweites Mal formuliert werden (Doppelstellen-Regel,
        Review-Checkliste 17)."""
        from src.core.app_state import channels_for_axis, channels_for_head
        for i in range(4):
            with self.subTest(kopf=i):
                self.assertEqual(channels_for_axis(self.chans, ACHSE_FARBE, i),
                                 channels_for_head(self.chans, i))

    def test_ohne_achse_das_ganze_geraet(self):
        from src.core.app_state import channels_for_axis
        d = channels_for_axis(self.chans, None, None)
        self.assertIn("color_r", d)
        self.assertIn("color_w", d)
        self.assertIn("intensity", d)

    def test_unbekannte_achse_liefert_nichts(self):
        from src.core.app_state import channels_for_axis
        self.assertEqual(channels_for_axis(self.chans, "gibtsnicht", 0), {})


class AmEchtenGeraetTest(unittest.TestCase):
    """Gegen das ECHTE Profil aus einer frisch geseedeten Bibliothek — die
    synthetischen Kanaele oben koennten die Bauform verfehlen."""

    @classmethod
    def setUpClass(cls):
        from _fixture_quelle import frische_library
        cls._eng = frische_library(cls)

    def _chans(self):
        from sqlalchemy import select
        from sqlalchemy.orm import Session, selectinload
        from src.core.database.models import FixtureProfile, FixtureMode
        with Session(self._eng) as s:
            p = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels))
                .where(FixtureProfile.short_name == "ZQ06121")).scalars().first()
            m = max(p.modes, key=lambda m: m.channel_count)
            return [SimpleNamespace(attribute=c.attribute,
                                    channel_number=c.channel_number)
                    for c in sorted(m.channels, key=lambda c: c.channel_number)]

    def test_acht_weiss_segmente_einzeln_erreichbar(self):
        from src.core.app_state import channels_for_axis
        chans = self._chans()
        kanaele = []
        for i in range(8):
            d = channels_for_axis(chans, ACHSE_WEISS, i)
            self.assertIn("color_w", d, f"Weiss-Segment {i} nicht erreichbar")
            kanaele.append(d["color_w"].channel_number)
        self.assertEqual(kanaele, list(range(147, 155)),
                         "die acht Segmente liegen nicht auf CH147..154")

    def test_das_neunte_gibt_es_nicht(self):
        from src.core.app_state import channels_for_axis
        self.assertEqual(channels_for_axis(self._chans(), ACHSE_WEISS, 8), {})

    def test_der_gemessene_zuordnungs_salat_ist_benannt(self):
        """★ Der Ausgangsbefund, als Messung festgehalten: der FARB-Kopf 3
        traegt heute auch das 4. Weiss-Segment mit. Diese Scheibe aendert das
        NICHT (das waere eine Verhaltensaenderung im Programmer) — sie schafft
        nur die getrennte Adressierung daneben. Der Test haelt den Ist-Zustand
        fest, damit Scheibe 2 ihn bewusst umstellt statt versehentlich."""
        from src.core.app_state import channels_for_head
        d = channels_for_head(self._chans(), 3)
        self.assertEqual(d["color_r"].channel_number, 12)
        self.assertEqual(d["color_w"].channel_number, 150,
                         "der Ist-Zustand hat sich geaendert — Scheibe 2 pruefen")


class SegmentZaehlungTest(unittest.TestCase):
    """FM-41 Scheibe 2: EINE Zaehl-Regel fuer die Weiss-Achse.

    Dieselbe Zaehlung stand bis 2026-09-03 zweimal inline im Baum —
    ``visualizer_window`` (``kanal_attrs.count("color_w")``) und
    ``rgb_matrix.write`` (Generator-Summe) — und Scheibe 1 legte implizit eine
    dritte daneben. Drei Fassungen derselben Frage sind die Doppelstellen-Klasse
    aus Review-Checkliste 17.
    """

    @classmethod
    def setUpClass(cls):
        from _fixture_quelle import frische_library
        cls._eng = frische_library(cls)

    def _chans(self, kurz):
        from sqlalchemy import select
        from sqlalchemy.orm import Session, selectinload
        from src.core.database.models import FixtureProfile, FixtureMode
        with Session(self._eng) as s:
            p = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels))
                .where(FixtureProfile.short_name == kurz)).scalars().first()
            m = max(p.modes, key=lambda m: m.channel_count)
            return [SimpleNamespace(attribute=c.attribute,
                                    channel_number=c.channel_number)
                    for c in sorted(m.channels, key=lambda c: c.channel_number)]

    def test_an_echten_profilen(self):
        from src.core.app_state import weiss_segment_count_for_channels as W
        for kurz, erwartet in (("ZQ06121", 8), ("STAIRMB5X5", 25),
                               ("DOTZMATRIX", 0), ("MH16", 0)):
            with self.subTest(geraet=kurz):
                self.assertEqual(W(self._chans(kurz)), erwartet)

    def test_null_heisst_null__anders_als_bei_den_farbkoepfen(self):
        """★ `color_head_count` rundet auf 1 auf („ein Geraet hat immer
        mindestens einen Farbkopf"). Fuer Weiss waere das falsch: ein erfundenes
        Segment ist sofort eine Phantom-Zelle."""
        from src.core.app_state import (weiss_segment_count_for_channels as W,
                                        color_head_count_for_channels as C)
        chans = self._chans("MH16")
        self.assertEqual(W(chans), 0)
        self.assertEqual(C(None, chans), 1, "Vorbedingung: Farbkoepfe runden auf")


class ZaehlungNichtProZelleTest(unittest.TestCase):
    """★★ Die Zahl ist eine Eigenschaft des GERAETS, nicht der Zelle.

    Vor dieser Aenderung lief die Zaehlung in der Zellschleife von
    ``RgbMatrixInstance.write`` — bei 48 Zellen also 48-mal pro Frame fuer EIN
    Geraet. **Gemessen am echten ZQ06121: 6,20 ms je Frame vorher, 4,57 ms
    nachher** (48 Zellen, Style RGBW) — 26 % des gesamten `write()`, allein
    fuers wiederholte Zaehlen.

    Der Test haelt die Eigenschaft fest, nicht die Millisekunden: eine
    Zeitmessung im Gate waere eine Wanduhr-Grenze und damit die QA-71-Falle.
    """

    def test_einmal_je_fixture_und_frame(self):
        import src.core.app_state as AS
        from src.core.engine.rgb_matrix import RgbMatrixInstance, MatrixStyle
        chans = [_ch("intensity", 1)]
        nr = 2
        for _ in range(4):
            for a in ("color_r", "color_g", "color_b"):
                chans.append(_ch(a, nr)); nr += 1
        chans.append(_ch("color_w", nr))

        aufrufe = {"n": 0}
        echt = AS.attr_head_count_for_channels

        def gezaehlt(fixture, channels, attribute):
            aufrufe["n"] += 1
            return echt(fixture, channels, attribute)

        alt_get, AS.attr_head_count_for_channels = AS.get_channels_for_patched, gezaehlt
        AS.get_channels_for_patched = lambda f: chans
        self.addCleanup(lambda: (setattr(AS, "attr_head_count_for_channels", echt),
                                 setattr(AS, "get_channels_for_patched", alt_get)))

        class _U:
            def __init__(self): self.ch = {}
            def set_channel(self, a, v): self.ch[a] = v

        fx = SimpleNamespace(fid=1, universe=1, address=1, fixture_type="matrix")
        mx = RgbMatrixInstance(name="T")
        mx.style = MatrixStyle.RGBW
        mx.fixture_grid = [1] * 4
        mx.head_grid = list(range(4))
        mx.drive_intensity = False
        mx._running = True
        mx._render = lambda phase: [(255, 255, 255)] * 4
        mx.write({1: _U()}, [fx], 0.02)

        self.assertLessEqual(
            aufrufe["n"], 2,
            f"{aufrufe['n']} Zaehlungen fuer EIN Geraet in EINEM Frame — die "
            "Zahl gehoert je Fixture geholt, nicht je Zelle")


class ZelleGehoertZuTest(unittest.TestCase):
    """Die eine Zugehoerigkeits-Regel — Wahrheitstabelle."""

    def test_wahrheitstabelle(self):
        from src.core.group_cells import (zelle_gehoert_zu as G,
                                          ACHSE_FARBE as F, ACHSE_WEISS as W)
        faelle = [
            #  Zellwert   alles  rgb    weiss   Begruendung
            (5,           True,  True,  True,  "ganzes Geraet gehoert zu jeder Achse"),
            ("5",         True,  True,  True,  "als Text dasselbe"),
            ("5:0",       True,  True,  False, "Farb-Kopf ist kein Weiss-Segment"),
            ("5:2",       True,  True,  False, ""),
            ("5:w0",      True,  False, True,  "und umgekehrt"),
            ("5:w3",      True,  False, True,  ""),
            (7,           False, False, False, "fremdes Geraet"),
            ("7:w0",      False, False, False, ""),
            ("5:-1",      False, False, False, "negativer Index ist unparsbar (FM-45)"),
            ("quatsch",   False, False, False, ""),
            (None,        False, False, False, ""),
        ]
        for wert, alles, rgb, weiss, warum in faelle:
            with self.subTest(zelle=wert):
                self.assertEqual(G(wert, 5), alles, warum)
                self.assertEqual(G(wert, 5, F), rgb, warum)
                self.assertEqual(G(wert, 5, W), weiss, warum)


class RasterZweiAchsenTest(unittest.TestCase):
    """★★ Der Kern von Scheibe 2: RGB-Zonen und Weiss-Segmente liegen
    NEBENEINANDER im Raster, und jede Operation trifft genau das, was sie meint.
    """

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])

    def _raster(self):
        """Geraet 5 mit zwei RGB-Zonen und zwei Weiss-Segmenten, daneben ein
        fremdes Geraet 7."""
        from src.ui.views.fixture_group_view import FixtureGridWidget
        g = FixtureGridWidget()
        g.cols, g.rows = 4, 2
        g.positions = {(0, 0): "5:0", (1, 0): "5:1",
                       (2, 0): "5:w0", (3, 0): "5:w1", (0, 1): 7}
        return g

    def test_alle_zellen_entfernen_laesst_keine_waisen(self):
        """★ REGRESSION, vor dem Umbau GEMESSEN: der Menuepunkt „Alle Zellen von
        X entfernen" liess die Weiss-Zellen stehen — ``parse_group_cell`` ist
        bewusst verlustbehaftet und erkennt ``"5:w0"`` gar nicht als zu Geraet 5
        gehoerig. Uebrig blieben Zellen, die keine Operation mehr ansprechen
        konnte: das Geraet stand als Waise im Raster."""
        g = self._raster()
        g._drop_fid_cells(5)
        self.assertEqual(g.positions, {(0, 1): 7})

    def test_farb_wurf_laesst_die_weiss_segmente_leben(self):
        g = self._raster()
        g._drop_fid_cells(5, ACHSE_FARBE)
        self.assertEqual(g.positions,
                         {(2, 0): "5:w0", (3, 0): "5:w1", (0, 1): 7})

    def test_weiss_wurf_laesst_die_farb_zonen_leben(self):
        g = self._raster()
        g._drop_fid_cells(5, ACHSE_WEISS)
        self.assertEqual(g.positions,
                         {(0, 0): "5:0", (1, 0): "5:1", (0, 1): 7})

    def test_die_ganz_geraet_zelle_geht_mit_jeder_achse(self):
        """Sie meint das ganze Geraet — bliebe sie liegen, staende das Geraet
        doppelt im Raster: einmal ganz, einmal in Segmenten."""
        from src.ui.views.fixture_group_view import FixtureGridWidget
        for achse in (None, ACHSE_FARBE, ACHSE_WEISS):
            with self.subTest(achse=achse):
                g = FixtureGridWidget()
                g.cols, g.rows = 4, 2
                g.positions = {(0, 0): 5, (0, 1): 7}
                g._drop_fid_cells(5, achse)
                self.assertEqual(g.positions, {(0, 1): 7})

    def test_ganzes_geraet_droppen_raeumt_beide_achsen(self):
        g = self._raster()
        ziel = g.place_fixture(5, 0, 1)
        self.assertIsNotNone(ziel)
        self.assertEqual(g.positions[ziel], 5)
        self.assertEqual([v for v in g.positions.values() if str(v).startswith("5")],
                         [5], "das Geraet steht genau einmal im Raster")

    def test_koepfe_auslegen_raeumt_die_weiss_segmente_nicht(self):
        """Der eigentliche Zweck: zwei ansprechbare Saetze je Geraet."""
        g = self._raster()
        g.place_fixture_heads(5, 2, 0, 1)
        weiss = sorted(v for v in g.positions.values() if str(v).startswith("5:w"))
        self.assertEqual(weiss, ["5:w0", "5:w1"])

    def test_zusammenfalten_geht_auch_aus_reinem_weiss(self):
        """★ Ueber ``_split_cell`` waren Weiss-Segmente unsichtbar: ein Geraet,
        das NUR in Weiss-Segmenten im Raster stand, galt als „gar nicht
        kopfweise da" und liess sich nicht zusammenfalten."""
        from src.ui.views.fixture_group_view import FixtureGridWidget
        g = FixtureGridWidget()
        g.cols, g.rows = 4, 2
        g.positions = {(1, 0): "5:w0", (2, 0): "5:w1", (0, 1): 7}
        zelle = g.collapse_fixture_heads(5)
        self.assertEqual(zelle, (1, 0))
        self.assertEqual(g.positions, {(1, 0): 5, (0, 1): 7})

    def test_freiraum_ist_achsen_bewusst(self):
        """Highlight und echte Platzierung muessen deckungsgleich bleiben —
        beide fragen dieselbe Funktion."""
        g = self._raster()
        for zelle, achse, frei, was in (
                ((0, 0), ACHSE_FARBE, True,  "eigene Farb-Zone weicht dem Farb-Wurf"),
                ((0, 0), ACHSE_WEISS, False, "… blockiert aber den Weiss-Wurf"),
                ((2, 0), ACHSE_WEISS, True,  "eigenes Weiss-Segment weicht dem Weiss-Wurf"),
                ((2, 0), ACHSE_FARBE, False, "… blockiert aber den Farb-Wurf"),
                ((0, 1), ACHSE_FARBE, False, "fremdes Geraet blockiert immer"),
                ((0, 1), ACHSE_WEISS, False, ""),
        ):
            with self.subTest(zelle=zelle, achse=achse):
                self.assertIs(g._is_free(zelle, 5, achse), frei, was)


class BestandsdatenUnveraendertTest(unittest.TestCase):
    """★★ Die wichtigste Zusicherung des ganzen Umbaus: für Raster OHNE
    Weiss-Zellen — also fuer jede heute gespeicherte Show — antwortet die neue
    Regel Zeichen fuer Zeichen wie die alte.

    Gemessen ueber die echten Shows: 66 von 66 gelesen, 225 Raster, 1461
    Zellen (813 ganze Geraete, 116 Kopf-Zellen, Rest Nicht-Zellwerte) —
    **0** Abweichungen. Der Test haelt dieselbe Aussage an einem Korpus fest,
    der die dort vorgefundenen Zellformen nachbildet, weil die Shows selbst
    private Daten sind und nicht ins oeffentliche Repo gehoeren.
    """

    def test_ohne_weiss_zellen_antwortet_neu_wie_alt(self):
        from src.core.group_cells import parse_group_cell, zelle_gehoert_zu
        korpus = [1, 5, 12, "1", "07", "5:0", "5:1", "12:3", "1:11",
                  "5:-1", "", None, "quatsch", "x:1", [0, 1], {"a": 1}]
        for fid in (0, 1, 5, 7, 12):
            for wert in korpus:
                with self.subTest(fid=fid, zelle=wert):
                    self.assertEqual(zelle_gehoert_zu(wert, fid),
                                     parse_group_cell(wert)[0] == fid)


class WeissFormTest(unittest.TestCase):
    """★ Woher die Form der Weiss-Segmente kommt — an ECHTEN Profilen.

    Beide Konventionen standen schon im Baum und wurden hier gelesen, nicht
    erfunden: eine 0 heisst „aus der Kanalzahl fuellen" (CDX-52,
    ``_ZQ06121_WEISS = (1, 0)``), und gleich viele Weiss- wie Farbkoepfe heisst
    „dieselbe Geometrie" (das ist wortwoertlich die ENG-25-Regel).
    """

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])
        from _fixture_quelle import frische_library
        cls._eng = frische_library(cls)

    def _stellvertreter(self, kurz):
        """Ein Geraet aus der echten Bibliothek, an die echten Methoden gebunden."""
        import types
        from sqlalchemy import select
        from sqlalchemy.orm import Session, selectinload
        from src.core.database.models import FixtureProfile, FixtureMode
        import src.core.app_state as AS
        from src.ui.views.fixture_group_view import FixtureGroupView as V
        with Session(self._eng) as s:
            p = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels))
                .where(FixtureProfile.short_name == kurz)).scalars().first()
            m = max(p.modes, key=lambda m: m.channel_count)
            ch = [SimpleNamespace(attribute=c.attribute,
                                  channel_number=c.channel_number)
                  for c in sorted(m.channels, key=lambda c: c.channel_number)]
            weiss = (m.white_rows, m.white_cols)
            panel = (m.grid_rows, m.grid_cols)
        alt = (AS.get_channels_for_patched, AS.panel_grid_for, AS.white_grid_for)
        AS.get_channels_for_patched = lambda f: ch
        AS.panel_grid_for = lambda f, _g=panel: _g
        AS.white_grid_for = lambda f, _w=weiss: _w
        def zurueck():
            (AS.get_channels_for_patched, AS.panel_grid_for,
             AS.white_grid_for) = alt
        self.addCleanup(zurueck)
        v = SimpleNamespace(_ACHSEN_WORT=V._ACHSEN_WORT,
                            _weiss_form_ergaenzen=V._weiss_form_ergaenzen)
        for nm in ("_hinterlegte_form", "_achsen_zahl"):
            setattr(v, nm, types.MethodType(getattr(V, nm), v))
        return v, SimpleNamespace(fid=1, label=kurz)

    def _formen(self, kurz):
        v, fx = self._stellvertreter(kurz)
        nf = v._achsen_zahl(fx, ACHSE_FARBE)
        nw = v._achsen_zahl(fx, ACHSE_WEISS)
        return (nf, nw,
                v._hinterlegte_form(fx, nf, ACHSE_FARBE),
                v._hinterlegte_form(fx, nw, ACHSE_WEISS))

    def test_eine_null_heisst_aus_der_kanalzahl_fuellen(self):
        """ZQ06121: hinterlegt steht ``(1, 0)`` — „die Warmweiss-Leiste ist EINE
        Reihe, die Spaltenzahl steht als acht ``color_w``-Kanaele in diesem
        Modus". Wer auf ``spalten >= 1`` besteht, wirft eine hinterlegte Form
        weg und nennt sie „nicht vorhanden"."""
        nf, nw, farbe, weiss = self._formen("ZQ06121")
        self.assertEqual((nf, nw), (48, 8))
        self.assertEqual(farbe, (4, 12), "Farb-Form unveraendert")
        self.assertEqual(weiss, (1, 8), "1 Reihe, Breite aus den 8 Kanaelen")

    def test_gleich_viele_weiss_wie_farbkoepfe_heisst_dieselbe_geometrie(self):
        """Stairville Matrix Blinder 5x5 RGBWW: 25 Weiss-Kanaele,
        ``white_grid = (0, 0)`` — es gibt keine eigene LEISTE, die Weiss-LEDs
        sitzen IN den 25 Pixeln. Ihre Form ist also die des Panels."""
        nf, nw, farbe, weiss = self._formen("STAIRMB5X5")
        self.assertEqual((nf, nw), (25, 25))
        self.assertEqual(farbe, (5, 5))
        self.assertEqual(weiss, (5, 5))

    def test_ohne_hinterlegte_form_wird_nichts_geraten(self):
        """★ Die Gegenprobe. ``(0, 0)`` ohne passende Farbzahl heisst nach
        CDX-52 **nein** — dann bleibt „wie im Geraet hinterlegt" ausgegraut und
        der Mensch nimmt „als Zeile"/„als Spalte". Eine geratene Form sieht
        richtig aus und ist es nicht."""
        for kurz in ("PARBAR4", "MH16"):
            with self.subTest(geraet=kurz):
                _nf, _nw, farbe, weiss = self._formen(kurz)
                self.assertIsNone(farbe)
                self.assertIsNone(weiss)

    def test_ohne_weiss_kanaele_gibt_es_keine_weiss_achse(self):
        _nf, nw, _f, _w = self._formen("MH16")
        self.assertEqual(nw, 0, "0 heisst 0 — hier wird nicht auf 1 aufgerundet")


class ZweiFragenTest(unittest.TestCase):
    """★★ „Welche Geraete FAEHRT diese Gruppe" und „welche ERWAEHNT sie" sind
    zwei Fragen mit ENTGEGENGESETZTEN sicheren Richtungen. Bis FM-41 hat eine
    Funktion beide beantwortet — und fuer eine davon war die Fehlrichtung
    falsch.
    """

    def test_die_beiden_antworten_gehen_auseinander(self):
        from src.core.group_cells import (base_fids_in_grid_order as FAEHRT,
                                          referenzierte_fids as ERWAEHNT)
        nur_weiss = {"0,0": "1:w0", "1,0": "1:w1"}
        self.assertEqual(FAEHRT(nur_weiss), [],
                         "faehrt nichts, solange der Renderer Weiss nicht bedient")
        self.assertEqual(sorted(ERWAEHNT(nur_weiss.values())), [1],
                         "erwaehnt aber sehr wohl Geraet 1")

    def test_bestand_deckungsgleich_ohne_weiss_zellen(self):
        """Fuer alles, was es heute gibt, sagen beide dasselbe."""
        from src.core.group_cells import (base_fids_in_grid_order as FAEHRT,
                                          referenzierte_fids as ERWAEHNT)
        for pos in ({"0,0": 1, "1,0": 2},
                    {"0,0": "1:0", "1,0": "1:1", "2,0": 7},
                    {"0,0": "5:3"},
                    {}):
            with self.subTest(raster=pos):
                self.assertEqual(sorted(FAEHRT(pos)),
                                 sorted(ERWAEHNT(pos.values())))

    def test_nur_weiss_ist_keine_waise(self):
        """★ REGRESSION, gemessen: ein Geraet, das NUR ueber Weiss-Zellen in
        einer Gruppe steckt, kam durch ``patch_dedup.referenzen`` als Waise
        durch — und ``--anwenden`` haette es aus dem Patch ENTFERNT. Das ist
        wortgleich der Fehler, den STAB-22 fuer Kopf-Zellen behoben hat, nur
        eine Achse weiter."""
        from src.core.show import patch_dedup
        from src.core.group_cells import (base_fids_in_grid_order,
                                          referenzierte_fids)

        class _St:
            cue_stacks = []
            visualizer_positions = visualizer_rotations = live_view_positions = {}

            def __init__(self, pos):
                self._pos = pos

            def list_fixture_groups(self):
                return [{"id": 1, "name": "Weissleiste", "folder": "",
                         "fids": base_fids_in_grid_order(self._pos),
                         "ref_fids": sorted(referenzierte_fids(self._pos.values()))}]

            def get_patched_fixtures(self):
                return []

        for name, pos in (("nur Weiss-Zellen", {"0,0": "1:w0", "1,0": "1:w1"}),
                          ("Kopf-Zellen", {"0,0": "1:0"}),
                          ("ganzes Gerät", {"0,0": 1})):
            with self.subTest(raster=name):
                self.assertIn("geraetegruppen",
                              patch_dedup.referenzen(_St(pos), 1),
                              f"{name}: Gerät gilt als Waise")

    def test_alte_quelle_ohne_den_schluessel_faellt_auf_den_alten_stand(self):
        """Eine Attrappe, die ``ref_fids`` nicht kennt, verliert nichts —
        sie bekommt wieder genau das bisherige Verhalten, nie weniger."""
        from src.core.show import patch_dedup

        class _Alt:
            cue_stacks = []
            visualizer_positions = visualizer_rotations = live_view_positions = {}
            def list_fixture_groups(self):
                return [{"id": 1, "name": "G", "folder": "", "fids": [1]}]
            def get_patched_fixtures(self):
                return []

        self.assertIn("geraetegruppen", patch_dedup.referenzen(_Alt(), 1))


if __name__ == "__main__":
    unittest.main()
