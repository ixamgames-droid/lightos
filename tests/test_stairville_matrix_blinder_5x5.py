"""Stairville Matrix Blinder 5x5 RGBWW (``STAIRMB5X5``, Thomann Art. 494410).

25 × RGBWW-LED zu 10 W in einem 5×5-Raster. Modi 4 / 9 / 100 Kanaele.
Quelle: Hersteller-Manual „Matrix Blinder 5x5 RGBWW", Abschn. 7.4 / 7.5 / 7.6
(Charts) und 8 (Technische Daten). **Ein QLC+-Gegenstueck gibt es nicht** — die
Baender stammen aus genau EINER Quelle und sind nicht gegengeprueft. Genau
deshalb pruefen die Tests hier die STRUKTUR der Baender mit (Luecken/
Ueberlappungen), statt sich auf einen Abgleich zu verlassen, den es nicht gibt.

Festgenagelt werden die Stellen, an denen ein Panel-Chart teuer wird:

1. **Pixel-Reihenfolge ist pro Pixel R,G,B,W** — nicht blockweise (erst alle
   Rot, dann alle Gruen). Faellt das um, zeigt das 3D-Panel Farbstreifen statt
   Pixeln, und am echten Geraet leuchtet die falsche Lampe.
2. **attr#N-Falle** (ENG-03/07/09): im 9-Kanal-Modus darf sich KEIN Attribut
   wiederholen. Die drei Effekt-Kanaele tragen darum `macro`/`effect`/`raw` —
   dreimal `macro` haette der Programmer zu EINEM Regler dedupliziert.
3. **Strobe ist NICHT `_SIMPLE_STROBE`.** Dieses Geraet schaltet erst ab 11 um
   (0…10 ohne Funktion), nicht ab 1. Der bequeme Griff zur geteilten Konstante
   waere hier falsch gewesen.
4. **Rasterform 5×5** und KEINE eigene Weiss-Leiste: das Weiss sitzt auf
   denselben 25 Pixeln wie RGB, anders als beim ZQ06121 (CDX-52).
5. **nHeads** reist durch den ECHTEN ``_fixture_to_dict``-Pfad.
6. **Das Geraet hat keinen Master-Dimmer** — in keinem Modus. Der Test haelt das
   fest, damit niemand ihn „nachtraegt", weil er ihn vermisst.
"""
import os
import unittest
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from _fixture_quelle import frische_library     # FIXTEST-FRESH

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

KURZ = "STAIRMB5X5"
M4 = "4-Kanal Panel gesamt"
M9 = "9-Kanal Panel gesamt + Effekte"
M100 = "100-Kanal 25 Pixel RGBW"


def _load(session, short=KURZ):
    from src.core.database.models import (
        FixtureChannel, FixtureMode, FixtureProfile,
    )
    return session.execute(
        select(FixtureProfile)
        .options(
            selectinload(FixtureProfile.manufacturer),
            selectinload(FixtureProfile.modes)
            .selectinload(FixtureMode.channels)
            .selectinload(FixtureChannel.ranges),
        )
        .where(FixtureProfile.short_name == short)
    ).scalars().first()


def _mode(profile, name):
    return next(m for m in profile.modes if m.name == name)


def _chans(mode):
    return sorted(mode.channels, key=lambda c: c.channel_number)


def _attrs(mode):
    return [c.attribute for c in _chans(mode)]


def _ranges(mode, channel_number):
    ch = _chans(mode)[channel_number - 1]
    return sorted(ch.ranges, key=lambda r: r.range_from)


class _SeededCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._eng = frische_library(cls)


