"""IMP-2: Mitschnitt-Assistent — Szenen aus einem anderen Lichtprogramm
uebernehmen.

Das andere Programm gibt seine Szenen nacheinander aus, LightOS empfaengt das
ueber den Art-Net-/sACN-Eingang, und **Als Szene festhalten** macht aus dem
gerade empfangenen Bild eine Szene. Am Ende werden die festgehaltenen Szenen
auf Wunsch ein Chaser.

★ Der Dialog LIEST nur den Eingang. Er gibt nichts aus, startet und stoppt
keinen Empfaenger, aendert keine Merge-Zuordnung und fasst weder Programmer
noch laufende Funktionen an. Die Rechnung steht in ``src/core/mitschnitt.py``.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout,
)

from src.core import mitschnitt as M

TITEL = "Mitschnitt-Assistent"
STAMM = "Mitschnitt"

TEXT_FESTHALTEN = "Als Szene festhalten"
TEXT_ENTFERNEN = "Entfernen"
TEXT_FERTIG = "Fertig"
TEXT_CHASER = "Am Ende als Chaser zusammenfassen"
TEXT_LASER = "Laser mit aufnehmen"
TEXT_UNRUHIG = "Auch festhalten, wenn sich das Bild noch ändert"

AUSWAHL_TEXT = {
    M.AUSWAHL_ALLE: "Alle gepatchten Kanäle",
    M.AUSWAHL_UNGLEICH_NULL: "Nur Kanäle ungleich 0",
    M.AUSWAHL_GEAENDERT: "Nur was sich seit dem letzten Festhalten geändert hat",
}

HILFE_EINGANG = (
    "So schaltest du den Eingang ein: Menü „Ausgabe“ → „Konfigurieren...“ → "
    "Reiter „DMX Input“. Dort „Art-Net Input aktivieren“ oder „sACN Input "
    "aktivieren“ anhaken, bei „Eingehendes Universe“ das Universum des anderen "
    "Programms und bei „Merge in Universe“ das LightOS-Universum deines Patches "
    "eintragen, dann „Übernehmen“. Das andere Programm muss an diesen Rechner "
    "senden.")
HINWEIS_NUR_LESEN = (
    "Der Assistent liest nur den Eingang. Er gibt selbst nichts aus und ändert "
    "weder den Programmer noch laufende Funktionen.")
HINWEIS_LASER = (
    "Laser werden ausgelassen (Sicherheitsvorgabe). Nur mit dem Haken „"
    + TEXT_LASER + "“ kommen ihre Kanäle mit in die Szene.")

GRUND_KEIN_SIGNAL = "Kein Signal — es gibt nichts festzuhalten."
GRUND_KEIN_PATCH = (
    "Es ist noch kein Gerät gepatcht. Lege zuerst den Patch an — ohne ihn "
    "weiß LightOS nicht, welche Kanäle zu welchem Gerät gehören.")
GRUND_UNRUHIG = (
    "Das Bild ändert sich noch (läuft eine Überblendung?). Warte, bis es "
    "ruhig steht, und drücke dann noch einmal.")
GRUND_KEINE_WERTE = (
    "Im empfangenen Bild liegt nichts auf gepatchten Adressen — es entsteht "
    "keine Szene.")


def _dauer(sekunden: float) -> str:
    s = int(sekunden)
    if s < 60:
        return f"{s} s"
    return f"{s // 60} min {s % 60:02d} s"


class MitschnittDialog(QDialog):
    """Der Assistent. ``state`` und ``leser`` lassen sich fuer Tests
    hereinreichen; ohne Angabe gelten AppState und die echten Empfaenger."""

    def __init__(self, parent=None, *, state=None, leser: M.EingangsLeser | None = None):
        super().__init__(parent)
        self.setWindowTitle(TITEL)
        self.setMinimumSize(560, 620)
        if state is None:
            from src.core.app_state import get_state
            state = get_state()
        self._state = state
        self._leser = leser or M.EingangsLeser()
        self._bezug: dict[int, bytes] | None = None
        self._zaehler = 1
        self._vorschlag = ""
        #: festgehaltene Szenen in Reihenfolge (Funktions-IDs)
        self._szenen: list[int] = []
        self.chaser = None

        self._baue_oberflaeche()
        self._leser.verbinden()
        self._name_vorschlagen()
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.aktualisiere)
        self._timer.start()
        self.aktualisiere()

    # ── Aufbau ───────────────────────────────────────────────────────────────

    def _baue_oberflaeche(self):
        root = QVBoxLayout(self)

        kopf = QLabel(HINWEIS_NUR_LESEN)
        kopf.setWordWrap(True)
        root.addWidget(kopf)

        box = QGroupBox("Eingang")
        bl = QVBoxLayout(box)
        self._lbl_status = {}
        for protokoll in (M.ARTNET, M.SACN):
            lbl = QLabel()
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.TextFormat.PlainText)
            self._lbl_status[protokoll] = lbl
            bl.addWidget(lbl)
        self._lbl_hilfe = QLabel(HILFE_EINGANG)
        self._lbl_hilfe.setWordWrap(True)
        self._lbl_hilfe.setStyleSheet("color:#c9a227;")
        bl.addWidget(self._lbl_hilfe)
        self._lbl_live = QLabel()
        self._lbl_live.setWordWrap(True)
        bl.addWidget(self._lbl_live)
        root.addWidget(box)

        box = QGroupBox("Festhalten")
        form = QFormLayout(box)
        self._edit_name = QLineEdit()
        self._edit_name.setToolTip("Name der nächsten Szene. Nach dem Festhalten "
                                   "zählt LightOS von selbst weiter.")
        form.addRow("Name:", self._edit_name)
        self._combo_auswahl = QComboBox()
        for schluessel in M.AUSWAHLEN:
            self._combo_auswahl.addItem(AUSWAHL_TEXT[schluessel], schluessel)
        self._combo_auswahl.setCurrentIndex(M.AUSWAHLEN.index(M.AUSWAHL_VORGABE))
        self._combo_auswahl.setToolTip(
            "Welche Kanäle in die Szene kommen. „Alle gepatchten Kanäle“ hält "
            "das ganze Bild fest — auch, was dunkel ist. Die anderen beiden "
            "Regeln lassen Kanäle weg; solche Szenen lassen andere Funktionen "
            "auf diesen Kanälen durch. Die Dimmer-Kanäle eines aufgenommenen "
            "Geräts kommen immer mit, damit eine Farbe ohne Dimmer dunkel bleibt.")
        form.addRow("Kanäle:", self._combo_auswahl)
        self._check_laser = QCheckBox(TEXT_LASER)
        self._check_laser.setToolTip(HINWEIS_LASER)
        form.addRow(self._check_laser)
        self._lbl_laser = QLabel(HINWEIS_LASER)
        self._lbl_laser.setWordWrap(True)
        form.addRow(self._lbl_laser)
        self._spin_ruhe = QDoubleSpinBox()
        self._spin_ruhe.setRange(0.1, 10.0)
        self._spin_ruhe.setSingleStep(0.1)
        self._spin_ruhe.setDecimals(1)
        self._spin_ruhe.setSuffix(" s")
        self._spin_ruhe.setValue(M.RUHEZEIT_VORGABE)
        self._spin_ruhe.setToolTip("So lange darf sich das empfangene Bild nicht "
                                   "geändert haben, damit es als ruhig gilt.")
        form.addRow("Ruhig nach:", self._spin_ruhe)
        self._check_unruhig = QCheckBox(TEXT_UNRUHIG)
        self._check_unruhig.setToolTip(
            "Für Quellen, die nie stillstehen (laufender Effekt). Festgehalten "
            "wird dann der Augenblick des Knopfdrucks.")
        form.addRow(self._check_unruhig)
        self._btn_festhalten = QPushButton(TEXT_FESTHALTEN)
        self._btn_festhalten.setMinimumHeight(36)
        self._btn_festhalten.setToolTip("Hält das gerade empfangene Bild als "
                                        "Szene fest (Leertaste).")
        self._btn_festhalten.clicked.connect(self.festhalten)
        form.addRow(self._btn_festhalten)
        self._lbl_meldung = QLabel()
        self._lbl_meldung.setWordWrap(True)
        form.addRow(self._lbl_meldung)
        root.addWidget(box)

        # Leertaste haelt fest — ausser man tippt gerade im Namensfeld (dort
        # nimmt das Feld die Taste und schreibt ein Leerzeichen).
        self._kuerzel = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._kuerzel.setContext(Qt.ShortcutContext.WindowShortcut)
        # Ohne das wiederholt eine gehaltene Leertaste das Kuerzel im Takt der
        # Tastenwiederholung — ein ruhiges Bild ergaebe dann Szene um Szene.
        self._kuerzel.setAutoRepeat(False)
        self._kuerzel.activated.connect(self.festhalten)

        box = QGroupBox("Festgehaltene Szenen")
        ll = QVBoxLayout(box)
        self._liste = QListWidget()
        ll.addWidget(self._liste)
        zeile = QHBoxLayout()
        self._btn_entfernen = QPushButton(TEXT_ENTFERNEN)
        self._btn_entfernen.setToolTip("Löscht die markierte Szene wieder "
                                       "(lässt sich rückgängig machen).")
        self._btn_entfernen.clicked.connect(self.entferne_markierte)
        zeile.addWidget(self._btn_entfernen)
        zeile.addStretch(1)
        ll.addLayout(zeile)
        zeile = QHBoxLayout()
        self._check_chaser = QCheckBox(TEXT_CHASER)
        self._check_chaser.setToolTip(
            "Beim Schließen über „Fertig“ entsteht ein Chaser, der die Szenen "
            "in dieser Reihenfolge abspielt.")
        zeile.addWidget(self._check_chaser)
        zeile.addWidget(QLabel("Schrittzeit:"))
        self._spin_schritt = QDoubleSpinBox()
        self._spin_schritt.setRange(0.1, 600.0)
        self._spin_schritt.setSingleStep(0.5)
        self._spin_schritt.setDecimals(1)
        self._spin_schritt.setSuffix(" s")
        self._spin_schritt.setValue(1.0)
        self._spin_schritt.setToolTip("So lange steht jeder Schritt des Chasers.")
        zeile.addWidget(self._spin_schritt)
        zeile.addStretch(1)
        ll.addLayout(zeile)
        root.addWidget(box, 1)

        zeile = QHBoxLayout()
        zeile.addStretch(1)
        self._btn_fertig = QPushButton(TEXT_FERTIG)
        self._btn_fertig.setToolTip("Schließt den Assistenten. Die Szenen "
                                    "bleiben in der Funktionsliste.")
        self._btn_fertig.setAutoDefault(False)
        self._btn_fertig.clicked.connect(self.fertig)
        zeile.addWidget(self._btn_fertig)
        root.addLayout(zeile)
        for knopf in (self._btn_festhalten, self._btn_entfernen):
            knopf.setAutoDefault(False)
        self._btn_festhalten.setFocus()

    # ── Abfragen ─────────────────────────────────────────────────────────────

    @property
    def szenen_ids(self) -> list[int]:
        return list(self._szenen)

    def _fm(self):
        return self._state.function_manager

    def _patch(self):
        return list(self._state.get_patched_fixtures())

    def _lies(self, bild: M.Eingangsbild, auswahl=None) -> M.Mitschnitt:
        return M.lies_abbild(
            bild.abbild, self._patch(),
            auswahl=auswahl or self._combo_auswahl.currentData(),
            bezug=self._bezug,
            laser_mitnehmen=self._check_laser.isChecked())

    def grund_gesperrt(self, bild: M.Eingangsbild | None = None) -> str:
        """Warum jetzt nicht festgehalten werden kann — leer, wenn es geht."""
        bild = bild or self._leser.bild()
        if not bild.hat_signal:
            return GRUND_KEIN_SIGNAL
        if not self._patch():
            return GRUND_KEIN_PATCH
        if (not self._check_unruhig.isChecked()
                and not bild.ist_ruhig(self._spin_ruhe.value())):
            return GRUND_UNRUHIG
        return ""

    # ── Anzeige ──────────────────────────────────────────────────────────────

    def _status_text(self, protokoll: str, bild: M.Eingangsbild) -> str:
        if not self._leser.laeuft(protokoll):
            return f"{protokoll}: Eingang ist aus."
        zuordnung = self._leser.zuordnungen(protokoll)
        if not zuordnung:
            return (f"{protokoll}: Eingang läuft, aber es ist kein Universum "
                    f"zugeordnet.")
        staende = {(s.protokoll, s.universum): s for s in self._leser.puffer.stand()}
        teile = []
        for von, nach in sorted(zuordnung.items()):
            st = staende.get((protokoll, von))
            if st is None:
                lage = "kein Signal"
            elif not st.hat_signal:
                lage = f"kein Signal (letztes Paket vor {_dauer(st.letztes_paket_vor)})"
            else:
                lage = f"Signal seit {_dauer(st.signal_seit)}"
            teile.append(f"Universum {von} → LightOS-Universum {nach}: {lage}")
        text = f"{protokoll}: " + "; ".join(teile)
        fremd = sorted(u for p, u in bild.nicht_zugeordnet if p == protokoll)
        if fremd:
            text += (" — außerdem empfangen, aber nicht zugeordnet und deshalb "
                     "nicht mitgeschnitten: Universum "
                     + ", ".join(str(u) for u in fremd)
                     + " (es gilt ein Universum je Protokoll).")
        return text

    def aktualisiere(self):
        """Status, Live-Anzeige und Knopf neu setzen (laeuft am Timer)."""
        bild = self._leser.bild()
        for protokoll, lbl in self._lbl_status.items():
            lbl.setText(self._status_text(protokoll, bild))
        self._lbl_hilfe.setVisible(not bild.hat_signal)

        if bild.hat_signal:
            m = self._lies(bild, auswahl=M.AUSWAHL_ALLE)
            text = (f"{m.geraete_mit_wert} von {m.geraete_gesehen} gepatchten "
                    f"Geräten bekommen gerade Werte.")
            text += (" Das Bild steht ruhig." if bild.ist_ruhig(self._spin_ruhe.value())
                     else " Das Bild ändert sich noch.")
            if m.ohne_bild:
                text += (f" {len(m.ohne_bild)} Gerät(e) liegen in einem Universum, "
                         f"das nicht empfangen wird — sie kommen nicht in die Szene.")
            if bild.doppelt:
                text += (" Achtung: Art-Net und sACN zeigen auf dasselbe "
                         "LightOS-Universum " + ", ".join(map(str, bild.doppelt))
                         + " — es gilt das zuletzt empfangene Bild.")
            laser = len(m.laser_ausgelassen)
        else:
            text = "Kein Signal."
            laser = 0
        self._lbl_live.setText(text)
        self._lbl_laser.setText(
            HINWEIS_LASER + (f" Gerade ausgelassen: {laser}." if laser else ""))
        self._lbl_laser.setVisible(not self._check_laser.isChecked())

        grund = self.grund_gesperrt(bild)
        # Der Knopf bleibt bedienbar und ERKLAERT, warum es nicht geht — ein
        # ausgegrauter Knopf sagt nichts. Nur der Tooltip traegt den Grund mit.
        self._btn_festhalten.setToolTip(
            grund or "Hält das gerade empfangene Bild als Szene fest (Leertaste).")
        self._btn_entfernen.setEnabled(self._liste.currentRow() >= 0)
        self._check_chaser.setEnabled(True)

    def _name_vorschlagen(self):
        self._vorschlag, self._zaehler = M.freier_name(self._fm(), STAMM, self._zaehler)
        self._edit_name.setText(self._vorschlag)

    def _melde(self, text: str, fehler: bool = False):
        self._lbl_meldung.setStyleSheet("color:#e0705a;" if fehler else "color:#7fc98f;")
        self._lbl_meldung.setText(text)

    # ── Aktionen ─────────────────────────────────────────────────────────────

    def festhalten(self):
        """Das gerade empfangene Bild als Szene anlegen. Gibt die Szene zurueck
        oder ``None`` (die Meldungszeile nennt dann den Grund)."""
        bild = self._leser.bild()
        grund = self.grund_gesperrt(bild)
        if grund:
            if grund == GRUND_KEIN_SIGNAL:
                grund += " " + HILFE_EINGANG
            self._melde(grund, fehler=True)
            return None
        m = self._lies(bild)
        if not m.kanalzahl:
            self._melde(GRUND_KEINE_WERTE, fehler=True)
            return None
        name = self._edit_name.text().strip() or f"{STAMM} {self._zaehler}"
        try:
            szene = M.baue_szene(self._fm(), name, m)
        except Exception as e:
            self._melde(str(e), fehler=True)
            return None
        self._bezug = dict(bild.abbild)
        self._szenen.append(szene.id)
        item = QListWidgetItem(
            f"{szene.name} — {len(m.geraete)} Geräte, {m.kanalzahl} Kanäle")
        item.setData(Qt.ItemDataRole.UserRole, szene.id)
        self._liste.addItem(item)
        self._liste.setCurrentItem(item)
        text = f"„{szene.name}“ festgehalten."
        if m.laser_ausgelassen:
            text += f" {len(m.laser_ausgelassen)} Laser ausgelassen."
        if not bild.ist_ruhig(self._spin_ruhe.value()):
            text += " Das Bild stand dabei nicht ruhig."
        self._melde(text)
        if szene.name == self._vorschlag:
            # Auch wenn die Szene wieder entfernt wird: die Nummer ist vergeben.
            self._zaehler += 1
        self._name_vorschlagen()
        self.aktualisiere()
        return szene

    def entferne_markierte(self):
        """Die markierte Szene wieder loeschen — eigener Rueckgaengig-Schritt."""
        zeile = self._liste.currentRow()
        if zeile < 0:
            return
        item = self._liste.takeItem(zeile)
        sid = item.data(Qt.ItemDataRole.UserRole)
        fm = self._fm()
        szene = fm.get(sid)
        if sid in self._szenen:
            self._szenen.remove(sid)
        if szene is not None:
            from src.core.undo import Command, get_undo_stack
            get_undo_stack().push(Command(
                label=f"Mitschnitt „{szene.name}“ entfernen",
                do=lambda: fm.remove(sid),
                undo=lambda: fm.add(szene)))
            self._melde(f"„{szene.name}“ entfernt.")
        self.aktualisiere()

    def fertig(self):
        """Schliessen; mit Haken vorher den Chaser anlegen."""
        if self._check_chaser.isChecked() and self._szenen:
            fm = self._fm()
            ids = [sid for sid in self._szenen if fm.get(sid) is not None]
            if ids:
                name, _ = M.freier_name(fm, f"{STAMM} Chaser", 1)
                try:
                    self.chaser = M.baue_chaser(fm, name, ids,
                                                self._spin_schritt.value())
                except Exception as e:
                    self._melde(str(e), fehler=True)
                    return
        self.accept()

    # ── Abbau ────────────────────────────────────────────────────────────────

    def done(self, ergebnis):
        self._timer.stop()
        self._leser.trennen()
        super().done(ergebnis)

    def closeEvent(self, ev):
        self._timer.stop()
        self._leser.trennen()
        super().closeEvent(ev)
