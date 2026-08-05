"""ZQ06121 — Profil an Davids echtem Geraet bestaetigt (2026-08-05).

Der Balken war seit dem Anlegen mit dem Vorbehalt „(ungeprueft)" IM MODUSNAMEN
versehen, weil die Kanaltabelle des Herstellers nicht zu beschaffen war und die
Reihenfolge nur hergeleitet werden konnte. David hat sie am Geraet nachgesehen;
sie stimmt. Damit faellt der Vorbehalt — und genau daran haengt dieser Test:

★ DAS ENTFERNEN EINES VORBEHALTS IST EINE UMBENENNUNG, und Modusnamen sind in
diesem Projekt faktisch Schluessel (vier Stellen loesen den Modus ueber
`FixtureMode.name` auf). Eine Namensaenderung im Quelltext erreicht eine bereits
befuellte `fixtures.db` deshalb NUR ueber den Signatur-Abgleich in
`ensure_builtins` — sonst bleibt in jeder existierenden Installation der alte
Name stehen, waehrend der Quelltext etwas anderes behauptet.

Abgedeckt:
- Kanal-Layout beider Modi (154/144) und die Sicherheits-Defaults.
- Keiner der Modusnamen traegt noch einen Vorbehalt.
- `_ZQ06121_SIGNATURE` und `_zq06121_modes_data()` koennen nicht auseinander-
  laufen (eine Quelle).
- `ensure_builtins()` benennt ein Profil mit ALTEM Modusnamen in-place um,
  Profil-ID stabil, und ruehrt ein korrektes Profil nicht an.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from _fixture_quelle import frische_library     # FIXTEST-FRESH

MODE_154 = "154-Kanal 48 Zonen RGB + 8x Weiss"
MODE_144 = "144-Kanal 48 Zonen RGB"


def _load(s):
    from src.core.database.models import FixtureProfile, FixtureMode
    return s.execute(
        select(FixtureProfile)
        .options(selectinload(FixtureProfile.modes)
                 .selectinload(FixtureMode.channels))
        .where(FixtureProfile.short_name == "ZQ06121")
    ).scalars().first()


def _mode(prof, name):
    return next(m for m in prof.modes if m.name == name)


def _attrs(mode):
    return [c.attribute for c in sorted(mode.channels,
                                        key=lambda c: c.channel_number)]


class Zq06121ProfilTest(unittest.TestCase):
    """Kanal-Layout, so wie es am Geraet nachgesehen wurde."""

    @classmethod
    def setUpClass(cls):
        cls._eng = frische_library(cls)

    def test_beide_modi_vorhanden_mit_richtiger_kanalzahl(self):
        with Session(self._eng) as s:
            prof = _load(s)
            self.assertIsNotNone(prof, "ZQ06121 fehlt in der frischen Library")
            self.assertEqual(prof.fixture_type, "matrix")
            namen = {m.name: m.channel_count for m in prof.modes}
            self.assertEqual(namen, {MODE_154: 154, MODE_144: 144})

    def test_kein_modusname_traegt_noch_einen_vorbehalt(self):
        # Der eigentliche Punkt dieser Runde. Bewusst als Muster-Pruefung und
        # nicht nur als Gleichheit gegen die zwei Namen: ein spaeter angelegter
        # dritter Modus mit „(ungeprueft)" faellt damit ebenfalls auf.
        with Session(self._eng) as s:
            prof = _load(s)
            for m in prof.modes:
                for wort in ("ungeprueft", "ungeprüft", "beta", "vorlaeufig",
                             "vorläufig"):
                    self.assertNotIn(wort, m.name.lower(),
                                     f"Modus '{m.name}' traegt noch einen Vorbehalt")

    def test_154_layout_dimmer_strobe_zonen_weiss(self):
        with Session(self._eng) as s:
            a = _attrs(_mode(_load(s), MODE_154))
        self.assertEqual(a[0], "intensity")            # CH1
        self.assertEqual(a[1], "shutter")              # CH2
        self.assertEqual(a[2:5], ["color_r", "color_g", "color_b"])   # Zone 1
        self.assertEqual(a[143:146], ["color_r", "color_g", "color_b"])  # Zone 48
        self.assertEqual(a[146:], ["color_w"] * 8)     # CH147-154
        self.assertEqual(a.count("color_r"), 48)
        self.assertEqual(a.count("color_w"), 8)

    def test_144_ist_die_zonen_haelfte_des_154(self):
        # Dieselbe Herleitung, deshalb muss der 144er exakt der Zonen-Block des
        # 154ers sein — laeuft das auseinander, ist einer von beiden falsch.
        with Session(self._eng) as s:
            prof = _load(s)
            a154 = _attrs(_mode(prof, MODE_154))
            a144 = _attrs(_mode(prof, MODE_144))
        self.assertEqual(a144, a154[2:146])

    def test_sicherheits_defaults_dunkel_und_ohne_blitz(self):
        # 200 W, 768 LEDs: beim ersten Patchen darf nichts von selbst hell
        # werden oder blitzen.
        with Session(self._eng) as s:
            m = _mode(_load(s), MODE_154)
            per_nr = {c.channel_number: c for c in m.channels}
        self.assertEqual(per_nr[1].default_value, 0, "Dimmer-Default muss 0 sein")
        self.assertEqual(per_nr[2].default_value, 0, "Strobe-Default muss 0 sein")
        self.assertTrue(all(c.default_value == 0 for c in per_nr.values()),
                        "kein Kanal darf ungleich 0 vorbelegt sein")


class Zq06121SignaturTest(unittest.TestCase):
    """Die Soll-Signatur muss zu dem passen, was tatsaechlich angelegt wird."""

    @classmethod
    def setUpClass(cls):
        cls._eng = frische_library(cls)

    def test_signatur_entspricht_dem_angelegten_profil(self):
        from src.core.database.fixture_db import (_ZQ06121_SIGNATURE,
                                                  _mode_attr_signature)
        with Session(self._eng) as s:
            ist = _mode_attr_signature(_load(s))
        self.assertEqual(ist, _ZQ06121_SIGNATURE)

    def test_signatur_schluessel_sind_die_modusnamen(self):
        # Der Grund, warum eine reine Umbenennung ueberhaupt auffaellt. Geht
        # diese Eigenschaft verloren (z. B. Signatur als reine Attributliste),
        # bleibt der alte Name in jeder befuellten DB stehen.
        from src.core.database.fixture_db import _ZQ06121_SIGNATURE
        self.assertEqual(set(_ZQ06121_SIGNATURE), {MODE_154, MODE_144})


class Zq06121UmbenennungMigriertTest(unittest.TestCase):
    """★ Der Kern: eine DB mit dem ALTEN Namen wird in-place korrigiert."""

    def setUp(self):
        self._eng = frische_library(self)

    def _auf_alten_namen_zuruecksetzen(self):
        """Den Zustand jeder Installation herstellen, die den Balken vor dem
        2026-08-05 gepatcht hat."""
        with Session(self._eng) as s:
            prof = _load(s)
            for m in prof.modes:
                m.name = m.name + " (ungeprueft)"
            s.commit()
            return prof.id

    def test_alter_modusname_wird_umbenannt(self):
        from src.core.database.fixture_db import ensure_builtins
        alt_id = self._auf_alten_namen_zuruecksetzen()
        ensure_builtins()
        with Session(self._eng) as s:
            prof = _load(s)
            self.assertEqual(prof.id, alt_id, "Profil-ID muss stabil bleiben")
            self.assertEqual({m.name for m in prof.modes}, {MODE_154, MODE_144})

    def test_kanaele_ueberleben_die_umbenennung_unveraendert(self):
        # Es ist eine reine Umbenennung — die Attribute duerfen sich dabei
        # nicht verschieben, sonst waere Davids gepatchtes Geraet danach falsch
        # adressiert.
        from src.core.database.fixture_db import ensure_builtins
        self._auf_alten_namen_zuruecksetzen()
        ensure_builtins()
        with Session(self._eng) as s:
            a = _attrs(_mode(_load(s), MODE_154))
        self.assertEqual(len(a), 154)
        self.assertEqual(a[0], "intensity")
        self.assertEqual(a[1], "shutter")
        self.assertEqual(a[146:], ["color_w"] * 8)

    def test_korrektes_profil_bleibt_unberuehrt(self):
        # Idempotenz: ohne diesen Test koennte der Block bei JEDEM Start alle
        # Kanaele neu anlegen — die Kanal-IDs zeigen das.
        from src.core.database.fixture_db import ensure_builtins
        with Session(self._eng) as s:
            vorher = sorted(c.id for m in _load(s).modes for c in m.channels)
        ensure_builtins()
        with Session(self._eng) as s:
            nachher = sorted(c.id for m in _load(s).modes for c in m.channels)
        self.assertEqual(vorher, nachher,
                         "Idempotenz: korrektes Profil nicht neu aufbauen")

    def test_zweimal_ausfuehren_aendert_nichts_mehr(self):
        from src.core.database.fixture_db import ensure_builtins
        self._auf_alten_namen_zuruecksetzen()
        ensure_builtins()
        with Session(self._eng) as s:
            nach_erstem = sorted(c.id for m in _load(s).modes for c in m.channels)
        ensure_builtins()
        with Session(self._eng) as s:
            nach_zweitem = sorted(c.id for m in _load(s).modes for c in m.channels)
        self.assertEqual(nach_erstem, nach_zweitem)


if __name__ == "__main__":
    unittest.main()
