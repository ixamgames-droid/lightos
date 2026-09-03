"""ENG-25 — ein RGBW-Matrixeffekt darf kein Licht wegwerfen.

`MatrixStyle.RGBW` zieht den Weissanteil aus R/G/B heraus und legt ihn auf den
W-Kanal (`rgbw_split`) — richtig, solange das Weiss zu DIESER Zelle gehoert.
Beim ZQ06121 gehoert es das nicht: 48 RGB-Zonen, aber nur **8** eigene
Warmweiss-Segmente, die physisch mittig zwischen Reihe 2 und 3 sitzen und je
anderthalb Spalten abdecken.

**Gemessen am Vollweiss-Frame (vor dem Fix):** der Split lief fuer alle 48
Zellen, aufnehmen konnten den Weissanteil aber nur die Koepfe 0-7 —
**144 von 144 Farbkanaelen standen auf 0**, es leuchteten allein die acht
Mittelsegmente. Ein weisser Chase zeigte statt des Balkens einen Streifen.

Die Regel dagegen ist nicht neu: `matrix_pattern.cell_channel_values` bedient
`color_w` ausdruecklich NICHT und begruendet das mit Robins Entscheidung vom
2026-08-05 („Weiss soll bei Farbeffekten nicht mitlaufen"). Zwei Pfade, dieselbe
Frage, zwei Antworten — hier zieht der Matrix-Pfad nach.

★ Massstab ist die **Ausrichtung**, nicht der Geraetename: deckt sich die Zahl
der Weiss-Emitter mit der Zahl der Farbkoepfe, gehoert das Weiss zum Pixel und
der Split bleibt exakt wie bisher. Deshalb pruefen die Tests unten beide Seiten
an ECHTEN Profilen (ZQ06121 = eigene Leiste, Stairville-Blinder = 25 zu 25) und
zusaetzlich an einem synthetischen Geraet, damit die Regel nicht an zwei
Bibliothekseintraegen haengt.
"""
import os
import unittest
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from _fixture_quelle import frische_library     # FIXTEST-FRESH

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _Universe:
    """Merkt sich, WELCHE Kanaele geschrieben wurden — nicht nur die Werte.

    „auf 0 geschrieben" und „gar nicht angefasst" sind hier zwei verschiedene
    Aussagen: ein Farbeffekt soll die fremde Weiss-Leiste NICHT anfassen, damit
    ein Dimmer-Effekt darunter sie weiter fahren kann. Ein Test, der nur Werte
    liest, koennte beides nicht unterscheiden.
    """

    def __init__(self):
        self.ch: dict[int, int] = {}

    def set_channel(self, adr, wert):
        self.ch[int(adr)] = int(wert)


def _kanaele(engine, kurz: str):
    from src.core.database.models import FixtureProfile, FixtureMode
    with Session(engine) as s:
        p = s.execute(
            select(FixtureProfile)
            .options(selectinload(FixtureProfile.modes)
                     .selectinload(FixtureMode.channels))
            .where(FixtureProfile.short_name == kurz)).scalars().first()
        assert p is not None, f"Profil {kurz} fehlt in der frischen Bibliothek"
        m = max(p.modes, key=lambda m: m.channel_count)
        return m.name, [SimpleNamespace(attribute=c.attribute,
                                        channel_number=c.channel_number)
                        for c in sorted(m.channels, key=lambda c: c.channel_number)]


def _ch(attr: str, nr: int):
    return SimpleNamespace(attribute=attr, channel_number=nr)


class _Basis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._eng = frische_library(cls)

    def _frame(self, chans, zellen, *, style, farbe=(255, 255, 255),
               head_grid=True):
        """Einen Frame ueber ``zellen`` Zellen schreiben und das Universe liefern."""
        import src.core.app_state as AS
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        alt = AS.get_channels_for_patched
        AS.get_channels_for_patched = lambda f: chans
        self.addCleanup(lambda: setattr(AS, "get_channels_for_patched", alt))
        fx = SimpleNamespace(fid=1, universe=1, address=1, fixture_type="matrix")
        mx = RgbMatrixInstance(name="T")
        mx.style = style
        mx.fixture_grid = [1] * zellen
        mx.head_grid = list(range(zellen)) if head_grid else []
        mx.drive_intensity = False
        mx._running = True
        mx._render = lambda phase: [farbe] * zellen
        u = _Universe()
        mx.write({1: u}, [fx], 0.02)
        return u

    def _adressen(self, chans, *attrs):
        return [c.channel_number for c in chans
                if (c.attribute or "").lower() in attrs]


