"""QA-23: MainWindow-Bau darf headless NIE ein modales Recovery-Prompt oeffnen.

Baseline-Bruch (gegen origin/main 1467cae verifiziert): `_check_autosave_recovery`
(main_window.py, via `QTimer.singleShot(500, ...)` im Konstruktor) oeffnete ein
MODALES `QMessageBox.question`, SOBALD auf dem Rechner eine echte
`%APPDATA%/LightOS/auto_save.lshow` neuer als alle Recents lag. Unter
`QT_QPA_PLATFORM=offscreen` beantwortet das niemand -> die einzigen zwei Tests,
die `MainWindow()` bauen (test_ui_polish_audit.py,
test_vc_canvas_clear_on_new_show.py), liefen in den pytest-Timeout — abhaengig
vom Maschinenzustand AUSSERHALB des Repos.

Fix (QA-23): `main_window._recovery_prompt_suppressed()` —
`LIGHTOS_NO_RECOVERY_PROMPT`-Env (setzt conftest.py) ODER offscreen-Platform.
Guard VOR jedem Dateizugriff im Recovery-Check + der singleShot wird gar nicht
erst geplant. Diese Datei nagelt beides fest:

  - Headless blockt NIE (Test A) — auch wenn die Trigger-Bedingung
    (Autosave-Datei existiert, keine neuere Recent) hermetisch hergestellt ist.
  - Die LIVE-Entscheidungslogik bleibt unveraendert (Tests B/C): ohne Suppress
    wird exakt einmal gefragt; Yes stellt die Autosave-Show wieder her, No nicht.

WICHTIG (Auflage): `_autosave_path` ist in ALLEN Tests strikt auf eine
Temp-Datei gemonkeypatcht (Assert in setUpClass) — die ECHTE
`%APPDATA%/LightOS/auto_save.lshow` des Nutzers wird von dieser Datei NIEMALS
gelesen, geschrieben oder geloescht (der App-Guard returnt zudem VOR jedem
Dateizugriff). `_load_recent_files` ist ebenso gepatcht, damit der Testausgang
nicht von der echten recent.json abhaengt.
"""
import os
import tempfile
import unittest
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox


def _app():
    return QApplication.instance() or QApplication([])


class _FakeMessageBox:
    """Ersetzt `QMessageBox` NUR im main_window-MODUL-Namespace (kein Patch an
    der Shiboken-Klasse, keine Nebenwirkung auf andere Module). Zeichnet jeden
    question()-Aufruf auf und antwortet ohne Event-Loop -> nie ein echtes Modal.
    `StandardButton` zeigt auf die ECHTE Enum, damit die Vergleiche im
    App-Code (`reply == QMessageBox.StandardButton.Yes`) unveraendert stimmen."""
    StandardButton = QMessageBox.StandardButton

    calls: list = []          # [(title, text), ...]
    answer = QMessageBox.StandardButton.No

    @classmethod
    def reset(cls, answer):
        cls.calls = []
        cls.answer = answer

    @classmethod
    def question(cls, _parent, title, text, *_args, **_kwargs):
        cls.calls.append((str(title), str(text)))
        return cls.answer


