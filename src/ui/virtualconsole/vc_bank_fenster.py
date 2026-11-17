"""VCB-45 Schritt 2/3: eine Bank der Virtual Console als eigenes Fenster.

Was im Code eine **Bank** ist: jedes VC-Widget traegt ``bank`` (0..9, ``-1``
= auf allen Baenken bzw. von einem Kasten geerbt). ``VCCanvas._active_bank``
ist die Bank, die die Flaeche zeigt; sie folgt der Executor-Seite der
Wiedergabe (``playback_engine.set_page`` / ``subscribe_page``) — dieselbe
Seite, die die Seitentasten des APC umschalten. MIDI und Tastenkuerzel
erreichen nur Widgets der aktiven Bank (``VCCanvas.on_active_bank``).

Eine **geloeste** Bank zieht ihre obersten Widgets (direkt auf der Flaeche,
``bank == n``) in ein eigenes Fenster um. Das Fenster ist ein Qt-Fenster
MIT der Flaeche als Eltern-Objekt: es liegt als eigenes Fenster auf dem
Bildschirm (z. B. dem Touch-Bildschirm unten), bleibt aber im Objektbaum der
Flaeche. Dadurch finden Speichern, MIDI, Tastenkuerzel, Kennungen und alles,
was ``findChildren`` benutzt, die Widgets weiter; nur wo die Flaeche ihre
DIREKTEN Kinder zaehlt, nimmt sie die geloesten ausdruecklich dazu
(``VCCanvas.oberste_widgets``).

Sichtbarkeit: Widgets einer geloesten Bank sind immer sichtbar
(``VCCanvas.bank_sichtbar``) — oben im Hauptfenster weiterblaettern laesst
das Fenster stehen. MIDI/Tastenkuerzel bleiben an die aktive Bank gebunden:
das APC bedient wie bisher die Seite, die oben gewaehlt ist.

Die Lage des Fensters merkt sich ``popout_lage`` je Bank
(``vc_bank_lagen`` in ``ui_prefs.json``) — Arbeitsplatz-Einstellung, kein
Show-Inhalt: dieselbe Show auf einem Laptop mit einem Bildschirm soll nicht
nach einem zweiten Bildschirm verlangen.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from src.ui.abbau import abbau_still

#: Hintergrund wie die Flaeche (``VCCanvas._bg``).
_HINTERGRUND = "#0d1117"
#: Rand um den Inhalt, damit nichts am Fensterrand klebt.
_RAND = 16


class BankFlaeche(QWidget):
    """Traeger der Widgets einer geloesten Bank (im Scrollbereich).

    Absichtlich OHNE ``on_active_bank``/``add_live_controls``: die Widgets
    suchen ihre Flaeche ueber die Eltern-Kette und sollen dabei die echte
    ``VCCanvas`` finden, nicht diesen Traeger."""

    def __init__(self, bank: int, parent=None):
        super().__init__(parent)
        self.bank_nummer = int(bank)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_HINTERGRUND))
        self.setPalette(pal)
        # UI-117: Wisch am Finger auf der freien Flaeche scrollt (wie oben).
        self.setProperty("ziehen_scrollen_finger", True)

    def groesse_anpassen(self) -> None:
        """Mindestgroesse = Inhalt + Rand (Scrollweg bei kleinem Fenster)."""
        rechts, unten = 200, 120
        for w in self.children():
            if not isinstance(w, QWidget) or not hasattr(w, "to_dict"):
                continue
            try:
                g = w.geometry()
            except RuntimeError:
                continue
            rechts = max(rechts, g.right() + _RAND)
            unten = max(unten, g.bottom() + _RAND)
        self.setMinimumSize(QSize(rechts, unten))
        self.resize(max(rechts, self.width()), max(unten, self.height()))


class _BankScroll(QScrollArea):
    """Scrollbereich: ``widgetResizable`` bleibt AUS (harte VC-Invariante,
    s. ``GrowingScrollArea``); der Traeger waechst selbst auf das Fenster."""

    def resizeEvent(self, event):  # noqa: N802 (Qt-API)
        super().resizeEvent(event)
        w = self.widget()
        if w is None:
            return
        vp = self.viewport().size()
        m = w.minimumSize()
        w.resize(max(m.width(), vp.width()), max(m.height(), vp.height()))


class BankFenster(QWidget):
    """Eigenes Fenster einer geloesten Bank (Kind der ``VCCanvas``)."""

    def __init__(self, canvas, bank: int):
        super().__init__(canvas, Qt.WindowType.Window)
        self._canvas = canvas
        self.bank = int(bank)
        self._lage_merker = None
        self._andocken_laeuft = False
        self.setWindowTitle(f"Virtual Console — Bank {self.bank + 1}")
        self.resize(1280, 800)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        leiste = QWidget(self)
        leiste.setStyleSheet("background:#161b22;")
        ll = QHBoxLayout(leiste)
        ll.setContentsMargins(8, 4, 8, 4)
        self.etikett = QLabel(f"Bank {self.bank + 1} — gelöst", leiste)
        self.etikett.setStyleSheet("color:#e6edf3; font-weight:bold;")
        ll.addWidget(self.etikett)
        ll.addStretch(1)
        from .vc_style import touch_aktiv
        self.knopf_andocken = QPushButton("⇱ Andocken", leiste)
        self.knopf_andocken.setToolTip(
            "Bank zurück in die Virtual Console im Hauptfenster legen")
        self.knopf_andocken.setMinimumHeight(44 if touch_aktiv() else 28)
        self.knopf_andocken.setMinimumWidth(120 if touch_aktiv() else 0)
        self.knopf_andocken.clicked.connect(self.close)
        ll.addWidget(self.knopf_andocken)
        lay.addWidget(leiste)

        self.scroll = _BankScroll(self)
        self.scroll.setWidgetResizable(False)
        self.scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:{_HINTERGRUND}; }}")
        self.flaeche = BankFlaeche(self.bank)
        self.scroll.setWidget(self.flaeche)
        lay.addWidget(self.scroll)

    # Lage merken (wie das Popout, aber je Bank) ---------------------------

    def _lage_anstossen(self):
        m = self._lage_merker
        if m is not None:
            m.angestossen()

    def moveEvent(self, event):  # noqa: N802 (Qt-API)
        super().moveEvent(event)
        self._lage_anstossen()

    def resizeEvent(self, event):  # noqa: N802 (Qt-API)
        super().resizeEvent(event)
        self._lage_anstossen()

    @abbau_still
    def changeEvent(self, event):  # noqa: N802 (Qt-API)
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._lage_anstossen()

    @abbau_still
    def closeEvent(self, event):  # noqa: N802 (Qt-API)
        """Schliessen = andocken: die Widgets gehen zurueck auf die Flaeche."""
        try:
            if self._lage_merker is not None:
                self._lage_merker.sichern()
        except Exception as e:
            print(f"[VC] Lage von Bank {self.bank + 1} nicht gemerkt: {e}")
        if not self._andocken_laeuft:
            cv = self._canvas
            try:
                cv.bank_andocken(self.bank, merken=False)
            except RuntimeError:
                pass
        event.accept()

    def widgets(self) -> list:
        """Die obersten VC-Widgets dieser Bank (in Stapel-Reihenfolge)."""
        from .vc_widget import VCWidget
        try:
            return list(self.flaeche.findChildren(
                VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly))
        except RuntimeError:
            return []


def zeige(fenster: BankFenster, haupt=None) -> None:
    """Fenster am gemerkten Platz dieser Bank oeffnen — ohne Gemerktes und mit
    zwei Bildschirmen maximiert auf dem anderen Bildschirm als das
    Hauptfenster (wie das Popout). Scheitert die Rechnung: einfach zeigen."""
    try:
        from . import popout_lage as pl
        ablage = pl.BankAblage(fenster.bank)
        paare = pl.lies_bildschirme()
        lage = pl.ziel_lage([b for b, _ in paare], ablage.lade(),
                            pl.haupt_index(paare, haupt) if haupt is not None else 0)
        fenster._lage_merker = pl.baue_merker(fenster, lage, haupt, ablage)
        qscreen = paare[lage.bildschirm][1] if paare else None
        pl.oeffne(fenster, lage, qscreen)
    except Exception as e:
        print(f"[VC] Lage von Bank {fenster.bank + 1} nicht wiederhergestellt: {e}")
        fenster.show()
