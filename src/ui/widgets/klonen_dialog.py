"""ENG-36: Dialog „Klonen" — Nachfrage, Vorschau, Anwenden.

Der Dialog rechnet nur: jede Änderung an einem Häkchen oder an der Wahl
lässt ``klonen.plane`` neu laufen und zeigt das Ergebnis. Geschrieben wird
erst mit „Anwenden" — vorher eine Sicherung der Show, danach EIN Schritt im
Rückgängig-Verlauf.

Die Vorschau ist eine Liste aus Einträgen (keine eingebetteten Widgets): sie
wird bei jeder Neuberechnung geleert und neu gefüllt, ohne dass ein Widget in
seinem eigenen Signal gelöscht wird.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QDialog, QDialogButtonBox,
    QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QRadioButton, QVBoxLayout,
)

from src.core.show import klonen as K

_FARBEN = {
    K.UNVERAENDERT: "#9DFF52",
    K.UEBERSETZT: "#ffcc44",
    K.FAELLT_WEG: "#ff7777",
    K.BLEIBT: "#999999",
}
_ZEICHEN = {K.UNVERAENDERT: "✓", K.UEBERSETZT: "≈", K.FAELLT_WEG: "✗", K.BLEIBT: "·"}


def _geraete_text(state, fids) -> str:
    namen = {int(f.fid): (getattr(f, "label", "") or "").strip()
             for f in state.get_patched_fixtures()}
    return ", ".join(f"{fid} „{namen.get(fid) or 'Gerät'}“" for fid in fids)


class Umgebung:
    """Was das Klonen von der Oberfläche braucht.

    Einige Ansichten halten ihren Stand selbst und geben ihn erst beim
    Speichern heraus (Konsole, Snapshots). Vor dem Rechnen wird er abgeholt,
    nach dem Schreiben zurückgegeben. Ohne Hauptfenster (Tests, Werkzeuge)
    tut jede Methode nichts.
    """

    def __init__(self, fenster=None, state=None):
        self.fenster = fenster
        self.state = state
        #: Die Konsole hat beim Laden Elemente übersprungen: ihr Layout wird
        #: dann NICHT abgeholt (das würde die übersprungenen Elemente aus der
        #: Show werfen) und die Konsole nicht geklont.
        self.konsole_gesperrt = False

    def _hat_ansichten(self) -> bool:
        return callable(getattr(self.fenster, "_views_in_state", None))

    def abholen(self) -> None:
        if not self._hat_ansichten() or self.state is None:
            return
        ansichten: dict = {}
        try:
            self.fenster._views_in_state(nur_vergleich=ansichten)
        except Exception as e:
            print(f"[klonen] Ansichten nicht abholbar: {e}")
            self.konsole_gesperrt = True
            return
        if isinstance(ansichten.get("snapshots"), list):
            self.state._snapshots_data = ansichten["snapshots"]
        vc = getattr(self.fenster, "_vc_view", None)
        try:
            uebersprungen = getattr(vc, "uebersprungene_widgets", lambda: [])()
        except Exception:
            uebersprungen = ["?"]
        self.konsole_gesperrt = bool(uebersprungen)
        if not uebersprungen and isinstance(ansichten.get("virtual_console"), dict):
            self.state._vc_layout = ansichten["virtual_console"]

    def sichern(self) -> str | None:
        name = None
        try:
            name = self.fenster._sicherungs_name()
        except Exception:
            pass
        return K.sicherung_anlegen(name)

    def nachziehen(self, plan) -> None:
        if not self._hat_ansichten() or self.state is None:
            return
        beruehrt = plan.beruehrte_bereiche
        if K.BEREICH_KONSOLE in beruehrt and not self.konsole_gesperrt:
            vc = getattr(self.fenster, "_vc_view", None)
            layout = getattr(self.state, "_vc_layout", None)
            if vc is not None and isinstance(layout, dict):
                try:
                    vc.from_dict(layout)
                except Exception as e:
                    print(f"[klonen] Konsole nicht nachgezogen: {e}")
        if any(e.schritte and e.objekt.startswith("Snapshot ")
               for e in plan.eintraege):
            sv = getattr(self.fenster, "_snapshots_view", None)
            if sv is not None:
                try:
                    sv.load_data(getattr(self.state, "_snapshots_data", []) or [])
                except Exception as e:
                    print(f"[klonen] Snapshots nicht nachgezogen: {e}")


class ZielAuswahlDialog(QDialog):
    """„Klonen auf …" — die Zielgeräte wählen."""

    def __init__(self, state, quellen, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Klonen auf …")
        self.setMinimumSize(420, 380)
        self._quellen = [int(q) for q in quellen]
        lay = QVBoxLayout(self)
        kopf = QLabel(f"Quelle: {_geraete_text(state, self._quellen)}\n"
                      "Auf welche Geräte soll übertragen werden?")
        kopf.setWordWrap(True)
        lay.addWidget(kopf)
        self._liste = QListWidget()
        self._liste.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        for f in sorted(state.get_patched_fixtures(), key=lambda f: f.fid):
            if int(f.fid) in self._quellen:
                continue
            typ = " · ".join(x for x in (getattr(f, "fixture_name", "") or "",
                                         getattr(f, "mode_name", "") or "") if x)
            item = QListWidgetItem(
                f"{f.fid}   {getattr(f, 'label', '') or ''}"
                + (f"   ({typ})" if typ else ""))
            item.setData(Qt.ItemDataRole.UserRole, int(f.fid))
            self._liste.addItem(item)
        lay.addWidget(self._liste, stretch=1)
        self._hinweis = QLabel("")
        self._hinweis.setWordWrap(True)
        self._hinweis.setStyleSheet("color:#aaa;")
        lay.addWidget(self._hinweis)
        knoepfe = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        self._ok = knoepfe.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText("Weiter")
        knoepfe.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self._liste.itemSelectionChanged.connect(self._pruefen)
        self._pruefen()

    def ziele(self) -> list[int]:
        return sorted(int(i.data(Qt.ItemDataRole.UserRole))
                      for i in self._liste.selectedItems())

    def _pruefen(self) -> None:
        ziele = self.ziele()
        try:
            paare = K.paare_bilden(self._quellen, ziele)
        except K.KlonFehler as e:
            self._ok.setEnabled(False)
            self._hinweis.setText(
                "Mehrere mit Strg/Umschalt wählen." if not ziele else str(e))
            return
        self._ok.setEnabled(True)
        self._hinweis.setText(
            "Paarweise in Reihenfolge der Nummern: "
            + ", ".join(f"{q} → {z}" for q, z in paare[:8])
            + (" …" if len(paare) > 8 else ""))


class KlonenDialog(QDialog):
    """Nachfrage (hinzufügen oder ersetzen) mit Vorschau."""

    def __init__(self, state, quellen, ziele, parent=None, umgebung=None,
                 snap_library=None, palette_manager=None):
        super().__init__(parent)
        self._snaps, self._paletten = snap_library, palette_manager
        self.setWindowTitle("Klonen")
        self.setMinimumSize(860, 520)
        self._state = state
        self._quellen = [int(q) for q in quellen]
        self._ziele = [int(z) for z in ziele]
        self._umgebung = umgebung or Umgebung(None, state)
        self._plan = None
        #: Zahl der geänderten Stellen nach „Anwenden", sonst ``None``.
        self.ergebnis: int | None = None
        self._umgebung.abholen()
        self._aufbauen()
        self._neu_rechnen()

    # ── Aufbau ───────────────────────────────────────────────────────────────

    def _aufbauen(self) -> None:
        lay = QVBoxLayout(self)
        self._kopf = QLabel(
            f"<b>Von:</b> {_geraete_text(self._state, self._quellen)}"
            f" &nbsp;→&nbsp; <b>Auf:</b> {_geraete_text(self._state, self._ziele)}")
        self._kopf.setWordWrap(True)
        lay.addWidget(self._kopf)

        mitte = QHBoxLayout()
        links = QVBoxLayout()

        was = QGroupBox("Was")
        wl = QVBoxLayout(was)
        self._haekchen: dict[str, QCheckBox] = {}
        for bereich in K.BEREICHE:
            cb = QCheckBox(K.BEREICH_TEXT[bereich])
            cb.setChecked(True)
            cb.toggled.connect(self._neu_rechnen)
            self._haekchen[bereich] = cb
            wl.addWidget(cb)
        if self._umgebung.konsole_gesperrt:
            cb = self._haekchen[K.BEREICH_KONSOLE]
            cb.setChecked(False)
            cb.setEnabled(False)
            cb.setToolTip("Beim Laden der Show konnten Bedienelemente der "
                          "Konsole nicht gebaut werden. Die Konsole wird "
                          "deshalb nicht angefasst.")
        links.addWidget(was)

        wie = QGroupBox("Wie")
        hl = QVBoxLayout(wie)
        self._hinzufuegen = QRadioButton(
            "Hinzufügen — hat das Ziel schon einen Wert, bleibt der")
        self._ersetzen = QRadioButton(
            "Ersetzen — wo die Quelle vorkommt, wird das Ziel überschrieben")
        self._wie = QButtonGroup(self)          # bewusst OHNE Vorauswahl
        self._wie.addButton(self._hinzufuegen)
        self._wie.addButton(self._ersetzen)
        for rb in (self._hinzufuegen, self._ersetzen):
            rb.toggled.connect(self._neu_rechnen)
            hl.addWidget(rb)
        nichts = QLabel("Es wird nichts gelöscht, was das Ziel sonst noch tut.")
        nichts.setStyleSheet("color:#aaa; font-size:11px;")
        hl.addWidget(nichts)
        links.addWidget(wie)

        wo = QGroupBox("Position in Gruppe, Raster und Fächer")
        ol = QVBoxLayout(wo)
        self._ans_ende = QRadioButton("ans Ende")
        self._neben = QRadioButton("neben die Quelle")
        self._wo = QButtonGroup(self)
        self._wo.addButton(self._ans_ende)
        self._wo.addButton(self._neben)
        self._ans_ende.setChecked(True)
        for rb in (self._ans_ende, self._neben):
            rb.toggled.connect(self._neu_rechnen)
            ol.addWidget(rb)
        links.addWidget(wo)
        links.addStretch()
        mitte.addLayout(links)

        rechts = QVBoxLayout()
        self._zaehler = QLabel("")
        self._zaehler.setStyleSheet("padding:4px; font-size:13px;")
        self._zaehler.setTextFormat(Qt.TextFormat.RichText)
        rechts.addWidget(self._zaehler)
        self._liste = QListWidget()
        self._liste.setWordWrap(True)
        self._liste.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        rechts.addWidget(self._liste, stretch=1)
        self._hinweise = QLabel("")
        self._hinweise.setWordWrap(True)
        self._hinweise.setStyleSheet("color:#ffcc44;")
        rechts.addWidget(self._hinweise)
        mitte.addLayout(rechts, stretch=1)
        lay.addLayout(mitte, stretch=1)

        fuss = QHBoxLayout()
        self._sicherung = QLabel(
            "Vorher wird eine Sicherung der Show angelegt („vor dem Klonen“, "
            "zu finden unter Datei → Ältere Version öffnen…). "
            "Rückgängig nimmt das Klonen in einem Schritt zurück.")
        self._sicherung.setWordWrap(True)
        self._sicherung.setStyleSheet("color:#aaa;")
        fuss.addWidget(self._sicherung, stretch=1)
        self._anwenden = QPushButton("Anwenden")
        self._anwenden.setEnabled(False)
        self._anwenden.clicked.connect(self._anwenden_geklickt)
        abbrechen = QPushButton("Abbrechen")
        abbrechen.clicked.connect(self.reject)
        fuss.addWidget(self._anwenden)
        fuss.addWidget(abbrechen)
        lay.addLayout(fuss)

    # ── Rechnen und Anzeigen ─────────────────────────────────────────────────

    def optionen(self) -> K.Optionen:
        wie = (K.HINZUFUEGEN if self._hinzufuegen.isChecked()
               else K.ERSETZEN if self._ersetzen.isChecked() else None)
        return K.Optionen(
            wie=wie,
            bereiche=frozenset(b for b, cb in self._haekchen.items()
                               if cb.isChecked()),
            position=K.POS_NEBEN if self._neben.isChecked() else K.POS_ENDE)

    def plan(self):
        return self._plan

    def _neu_rechnen(self, *_args) -> None:
        self._liste.clear()
        self._plan = None
        opt = self.optionen()
        if opt.wie is None:
            self._zaehler.setText(
                "Bitte wählen: <b>Hinzufügen</b> oder <b>Ersetzen</b> — "
                "dann erscheint hier die Vorschau.")
            self._hinweise.setText("")
            self._anwenden.setEnabled(False)
            return
        try:
            plan = K.plane(self._state, self._quellen, self._ziele, opt,
                           snap_library=self._snaps,
                           palette_manager=self._paletten)
        except K.KlonFehler as e:
            self._zaehler.setText(f"<span style='color:#ff7777'>{e}</span>")
            self._hinweise.setText("")
            self._anwenden.setEnabled(False)
            return
        except Exception as e:                       # noqa: BLE001
            self._zaehler.setText(
                "<span style='color:#ff7777'>Die Vorschau konnte nicht "
                f"berechnet werden ({e}). Es wurde nichts geändert.</span>")
            self._hinweise.setText("")
            self._anwenden.setEnabled(False)
            return
        self._plan = plan
        z = plan.zaehler()
        text = (f"<b style='color:{_FARBEN[K.UNVERAENDERT]}'>"
                f"{z[K.UNVERAENDERT]} unverändert übernommen</b> &middot; "
                f"<b style='color:{_FARBEN[K.UEBERSETZT]}'>"
                f"{z[K.UEBERSETZT]} übersetzt</b> &middot; "
                f"<b style='color:{_FARBEN[K.FAELLT_WEG]}'>"
                f"{z[K.FAELLT_WEG]} fällt weg</b>")
        if z[K.BLEIBT]:
            text += f" &middot; {z[K.BLEIBT]} bleibt, wie es ist"
        self._zaehler.setText(text)
        bereich = None
        for e in plan.eintraege:
            if e.bereich != bereich:
                bereich = e.bereich
                kopf = QListWidgetItem(K.BEREICH_TEXT[bereich])
                schrift = kopf.font()
                schrift.setBold(True)
                kopf.setFont(schrift)
                kopf.setFlags(Qt.ItemFlag.NoItemFlags)
                kopf.setForeground(QBrush(QColor("#dddddd")))
                self._liste.addItem(kopf)
            item = QListWidgetItem(
                f"  {_ZEICHEN[e.kennzeichen]}  {e.zeile}"
                + (f"  [{K.KENNZEICHEN_TEXT[e.kennzeichen]}]"
                   if e.kennzeichen != K.BLEIBT else ""))
            item.setData(Qt.ItemDataRole.UserRole, e.kennzeichen)
            item.setForeground(QBrush(QColor(_FARBEN[e.kennzeichen])))
            self._liste.addItem(item)
        if not plan.eintraege:
            leer = QListWidgetItem(
                "Die Quelle kommt in den gewählten Bereichen nirgends vor.")
            leer.setFlags(Qt.ItemFlag.NoItemFlags)
            self._liste.addItem(leer)
        self._hinweise.setText("\n".join("• " + h for h in plan.hinweise))
        self._anwenden.setEnabled(plan.aenderungen > 0)
        self._anwenden.setText(
            f"Anwenden ({plan.aenderungen} Stellen)" if plan.aenderungen
            else "Anwenden")

    # ── Anwenden ─────────────────────────────────────────────────────────────

    def _anwenden_geklickt(self) -> None:
        plan = self._plan
        if plan is None or not plan.aenderungen:
            return
        if self._umgebung.sichern() is None:
            antwort = QMessageBox.question(
                self, "Keine Sicherung",
                "Die Sicherung der Show konnte nicht angelegt werden.\n\n"
                "Trotzdem klonen? (Rückgängig bleibt möglich.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if antwort != QMessageBox.StandardButton.Yes:
                return
        try:
            self.ergebnis = K.anwenden_mit_rueckweg(
                self._state, plan, davor=self._umgebung.abholen,
                danach=self._umgebung.nachziehen)
        except Exception as e:                       # noqa: BLE001
            try:
                plan.zuruecknehmen(self._state)
            except Exception:
                pass
            QMessageBox.warning(
                self, "Klonen",
                f"Das Klonen ist fehlgeschlagen ({e}).\nBereits geschriebene "
                "Stellen wurden zurückgenommen; die Sicherung „vor dem "
                "Klonen“ liegt unter Datei → Ältere Version öffnen….")
            return
        self.accept()


def klonen_starten(parent, state, quellen, fenster=None) -> int | None:
    """Einstieg: Ziele wählen, dann der Dialog. Liefert die Zahl der
    geänderten Stellen oder ``None`` (abgebrochen)."""
    quellen = [int(q) for q in quellen]
    if not quellen:
        QMessageBox.information(parent, "Klonen",
                                "Bitte zuerst mindestens ein Gerät auswählen.")
        return None
    auswahl = ZielAuswahlDialog(state, quellen, parent)
    if not auswahl.exec():
        return None
    dlg = KlonenDialog(state, quellen, auswahl.ziele(), parent,
                       umgebung=Umgebung(fenster, state))
    if not dlg.exec():
        return None
    return dlg.ergebnis
