"""UI-ADDRCONFLICT: Adresskonflikte sichtbar machen UND auflösen.

Bis hierher war der Konflikt eine Sackgasse: die Patch-Ansicht färbte die Zeilen
rot und schrieb „⚠ 2 Adresskonflikt(e)!" in die Werkzeugleiste, und
``validate_and_repair`` (Check 5) meldete beim Laden dasselbe — **report-only**,
weil eine automatische Umadressierung eine Show still anders klingen lassen
würde. Was fehlte, war der Schritt danach: *welche* Geräte, und wohin damit.

Dieser Dialog listet die überlappenden Paare mit vollen Bereichen und bietet je
Gerät die nächste freie Startadresse an. Die Rechnung dafür ist **nicht neu** —
sie kommt aus ``AppState.suggest_address`` (erste passende Lücke, sonst hinter
dem letzten belegten Kanal, ``None`` wenn es nicht mehr passt), derselben
Quelle, die auch der Patch-Dialog benutzt.

**Bewusst nicht drin: Löschen.** Das Item nennt „Re-Adressieren/Entfernen"; das
Entfernen gibt es in der Patch-Ansicht bereits mit Auswahl, Rückfrage und Undo.
Ein zweiter Löschweg in einem Aufräum-Dialog wäre der gefährlichere: hier klickt
man schnell, und ein Gerät ist kein Adressbereich, sondern hängt an Gruppen,
Szenen und Cues.
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QHeaderView, QAbstractItemView)
from PySide6.QtCore import Qt


def find_conflict_pairs(fixtures) -> list[tuple]:
    """Überlappende Fixture-Paare im selben Universe — ``(a, b)`` je Paar.

    Dieselbe Bedingung wie ``PatchView._find_conflicts`` und
    ``sync.validate_and_repair`` Check 5, nur dass hier das PAAR erhalten
    bleibt: für die Anzeige ist „7 überlappt 12" die Aussage, nicht „7 und 12
    sind irgendwie beteiligt"."""
    paare = []
    liste = list(fixtures or [])
    for i, a in enumerate(liste):
        for b in liste[i + 1:]:
            if a.universe != b.universe:
                continue
            a_end = a.address + a.channel_count - 1
            b_end = b.address + b.channel_count - 1
            if a.address <= b_end and a_end >= b.address:
                paare.append((a, b))
    return paare


