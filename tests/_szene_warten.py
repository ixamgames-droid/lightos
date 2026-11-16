"""QA-115: gemeinsames Warten fuer Szenen-Tests (QWebEngineView).

Die Szenen-Tests warteten mit ``processEvents()`` + ``time.sleep(0.05)`` je
Schleifendurchgang. Ein ``runJavaScript``-Ergebnis kommt aber meist nach
wenigen Millisekunden — jedes ``_eval`` kostete so 50-100 ms reinen Schlaf,
jedes ``_poll_until_true`` dazu noch einmal 50 ms je Runde. Auf Windows-ARM
summierte sich das in ``test_viz13_scene_modules_smoke.py`` auf ueber 300 s.

Hier wird im 5-ms-Takt gepumpt. Die Ereignis-Zustellung bleibt bewusst
dieselbe (``processEvents()``, keine eigene ``QEventLoop``): eine verschachtelte
Schleife stellt zusaetzlich ``DeferredDelete`` zu und haette damit das
Abbau-Verhalten veraendert, auf das ``_qt_lifecycle`` (XPLAT-09/-15) gebaut
ist. Die Zeitgrenzen (``timeout_s``) bleiben unveraendert grosszuegig — nur
der Takt wird feiner, keine Aussage eines Tests haengt daran.
"""
from __future__ import annotations

import time

from PySide6.QtWidgets import QApplication

#: Pump-Takt in Sekunden (vorher 0.05).
TAKT_S = 0.005


def warte_bis(bedingung, timeout_s: float, takt_s: float = TAKT_S) -> bool:
    """Ereignisse zustellen, bis ``bedingung()`` wahr ist oder die Zeit um ist.

    Prueft vor jedem Schlaf, kehrt also sofort zurueck, sobald es soweit ist.
    Gibt das letzte Ergebnis von ``bedingung()`` als bool zurueck."""
    app = QApplication.instance()
    ende = time.monotonic() + timeout_s
    while True:
        app.processEvents()
        if bedingung():
            return True
        if time.monotonic() >= ende:
            return bool(bedingung())
        time.sleep(takt_s)


def js_eval(view, js_expr: str, timeout_s: float):
    """``runJavaScript`` und auf den Callback warten.

    Gibt ``(True, ergebnis)`` zurueck oder ``(False, None)`` nach Zeitablauf."""
    box: list = []
    view.page().runJavaScript(js_expr, lambda result: box.append(result))
    if warte_bis(lambda: bool(box), timeout_s):
        return True, box[0]
    return False, None


#: Pause zwischen zwei Abfragen in ``_poll_until_true``/``_emit_until_true``
#: (vorher 50 ms blockierender Schlaf; jetzt wird dabei gepumpt).
POLL_PAUSE_S = 0.01


def pumpen(sekunden: float, takt_s: float = TAKT_S) -> None:
    """``sekunden`` lang Ereignisse zustellen (statt blockierend zu schlafen)."""
    warte_bis(lambda: False, sekunden, takt_s)
