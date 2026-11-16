"""QA-123: Doppeltipps im Test zuverlaessig machen.

Qt macht aus zwei Druecken nur dann einen Doppelklick, wenn der Zeitstempel
des zweiten Drucks *echt groesser* ist als der des ersten
(``QGuiApplicationPrivate::processMouseEvent``: ``timestampDelta > 0 &&
timestampDelta < mouseDoubleClickInterval``, dazu gleiche Taste und gleiches
Fenster). Die Zeitstempel kommen in Millisekunden aus Qts Ereignisuhr
(``QWindowSystemInterfacePrivate::eventTime``), und ``QTest.touchEvent(...)
.commit()`` legt unter PySide keine Pause ein (gemessen 0,05 ms je Aufruf).
Ein schneller Rechner schafft Tipp + zweiten Druck in derselben Millisekunde:
beide Druecke tragen denselben Zeitstempel, Qt sieht keinen Doppelklick — der
Test schlug nur auf schnellen CI-Rechnern fehl und nie unter Last.

``DruckUhr`` merkt sich den Zeitstempel des letzten Fenster-Drucks und wann er
ankam. ``naechster_zeitstempel()`` laesst die Ereignisschleife laufen, bis Qts
Ereignisuhr sicher ueber diesen Zeitstempel hinaus ist: die Uhr zaehlt in
ganzen Millisekunden ab und laeuft mit der monotonen Uhr gleich schnell —
ist seit der Ankunft des Drucks mehr als eine Millisekunde vergangen, traegt
jeder neue Druck einen groesseren Zeitstempel. Das ist eine Bedingung, keine
Schlafzeit als Toleranz: auf die Dauer des Rechners kommt es nicht an.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QApplication

# Eine Ereignisuhr-Millisekunde plus Reserve fuer das Abrunden beider Uhren.
_TICK_S = 0.0015


class DruckUhr(QObject):
    """Beobachtet die Druecke, die Qt an Fenster zustellt (nur lesend)."""

    def __init__(self):
        super().__init__()
        self.zeitstempel: list[int] = []        # Zeitstempel aller Fenster-Druecke
        self.doppelklicks = 0                    # von Qt erzeugte Doppelklicks (Fenster)
        self._ankunft = None
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, ev):              # noqa: N802 (Qt)
        if isinstance(obj, QWindow):
            t = ev.type()
            if t == QEvent.Type.MouseButtonPress:
                self.zeitstempel.append(ev.timestamp())
                self._ankunft = time.monotonic()
            elif t == QEvent.Type.MouseButtonDblClick:
                self.doppelklicks += 1
        return False

    def naechster_zeitstempel(self) -> None:
        """Warten, bis ein neuer Druck einen groesseren Zeitstempel bekommt."""
        if self._ankunft is None:
            return
        while time.monotonic() - self._ankunft < _TICK_S:
            QApplication.processEvents()
        QApplication.processEvents()

    def entfernen(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
