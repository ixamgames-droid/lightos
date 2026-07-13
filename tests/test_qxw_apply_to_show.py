"""FIMP-05: QXW-Import wendet geparste Fixtures WIRKLICH auf die Show an.

Bug (Backlog FIMP-05, belegt): `main_window._import_qxw` parste die .qxw-Datei
via `import_qxw()`, zeigte die Zusammenfassung — und VERWARF das Ergebnis. Die
Fixtures/Adressen/Modes landeten NIE in der Patch-/Show-Struktur: der Nutzer
importierte, und es passierte effektiv nichts.

Fix (FIMP-05): `_import_qxw` iteriert `result['fixtures']` und uebernimmt jedes
ueber den regulaeren Patch-Pfad (`AppState.add_fixture` + die kanonische
`show_file._patched_fixture_from_data`-Konvertierung), mit frischen fids.

Dieser Test baut das echte MainWindow (headless/offscreen — wie
test_vc_canvas_clear_on_new_show.py), monkeypatcht den Datei-Dialog auf eine
Temp-.qxw und die Info/Warn-Boxen auf No-Op, ruft `_import_qxw()` und prueft:
die Fixtures stehen danach TATSAECHLICH in `state.get_patched_fixtures()` mit
den QXW-Adressen/Universen/Kanalzahlen (0-basiert -> 1-basiert).
"""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox


def _app():
    return QApplication.instance() or QApplication([])


_QXW = """<?xml version="1.0" encoding="UTF-8"?>
<Workspace>
 <Engine>
  <Fixture>
   <Manufacturer>Generic</Manufacturer>
   <Model>RGB-Par</Model>
   <Mode>3-Channel</Mode>
   <ID>0</ID>
   <Name>Par Links</Name>
   <Universe>0</Universe>
   <Address>10</Address>
   <Channels>3</Channels>
  </Fixture>
  <Fixture>
   <Manufacturer>Generic</Manufacturer>
   <Model>Moving-Head</Model>
   <Mode>16-Channel</Mode>
   <ID>1</ID>
   <Name>MH Rechts</Name>
   <Universe>0</Universe>
   <Address>20</Address>
   <Channels>16</Channels>
  </Fixture>
 </Engine>
</Workspace>
"""


class TestQxwApplyToShow(unittest.TestCase):
    def test_import_qxw_patches_fixtures_into_show(self):
        app = _app()
        from src.ui.main_window import MainWindow

        # Temp-.qxw schreiben; Datei-Dialog + Message-Boxen kapseln.
        fd, qxw_path = tempfile.mkstemp(suffix=".qxw")
        os.close(fd)
        with open(qxw_path, "w", encoding="utf-8") as f:
            f.write(_QXW)

        orig_open = QFileDialog.getOpenFileName
        orig_info = QMessageBox.information
        orig_warn = QMessageBox.warning
        QFileDialog.getOpenFileName = staticmethod(
            lambda *a, **k: (qxw_path, "")
        )
        QMessageBox.information = staticmethod(lambda *a, **k: None)
        QMessageBox.warning = staticmethod(lambda *a, **k: None)

        win = MainWindow()
        try:
            state = win._state
            before = {f.fid for f in state.get_patched_fixtures()}

            win._import_qxw()

            after = state.get_patched_fixtures()
            new = [f for f in after if f.fid not in before]

            # KERN-ASSERT: die geparsten Fixtures landen wirklich in der Show —
            # nicht nur geparst/angezeigt/verworfen.
            self.assertEqual(
                len(new), 2,
                "QXW-Import hat die geparsten Fixtures nicht in die Patch-"
                "Struktur uebernommen (FIMP-05)")

            by_label = {f.label: f for f in new}
            self.assertIn("Par Links", by_label)
            self.assertIn("MH Rechts", by_label)

            par = by_label["Par Links"]
            # Universe 0 -> 1, Address 10 -> 11 (QLC+ ist 0-basiert), 3 Kanaele.
            self.assertEqual(par.universe, 1)
            self.assertEqual(par.address, 11)
            self.assertEqual(par.channel_count, 3)
            self.assertEqual(par.mode_name, "3-Channel")

            mh = by_label["MH Rechts"]
            self.assertEqual(mh.address, 21)
            self.assertEqual(mh.channel_count, 16)

            # Frische, kollisionsfreie fids (QLC+ liefert 0/1).
            self.assertEqual(len({f.fid for f in new}), 2)
        finally:
            win.close()
            app.processEvents()
            QFileDialog.getOpenFileName = orig_open
            QMessageBox.information = orig_info
            QMessageBox.warning = orig_warn
            try:
                os.remove(qxw_path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