class ProfilVorhandenTest(_SeededCase):

    def test_profil_ist_in_der_frischen_bibliothek(self):
        """★ Der Test, der beim ZQ06121 gefehlt hat: ein Builtin muss in `_seed`
        UND im Backfill von `ensure_builtins` stehen. `frische_library` seedet
        ueber `_seed` — fehlt es dort, faellt genau dieser Test um."""
        with Session(self._eng) as s:
            p = _load(s)
            self.assertIsNotNone(p, "STAIRMB5X5 fehlt in der frisch geseedeten Bibliothek")
            self.assertEqual(p.manufacturer.name, "Stairville")
            self.assertEqual(p.name, "Matrix Blinder 5x5 RGBWW")
            self.assertEqual(p.fixture_type, "matrix")
            self.assertEqual(p.power_w, 115)   # Manual Abschn. 8, nicht 25*10 W

    def test_die_drei_modi_des_manuals(self):
        with Session(self._eng) as s:
            p = _load(s)
            self.assertEqual(
                sorted((m.name, m.channel_count) for m in p.modes),
                sorted([(M4, 4), (M9, 9), (M100, 100)]))


class KanalbelegungTest(_SeededCase):

    def test_4_kanal_ist_rgbw_ohne_alles(self):
        with Session(self._eng) as s:
            self.assertEqual(_attrs(_mode(_load(s), M4)),
                             ["color_r", "color_g", "color_b", "color_w"])

    def test_9_kanal_reihenfolge_laut_manual(self):
        with Session(self._eng) as s:
            self.assertEqual(_attrs(_mode(_load(s), M9)), [
                "color_r", "color_g", "color_b", "color_w",
                "shutter", "macro", "effect", "effect_speed", "raw",
            ])

    def test_kein_attribut_wiederholt_sich_im_9_kanal_modus(self):
        """attr#N-Falle (ENG-03/07/09): ein wiederholtes Attribut wird als Kopf
        gelesen. Drei Effekt-Kanaele mit dreimal `macro` haetten im Programmer
        EINEN Regler ergeben — und zwei stumme Kanaele am Geraet."""
        with Session(self._eng) as s:
            attrs = _attrs(_mode(_load(s), M9))
            self.assertEqual(len(attrs), len(set(attrs)))

    def test_kein_modus_hat_einen_master_dimmer(self):
        """Geraetetreu, kein Versehen: das Manual kennt in 4/9/100 keinen
        Dimmer-Kanal. Helligkeit kommt aus den Farbwerten. Wer hier einen
        `intensity` nachtraegt, erfindet einen Kanal, den das Geraet nicht hat."""
        with Session(self._eng) as s:
            p = _load(s)
            for name in (M4, M9, M100):
                with self.subTest(modus=name):
                    self.assertEqual(
                        {"intensity", "dimmer", "master"} & set(_attrs(_mode(p, name))),
                        set())


class KeinModus102Test(_SeededCase):
    """Der Thomann-Beschreibungstext nennt „four, nine, 100 or 102 channels".

    Nachgesehen statt geglaubt: die Spezifikationstabelle DERSELBEN Seite sagt
    „DMX-512 (4/9/100)", in beiden Manual-Revisionen (fr v3, de v4) kommt „102"
    kein einziges Mal vor, das Geraetemenue bietet drei Modi an, und die Tabelle
    der hoechsten DMX-Adresse (509/504/413) kennt ebenfalls nur drei. Der Test
    haelt die Entscheidung fest, damit niemand den Modus aus dem Shop-Text
    nachtraegt — geraten waere er in jedem Fall.
    """

    def test_es_gibt_genau_drei_modi_und_keiner_hat_102_kanaele(self):
        with Session(self._eng) as s:
            zahlen = sorted(m.channel_count for m in _load(s).modes)
        self.assertEqual(zahlen, [4, 9, 100])
        self.assertNotIn(102, zahlen)


