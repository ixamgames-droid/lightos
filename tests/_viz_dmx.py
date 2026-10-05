"""VIZ-71: DMX in einer Szenen-Testseite anwenden.

Bis VIZ-71 nahmen die Szenen-Tests den Signal-Weg ``bridge.dmxBatch`` — den
gibt es seit VIZ-71 in JS nicht mehr (der Service schiebt die Werte per
``runJavaScript`` an ``window.__lightos.applyDmx``). Dieser Helfer geht
denselben Weg wie die Produktion: ``runJavaScript`` ist auch auf einer
gedrosselten offscreen-Seite zuverlaessig, und mehrere Aufrufe kommen in
Reihenfolge an — ein danach abgesetztes ``runJavaScript`` sieht das Ergebnis.
"""


def dmx_push(view, batch_json: str) -> None:
    """``batch_json``: JSON-Liste von Payloads wie aus dem VisualizerService."""
    view.page().runJavaScript(
        "window.__lightos && window.__lightos.applyDmx"
        " && window.__lightos.applyDmx(%s)" % batch_json)
