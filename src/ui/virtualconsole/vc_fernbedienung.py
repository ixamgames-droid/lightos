"""WEB-08: Fernausloesung eines VC-Widgets ueber seine Kennung.

Die Handy-Konsole (WEB-07, Konzept A) zeigt keine eigenen Tasten, sondern
Verknuepfungen auf Widgets der grossen Konsole. Das Handy „drueckt" also das
Original — gleiche Funktion, gleicher Zustand, auch wenn das Widget auf einer
anderen Bank oder in einem Kasten liegt.

Drei Dinge leistet diese Schicht:

* :func:`beschreibe` — was ein Widget aus der Ferne kann und in welchem Zustand
  es ist (Typ, Beschriftung, Farbe, gedrueckt/aktiv, Fader-Wert, laufende Cue).
* :func:`ausfuehren` — eine Aktion ueber den Weg, den auch ein Klick nimmt.
* :class:`VCFernbedienung` — die Uebergabe in den UI-Thread. Der Web-Server
  laeuft in einem eigenen Thread; Widgets duerfen nur im UI-Thread angefasst
  werden.

Fernbedienbar sind in diesem Schritt Taste, Fader und Cueliste. Alles andere
(XY-Pad, Encoder, Tempo-Regler, Anzeigen, Kaesten) wird sauber abgelehnt.

**Bearbeiten-Modus und Touch-Sperre** gelten hier nicht — wie bei MIDI und
Tastatur: beide betreffen nur Maus und Finger am Pult.

**Sicherheit**

* *Blackout* verhaelt sich wie an der Taste (gehalten = dunkel, losgelassen =
  wieder hell) und damit wie im bestehenden Web-Remote, dessen
  ``/api/blackout`` ebenfalls setzt UND aufhebt. Die Fernausloesung kann hier
  nichts, was die feste Web-Remote-Seite nicht schon konnte.
* *Laser NOT-AUS* ist ausloesbar. Die Taste kennt nur diese eine Richtung
  (dunkel + unscharf); aufheben kann sie nichts.
* *Laser scharf/unscharf*: aus der Ferne nur UNSCHARF. Scharf geschaltet wird
  am Pult — dort steht jemand, der den Raum sieht. Das Web-Remote konnte den
  Laser bisher nicht scharf schalten, und dabei bleibt es.
* *Laser-Muster abrufen* ist nicht fernbedienbar: auf DMX-Lasern wirkt ein
  Muster ohne Scharfschaltung direkt auf die Ausgabe.
"""
from __future__ import annotations

import math
import threading

from PySide6.QtCore import QObject, Signal

from .vc_widget import kennung_gueltig

# Fehlercodes — die Web-Schicht bildet sie auf HTTP-Status ab.
UNBEKANNTE_KENNUNG = "unbekannte_kennung"
TYP_NICHT_ERLAUBT = "typ_nicht_erlaubt"
AKTION_UNBEKANNT = "aktion_unbekannt"
WERT_UNGUELTIG = "wert_ungueltig"
NUR_AM_PULT = "nur_am_pult"
KEINE_KONSOLE = "keine_konsole"
ZEITUEBERSCHREITUNG = "zeitueberschreitung"
FEHLER = "fehler"

AKTIONEN_TASTE = ["druecken", "loslassen", "umschalten"]
AKTIONEN_FADER = ["setzen"]
AKTIONEN_CUELISTE = ["go", "back", "stop"]


def _nein(code: str) -> dict:
    return {"ok": False, "fehler": code}


def _art(widget) -> str | None:
    """Fernbedien-Art eines Widgets: 'taste' | 'fader' | 'cueliste' | None.

    Ueber den Klassennamen statt ``isinstance`` — die Widget-Module werden so
    nicht alle importiert, nur um eine Liste zu filtern.
    """
    name = type(widget).__name__
    if name == "VCButton":
        from .vc_button import ButtonAction
        if getattr(widget, "action", None) == ButtonAction.LASER_PATTERN:
            return None             # s. Modulkopf, Sicherheit
        return "taste"
    if name == "VCSlider":
        return "fader"
    if name == "VCCueList":
        return "cueliste"
    return None


