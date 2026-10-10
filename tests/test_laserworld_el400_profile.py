"""FM-68: Laserworld EL-400RGB MK2 (``EL400RGBMK2``) — Bibliotheksprofil.

Show-Laser Klasse 3B, RGB 320-400 mW, EIN DMX-Modus mit 9 Kanaelen.
Quelle: Laserworld-Handbuch „EL-400RGB MK2“, Abschnitt 8.4 (DMX-512), in zwei
Revisionen (Maerz 2022 und April 2024) — beide Tabellen deckungsgleich.
Gegenprobe: QLC+ ``Laserworld-EL-400RGB-MK2.qxf`` und Open Fixture Library
``laserworld/el-400rgb-mk2.json`` (gleiche Kanalfolge, gleiche Betriebsart-Baender).

Festgenagelt wird:

1. die Kanalfolge und die Attribute laut Handbuch (eine verrutschte Zeile
   schaltet am Geraet die falsche Funktion);
2. die Betriebsart-Baender von Kanal 1 Wert fuer Wert — ``0-49 Laser aus`` ist
   die Grundlage der ganzen Sicherheitskette;
3. **Sicherheit:** Patch-Grundwert, Blackout, Grand Master 0, Ziel-Blackout und
   Laser-NOT-AUS landen an Kanal 1 auf einem Wert im Band „Laser aus“ — ueber den
   echten Sende-Pfad (``OutputManager._send_all``), mit den Masken, die AppState
   aus den echten Profil-Kanaelen baut;
4. X/Y sind ``laser_x``/``laser_y`` (EFX auf Laser-Achsen, LAS-22/LAS-23) und
   tragen bewusst KEINE Bereiche (die 3D-Ansicht liest den ersten Bereich als
   statischen — ein Band ``0-10 Mitte`` haette 11-255 als Eigenbewegung gezeigt);
5. jeder Kanal ausser der Betriebsart ist auf der Laser-Seite des Programmers
   bedienbar (LAS-26: ``effect_speed`` fehlte dort).
"""
import os
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from _fixture_quelle import frische_library     # FIXTEST-FRESH

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(_REPO, "fixtures", "bibliothek", "laserworld",
                     "el-400rgb-mk2.json")
KURZ = "EL400RGBMK2"
MODUS = "9-Kanal"
ADRESSE = 101           # Startadresse des Test-Patches
UNIVERSUM = 1

# Handbuch 8.4, Kanal 1 (EN „Laser off / Sound mode / Automatic mode / Static
# pattern (DMX mode) / Dynamic pattern (DMX mode)“; DE „Laser aus …“).
BETRIEBSART = [(0, 49, "closed"), (50, 99, "sound"), (100, 149, ""),
               (150, 199, "open"), (200, 255, "open")]
ATTRIBUTE = ["shutter", "gobo_wheel", "laser_x", "laser_y", "laser_scan_rate",
             "effect_speed", "zoom", "laser_color", "laser_color_change"]


def _laden(session):
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
        .where(FixtureProfile.short_name == KURZ)
    ).scalars().first()


class _Fx:
    """Gepatchtes Geraet (nur die Felder, die die Masken-Bauer lesen)."""
    protocol = "dmx"
    fixture_type = "laser"
    name = "EL-400RGB MK2"
    label = ""

    def __init__(self, fid=1):
        self.fid = fid
        self.universe = UNIVERSUM
        self.address = ADRESSE


class _Basis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.core.database.bibliothek_format import einspielen
        motor = frische_library(cls)
        # Nur diese eine Datei einspielen — die ganze Bibliothek kostet Sekunden
        # und testet hier nichts.
        verz = tempfile.mkdtemp(prefix="lightos_fm68_")
        cls.addClassCleanup(shutil.rmtree, verz, True)
        os.makedirs(os.path.join(verz, "laserworld"))
        shutil.copy(DATEI, os.path.join(verz, "laserworld"))
        with Session(motor) as s:
            einspielen(s, verz)
            s.commit()
        cls._s = Session(motor)
        cls.addClassCleanup(cls._s.close)
        cls.prof = _laden(cls._s)

    def _kanaele(self):
        modus = next(m for m in self.prof.modes if m.name == MODUS)
        return sorted(modus.channels, key=lambda c: c.channel_number)

    def _baender(self, nr):
        ch = self._kanaele()[nr - 1]
        return sorted(ch.ranges, key=lambda r: r.range_from)


class DateiTest(unittest.TestCase):
    def test_datei_besteht_den_waechter(self):
        from src.core.database.bibliothek_format import lade_datei, pruefe
        self.assertEqual(pruefe(lade_datei(DATEI), DATEI), [])

    def test_herkunft_handbuch_mit_quelle(self):
        from src.core.database.bibliothek_format import lade_datei
        d = lade_datei(DATEI)
        self.assertEqual(d["herkunft"], {"art": "hersteller-handbuch",
                                         "lizenz": "eigen"})
        self.assertIn("laserworld.com", d["quelle"]["url"])
        # Was am Geraet noch offen ist, steht im Profil (nicht nur im Backlog).
        self.assertIn("abzugleichen", d["notizen"])
        # DIP-Schalter: 10 OFF = DMX, 1-9 = Adresse (Handbuch 8.4).
        self.assertIn("10 OFF = DMX", d["notizen"])