class PixelReihenfolgeTest(_SeededCase):
    """Der teuerste denkbare Fehler: blockweise statt pro Pixel."""

    def test_100_kanal_ist_pro_pixel_rgbw(self):
        with Session(self._eng) as s:
            attrs = _attrs(_mode(_load(s), M100))
        self.assertEqual(attrs, ["color_r", "color_g", "color_b", "color_w"] * 25)

    def test_pixelnamen_zaehlen_1_bis_25(self):
        """Manual Abschn. 7.6 nummeriert die LEDs 1-25, zeilenweise von links
        oben. Die Kanalnamen folgen dieser Zaehlung."""
        with Session(self._eng) as s:
            chs = _chans(_mode(_load(s), M100))
        self.assertEqual([c.name for c in chs[:4]],
                         ["P1 Rot", "P1 Grün", "P1 Blau", "P1 Weiß"])
        self.assertEqual([c.name for c in chs[4:8]],
                         ["P2 Rot", "P2 Grün", "P2 Blau", "P2 Weiß"])
        self.assertEqual([c.name for c in chs[96:100]],
                         ["P25 Rot", "P25 Grün", "P25 Blau", "P25 Weiß"])

    def test_rasterform_5x5_ohne_eigene_weissleiste(self):
        """5×5 steht im Manual als BILD (Abschn. 7.6) — beim Pixel Panel 144
        musste sie nachgetragen werden, hier ist sie belegt. Die Weiss-LEDs
        sitzen auf DENSELBEN Pixeln wie RGB, also keine eigene Leiste (CDX-52):
        ``white_rows/cols`` bleiben 0."""
        with Session(self._eng) as s:
            m = _mode(_load(s), M100)
            self.assertEqual((m.grid_rows, m.grid_cols), (5, 5))
            self.assertEqual((m.white_rows, m.white_cols), (0, 0))


class BaenderTest(_SeededCase):
    """Die Baender sind generiert. Diese Tests pruefen das Ergebnis gegen das
    Manual — und die Struktur gegen Off-by-one im Generator."""

    def _lueckenlos(self, ranges, wo):
        self.assertEqual(ranges[0].range_from, 0, f"{wo}: faengt nicht bei 0 an")
        self.assertEqual(ranges[-1].range_to, 255, f"{wo}: endet nicht bei 255")
        for a, b in zip(ranges, ranges[1:]):
            self.assertEqual(
                b.range_from, a.range_to + 1,
                f"{wo}: Luecke oder Ueberlappung zwischen "
                f"{a.range_from}-{a.range_to} und {b.range_from}-{b.range_to}")

    def test_strobe_schaltet_erst_ab_11(self):
        """NICHT `_SIMPLE_STROBE` (0 aus / 1-255 Strobe): dieses Geraet hat laut
        Manual ein totes Band 0…10. Wer die geteilte Konstante nimmt, macht aus
        dem DMX-Wert 5 einen Blitz, den das Geraet gar nicht kennt."""
        with Session(self._eng) as s:
            rr = _ranges(_mode(_load(s), M9), 5)
        self.assertEqual([(r.range_from, r.range_to, r.kind) for r in rr],
                         [(0, 10, "open"), (11, 255, "strobe")])

    def test_zeichenkanal_ziffern_und_buchstaben(self):
        with Session(self._eng) as s:
            rr = _ranges(_mode(_load(s), M9), 6)
        self.assertEqual(len(rr), 1 + 10 + 26)
        nach_name = {r.name: (r.range_from, r.range_to) for r in rr}
        self.assertEqual(nach_name["Ohne Funktion"], (0, 15))
        self.assertEqual(nach_name["Ziffer 0"], (16, 21))
        self.assertEqual(nach_name["Ziffer 9"], (70, 75))
        self.assertEqual(nach_name["Buchstabe A"], (76, 81))
        self.assertEqual(nach_name["Buchstabe J"], (130, 135))
        # Letztes Band ist laut Chart breiter als das 6er-Raster.
        self.assertEqual(nach_name["Buchstabe Z"], (226, 255))
        self._lueckenlos(rr, "Zeichenkanal")

    def test_showkanal_sechs_programme(self):
        with Session(self._eng) as s:
            rr = _ranges(_mode(_load(s), M9), 7)
        self.assertEqual(len(rr), 1 + 6)
        nach_name = {r.name: (r.range_from, r.range_to) for r in rr}
        self.assertEqual(nach_name["Show-Programm 1"], (16, 55))
        self.assertEqual(nach_name["Show-Programm 6"], (216, 255))
        self._lueckenlos(rr, "Showkanal")

    def test_showspeed_hat_ein_band_mit_der_bedingung(self):
        """Kanal 8 stand zunaechst ganz ohne Band da — gefunden beim
        maschinellen Abgleich gegen das Manual (73 Baender hier, 74 dort). Das
        Band traegt die Bedingung, die sonst nirgends steht: der Regler tut
        nichts, solange Kanal 7 unter 16 bleibt."""
        with Session(self._eng) as s:
            rr = _ranges(_mode(_load(s), M9), 8)
        self.assertEqual(len(rr), 1)
        self.assertEqual((rr[0].range_from, rr[0].range_to), (0, 255))
        self.assertIn("Kanal 7", rr[0].name)

    def test_soundkanal_26_modi(self):
        with Session(self._eng) as s:
            rr = _ranges(_mode(_load(s), M9), 9)
        self.assertEqual(len(rr), 1 + 26)
        nach_name = {r.name: (r.range_from, r.range_to) for r in rr}
        self.assertEqual(nach_name["Sound-Modus 1"], (16, 24))
        self.assertEqual(nach_name["Sound-Modus 26"], (241, 255))
        self._lueckenlos(rr, "Soundkanal")
        # `sound` wird aus dem Namen abgeleitet — der Test haelt fest, dass die
        # Ableitung hier wirklich greift (sonst faende ein Sound-Filter nichts).
        self.assertTrue(all(r.kind == "sound" for r in rr if r.name != "Ohne Funktion"))


