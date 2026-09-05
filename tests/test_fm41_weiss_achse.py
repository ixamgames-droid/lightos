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

    def test_gleich_viele_weiss_wie_farbkoepfe_heisst_GAR_KEINE_eigene_achse(self):
        """★★★ HIER LAG ICH ZUERST FALSCH — und die Korrektur ist lehrreicher
        als der Fehler.

        Meine erste Fassung schloss aus ``n_w == n_c``: „gleiche Anzahl, also
        gleiche Geometrie, also biete die Weiss-Achse als 5x5 an". Dieselbe
        Regel sagt in Wahrheit das **Gegenteil**: sitzt je ein Weiss-Emitter IM
        Pixel, dann gehoert er der FARBZELLE — es gibt gar nichts Zweites
        anzusprechen. Genau das ist die ENG-25-Aussage, ich hatte sie nur
        andersherum gelesen.

        Was daraus wurde, gemessen an einem 4-Kanal-RGBW-PAR: die Farbzelle
        schrieb ueber den RGBW-Split ``color_w = 0`` (rot), die daneben gelegte
        Weiss-Zelle ueberschrieb CH4 mit **255** — und gewann immer, weil die
        Weiss-Schleife baulich spaeter laeuft. Ueber die echte Bibliothek waren
        **1564 von 5125 Modi** so betroffen; eine eigene Achse haben **71**.

        ★ Die Lehre: eine Zahlengleichheit ist noch keine Aussage ueber
        ZUSTAENDIGKEIT. „Gleich viele" hiess hier nicht „passend anordnen",
        sondern „es ist dasselbe Ding".
        """
        nf, nw, farbe, weiss = self._formen("STAIRMB5X5")
        self.assertEqual(nf, 25, "25 Farbzonen")
        self.assertEqual(nw, 0,
                         "keine ansprechbare Weiss-Achse — das Weiss sitzt in "
                         "den Pixeln und gehoert der Farbzelle")
        self.assertEqual(farbe, (5, 5), "die Farb-Form bleibt unveraendert")
        self.assertIsNone(weiss, "und damit gibt es auch keine Weiss-Form")

    def test_die_achse_gibt_es_nur_wo_die_zahlen_auseinandergehen(self):
        """Die Regel an echten Profilen — dieselbe, die der Renderer seit
        ENG-25 fuehrt, hier fuer die Frage „darf man das ueberhaupt anbieten"."""
        from src.core.app_state import weiss_ist_eigene_achse_for_channels as EIGEN
        for kurz, erwartet, warum in (
                ("ZQ06121", True,  "8 Weiss zu 48 Zonen — eigene Leiste"),
                ("STAIRMB5X5", False, "25 zu 25 — Weiss sitzt im Pixel"),
                ("PARW", False, "1 zu 1 — gewoehnlicher RGBW-PAR"),
                ("PARBAR4", False, "4 zu 4"),
                ("MH16", False, "gar kein Weiss"),
        ):
            with self.subTest(geraet=kurz):
                v, _fx = self._stellvertreter(kurz)
                import src.core.app_state as AS
                self.assertIs(EIGEN(AS.get_channels_for_patched(None)), erwartet, warum)

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


