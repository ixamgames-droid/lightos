"""VCB-48: Pop-up-Felder der Virtual Console — gemeinsame Regeln.

Ein **Pop-up-Feld** ist ein normaler :class:`VCFrame` mit der Eigenschaft
„Pop-up-Feld“. Es liegt direkt auf der Canvas, ist beim Laden der Show
geschlossen und wird von einer **Pop-up-Taste** (``ButtonAction.POPUP_TOGGLE``)
geoeffnet und von DERSELBEN Taste wieder geschlossen. Offen liegt es ueber allen
anderen VC-Elementen (Z-Reihenfolge ganz oben); Klicks auf seine Flaeche gehen
nicht an die Elemente darunter.

Die Verknuepfung Taste → Feld laeuft ueber eine stabile Kennung
(``popup_id``, zufaellige Hex-Zeichenkette), nicht ueber den Namen — Umbenennen
bricht sie nicht.

Keine Verschachtelung: ein Pop-up-Feld darf weder eine Pop-up-Taste noch ein
weiteres Pop-up-Feld enthalten. Diese Datei haelt die Pruefungen an EINER
Stelle, damit Rahmen-Dialog, Tasten-Einstellungen, Drag & Drop und Ausloesen
dieselbe Regel anwenden.

Bewusst ohne Qt-Klassenimporte auf Modulebene (kein Importzyklus mit
vc_frame/vc_button) — die Pruefungen arbeiten duck-typed.
"""
from __future__ import annotations

import uuid

HINWEIS_TASTE_IM_POPUP = (
    "Eine Pop-up-Taste darf nicht in einem Pop-up-Feld liegen — "
    "Pop-up-Felder lassen sich nicht verschachteln.")
HINWEIS_FELD_ENTHAELT_POPUP = (
    "Dieses Feld enthält eine Pop-up-Taste oder ein Pop-up-Feld. "
    "Pop-up-Felder lassen sich nicht verschachteln — erst die Pop-up-Taste "
    "herausnehmen oder umstellen.")
HINWEIS_FELD_NICHT_OBEN = (
    "Nur ein Rahmen direkt auf der Konsole kann ein Pop-up-Feld sein, "
    "nicht ein Rahmen in einem anderen Rahmen.")
HINWEIS_ZIEL_FEHLT = (
    "Pop-up-Taste: das zugehörige Pop-up-Feld gibt es nicht (mehr). "
    "In den Einstellungen der Taste ein Feld wählen.")

# Fuer Tests und Diagnose: der zuletzt gezeigte Hinweis.
_letzter_hinweis: str = ""


def neue_kennung() -> str:
    """Stabile Kennung eines Pop-up-Felds (12 Hex-Zeichen)."""
    return uuid.uuid4().hex[:12]


def ist_popup_feld(w) -> bool:
    """True, wenn ``w`` ein Rahmen mit Eigenschaft „Pop-up-Feld“ ist."""
    try:
        return bool(getattr(w, "_popup", False)) and callable(getattr(w, "is_popup", None))
    except RuntimeError:
        return False


def ist_popup_taste(w) -> bool:
    """True, wenn ``w`` eine Taste mit der Aktion „Pop-up-Feld öffnen/schließen“ ist."""
    act = getattr(w, "action", None)
    return getattr(act, "value", act) == "PopupToggle"


def popup_vorfahr(w):
    """Naechstes Pop-up-Feld OBERHALB von ``w`` (``w`` selbst zaehlt nicht) — oder None."""
    p = w.parent() if w is not None else None
    while p is not None:
        if ist_popup_feld(p):
            return p
        p = p.parent()
    return None


def enthaelt_popup_elemente(container) -> bool:
    """True, wenn irgendwo IN ``container`` eine Pop-up-Taste oder ein Pop-up-Feld liegt."""
    from .vc_widget import VCWidget
    try:
        kinder = container.findChildren(VCWidget)
    except RuntimeError:
        return False
    return any(k is not container and (ist_popup_taste(k) or ist_popup_feld(k))
               for k in kinder)


def alle_popups(canvas) -> list:
    """Alle Pop-up-Felder der Canvas (nur direkte Kinder — nur dort sind sie erlaubt)."""
    from PySide6.QtCore import Qt
    from .vc_widget import VCWidget
    if canvas is None:
        return []
    try:
        kinder = canvas.findChildren(
            VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
    except RuntimeError:
        return []
    return [k for k in kinder if ist_popup_feld(k)]


def finde_popup(canvas, kennung: str):
    """Pop-up-Feld mit dieser Kennung — oder None."""
    if not kennung:
        return None
    for f in alle_popups(canvas):
        if getattr(f, "popup_id", "") == kennung:
            return f
    return None


def hinweis(widget, text: str, modal: bool = False) -> None:
    """Hinweis zeigen: Statusleiste des Hauptfensters (falls vorhanden), bei
    ``modal`` zusaetzlich als Meldungsfenster. Nie eine Exception nach aussen."""
    global _letzter_hinweis
    _letzter_hinweis = text
    try:
        win = widget.window() if widget is not None else None
        sb = win.statusBar() if win is not None and hasattr(win, "statusBar") else None
        if sb is not None:
            sb.showMessage(f"⚠ {text}", 6000)
    except Exception:
        pass
    if modal:
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(widget, "Pop-up-Feld", text)
        except Exception:
            pass
    else:
        print(f"[vc_popup] {text}")


def letzter_hinweis() -> str:
    return _letzter_hinweis


def hinweis_zuruecksetzen() -> None:
    global _letzter_hinweis
    _letzter_hinweis = ""
