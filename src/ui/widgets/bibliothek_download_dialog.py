"""FM-53 Etappe 1: Dialog „Geräte-Bibliothek herunterladen?“.

Minimal: Quelle waehlen, Groesse und Lizenz VOR dem Download sehen, zustimmen,
Fortschritt, abbrechen. Die Arbeit macht ``src/core/database/bibliothek_download``
in einem Hintergrund-Thread; der Dialog zeigt nur an.

* „Nicht jetzt“ beim ersten Start zaehlt als Antwort — die Frage kommt nicht
  wieder (ueber das Menue Datenbank bleibt der Download jederzeit erreichbar).
* Ohne Netz zaehlt sie NICHT als Antwort: beim naechsten Start wird erneut
  gefragt.
"""
from __future__ import annotations

import threading
import urllib.request

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QProgressBar,
                               QPushButton, QRadioButton, QVBoxLayout)

from src.core.database import bibliothek_download as BD


def _mb(n):
    return f"{n / 1_000_000:.1f} MB"


class _Signale(QObject):
    groesse = Signal(str, object)          # schluessel, Bytes oder Fehlertext
    fortschritt = Signal(str, int, object)  # phase, wert, gesamt
    fertig = Signal(object)                 # BD.Ergebnis
    fehler = Signal(str, str)               # art, meldung


