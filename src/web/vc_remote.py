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
    "laser_gesperrt": 403,              # WEB-12: Schalter „Laser vom Handy erlauben“ aus
    "blackout_nicht_von_hier": 403,     # WEB-12: Blackout hat jemand anderes gesetzt
    "gruppe_blockiert": 409,            # WEB-14: andere aktive Gruppen-Taste nicht ausschaltbar
    "nur_ueber_socket": 400,            # WEB-12: Halten nur ueber den Socket
    "zu_viele": 429,                    # WEB-15: Grenze je Verbindung erreicht
    "kein_recht": 403,
    "kein_zugang": 403,
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
# WEB-12: Druck und Loslassen DERSELBEN Taste nacheinander — sonst saehen zwei
# Handys, die gleichzeitig druecken, beide „noch niemand haelt“.
# WEB-15: nicht mehr ueber einen globalen Lock, der waehrend des Rundlaufs zur
# Oberflaeche (bis zu ZEITLIMIT_S) gehalten wurde — dahinter warteten das
# Loslassen und der Verbindungsabbau ALLER anderen Handys. Stattdessen traegt
# sich ein laufender Druck/Loslassen je Taste ein (``_im_lauf``); nur ein
# zweiter Druck auf DIESELBE Taste wartet darauf. Loslassen und Abbau warten
# nie: was waehrenddessen ankommt, wird gemerkt und nach dem Druck erledigt.
_im_lauf: dict = {}             # Kennung -> (Verbindung, "druecken"|"loslassen", Event)
_los_nach_druck: set = set()    # (Verbindung, Kennung): nach dem Druck gleich los
_verwaist: set = set()          # Kennungen: letzter Halter ging, waehrend ein Druck lief
#: So lange wartet ein Druck hoechstens auf den laufenden Druck/Loslassen
#: derselben Taste (der Rundlauf selbst ist durch ZEITLIMIT_S begrenzt).
WARTEN_S = 5.0


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


def pult(gm=None, blackout=None, geraet: str = "") -> dict:
    """Grand Master (0..255) und/oder Blackout der Handy-Konsole setzen.
    WEB-12: ``geraet`` = Kennung der Browser-Sitzung; ein Blackout wird nur
    aufgehoben, wenn ihn dieses Geraet gesetzt hat (``fern_pult``)."""
    if not ist_aktiv():
        return _nein("abgeschaltet")
    if gm is None and blackout is None:
        return _nein("anfrage_ungueltig")
    b = bruecke()
    if b is None:
        return _nein("keine_konsole")
    try:
        antwort = b.pult(gm=gm, blackout=blackout, geraet=str(geraet or ""))
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


def _andere_halten(kennung, ausser) -> bool:
    """Haelt eine andere Verbindung als ``ausser`` die Taste? (unter ``_lock``)"""
    return any(kennung in menge for v, menge in _gehalten.items() if v != ausser)


def halten(verbindung, kennung) -> dict:
    """WEB-12: ``verbindung`` drueckt die Halten-Taste ``kennung``.

    Halter werden je Verbindung gezaehlt (Codex zu #1030/#1039/#1041): diese
    Verbindung wird nur dann Halter, wenn IHR Druck die Taste ausgeloest hat
    oder schon ein anderes Handy sie haelt. Haelt sie das Pult (Maus, MIDI),
    bleibt das Pult der einzige Halter — Loslassen oder Abreissen dieses Handys
    laesst sie dann nicht los.

    WEB-15: der Rundlauf zur Oberflaeche laeuft OHNE gehaltenen Lock (s.
    ``_im_lauf``)."""
    while True:
        with _lock:
            if kennung in _gehalten.get(verbindung, ()):
                return {"ok": True}             # haelt schon
            lauf = _im_lauf.get(kennung)
            if lauf is None:
                andere = _andere_halten(kennung, verbindung)
                fertig = threading.Event()
                _im_lauf[kennung] = (verbindung, "druecken", fertig)
                break
        if lauf[0] == verbindung and lauf[1] == "druecken":
            return {"ok": True}                 # derselbe Druck laeuft schon
        if not lauf[2].wait(WARTEN_S):
            return _nein("zeitueberschreitung")
    antwort = _nein("fehler")
    los_jetzt = halter = nachher_los = False
    try:
        antwort = widget_aktion(kennung, "druecken")
    finally:
        with _lock:
            _im_lauf.pop(kennung, None)
            nachher_los = (verbindung, kennung) in _los_nach_druck
            _los_nach_druck.discard((verbindung, kennung))
            verwaist = kennung in _verwaist
            _verwaist.discard(kennung)
            halter = bool(antwort.get("ok")) and bool(
                antwort.get("ausgeloest") or andere or verwaist)
            if halter and not nachher_los:
                _gehalten.setdefault(verbindung, set()).add(kennung)
            elif (halter or verwaist) and not _andere_halten(kennung, verbindung):
                # Finger/Verbindung schon wieder weg, oder der fruehere Halter
                # ging und dieser Druck uebernimmt nicht: niemand haelt mehr.
                los_jetzt = True
        fertig.set()
        if los_jetzt:
            _loslassen({kennung})
    if antwort.get("ok") and not halter:
        antwort = dict(antwort, gehalten_vom_pult=True)
    return antwort