class RendererWeissAchseTest(unittest.TestCase):
    """★★★ Der Renderer faehrt die Weiss-Achse — gemessen am ECHTEN Geraet.

    Die Abnahme dieser Scheibe stand vor dem Bauen fest: ein Vollweiss-Frame
    ueber eine Weiss-Gruppe **muss CH147-154 tragen**. Steht dort 0, ist eine
    der beiden gemessenen Sperren noch scharf (die Weiss-Zelle stirbt in
    ``fixture_grid``, oder der ENG-25-Torwaechter greift faelschlich).
    """

    @classmethod
    def setUpClass(cls):
        from _fixture_quelle import frische_library
        from sqlalchemy import select
        from sqlalchemy.orm import Session, selectinload
        from src.core.database.models import FixtureProfile, FixtureMode
        eng = frische_library(cls)
        with Session(eng) as s:
            p = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels))
                .where(FixtureProfile.short_name == "ZQ06121")).scalars().first()
            m = max(p.modes, key=lambda m: m.channel_count)
            cls.chans = [SimpleNamespace(attribute=c.attribute,
                                         channel_number=c.channel_number)
                         for c in sorted(m.channels, key=lambda c: c.channel_number)]
        cls.weiss_kanaele = [c.channel_number for c in cls.chans
                             if c.attribute == "color_w"]

    def setUp(self):
        import src.core.app_state as AS
        self._alt = AS.get_channels_for_patched
        AS.get_channels_for_patched = lambda f: self.chans
        self.addCleanup(lambda: setattr(AS, "get_channels_for_patched", self._alt))

    def _frame(self, positions, cols, rows, style=None, drive=False):
        """Ein Vollweiss-Frame ueber dieses Raster -> geschriebene Adressen."""
        from src.core.engine.rgb_matrix import (RgbMatrixInstance, MatrixStyle,
                                                grids_from_positions,
                                                weiss_grid_from_positions)
        fg, hg = grids_from_positions(positions, cols, rows)
        wg = weiss_grid_from_positions(positions, cols, rows)
        mx = RgbMatrixInstance(name="T")
        mx.cols, mx.rows = cols, rows
        mx.style = style or MatrixStyle.RGBW
        mx.fixture_grid, mx.head_grid, mx.weiss_grid = fg, hg, wg
        mx.drive_intensity = drive
        mx._running = True
        mx._render = lambda phase, n=cols * rows: [(255, 255, 255)] * n

        class _U:
            def __init__(self): self.ch = {}
            def set_channel(self, a, v): self.ch[a] = v

        u = _U()
        fx = SimpleNamespace(fid=1, universe=1, address=1, fixture_type="matrix")
        mx.write({1: u}, [fx], 0.02)
        return sorted(u.ch)

    def test_die_abnahme__vollweiss_traegt_ch147_bis_154(self):
        adressen = self._frame({f"{i},0": f"1:w{i}" for i in range(8)}, 8, 1)
        self.assertEqual(adressen, self.weiss_kanaele)
        self.assertEqual(adressen, list(range(147, 155)),
                         "die acht color_w-Kanaele des ZQ06121")

    def test_farb_und_weiss_zellen_stoeren_einander_nicht(self):
        """Gemischtes Raster: die Farbzonen schreiben ihre RGB-Kanaele, das
        Weiss-Segment seinen — und keiner den des anderen."""
        adressen = self._frame({"0,0": "1:0", "1,0": "1:1", "2,0": "1:w3"}, 3, 1)
        self.assertEqual(adressen, [3, 4, 5, 6, 7, 8, 150],
                         "Zone 1 (CH3-5), Zone 2 (CH6-8), Weiss-Segment 4 (CH150)")

    def test_kein_phantom_segment(self):
        """★ 20 Weiss-Zellen bei 8 Segmenten schreiben 8 Kanaele, nicht 20 —
        und ziehen vor allem NICHT den geteilten Master hoch (FM-45-Grenze)."""
        adressen = self._frame({f"{i},0": f"1:w{i}" for i in range(20)}, 20, 1)
        self.assertEqual(adressen, list(range(147, 155)))

    def test_dimmer_und_shutter_stil_fahren_die_weiss_achse_nicht(self):
        """★★ Ein Weiss-Segment hat keinen EIGENEN Dimmer und keinen eigenen
        Shutter. Wuerde die Achse dort fahren, schrieben alle acht Zellen auf
        DENSELBEN geteilten Kanal und ueberholten einander — letzter gewinnt,
        sichtbar als Flackern. Es gibt dort nichts Pro-Segment zu fahren."""
        from src.core.engine.rgb_matrix import MatrixStyle
        raster = {f"{i},0": f"1:w{i}" for i in range(8)}
        for stil in (MatrixStyle.DIMMER, MatrixStyle.SHUTTER):
            with self.subTest(stil=stil):
                self.assertEqual(self._frame(raster, 8, 1, style=stil), [])

    def test_rgb_stil_faehrt_die_weiss_achse_sehr_wohl(self):
        """★ Die RGB/RGBW-Unterscheidung betrifft die FARB-Zellen (ob deren
        `color_w` aus dem Split mitlaeuft) — mit einem eigenstaendigen
        Weiss-Segment hat sie nichts zu tun. Sonst waere hier der
        ENG-25-Torwaechter auf die falsche Frage angewandt."""
        from src.core.engine.rgb_matrix import MatrixStyle
        raster = {f"{i},0": f"1:w{i}" for i in range(8)}
        self.assertEqual(self._frame(raster, 8, 1, style=MatrixStyle.RGB),
                         list(range(147, 155)))


