"""QA-15: Undo-Abdeckungs-Matrix fuer die mutierenden Kernaktionen.

Ein Fall pro undo-faehiger Kernaktion aus ``core/app_state.py`` (gefunden per
grep ``undoable``/``_push_undo``): Aktion ausfuehren -> ``undo()`` -> der exakte
Vorzustand ist wiederhergestellt (und ``redo()`` stellt die Aktion wieder her).
Der Test faengt REGRESSIONEN im Undo-Verhalten — er fordert NICHT hart 100 %
Abdeckung: bewusst NICHT-undo-bare Aktionen stehen als Baseline/Allowlist unten
und sind in ``docs/UNDO_COVERAGE.md`` dokumentiert.

Kern-Matrix (undo-bar, je ein Testfall):
    1. add_fixture              -> undo entfernt das Fixture wieder
    2. remove_fixture          -> undo stellt Fixture inkl. Adresse wieder her
    3. update_fixture          -> Patch-Aenderung (Adresse) rollt exakt zurueck
    4. auto_patch_fixtures     -> Sammel-Patch rollt alle Adressen zurueck
    5. set_programmer_value    -> Programmer-Set rollt auf Vorwert (bzw. leer)

Allowlist (bewusst NICHT undo-bar, Baseline unten dokumentiert):
    - FixtureGroup add/remove (Gruppen) laeuft in der View direkt gegen die
      Show-DB (fixture_group_view.py) und beruehrt den globalen UndoStack nicht.
      -> ENG-Item im Report; hier nur als Baseline-Assertion (kein Undo gepusht).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile, FixtureGroup
from src.core.engine.function_manager import get_function_manager
from src.core.show.show_file import reset_show
from src.core.undo import get_undo_stack


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _any_pid() -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id)).scalars().first())


class UndoCoverageTest(unittest.TestCase):
    """Abdeckungs-Matrix: pro Kernaktion genau ein Undo/Redo-Fall."""

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.undo = get_undo_stack()
        self.undo.clear()  # Singleton ueber den Prozess -> pro Test frisch

    def tearDown(self):
        self.fm.stop_all()
        self.undo.clear()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _fids(self):
        return {f.fid for f in self.state.get_patched_fixtures()}

    def _fix(self, fid):
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)

    def _add(self, fid, addr=1, undoable=False):
        self.state.add_fixture(PatchedFixture(
            fid=fid, label=f"Fix {fid}", fixture_profile_id=_any_pid(),
            mode_name="", universe=1, address=addr, channel_count=1,
            manufacturer_name="Test", fixture_name="Test", fixture_type="dimmer"),
            undoable=undoable)

    # ── 1) add_fixture ────────────────────────────────────────────────────────

    def test_add_fixture_undo_redo(self):
        self._add(1, addr=3, undoable=True)
        self.assertIn(1, self._fids())
        self.assertTrue(self.undo.can_undo(), "add_fixture muss ein Undo pushen")

        self.undo.undo()
        self.assertNotIn(1, self._fids(), "Undo muss das Fixture wieder entfernen")

        self.undo.redo()
        self.assertIn(1, self._fids(), "Redo muss das Fixture wieder anlegen")
        self.assertEqual(self._fix(1).address, 3,
                         "Redo muss die Adresse exakt wiederherstellen")

    # ── 2) remove_fixture ─────────────────────────────────────────────────────

    def test_remove_fixture_undo_restores_state(self):
        self._add(7, addr=42)  # Setup nicht auf dem Stack
        self.assertFalse(self.undo.can_undo())
        addr, uni = self._fix(7).address, self._fix(7).universe

        self.state.remove_fixture(7)
        self.assertNotIn(7, self._fids())
        self.assertTrue(self.undo.can_undo(), "remove_fixture muss ein Undo pushen")

        self.undo.undo()
        self.assertIn(7, self._fids(), "Undo muss das Fixture wiederherstellen")
        self.assertEqual((self._fix(7).address, self._fix(7).universe), (addr, uni),
                         "Wiederhergestelltes Fixture muss Adresse/Universe behalten")

    # ── 3) update_fixture (Patch-Aenderung) — ENG: undo aktuell DEFEKT ─────────

    def test_update_fixture_pushes_undo(self):
        """update_fixture legt zwar ein Undo-Command an (Push funktioniert)."""
        self._add(4, addr=10)
        ok = self.state.update_fixture(4, address=100, universe=2)
        self.assertTrue(ok)
        self.assertEqual((self._fix(4).address, self._fix(4).universe), (100, 2))
        self.assertTrue(self.undo.can_undo(), "update_fixture muss ein Undo pushen")

    def test_update_fixture_undo_rolls_back_ENG(self):
        """ENG-12: update_fixture ist undo-bar. Frueher rief die Undo/Redo-Closure
        ``update_fixture(fid, **before)``, wobei ``before`` (aus
        ``_fixture_to_dict``) selbst einen Schluessel ``fid`` trug ->
        ``TypeError: got multiple values for argument 'fid'``; der Fehler wurde im
        UndoStack nur geloggt und verschluckt, der Vorzustand blieb stehen.
        Fix: die Closure entfernt ``fid`` aus dem before/after-Dict, bevor es als
        **kwargs uebergeben wird. Siehe docs/UNDO_COVERAGE.md."""
        self._add(4, addr=10)
        self.state.update_fixture(4, address=100, universe=2)
        self.assertEqual((self._fix(4).address, self._fix(4).universe), (100, 2))

        self.undo.undo()
        self.assertEqual((self._fix(4).address, self._fix(4).universe), (10, 1),
                         "Undo muss die Patch-Aenderung exakt zuruecknehmen")

        self.undo.redo()
        self.assertEqual((self._fix(4).address, self._fix(4).universe), (100, 2),
                         "Redo muss die Patch-Aenderung wiederherstellen")

    # ── 4) auto_patch_fixtures ────────────────────────────────────────────────

    def test_auto_patch_undo_restores_all_addresses(self):
        # Zwei Fixtures mit "krummen" Adressen; Auto-Patch normalisiert sie.
        self._add(1, addr=50)
        self._add(2, addr=200)
        before = {f.fid: (f.universe, f.address)
                  for f in self.state.get_patched_fixtures()}

        self.state.auto_patch_fixtures()
        after = {f.fid: (f.universe, f.address)
                 for f in self.state.get_patched_fixtures()}
        self.assertNotEqual(after, before, "Auto-Patch muss Adressen aendern")
        self.assertTrue(self.undo.can_undo(), "auto_patch_fixtures muss ein Undo pushen")

        self.undo.undo()
        restored = {f.fid: (f.universe, f.address)
                    for f in self.state.get_patched_fixtures()}
        self.assertEqual(restored, before,
                         "Undo muss ALLE Adressen exakt auf den Vorzustand rollen")

    # ── 5) set_programmer_value (Programmer-Set) ──────────────────────────────

    def test_programmer_set_undo_restores_previous(self):
        self._add(3)
        # Vorwert setzen (nicht undo-bar), dann undo-bar ueberschreiben.
        self.state.set_programmer_value(3, "dimmer", 100, undoable=False)
        self.assertEqual(self.state.get_programmer_value(3, "dimmer"), 100)

        self.state.set_programmer_value(3, "dimmer", 255, undoable=True)
        self.assertEqual(self.state.get_programmer_value(3, "dimmer"), 255)
        self.assertTrue(self.undo.can_undo(), "set_programmer_value muss ein Undo pushen")

        self.undo.undo()
        self.assertEqual(self.state.get_programmer_value(3, "dimmer"), 100,
                         "Undo muss den vorherigen Programmer-Wert wiederherstellen")

        self.undo.redo()
        self.assertEqual(self.state.get_programmer_value(3, "dimmer"), 255,
                         "Redo muss den Programmer-Wert wiederherstellen")

    def test_programmer_set_undo_clears_when_no_prior(self):
        """Wenn zuvor KEIN Wert existierte, muss Undo den Attribut-Eintrag wieder
        leeren (old is None -> _clear_programmer_attr)."""
        self._add(3)
        self.assertIsNone(self.state.get_programmer_value(3, "dimmer"))

        self.state.set_programmer_value(3, "dimmer", 180, undoable=True)
        self.assertEqual(self.state.get_programmer_value(3, "dimmer"), 180)

        self.undo.undo()
        self.assertIsNone(self.state.get_programmer_value(3, "dimmer"),
                          "Undo muss den neu gesetzten Wert wieder entfernen")

    # ── Allowlist / Baseline: bewusst NICHT undo-bar ──────────────────────────

    def test_group_add_is_not_undoable_baseline(self):
        """FixtureGroup-Add laeuft in der View direkt gegen die Show-DB und
        beruehrt den globalen UndoStack NICHT. Dokumentierte Baseline (kein
        Produktivcode-Change) — schlaegt an, falls Gruppen kuenftig doch ueber
        die Undo-Pipeline laufen (dann Matrix oben ergaenzen)."""
        engine = self.state._show_engine
        self.assertIsNotNone(engine, "Show-Engine muss fuer den DB-Pfad existieren")
        with Session(engine) as s:
            s.add(FixtureGroup(name="Undo-Baseline", cols=8, rows=8,
                               positions_json="{}"))
            s.commit()
        self.assertFalse(
            self.undo.can_undo(),
            "Gruppen-Add ist (Stand QA-15) bewusst NICHT undo-bar — siehe "
            "docs/UNDO_COVERAGE.md (ENG-Item).")


if __name__ == "__main__":
    unittest.main()