class BibliothekDownloadDialog(QDialog):
    def __init__(self, parent=None, erststart: bool = False, engine=None,
                 oeffnen=urllib.request.urlopen):
        super().__init__(parent)
        self.setWindowTitle("Geräte-Bibliothek herunterladen?")
        self.setMinimumWidth(520)
        self._erststart = erststart
        self._engine = engine
        self._oeffnen = oeffnen
        self._stopp = threading.Event()
        self._thread = None
        self.ergebnis = None
        self._s = _Signale()
        self._s.groesse.connect(self._groesse_da)
        self._s.fortschritt.connect(self._fortschritt)
        self._s.fertig.connect(self._fertig)
        self._s.fehler.connect(self._fehler)

        lay = QVBoxLayout(self)
        einleitung = QLabel(
            "LightOS kann eine freie Geräte-Bibliothek aus dem Internet laden und "
            "über den QLC+-Import einlesen. Vorhandene und eigene Profile bleiben "
            "unverändert; Herkunft und Lizenz werden je Profil gespeichert.")
        einleitung.setWordWrap(True)
        lay.addWidget(einleitung)

        self._wahl = {}
        for i, quelle in enumerate(BD.QUELLEN.values()):
            knopf = QRadioButton(quelle.name)
            knopf.setChecked(i == 0)
            knopf.toggled.connect(lambda an, q=quelle: an and self._groesse_fragen(q))
            lay.addWidget(knopf)
            info = QLabel(
                f'Lizenz: <a href="{quelle.lizenz_url}">{quelle.lizenz}</a>'
                + (f" — {quelle.hinweis}" if quelle.hinweis else ""))
            info.setOpenExternalLinks(True)
            info.setWordWrap(True)
            info.setContentsMargins(22, 0, 0, 6)
            lay.addWidget(info)
            self._wahl[quelle.schluessel] = knopf

        self._status = QLabel("")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)
        self._balken = QProgressBar()
        self._balken.setRange(0, 100)
        self._balken.setValue(0)
        lay.addWidget(self._balken)

        knoepfe = QHBoxLayout()
        knoepfe.addStretch(1)
        self.btn_spaeter = QPushButton("Nicht jetzt" if erststart else "Schließen")
        self.btn_spaeter.clicked.connect(self._spaeter)
        self.btn_abbrechen = QPushButton("Abbrechen")
        self.btn_abbrechen.setEnabled(False)
        self.btn_abbrechen.clicked.connect(self._stopp.set)
        self.btn_laden = QPushButton("Herunterladen")
        self.btn_laden.setDefault(True)
        self.btn_laden.clicked.connect(self.starten)
        for b in (self.btn_spaeter, self.btn_abbrechen, self.btn_laden):
            knoepfe.addWidget(b)
        lay.addLayout(knoepfe)

        self._groesse_fragen(self.quelle())

    # ── Zustand ───────────────────────────────────────────────────────────────
    def quelle(self) -> BD.Quelle:
        for schluessel, knopf in self._wahl.items():
            if knopf.isChecked():
                return BD.QUELLEN[schluessel]
        return next(iter(BD.QUELLEN.values()))

    def laeuft(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Groesse vorab ─────────────────────────────────────────────────────────
    def _groesse_fragen(self, quelle):
        self._status.setText("Größe wird ermittelt …")

        def arbeit():
            try:
                wert = BD.groesse_ermitteln(quelle, oeffnen=self._oeffnen)
            except BD.OfflineFehler as e:
                wert = f"offline: {e}"
            self._s.groesse.emit(quelle.schluessel, wert)
        threading.Thread(target=arbeit, daemon=True).start()

    def _groesse_da(self, schluessel, wert):
        if self.laeuft() or schluessel != self.quelle().schluessel:
            return
        if isinstance(wert, str):
            self._status.setText("Keine Verbindung — der Download ist später über "
                                 "Datenbank → Geräte-Bibliothek herunterladen möglich.")
        elif wert:
            self._status.setText(f"Download: {_mb(wert)}.")
        else:
            self._status.setText("Größe unbekannt (die Gegenstelle nennt keine).")

    # ── Download ──────────────────────────────────────────────────────────────
    def starten(self):
        if self.laeuft():
            return
        quelle = self.quelle()
        self._stopp.clear()
        for knopf in self._wahl.values():
            knopf.setEnabled(False)
        self.btn_laden.setEnabled(False)
        self.btn_spaeter.setEnabled(False)
        self.btn_abbrechen.setEnabled(True)
        self._status.setText(f"Lade {quelle.name} …")

        def arbeit():
            try:
                erg = BD.bibliothek_herunterladen(
                    quelle, engine=self._engine,
                    fortschritt=lambda p, w, g: self._s.fortschritt.emit(p, int(w), g),
                    abbrechen=self._stopp.is_set, oeffnen=self._oeffnen)
            except BD.Abgebrochen:
                # Im Download/Entpacken ist noch nichts importiert; im Import
                # bleiben die schon eingelesenen Profile (mit Herkunft) stehen.
                self._s.fehler.emit("abbruch", "Abgebrochen. Vorhandene und eigene "
                                    "Profile sind unverändert.")
            except BD.OfflineFehler as e:
                self._s.fehler.emit("offline", f"Keine Verbindung: {e}")
            except BD.DownloadFehler as e:
                self._s.fehler.emit("fehler", str(e))
            except Exception as e:      # nie den Dialog mit einem Thread-Tod zuruecklassen
                print(f"[bibliothek] ERROR: {e}")
                self._s.fehler.emit("fehler", f"Unerwarteter Fehler: {e}")
            else:
                self._s.fertig.emit(erg)
        self._thread = threading.Thread(target=arbeit, daemon=True)
        self._thread.start()

    def _fortschritt(self, phase, wert, gesamt):
        if gesamt:
            self._balken.setValue(int(100 * wert / max(1, gesamt)))
        text = {"download": "Download", "import": "Import"}.get(phase, phase)
        if phase == "download":
            self._status.setText(f"{text}: {_mb(wert)}" + (f" von {_mb(gesamt)}" if gesamt else ""))
        else:
            self._status.setText(f"{text}: {wert} von {gesamt or '?'} Dateien")

    def _fertig(self, erg):
        self.ergebnis = erg
        self._balken.setValue(100)
        q = self.quelle()
        self._status.setText(
            f"Fertig: {erg.neu} neue Profile ({q.lizenz}). SHA-256 {erg.sha256[:16]}…")
        self._ende()

    def _fehler(self, art, meldung):
        self._status.setText(meldung)
        self._ende()

    def _ende(self):
        self.btn_abbrechen.setEnabled(False)
        self.btn_spaeter.setText("Schließen")
        self.btn_spaeter.setEnabled(True)
        self.btn_laden.setEnabled(True)
        for knopf in self._wahl.values():
            knopf.setEnabled(True)

    def _spaeter(self):
        if self._erststart and self.ergebnis is None:
            BD.merker_schreiben(gefragt=True, antwort="nicht jetzt")
        self.accept()

    def reject(self):
        if self.laeuft():
            self._stopp.set()
            return                       # erst schliessen, wenn der Thread steht
        super().reject()

    def closeEvent(self, ev):
        if self.laeuft():
            self._stopp.set()
            ev.ignore()
            return
        super().closeEvent(ev)