def _farbe(widget, attr: str) -> str | None:
    try:
        return getattr(widget, attr).name()
    except Exception:
        return None


def _gruppe(widget) -> str | None:
    """Beschriftung des umschliessenden Kastens (None = direkt auf der Flaeche)."""
    try:
        p = widget.parent()
        if p is not None and type(p).__name__ == "VCFrame":
            return str(getattr(p, "caption", "") or "")
    except Exception:
        pass
    return None


def _halteart(widget) -> str:
    """Wie eine Taste bedient wird: 'halten' wirkt nur, solange sie gedrueckt
    ist — das Handy muss dort Druck UND Loslassen senden statt eines Tipps."""
    from .vc_button import ButtonAction as A
    a = getattr(widget, "action", None)
    if a in (A.FLASH, A.FUNCTION_FLASH, A.BLACKOUT, A.ALL_WHITE):
        return "halten"
    if a == A.LIBRARY_SNAP and getattr(widget, "snap_mode", "") == "flash":
        return "halten"
    return "tippen"


def _cue_auskunft(cue) -> dict | None:
    if cue is None:
        return None
    try:
        nummer = float(getattr(cue, "number", 0) or 0)
    except (TypeError, ValueError):
        nummer = 0.0
    return {"nummer": nummer, "name": str(getattr(cue, "label", "") or "")}


def beschreibe(widget) -> dict | None:
    """Fernbedien-Auskunft zu einem Widget — oder None, wenn es nicht
    fernbedienbar ist. Nur JSON-taugliche Werte. Im UI-Thread aufrufen."""
    art = _art(widget)
    if art is None:
        return None
    d = {
        "id": widget.widget_id,
        "typ": art,
        "beschriftung": str(getattr(widget, "caption", "") or ""),
        "farbe": _farbe(widget, "_bg_color"),
        "textfarbe": _farbe(widget, "_fg_color"),
        "bank": int(getattr(widget, "bank", -1)),
        "gruppe": _gruppe(widget),
    }
    if art == "taste":
        aktion = getattr(widget, "action", None)
        d["funktion"] = str(getattr(aktion, "value", aktion) or "")
        d["bedienung"] = _halteart(widget)
        d["gedrueckt"] = bool(widget._pressed)
        d["aktiv"] = bool(widget.leuchtet())
        d["aktionen"] = list(AKTIONEN_TASTE)
    elif art == "fader":
        d["modus"] = str(getattr(widget, "mode", "") or "")
        d["wert"] = int(widget.value)
        d["aktionen"] = list(AKTIONEN_FADER)
    else:
        d["slot"] = int(getattr(widget, "stack_slot", 0) or 0)
        d.update({"liste": None, "anzahl": 0, "cue_index": -1,
                  "cue": None, "naechste": None})
        ex = widget._executor()
        stack = getattr(ex, "stack", None) if ex is not None else None
        if stack is not None:
            cues = list(getattr(stack, "cues", []) or [])
            try:
                idx = int(getattr(stack, "current_index", -1))
            except (TypeError, ValueError):
                idx = -1
            d["liste"] = str(getattr(stack, "name", "") or "")
            d["anzahl"] = len(cues)
            d["cue_index"] = idx
            d["cue"] = _cue_auskunft(cues[idx]) if 0 <= idx < len(cues) else None
            d["naechste"] = (_cue_auskunft(cues[idx + 1])
                             if -1 <= idx < len(cues) - 1 else None)
        d["aktionen"] = list(AKTIONEN_CUELISTE)
    return d


