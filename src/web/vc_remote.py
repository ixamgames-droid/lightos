"""WEB-08: Zugang des Web-Servers zur virtuellen Konsole.

Der Web-Server kennt keine Qt-Klassen und soll keine brauchen. Die Ansicht der
virtuellen Konsole meldet hier ihre Bruecke an
(``src.ui.virtualconsole.vc_fernbedienung.VCFernbedienung``); die Routen in
``src.web.app`` fragen nur dieses Modul.

**Standardmaessig AUS** (Einstellung ``vc_remote_enabled``, im Dialog
„Web-Remote: Verbindung & Token" als „Handy-Konsole"). Ohne sie liefert die
Schnittstelle eine leere Liste und fuehrt nichts aus.

**WEB-09: nur was auf einer Handy-Seite liegt.** Auch eingeschaltet gibt diese
Schicht nie die ganze Konsole frei: jeder Aufruf an die Bruecke traegt
``nur_handy_seiten=True``. Ein Widget ausserhalb der Seiten ist fuer das Handy
nicht sichtbar und nicht bedienbar (``nicht_freigegeben``, HTTP 403).

**WEB-09: Rueckmeldung.** Der Web-Server meldet hier an, wie er eine Nachricht
an alle zuschauenden Handys schickt (:func:`setze_sender`) und wie viele gerade
zuschauen (:func:`zuschauer_dazu`/:func:`zuschauer_weg`). Die Bruecke fragt
:func:`zuschauer` und gibt Aenderungen ueber :func:`melde` ab. Welche Tasten
ein Handy gerade HAELT, steht ebenfalls hier (:func:`gehalten_merken`): reisst
die Verbindung ab, werden genau diese losgelassen.

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
    "nicht_freigegeben": 403,
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
        eintraege = b.widgets(nur_handy_seiten=True)
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
        antwort = b.aktion(kennung, aktion, wert, nur_handy_seiten=True)
    except Exception as e:
        print(f"[vc_remote] ERROR: Aktion: {e}")
        return _nein("fehler")
    if not isinstance(antwort, dict) or "ok" not in antwort:
        return _nein("fehler")
    return antwort


# ── WEB-09: Handy-Konsole ────────────────────────────────────────────────────

_sender = None                  # fn(ereignis, daten) -> an alle Zuschauer
_zuschauer: set = set()         # Verbindungen, die die Konsole anzeigen
_gehalten: dict = {}            # Verbindung -> Kennungen gehaltener Tasten


def konsole() -> dict:
    """Vollstaendiger Stand der Handy-Konsole:
    ``{"ok": True, "aktiv": bool, "seiten": [...], "widgets": {...},
    "gm": 0..255, "blackout": bool, "rev": int}``. Abgeschaltet oder ohne
    Konsole: keine Seiten."""
    leer = {"ok": True, "aktiv": False, "seiten": [], "widgets": {},
            "gm": 255, "blackout": False, "rev": 0}
    if not ist_aktiv():
        return leer
    leer["aktiv"] = True
    b = bruecke()
    if b is None:
        return leer
    try:
        k = b.konsole()
    except Exception as e:
        print(f"[vc_remote] ERROR: Konsole: {e}")
        k = None
    if not isinstance(k, dict):
        return leer
    return {"ok": True, "aktiv": True, **k}


def pult(gm=None, blackout=None) -> dict:
    """Grand Master (0..255) und/oder Blackout der Handy-Konsole setzen."""
    if not ist_aktiv():
        return _nein("abgeschaltet")
    if gm is None and blackout is None:
        return _nein("anfrage_ungueltig")
    b = bruecke()
    if b is None:
        return _nein("keine_konsole")
    try:
        antwort = b.pult(gm=gm, blackout=blackout)
    except Exception as e:
        print(f"[vc_remote] ERROR: Pult: {e}")
        return _nein("fehler")
    if not isinstance(antwort, dict) or "ok" not in antwort:
        return _nein("fehler")
    return antwort


def setze_sender(fn) -> None:
    """Der Web-Server meldet an (oder mit None ab), wie eine Nachricht an alle
    zuschauenden Handys geht. Wird aus dem UI-Thread gerufen — ``fn`` muss das
    vertragen (Socket.IO im Thread-Modus tut es)."""
    global _sender
    with _lock:
        _sender = fn
        if fn is None:
            _zuschauer.clear()


def melde(ereignis: str, daten: dict) -> bool:
    """Nachricht an alle Zuschauer. False, wenn nichts gesendet wurde
    (abgeschaltet, kein Server, Fehler). Wirft nicht."""
    with _lock:
        fn = _sender
    if fn is None or not ist_aktiv():
        return False
    try:
        fn(ereignis, daten)
        return True
    except Exception as e:
        print(f"[vc_remote] ERROR: Meldung '{ereignis}': {e}")
        return False


def zuschauer() -> int:
    with _lock:
        return len(_zuschauer)


def zuschauer_dazu(verbindung) -> None:
    with _lock:
        _zuschauer.add(verbindung)


def gehalten_merken(verbindung, kennung, gehalten: bool) -> None:
    """Merkt, dass ``verbindung`` die Taste ``kennung`` haelt (oder nicht mehr)."""
    with _lock:
        menge = _gehalten.setdefault(verbindung, set())
        if gehalten:
            menge.add(kennung)
        else:
            menge.discard(kennung)
            if not menge:
                _gehalten.pop(verbindung, None)


def gehaltene(verbindung=None) -> set:
    """Kennungen, die ``verbindung`` haelt — ohne Angabe: die aller Verbindungen."""
    with _lock:
        if verbindung is not None:
            return set(_gehalten.get(verbindung, ()))
        return {k for menge in _gehalten.values() for k in menge}


def zuschauer_weg(verbindung) -> None:
    """Eine Verbindung ist weg (Abbruch, abgemeldet, Server aus): nicht mehr
    zaehlen und ALLES loslassen, was sie gehalten hat. Eine Flash-Taste oder
    ein Blackout bleibt sonst stehen, wenn das Handy das WLAN verliert."""
    with _lock:
        _zuschauer.discard(verbindung)
        kennungen = _gehalten.pop(verbindung, set())
    _loslassen(kennungen)


def alle_loslassen() -> None:
    """Alles loslassen, was irgendein Handy haelt — beim Ausschalten der
    Handy-Konsole und beim Stoppen des Servers."""
    with _lock:
        kennungen = {k for menge in _gehalten.values() for k in menge}
        _gehalten.clear()
    _loslassen(kennungen)


def loslassen(kennungen) -> None:
    """Tasten loslassen, die ein Handy gehalten hat — ohne auf die Oberflaeche
    zu warten und ohne zu verfallen. Fuer ein Loslassen, das ueber den normalen
    Weg nicht ankam. Der Aufrufer stellt sicher, dass das Handy sie hielt."""
    _loslassen(set(kennungen or ()))


def _loslassen(kennungen) -> None:
    if not kennungen:
        return
    b = bruecke()
    if b is None:
        return
    try:
        b.loslassen(sorted(kennungen))
    except Exception as e:
        print(f"[vc_remote] ERROR: Loslassen: {e}")


def einstellung_geaendert() -> None:
    """Nach dem Umschalten von „Handy-Konsole" rufen: beim Ausschalten wird
    losgelassen, was gehalten wird, und die Handys erfahren es sofort (ihre
    Anzeige sperrt sich). Beim Einschalten holen sie sich den Stand neu."""
    aktiv = ist_aktiv()
    if not aktiv:
        alle_loslassen()
    with _lock:
        fn = _sender
    if fn is None:
        return
    try:
        fn("vc_konsole", konsole() if aktiv else
           {"ok": True, "aktiv": False, "seiten": [], "widgets": {},
            "gm": 255, "blackout": False, "rev": 0})
    except Exception as e:
        print(f"[vc_remote] ERROR: Meldung Einstellung: {e}")