class WeissZelleBleibtEineLueckeTest(unittest.TestCase):
    """★★★ Das Regressionsnetz. Die Weiss-Zelle ist in ``fixture_grid``
    bewusst eine LUECKE, damit jeder Konsument ohne Achsenkenntnis **nichts**
    erzeugt statt etwas Falschem.

    Gemessen degradieren alle drei Alternativen falsch — deshalb nagelt dieser
    Test genau die Pfade fest, die es sonst still kaputt machen wuerden.
    """

    def _grids(self):
        from src.core.engine.rgb_matrix import (grids_from_positions,
                                                weiss_grid_from_positions)
        pos = {"0,0": "1:0", "1,0": "1:1", "2,0": "1:w3", "3,0": 7}
        return (*grids_from_positions(pos, 4, 1),
                weiss_grid_from_positions(pos, 4, 1))

    def test_fixture_grid_meldet_eine_luecke(self):
        from src.core.engine.rgb_matrix import is_gap
        fg, hg, wg = self._grids()
        self.assertEqual(fg, [1, 1, None, 7])
        self.assertEqual(hg, [0, 1, None, None])
        self.assertEqual(wg, [None, None, (1, 3), None])
        self.assertTrue(is_gap(fg, 2), "Zelle 2 muss fuer Nicht-Wissende leer sein")

    def test_die_achse_landet_NICHT_im_kopf_slot(self):
        """★★ Die Falle, in die ein spaeterer „kleiner Umbau" sonst tappt.

        Ein Achsen-String im Kopf-Slot laesst ``channels_for_head`` mit einem
        ``TypeError`` scheitern, den der FunctionManager schluckt — der Tick
        bricht dann MITTEN in der Zellschleife ab, und die gueltigen Zellen
        dahinter rendern nie, jedes Frame aufs Neue. Ein Kopf-INDEX waere
        genauso falsch, nur leiser: drei Konsumenten faerben dann RGB-Zone 4.
        """
        _fg, hg, _wg = self._grids()
        for eintrag in hg:
            with self.subTest(eintrag=eintrag):
                self.assertIsInstance(eintrag, (int, type(None)),
                                      "head_grid traegt Kopf-Indizes oder None")
        self.assertIsNone(hg[2], "die Weiss-Zelle hat KEINEN Kopf-Index")

    def test_show_vertrag__fehlender_schluessel_faellt_in_die_schmalere_richtung(self):
        """★ Bewusst anders herum als ``head_grid``: dort heisst ein fehlender
        Schluessel „ganzes Geraet" und erzeugt MEHR Ausgabe. Eine verlorene
        Weiss-Angabe darf zu „leuchtet nicht" degradieren, nie zu ungewolltem
        Licht — eine Rueckstufung auf ein aelteres LightOS ueberlebt der
        Schluessel gemessen nicht."""
        import json
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        m = RgbMatrixInstance(name="T")
        m.cols, m.rows = 4, 1
        m.weiss_grid = [None, None, (1, 3), None]
        d = m.to_dict()
        json.dumps(d)                       # muss serialisierbar bleiben
        zurueck = RgbMatrixInstance(name="X")
        zurueck.apply_dict(d)
        self.assertEqual(zurueck.weiss_grid, [None, None, (1, 3), None])

        ohne = dict(d)
        del ohne["weiss_grid"]
        alt = RgbMatrixInstance(name="Y")
        alt.apply_dict(ohne)
        self.assertEqual(alt.weiss_grid, [], "kein Schluessel = keine Weiss-Zelle")

    def test_die_schluessel_lesung_steht_nur_an_EINER_stelle(self):
        """Beide Ableitungen lesen ``\"col,row\"`` ueber denselben Helfer —
        nebeneinander kopiert waeren es acht Zeilen, die byte-genau synchron
        bleiben muessten."""
        import inspect
        from src.core.engine import rgb_matrix as RM
        for fn in (RM.grids_from_positions, RM.weiss_grid_from_positions):
            with self.subTest(funktion=fn.__name__):
                quelle = inspect.getsource(fn)
                self.assertIn("_zellen_indizes", quelle)
                self.assertNotIn('.split(",")', quelle,
                                 "zweite Schluessel-Lesung — s. Checkliste 17")


