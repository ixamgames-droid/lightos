"""OUT-63 — die Laser-NOT-AUS-Maske bleibt bei aktivem Latch klebrig.

Befund (adversariales Review zu #929, schon auf main): Laser-NOT-AUS aktiv, auf
der alten Laser-Adresse liegt ein INVERSE-Modifier (Modifier gehoeren zum Rig
und ueberleben einen Show-Load). Faellt der Laser bei aktivem Latch aus dem
Patch — Show ohne ihn geladen, geloescht, umadressiert, anderes Universum —,
engte der Plan-Rebuild die Ebene-2-Maske auf die NEUEN Laser-Adressen ein. Der
Laser haengt physisch aber weiter an der alten Adresse: dort lag 0 im Frame,
INVERSE machte 255 daraus — Laser AN trotz NOT-AUS.

Fix: solange der Latch steht, ist die Maske die Vereinigung aller Laser-
Adressen (je Universum) seit der Aktivierung; erst das Loesen leert sie.

Alle Tests ueber den echten Pfad: echter AppState, echter Patch,
``save_show``/``load_show``, ``set_laser_estop``, ``_render_frame`` und
``_send_all``; geprueft wird der gesendete Frame (``_display_frame``).
Keine injizierten Masken.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import get_state                                  # noqa: E402
from src.core.engine.channel_modifier import (ChannelModifier, CurveType,  # noqa: E402
                                              get_modifier_manager)

ALT = 40          # Laser-Startadresse vor dem Wechsel
NEU = 200         # Ziel beim Umadressieren


class KlebrigeEstopMaskeTest(unittest.TestCase):

    def setUp(self):
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
        from src.core.database.models import FixtureProfile
        from src.core.show.show_file import reset_show
        ensure_builtins()
        self.st = get_state()
        self.om = self.st.output_manager
        self.mods = get_modifier_manager()
        self.st.set_laser_estop(False)
        reset_show()
        with Session(fdb_engine()) as s:
            prof = s.execute(select(FixtureProfile).where(
                FixtureProfile.short_name == "PARTYLASER")).scalars().first()
            self.assertIsNotNone(prof, "Laser-Profil fehlt in der Bibliothek")
            self.pid, self.modus = prof.id, prof.modes[0].name
            self.n = len(prof.modes[0].channels)
        self.tmp = tempfile.mkdtemp(prefix="out63_")
        self._mod_adressen = []
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(self._modifier_weg)
        self.addCleanup(self.st.set_laser_estop, False)
        self.addCleanup(self.st.clear_programmer)

    # ── Helfer ───────────────────────────────────────────────────────────────

    def _modifier_weg(self):
        for u, a in self._mod_adressen:
            self.mods.remove(u, a)

    def _inverse(self, universe, start):
        for a in range(start, start + self.n):
            self.mods.add(ChannelModifier(universe=universe, address=a,
                                          curve=CurveType.INVERSE))
            self._mod_adressen.append((universe, a))

    def _laser(self, fid, universe, adresse):
        from src.core.database.models import PatchedFixture
        if universe not in self.om.universes:
            self.om.add_universe(universe)
        self.st.add_fixture(PatchedFixture(
            fid=fid, label=f"Laser {fid}", fixture_profile_id=self.pid,
            mode_name=self.modus, universe=universe, address=adresse,
            channel_count=self.n, fixture_type="laser"), undoable=False)

    def _speichern(self, name):
        from src.core.show.show_file import save_show
        pfad = os.path.join(self.tmp, name + ".lshow")
        save_show(pfad)
        return pfad

    def _senden(self):
        self.st._render_frame(0.02)
        self.om._send_all()

    def _offen(self, universe, start):
        """Adressen des Laser-Blocks, die im GESENDETEN Frame nicht 0 sind."""
        f = self.om._display_frame.get(universe)
        self.assertIsNotNone(f, f"kein Frame fuer Universum {universe}")
        return [a for a in range(start, start + self.n) if f[a - 1] != 0]

    def _vorbedingung_inverse_offen(self, universe, start):
        """Ohne Maske macht INVERSE die alten Adressen hell — sonst testete
        der Aufbau nichts."""
        self.assertTrue(self._offen(universe, start),
                        "Testaufbau: INVERSE muesste ohne Maske Werte != 0 liefern")

    # ── (1) Show ohne Laser bei aktivem Latch + INVERSE ──────────────────────

    def test_show_ohne_laser_bei_aktivem_latch_bleibt_dunkel(self):
        from src.core.show.show_file import load_show, reset_show
        reset_show()
        ohne = self._speichern("ohne_laser")
        self._vorbedingung_inverse_offen_nach_inverse(1, ALT)
        self._laser(1, 1, ALT)
        self.st.set_laser_estop(True)
        self._senden()
        self.assertEqual(self._offen(1, ALT), [], "Vorbedingung: Laser im NOT-AUS dunkel")
        ok, msg = load_show(ohne)
        self.assertTrue(ok, msg)
        self.assertTrue(self.st.laser_estop_active, "Load darf den Latch nicht loesen")
        self._senden()
        self.assertEqual(self._offen(1, ALT), [],
                         "OUT-63: Laser nach Load einer Show ohne ihn AN (INVERSE)")

    def _vorbedingung_inverse_offen_nach_inverse(self, universe, start):
        self._inverse(universe, start)
        self._senden()
        self._vorbedingung_inverse_offen(universe, start)

    # ── (2) Laser aus dem Patch loeschen ─────────────────────────────────────

    def test_laser_loeschen_bei_aktivem_latch_bleibt_dunkel(self):
        self._laser(1, 1, ALT)
        self._inverse(1, ALT)
        self.st.set_laser_estop(True)
        self._senden()
        self.assertEqual(self._offen(1, ALT), [])
        self.st.remove_fixture(1, undoable=False)
        self._senden()
        self.assertEqual(self._offen(1, ALT), [],
                         "OUT-63: geloeschter Laser bei aktivem NOT-AUS AN (INVERSE)")

    # ── (3) Laser umadressiert: alte UND neue Adresse dunkel ─────────────────

    def test_laser_umadressiert_alt_und_neu_dunkel(self):
        self._laser(1, 1, ALT)
        self._inverse(1, ALT)
        self._inverse(1, NEU)
        self.st.set_laser_estop(True)
        self.assertTrue(self.st.update_fixture(1, undoable=False, address=NEU))
        self._senden()
        self.assertEqual(self._offen(1, NEU), [], "neue Laser-Adresse offen")
        self.assertEqual(self._offen(1, ALT), [],
                         "OUT-63: alte Laser-Adresse nach Umadressieren AN (INVERSE)")

    # ── (4) Nach dem Loesen sind die alten Adressen wieder frei ──────────────

    def test_nach_dem_loesen_sind_alte_adressen_frei(self):
        self._laser(1, 1, ALT)
        self._inverse(1, ALT)
        self.st.set_laser_estop(True)
        self.st.remove_fixture(1, undoable=False)
        self._senden()
        self.assertEqual(self._offen(1, ALT), [])
        self.st.set_laser_estop(False)
        self.assertEqual(self.om._laser_estop_mask, {})
        self._senden()
        # Nicht mehr gepatcht -> normale Ausgabe: INVERSE auf 0 = 255.
        self.assertEqual(len(self._offen(1, ALT)), self.n,
                         "alte Adressen nach dem Loesen weiter gesperrt")
        # Ein neuer Latch beginnt frisch — nur die aktuellen Laser-Adressen.
        self._laser(2, 1, NEU)
        self.st.set_laser_estop(True)
        self.assertEqual(self.om._laser_estop_mask,
                         {1: frozenset(range(NEU, NEU + self.n))})

    # ── (5) Zwei Universen / Universum-Wechsel ───────────────────────────────

    def test_zwei_universen_show_ohne_laser(self):
        from src.core.show.show_file import load_show, reset_show
        reset_show()
        ohne = self._speichern("ohne_laser")
        self._laser(1, 1, ALT)
        self._laser(2, 2, NEU)
        self._inverse(1, ALT)
        self._inverse(2, NEU)
        self.st.set_laser_estop(True)
        ok, msg = load_show(ohne)
        self.assertTrue(ok, msg)
        self._senden()
        self.assertEqual(self._offen(1, ALT), [], "Universum 1: Laser AN")
        self.assertEqual(self._offen(2, NEU), [], "Universum 2: Laser AN")

    # ── (6) Latch erst WAEHREND des Ladens einer Show ohne Laser ─────────────

    def test_latch_im_lade_fenster_show_ohne_laser_bleibt_dunkel(self):
        """Der NOT-AUS kommt nach dem reset-first (Plan leer). Waehrend der
        Sperre schuetzt OUT-61b; danach muss die klebrige Maske die Laser-
        Adressen vom Ladebeginn weiter halten."""
        from unittest import mock
        from src.core.show import show_file
        from src.core.show.show_file import load_show, reset_show
        reset_show()
        ohne = self._speichern("ohne_laser")
        self._laser(1, 1, ALT)
        self._inverse(1, ALT)
        for attr in ("macro", "shutter"):
            self.st.set_programmer_value(1, attr, 200)
        self._senden()
        self.assertTrue(self._offen(1, ALT), "Laser laeuft nicht")
        echt = show_file._reset_state

        def reset_dann_notaus(*a, **k):
            echt(*a, **k)
            self.st.set_laser_estop(True)

        with mock.patch.object(show_file, "_reset_state", reset_dann_notaus):
            ok, msg = load_show(ohne)
        self.assertTrue(ok, msg)
        self.assertTrue(self.st.laser_estop_active)
        self._senden()
        self.assertEqual(self._offen(1, ALT), [],
                         "OUT-63: Latch im Lade-Fenster, nach dem Laden Laser AN")

    def test_universum_wechsel_alt_und_neu_dunkel(self):
        self._laser(1, 1, ALT)
        if 2 not in self.om.universes:
            self.om.add_universe(2)
        self._inverse(1, ALT)
        self._inverse(2, ALT)
        self.st.set_laser_estop(True)
        self.assertTrue(self.st.update_fixture(1, undoable=False, universe=2))
        self._senden()
        self.assertEqual(self._offen(2, ALT), [], "neues Universum offen")
        self.assertEqual(self._offen(1, ALT), [],
                         "OUT-63: altes Universum nach Wechsel AN (INVERSE)")


class KeinStillerRueckfallTest(unittest.TestCase):
    """OUT-63 (Niedrig-Befund): ``_push_laser_estop_mask`` rief nach einem
    TypeError ``set_laser_estop_mask`` OHNE ``aktiv=`` erneut auf; die Maske
    kam an, der OUT-61b-Latch (``_laser_estop_aktiv``) aber wurde aus der Maske
    abgeleitet — bei leerem Plan also still AUS."""

    def test_typeerror_im_setter_ruft_nicht_ohne_aktiv_erneut(self):
        st = get_state()
        om = st.output_manager
        aufrufe = []
        echt = om.set_laser_estop_mask

        def spion(maske, aktiv=None):
            aufrufe.append(aktiv)
            if aktiv is not None:
                raise TypeError("Fehler im Setter")
            return echt(maske, aktiv=aktiv)

        om.set_laser_estop_mask = spion
        try:
            st._push_laser_estop_mask(target_active=True, target_addrs={})
        finally:
            del om.set_laser_estop_mask
            st._laser_estop_klebrig = {}
            st._push_laser_estop_mask()
        self.assertEqual(aufrufe, [True],
                         "Rueckfall ohne aktiv= schaltet den OUT-61b-Schutz still ab")


if __name__ == "__main__":
    unittest.main()
