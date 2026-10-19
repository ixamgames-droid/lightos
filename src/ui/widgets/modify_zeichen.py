"""ENG-37-B: Zeichen und Farben der Modify-Betriebsart — EINE Quelle fuer die
Matrix-Vorschau im Editor und die Konsole (VC-Taste, VC-Fader).

Entscheidung des Projektinhabers vom 19.10.2026: Eine Taste, deren Funktion ein
Modify-Effekt ist, zeigt unten links das Zeichen der Betriebsart — „+" Addieren,
„−" Abziehen, „◐" Abdunkeln — in den Farben, mit denen die Editor-Vorschau einen
Dimmer-Modify einfaerbt (Bernstein / Blau / Grau).

Kein Qt-Zeichnen ohne Aufrufer: ``modify_arten`` ist reine Logik (testbar ohne
Fenster), ``zeichne_modify_zeichen`` malt nur auf einen uebergebenen QPainter.
"""
from __future__ import annotations

from src.core.engine.modify import (MODIFY_ADD, MODIFY_DIM, MODIFY_LABELS,
                                    MODIFY_SUB, normalize_mode)
from src.core.engine.stufen import ist_modify

# Volle Helligkeit der Vorschau-Farbe je Betriebsart (rgb_matrix_view.paintEvent
# skaliert sie mit dem Betrag der Zelle).
MODIFY_VORSCHAU_RGB: dict[str, tuple[int, int, int]] = {
    MODIFY_ADD: (255, 176, 0),     # Bernstein: kommt dazu
    MODIFY_SUB: (64, 140, 255),    # Blau: geht weg
    MODIFY_DIM: (200, 200, 200),   # Grau (in der Vorschau schraffiert)
}

MODIFY_ZEICHEN: dict[str, str] = {
    MODIFY_ADD: "+",
    MODIFY_SUB: "−",
    MODIFY_DIM: "◐",
}

MODIFY_ART_NAMEN: dict[str, str] = MODIFY_LABELS


def modify_art_von(funktion) -> str | None:
    """Betriebsart (``add``/``sub``/``dim``), wenn ``funktion`` als Modify-Effekt
    verrechnet wird — sonst ``None`` (auch fuer den blossen Haken bei einem Stil
    ohne Modify, z. B. Shutter)."""
    if funktion is None or not ist_modify(funktion):
        return None
    return normalize_mode(getattr(funktion, "modify_mode", MODIFY_ADD))


def modify_arten(fids, fm) -> list[str]:
    """Betriebsarten der Modify-Effekte unter ``fids`` (Reihenfolge wie die IDs,
    ohne Doppelte). Unbekannte IDs und Nicht-Modify-Funktionen fallen weg."""
    arten: list[str] = []
    for fid in fids or ():
        try:
            f = fm.get(int(fid))
        except Exception:
            f = None
        art = modify_art_von(f)
        if art is not None and art not in arten:
            arten.append(art)
    return arten


def modify_tooltip(arten) -> str:
    """Erklaerung zum Zeichen (fuer Tooltips / Barrierefreiheit)."""
    if not arten:
        return ""
    namen = ", ".join(MODIFY_ART_NAMEN[a] for a in arten)
    return (f"Modify-Effekt ({namen}): verrechnet sich mit dem, was schon läuft, "
            "statt es zu ersetzen.")


def modify_signatur(funktionen) -> tuple:
    """Kurze Signatur aller Modify-Effekte (ID, Betriebsart) — die Konsole zeichnet
    ihre Widgets neu, sobald sie sich aendert (Haken oder Betriebsart umgestellt)."""
    out = []
    for f in funktionen or ():
        art = modify_art_von(f)
        if art is not None:
            out.append((getattr(f, "id", None), art))
    return tuple(out)


def zeichne_modify_zeichen(p, x: int, y: int, arten, hoehe: int = 15) -> int:
    """Malt die Zeichen ``arten`` ab (x, y) nach rechts — je ein dunkles Kaestchen
    mit dem Zeichen in der Vorschau-Farbe (lesbar auf jeder Tastenfarbe und auf
    Hintergrundbildern). Gibt die belegte Breite zurueck (0 ohne Arten)."""
    if not arten:
        return 0
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QFont, QPen
    p.save()
    p.setRenderHint(p.RenderHint.Antialiasing, True)
    font = QFont("Segoe UI", 10, QFont.Weight.Bold)
    font.setPixelSize(max(10, hoehe - 1))
    p.setFont(font)
    breite = hoehe
    cx = x
    for art in arten:
        r = QRect(cx, y, breite, hoehe)
        p.setPen(QPen(QColor(0, 0, 0, 200), 1))
        p.setBrush(QColor(13, 17, 23, 210))          # #0d1117, LightOS-Grund
        p.drawRoundedRect(r, 3, 3)
        p.setPen(QColor(*MODIFY_VORSCHAU_RGB[art]))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, MODIFY_ZEICHEN[art])
        cx += breite + 2
    p.restore()
    return cx - x - 2
