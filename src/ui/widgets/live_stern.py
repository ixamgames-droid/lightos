"""UI-129: Sternchen an VC-Tasten und -Fadern, deren Effekt live bearbeitet ist.

Wunsch des Projektinhabers vom 15.11.2026: Wurde ein Effekt live veraendert
(Fader, Aktionstaste, Farb-Kachel, Live-Edit-Panel, MIDI …), bekommt jede Taste
und jeder Fader, der GENAU fuer diesen Effekt zustaendig ist, ein kleines
Sternchen in einer oberen Ecke. Es verschwindet bei „Reset Live", bei der
Uebernahme als neuer Stand/Preset und beim Laden einer Show.

Die Frage „ist der Effekt live bearbeitet?" beantwortet ``effect_live`` (eine
Wahrheit fuer alle Effekttypen). Hier liegt nur, was Taste und Fader teilen:
die Eckenwahl, das Malen und der Tooltip-Zusatz. Kein eigener Timer — die
Konsole zeichnet Tasten/Fader in ihrem 400-ms-Statustakt neu, wenn sich die
Menge der live bearbeiteten Effekte aendert.
"""
from __future__ import annotations

# Kantenlaenge des Sternchens in Pixeln. Es ist eine Anzeige, kein Bedienziel —
# die 44-px-Regel des Touch-Modus gilt fuer Bedienziele, nicht fuer Marken.
STERN_D = 12

# Wie alt der Zwischenstand aus ``effect_live.live_editiert_ids`` beim Malen
# und fuer die Handy-Konsole hoechstens sein darf (Sekunden). Unter dem
# Statustakt der Konsole (400 ms), damit dessen Vergleich frisch rechnet.
STAND_ALTER = 0.3

TOOLTIP_ZUSATZ = ("★ live bearbeitet — weicht vom gespeicherten Stand ab. "
                  "„Reset Live“ verwirft, „Commit“ übernimmt; die Show "
                  "speichert weiter den gespeicherten Stand.")

STERN_FUELLUNG = (255, 212, 0)    # kraeftiges Gelb
STERN_KONTUR = (20, 20, 20)       # fast schwarz: traegt den Stern auf hellen Tasten


def ist_live_editiert_fid(fid) -> bool:
    """Zwischenstand-Abfrage fuer Anzeigen: liegt ``fid`` in der Menge der live
    bearbeiteten Funktionen? Wirft nie."""
    if fid is None:
        return False
    try:
        from src.core.engine import effect_live
        return int(fid) in effect_live.live_editiert_ids(max_alter=STAND_ALTER)
    except Exception:
        return False


def waehle_stern_rect(kandidaten, belegt):
    """Erste Kandidaten-Flaeche, die keine belegte Flaeche schneidet — sonst die
    erste (ein Stern ueber einem Zeichen ist besser als gar keiner).
    ``kandidaten``/``belegt``: Listen von QRect (None in ``belegt`` wird
    uebersprungen)."""
    belegt = [r for r in belegt if r is not None and not r.isEmpty()]
    for k in kandidaten:
        if not any(k.intersects(b) for b in belegt):
            return k
    return kandidaten[0]


def zeichne_live_stern(p, rect) -> None:
    """Malt einen fuenfzackigen gelben Stern mit dunkler Kontur in ``rect``."""
    import math
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QPen, QPolygonF
    cx = rect.x() + rect.width() / 2.0
    cy = rect.y() + rect.height() / 2.0 + 0.5
    aussen = min(rect.width(), rect.height()) / 2.0
    innen = aussen * 0.45
    punkte = []
    for i in range(10):
        r = aussen if i % 2 == 0 else innen
        w = -math.pi / 2 + i * math.pi / 5
        punkte.append(QPointF(cx + r * math.cos(w), cy + r * math.sin(w)))
    p.save()
    p.setRenderHint(p.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor(*STERN_KONTUR), 1.6))
    p.setBrush(QColor(*STERN_FUELLUNG))
    p.drawPolygon(QPolygonF(punkte))
    p.restore()


def tooltip_mit_stern(basis: str) -> str:
    """Normaler Tooltip des Widgets plus der Zusatz „live bearbeitet"."""
    basis = (basis or "").strip()
    return f"{basis}\n{TOOLTIP_ZUSATZ}" if basis else TOOLTIP_ZUSATZ


def zeige_live_stern_tooltip(widget, event) -> bool:
    """Fuer ``event()`` von Taste/Fader: zeigt beim Tooltip-Ereignis den eigenen
    Tooltip mit dem Zusatz „live bearbeitet", solange das Sternchen steht.
    Sonst False — der normale Tooltip bleibt unberuehrt."""
    from PySide6.QtCore import QEvent
    if event.type() != QEvent.Type.ToolTip:
        return False
    try:
        if not widget.live_stern_sichtbar():
            return False
    except Exception:
        return False
    from PySide6.QtWidgets import QToolTip
    QToolTip.showText(event.globalPos(), tooltip_mit_stern(widget.toolTip()), widget)
    return True
