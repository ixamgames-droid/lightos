"""UI-100: einheitliche deutsche Begriffe in „Ausgabe konfigurieren“ und im
Fixture-Editor.

Befund (Sichtpruefung 19.10.2026): der Ausgabe-Dialog mischte „Universe:“,
„Eingehendes Universe“, „Merge in Universe“, „+ Universe hinzufügen“, die
Spalten „Output“/„Ext-Universe“, den Typ „Disabled“ und den Reiter „DMX Input“
mit deutschem Text; der Fixture-Editor sagte „Modes“, „Mode-Name“, „+ Channel“,
„+ Mode“ und hiess „Fixture Editor“, waehrend der Generator „Modi & Kanäle“,
„Modus-Name“, „+ Kanal“, „+ Modus“ sagt. Die Erklaerzeile im Reiter Universen
wurde bei schmalem Dialog hart abgeschnitten.

Festgehalten wird:
  * die neuen Begriffe stehen wirklich im Dialog (an den Widgets gemessen),
  * die alten englischen Woerter kommen in keinem sichtbaren Text dieser beiden
    Dialoge mehr vor (Gegenprobe: der Pruefer schlaegt bei den alten Texten an),
  * „Aus“ ist NUR Anzeige — gespeichert wird weiter ``"Disabled"``,
  * die Erklaerzeile bricht um.

Bewusst NICHT geaendert (Entscheidung Projektinhaber 20.10.2026): die
Programmer-Reiter „Intensity“/„Color“ und der E/A-Reiter „Output“ bleiben als
Fachbegriffe. Statusmeldungen mit „Universe <n>“ (geteilt mit DMX-Monitor und
Adapter-Zuordnung) sind nicht Teil dieses Items.
"""
import json
import os
import re
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")

from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox,  # noqa: E402
                               QGroupBox, QLabel, QTableWidget, QTabWidget,
                               QWidget, QPushButton, QVBoxLayout)

import src.ui.widgets.output_config as oc  # noqa: E402

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


#: Alte englische Woerter, die in den beiden Dialogen nicht mehr sichtbar sein
#: duerfen. Wortgrenzen, damit „Universum“/„Universen“ nicht anschlagen.
VERBOTEN_AUSGABE = re.compile(
    r"\bUniverse\b|\bOutput\b|\bDisabled\b|\bInput\b|\bMerge in\b|Ext-Universe")
VERBOTEN_EDITOR = re.compile(r"\bChannels?\b|\bModes?\b|Fixture Editor")


def sichtbare_texte(wurzel: QWidget, ohne=()) -> list[str]:
    """Alle Beschriftungen, die ein Nutzer sieht: Fenstertitel, Labels, Knoepfe,
    Kaesten, Reiter, Tabellenkoepfe und Combo-Eintraege. ``ohne`` = Widgets, deren
    Text Nutzerdaten ist (z. B. Statuszeilen mit Laufzeitmeldungen)."""
    texte = [wurzel.windowTitle()]
    for w in wurzel.findChildren(QWidget):
        if w in ohne:
            continue
        if isinstance(w, QLabel):
            texte.append(w.text())
        elif isinstance(w, QAbstractButton):
            texte.append(w.text())
        elif isinstance(w, QGroupBox):
            texte.append(w.title())
        elif isinstance(w, QTabWidget):
            texte += [w.tabText(i) for i in range(w.count())]
        elif isinstance(w, QTableWidget):
            for c in range(w.columnCount()):
                h = w.horizontalHeaderItem(c)
                if h is not None:
                    texte += [h.text(), h.toolTip()]
        elif isinstance(w, QComboBox):
            texte += [w.itemText(i) for i in range(w.count())]
        texte.append(w.toolTip())
    return [t for t in texte if t]


def treffer(texte, muster) -> list[str]:
    return [t for t in texte if muster.search(t)]


