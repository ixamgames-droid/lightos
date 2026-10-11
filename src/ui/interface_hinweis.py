"""OUT-70: dezenter Hinweis, wenn im Betrieb ein DMX-Interface dazukommt.

Alle paar Sekunden wird — in einem Hilfs-Thread, rein lesend — nachgesehen, was
am Rechner haengt (``interfaces.erkenne(schnell=True)``). Kommt ein BEKANNTES
Interface dazu, erscheint in der Statusleiste ein anklickbarer Satz
„Neues DMX-Interface erkannt: … — Einrichten…“ mit einem Schliessen-Knopf.

Bewusst klein gehalten:

* kein modaler Dialog, nichts wird von selbst eingerichtet;
* was beim Start schon steckt, ist keine Neuigkeit;
* abschaltbar (Menue *Ausgabe*), und mit ``LIGHTOS_KEIN_USB`` ganz aus;
* der Thread bekommt nur ein Dict und die Suchfunktion — nie ein Qt-Objekt.
"""
from __future__ import annotations

import os
import threading

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from src.core.dmx import interfaces

#: Abstand der Abfragen (Millisekunden).
ABFRAGE_MS = 5000
PREF = "interface_hinweis"


def _niemand(_port) -> list:
    return []


def _standard_suche():
    # Der Hinweis braucht nur „was steckt?“ — nicht „wer haelt den Port?“.
    # Diese Frage durchsucht unter Linux ganz ``/proc`` und fiele sonst alle
    # 5 s fuer jeden seriellen Adapter an (auch den eigenen, laufenden).
    return interfaces.erkenne(schnell=True, belegt=_niemand)


class InterfaceHinweis:
    """Steuerung + das kleine Widget in der Statusleiste."""

    def __init__(self, statusleiste, bei_klick, *, suche=None, aktiv=None):
        self._statusleiste = statusleiste
        self._bei_klick = bei_klick
        self._suche = suche
        self._aktiv = aktiv or (lambda: True)
        self._waechter = interfaces.EinsteckWaechter()
        self._thread = None
        self._ergebnis: dict | None = None
        self.widget: QWidget | None = None
        self.knopf: QPushButton | None = None
        self.text = ""

    # ── Abfrage ──────────────────────────────────────────────────────────────

    def takt(self):
        """Vom Timer des Hauptfensters: Ergebnis der letzten Suche abholen,
        dann die naechste starten. Blockiert nie."""
        if not self._aktiv():
            return
        if self._suche is None and os.environ.get("LIGHTOS_KEIN_USB"):
            return
        t = self._thread
        if t is not None and t.is_alive():
            return
        if self._ergebnis is not None and "befunde" in self._ergebnis:
            self.pruefe(self._ergebnis["befunde"])
        ergebnis: dict = {}
        self._ergebnis = ergebnis
        suche = self._suche or _standard_suche

        def lauf(ziel=ergebnis):
            try:
                ziel["befunde"] = suche()
            except Exception:                            # noqa: BLE001
                pass

        self._thread = threading.Thread(target=lauf, name="InterfaceWache",
                                        daemon=True)
        self._thread.start()

    def pruefe(self, befunde) -> str:
        """Befunde gegen den letzten Stand halten; bei Neuem den Hinweis
        zeigen. Liefert den gezeigten Text (leer = nichts Neues)."""
        neue = self._waechter.neue(befunde)
        if not neue or not self._aktiv():
            return ""
        self.zeige(interfaces.hinweis_text(neue))
        return self.text

    # ── Anzeige ──────────────────────────────────────────────────────────────

    def zeige(self, text: str):
        self.text = text
        if self.widget is None:
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(2)
            self.knopf = QPushButton(text)
            self.knopf.setFlat(True)
            self.knopf.setStyleSheet("color: #6aa9ff; text-align: left;")
            self.knopf.setToolTip("Öffnet den Assistenten „Interface "
                                  "einrichten…“. Es wird nichts von selbst "
                                  "eingerichtet.")
            self.knopf.clicked.connect(self._geklickt)
            lay.addWidget(self.knopf)
            self.zu = QPushButton("✕")
            self.zu.setFlat(True)
            self.zu.setFixedWidth(24)
            self.zu.setToolTip("Hinweis schließen")
            self.zu.setAccessibleName("Hinweis schließen")
            self.zu.clicked.connect(self.schliesse)
            lay.addWidget(self.zu)
            self.widget = w
            self._statusleiste.addPermanentWidget(w)
        else:
            self.knopf.setText(text)
        self.widget.show()

    def sichtbar(self) -> bool:
        return self.widget is not None and not self.widget.isHidden()

    def schliesse(self, *_):
        self.text = ""
        if self.widget is not None:
            self.widget.hide()

    def _geklickt(self, *_):
        self.schliesse()
        self._bei_klick()
