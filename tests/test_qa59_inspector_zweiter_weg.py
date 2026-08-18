"""QA-59: Der VC-Inspector sichert zweifach — geprueft war nur ein Weg.

Der Inspector haelt die Konfiguration eines VC-Buttons auf zwei Wegen fest:

1. **Live** — jede Aenderung wird sofort angewendet
   (``_live()`` in ``VCButton._build_settings``, ``live=True``).
2. **Beim Verlassen** — ``VCInspectorPanel`` ruft ``w._inspector_apply()`` ein
   letztes Mal und setzt einen Undo-Punkt.

**Gemessen beim Abschluss von UXT-02 (12.08.2026):** Weg 1 ist geprueft — ihn
zu entfernen macht vier Tests rot. Weg 2 war **nicht** geprueft: sowohl
``apply = None`` im Panel als auch ``self._inspector_apply = lambda: None`` im
Button liessen **alle zehn** Tests von ``test_vc_inspector_panel.py`` gruen. Er
haette still verschwinden koennen.

Das ist keine akute Luecke, solange Weg 1 traegt — aber genau dafuer ist Weg 2
da: fuer den Fall, dass ein Feld ohne Live-Verdrahtung dazukommt. Diese Datei
prueft beides: dass Weg 1 **lueckenlos** ist, und dass Weg 2 **wirkt**, wenn er
gebraucht wird.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QLineEdit,
                               QSpinBox)

from src.ui.virtualconsole.vc_button import VCButton
from src.ui.virtualconsole.vc_inspector_panel import VCInspectorPanel

_VERFAELSCHT = "\x00QA59-ZERSTOERT\x00"


def _app():
    return QApplication.instance() or QApplication([])


def _formularzeilen(einstellungen):
    """Alle (Pfad, Widget)-Paare des Einstellungsformulars."""
    zeilen = [(f"top/{label}", w) for label, w in einstellungen["top"]]
    for key, _titel, _zu, _prefs, rows in einstellungen["sections"]:
        zeilen += [(f"{key}/{label}", w) for label, w in rows]
    return zeilen


def _aendern(w) -> bool:
    """Aendert das Widget wie ein Benutzer. False = nicht aenderbar."""
    if isinstance(w, QLineEdit):
        w.setText((w.text() or "") + "x")
        return True
    if isinstance(w, QComboBox):
        if w.count() < 2:
            return False            # in einer leeren Show oft nur ein Eintrag
        w.setCurrentIndex((w.currentIndex() + 1) % w.count())
        return True
    if isinstance(w, QCheckBox):
        w.toggle()
        return True
    if isinstance(w, QSpinBox):
        neu = w.value() + 1
        w.setValue(w.minimum() if neu > w.maximum() else neu)
        return True
    return False


class JedesFeldCommittetLiveTest(unittest.TestCase):
    """Weg 1, lueckenlos: KEIN Eingabefeld darf stumm bleiben.

    Geprueft wird die **Wirkung**, nicht die Signalverbindung: vor jeder
    Aenderung wird ``button.caption`` verfaelscht. Ein Live-Commit schreibt
    saemtliche Attribute aus den Widgets zurueck und raeumt die Verfaelschung
    damit weg. Bleibt sie stehen, hat das Feld keinen Live-Weg.

    Das ist der Waechter, den es bisher nicht gab: ein neu hinzugefuegtes Feld,
    dessen ``connect``-Zeile vergessen wurde, faellt hier auf.
    """

    def setUp(self):
        _app()
        self.btn = VCButton()
        self.addCleanup(self.btn.deleteLater)
        self.einstellungen = self.btn._build_settings(self.btn, live=True)

    def test_kein_eingabefeld_bleibt_stumm(self):
        stumm, geprueft, uebersprungen = [], 0, []
        for pfad, w in _formularzeilen(self.einstellungen):
            self.btn.caption = _VERFAELSCHT
            if not _aendern(w):
                uebersprungen.append(f"{type(w).__name__} {pfad}")
                continue
            geprueft += 1
            if self.btn.caption == _VERFAELSCHT:
                stumm.append(f"{type(w).__name__} {pfad}")

        self.assertGreaterEqual(
            geprueft, 12,
            f"Die Messung muss genug Felder erreichen, sonst sagt sie nichts "
            f"(nur {geprueft} geprueft, uebersprungen: {uebersprungen})")
        self.assertEqual(
            [], stumm,
            "Diese Felder loesen KEINEN Live-Commit aus — ihr Wert haengt dann "
            "allein am Verlassen-Pfad des Panels:\n  " + "\n  ".join(stumm))

    def test_die_messung_wuerde_ein_stummes_feld_auch_sehen(self):
        """POSITIVKONTROLLE. Ohne sie koennte ``_aendern`` stillschweigend
        nichts tun und der Test waere gruen, ohne etwas zu unterscheiden."""
        cap = self.einstellungen["top"][0][1]
        self.assertIsInstance(cap, QLineEdit)
        cap.textChanged.disconnect()          # genau eine Live-Verbindung kappen
        self.btn.caption = _VERFAELSCHT
        _aendern(cap)
        self.assertEqual(
            _VERFAELSCHT, self.btn.caption,
            "Nach dem Kappen der Verbindung MUSS die Verfaelschung stehen "
            "bleiben — sonst misst der Test oben nicht den Live-Commit")


class VerlassenRettetEinStummesFeldTest(unittest.TestCase):
    """Weg 2, unter der Bedingung, fuer die es ihn gibt.

    Ein Feld ohne Live-Verdrahtung gibt es heute nicht (s. Test oben) — deshalb
    stellt dieser Test genau diesen Fall her, indem er die Live-Verbindung EINES
    echten Feldes kappt. Damit faehrt er den Weg, den die Absicherung
    verspricht, statt eine Attrappe zu bauen.
    """

    def setUp(self):
        _app()
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        self.canvas = VCCanvas()
        self.addCleanup(self.canvas.deleteLater)
        self.btn = self.canvas._add_widget("VCButton", QPoint(20, 20))
        self.assertIsInstance(self.btn, VCButton)
        self.panel = VCInspectorPanel()
        self.addCleanup(self.panel.deleteLater)

    def test_der_wert_eines_stummen_feldes_ueberlebt_das_verlassen(self):
        self.panel.bind(self.btn)
        koerper = self.panel._scroll.widget()
        self.assertIsNotNone(koerper, "Inspector hat keinen Koerper gebaut")

        feld = koerper.findChild(QLineEdit)
        self.assertIsNotNone(feld, "kein Textfeld im Inspector gefunden")
        feld.textChanged.disconnect()         # ab jetzt ist es ein STUMMES Feld
        feld.setText("Nur ueber Weg 2")

        # Ohne den Verlassen-Apply waere der Wert jetzt verloren.
        self.panel.bind(None)

        self.assertEqual(
            "Nur ueber Weg 2", self.btn.caption,
            "Das Panel muss beim Verlassen ein letztes Mal anwenden — sonst "
            "geht der Wert eines Feldes ohne Live-Verdrahtung verloren. Genau "
            "dafuer gibt es _inspector_apply.")

    def test_ohne_kappen_haelt_der_wert_ohnehin(self):
        """POSITIVKONTROLLE: im Normalfall traegt schon Weg 1. Der Test oben
        misst also den ZWEITEN Weg und nicht bloss ``bind(None)``."""
        self.panel.bind(self.btn)
        koerper = self.panel._scroll.widget()
        feld = koerper.findChild(QLineEdit)
        feld.setText("Ueber Weg 1")
        self.assertEqual(
            "Ueber Weg 1", self.btn.caption,
            "schon vor dem Verlassen muss der Live-Commit gegriffen haben")


if __name__ == "__main__":
    unittest.main()
