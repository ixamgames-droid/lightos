"""WEB-08: Zugang des Web-Servers zur virtuellen Konsole.

Der Web-Server kennt keine Qt-Klassen und soll keine brauchen. Die Ansicht der
virtuellen Konsole meldet hier ihre Bruecke an
(``src.ui.virtualconsole.vc_fernbedienung.VCFernbedienung``); die Routen in
``src.web.app`` fragen nur dieses Modul.

**Standardmaessig AUS.** Solange es keine Auswahl gibt, welche Widgets aufs
Handy duerfen (die Handy-Seite im VC-Editor, WEB-07), wuerde diese
Schnittstelle JEDES fernbedienbare Widget freigeben. Deshalb liefert sie ohne
die Einstellung ``vc_remote_enabled`` eine leere Liste und fuehrt nichts aus.

Nichts hier wirft: der Aufrufer ist ein Web-Handler, eine Ausnahme waere dort
ein HTTP 500 — oder, schlimmer, eine halb ausgefuehrte Aktion.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_bruecke = None

#: Fehlercode -> HTTP-Status. Unbekannte Codes gelten als 500.
HTTP_STATUS = {
    "abgeschaltet": 403,
    "typ_nicht_erlaubt": 403,
    "nur_am_pult": 403,
    "unbekannte_kennung": 404,
    "aktion_unbekannt": 400,
    "wert_ungueltig": 400,
    "anfrage_ungueltig": 400,
    "keine_konsole": 503,
    "zeitueberschreitung": 504,
    "fehler": 500,
}


def registriere(bruecke) -> None:
    """Die Bruecke der (einen) Konsole anmelden. Die zuletzt angemeldete gilt."""
    global _bruecke
    with _lock:
        _bruecke = bruecke


def abmelden(bruecke) -> None:
    """Abmelden — nur, wenn ``bruecke`` die gerade angemeldete ist. Eine alte
    Ansicht, die spaet abgebaut wird, meldet so nicht die neue mit ab."""
    global _bruecke
    with _lock:
        if _bruecke is bruecke:
            _bruecke = None


def bruecke():
    with _lock:
        return _bruecke


def ist_aktiv() -> bool:
    """Ist die Fernausloesung eingeschaltet? Im Zweifel nein."""
    try:
        from src.web import remote_settings
        return bool(remote_settings.is_vc_remote_enabled())
    except Exception as e:
        print(f"[vc_remote] ERROR: Einstellung nicht lesbar: {e}")
        return False


def _nein(code: str) -> dict:
    return {"ok": False, "fehler": code}


def status_fuer(antwort: dict) -> int:
    """HTTP-Status zu einer Antwort von :func:`widget_aktion`."""
    if antwort.get("ok"):
        return 200
    return HTTP_STATUS.get(str(antwort.get("fehler")), 500)


def widget_liste() -> dict:
    """``{"ok": True, "aktiv": bool, "widgets": [...]}`` — ``widgets`` ist leer,
    solange die Fernausloesung abgeschaltet ist oder keine Konsole laeuft."""
    if not ist_aktiv():
        return {"ok": True, "aktiv": False, "widgets": []}
    b = bruecke()
    if b is None:
        return {"ok": True, "aktiv": True, "widgets": []}
    try:
        eintraege = b.widgets()
    except Exception as e:
        print(f"[vc_remote] ERROR: Widget-Liste: {e}")
        eintraege = []
    return {"ok": True, "aktiv": True,
            "widgets": eintraege if isinstance(eintraege, list) else []}


def widget_aktion(kennung, aktion, wert=None) -> dict:
    """Aktion auf einem Widget. Immer ein Dict mit ``ok``."""
    if not ist_aktiv():
        return _nein("abgeschaltet")
    b = bruecke()
    if b is None:
        return _nein("keine_konsole")
    try:
        antwort = b.aktion(kennung, aktion, wert)
    except Exception as e:
        print(f"[vc_remote] ERROR: Aktion: {e}")
        return _nein("fehler")
    if not isinstance(antwort, dict) or "ok" not in antwort:
        return _nein("fehler")
    return antwort