class EigeneWeissLeisteTest(_Basis):
    """Der gemeldete Fall: Weiss-Emitter, die NICHT zu den Farbzonen gehoeren."""

    def setUp(self):
        self.name, self.chans = _kanaele(self._eng, "ZQ06121")
        self.rgb = self._adressen(self.chans, "color_r", "color_g", "color_b")
        self.weiss = self._adressen(self.chans, "color_w")

    def test_vorbedingung_die_zahlen_gehen_auseinander(self):
        """Ohne diese Ungleichheit prueft die ganze Klasse den falschen Fall."""
        self.assertEqual(len(self.weiss), 8)
        self.assertEqual(len(self._adressen(self.chans, "color_r")), 48)

    def test_vollweiss_laesst_alle_farbzonen_leuchten(self):
        """★ Der Kern: vorher standen 144 von 144 Farbkanaelen auf 0."""
        from src.core.engine.rgb_matrix import MatrixStyle
        u = self._frame(self.chans, 48, style=MatrixStyle.RGBW)
        dunkel = [a for a in self.rgb if u.ch.get(a, 0) == 0]
        self.assertEqual(dunkel, [],
                         f"{len(dunkel)} von {len(self.rgb)} Farbkanaelen dunkel")

    def test_die_fremde_weissleiste_wird_nicht_angefasst(self):
        """Nicht „auf 0 gesetzt", sondern gar nicht geschrieben — sonst kann ein
        Dimmer-Effekt darunter sie nicht mehr fahren."""
        from src.core.engine.rgb_matrix import MatrixStyle
        u = self._frame(self.chans, 48, style=MatrixStyle.RGBW)
        beruehrt = [a for a in self.weiss if a in u.ch]
        self.assertEqual(beruehrt, [])

    def test_auch_ohne_kopf_matrix(self):
        """Der Fehler haengt nicht an FM-16/FM-40: ohne `head_grid` (jede Zelle
        faerbt das ganze Fixture) war er gemessen derselbe."""
        from src.core.engine.rgb_matrix import MatrixStyle
        u = self._frame(self.chans, 4, style=MatrixStyle.RGBW, head_grid=False)
        self.assertTrue(any(u.ch.get(a, 0) > 0 for a in self.rgb))
        self.assertEqual([a for a in self.weiss if a in u.ch], [])

    def test_rgb_style_bleibt_wie_er_war(self):
        """Positivkontrolle: das Problem hing ausschliesslich am RGBW-Style."""
        from src.core.engine.rgb_matrix import MatrixStyle
        u = self._frame(self.chans, 48, style=MatrixStyle.RGB)
        self.assertEqual([a for a in self.rgb if u.ch.get(a, 0) == 0], [])
        self.assertEqual([a for a in self.weiss if a in u.ch], [])


class PixelWeissBleibtUnveraendertTest(_Basis):
    """Die andere Seite: Weiss, das zum Pixel GEHOERT, muss weiter gesplittet
    werden — sonst repariert der Fix das eine und zerstoert das andere."""

    def setUp(self):
        self.name, self.chans = _kanaele(self._eng, "STAIRMB5X5")
        self.rgb = self._adressen(self.chans, "color_r", "color_g", "color_b")
        self.weiss = self._adressen(self.chans, "color_w")

    def test_vorbedingung_die_zahlen_decken_sich(self):
        self.assertEqual(len(self.weiss), 25)
        self.assertEqual(len(self._adressen(self.chans, "color_r")), 25)

    def test_reines_weiss_laeuft_weiter_ueber_den_weissen_chip(self):
        """Unveraendertes RGBW-Verhalten: R=G=B=0, W voll."""
        from src.core.engine.rgb_matrix import MatrixStyle
        u = self._frame(self.chans, 25, style=MatrixStyle.RGBW)
        self.assertEqual([a for a in self.rgb if u.ch.get(a, 0) != 0], [])
        self.assertEqual([u.ch.get(a) for a in self.weiss], [255] * 25)

    def test_bunte_farbe_behaelt_ihren_weissanteil(self):
        """(255, 128, 0): cw = min = 0, also unveraendert auf RGB."""
        from src.core.engine.rgb_matrix import MatrixStyle
        u = self._frame(self.chans, 25, style=MatrixStyle.RGBW,
                        farbe=(255, 128, 0))
        r0 = self._adressen(self.chans, "color_r")[0]
        self.assertEqual(u.ch.get(r0), 255)
        self.assertEqual(u.ch.get(self.weiss[0]), 0)


