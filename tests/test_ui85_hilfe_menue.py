"""UI-85: Hilfe in der App — Anleitungen, Tastenkuerzel, Ordner, echtes „Ueber“.

Vorher bestand das Hilfe-Menue aus „Über LightOS“ (mit fest verdrahtetem
„v1.0“) und dem Diagnosepaket. Wer die Anleitungen suchte, musste das Repo
kennen; die Tastenkuerzel standen nirgends; der Datenordner liess sich nur ueber
den Dateimanager finden.

Geprueft wird am echten Hauptfenster (Bau ist teuer -> eine Klasse,
``setUpClass``). ``QDesktopServices.openUrl`` ist IMMER gemockt, der Datenordner
zeigt auf ein Temp-Verzeichnis — der Test oeffnet nichts und legt nichts im
echten Nutzerordner an.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from src.core.show import show_file as SF

from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _app():
    return QApplication.instance() or QApplication([])


def _app_version() -> str:
    with open(os.path.join(_REPO, "main.py"), encoding="utf-8") as f:
        m = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', f.read(), re.M)
    assert m, "APP_VERSION nicht in main.py gefunden"
    return m.group(1)


class HilfeMenueTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        from src.ui import hilfe
        from src.ui import main_window as mw
        cls.hilfe = hilfe
        cls.tmp = tempfile.mkdtemp(prefix="lightos_ui85_")
        cls.daten = os.path.join(cls.tmp, "LightOS")
        SF.reset_show()
        cls.win = mw.MainWindow()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.win.deleteLater()
        except Exception:
            pass
        destroy_all_top_level_widgets()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        # Datenordner umbiegen (nie den echten anfassen) + openUrl abfangen.
        p1 = mock.patch.object(self.hilfe, "app_data_dir", return_value=self.daten)
        p2 = mock.patch.object(self.hilfe.QDesktopServices, "openUrl",
                               return_value=True)
        p1.start()
        self.open_url = p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)

    # ── Helfer ───────────────────────────────────────────────────────────────

    def _hilfe_menue(self):
        # ueber findChildren, nicht ``QAction.menu()``: dessen Wrapper ueberlebt
        # in PySide6 den Aufruf nicht zuverlaessig („already deleted“).
        for menue in self.win.menuBar().findChildren(QMenu):
            if menue.title().replace("&", "") == "Hilfe":
                return menue
        self.fail("Menue „Hilfe“ fehlt")

    def _aktion(self, text: str) -> QAction:
        for act in self._hilfe_menue().actions():
            if act.text().replace("&", "") == text:
                return act
        self.fail(f"Hilfe-Menue hat keinen Eintrag „{text}“: "
                  f"{[a.text() for a in self._hilfe_menue().actions()]}")

    def _geoeffnet(self) -> QUrl:
        self.assertEqual(self.open_url.call_count, 1, "openUrl genau einmal")
        return self.open_url.call_args[0][0]

    # ── (1) Menue-Eintraege ──────────────────────────────────────────────────

    def test_menue_hat_alle_eintraege_in_sinnvoller_reihenfolge(self):
        texte = [a.text().replace("&", "") for a in self._hilfe_menue().actions()
                 if not a.isSeparator()]
        for t in ("Erste Schritte", "Anleitungen öffnen", "Tastenkürzel…",
                  "Datenordner öffnen", "Show-Ordner öffnen",
                  "Diagnosepaket speichern…", "Über LightOS"):
            self.assertIn(t, texte)
        # Diagnosepaket steht bei den Ordnern (Fehlersuche), „Ueber“ ganz unten.
        self.assertLess(texte.index("Datenordner öffnen"),
                        texte.index("Diagnosepaket speichern…"))
        self.assertEqual(texte[-1], "Über LightOS")
        self.assertLess(texte.index("Erste Schritte"),
                        texte.index("Datenordner öffnen"))

    def test_anleitungen_oeffnet_lokale_doku_im_quellbetrieb(self):
        self._aktion("Anleitungen öffnen").trigger()
        url = self._geoeffnet()
        self.assertTrue(url.isLocalFile(), url.toString())
        self.assertEqual(os.path.normpath(url.toLocalFile()),
                         os.path.join(_REPO, "docs", "ANLEITUNGEN.md"))

    def test_erste_schritte_oeffnet_die_anleitung(self):
        self._aktion("Erste Schritte").trigger()
        url = self._geoeffnet()
        self.assertTrue(url.isLocalFile(), url.toString())
        self.assertEqual(
            os.path.normpath(url.toLocalFile()),
            os.path.join(_REPO, "docs", "anleitung_erste_schritte", "ANLEITUNG.md"))

    def test_ohne_mitgelieferte_doku_geht_es_zur_github_seite(self):
        """Im Setup-Build liegt ``docs/`` nicht im Bundle -> oeffentlicher Link."""
        leer = os.path.join(self.tmp, "bundle_ohne_docs")
        os.makedirs(leer, exist_ok=True)
        with mock.patch.object(self.hilfe, "programm_dir", return_value=leer):
            self._aktion("Anleitungen öffnen").trigger()
            self._aktion("Erste Schritte").trigger()
        urls = [c[0][0].toString() for c in self.open_url.call_args_list]
        basis = "https://github.com/ixamgames-droid/lightos/blob/main/docs/"
        self.assertEqual(urls, [
            basis + "ANLEITUNGEN.md",
            basis + "anleitung_erste_schritte/ANLEITUNG.md"])

    def test_bundle_liefert_docs_wirklich_nicht_mit(self):
        """Haelt die Annahme hinter dem GitHub-Rueckfall fest: kommt ``docs``
        eines Tages ins Bundle, greift ohnehin der lokale Zweig — dieser Test
        erinnert dann daran, die Aussage in der Doku anzupassen."""
        sys.path.insert(0, os.path.join(_REPO, "packaging", "windows"))
        try:
            import bundle_inhalt
        finally:
            sys.path.pop(0)
        self.assertFalse(any(o == "docs" or o.startswith("docs/")
                             for o in bundle_inhalt.DATENORDNER
                             + bundle_inhalt.EINZELDATEIEN))

    # ── (3) Ordner ───────────────────────────────────────────────────────────

    def test_datenordner_oeffnen(self):
        self._aktion("Datenordner öffnen").trigger()
        url = self._geoeffnet()
        self.assertEqual(os.path.normpath(url.toLocalFile()), self.daten)
        self.assertTrue(os.path.isdir(self.daten))

    def test_show_ordner_oeffnen(self):
        self._aktion("Show-Ordner öffnen").trigger()
        url = self._geoeffnet()
        ziel = os.path.join(self.daten, "shows")
        self.assertEqual(os.path.normpath(url.toLocalFile()), ziel)
        self.assertTrue(os.path.isdir(ziel))

    def test_diagnosepaket_eintrag_fragt_erst_nach(self):
        """Der Menue-Klick darf ``triggered(checked)`` nicht als ``ziel``
        durchreichen — sonst entfiele die Rueckfrage samt Zieldialog."""
        from src.ui import main_window as mw
        with mock.patch.object(
                mw.QMessageBox, "information",
                return_value=mw.QMessageBox.StandardButton.Cancel) as frage, \
             mock.patch("src.core.diagnose_log.erstelle_diagnosepaket") as bau:
            self._aktion("Diagnosepaket speichern…").trigger()
        self.assertEqual(frage.call_count, 1)
        bau.assert_not_called()

    # ── (1) Tastenkuerzel ────────────────────────────────────────────────────

    def test_kuerzel_werden_aus_den_aktionen_gesammelt(self):
        eintraege = self.hilfe.sammle_tastenkuerzel([self.win])
        tasten = {e.tasten for e in eintraege}
        self.assertIn("Strg+S", tasten)
        for i in range(1, 9):
            self.assertIn(f"Strg+{i}", tasten)
        nach_taste = {e.tasten: e for e in eintraege}
        self.assertEqual(nach_taste["Strg+S"].bereich, "Datei")
        self.assertEqual(nach_taste["Strg+S"].aktion, "Show speichern")
        self.assertEqual(nach_taste["F5"].bereich, "Ansicht")
        self.assertIn("Leertaste", tasten)           # GO
        self.assertIn("Umschalt+Leertaste", tasten)  # BACK
        # Mnemonic-„&“ ist entfernt, ein echtes „&&“ bleibt als „&“ stehen.
        self.assertEqual(nach_taste["Strg+Umschalt+R"].aktion,
                         "Show prüfen & reparieren")
        self.assertFalse(any("&&" in e.aktion or "&" in e.bereich
                             for e in eintraege))

    def test_sammlung_ist_nicht_von_hand_gepflegt(self):
        """Ein NEUES Kuerzel taucht ohne weitere Pflege auf — QAction wie
        QShortcut; Aktionen ohne Kuerzel bleiben draussen."""
        w = QWidget()
        self.addCleanup(w.deleteLater)
        w.setWindowTitle("Probe")
        a = QAction("Probe-Aktion", w)
        a.setShortcut("Ctrl+Alt+F9")
        w.addAction(a)
        w.addAction(QAction("Ohne Kürzel", w))
        sc = QShortcut(QKeySequence("Ctrl+Alt+F10"), w)
        sc.setWhatsThis("Probe-Shortcut")
        eintraege = self.hilfe.sammle_tastenkuerzel([w])
        self.assertEqual(
            sorted((e.tasten, e.aktion, e.bereich) for e in eintraege),
            [("Strg+Alt+F10", "Probe-Shortcut", "Probe"),
             ("Strg+Alt+F9", "Probe-Aktion", "Probe")])

    def test_dialog_listet_die_kuerzel(self):
        dlg = self.win._tastenkuerzel_dialog()
        self.addCleanup(dlg.deleteLater)
        tab = dlg.tabelle
        zellen = {tab.item(r, 0).text() for r in range(tab.rowCount())}
        self.assertIn("Strg+S", zellen)
        for i in range(1, 9):
            self.assertIn(f"Strg+{i}", zellen)
        self.assertEqual(tab.columnCount(), 3)
        zeilen = {tuple(tab.item(r, c).text() for c in range(3))
                  for r in range(tab.rowCount())}
        # Sektionswechsel nennt die Sektion beim Namen …
        erste = self.win._section_btns[0]._full_text
        self.assertIn(("Strg+1", f"Sektion 1: {erste}", "Allgemein"), zeilen)
        # … und Kuerzel aus einer Ansicht stehen unter ihrer Sektion statt
        # unter einem Klassennamen.
        self.assertFalse([z for z in zeilen if z[2].endswith("View")
                          or z[2].startswith("Q")], zeilen)
        self.assertTrue(any(z[2].startswith("Sektion ") for z in zeilen))
        # Der Menue-Eintrag oeffnet genau diesen Dialog (ohne exec im Test).
        with mock.patch.object(self.hilfe.TastenkuerzelDialog, "exec",
                               return_value=0) as ex:
            self._aktion("Tastenkürzel…").trigger()
        self.assertEqual(ex.call_count, 1)

    # ── (2) Ueber LightOS ────────────────────────────────────────────────────

    def test_ueber_zeigt_version_build_datenordner_und_doku(self):
        text = self.win._about_text()
        self.assertIn(f"LightOS {_app_version()}", text)
        self.assertNotIn("v1.0<", text)
        self.assertIn("Quellbetrieb", text)
        self.assertIn(self.daten, text)
        self.assertIn(self.hilfe.DOKU_URL, text)
        with mock.patch.object(self.hilfe, "ist_gefroren", return_value=True):
            self.assertIn("Setup-Build", self.win._about_text())
            self.assertNotIn("Quellbetrieb", self.win._about_text())

    def test_ueber_dialog_bekommt_diesen_text(self):
        from src.ui import main_window as mw
        with mock.patch.object(mw.QMessageBox, "about") as about:
            self._aktion("Über LightOS").trigger()
        self.assertEqual(about.call_count, 1)
        self.assertIn(_app_version(), about.call_args[0][2])


if __name__ == "__main__":
    unittest.main()