def _fader_wert(wert) -> int | None:
    """Zahl 0..255 fuer den Fader oder None. Geklemmt wird wie am Fader selbst;
    abgelehnt wird, was keine Zahl ist. ``bool`` zaehlt nicht als Zahl — ein
    versehentliches ``true`` soll keinen Fader auf 1 stellen."""
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        return None
    if not math.isfinite(wert):
        return None
    return max(0, min(255, int(round(wert))))


def _taste_ausfuehren(widget, aktion: str) -> dict:
    from .vc_button import ButtonAction
    druck = aktion in ("druecken", "umschalten")
    if (druck and widget.action == ButtonAction.LASER_ARM
            and not widget._aktionszustand()):
        # Der Laser ist unscharf — ein Druck schaltete ihn scharf. Nur am Pult.
        return _nein(NUR_AM_PULT)
    if aktion == "druecken":
        widget.fern_taste(True)
    elif aktion == "loslassen":
        widget.fern_taste(False)
    else:                                   # ein Tipp: Druck und Loslassen
        widget.fern_taste(True)
        widget.fern_taste(False)
    return {"ok": True}


def ausfuehren(widget, aktion, wert=None) -> dict:
    """Fuehrt ``aktion`` auf ``widget`` aus — ueber den Weg eines Klicks.
    Im UI-Thread aufrufen. Wirft nicht: jeder Fehler wird zur Ablehnung."""
    art = _art(widget)
    if art is None:
        return _nein(TYP_NICHT_ERLAUBT)
    erlaubt = {"taste": AKTIONEN_TASTE, "fader": AKTIONEN_FADER,
               "cueliste": AKTIONEN_CUELISTE}[art]
    if not isinstance(aktion, str) or aktion not in erlaubt:
        return _nein(AKTION_UNBEKANNT)
    try:
        if art == "taste":
            ergebnis = _taste_ausfuehren(widget, aktion)
        elif art == "fader":
            v = _fader_wert(wert)
            if v is None:
                return _nein(WERT_UNGUELTIG)
            widget.value = v                # derselbe Setter wie Maus, Rad, MIDI
            ergebnis = {"ok": True}
        else:
            # dieselben Slots, an denen die drei Knoepfe der Cueliste haengen
            {"go": widget._do_go, "back": widget._do_back,
             "stop": widget._do_stop}[aktion]()
            ergebnis = {"ok": True}
        if ergebnis.get("ok"):
            ergebnis["widget"] = beschreibe(widget)
        return ergebnis
    except Exception as e:
        print(f"[vc_fernbedienung] ERROR: Aktion '{aktion}' auf "
              f"{type(widget).__name__}: {e}")
        return _nein(FEHLER)


class _Auftrag:
    """Ein Aufruf, der im UI-Thread laufen soll. ``zustand`` entscheidet unter
    dem Lock, wer zuerst war: der UI-Thread (fuehrt aus) oder der Aufrufer, der
    nicht laenger wartet (verwirft)."""
    __slots__ = ("fn", "fertig", "ergebnis", "zustand", "lock")

    def __init__(self, fn):
        self.fn = fn
        self.fertig = threading.Event()
        self.ergebnis = None
        self.zustand = "wartet"             # wartet | laeuft | verworfen
        self.lock = threading.Lock()