class AddressConflictDialog(QDialog):
    """Konflikt-Liste mit „Verschieben"-Aktion je beteiligtem Gerät."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self._state = state
        self.setWindowTitle("Adresskonflikte auflösen")
        self.resize(760, 420)
        lay = QVBoxLayout(self)

        self._lbl = QLabel()
        self._lbl.setWordWrap(True)
        lay.addWidget(self._lbl)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Gerät", "Universe", "Belegt", "Überlappt mit", "Vorschlag"])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self._table, 1)

        zeile = QHBoxLayout()
        self._btn_move = QPushButton("Auf Vorschlag verschieben")
        self._btn_move.setToolTip(
            "Verschiebt das gewählte Gerät auf die nächste freie Startadresse "
            "in seinem Universe (rückgängig machbar).")
        self._btn_move.clicked.connect(self._verschieben)
        self._btn_move_all = QPushButton("Alle verschieben")
        self._btn_move_all.setToolTip(
            "Arbeitet die Liste von oben nach unten ab — nach jedem Schritt "
            "wird neu gerechnet, damit die Vorschläge sich nicht gegenseitig "
            "belegen.")
        self._btn_move_all.clicked.connect(self._alle_verschieben)
        btn_close = QPushButton("Schließen")
        btn_close.clicked.connect(self.accept)
        zeile.addWidget(self._btn_move)
        zeile.addWidget(self._btn_move_all)
        zeile.addStretch()
        zeile.addWidget(btn_close)
        lay.addLayout(zeile)

        self.refresh()

    # ── Inhalt ────────────────────────────────────────────────────────────
    def rows(self) -> list[dict]:
        """Die anzuzeigenden Zeilen — je beteiligtem Gerät eine.

        Getrennt von der Darstellung, damit der Test die Logik ohne Qt-Tabelle
        prüfen kann."""
        try:
            fixtures = list(self._state.get_patched_fixtures())
        except Exception:
            return []
        zeilen = []
        gegner: dict[int, list[int]] = {}
        for a, b in find_conflict_pairs(fixtures):
            gegner.setdefault(a.fid, []).append(b.fid)
            gegner.setdefault(b.fid, []).append(a.fid)
        by_fid = {f.fid: f for f in fixtures}
        for fid in sorted(gegner):
            f = by_fid[fid]
            try:
                vorschlag = self._state.suggest_address(
                    f.universe, f.channel_count, exclude_fid=f.fid)
            except Exception:
                vorschlag = None
            zeilen.append({
                "fid": fid,
                "label": f"[{fid:03d}] {f.label}",
                "universe": f.universe,
                "belegt": f"{f.address}–{f.address + f.channel_count - 1}"
                          f" ({f.channel_count} Kan.)",
                "gegner": ", ".join(str(g) for g in sorted(set(gegner[fid]))),
                "vorschlag": vorschlag,
            })
        return zeilen

    def refresh(self):
        zeilen = self.rows()
        self._table.setRowCount(len(zeilen))
        for r, z in enumerate(zeilen):
            werte = [z["label"], str(z["universe"]), z["belegt"], z["gegner"],
                     str(z["vorschlag"]) if z["vorschlag"] else "— kein Platz"]
            for c, wert in enumerate(werte):
                it = QTableWidgetItem(wert)
                it.setData(Qt.ItemDataRole.UserRole, z["fid"])
                self._table.setItem(r, c, it)
        if zeilen:
            self._lbl.setText(
                f"<b>{len(zeilen)} Gerät(e) überlappen sich.</b> Der Vorschlag "
                f"ist die nächste freie Startadresse im selben Universe — "
                f"Verschieben lässt sich mit Strg+Z zurücknehmen. Das Entfernen "
                f"eines Geräts bleibt bewusst in der Patch-Ansicht.")
            self._table.selectRow(0)
        else:
            self._lbl.setText("<b>Keine Adresskonflikte.</b>")
        hat = bool(zeilen)
        self._btn_move.setEnabled(hat)
        self._btn_move_all.setEnabled(hat)

    # ── Aktionen ──────────────────────────────────────────────────────────
    def _gewaehltes_fid(self):
        it = self._table.currentItem()
        return None if it is None else it.data(Qt.ItemDataRole.UserRole)

    def verschiebe_fid(self, fid) -> bool:
        """Ein Gerät auf seinen aktuellen Vorschlag verschieben. ``False``,
        wenn es keinen gibt (Universe voll) — dann bleibt alles, wie es war."""
        z = next((x for x in self.rows() if x["fid"] == fid), None)
        if z is None or not z["vorschlag"]:
            return False
        return bool(self._state.update_fixture(fid, address=int(z["vorschlag"])))

    def _verschieben(self):
        fid = self._gewaehltes_fid()
        if fid is not None:
            self.verschiebe_fid(fid)
            self.refresh()

    def _alle_verschieben(self):
        """Von oben nach unten, mit Neuberechnung nach jedem Schritt.

        Ein Stapel vorab berechneter Vorschläge wäre falsch: der erste Umzug
        belegt Kanäle, die im zweiten Vorschlag noch als frei galten."""
        for _ in range(len(self.rows()) * 2 + 4):     # Schleifen-Riegel
            offen = [z for z in self.rows() if z["vorschlag"]]
            if not offen:
                break
            if not self.verschiebe_fid(offen[0]["fid"]):
                break
        self.refresh()
