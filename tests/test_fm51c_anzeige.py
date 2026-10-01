"""FM-51 Scheibe C: Render-Vorrang, Waisen-Pruefung und Anzeige bei reiner
Weiss-Auswahl.

Ein Geraet, das nur ueber Weiss-Zellen (``"1:w3"``) gewaehlt ist, steht bewusst
NICHT in ``AppState.selected_fids``. Drei Stellen lasen bis Scheibe C nur diese
Liste:

* Render ``intensity_wins``: im Intensity-Tab gewinnt der Programmer-Dimmer
  gegen einen laufenden Dimmer-Effekt nur fuer GEWAEHLTE Geraete. Der geteilte
  Segment-Dimmer (``weiss_dimmer_key``) blieb wirkungslos, der Effekt behielt
  den Master.
* ``patch_dedup.referenzen``: Ort „auswahl" — das Geraet galt als nicht
  referenziert (Regel des Moduls: jede Unsicherheit ist eine Referenz).
* Live-Ansicht: kein Ring fuer das nur ueber Weiss gewaehlte Geraet. Die
  Markierung ist reine Anzeige und darf NICHT in die Canvas-Auswahl, die bei
  Klick/„Gruppe aus Auswahl" zurueckgeschrieben wird.

Aufbau: fid 1 = ZQ06121 (48 RGB-Zonen + 8 Weiss-Segmente, Adresse 1, CH1
Master), fid 2 = RGBW-PAR ZQ01424. Echter AppState, eingebaute Profile.
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                          # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from src.core.app_state import get_state                            # noqa: E402
from src.core.database.fixture_db import engine, ensure_builtins    # noqa: E402
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.show import patch_dedup                               # noqa: E402
from src.core.show.show_file import reset_show                      # noqa: E402

_app = QApplication.instance() or QApplication([])
BALKEN_MODUS = "154-Kanal 48 Zonen RGB + 8x Weiss"
MASTER_CH = 1


def _pid(short):
    with Session(engine()) as s:
        return s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first()


class _Rig(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ensure_builtins()

    def setUp(self):
        reset_show()
        self.st = get_state()
        self.st.add_fixture(PatchedFixture(
            fid=1, label="Balken", fixture_profile_id=_pid("ZQ06121"),
            mode_name=BALKEN_MODUS, universe=1, address=1, channel_count=154,
            fixture_type="matrix"), undoable=False)
        self.st.add_fixture(PatchedFixture(
            fid=2, label="PAR", fixture_profile_id=_pid("ZQ01424"),
            mode_name="8-Kanal RGBW", universe=1, address=300, channel_count=8,
            fixture_type="par"), undoable=False)
        self.addCleanup(self.st.set_selected_cells, [])
        self.addCleanup(self.st.clear_programmer)
        self.st.clear_programmer()
        self.st.set_selected_cells([])
        alt_fokus = getattr(self.st, "programmer_focus", None)
        self.addCleanup(setattr, self.st, "programmer_focus", alt_fokus)


# ── 1. Render: intensity_wins ────────────────────────────────────────────────

class IntensityWinsTest(_Rig):
    """Ein Dimmer-Effekt treibt CH1 (Master) auf 200; im Programmer steht der
    Segment-Dimmer auf 128. Intensity-Tab aktiv."""

    def _render_mit_effekt(self):
        def _tick(universes, patch_cache, dt):
            u = universes.get(1)
            if u is not None:
                u.set_channel(MASTER_CH, 200)
        with mock.patch.object(self.st.function_manager, "tick", _tick):
            self.st._render_frame(0.02)
        return self.st.universes[1].get_channel(MASTER_CH)

    def _belegen(self):
        self.assertEqual(self.st.weiss_dimmer_key(1, 3), "intensity")
        self.st.weiss_setzen(1, 3, 255)
        self.st.set_programmer_value(1, self.st.weiss_dimmer_key(1, 3), 128)
        self.st.programmer_focus = "Intensity"

    def test_nur_weiss_auswahl_segment_dimmer_gewinnt(self):
        self._belegen()
        self.st.set_selected_cells(["1:w3"])
        self.assertEqual(self.st.selected_fids, [])      # Vertrag unveraendert
        self.assertEqual(self._render_mit_effekt(), 128)

    def test_gegenprobe_ganzes_geraet(self):
        self._belegen()
        self.st.set_selected_cells(["1"])
        self.assertEqual(self._render_mit_effekt(), 128)

    def test_gegenprobe_anderes_geraet_gewaehlt_effekt_behaelt(self):
        self._belegen()
        self.st.set_selected_cells(["2"])
        self.assertEqual(self._render_mit_effekt(), 200)

    def test_gegenprobe_anderer_tab_effekt_behaelt(self):
        self._belegen()
        self.st.programmer_focus = "Color"
        self.st.set_selected_cells(["1:w3"])
        self.assertEqual(self._render_mit_effekt(), 200)


# ── 2. patch_dedup.referenzen, Ort „auswahl" ─────────────────────────────────

class PatchDedupTest(_Rig):

    def test_nur_weiss_gewaehlt_ist_referenziert(self):
        self.st.set_selected_cells(["1:w3"])
        self.assertEqual(self.st.programmer, {})
        self.assertIn("auswahl", patch_dedup.referenzen(self.st, 1))

    def test_nicht_gewaehltes_geraet_nicht_ueber_auswahl(self):
        self.st.set_selected_cells(["1:w3"])
        self.assertNotIn("auswahl", patch_dedup.referenzen(self.st, 2))

    def test_ganzes_geraet_weiter_referenziert(self):
        self.st.set_selected_cells(["2"])
        self.assertIn("auswahl", patch_dedup.referenzen(self.st, 2))


# ── 3. Live-Ansicht: Ring fuer das nur ueber Weiss gewaehlte Geraet ──────────

class LiveViewMarkierungTest(_Rig):

    def setUp(self):
        super().setUp()
        from src.ui.views.live_view import LiveView
        self.lv = LiveView()
        self.addCleanup(self.lv.deleteLater)

    def test_nur_weiss_bekommt_markierung_nicht_auswahl(self):
        self.st.set_selected_cells(["1:w3"])
        self.lv._on_global_selection_changed([])     # Payload = selected_fids
        self.assertEqual(self.lv._canvas._teil_fids, {1})
        # Reine Anzeige: die zurueckgeschriebene Canvas-Auswahl bleibt leer.
        self.assertEqual(self.lv._canvas._selected_fids, [])

    def test_ganzes_geraet_keine_teilmarkierung(self):
        self.st.set_selected_cells(["2", "1:w3"])
        self.lv._on_global_selection_changed([2])
        self.assertEqual(self.lv._canvas._selected_fids, [2])
        self.assertEqual(self.lv._canvas._teil_fids, {1})
        self.st.set_selected_cells(["1"])
        self.lv._on_global_selection_changed([1])
        self.assertEqual(self.lv._canvas._teil_fids, set())

    def test_leeren_raeumt_markierung(self):
        self.st.set_selected_cells(["1:w3"])
        self.lv._on_global_selection_changed([])
        self.st.set_selected_cells([])
        self.lv._on_global_selection_changed([])
        self.assertEqual(self.lv._canvas._teil_fids, set())

    def _shift_klick(self, fid):
        from unittest import mock
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent
        c = self.lv._canvas
        c._positions.setdefault(fid, (0.0, 0.0))
        ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(5, 5), QPointF(5, 5),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.ShiftModifier)
        with mock.patch.object(c, "_fixture_at", return_value=fid):
            c.mousePressEvent(ev)

    def test_shift_klick_auf_teilmarkierung_waehlt_ab_statt_ganzes_geraet(self):
        """Review FM-51 C: Der Ring sieht aus wie volle Auswahl — Umschalten muss
        ABWAEHLEN. Vorher wurde fid 1 hinzugefuegt und aus dem Segment das ganze
        Geraet (selected_cells == ['1'])."""
        self.st.set_selected_cells(["2", "1:w3"])
        self.lv._on_global_selection_changed([2])
        self._shift_klick(1)
        self.assertEqual(self.st.get_selected_cells(), ["2"])
        self.assertNotIn(1, self.st.get_selected_fids())

    def test_shift_klick_gegenprobe_normales_geraet_kommt_dazu(self):
        self.st.set_selected_cells(["2"])
        self.lv._on_global_selection_changed([2])
        self._shift_klick(1)
        self.assertIn(1, self.st.get_selected_fids())


if __name__ == "__main__":
    unittest.main()