class DieRegelHaengtAnDerAusrichtungTest(_Basis):
    """Synthetisch, damit die Regel nicht an zwei Bibliothekseintraegen haengt."""

    def _geraet(self, n_rgb: int, n_weiss: int):
        chans, nr = [], 1
        for _ in range(n_rgb):
            for a in ("color_r", "color_g", "color_b"):
                chans.append(_ch(a, nr)); nr += 1
        for _ in range(n_weiss):
            chans.append(_ch("color_w", nr)); nr += 1
        return chans

    def _laeuft_split(self, n_rgb, n_weiss):
        from src.core.engine.rgb_matrix import MatrixStyle
        chans = self._geraet(n_rgb, n_weiss)
        u = self._frame(chans, n_rgb, style=MatrixStyle.RGBW)
        erste_rot = [c.channel_number for c in chans
                     if c.attribute == "color_r"][0]
        return u.ch.get(erste_rot) == 0        # Split lief -> Rot auf 0

    def test_gleiche_zahl__split_laeuft(self):
        self.assertTrue(self._laeuft_split(4, 4))

    def test_ungleiche_zahl__kein_split(self):
        self.assertFalse(self._laeuft_split(4, 2))

    def test_einzelkopf_rgbw__split_laeuft(self):
        """Ein gewoehnlicher RGBW-PAR (1 zu 1) darf sich nicht aendern."""
        self.assertTrue(self._laeuft_split(1, 1))

    def test_ohne_farbkoepfe__weiss_bleibt_bedient(self):
        """★★ Tunable White (warm + kalt, KEIN RGB) — der Fall, den meine erste
        Fassung kaputtgemacht hat.

        Die erste Regel lautete ``_n_w == max(_n_c, 1)``. Fuer ein Geraet ohne
        Farbkoepfe und mit MEHREREN Weiss-Kanaelen ist das False — gemessen
        schrieb ein solches Geraet danach **gar nichts** mehr (`{}`), vorher
        beide Weiss-Kanaele. Betroffen waren 72 Modi der Bibliothek.

        Der Fehler war eine zu enge Formulierung derselben Absicht: hat ein
        Geraet gar keine Farbkoepfe, IST das Weiss sein Emitter-Satz. Das
        ``max(_n_c, 1)`` deckte davon zufaellig nur den Ein-Kanal-Fall ab —
        und genau den hatte ich getestet. **Die Luecke lag also nicht im Code,
        sondern in meiner Fallauswahl.**
        """
        from src.core.engine.rgb_matrix import MatrixStyle
        chans = [_ch("intensity", 1), _ch("color_w", 2), _ch("color_w", 3)]
        # OHNE Kopf-Raster: eine Zelle faerbt das GANZE Geraet, also beide
        # Weiss-Kanaele. (Mit Kopf-Raster adressiert eine Zelle genau einen
        # Kopf und damit auch nur einen Kanal — daran ist die erste Fassung
        # dieses Tests gescheitert, nicht am Code.)
        u = self._frame(chans, 1, style=MatrixStyle.RGBW, head_grid=False)
        self.assertEqual(u.ch.get(2), 255)
        self.assertEqual(u.ch.get(3), 255,
                         "der zweite Weiss-Kanal fehlt — Tunable White bleibt dunkel")

    def test_ohne_farbkoepfe_und_EIN_weiss__weiterhin_bedient(self):
        """Der Nachbarfall, der zufaellig durchkam und deshalb nichts bewies."""
        from src.core.engine.rgb_matrix import MatrixStyle
        chans = [_ch("intensity", 1), _ch("color_w", 2)]
        u = self._frame(chans, 1, style=MatrixStyle.RGBW, head_grid=False)
        self.assertEqual(u.ch.get(2), 255)

    def test_ganz_ohne_weiss__unveraendert(self):
        """Ein reines RGB-Geraet im RGBW-Style: es gibt nichts zu verteilen, und
        der Split darf trotzdem laufen (Bestandsverhalten, `rgbw_split` zieht den
        Anteil ab und niemand nimmt ihn auf — das ist eine ANDERE Frage als
        ENG-25 und wird hier bewusst nicht mitgeaendert)."""
        self.assertTrue(self._laeuft_split(4, 0))


if __name__ == "__main__":
    unittest.main()
