"""ENG-35: Auswahlfeld „Stufe“ — ersetzt das Zahlenfeld „Layer-Priorität“.

Zwei Betriebsarten:

* **gebunden** (``StufeAuswahl(funktion)``) — das Feld schreibt die Stufe direkt
  in die Funktion, als EIN Rueckgaengig-Schritt, und zieht nach, wenn die Stufe
  anderswo geaendert wird (Ansicht „Prioritäten“). So steckt es in Szene,
  Chaser, Sequenz, Sammlung, Audio, Skript, Ebenen-Effekt und Carousel.
* **lose** (``StufeAuswahl()``) — das Feld haelt nur die Zahl; der Editor liest
  sie mit ``zahl()`` und setzt sie mit ``setze_zahl()``. So steckt es im Matrix-
  und im Bewegungs-Editor, die auf einer Arbeitskopie rechnen.

Die Eintraege werden einmal gebaut und danach nie im eigenen Signal veraendert.
Passt eine Zahl aus einer alten Show auf keine Stufe, steht sie als eigener
Eintrag „eigene Zahl (n)“ in der Liste und bleibt gespeichert, bis der Nutzer
bewusst eine Stufe waehlt.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QComboBox

from src.core.engine import stufen


class _StufenMelder(QObject):
    """Sagt allen Stufen-Feldern und der Ansicht Bescheid, wenn sich die Stufe
    einer Funktion geaendert hat. Bewusst NICHT ``SyncEvent.FUNCTION_CHANGED``:
    daran haengen Editoren, die sich komplett neu aufbauen — das darf nicht aus
    dem Signal eines ihrer eigenen Felder heraus passieren."""
    geaendert = Signal(object)        # frozenset der Funktions-IDs


_melder: _StufenMelder | None = None


def stufen_melder() -> _StufenMelder:
    global _melder
    if _melder is None:
        _melder = _StufenMelder()
    return _melder


def setze_stufen(zuordnung, rueckgaengig: bool = True) -> int:
    """Setzt ``priority`` fuer mehrere Funktionen — ``zuordnung`` ist eine Liste
    ``(funktion, zahl)``. Alles zusammen ist EIN Rueckgaengig-Schritt. Liefert,
    wie viele Funktionen sich wirklich aendern."""
    plan = []
    for f, zahl in zuordnung:
        if f is None:
            continue
        alt = stufen.zahl_von(getattr(f, "priority", 0))
        neu = int(zahl)
        if alt != neu:
            plan.append((f, alt, neu))
    if not plan:
        return 0
    ids = frozenset(getattr(f, "id", None) for f, _a, _n in plan)

    def tun():
        for f, _a, n in plan:
            f.priority = n
        stufen_melder().geaendert.emit(ids)

    def zurueck():
        for f, a, _n in plan:
            f.priority = a
        stufen_melder().geaendert.emit(ids)

    if rueckgaengig:
        try:
            from src.core.undo import get_undo_stack
            ziele = {n for _f, _a, n in plan}
            wohin = (stufen.stufen_name(next(iter(ziele))) if len(ziele) == 1
                     else "neue Stufen")
            if len(plan) == 1:
                titel = f"Stufe: {getattr(plan[0][0], 'name', '')} → {wohin}"
            else:
                titel = f"Stufe: {len(plan)} Effekte → {wohin}"
            get_undo_stack().push_simple(titel, tun, zurueck)
            # Waehrend eines laufenden Undo/Redo nimmt der Stapel nichts an —
            # dann ist ``tun`` nicht gelaufen. Am Ergebnis pruefen statt raten.
            if all(stufen.zahl_von(f.priority) == n for f, _a, n in plan):
                return len(plan)
        except Exception as e:
            print(f"[stufe_auswahl] undo error: {e}")
    tun()
    return len(plan)


def setze_stufe(funktionen, zahl: int, rueckgaengig: bool = True) -> int:
    """Alle ``funktionen`` auf dieselbe Zahl — EIN Rueckgaengig-Schritt."""
    return setze_stufen([(f, zahl) for f in funktionen], rueckgaengig)


class StufeAuswahl(QComboBox):
    """Auswahlfeld der fuenf Stufen, staerkste oben (wie in der Ansicht)."""

    #: Nur bei einer Auswahl durch den Nutzer — nie beim Laden.
    stufe_gewaehlt = Signal(int)

    TOOLTIP = (
        "Stufe: Schreiben zwei Effekte denselben Kanal, gewinnt die höhere "
        "Stufe. Bei gleicher Stufe gewinnt der zuletzt gestartete Effekt.\n"
        "Snap-Tasten und der Programmer liegen immer über allen Stufen.")

    def __init__(self, funktion=None, parent=None):
        super().__init__(parent)
        self._funktion = funktion
        self._eigene: int | None = None
        for s in reversed(stufen.STUFEN):
            self.addItem(s.name, s.zahl)
            self.setItemData(self.count() - 1, s.hinweis,
                             Qt.ItemDataRole.ToolTipRole)
        self.setToolTip(self.TOOLTIP)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setze_zahl(getattr(funktion, "priority", 0) if funktion is not None
                        else stufen.STUFE_VORGABE.zahl)
        self.activated.connect(self._gewaehlt)
        if funktion is not None:
            stufen_melder().geaendert.connect(self._nachziehen)

    # Das Mausrad darf die Stufe nicht nebenbei verstellen, waehrend man durch
    # einen langen Editor rollt.
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

    def zahl(self) -> int:
        d = self.currentData()
        return stufen.zahl_von(d)

    def setze_zahl(self, zahl) -> None:
        """Wert von aussen setzen (Laden) — ohne Signal."""
        z = stufen.zahl_von(zahl)
        self.blockSignals(True)
        try:
            idx = self.findData(z)
            if idx < 0:
                # Zahl ohne Stufe: als eigenen Eintrag fuehren. Ein schon
                # vorhandener „eigene Zahl“-Eintrag wird umbeschriftet, nicht
                # entfernt — es gibt hoechstens einen.
                text = stufen.stufen_name(z)
                if self._eigene is None:
                    self.insertSeparator(self.count())
                    self.addItem(text, z)
                else:
                    alt = self.findData(self._eigene)
                    self.setItemText(alt, text)
                    self.setItemData(alt, z)
                self._eigene = z
                idx = self.findData(z)
                self.setItemData(
                    idx, "Zahl aus einer älteren Show, die auf keine Stufe "
                         "passt. Sie bleibt erhalten, bis du eine Stufe wählst.",
                    Qt.ItemDataRole.ToolTipRole)
            self.setCurrentIndex(idx)
        finally:
            self.blockSignals(False)

    def _gewaehlt(self, _index: int) -> None:
        z = self.zahl()
        f = self._funktion
        if f is not None:
            setze_stufe([f], z)
        self.stufe_gewaehlt.emit(z)

    def _nachziehen(self, ids) -> None:
        f = self._funktion
        if f is None:
            return
        try:
            if getattr(f, "id", None) in ids:
                z = stufen.zahl_von(getattr(f, "priority", 0))
                if z != self.zahl():
                    self.setze_zahl(z)
        except RuntimeError:
            pass            # Feld schon abgebaut

    def binde(self, funktion) -> None:
        """Feld an eine andere Funktion haengen (Editor zeigt eine neue an)."""
        self._funktion = funktion
        self.setze_zahl(getattr(funktion, "priority", 0))


def stufe_zeile(funktion, parent=None):
    """``(Zeile, Feld)`` — fertige Zeile „Stufe: [Auswahl]“ fuer Editoren, die
    ihre Kopfzeilen von Hand setzen statt ueber ein Formular."""
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
    zeile = QWidget(parent)
    lay = QHBoxLayout(zeile)
    lay.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel("Stufe:")
    lbl.setToolTip(StufeAuswahl.TOOLTIP)
    lay.addWidget(lbl)
    feld = StufeAuswahl(funktion)
    lay.addWidget(feld)
    lay.addStretch(1)
    return zeile, feld
