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


if __name__ == "__main__":
    unittest.main()
