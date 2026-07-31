"""VC-IMG: grafischer Galerie-Auswaehler fuer Button-Hintergruende.

QDialog mit einem Raster aus Vorschau-Kacheln (GIF -> QMovie, damit die Kachel
im Dialog animiert; PNG/JPG -> statischer erster Frame). Ein Klick auf eine Kachel
importiert die Grafik in den Asset-Cache (``vc_gallery.import_to_cache``) und
liefert den Content-Hash-Key zurueck; zusaetzlich ``Eigene Datei…`` (Fallback auf
den bisherigen Datei-Dialog) und ``Abbrechen``.

Headless-sicher: der Konstruktor befuellt das Raster ohne ``exec()``; im Test kann
``_choose_gallery(name)`` direkt aufgerufen werden. Fehlt das GIF-Plugin
(offscreen), zeigt die Kachel den statischen ersten Frame — nie ein Crash.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QMovie, QPixmap, QImageReader, QIcon
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QVBoxLayout, QHBoxLayout, QPushButton, QToolButton,
    QLabel, QScrollArea, QWidget, QFileDialog, QTabWidget,
)

from src.core.show import vc_assets, vc_gallery

_THUMB = QSize(112, 112)
_COLS = 4


# VCG-01: Anzeige-Namen + REIHENFOLGE der Reiter. Der Schluessel ist die
# Kategorie aus dem Manifest; was hier fehlt, landet alphabetisch dahinter.
_KAT_TITEL = {
    "pfeile":   "Pfeile",
    "bewegung": "Bewegung",
    "dynamik":  "Dynamik",
    "farbe":    "Farbe",
    "statisch": "Statisch",
}


class VCGalleryDialog(QDialog):
    """Grafischer Auswaehler; nach Annahme steht der Key in ``selected_key``."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Button-Grafik wählen")
        self.selected_key: str | None = None
        self._movies: list[QMovie] = []      # am Leben halten (sonst GC -> keine Animation)

        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "Fertige Effekt-Grafiken — Klick übernimmt sie auf den Button:"))

        # VCG-01 (David-Wunsch 2026-08-01): nach Kategorien gruppiert statt als
        # eine lange Liste. Die Kategorie steht SCHON im Manifest — sie wurde
        # hier nur nie benutzt. Deshalb kein zweites Verzeichnis und keine
        # Namens-Heuristik: die Reiter kommen aus den Daten.
        ents = vc_gallery.entries()
        tabs = QTabWidget(self)
        for kat, liste in self._nach_kategorie(ents):
            scroll = QScrollArea(self)
            scroll.setWidgetResizable(True)
            host = QWidget()
            grid = QGridLayout(host)
            grid.setSpacing(10)
            for i, e in enumerate(liste):
                grid.addWidget(self._make_tile(e), i // _COLS, i % _COLS)
            grid.setRowStretch(grid.rowCount(), 1)
            scroll.setWidget(host)
            tabs.addTab(scroll, f"{_KAT_TITEL.get(kat, kat or 'Sonstige')} ({len(liste)})")
        if not ents:
            leer = QLabel("Keine eingebauten Grafiken gefunden.")
            tabs.addTab(leer, "—")
        root.addWidget(tabs, 1)

        row = QHBoxLayout()
        own = QPushButton("Eigene Datei…")
        own.clicked.connect(self._pick_own_file)
        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(self.reject)
        row.addWidget(own)
        row.addStretch(1)
        row.addWidget(cancel)
        root.addLayout(row)
        self.resize(520, 470)


    @staticmethod
    def _nach_kategorie(ents: list[dict]) -> list[tuple]:
        """``[(kategorie, [eintraege])]`` in stabiler Reihenfolge.

        Bekannte Kategorien zuerst in der Reihenfolge von ``_KAT_TITEL`` (damit
        die Reiter nicht bei jedem neuen Bild springen), unbekannte danach
        alphabetisch — eine neue Kategorie im Manifest taucht also von selbst
        auf, ohne dass hier etwas nachgetragen werden muss.
        """
        gruppen: dict[str, list] = {}
        for e in ents:
            gruppen.setdefault(str(e.get("category") or ""), []).append(e)
        bekannt = [k for k in _KAT_TITEL if k in gruppen]
        rest = sorted(k for k in gruppen if k not in _KAT_TITEL)
        return [(k, gruppen[k]) for k in bekannt + rest]

    # ── Kacheln ───────────────────────────────────────────────────────────────
    def _make_tile(self, entry: dict) -> QToolButton:
        btn = QToolButton(self)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setText(entry.get("title") or entry.get("name", "?"))
        btn.setIconSize(_THUMB)
        btn.setAutoRaise(True)
        btn.setToolTip(entry.get("title") or entry.get("name", ""))
        path = entry["path"]
        if entry.get("kind") == "gif":
            mv = QMovie(path)
            if mv.isValid():
                mv.setScaledSize(_THUMB)
                mv.frameChanged.connect(
                    lambda _f, b=btn, m=mv: b.setIcon(QIcon(m.currentPixmap())))
                mv.start()
                self._movies.append(mv)
            else:
                self._set_static_icon(btn, path)
        else:
            self._set_static_icon(btn, path)
        btn.clicked.connect(
            lambda _=False, name=entry.get("name", ""): self._choose_gallery(name))
        return btn

    def _set_static_icon(self, btn: QToolButton, path: str) -> None:
        try:
            img = QImageReader(path).read()
            if not img.isNull():
                btn.setIcon(QIcon(QPixmap.fromImage(img)))
        except Exception:
            pass

    # ── Auswahl ───────────────────────────────────────────────────────────────
    def _choose_gallery(self, name: str) -> None:
        try:
            self.selected_key = vc_gallery.import_to_cache(name)
        except Exception as e:
            print(f"[vc_gallery_dialog] Galerie-Import fehlgeschlagen: {e}")
            return
        self.accept()

    def _pick_own_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Eigene Bilddatei wählen", "",
            "Bilder (*.png *.jpg *.jpeg *.gif *.webp *.bmp)")
        if not path:
            return
        try:
            self.selected_key = vc_assets.import_file(path)
        except Exception as e:
            print(f"[vc_gallery_dialog] Datei-Import fehlgeschlagen: {e}")
            return
        self.accept()

    # ── Aufraeumen ────────────────────────────────────────────────────────────
    def _stop_movies(self) -> None:
        """Alle Vorschau-GIFs anhalten + Signale trennen (sonst laufen sie nach
        dem Schliessen als verstecktes Button-Kind mit ~12 fps endlos weiter)."""
        for mv in self._movies:
            try:
                mv.stop()
                mv.frameChanged.disconnect()
            except Exception:
                pass
        self._movies.clear()

    def done(self, result: int) -> None:
        # Wird von accept()/reject()/Esc/Fenster-Schliessen aufgerufen -> hier ist
        # der einzige garantierte Punkt, die Animationen zu stoppen.
        self._stop_movies()
        super().done(result)


def pick_bg_image_key(parent=None) -> str | None:
    """Dialog modal oeffnen; liefert den gewaehlten Asset-Key oder ``None``.
    Der Dialog wird danach zuverlaessig entsorgt (kein verstecktes Button-Kind mit
    weiterlaufenden GIF-Timers)."""
    dlg = VCGalleryDialog(parent)
    try:
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        return dlg.selected_key if accepted else None
    finally:
        dlg._stop_movies()      # falls exec ohne done() endet (Ausnahmefall)
        dlg.setParent(None)     # sofort aus der Kind-Liste des Buttons loesen
        dlg.deleteLater()
