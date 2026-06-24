"""WURZEL-Fix (2026-06-24): Der Programmer-eingebettete EFX-Editor (follow_selection)
darf die Geraeteliste der gespielten EFX NICHT im Hintergrund ueberschreiben.

David: „Das Kreisfahren war über den EFX-Tab programmiert" — mit Moving Heads.
In der VC fuhr der Kreis trotzdem nicht. Wurzel: der eingebettete Follow-Editor
hoert GLOBAL auf SELECTION_CHANGED und setzte ``_current.fixtures = <Auswahl>``
(leer, wenn nichts Bewegliches ausgewaehlt ist) — auch wenn der Nutzer gar nicht
im EFX-Editor war, sondern in der VC. So verlor die gespielte EFX ihre Geraete
und ``write()`` lief stumm. (#45 machte das sichtbar, #50 fing es ab — DIES ist
die eigentliche Ursache.)

Fix: ``_sync_follow_selection`` wirkt nur, wenn die Editor-Seite sichtbar/aktiv ist.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

import src.core.app_state as A
from src.core.engine.efx import EfxInstance, EfxFixture
from src.ui.views.efx_view import EfxView


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0
        self.highlight_value = 255
        self.ranges = []


class _Fx:
    def __init__(self, fid, address, chans):
        self.fid = fid
        self.universe = 1
        self.address = address
        self._chans = chans
        self.invert_pan = self.invert_tilt = self.swap_pan_tilt = False


def _mh(fid, addr):
    return _Fx(fid, addr, [_Ch("pan", 1), _Ch("tilt", 2), _Ch("intensity", 3)])


class FollowNoBackgroundClobberTest(unittest.TestCase):
    def setUp(self):
        self._all = [_mh(1, 10), _mh(2, 20)]
        self._sel = []
        self._orig_gcp = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: getattr(fx, "_chans", [])
        st = A.get_state()
        st.get_patched_fixtures = lambda: list(self._all)
        st.get_selected_fids = lambda: list(self._sel)
        self.v = EfxView(follow_selection=True)        # eingebettet, NICHT gezeigt
        self.efx = self.v._fm.add(EfxInstance("Kreis"))
        self.efx.fixtures = [EfxFixture(fid=1), EfxFixture(fid=2)]  # im EFX-Tab zugewiesen
        self.v._current = self.efx

    def tearDown(self):
        A.get_channels_for_patched = self._orig_gcp
        try:
            self.v._fm.remove(self.efx.id)
            self.v.deleteLater()
        except Exception:
            pass

    def test_hidden_editor_keeps_fixtures_on_empty_selection(self):
        # Hintergrund-Selektionsevent (Nutzer ist in der VC, nichts ausgewaehlt):
        self._sel = []
        self.assertFalse(self.v.isVisible())
        self.v._sync_follow_selection()                # = der SELECTION_CHANGED-Handler
        self.assertEqual([f.fid for f in self.efx.fixtures], [1, 2],
                         "Unsichtbarer Follow-Editor darf Geraete nicht leeren")

    def test_hidden_editor_keeps_fixtures_on_foreign_selection(self):
        # Auch eine fremde (Nicht-Mover-)Auswahl darf die Geraete nicht aendern.
        self._sel = [2]
        self.v._sync_follow_selection()
        self.assertEqual([f.fid for f in self.efx.fixtures], [1, 2])

    def test_visible_editor_still_follows_selection(self):
        # Sichtbar/aktiv: Follow funktioniert weiterhin wie vorgesehen.
        self.v.show()
        self.assertTrue(self.v.isVisible())
        self._sel = [1]
        self.v._sync_follow_selection()
        self.assertEqual([f.fid for f in self.v._current.fixtures], [1])


if __name__ == "__main__":
    unittest.main()
