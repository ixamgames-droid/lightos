"""VIZ-109: rechte Spalte des 3D-Visualizers per Knopf ein- und ausklappen.

Die Spalte (Reiter Fixtures / Bühne / Einstellungen) liess sich bisher nur
verstecken, indem man die Trennleiste des Splitters ganz nach rechts zog — das
findet niemand. ``SpaltenKlappe`` haengt einen sichtbaren Knopf an genau diesen
Splitter:

* **Ein Zustand, eine Quelle.** „Eingeklappt" heisst: der Splitter gibt der
  Spalte die Breite 0. Der Knopf setzt nur Splitter-Groessen; er versteckt,
  entfernt oder baut kein Widget. Die 3D-Ansicht bleibt dasselbe Objekt und
  laedt nicht neu.
* **Von Hand zugezogen zaehlt genauso.** ``splitterMoved`` zieht Pfeil und
  Tooltip nach; eine von Hand gewaehlte Breite wird zur gemerkten Breite.
* **Gemerkt wird geraetegebunden** in ``ui_prefs.json`` — derselbe Weg wie
  Qualitaetsstufe und Strahl-Reichweite des Visualizers
  (``programmer_view._load_prefs`` / ``_save_prefs``).

Das Modul kennt das Visualizer-Fenster nicht; es braucht nur einen
``QSplitter`` mit zwei Widgets und einen Knopf. So laesst es sich ohne
WebEngine testen.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import QSizePolicy, QSplitter, QToolButton

PREF_EINGEKLAPPT = "viz_right_panel_collapsed"
PREF_BREITE = "viz_right_panel_width"

TASTE = "F9"
TIPP_EINKLAPPEN = f"Rechte Spalte einklappen ({TASTE})"
TIPP_AUSKLAPPEN = f"Rechte Spalte ausklappen ({TASTE})"
# Der Pfeil zeigt, wohin die Spalte beim Klick geht: offen -> nach rechts weg.
PFEIL_EINKLAPPEN = "›"
PFEIL_AUSKLAPPEN = "‹"

# Von Hand ziehen feuert splitterMoved je Mausbewegung; geschrieben wird erst,
# wenn die Leiste kurz stillsteht.
_SPEICHER_VERZUG_MS = 300


def _lade_prefs() -> dict:
    try:
        from src.ui.views.programmer_view import _load_prefs
        return _load_prefs() or {}
    except Exception:
        return {}


def _speichere_prefs(werte: dict) -> None:
    try:
        from src.ui.views.programmer_view import _save_prefs
        _save_prefs(werte)
    except Exception as e:
        print(f"[spalte_einklappen] ERROR: Spalten-Zustand nicht gespeichert: {e}")


def baue_knopf(parent=None) -> QToolButton:
    """Schmaler Knopf ueber die ganze Hoehe, direkt links neben der Spalte."""
    knopf = QToolButton(parent)
    knopf.setObjectName("vizSpalteKlappen")
    knopf.setFixedWidth(18)
    knopf.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
    knopf.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # nimmt der 3D-Ansicht keinen Fokus
    knopf.setCursor(Qt.CursorShape.PointingHandCursor)
    # Farben halbtransparent statt fest: passt auf hellem wie dunklem Thema.
    knopf.setStyleSheet(
        "QToolButton#vizSpalteKlappen { border: none; padding: 0;"
        " font-size: 16px; font-weight: bold;"
        " background: rgba(128, 128, 128, 0.22); }"
        "QToolButton#vizSpalteKlappen:hover { background: rgba(128, 128, 128, 0.45); }"
        "QToolButton#vizSpalteKlappen:pressed { background: rgba(128, 128, 128, 0.60); }"
    )
    return knopf


class SpaltenKlappe(QObject):
    """Koppelt Knopf, Splitter und gemerkten Zustand der rechten Spalte."""

    geaendert = Signal(bool)   # True = eingeklappt

    def __init__(self, splitter: QSplitter, knopf: QToolButton,
                 spalten_index: int = 1, parent: QObject | None = None):
        super().__init__(parent if parent is not None else splitter)
        self._splitter = splitter
        self._knopf = knopf
        self._idx = int(spalten_index)
        self._andere = 1 - self._idx

        prefs = _lade_prefs()
        self._eingeklappt = bool(prefs.get(PREF_EINGEKLAPPT, False))
        try:
            self._breite = max(0, int(prefs.get(PREF_BREITE, 0) or 0))
        except (TypeError, ValueError):
            self._breite = 0
        self._erst_anzeige_offen = True

        self._speicher_timer = QTimer(self)
        self._speicher_timer.setSingleShot(True)
        self._speicher_timer.setInterval(_SPEICHER_VERZUG_MS)
        self._speicher_timer.timeout.connect(self.sichern)
        self._grenz_timer = QTimer(self)
        self._grenz_timer.setSingleShot(True)
        self._grenz_timer.setInterval(0)
        self._grenz_timer.timeout.connect(self._auf_hoechstbreite_begrenzen)

        splitter.setCollapsible(self._idx, True)
        knopf.clicked.connect(self.umschalten)
        splitter.splitterMoved.connect(self._on_von_hand_bewegt)
        splitter.installEventFilter(self)

        if self._eingeklappt:
            # Schon vor dem ersten Anzeigen zu: kein Aufblitzen der Spalte.
            groessen = [0, 0]
            groessen[self._andere] = 1
            splitter.setSizes(groessen)
        self._zeige_zustand()

    # ── Abfragen ────────────────────────────────────────────────────────────

    @property
    def eingeklappt(self) -> bool:
        return self._eingeklappt

    @property
    def gemerkte_breite(self) -> int:
        return self._breite

    # ── Bedienung ───────────────────────────────────────────────────────────

    def umschalten(self) -> None:
        self.setze_eingeklappt(not self._eingeklappt)

    def setze_eingeklappt(self, eingeklappt: bool) -> None:
        eingeklappt = bool(eingeklappt)
        groessen = list(self._splitter.sizes())
        if len(groessen) < 2:
            return
        gesamt = sum(groessen)
        if eingeklappt:
            if groessen[self._idx] > 0:
                self._breite = self._begrenzt(groessen[self._idx])
            groessen[self._idx] = 0
            groessen[self._andere] = max(gesamt, 1)
            self._fokus_aus_der_spalte()
        else:
            breite = self._wunsch_breite()
            groessen[self._idx] = breite
            groessen[self._andere] = max(gesamt - breite, 1)
        self._splitter.setSizes(groessen)
        self._eingeklappt = eingeklappt
        if not eingeklappt:
            # Was der Splitter wirklich gegeben hat (Mindest-/Hoechstbreite).
            ist = self._splitter.sizes()[self._idx]
            if ist > 0:
                self._breite = ist
        self._zeige_zustand()
        self.sichern()
        self.geaendert.emit(eingeklappt)

    def sichern(self) -> None:
        """Zustand und Breite sofort in die Einstellungs-Ablage schreiben."""
        self._speicher_timer.stop()
        _speichere_prefs({PREF_EINGEKLAPPT: self._eingeklappt,
                          PREF_BREITE: int(self._breite)})

    # ── intern ──────────────────────────────────────────────────────────────

    def _wunsch_breite(self) -> int:
        spalte = self._splitter.widget(self._idx)
        if spalte is None:
            return max(self._breite, 1)
        if self._breite > 0:
            breite = self._breite
        else:
            breite = max(spalte.minimumWidth(), spalte.sizeHint().width(), 1)
        # Nie breiter als die Spalte werden darf: ``setSizes`` nimmt mehr an,
        # als das Widget fuellt — das gaebe einen leeren Streifen daneben und
        # bei einem unbrauchbar grossen gemerkten Wert eine Ansicht ohne Breite.
        return max(1, min(breite, spalte.maximumWidth()))

    def _begrenzt(self, breite: int) -> int:
        """``breite``, hoechstens die Hoechstbreite der Spalte."""
        spalte = self._splitter.widget(self._idx)
        if spalte is None:
            return breite
        return min(breite, spalte.maximumWidth())

    def _fokus_aus_der_spalte(self) -> None:
        """Eine eingeklappte Spalte behaelt keinen Tastaturfokus.

        Der Splitter versteckt die Spalte nicht, er schiebt sie nur aus dem
        Bild — ein Eingabefeld darin behielte den Fokus. Buchstabentasten
        (S, F …) gingen dann als Texteingabe in ein Feld, das niemand sieht,
        statt die Spalte auszuklappen."""
        spalte = self._splitter.widget(self._idx)
        if spalte is None:
            return
        try:
            fokus = spalte.window().focusWidget()
            if fokus is not None and (fokus is spalte
                                      or spalte.isAncestorOf(fokus)):
                fokus.clearFocus()
        except RuntimeError:          # Widget waehrend des Abbaus
            pass

    def _zeige_zustand(self) -> None:
        zu = self._eingeklappt
        self._knopf.setText(PFEIL_AUSKLAPPEN if zu else PFEIL_EINKLAPPEN)
        tipp = TIPP_AUSKLAPPEN if zu else TIPP_EINKLAPPEN
        self._knopf.setToolTip(tipp)
        self._knopf.setAccessibleName(tipp)

    def _on_von_hand_bewegt(self, *_):
        groessen = self._splitter.sizes()
        if len(groessen) < 2:
            return
        breite = groessen[self._idx]
        zu = breite <= 0
        if not zu:
            self._breite = self._begrenzt(breite)
        wechsel = zu != self._eingeklappt
        self._eingeklappt = zu
        if zu:
            self._fokus_aus_der_spalte()
        self._zeige_zustand()
        self._speicher_timer.start()
        if wechsel:
            self.geaendert.emit(zu)

    def _erste_anzeige(self) -> None:
        """Gemerkten Stand anwenden, sobald der Splitter echte Masse hat."""
        groessen = list(self._splitter.sizes())
        if len(groessen) < 2 or sum(groessen) <= 0:
            return
        gesamt = sum(groessen)
        if self._eingeklappt:
            groessen[self._idx] = 0
            groessen[self._andere] = gesamt
            self._splitter.setSizes(groessen)
        elif self._breite > 0:
            breite = self._wunsch_breite()
            groessen[self._idx] = breite
            groessen[self._andere] = max(gesamt - breite, 1)
            self._splitter.setSizes(groessen)
            ist = self._splitter.sizes()[self._idx]
            if ist > 0:
                self._breite = ist
        else:
            self._auf_hoechstbreite_begrenzen()
        self._zeige_zustand()

    def _auf_hoechstbreite_begrenzen(self) -> bool:
        """Gibt der Splitter der offenen Spalte mehr, als sie fuellen darf,
        geht der Ueberschuss an die andere Seite. Gibt zurueck, ob korrigiert
        wurde.

        Ohne gemerkte Breite verteilt ``QSplitter`` beim ersten Zeigen nach
        dem ``sizeHint()`` der Spalte — und der liegt ueber ihrer
        Hoechstbreite (558 gegen 420 px). Die Spalte selbst wird dann nur 420
        px breit, die restlichen 138 px blieben als leerer Streifen rechts
        stehen, bis man einmal ein- und ausklappte."""
        spalte = self._splitter.widget(self._idx)
        groessen = list(self._splitter.sizes())
        if spalte is None or len(groessen) < 2:
            return False
        hoechst = spalte.maximumWidth()
        if groessen[self._idx] <= hoechst:
            return False
        gesamt = sum(groessen)
        groessen[self._idx] = hoechst
        groessen[self._andere] = max(gesamt - hoechst, 1)
        self._splitter.setSizes(groessen)
        return True

    def eventFilter(self, obj, event):
        if obj is not self._splitter:
            return False
        art = event.type()
        if art == QEvent.Type.Show and self._erst_anzeige_offen:
            self._erst_anzeige_offen = False
            # Erst nach dem Show-Ereignis sind die Groessen verteilt.
            QTimer.singleShot(0, self._erste_anzeige)
        elif (art == QEvent.Type.Resize and not self._eingeklappt
                and not self._erst_anzeige_offen):
            # Der Filter laeuft VOR dem Splitter; geprueft wird deshalb erst,
            # wenn er die neue Breite verteilt hat.
            self._grenz_timer.start()
        return False