class GegenpruefungFundeTest(unittest.TestCase):
    """★★★ Drei Funde einer adversarischen Gegenpruefung, alle selbst
    nachgemessen und behoben. Sie stehen hier zusammen, weil sie EINE Ursache
    haben: die Weiss-Achse wurde angeboten, wo es sie gar nicht gibt.
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

    def _frame(self, chans, positions, cols, rows, farbe=(255, 255, 255),
               drive=False, inten=1.0, mit_weiss=True):
        import src.core.app_state as AS
        from src.core.engine.rgb_matrix import (RgbMatrixInstance, MatrixStyle,
                                                grids_from_positions,
                                                weiss_grid_from_positions)
        alt = AS.get_channels_for_patched
        AS.get_channels_for_patched = lambda f: chans
        self.addCleanup(lambda: setattr(AS, "get_channels_for_patched", alt))
        fg, hg = grids_from_positions(positions, cols, rows)
        mx = RgbMatrixInstance(name="T")
        mx.cols, mx.rows = cols, rows
        mx.style = MatrixStyle.RGBW
        mx.fixture_grid, mx.head_grid = fg, hg
        mx.weiss_grid = (weiss_grid_from_positions(positions, cols, rows)
                         if mit_weiss else [])
        mx.drive_intensity = drive
        mx.intensity = inten
        mx._running = True
        mx._render = lambda p, n=cols * rows: [farbe] * n

        class _U:
            def __init__(self): self.ch = {}
            def set_channel(self, a, v): self.ch[a] = v

        u = _U()
        fx = SimpleNamespace(fid=1, universe=1, address=1, fixture_type="matrix")
        mx.write({1: u}, [fx], 0.02)
        return u.ch

    # ── Fund 1 ──────────────────────────────────────────────────────────────
    def test_eine_weiss_zelle_ueberschreibt_NIE_einen_farbkanal(self):
        """★★ Der Fund: bei einem Geraet, dessen Weiss zur Farbzelle gehoert,
        adressieren Farb- und Weiss-Zelle DENSELBEN Kanal. Gemessen schrieb die
        Farbzelle ueber den RGBW-Split ``color_w = 0`` (rot) und die
        Weiss-Zelle ueberschrieb ihn mit 255 — und gewann IMMER, weil die
        Weiss-Schleife baulich spaeter laeuft; der Vorrang liesse sich nicht
        einmal umdrehen.

        Die Zusicherung ist deshalb hart: die Weiss-Achse darf Kanaele
        HINZUFUEGEN, aber niemals einen Wert aendern, den die Farbschleife
        bereits geschrieben hat."""
        for kurz in ("PARW", "PARBAR4", "STAIRMB5X5", "ZQ06121"):
            for farbe in ((255, 0, 0), (0, 128, 255), (255, 255, 255)):
                with self.subTest(geraet=kurz, farbe=farbe):
                    chans = self._chans(kurz)
                    n_w = sum(1 for c in chans if c.attribute == "color_w")
                    raster = {"0,0": 1}
                    raster.update({("%d,0" % (i + 1)): ("1:w%d" % i)
                                   for i in range(min(n_w, 4))})
                    breite = len(raster)
                    ohne = self._frame(chans, raster, breite, 1, farbe,
                                       mit_weiss=False)
                    mit = self._frame(chans, raster, breite, 1, farbe,
                                      mit_weiss=True)
                    geaendert = {k: (ohne[k], mit[k]) for k in ohne
                                 if k in mit and ohne[k] != mit[k]}
                    self.assertEqual(geaendert, {},
                                     "die Weiss-Achse hat bestehende Werte "
                                     "ueberschrieben")

    # ── Fund 2 ──────────────────────────────────────────────────────────────
    def test_weiss_wird_genauso_gedimmt_wie_die_farbzonen(self):
        """★★ Der Fund: die Farbschleife hat einen Vorbehalt (``scale_colors``),
        weil bei ``drive_intensity=True`` der Merge bereits ueber den
        Dimmer-Kanal skaliert. Die Weiss-Schleife hatte ihn nicht und
        multiplizierte unbedingt — also QUADRATISCH. Gemessen stand bei Master
        0,5 die Farbzone auf 255 und das Weiss-Segment schon auf 127, bevor der
        Merge nochmal halbierte.

        Der Test vergleicht die beiden Achsen im SELBEN Frame gegeneinander,
        statt absolute Werte festzunageln — die Aussage ist „gleich behandelt",
        nicht „dieser Zahlenwert"."""
        chans = self._chans("ZQ06121")
        raster = {"0,0": "1:0", "1,0": "1:w0"}
        for drive in (True, False):
            for inten in (1.0, 0.75, 0.5, 0.25):
                with self.subTest(drive_intensity=drive, master=inten):
                    d = self._frame(chans, raster, 2, 1, (255, 255, 255),
                                    drive=drive, inten=inten)
                    self.assertEqual(
                        d.get(147), d.get(3),
                        "Weiss-Segment (CH147) und Farbzone (CH3) muessen im "
                        "selben Frame gleich behandelt werden")

    # ── Fund 3 ──────────────────────────────────────────────────────────────
    class _Egal:
        """Schluckt jeden Anzeige-Nachzug: aufrufbar UND attributierbar."""
        def __call__(self, *_a, **_k):
            return self
        def __getattr__(self, _n):
            return self

    def test_ein_neues_raster_raeumt_die_weiss_achse_mit(self):
        """★★★ Der schwerste der drei: beim Umhaengen einer Matrix auf andere
        Geraete wurden ``fixture_grid`` und ``head_grid`` zurueckgesetzt,
        ``weiss_grid`` aber nicht. Gemessen fuhr die Matrix danach weiter die
        Weiss-Segmente eines Geraets, das in ``fixture_grid`` gar nicht mehr
        vorkam — und der Zustand ueberlebte Speichern und Laden.

        Genau die Richtung, die der ``to_dict``-Docstring ausschliessen will:
        eine verlorene Weiss-Angabe darf zu „leuchtet nicht" degradieren, nie zu
        ungewolltem Licht."""
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        inst = RgbMatrixInstance(name="T")
        inst.weiss_grid = [None, (5, 3), (5, 7), None]

        class _View:
            """Stellvertreter fuer die Raster-Politik.

            Die Anzeige-Nachzuege der Methode (Spinboxen, Beschriftung,
            Vorschau-Naht, Dirty-Marker) sind hier ohne Belang — sie bekommen
            deshalb pauschal einen Leerlauf. Das macht den Test NICHT blind:
            die Zusicherung haengt an ``inst.weiss_grid``, und wuerde die
            Methode das Feld nicht mehr anfassen, faellt sie trotzdem."""
            _current = inst
            _saved = None

            def __getattr__(self, name):
                return GegenpruefungFundeTest._Egal()

        from src.ui.views.rgb_matrix_view import RgbMatrixView
        v = _View()
        v.__dict__.clear()          # nur die Klassen-Attribute zaehlen
        RgbMatrixView._apply_panel_grid(v, 2, 1, [6, None], [0, None], "x")
        self.assertEqual(inst.weiss_grid, [],
                         "ein neues Raster ersetzt ALLE Achsen")