def loslassen_von(verbindung, kennung) -> dict:
    """WEB-12: ``verbindung`` laesst ``kennung`` los. Losgelassen wird die
    Taste nur, wenn diese Verbindung sie hielt UND kein anderes Handy sie noch
    haelt; ein Loslassen ohne vorheriges Halten tut nichts.

    WEB-15: wartet nie auf einen laufenden Druck. Laeuft gerade der EIGENE
    Druck, wird das Loslassen danach nachgeholt; laeuft der Druck eines
    anderen Handys, uebernimmt der (oder laesst los, wenn er nicht Halter
    wird)."""
    with _lock:
        menge = _gehalten.get(verbindung)
        if not menge or kennung not in menge:
            lauf = _im_lauf.get(kennung)
            if lauf is not None and lauf[0] == verbindung and lauf[1] == "druecken":
                _los_nach_druck.add((verbindung, kennung))
                return {"ok": True, "nach_dem_druck": True}
            return {"ok": True, "nicht_gehalten": True}
        menge.discard(kennung)
        if not menge:
            _gehalten.pop(verbindung, None)
        if _andere_halten(kennung, verbindung):
            return {"ok": True, "andere_halten": True}
        if kennung in _im_lauf:
            _verwaist.add(kennung)
            return {"ok": True, "uebergeben": True}
        fertig = threading.Event()
        _im_lauf[kennung] = (verbindung, "loslassen", fertig)
    antwort = _nein("fehler")
    try:
        antwort = widget_aktion(kennung, "loslassen")
    finally:
        with _lock:
            _im_lauf.pop(kennung, None)
        fertig.set()
        if not antwort.get("ok"):
            # Das Loslassen kam nicht an (Oberflaeche antwortete nicht
            # rechtzeitig, Widget inzwischen von der Seite genommen) — die
            # Taste gilt hier aber nicht mehr als gehalten, ein spaeterer
            # Verbindungsabbruch liesse sie also auch nicht mehr los. Deshalb
            # jetzt ueber den Weg, der nicht verfaellt.
            _loslassen({kennung})
    return antwort


def vergessen(kennungen) -> set:
    """WEB-12 (Codex zu #1039): die Tasten werden geloescht oder im Typ
    getauscht — niemand haelt sie mehr. Gibt die Kennungen zurueck, die ein
    Handy gehalten hatte (der Aufrufer laesst sie selbst los)."""
    ziel = set(kennungen or ())
    raus = set()
    with _lock:
        for v in list(_gehalten):
            treffer = _gehalten[v] & ziel
            if treffer:
                raus |= treffer
                _gehalten[v] -= treffer
                if not _gehalten[v]:
                    _gehalten.pop(v, None)
    return raus


def zuschauer_weg(verbindung) -> None:
    """Eine Verbindung ist weg (Abbruch, abgemeldet, Server aus): nicht mehr
    zaehlen und loslassen, was sie gehalten hat — ausser ein anderes Handy
    haelt dieselbe Taste noch (WEB-12). Eine Flash-Taste oder ein Blackout
    bleibt sonst stehen, wenn das Handy das WLAN verliert."""
    with _lock:
        _zuschauer.discard(verbindung)
        kennungen = set()
        for k in _gehalten.pop(verbindung, set()):
            if _andere_halten(k, verbindung):
                continue
            if k in _im_lauf:
                _verwaist.add(k)            # WEB-15: der laufende Druck entscheidet
            else:
                kennungen.add(k)
        for k, (v, art, _e) in _im_lauf.items():
            if v == verbindung and art == "druecken":
                _los_nach_druck.add((v, k))
    _loslassen(kennungen)


def alle_loslassen() -> None:
    """Alles loslassen, was irgendein Handy haelt — beim Ausschalten der
    Handy-Konsole und beim Stoppen des Servers."""
    with _lock:
        kennungen = {k for menge in _gehalten.values() for k in menge}
        _gehalten.clear()
        for k, (v, art, _e) in _im_lauf.items():
            if art == "druecken":
                _los_nach_druck.add((v, k))
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