class VCFernbedienung(QObject):
    """Bruecke zwischen Web-Thread und der Konsole im UI-Thread.

    Im UI-Thread erzeugen (sie merkt sich dessen Thread-ID). Aufrufe aus dem
    UI-Thread laufen direkt; Aufrufe aus jedem anderen Thread werden ueber ein
    Qt-Signal eingereiht und warten hoechstens :attr:`ZEITLIMIT_S` auf das
    Ergebnis. Antwortet die Oberflaeche nicht rechtzeitig, wird der Auftrag
    VERWORFEN — eine Taste, deren Druck dem Handy als „nicht ausgefuehrt"
    gemeldet wurde, loest nicht Sekunden spaeter doch noch aus.
    """

    ZEITLIMIT_S = 2.0
    _auftrag_sig = Signal(object)

    def __init__(self, canvas):
        super().__init__(canvas)            # stirbt mit der Konsole
        self._canvas = canvas
        self._ui_thread = threading.get_ident()
        self._auftrag_sig.connect(self._bearbeite)   # fremder Thread -> eingereiht

    # ── Konsole ──────────────────────────────────────────────────────────────

    def canvas(self):
        """Die Konsole — oder None, wenn sie schon abgebaut ist."""
        c = self._canvas
        if c is None:
            return None
        try:
            import shiboken6
            if not shiboken6.isValid(c):
                return None
        except Exception:
            pass
        return c

    # ── Uebergabe in den UI-Thread ───────────────────────────────────────────

    def _bearbeite(self, auftrag):
        with auftrag.lock:
            if auftrag.zustand != "wartet":
                return                      # Aufrufer hat aufgegeben
            auftrag.zustand = "laeuft"
        try:
            auftrag.ergebnis = auftrag.fn()
        except Exception as e:
            print(f"[vc_fernbedienung] ERROR: {e}")
            auftrag.ergebnis = None
        finally:
            auftrag.fertig.set()

    def _im_ui_thread(self, fn, bei_fehler):
        if threading.get_ident() == self._ui_thread:
            try:
                return fn()
            except Exception as e:
                print(f"[vc_fernbedienung] ERROR: {e}")
                return bei_fehler(FEHLER)
        auftrag = _Auftrag(fn)
        try:
            self._auftrag_sig.emit(auftrag)
        except RuntimeError:                # Bruecke/Konsole schon geloescht
            return bei_fehler(KEINE_KONSOLE)
        if not auftrag.fertig.wait(self.ZEITLIMIT_S):
            with auftrag.lock:
                if auftrag.zustand == "wartet":
                    auftrag.zustand = "verworfen"
                    return bei_fehler(ZEITUEBERSCHREITUNG)
            # Der UI-Thread hat gerade doch begonnen: zu Ende laufen lassen,
            # sonst meldeten wir „nicht ausgefuehrt" fuer etwas, das geschieht.
            auftrag.fertig.wait(self.ZEITLIMIT_S)
        if auftrag.ergebnis is None:
            return bei_fehler(FEHLER)
        return auftrag.ergebnis

    # ── Oeffentlich (aus jedem Thread) ───────────────────────────────────────

    def widgets(self) -> list[dict]:
        """Alle fernbedienbaren Widgets mit Zustand. Leer, wenn es keine
        Konsole (mehr) gibt oder die Oberflaeche nicht antwortet."""
        def _liste():
            c = self.canvas()
            if c is None:
                return []
            out = []
            for w in c.alle_widgets():
                try:
                    e = beschreibe(w)
                except Exception as err:
                    print(f"[vc_fernbedienung] ERROR: Auskunft "
                          f"{type(w).__name__}: {err}")
                    e = None
                if e is not None:
                    out.append(e)
            return out
        try:
            return self._im_ui_thread(_liste, lambda _code: [])
        except Exception as e:              # nie in den Web-Handler durchreichen
            print(f"[vc_fernbedienung] ERROR: {e}")
            return []

    def aktion(self, kennung, aktion, wert=None) -> dict:
        """Aktion auf dem Widget mit ``kennung``. Liefert immer ein Dict mit
        ``ok``; bei Ablehnung steht der Grund in ``fehler``."""
        def _tun():
            c = self.canvas()
            if c is None:
                return _nein(KEINE_KONSOLE)
            if not kennung_gueltig(kennung):
                return _nein(UNBEKANNTE_KENNUNG)
            w = c.widget_mit_kennung(kennung)
            if w is None:
                return _nein(UNBEKANNTE_KENNUNG)
            return ausfuehren(w, aktion, wert)
        try:
            return self._im_ui_thread(_tun, _nein)
        except Exception as e:
            print(f"[vc_fernbedienung] ERROR: {e}")
            return _nein(FEHLER)
