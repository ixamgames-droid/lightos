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
        print(f"[Visualizer] Spalten-Zustand nicht gespeichert: {e}")


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
                self._breite = groessen[self._idx]
            groessen[self._idx] = 0
            groessen[self._andere] = max(gesamt, 1)
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
        if self._breite > 0:
            return self._breite
        spalte = self._splitter.widget(self._idx)
        if spalte is None:
            return 1
        return max(spalte.minimumWidth(), spalte.sizeHint().width(), 1)

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
            self._breite = breite
        wechsel = zu != self._eingeklappt
        self._eingeklappt = zu
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
            groessen[self._idx] = self._breite
            groessen[self._andere] = max(gesamt - self._breite, 1)
            self._splitter.setSizes(groessen)
            ist = self._splitter.sizes()[self._idx]
            if ist > 0:
                self._breite = ist
        self._zeige_zustand()

    def eventFilter(self, obj, event):
        if (obj is self._splitter and self._erst_anzeige_offen
                and event.type() == QEvent.Type.Show):
            self._erst_anzeige_offen = False
            # Erst nach dem Show-Ereignis sind die Groessen verteilt.
            QTimer.singleShot(0, self._erste_anzeige)
        return False
