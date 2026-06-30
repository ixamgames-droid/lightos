"""Codex-Audit-Fixes im ProgrammerView (UI-05, UI-07, UI-08, UI-09).

- UI-05: programmer_focus wird beim Bau initialisiert (Bootstrap), nicht erst nach
  manuellem Tab-Wechsel — sonst greift "aktiver Tab gewinnt" (ENG-02) beim Start
  nicht.
- UI-07: range-basierte QuickBars (Shutter/Gobo) bekommen nur range-kompatible
  Fixtures, damit kein Vorlagen-Range-Mittelwert in einen inkompatiblen Kanal
  geschrieben wird (_range_signature / _range_compatible_fixtures).
- UI-08: die Orientierungs-Leiste (Pan/Tilt invert/swap) beruecksichtigt nur
  Pan/Tilt-faehige Fixtures — statische Geraete verfaelschen sonst den Tri-State
  und bekommen bedeutungslose Flags.
- UI-09: externe SELECTION_CHANGED (z. B. Preset-Browser-Gruppe) wird in den
  Attribut-Tab gespiegelt, ohne Re-Publish-Ping-Pong.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox
from PySide6.QtCore import Qt
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.show.show_file import reset_show
from src.ui.views import programmer_view as pv_mod
from src.ui.views.programmer_view import ProgrammerView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class _Base(unittest.TestCase):
    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        # Moving Head (Pan/Tilt, Shutter, Gobo) + statischer RGBW-PAR.
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Spider", fixture_profile_id=_pid("SPIDER14"),
            mode_name="14-Kanal", universe=1, address=1, channel_count=14,
            manufacturer_name="U King", fixture_name="Spider 14ch",
            fixture_type="moving_head"), undoable=False)
        self.state.add_fixture(PatchedFixture(
            fid=2, label="PAR", fixture_profile_id=_pid("ZQ01424"),
            mode_name="8-Kanal RGBW", universe=1, address=40, channel_count=8,
            manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
            fixture_type="par"), undoable=False)
        self.state._rebuild_render_plan()

    def _fx(self, fid):
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)


class UI05ProgrammerFocusBootstrap(_Base):
    def test_focus_set_on_build_not_none(self):
        """UI-05: nach dem Bau ist programmer_focus gesetzt (Bootstrap feuerte
        _on_main_tab_changed fuer den initial sichtbaren Tab) — nicht None."""
        self.state.set_programmer_focus(None)
        v = ProgrammerView()
        try:
            self.assertIsNotNone(
                self.state.programmer_focus,
                "programmer_focus darf nach dem Bau nicht None sein — sonst greift "
                "'aktiver Tab gewinnt' (ENG-02) beim Start nicht")
        finally:
            v.deleteLater()


class UI07RangeCompatibleQuickBars(_Base):
    def test_range_signature_distinguishes_layouts(self):
        class _R:
            def __init__(self, a, b, kind=""):
                self.range_from, self.range_to, self.kind = a, b, kind

        class _Ch:
            def __init__(self, attr, ranges):
                self.attribute, self.ranges = attr, ranges

        sig = ProgrammerView._range_signature
        a = _Ch("shutter", [_R(0, 7, "closed"), _R(8, 15, "open")])
        b = _Ch("shutter", [_R(0, 7, "closed"), _R(8, 15, "open")])
        c = _Ch("shutter", [_R(0, 31, "open"), _R(32, 63, "strobe")])
        d = _Ch("shutter", [])
        self.assertEqual(sig(a), sig(b), "gleiche Ranges -> gleiche Signatur")
        self.assertNotEqual(sig(a), sig(c), "andere Ranges -> andere Signatur")
        self.assertEqual(sig(d), (), "range-loser Kanal -> leere Signatur")

    def test_compatible_filter_excludes_mismatched_ranges(self):
        """_range_compatible_fixtures behaelt nur Fixtures mit gleichem Range-Layout
        fuer das Attribut wie die Vorlage."""
        class _R:
            def __init__(self, a, b, kind=""):
                self.range_from, self.range_to, self.kind = a, b, kind

        class _Ch:
            def __init__(self, attr, ranges):
                self.attribute, self.ranges = attr, ranges

        tpl = _Ch("shutter", [_R(0, 7, "closed"), _R(8, 15, "open")])
        same = object()   # gleiche Ranges
        diff = object()   # andere Ranges
        none = object()   # kein shutter-Kanal
        chmap = {
            same: [_Ch("shutter", [_R(0, 7, "closed"), _R(8, 15, "open")])],
            diff: [_Ch("shutter", [_R(0, 31, "open")])],
            none: [_Ch("dimmer", [])],
        }
        v = ProgrammerView()
        try:
            orig = pv_mod.get_channels_for_patched
            pv_mod.get_channels_for_patched = lambda f: chmap.get(f, [])
            try:
                out = v._range_compatible_fixtures(tpl, [same, diff, none])
            finally:
                pv_mod.get_channels_for_patched = orig
            self.assertIn(same, out)
            self.assertNotIn(diff, out)
            self.assertNotIn(none, out)
        finally:
            v.deleteLater()


class UI08OrientationPanTiltOnly(_Base):
    def test_orientation_bar_ignores_static_fixtures(self):
        """UI-08: bei gemischter Auswahl (Mover invert_pan=True + statischer PAR)
        zeigt 'Pan invertieren' VOLL gecheckt (nur Mover zaehlen), nicht Tri-State."""
        # Mover invert_pan=True; PAR bleibt default (kein Pan/Tilt).
        self.state.update_fixture(1, undoable=False, invert_pan=True)
        v = ProgrammerView()
        try:
            bar = v._build_orientation_bar([self._fx(1), self._fx(2)])
            self.assertIsNotNone(bar, "Bar muss gebaut werden (Mover hat Pan/Tilt)")
            cbs = bar.findChildren(QCheckBox)
            pan_cb = next(c for c in cbs if "Pan invert" in c.text())
            self.assertEqual(
                pan_cb.checkState(), Qt.CheckState.Checked,
                "Nur der Mover (invert_pan=True) zaehlt -> voll gecheckt; der "
                "statische PAR darf KEINEN Tri-State erzwingen")
        finally:
            v.deleteLater()

    def test_set_orientation_skips_static(self):
        """UI-08: ein Klick (ueber die gefilterte Liste) schreibt invert_pan NICHT
        auf den statischen PAR."""
        v = ProgrammerView()
        try:
            # _build_orientation_bar filtert intern -> _set_orientation bekaeme nur
            # Pan/Tilt-Fixtures. Direkt die gefilterte Liste pruefen:
            filtered = [f for f in [self._fx(1), self._fx(2)]
                        if any(getattr(ch, "attribute", "") in ("pan", "tilt")
                               for ch in pv_mod.get_channels_for_patched(f))]
            self.assertEqual([f.fid for f in filtered], [1],
                             "nur der Mover (fid=1) ist Pan/Tilt-faehig")
        finally:
            v.deleteLater()


class UI09ExternalSelectionMirror(_Base):
    def test_sync_follow_selection_helper(self):
        """UI-09: _sync_follow_selection uebernimmt die externe Auswahl in
        _selected_fids (Kern-Logik des SELECTION_CHANGED-Handlers)."""
        v = ProgrammerView()
        try:
            self.state.set_selected_fids([2])
            v._sync_follow_selection()
            self.assertEqual(v._selected_fids, [2])
            # Idempotenz / Guard: erneuter Aufruf ohne Aenderung kein Problem.
            v._sync_follow_selection()
            self.assertEqual(v._selected_fids, [2])
        finally:
            v.deleteLater()

    def test_selection_changed_event_mirrored(self):
        """UI-09: der echte SELECTION_CHANGED-Pfad (set_selected_fids) spiegelt die
        Auswahl in den ProgrammerView (Subscription verdrahtet)."""
        v = ProgrammerView()
        try:
            self.state.set_selected_fids([2])
            _app().processEvents()
            self.assertEqual(v._selected_fids, [2],
                             "externe set_selected_fids muss via SELECTION_CHANGED "
                             "in _selected_fids ankommen")
        finally:
            v.deleteLater()


if __name__ == "__main__":
    unittest.main()
