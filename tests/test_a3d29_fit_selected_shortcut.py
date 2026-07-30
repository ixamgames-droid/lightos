"""A3D-29: Die F-Taste im Visualizer hatte zwei Herren — und der falsche gewann.

Das Kamera-Menü beschriftet den Eintrag ausdrücklich mit „⛶ Fit Auswahl  (F)",
und `interaction/touch.js` hat dafür einen window-keydown-Handler. Erreicht hat
ihn die Taste trotzdem nie: `visualizer_window._setup_shortcuts` registriert
`QShortcut(QKeySequence("F"), self)` → Sprung auf den Fixtures-Tab. Der hängt
mit **WindowShortcut**-Kontext am Top-Level-Fenster, und der
ShortcutOverride-Zweig reicht Tasten nur an echte Text-Widgets weiter
(`_should_pass_key_to_text`), nicht an die WebEngine-Canvas.

Aufgelöst wird der Konflikt **nach dem Fokus**, nicht durch Wegnehmen: liegt er
auf der 3D-Szene, heißt F „Fit Auswahl"; sonst bleibt es der Tab-Sprung. Beide
dokumentierten Bedeutungen bleiben damit erreichbar.
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout   # noqa: E402

import src.ui.visualizer.visualizer_window as VW                   # noqa: E402

_app = QApplication.instance() or QApplication([])


class FokusErkennungTest(unittest.TestCase):
    """``_focus_is_in_3d`` — der eigentliche Knackpunkt."""

    def test_fokus_im_kind_widget_zaehlt_als_3d(self):
        """★ QWebEngineView hält den Fokus in einem internen Kind (dem
        Render-Delegate) — ``view.hasFocus()`` allein wäre `False` und die
        Weiche würde in genau dem Fall falsch abbiegen, für den sie da ist."""
        host = QWidget()
        lay = QVBoxLayout(host)
        view = QWidget()            # steht hier für die QWebEngineView
        lay.addWidget(view)
        kind = QWidget(view)        # der interne Render-Delegate
        host.show()
        kind.setFocus()
        _app.processEvents()
        self.assertIs(QApplication.focusWidget(), kind)
        fake = SimpleNamespace(_view=view)
        self.assertTrue(VW.VisualizerWindow._focus_is_in_3d(fake))
        host.close()

    def test_fokus_woanders_ist_nicht_3d(self):
        host = QWidget()
        lay = QVBoxLayout(host)
        view = QWidget()
        anderes = QWidget()
        lay.addWidget(view)
        lay.addWidget(anderes)
        host.show()
        anderes.setFocus()
        _app.processEvents()
        fake = SimpleNamespace(_view=view)
        self.assertFalse(VW.VisualizerWindow._focus_is_in_3d(fake))
        host.close()

    def test_ohne_view_kein_absturz(self):
        self.assertFalse(VW.VisualizerWindow._focus_is_in_3d(SimpleNamespace()))


class TastenWeicheTest(unittest.TestCase):
    def _fake(self, im_3d: bool):
        f = SimpleNamespace(_tabs=MagicMock(), _on_fit_selected=MagicMock())
        f._focus_is_in_3d = lambda: im_3d
        return f

    def test_f_in_der_szene_ist_fit_auswahl(self):
        f = self._fake(True)
        VW.VisualizerWindow._on_key_f(f)
        f._on_fit_selected.assert_called_once_with()
        f._tabs.setCurrentIndex.assert_not_called()

    def test_f_ausserhalb_bleibt_der_tab_sprung(self):
        """Bestandsverhalten (T-VIZ-10) — nicht weggenommen, nur eingegrenzt."""
        f = self._fake(False)
        VW.VisualizerWindow._on_key_f(f)
        f._tabs.setCurrentIndex.assert_called_once_with(0)
        f._on_fit_selected.assert_not_called()


class FitPfadTest(unittest.TestCase):
    def test_fit_selected_reist_ueber_den_bestehenden_kanal(self):
        """Kein neuer Bridge-Kanal: dieselbe Route wie der Menue-Eintrag."""
        f = SimpleNamespace(_bridge=MagicMock())
        VW.VisualizerWindow._on_fit_selected(f)
        f._bridge.push_camera_preset.assert_called_once_with("fit_selected")


if __name__ == "__main__":
    unittest.main()