class WeissMatrixSteuertEinGeraetTest(unittest.TestCase):
    """★★ Eine Matrix, die nur Weiss-Segmente faehrt, meldete „steuert kein
    Geraet" — und damit fielen zwei Dinge aus.

    * **Solo / „Effekte auf denselben Geraeten stoppen"** liess Farb- und
      Weiss-Matrix desselben Geraets nebeneinander laufen.
    * **``patch_dedup``** (`:184` fragt genau hier) hielt ein nur ueber
      Weiss-Zellen gefahrenes Geraet fuer eine **Waise** — dieselbe
      Datenverlust-Klasse wie STAB-22, nur ueber Funktionen statt Gruppen.

    ★ Hier fallen „was FAEHRT das" und „was wird ERWAEHNT" ausnahmsweise
    zusammen, denn der Renderer faehrt die Weiss-Achse seit FM-41 wirklich.
    Eine Trennung wie bei ``base_fids_in_grid_order`` waere hier **erfunden**,
    nicht gefunden — und das ist der Grund, warum es hier EINE Antwort gibt und
    dort zwei.
    """

    def _fm_mit(self, *funktionen):
        from src.core.engine.function_manager import get_function_manager
        fm = get_function_manager()
        for f in funktionen:
            for name in ("add", "add_function", "register"):
                if hasattr(fm, name):
                    try:
                        getattr(fm, name)(f)
                        break
                    except Exception:
                        continue
        return fm

    def _matrix(self, name, fixture_grid, weiss_grid):
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        m = RgbMatrixInstance(name=name)
        m.cols, m.rows = len(fixture_grid), 1
        m.fixture_grid = list(fixture_grid)
        m.weiss_grid = list(weiss_grid)
        return m

    def test_nur_weiss_steuert_sehr_wohl_ein_geraet(self):
        w = self._matrix("NurWeiss", [None] * 4,
                         [(5, 0), (5, 1), (5, 2), (5, 3)])
        fm = self._fm_mit(w)
        self.assertEqual(sorted(fm.affected_fids(w.id)), [5])

    def test_gemischt_nennt_beide_geraete(self):
        g = self._matrix("Gemischt", [7, None, None], [None, (5, 0), None])
        fm = self._fm_mit(g)
        self.assertEqual(sorted(fm.affected_fids(g.id)), [5, 7])

    def test_missgeformte_eintraege_tragen_NICHTS_bei(self):
        """★ Streng auf die vereinbarte Form ``(fid, index)``: ein Text wie
        ``"5abc"`` wuerde ueber ``sub[0]`` sonst als Geraet 5 durchgehen — ein
        erfundenes Geraet ist schlimmer als ein fehlendes."""
        k = self._matrix("Kaputt", [None] * 3, ["5abc", None, (9,)])
        fm = self._fm_mit(k)
        self.assertEqual(sorted(fm.affected_fids(k.id)), [])

    def test_write_reisst_bei_missgeformten_eintraegen_nicht_ab(self):
        """★★ Wichtiger als es aussieht: ein ValueError beim Entpacken kaeme
        aus ``write()`` heraus, und der FunctionManager SCHLUCKT ihn — der Tick
        braeche mitten in der Schleife ab und die gueltigen Zellen dahinter
        blieben JEDES Frame dunkel. Genau die Falle, wegen der die Achse nicht
        in den Kopf-Slot durfte."""
        import src.core.app_state as AS
        from src.core.engine.rgb_matrix import MatrixStyle
        alt = AS.get_channels_for_patched
        AS.get_channels_for_patched = lambda f: [
            SimpleNamespace(attribute="color_w", channel_number=1),
            SimpleNamespace(attribute="color_r", channel_number=2),
            SimpleNamespace(attribute="color_r", channel_number=3)]
        self.addCleanup(lambda: setattr(AS, "get_channels_for_patched", alt))

        class _U:
            def __init__(self): self.ch = {}
            def set_channel(self, a, v): self.ch[a] = v

        m = self._matrix("Kaputt", [None] * 3, ["quatsch", None, (9,)])
        m.style = MatrixStyle.RGBW
        m._running = True
        m._render = lambda p: [(255, 255, 255)] * 3
        u = _U()
        m.write({1: u}, [SimpleNamespace(fid=9, universe=1, address=1,
                                         fixture_type="matrix")], 0.02)
        self.assertEqual(u.ch, {}, "nichts geschrieben, aber auch nicht geworfen")


if __name__ == "__main__":
    unittest.main()