class RoutingTest(_SeededCase):
    """Kommt nHeads nicht durch den ECHTEN Pfad, baut `buildMatrixPanel` stumm
    ein 4x4 und neun der 25 Pixel fallen weg."""

    def _dict_for(self, mode_name):
        import types
        import src.core.app_state as AS
        import src.ui.visualizer.visualizer_window as VW
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        with Session(self._eng) as s:
            chans = [SimpleNamespace(attribute=c.attribute)
                     for c in _chans(_mode(_load(s), mode_name))]
        fake_state = SimpleNamespace(visualizer_positions={}, visualizer_rotations={},
                                     visualizer_docks={})
        fake_self = SimpleNamespace(_state=fake_state)
        fake_self._viz_model_for = types.MethodType(
            VisualizerBridge._viz_model_for, fake_self)
        fake_f = SimpleNamespace(fid=1, label="P", fixture_type="matrix")
        saved_as, saved_vw = AS.get_channels_for_patched, VW.get_channels_for_patched
        AS.get_channels_for_patched = lambda f: chans
        VW.get_channels_for_patched = lambda f: chans
        try:
            return VisualizerBridge._fixture_to_dict(fake_self, fake_f)
        finally:
            AS.get_channels_for_patched = saved_as
            VW.get_channels_for_patched = saved_vw

    def test_100_kanal_traegt_25_pixel(self):
        d = self._dict_for(M100)
        self.assertEqual(d["model"], "matrix")
        self.assertEqual(d["nHeads"], 25)

    def test_schmale_modi_sind_ein_feld(self):
        """4- und 9-Kanal faerben das GANZE Panel — eine Bank, ein Feld.
        Geraetetreu, kein Routing-Fehler."""
        self.assertEqual(self._dict_for(M4)["nHeads"], 1)
        self.assertEqual(self._dict_for(M9)["nHeads"], 1)


class HelferRegressionTest(unittest.TestCase):
    """`_pixel_rgb_channels` hat fuer dieses Geraet einen optionalen Weiss-Kanal
    bekommen. Der Default darf die Bestandspanels (Dotz, PP144) nicht anfassen."""

    def test_ohne_weiss_unveraendert(self):
        from src.core.database.fixture_db import _pixel_rgb_channels
        ohne = _pixel_rgb_channels(3)
        self.assertEqual([c[1] for c in ohne],
                         ["color_r", "color_g", "color_b"] * 3)
        self.assertEqual(ohne[0], ("P1 Rot", "color_r", 0, 255))

    def test_mit_weiss_haengt_je_pixel_einen_kanal_an(self):
        from src.core.database.fixture_db import _pixel_rgb_channels
        mit = _pixel_rgb_channels(3, white=True)
        self.assertEqual([c[1] for c in mit],
                         ["color_r", "color_g", "color_b", "color_w"] * 3)
        self.assertEqual(mit[3], ("P1 Weiß", "color_w", 0, 255))


if __name__ == "__main__":
    unittest.main()