class TestAutosaveRecoveryHeadless(unittest.TestCase):
    """EIN MainWindow fuer alle drei Tests (Bau ist teuer; Muster wie
    test_ui_polish_audit). Die Tests teilen KEINEN veraenderlichen Zustand:
    jeder patcht sein Setup selbst und restauriert im finally."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

        # Hermetische Autosave-Datei in Temp — mtime=jetzt (neuer als alles).
        cls.tmp_autosave = os.path.join(
            tempfile.gettempdir(), f"qa23_auto_save_{uuid.uuid4().hex}.lshow")
        with open(cls.tmp_autosave, "wb") as f:
            f.write(b"qa23 dummy autosave")

        # AUFLAGE: nie den echten %APPDATA%-Pfad anfassen — hart zusichern.
        real_appdata_dir = os.path.normcase(os.path.abspath(os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS")))
        tmp_norm = os.path.normcase(os.path.abspath(cls.tmp_autosave))
        assert not tmp_norm.startswith(real_appdata_dir + os.sep), \
            "Regressionstest darf NIE auf %APPDATA%/LightOS zeigen (QA-23-Auflage)"
        assert tmp_norm.startswith(
            os.path.normcase(os.path.abspath(tempfile.gettempdir())) + os.sep)

        # Fenster-Bau mit AKTIVEM Suppress (conftest-Env + offscreen sind der
        # Normalfall der Suite): Guard #2 plant den Recovery-singleShot gar
        # nicht erst -> kein haengender 500ms-Timer, der nach Patch-Restore
        # mit echten Pfaden feuern koennte.
        from src.ui import main_window as MW
        cls.MW = MW
        assert MW._recovery_prompt_suppressed(), \
            "Suite-Umgebung muss suppressed sein (conftest/offscreen)"
        cls.win = MW.MainWindow()
        # Defense-in-Depth ab der ersten Sekunde: SOLLTE irgendetwas doch den
        # Autosave-Pfad ziehen (z. B. der >=60s-Autosave-Timer bei extrem
        # langsamem Lauf), landet es in Temp — nie in Davids echter Datei.
        cls.win._autosave_path = lambda: cls.tmp_autosave

        cls.app.processEvents()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.win.close()
            cls.win.deleteLater()
        except Exception:
            pass
        cls.app.processEvents()
        from src.core.show.show_file import reset_show
        reset_show()
        cls.app.processEvents()
        try:
            os.remove(cls.tmp_autosave)
        except OSError:
            pass

    # ── Helper: Trigger-Bedingung hermetisch stellen + sauber restaurieren ──

    def _patched_recovery_call(self, suppressed, answer):
        """Ruft `_check_autosave_recovery()` mit hergestellter Trigger-Bedingung
        (Temp-Autosave existiert, KEINE Recents) und gibt die aufgezeichneten
        question()-Aufrufe + _open_show_path-Aufrufe zurueck."""
        MW = self.MW
        orig_recents = MW._load_recent_files
        orig_suppress = MW._recovery_prompt_suppressed
        orig_msgbox = MW.QMessageBox
        opened = []
        _FakeMessageBox.reset(answer)
        try:
            MW._load_recent_files = lambda: []
            if not suppressed:
                MW._recovery_prompt_suppressed = lambda: False
            MW.QMessageBox = _FakeMessageBox
            self.win._open_show_path = lambda p: opened.append(p)
            self.win._check_autosave_recovery()
            self.app.processEvents()
        finally:
            MW._load_recent_files = orig_recents
            MW._recovery_prompt_suppressed = orig_suppress
            MW.QMessageBox = orig_msgbox
            try:
                del self.win._open_show_path
            except AttributeError:
                pass
        recovery_calls = [c for c in _FakeMessageBox.calls
                          if "Wiederherstellung" in c[0]]
        return recovery_calls, opened

    # ── A: headless blockt NIE ────────────────────────────────────────────────

    def test_headless_build_never_blocks_on_recovery_prompt(self):
        """Trigger-Bedingung steht (Datei da, keine Recents) — trotzdem darf
        suppressed NIE gefragt werden. Faellt das App-Gate, zeichnet der
        Fake-Recorder den Aufruf auf -> Test rot (statt Suite-Haenger)."""
        self.assertTrue(os.path.exists(self.tmp_autosave))
        recovery_calls, opened = self._patched_recovery_call(
            suppressed=True, answer=QMessageBox.StandardButton.Yes)
        self.assertEqual(
            recovery_calls, [],
            "Headless/suppressed darf das Recovery-Prompt NIE erscheinen (QA-23)")
        self.assertEqual(opened, [])
        # Und app-weit haengt kein Modal (weder aus dem Bau noch aus dem Check).
        self.assertIsNone(
            self.app.activeModalWidget(),
            "MainWindow-Bau/Recovery-Check hat headless ein Modal hinterlassen")

    # ── B/C: Live-Entscheidungslogik unveraendert ────────────────────────────

    def test_live_logic_still_asks_once_when_not_suppressed(self):
        """Ohne Suppress (echte App) wird EXAKT einmal gefragt — das Gate ist
        der einzige Unterdruecker, die Entscheidungslogik ist unangetastet.
        Antwort No -> keine Wiederherstellung."""
        recovery_calls, opened = self._patched_recovery_call(
            suppressed=False, answer=QMessageBox.StandardButton.No)
        self.assertEqual(
            len(recovery_calls), 1,
            f"Live-Pfad muss genau einmal fragen, fragte {len(recovery_calls)}x")
        self.assertIn("Auto-Save Wiederherstellung", recovery_calls[0][0])
        self.assertEqual(opened, [], "Antwort 'No' darf NICHT wiederherstellen")

    def test_live_yes_restores_the_autosave_show(self):
        """Antwort Yes -> `_open_show_path` wird genau einmal mit dem
        Autosave-Pfad gerufen (Recorder, kein echtes Oeffnen) — das
        Live-Recovery-Feature nach App-Absturz bleibt funktionsfaehig."""
        recovery_calls, opened = self._patched_recovery_call(
            suppressed=False, answer=QMessageBox.StandardButton.Yes)
        self.assertEqual(len(recovery_calls), 1)
        self.assertEqual(
            opened, [self.tmp_autosave],
            "Antwort 'Yes' muss genau die Autosave-Show wiederherstellen")


if __name__ == "__main__":
    unittest.main()
