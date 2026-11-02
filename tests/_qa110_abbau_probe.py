"""QA-110: Kind-Probe fuer test_qa110_windows_abbau.py — nie im Gate-Lauf
(Name ohne ``test_``; nur ausdruecklich als Datei an pytest gegeben).

Nachgestellt wird, was die Abbau-Crashes unter Windows ausloeste: QtWebEngine
ist geladen (dann schaltet ``conftest.pytest_unconfigure`` die Exit-Haertung
scharf), und beim Ende leben noch Top-Level-Widgets, deren Klasse in Python
abgeleitet ist. Am Ende steht ``os._exit`` — unter Windows entlaedt das noch
die DLLs, und Qt fragt dabei die Python-Widgets nach ihrem ``metaObject()``
(gemessen: pyside6.abi3.dll in ``SignalManager::retrieveMetaObject``).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401 -> Haertung scharf
from PySide6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

_HALTEN = []


class _Fenster(QWidget):
    """In Python abgeleitet — wie SperrzonenPlaner, EinmessAssistent & Co.,
    mit eigenem ``event()`` wie ``VisualizerWindow`` (dort stand der Crash)."""

    def event(self, ev):
        return super().event(ev)


def test_fenster_bleiben_bis_zum_ende_offen():
    app = QApplication.instance() or QApplication([])
    for i in range(int(os.environ.get("QA110_FENSTER", "20"))):
        w = _Fenster()
        QLabel(f"Fenster {i}", w)
        w.show()
        _HALTEN.append(w)
    if os.environ.get("QA110_WEBVIEW", "1") == "1":
        w = _Fenster()
        v = QWebEngineView(w)
        v.setHtml("<html><body>QA-110</body></html>")
        w.show()
        _HALTEN.append(w)
        for _ in range(50):
            app.processEvents()
    app.processEvents()
    assert len(_HALTEN) > 0
    # Gegenprobe fuer den Rueckgabewert: der harte Ausstieg muss „rot“ weitergeben
    assert os.environ.get("QA110_ROT") != "1", "gewollt rot (QA110_ROT=1)"
