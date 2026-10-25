"""OUT-79: Kopf des Reiters „DMX-Eingang“ — Empfangsadresse, Firewall-Hinweis
und „seit dem Einschalten kam nichts an“ in den Statuszeilen.

Eigene Datei, damit ``output_config.py`` nur um wenige Zeilen wächst. Logik
und Texte: :mod:`src.core.dmx.empfangsadresse`, :mod:`src.core.netz_hinweis`.

Was der Bediener sieht:

* **Empfangen auf:** alle Netzwerkkarten (Vorgabe, wie bisher) · eine
  bestimmte Karte · nur dieser Rechner (127.0.0.1). Gilt für Art-Net- und
  sACN-Eingang UND die Fernsteuerung (ein gemeinsamer Empfänger je
  Protokoll); laufende Empfänger werden sofort neu gebunden.
* Ein kurzer Hinweis darunter, passend zum System (Windows: die Abfrage
  kommt gleich; Linux: ufw; macOS: „Erlauben“), mit „Ausblenden“.
* Beim ersten Haken (Art-Net-/sACN-Eingang oder „Fernsteuerung aktiv“) unter
  Windows einmal ein Fenster mit demselben Text — BEVOR Windows fragt.
* Kommt nach dem Einschalten 5 s lang gar nichts an, hängt die Statuszeile
  des Eingangs die Firewall als mögliche Ursache an und sagt, wo man
  nachsieht. LightOS ändert an der Firewall nichts.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QVBoxLayout,
)

from src.core import netz_hinweis as nh
from src.core.dmx import empfangsadresse as ea

#: ui_prefs.json — gerätegebunden wie die Ausgangs-Netzwerkkarte (NET-04)
PREF_GEZEIGT = "netz_hinweis_dmx_eingang_gezeigt"
PREF_AUS = "netz_hinweis_dmx_eingang_aus"

#: Trennt den angehängten Hinweis vom Status, den der Reiter selbst setzt.
MARKE = "\n⚠ "

TEXT_ALLE = "Alle Netzwerkkarten (Vorgabe)"
TEXT_LOKAL = "Nur dieser Rechner (127.0.0.1)"
TITEL_VORWARNUNG = "Gleich fragt Windows nach"


def _prefs() -> dict:
    try:
        from src.ui.views.programmer_view import _load_prefs
        return _load_prefs()
    except Exception:
        return {}


def _prefs_merken(updates: dict) -> None:
    try:
        from src.ui.views.programmer_view import _save_prefs
        _save_prefs(updates)
    except Exception as e:
        print(f"[dmx_empfang] prefs: {e}")


def _zeige_vorwarnung(parent, text: str) -> None:
    """Das eine Fenster vor der Windows-Abfrage (Tests ersetzen das)."""
    QMessageBox.information(parent, TITEL_VORWARNUNG, text)


def _karten() -> list:
    try:
        from src.core.dmx.output_iface import list_output_interfaces
        return [e for e in list_output_interfaces()
                if not ea.ist_lokal(e.get("ip", ""))]
    except Exception:
        return []


class EmpfangsBox(QGroupBox):
    """Empfangsadresse + Firewall-Hinweis + Überwachung der Statuszeilen."""

    def __init__(self, parent=None, pfad: str | None = None,
                 karten: list | None = None, empfaenger: dict | None = None,
                 sys_platform: str | None = None, uhr=time.monotonic):
        super().__init__("Empfang", parent)
        self._pfad = pfad                  # None = App-Datenordner
        self._empfaenger = empfaenger      # None = App-Empfänger
        self._plattform = sys_platform
        self._uhr = uhr
        self._ueberwacht: list = []        # [(label, check, protokolle)]
        lay = QVBoxLayout(self)

        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Empfangen auf:"))
        self.combo_adresse = QComboBox()
        self.combo_adresse.addItem(TEXT_ALLE, ea.ALLE)
        for e in (_karten() if karten is None else karten):
            self.combo_adresse.addItem(f"{e['name']} — {e['ip']}", e["ip"])
        self.combo_adresse.addItem(TEXT_LOKAL, ea.LOKAL)
        self.combo_adresse.setToolTip(
            "Auf welcher Adresse LightOS Art-Net und sACN empfängt — gilt für "
            "den Art-Net- und sACN-Eingang und die Fernsteuerung.\n"
            "Alle Netzwerkkarten = wie bisher.\n"
            "Eine Netzwerkkarte = nur, was über diese Karte kommt (sACN tritt "
            "dort den Multicast-Gruppen bei).\n"
            "Nur dieser Rechner = für ein zweites Programm auf diesem Rechner; "
            "Windows fragt dafür nicht nach. sACN kommt dann nur als Unicast "
            "an 127.0.0.1 an.\n"
            "Gilt für diesen Rechner, nicht für die Show.")
        zeile.addWidget(self.combo_adresse, 1)
        lay.addLayout(zeile)

        hinweis_zeile = QHBoxLayout()
        self.lbl_hinweis = QLabel()
        self.lbl_hinweis.setWordWrap(True)
        self.lbl_hinweis.setStyleSheet("color:#c9a227;")
        hinweis_zeile.addWidget(self.lbl_hinweis, 1)
        self.btn_ausblenden = QPushButton("Ausblenden")
        self.btn_ausblenden.setAutoDefault(False)
        self.btn_ausblenden.setToolTip(
            "Blendet diesen Hinweis auf diesem Rechner aus. Die Statuszeilen "
            "melden trotzdem, wenn nach dem Einschalten nichts ankommt.")
        self.btn_ausblenden.clicked.connect(self.hinweis_ausblenden)
        hinweis_zeile.addWidget(self.btn_ausblenden)
        lay.addLayout(hinweis_zeile)

        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        self._wahl_zeigen(ea.lade(self._pfad))
        self.combo_adresse.currentIndexChanged.connect(self._wahl_geaendert)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.pruefen)
        self._timer.start()

    # ── Wahl ──────────────────────────────────────────────────────────────

    def wahl(self) -> str:
        return ea.normiere(self.combo_adresse.currentData())

    def _wahl_zeigen(self, wahl: str) -> None:
        self.combo_adresse.blockSignals(True)
        i = self.combo_adresse.findData(wahl)
        if i < 0:
            # Gespeicherte Karte fehlt (anderes Netz, Adapter ab): NICHT still
            # auf „alle“ zurück — der Empfang scheitert sichtbar im Status.
            self.combo_adresse.insertItem(
                self.combo_adresse.count() - 1,
                f"{wahl} — derzeit nicht gefunden", wahl)
            i = self.combo_adresse.findData(wahl)
        self.combo_adresse.setCurrentIndex(max(0, i))
        self.combo_adresse.blockSignals(False)
        self._hinweis_zeigen()
        self.lbl_status.setText(f"Empfang: {ea.beschreibung(wahl)}.")

    def _bind_host(self) -> str:
        return ea.bind_host(self.wahl(), self._plattform)

    def _rx(self) -> dict:
        if self._empfaenger is None:
            from src.core.dmx.artnet_input import get_artnet_receiver
            from src.core.dmx.sacn_input import get_sacn_receiver
            return {"artnet": get_artnet_receiver(), "sacn": get_sacn_receiver()}
        return self._empfaenger

    def _wahl_geaendert(self, *_):
        wahl = self.wahl()
        rx = self._rx()
        laeuft = any(r.is_running() for r in rx.values())
        if laeuft:
            self.vorwarnen()        # neu binden auf eine Karte fragt Windows
        gespeichert = ea.speichere(wahl, self._pfad)
        neu = ea.anwenden(wahl, rx.get("artnet"), rx.get("sacn"))
        self._hinweis_zeigen()
        teil = "(gespeichert)" if gespeichert else "(NICHT gespeichert!)"
        text = f"Empfang: {ea.beschreibung(wahl)} {teil}."
        if neu:
            text += " Laufender Empfang neu gestartet."
        self.lbl_status.setText(text)

    # ── Hinweis ───────────────────────────────────────────────────────────

    def hinweistext(self) -> str:
        return nh.vorwarnung(self._bind_host(), sys_platform=self._plattform)

    def _hinweis_zeigen(self) -> None:
        aus = bool(_prefs().get(PREF_AUS))
        text = self.hinweistext()
        self.lbl_hinweis.setText(text)
        self.lbl_hinweis.setVisible(bool(text) and not aus)
        self.btn_ausblenden.setVisible(bool(text) and not aus)

    def hinweis_ausblenden(self) -> None:
        _prefs_merken({PREF_AUS: True})
        self._hinweis_zeigen()

    def vorwarnen(self) -> bool:
        """Vor dem ersten Einschalten unter Windows einmal das Fenster zeigen.
        ``True`` = gezeigt. Danach nie wieder (ui_prefs.json)."""
        if not nh.loest_abfrage_aus(self._bind_host(), self._plattform):
            return False
        if _prefs().get(PREF_GEZEIGT):
            return False
        _prefs_merken({PREF_GEZEIGT: True})
        _zeige_vorwarnung(self.window(), self.hinweistext())
        return True

    def beim_haken(self, an: bool) -> None:
        """Slot für die Haken „…-Eingang aktivieren“ / „Fernsteuerung aktiv“."""
        if an:
            self.vorwarnen()

    # ── Statuszeilen überwachen ───────────────────────────────────────────

    def ueberwache(self, label, check, protokolle=None) -> None:
        """``label`` bekommt den Firewall-Hinweis angehängt, solange ``check``
        angehakt ist und ein Empfänger seit dem Start nichts bekommen hat.
        ``protokolle`` = ("artnet",) / ("sacn",); ``None`` = die von der
        Fernsteuerung benutzten."""
        label.setWordWrap(True)
        self._ueberwacht.append((label, check, protokolle))

    def _protokolle(self, protokolle) -> tuple:
        if protokolle is not None:
            return tuple(protokolle)
        try:
            from src.core.dmx.fernsteuerung import get_fernsteuerung, QUELLEN
            fs = get_fernsteuerung()
            return tuple(q for q in QUELLEN if fs.universen(q))
        except Exception:
            return ()

    def meldung(self, protokolle, jetzt: float | None = None) -> str:
        """Was an die Statuszeile angehängt wird ("" = nichts)."""
        jetzt = self._uhr() if jetzt is None else jetzt
        rx_alle = self._rx()
        for p in protokolle:
            rx = rx_alle.get(p)
            if rx is None:
                continue
            if nh.empfaenger_ohne_empfang(rx, jetzt):
                start = getattr(rx, "gestartet_um", None)
                seit = jetzt - (jetzt if start is None else start)
                return nh.kein_empfang_text(
                    getattr(rx, "host", None), sekunden=seit,
                    sys_platform=self._plattform)
            fehler = getattr(rx, "letzter_fehler", "")
            if fehler and not rx.is_running():
                return (f"Empfang konnte nicht starten ({fehler}). Ist die "
                        "gewählte Netzwerkkarte da, und nutzt kein anderes "
                        "Programm den Port allein?")
        return ""

    def pruefen(self, jetzt: float | None = None) -> None:
        for label, check, protokolle in list(self._ueberwacht):
            try:
                basis = label.text().split(MARKE, 1)[0]
                zusatz = ""
                if check.isChecked():
                    zusatz = self.meldung(self._protokolle(protokolle), jetzt)
                soll = basis + (MARKE + zusatz if zusatz else "")
                if label.text() != soll:
                    label.setText(soll)
            except RuntimeError:
                pass   # Label schon zerstört (Dialog zu)
