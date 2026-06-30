"""DEMO-03: reset_show() leert die Patch-Tabelle HART (DELETE), wie load_show.

Nach einem abgestuerzten Generator-Lauf koennen Patch-Zeilen in der Show-DB
(current_show.db) liegenbleiben, die NICHT im In-Memory-Cache stehen (verwaiste
Zeilen / Cache-DB-Desync). reset_show() rief intern nur _replace_patch_from_data(
state, []) auf. Faellt dessen clear_patch() aus (z. B. wegen des Desyncs), raeumt
der Fallback dort nur ueber den CACHE auf (remove_fixture je gecachter fid) — die
verwaisten DB-Zeilen ueberleben. Beim naechsten Patch greift dann der FLD-FID-Guard
in add_fixture und weicht auf next_fid() aus -> die neue fid wird ueberraschend nach
oben verschoben (z. B. fid=1 -> fid=12).

Der Fix laesst reset_show() ZUSAETZLICH direkt state.clear_patch() (hartes DELETE)
aufrufen — eigenstaendig abgesichert, unabhaengig vom internen clear in
_replace_patch_from_data. Diese Tests:
  * test_reset_show_hard_clears_patch_table / _new_patch_keeps_intended_fid_after_reset:
    Endzustand nach reset_show() — Patch-Tabelle leer bzw. naechste fid wie beabsichtigt.
  * test_reset_show_clears_orphan_when_internal_clear_fails:
    REGRESSIONS-Kern — simuliert die Crash-Situation (interner clear-Pfad raeumt nur
    den Cache) und prueft, dass reset_show() die verwaiste DB-Zeile TROTZDEM entfernt.
    Ohne den expliziten clear_patch()-Aufruf bliebe die Zeile liegen.
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.show import show_file
from src.core.show.show_file import reset_show


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _any_pid() -> int:
    """Irgendein gueltiges Builtin-Profil — der Test ist profil-agnostisch."""
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id)).scalars().first())


class ResetShowClearPatchTest(unittest.TestCase):

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()

    def tearDown(self):
        # Saubere, leere Show fuer Folgetests hinterlassen.
        reset_show()

    def _db_fids(self) -> set[int]:
        """fids DIREKT aus der Show-DB lesen (am Cache vorbei)."""
        with Session(self.state._show_engine) as s:
            return set(s.execute(select(PatchedFixture.fid)).scalars())

    def _db_count(self) -> int:
        with Session(self.state._show_engine) as s:
            return int(s.execute(select(func.count(PatchedFixture.fid))).scalar() or 0)

    def _inject_orphan(self, fid: int):
        """Verwaiste Patch-Zeile simulieren: eine fid DIREKT in die Show-DB
        schreiben, OHNE den In-Memory-Cache zu aktualisieren (so wie eine Zeile
        nach einem abgestuerzten Generator-Lauf zurueckbleibt)."""
        with Session(self.state._show_engine) as s:
            s.add(PatchedFixture(
                fid=fid, label=f"Orphan {fid}", fixture_profile_id=_any_pid(),
                mode_name="", universe=1, address=1, channel_count=1,
                manufacturer_name="Test", fixture_name="Test", fixture_type="dimmer"))
            s.commit()
        # Cache bewusst NICHT neu laden -> Zeile ist in der DB, aber nicht im Cache.

    def test_orphan_present_before_reset(self):
        """Vorbedingung: die injizierte Zeile liegt wirklich (nur) in der DB."""
        self._inject_orphan(1)
        self.assertIn(1, self._db_fids(), "Orphan muss in der DB liegen")
        self.assertNotIn(
            1, {f.fid for f in self.state.get_patched_fixtures()},
            "Orphan darf (noch) nicht im Cache stehen — sonst ist es kein Desync")

    def test_reset_show_hard_clears_patch_table(self):
        """Nach reset_show() ist die Patch-Tabelle WIRKLICH leer (auch Orphans)."""
        self._inject_orphan(1)
        self.assertEqual(self._db_count(), 1)

        reset_show()

        self.assertEqual(self._db_count(), 0,
                         "reset_show() muss die Patch-Tabelle hart leeren")
        self.assertEqual(self._db_fids(), set())
        self.assertEqual(self.state.get_patched_fixtures(), [])

    def test_new_patch_keeps_intended_fid_after_reset(self):
        """Kern-DoD: verwaiste Zeile -> reset_show() -> neuer Patch behaelt die
        beabsichtigte fid (kein Ausweichen auf einen hohen next_fid()-Wert)."""
        # Verwaiste Zeile mit hoher fid, die ohne harten Reset kollidieren wuerde.
        self._inject_orphan(11)

        reset_show()

        # Frisches Fixture mit fid=1 patchen — die beabsichtigte ID.
        pf = PatchedFixture(
            fid=1, label="Neu", fixture_profile_id=_any_pid(),
            mode_name="", universe=1, address=1, channel_count=1,
            manufacturer_name="Test", fixture_name="Test", fixture_type="dimmer")
        self.state.add_fixture(pf, undoable=False)

        fids = {f.fid for f in self.state.get_patched_fixtures()}
        self.assertEqual(fids, {1},
                         "Nach reset_show() darf der Patch die beabsichtigte fid=1 "
                         "vergeben — KEIN Ausweichen auf next_fid() wegen Orphan")
        # Und die hohe Orphan-fid ist endgueltig verschwunden.
        self.assertNotIn(11, self._db_fids(),
                         "Verwaiste fid=11 muss nach reset_show() weg sein")

    def test_reset_show_clears_orphan_when_internal_clear_fails(self):
        """REGRESSION (DEMO-03): Simuliert die Crash-Situation, in der der interne
        Aufraeumpfad von _replace_patch_from_data NUR den Cache raeumt (so wie der
        Fallback nach einem fehlgeschlagenen clear_patch). Genau hier MUSS der
        zusaetzliche, eigenstaendige clear_patch() in reset_show() greifen und die
        verwaiste DB-Zeile entfernen. Ohne den Fix bliebe sie liegen, und der naechste
        Patch wiche per FLD-FID-Guard auf next_fid() aus.

        Wir ersetzen _replace_patch_from_data fuer die Dauer des Tests durch eine
        Variante, die NUR die im Cache bekannten Fixtures entfernt (cache-only) — das
        bewusste 'kaputte' Verhalten. Bleibt die Patch-Tabelle danach trotzdem leer,
        ist allein der explizite reset_show()-clear_patch() dafuer verantwortlich.
        """
        self._inject_orphan(7)  # nur in der DB, nicht im Cache

        def _cache_only_replace(state, patch_data):
            # Bewusst defektes 'Aufraeumen': nur ueber den Cache, wie der
            # remove_fixture-Fallback nach einem fehlgeschlagenen clear_patch.
            for f in list(state.get_patched_fixtures()):
                state.remove_fixture(f.fid, undoable=False)

        with mock.patch.object(show_file, "_replace_patch_from_data",
                               side_effect=_cache_only_replace):
            reset_show()

        self.assertEqual(
            self._db_count(), 0,
            "reset_show() muss die verwaiste DB-Zeile auch dann entfernen, wenn der "
            "interne Aufraeumpfad sie (nur Cache) verfehlt — sonst fehlt der "
            "explizite clear_patch() (DEMO-03)")
        self.assertNotIn(7, self._db_fids())

    def test_reset_show_empty_is_idempotent(self):
        """Gegenprobe/Robustheit: reset_show() ohne Orphan haelt die Tabelle leer
        und stuerzt nicht ab (Rueckwaertskompatibilitaet, kein clear_patch-Fehler)."""
        reset_show()
        self.assertEqual(self._db_count(), 0)
        reset_show()
        self.assertEqual(self._db_count(), 0)

    def test_reset_show_emits_patch_changed_once(self):
        """STAB-09: reset_show() darf patch_changed nur EINMAL feuern — den
        finalen, gebuendelten Emit am Ende.

        Der DEMO-03-clear_patch() laeuft NACH _replace_patch_from_data, das
        _suppress_emits in seinem finally wieder auf False setzt. Ohne die
        STAB-09-Unterdrueckung feuerte dieser harte clear_patch() ein ZWEITES,
        re-entrantes patch_changed MITTEN im Reset — waehrend programmer,
        Funktionen, VC-Layout und Snap-Bibliothek noch den ALTEN Stand haben.
        Genau dieser re-entrante Refresh ist der STAB-07/BUG-01-Pfad (native
        Access Violation im Programmer-Refresh). Vor dem Fix: 2 Emits, danach
        genau 1.
        """
        # Etwas Patch-/Programmer-State anlegen, damit der Reset real raeumt.
        pf = PatchedFixture(
            fid=1, label="X", fixture_profile_id=_any_pid(),
            mode_name="", universe=1, address=1, channel_count=1,
            manufacturer_name="Test", fixture_name="Test", fixture_type="dimmer")
        self.state.add_fixture(pf, undoable=False)
        self.state.set_programmer_value(1, "dimmer", 200)

        events: list[str] = []

        def _cb(event, *_args):
            if event == "patch_changed":
                events.append(event)

        self.state.subscribe(_cb)
        try:
            reset_show()
        finally:
            try:
                self.state._callbacks.remove(_cb)
            except (ValueError, AttributeError):
                pass

        self.assertEqual(
            len(events), 1,
            "reset_show() muss patch_changed GENAU einmal feuern (finaler "
            "gebuendelter Emit); ein zweiter, re-entranter Emit aus dem harten "
            "clear_patch() ist die STAB-09-Regression (siehe STAB-07/BUG-01)")


if __name__ == "__main__":
    unittest.main()