class PrueferGegenprobeTest(unittest.TestCase):
    """Der Pruefer selbst: er muss die alten Texte finden, sonst beweist der
    gruene Lauf unten nichts."""

    def setUp(self):
        QApplication.instance() or QApplication([])

    def test_alte_texte_schlagen_an(self):
        w = QWidget()
        self.addCleanup(w.deleteLater)
        lay = QVBoxLayout(w)
        for t in ("Universe:", "+ Universe hinzufügen", "DMX Input",
                  "Merge in Universe:"):
            lay.addWidget(QLabel(t))
        tabelle = QTableWidget(0, 2)
        tabelle.setHorizontalHeaderLabels(["Output", "Ext-Universe"])
        lay.addWidget(tabelle)
        combo = QComboBox()
        combo.addItem("Disabled")
        lay.addWidget(combo)
        self.assertEqual(len(treffer(sichtbare_texte(w), VERBOTEN_AUSGABE)), 7)

        e = QWidget()
        self.addCleanup(e.deleteLater)
        e.setWindowTitle("Fixture Editor")
        lay = QVBoxLayout(e)
        for t in ("+ Channel", "- Mode", "Mode-Name:"):
            lay.addWidget(QPushButton(t))
        lay.addWidget(QGroupBox("Modes"))
        self.assertEqual(len(treffer(sichtbare_texte(e), VERBOTEN_EDITOR)), 5)

    def test_neue_texte_schlagen_nicht_an(self):
        for t in ("Universum:", "Universen", "Ausgang", "Ext. Universum",
                  "Aus", "DMX-Eingang", "Mischen in Universum:"):
            self.assertIsNone(VERBOTEN_AUSGABE.search(t), t)
        for t in ("+ Kanal", "- Modus", "Modus-Name:", "Modi && Kanäle",
                  "Fixture-Editor", "Kanäle"):
            self.assertIsNone(VERBOTEN_EDITOR.search(t), t)