class KanalbelegungTest(_Basis):
    def test_ein_modus_mit_neun_kanaelen(self):
        self.assertIsNotNone(self.prof, "Profil nicht eingespielt")
        self.assertEqual([m.name for m in self.prof.modes], [MODUS])
        self.assertEqual(len(self._kanaele()), 9)

    def test_geraetetyp_laser(self):
        self.assertEqual(self.prof.fixture_type, "laser")
        self.assertEqual(self.prof.manufacturer.name, "Laserworld")

    def test_attribute_in_handbuch_reihenfolge(self):
        self.assertEqual([c.attribute for c in self._kanaele()], ATTRIBUTE)

    def test_kein_attribut_doppelt(self):
        # attr#N-Falle (ENG-03): ein doppeltes Attribut wuerde als Kopf 2 gelesen.
        attrs = [c.attribute for c in self._kanaele()]
        self.assertEqual(len(attrs), len(set(attrs)))

    def test_betriebsart_baender_wie_handbuch(self):
        self.assertEqual(
            [(r.range_from, r.range_to, r.kind) for r in self._baender(1)],
            BETRIEBSART)

    def test_betriebsart_lueckenlos(self):
        b = self._baender(1)
        self.assertEqual(b[0].range_from, 0)
        self.assertEqual(b[-1].range_to, 255)
        for a, n in zip(b, b[1:]):
            self.assertEqual(n.range_from, a.range_to + 1)

    def test_xy_ohne_baender_und_mitte_im_namen(self):
        for nr in (3, 4):
            ch = self._kanaele()[nr - 1]
            self.assertEqual(list(ch.ranges), [])
            self.assertIn("0-10 = Mitte", ch.name)
            self.assertEqual(ch.default_value, 0)      # Handbuch: 0-10 Mitte


class SicherheitTest(_Basis):
    """Kanal 1 muss in jeder Abschalt-Lage im Band „Laser aus“ landen."""

    def setUp(self):
        from src.core.app_state import AppState
        from src.core.dmx.output_manager import OutputManager
        from src.core.engine.channel_modifier import get_modifier_manager
        get_modifier_manager().clear()
        self.addCleanup(get_modifier_manager().clear)
        self.chans = self._kanaele()
        self.fx = _Fx()
        self.st = AppState.__new__(AppState)
        self.index = {self.fx.fid: (self.fx, self.chans)}
        self.om = OutputManager()
        self.u = self.om.add_universe(UNIVERSUM)
        # Laser AN: statisches Muster, Farbe, Position.
        for nr, wert in ((1, 175), (2, 12), (3, 90), (4, 90), (8, 40)):
            self.u.set_channel(ADRESSE + nr - 1, wert)
        self.om.set_gm_address_mask(self.st._build_gm_mask(self.index))
        self.om.set_gm_laser_aus_mask(
            self.st._build_gm_laser_aus_mask(self.index))
        self.om.set_blackout_keep_mask(
            {u: frozenset(a) for u, a in
             self.st._build_blackout_keep_mask(self.index).items()})

    def _kanal1(self):
        return self.om._display_frame[UNIVERSUM][ADRESSE - 1]

    def _ist_aus(self, wert):
        lo, hi, kind = BETRIEBSART[0]
        self.assertEqual(kind, "closed")
        self.assertTrue(lo <= wert <= hi, f"Kanal 1 = {wert}: Laser NICHT aus")

    def test_vorher_an(self):
        self.om._send_all()
        self.assertEqual(self._kanal1(), 175)

    def test_patch_grundwert_ist_aus(self):
        self._ist_aus(self.chans[0].default_value)

    def test_gm_aus_maske_kennt_den_aus_wert(self):
        self.assertEqual(self.st._build_gm_laser_aus_mask(self.index),
                         {UNIVERSUM: {ADRESSE: 0}})

    def test_grand_master_null(self):
        self.om.grand_master = 0.0
        self.om._send_all()
        self._ist_aus(self._kanal1())

    def test_blackout(self):
        # Laser haben keinen Erhalten-Kanal — der Blackout nullt das Geraet ganz.
        keep = self.st._build_blackout_keep_mask(self.index)
        self.assertFalse(keep.get(UNIVERSUM))
        self.om.set_blackout(True)
        self.om._send_all()
        self._ist_aus(self._kanal1())

    def test_ziel_blackout(self):
        _erhalten, aus = self.st._blackout_aufteilung(self.fx, self.chans)
        self.assertIn(ADRESSE, aus)
        self.om.set_target_blackout("vc-taste", {UNIVERSUM: frozenset(aus)})
        self.om._send_all()
        self._ist_aus(self._kanal1())

    def test_laser_not_aus(self):
        self.om.set_laser_estop_mask(
            {UNIVERSUM: frozenset(ADRESSE + i for i in range(9))})
        self.om._send_all()
        self._ist_aus(self._kanal1())

    def test_not_aus_loest_nur_ueber_betriebsart_oder_muster(self):
        # A3D-02: Position/Farbe/Zoom duerfen den NOT-AUS nicht loesen; die
        # Betriebsart (shutter) und die Musterauswahl (gobo_wheel) schon.
        from src.core.app_state import _LASER_REARM_ATTRS
        rearm = {c.attribute for c in self.chans} & _LASER_REARM_ATTRS
        self.assertEqual(rearm, {"shutter", "gobo_wheel"})


class LaserSeiteTest(_Basis):
    """LAS-26: jeder Kanal ausser der Betriebsart (Modus-Kacheln) ist auf der
    Laser-Seite des Programmers als Regler erreichbar."""

    def test_alle_kanaele_haben_einen_platz(self):
        from src.ui.views import laser_view as LV
        sichtbar = set(LV.LASER_EXTRA_ATTRS)
        gruppiert = set(LV._GROUPED_ATTRS)
        for ch in self._kanaele():
            a = ch.attribute
            if a == "shutter":
                continue
            self.assertTrue(a.startswith("laser_") or a in sichtbar,
                            f"{a} wird auf der Laser-Seite ausgefiltert")
            self.assertIn(a, gruppiert,
                          f"{a} landet nur unter „Weitere Kanäle“")


if __name__ == "__main__":
    unittest.main()
