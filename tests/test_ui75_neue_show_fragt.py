"""UI-75: eine nie gespeicherte Show fragt beim Beenden, sobald sie Show-Inhalt hat.

Codex-Review #847: ``MainWindow._has_unsaved_changes()`` wertete bei einer nie
gespeicherten Show nur Cuelisten, Funktionen und Programmer-Werte aus. Eine
Show mit nur Patch oder nur VC-Layout schloss deshalb ohne Rueckfrage - die
Patch-Arbeit war weg -, eine mit nur Programmer-Werten fragte. Die Anleitung
„Erste Schritte“ verspricht das Gegenteil: Show-Inhalt (Patch, Cuelisten,
Funktionen, VC-Layout) fragt, Bedienung (Programmer, GO, Fader, Tempo) nicht.

Ein echtes Hauptfenster (Bau ist teuer -> eine Klasse, ``setUpClass``).
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from src.core.show import show_file as SF

from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


def _app():
    return QApplication.instance() or QApplication([])


def _dimmer(fid: int, addr: int = 1):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database.fixture_db import engine as fdb_engine
    from src.core.database.models import FixtureProfile, PatchedFixture
    with Session(fdb_engine()) as s:
        pid = int(s.execute(select(FixtureProfile.id)).scalars().first())
    return PatchedFixture(
        fid=fid, label=f"Fix {fid}", fixture_profile_id=pid,
        mode_name="", universe=1, address=addr, channel_count=1,
        manufacturer_name="Test", fixture_name="Test", fixture_type="dimmer")


class NieGespeicherteShowTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        from src.core.app_state import get_state
        from src.ui import main_window as mw
        cls.mw = mw
        cls.state = get_state()
        SF.reset_show()
        cls.win = mw.MainWindow()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.win.deleteLater()
        except Exception:
            pass
        cls.app.processEvents()
        destroy_all_top_level_widgets(cls.app)
        SF.reset_show()
        cls.app.processEvents()

    def setUp(self):
        # Jeder Fall beginnt mit einer leeren, nie gespeicherten Show.
        SF.reset_show()
        self.win._vc_view.from_dict({"widgets": []})
        self.win._current_show_path = None
        self.win._aus_auto_save = False
        self.app.processEvents()
        self.assertFalse(self.win._has_unsaved_changes(),
                         "leere neue Show darf nicht nach dem Speichern fragen")

    def _beenden_fragt(self) -> bool:
        """Beenden mit „Abbrechen“ auf die Rueckfrage. NUR aufrufen, wenn eine
        Rueckfrage erwartet wird - ohne sie liefe der echte Abbau (Ausgabe,
        Playback, MIDI) und zoege den gemeinsamen State herunter."""
        fragen = []

        def _frage(*a, **k):
            fragen.append(a)
            return QMessageBox.StandardButton.Cancel

        ev = QCloseEvent()
        with mock.patch.object(self.mw, "_exit_prompt_suppressed", lambda: False), \
             mock.patch.object(self.mw.QMessageBox, "question", _frage):
            self.win.closeEvent(ev)
        self.assertEqual(1, len(fragen), "Beenden hat nicht nachgefragt")
        self.assertFalse(ev.isAccepted(), "Abbrechen muss das Fenster offen halten")
        self.assertIn("noch nie gespeichert", fragen[0][2])
        return True

    def test_nur_patch_fragt(self):
        self.state.add_fixture(_dimmer(1, 1), undoable=False)
        self.assertTrue(self.win._has_unsaved_changes(),
                        "nie gespeicherte Show mit Patch gilt nicht als ungespeichert")
        self.assertTrue(self._beenden_fragt(), "Beenden fragte bei reinem Patch nicht")

    def test_nur_vc_layout_fragt(self):
        self.win._vc_view._canvas._add_widget("VCButton", QPoint(20, 20))
        self.app.processEvents()
        self.assertTrue(self.win._has_unsaved_changes(),
                        "nie gespeicherte Show mit VC-Bedienelement gilt nicht als ungespeichert")
        self.assertTrue(self._beenden_fragt(), "Beenden fragte bei reinem VC-Layout nicht")

    def test_nur_gruppe_fragt(self):
        from src.core.database.models import FixtureGroup
        with self.state._session() as s:
            s.add(FixtureGroup(name="UI75", cols=4, rows=1, positions_json="{}"))
            s.commit()
        self.assertTrue(self.win._has_unsaved_changes(),
                        "nie gespeicherte Show mit Gruppe gilt nicht als ungespeichert")

    def test_cueliste_fragt_weiterhin(self):
        from src.core.engine.cue_stack import CueStack
        self.state.cue_stacks.append(CueStack("UI75"))
        self.assertTrue(self.win._has_unsaved_changes())

    def test_nur_programmer_ist_bedienung(self):
        with self.state._prog_lock:
            self.state.programmer[1] = {"dimmer": 200}
        self.assertFalse(self.win._has_unsaved_changes(),
                         "Programmer-Werte sind Bedienung, kein Show-Inhalt (wie bei "
                         "einer geladenen Show und laut Anleitung)")


if __name__ == "__main__":
    unittest.main()