class AusgabeDialogTest(unittest.TestCase):

    def setUp(self):
        QApplication.instance() or QApplication([])
        fd, self._tmp = tempfile.mkstemp(suffix="_universes.json")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(self._tmp) and os.remove(self._tmp))
        alt = oc._UNIV_CONFIG_PATH
        oc._UNIV_CONFIG_PATH = self._tmp
        self.addCleanup(setattr, oc, "_UNIV_CONFIG_PATH", alt)
        oc._save_universe_config([
            {"num": 1, "name": "Main", "output": "Disabled", "patch": ""},
            {"num": 2, "name": "Netz", "output": "ArtNet", "patch": ""},
        ])
        from src.core.app_state import get_state
        state = get_state()
        om = state.output_manager
        for name in ("add_enttec", "add_sacn", "add_artnet", "remove_output"):
            p = mock.patch.object(om, name, lambda *a, **k: None)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(state, "apply_output_config", lambda *a, **k: None)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(oc, "QMessageBox")
        p.start()
        self.addCleanup(p.stop)
        self.dlg = oc.OutputConfigDialog()
        self.addCleanup(self.dlg.deleteLater)

    def _statuszeilen(self):
        return [w for n, w in vars(self.dlg).items()
                if n.startswith("_lbl_") and n.endswith("_status")]

    def test_neue_begriffe_stehen_im_dialog(self):
        texte = sichtbare_texte(self.dlg)
        for t in ("Universum:", "Eingehendes Universum:", "Mischen in Universum:",
                  "+ Universum hinzufügen", "Ausgang", "Ext. Universum", "Aus",
                  "DMX-Eingang", "Art-Net-Eingang", "sACN-Eingang",
                  "Art-Net-Eingang aktivieren", "sACN-Eingang aktivieren"):
            self.assertIn(t, texte)

    def test_keine_alten_englischen_woerter(self):
        # Statuszeilen tragen Laufzeitmeldungen (eigenes Thema, s. Modulkopf).
        texte = sichtbare_texte(self.dlg, ohne=self._statuszeilen())
        self.assertEqual(treffer(texte, VERBOTEN_AUSGABE), [])

    def test_aus_ist_nur_anzeige_gespeichert_wird_disabled(self):
        t = self.dlg._univ_table
        combo = t.cellWidget(0, 2)
        self.assertEqual(combo.currentText(), "Aus")
        self.assertEqual(oc.ausgabe_typ_wert(combo), "Disabled")
        self.assertEqual(oc.ausgabe_typ_wert(t.cellWidget(1, 2)), "ArtNet")
        self.dlg._univ_add()
        neu = t.cellWidget(t.rowCount() - 1, 2)
        self.assertEqual((neu.currentText(), oc.ausgabe_typ_wert(neu)),
                         ("Aus", "Disabled"))
        self.dlg._univ_save()
        with open(self._tmp, encoding="utf-8") as fh:
            gespeichert = [r["output"] for r in json.load(fh)]
        self.assertEqual(gespeichert, ["Disabled", "ArtNet", "Disabled"])
        self.assertNotIn("Aus", gespeichert)

    def test_unbekannter_typ_faellt_wie_bisher_auf_den_ersten_eintrag(self):
        combo = oc._ausgabe_typ_combo("Quatsch")
        self.assertEqual(oc.ausgabe_typ_wert(combo), "Disabled")
        combo.deleteLater()

    def test_erklaerzeile_bricht_um(self):
        lbl = self.dlg._lbl_univ_hinweis
        self.assertTrue(lbl.wordWrap())
        self.assertIn("Pro Universum:", lbl.text())
        self.assertNotIn("\n", lbl.text())
        zeile = lbl.fontMetrics().height()
        self.assertGreater(lbl.heightForWidth(320), 2 * zeile,
                           "schmal: mehrere Zeilen statt abgeschnitten")
        # Gegenprobe: ohne Umbruch bliebe es bei EINER Zeile (= abgeschnitten).
        lbl.setWordWrap(False)
        self.assertLess(lbl.heightForWidth(320), 2 * zeile)
        lbl.setWordWrap(True)


class FixtureEditorTest(unittest.TestCase):

    def setUp(self):
        QApplication.instance() or QApplication([])
        from src.ui.widgets import fixture_editor as ed
        self.ed = ed
        self.dlg = ed.FixtureEditorDialog()
        self.addCleanup(self.dlg.deleteLater)

    def test_begriffe_wie_im_generator(self):
        texte = sichtbare_texte(self.dlg)
        for t in ("Fixture-Editor", "Modi && Kanäle", "Modus-Name:", "+ Kanal",
                  "- Kanal", "+ Modus", "- Modus", "Modus umbenennen"):
            self.assertIn(t, texte)

    def test_keine_alten_englischen_woerter(self):
        self.assertEqual(treffer(sichtbare_texte(self.dlg), VERBOTEN_EDITOR), [])

    def test_generator_nutzt_dieselben_knoepfe(self):
        """Die Editor-Begriffe sind die des Generators — am Quelltext des
        Generators gemessen, damit beide nicht wieder auseinanderlaufen."""
        import pathlib
        gen = (pathlib.Path(__file__).resolve().parents[1] / "src" / "ui"
               / "widgets" / "fixture_generator.py").read_text(encoding="utf-8")
        for t in ("Modi && Kanäle", "Modus-Name:", "+ Kanal", "- Kanal",
                  "+ Modus", "- Modus", "Modus umbenennen"):
            self.assertIn(f'"{t}"', gen, t)

    def test_neue_modi_und_kanaele_heissen_deutsch(self):
        tab = self.dlg._add_mode()
        self.assertEqual(tab.mode_name, "Modus 1")
        tab._add_channel()
        self.assertEqual(tab.channels[-1]["name"], "Kanal 1")


if __name__ == "__main__":
    unittest.main()
