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
  Aufheben kann die Fernausloesung ihn auch auf Umwegen nicht: seit LAS-36
  loest kein Laser-Wert den NOT-AUS (auch kein Fader, keine Snap-Taste); der
  einzige Weg ist ``AppState.laser_notaus_loesen`` nach der Rueckfrage am Pult.
  Jede Aktion laeuft zusaetzlich in ``app_state.laser_notaus_nicht_loesbar()``,
  dort verweigert auch ``laser_notaus_loesen`` das Loesen. Das gilt auch fuer
  verzoegerte Zusatzaktionen einer Taste.
* *Laser scharf/unscharf*: aus der Ferne nur UNSCHARF. Scharf geschaltet wird
  am Pult — dort steht jemand, der den Raum sieht. Das Web-Remote konnte den
  Laser bisher nicht scharf schalten, und dabei bleibt es.
* *Laser-Inhalt* (WEB-12, Entscheidung des Projektinhabers vom 12.10.2026):
  ein Element, das einen Laser ansteuert — Laser-Muster, eine Funktion/Szene/
  Cueliste mit Laser-Geraeten, ein Fader auf Laser-Kanaelen oder Grand Master
  bei gepatchtem Laser —, ist vom Handy nur bedienbar, wenn am Pult „Laser vom
  Handy erlauben“ an ist (:func:`laser_inhalt`, ``laser_gesperrt``). Geprueft
  wird bei JEDER Aktion neu: auch ein nachtraeglich umgestelltes Element und
  eines, das „Automatisch fuellen“ aufs Handy gelegt hat, ist gesperrt.
  Loslassen und STOP gehen immer.
* *Blackout aus Zusatzaktionen*: eine Taste, deren Zusatzaktion den
  Blackout-Schalter AUS legt, wird abgelehnt, solange der Schalter steht
  (WEB-12 — das Handy hebt keinen fremden Blackout auf).

**WEB-09: Handy-Seiten, Freigabe und Rueckmeldung**

* Die Web-Schnittstelle ruft alles mit ``nur_handy_seiten=True``: geliefert und
  bedient wird dann nur, was auf einer Handy-Seite der Konsole liegt
  (``VCCanvas.handy_seiten()``). Geprueft wird im UI-Thread, im selben Auftrag
  wie die Aktion — zwischen Pruefung und Ausfuehrung kann sich nichts aendern.
* :meth:`VCFernbedienung.konsole` liefert die Seiten samt Zustand der darauf
  liegenden Widgets, dazu Grand Master und Blackout.
* Ein Takt im UI-Thread (:attr:`VCFernbedienung.TAKT_MS`) vergleicht diesen
  Stand mit dem zuletzt gemeldeten und gibt nur die AENDERUNG an
  ``src.web.vc_remote`` weiter — solange ein Handy zuschaut. Abgefragt statt
  verdrahtet: so ist jede Quelle einer Aenderung erfasst (Maus, MIDI, eine
  Funktion, die von selbst endet, eine Cue, die weiterlaeuft), ohne an jeder
  einzeln einen Haken zu pflegen.
* :meth:`VCFernbedienung.loslassen` laesst gehaltene Tasten los, OHNE auf den
  UI-Thread zu warten — der Weg fuer „Verbindung zum Handy abgerissen".
"""
from __future__ import annotations

import math
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from .vc_widget import kennung_gueltig

# Fehlercodes — die Web-Schicht bildet sie auf HTTP-Status ab.
UNBEKANNTE_KENNUNG = "unbekannte_kennung"
TYP_NICHT_ERLAUBT = "typ_nicht_erlaubt"
AKTION_UNBEKANNT = "aktion_unbekannt"
WERT_UNGUELTIG = "wert_ungueltig"
NUR_AM_PULT = "nur_am_pult"
KEINE_KONSOLE = "keine_konsole"
NICHT_FREIGEGEBEN = "nicht_freigegeben"     # WEB-09: liegt auf keiner Handy-Seite
LASER_GESPERRT = "laser_gesperrt"           # WEB-12: Laser-Inhalt ohne Schalter
BLACKOUT_NICHT_VON_HIER = "blackout_nicht_von_hier"   # WEB-12
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
        # WEB-12: auch Laser-Muster — gesperrt ist es dann ueber den Schalter
        # „Laser vom Handy erlauben“ (``laser_inhalt``), nicht ueber den Typ.
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


# ── WEB-12: Laser-Inhalt ─────────────────────────────────────────────────────

def _harmlose_tastenaktionen():
    from .vc_button import ButtonAction as A
    # Aktionen, die keinen Laser einschalten koennen (dunkel, stoppen, Tempo,
    # Auswahl, Musik). Der NOT-AUS und Scharf/Unscharf haben eigene Regeln.
    return {A.BLACKOUT, A.STOP_ALL, A.CLEAR, A.TAP, A.AUDIO_BPM, A.BPM_NUDGE_UP,
            A.BPM_NUDGE_DOWN, A.BPM_MODE_TOGGLE, A.SELECT_GROUP, A.MEDIA_PLAY_PAUSE,
            A.MEDIA_NEXT, A.MEDIA_PREV, A.TAP_BUS, A.SYNC_BUS, A.ARM_BUS, A.FREEZE,
            A.STOP_EFFECTS, A.AUTO_SYNC, A.LASER_ESTOP, A.LASER_ARM}


_snapshot_cache: tuple = (None, None, {})   # (Pfad, mtime, {index: fids})


def _snapshot_fids(index) -> set | None:
    """Geraete eines gespeicherten Snapshots — None, wenn nicht lesbar."""
    global _snapshot_cache
    try:
        import json
        import os
        from .vc_button import _SNAPSHOTS_FILE as pfad
        if not os.path.isfile(pfad):
            return set()
        mtime = os.path.getmtime(pfad)
        alt_pfad, alt_mtime, tabelle = _snapshot_cache
        if alt_pfad != pfad or alt_mtime != mtime:
            with open(pfad, encoding="utf-8") as f:
                daten = json.load(f)
            tabelle = {}
            for i, eintrag in enumerate(daten if isinstance(daten, list) else []):
                werte = (eintrag or {}).get("values", {}) if isinstance(eintrag, dict) else {}
                tabelle[i] = set(werte) if isinstance(werte, dict) else set()
            _snapshot_cache = (pfad, mtime, tabelle)
        return tabelle.get(int(index), set())
    except Exception:
        return None


def _snap_fids(snap_id) -> set | None:
    try:
        from src.core.engine.snap_library import get_snap_library
        snap = get_snap_library().get(int(snap_id))
        return set((snap.values or {}).keys()) if snap is not None else set()
    except Exception:
        return None


def _eintrag_laser(state, typ, eintrag) -> bool:
    """Eine Zusatzaktion (BTN-01) einer Taste."""
    from src.core.laser import fern_freigabe as ff
    if typ in ("function", "funktion"):
        return ff.funktion_trifft_laser(state, eintrag.get("function_id"))
    if typ == "effect_action":
        fid = eintrag.get("function_id")
        return True if fid is None else ff.funktion_trifft_laser(state, fid)
    if typ == "snapshot":
        idx = eintrag.get("snapshot_index")
        fids = _snapshot_fids(idx) if idx is not None else set()
        return True if fids is None else ff.fids_treffen_laser(state, fids)
    if typ == "library_snap":
        fids = _snap_fids(eintrag.get("snap_id"))
        return True if fids is None else ff.fids_treffen_laser(state, fids)
    if typ in ("blackout", "stop_all", "clear"):
        return False
    return eintrag.get("function_id") is not None and ff.funktion_trifft_laser(
        state, eintrag.get("function_id"))


def _taste_laser(widget, state) -> bool:
    from src.core.laser import fern_freigabe as ff
    from .vc_button import ButtonAction as A
    for eintrag in list(getattr(widget, "actions", None) or ()):
        if isinstance(eintrag, dict) and _eintrag_laser(
                state, str(eintrag.get("type", "")), eintrag):
            return True
    a = getattr(widget, "action", None)
    if a in _harmlose_tastenaktionen():
        return False
    fids_fn = list(widget._all_function_ids())
    if any(ff.funktion_trifft_laser(state, f) for f in fids_fn):
        return True
    if a == A.EFFECT_ACTION and not fids_fn:
        return True                     # wirkt auf den gerade aktiven Effekt
    if a == A.LIBRARY_SNAP:
        for sid in widget._all_snap_ids():
            fids = _snap_fids(sid)
            if fids is None or ff.fids_treffen_laser(state, fids):
                return True
    if a == A.SNAPSHOT and getattr(widget, "snapshot_index", None) is not None:
        fids = _snapshot_fids(widget.snapshot_index)
        if fids is None or ff.fids_treffen_laser(state, fids):
            return True
    return False


def _fader_laser(widget, state) -> bool:
    from src.core.laser import fern_freigabe as ff
    from .vc_slider import SliderMode as M
    m = getattr(widget, "mode", None)
    if m in (M.BPM, M.SPEED, M.TEMPO_BUS):
        return False                    # nur Tempo
    if m == M.LEVEL:
        return ff.adresse_ist_laser(state, widget.dmx_universe, widget.dmx_channel)
    if m == M.PLAYBACK:
        slot = getattr(widget, "playback_slot", None)
        if slot is None:
            return False
        executors = list(state.playback_engine.executors)
        return 0 <= slot < len(executors) and ff.executor_trifft_laser(
            state, executors[slot])
    if m == M.SUBMASTER:
        fids, _heads = widget._submaster_targets(state)
        return True if fids is None else ff.fids_treffen_laser(state, fids)
    if m in (M.GROUP_DIMMER, M.FEATURE_DIMMER) or (
            m == M.PROGRAMMER and widget.programmer_scope == "group"
            and widget.programmer_group):
        return ff.fids_treffen_laser(state, widget._group_fids(state, widget.programmer_group))
    if m in (M.EFFECT_INTENSITY, M.EFFECT_SPEED, M.EFFECT_PARAM):
        ids = list(widget._all_target_fids())
        return True if not ids else any(ff.funktion_trifft_laser(state, i) for i in ids)
    # GRANDMASTER und PROGRAMMER (alle / Auswahl): erreicht jeden Laser.
    return True


def laser_inhalt(widget, state=None) -> bool:
    """WEB-12: steuert dieses Element einen Laser an? Im UI-Thread aufrufen.
    Im Zweifel ja — aber nur, wenn ueberhaupt ein Laser im Patch steht (Laser-
    Muster zaehlen immer). Wirft nie."""
    try:
        name = type(widget).__name__
        if name == "VCButton":
            from .vc_button import ButtonAction as A
            if getattr(widget, "action", None) == A.LASER_PATTERN:
                return True
        if state is None:
            from src.core.app_state import get_state
            state = get_state()
        from src.core.laser import fern_freigabe as ff
        if not ff.gibt_laser(state):
            return False
        if name == "VCButton":
            return _taste_laser(widget, state)
        if name == "VCSlider":
            return _fader_laser(widget, state)
        if name == "VCCueList":
            return ff.executor_trifft_laser(state, widget._executor())
        return False
    except Exception as e:
        print(f"[vc_fernbedienung] ERROR: Laser-Pruefung {type(widget).__name__}: "
              f"{type(e).__name__}")
        return True


def _laser_gesperrt(widget) -> bool:
    from src.core.laser import fern_freigabe as ff
    return laser_inhalt(widget) and not ff.laser_erlaubt()


def _ziel_fehlt(widget) -> list[str]:
    """WEB-12 (QA96-19): verlorene Ziele, die das Pult am Element mit rotem
    Rahmen zeigt — Funktion geloescht (tote Bindung) oder Blackout-Ziel weg.
    Das Handy zeigt sie ebenfalls, statt die Taste unbedarft „aktiv“ zu
    zeichnen."""
    if type(widget).__name__ != "VCButton":
        return []
    raus = []
    try:
        if widget._binding_unresolved():
            raus.append("Funktion nicht gefunden")
    except Exception:
        pass
    try:
        raus += [f"Blackout-Ziel verloren: {t}" for t in widget._blackout_verloren_anzeige()]
    except Exception:
        pass
    return raus


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
        # WEB-12: Laser-Inhalt und ob er gerade gesperrt ist (Schalter aus),
        # verlorene Ziele (QA96-19).
        "laser": bool(laser_inhalt(widget)),
        "gesperrt": None,
        "ziel_fehlt": _ziel_fehlt(widget),
    }
    if d["laser"]:
        from src.core.laser import fern_freigabe as _ff
        if not _ff.laser_erlaubt():
            d["gesperrt"] = "laser"
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


def _hebt_blackout_auf(widget) -> bool:
    """Legt eine Zusatzaktion der Taste den Blackout-Schalter AUS?"""
    for e in list(getattr(widget, "actions", None) or ()):
        if isinstance(e, dict) and e.get("type") == "blackout" and e.get("mode") == "off":
            return True
    return False


def _taste_ausfuehren(widget, aktion: str) -> dict:
    from .vc_button import ButtonAction
    druck = aktion in ("druecken", "umschalten")
    if (druck and widget.action == ButtonAction.LASER_ARM
            and not widget._aktionszustand()):
        # Der Laser ist unscharf — ein Druck schaltete ihn scharf. Nur am Pult.
        return _nein(NUR_AM_PULT)
    if druck and _hebt_blackout_auf(widget):
        from src.core.app_state import get_state
        if get_state().output_manager.blackout_schalter:
            return _nein(BLACKOUT_NICHT_VON_HIER)
    ausgeloest = False
    if aktion == "druecken":
        ausgeloest = widget.fern_taste(True)
    elif aktion == "loslassen":
        ausgeloest = widget.fern_taste(False)
    else:                                   # ein Tipp: Druck und Loslassen
        # WEB-12: haelt schon jemand die Taste (Pult, MIDI, ein anderes Handy),
        # tut ein Tipp nichts. Sonst liesse sein Loslassen eine fremd gehaltene
        # Taste los — bei einer Blackout-Taste hiesse das: ein fremder Blackout
        # wird von fern aufgehoben.
        ausgeloest = widget.fern_taste(True)
        if ausgeloest:
            widget.fern_taste(False)
    # WEB-12: ``ausgeloest`` = DIESER Druck hat die Taste gedrueckt (sie war
    # nicht schon gehalten) — daran haengt, wer sie wieder loslassen darf.
    return {"ok": True, "ausgeloest": bool(ausgeloest)}


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
    # WEB-12: Laser-Inhalt nur mit dem Schalter. Loslassen und STOP gehen
    # immer — sie machen nichts an, und ein gehaltener Flash muss los koennen.
    if aktion not in ("loslassen", "stop") and _laser_gesperrt(widget):
        return _nein(LASER_GESPERRT)
    try:
        # Der Laser-NOT-AUS ist aus der Ferne nicht aufhebbar (s. Modulkopf):
        # alles, was die Aktion in den Programmer schreibt, laesst den Latch stehen.
        from src.core.app_state import laser_notaus_nicht_loesbar
        with laser_notaus_nicht_loesbar():
            if art == "taste":
                ergebnis = _taste_ausfuehren(widget, aktion)
            elif art == "fader":
                v = _fader_wert(wert)
                if v is None:
                    return _nein(WERT_UNGUELTIG)
                widget.value = v            # derselbe Setter wie Maus, Rad, MIDI
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
    #: WEB-09: Abstand der Rueckmeldung ans Handy. 100 ms = hoechstens zehn
    #: Meldungen je Sekunde, egal wie schnell sich am Pult etwas aendert.
    TAKT_MS = 100
    _auftrag_sig = Signal(object)

    def __init__(self, canvas):
        super().__init__(canvas)            # stirbt mit der Konsole
        self._canvas = canvas
        self._ui_thread = threading.get_ident()
        self._auftrag_sig.connect(self._bearbeite)   # fremder Thread -> eingereiht
        # WEB-09: Rueckmeldung. ``_gemeldet`` ist der Stand, den die Handys
        # kennen; ``_rev`` zaehlt die Meldungen (das Handy erkennt daran eine
        # Luecke und gleicht neu ab).
        self._gemeldet: dict | None = None
        self._rev = 0
        self._takt_timer = QTimer(self)
        self._takt_timer.setInterval(self.TAKT_MS)
        self._takt_timer.timeout.connect(self._takt)
        self._takt_timer.start()

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
            # Der UI-Thread hat gerade doch begonnen: zu Ende laufen lassen und
            # das ECHTE Ergebnis melden. WEB-12 (Codex zu #1028): frueher wurde
            # nach einer zweiten Wartezeit „Fehler“ gemeldet, obwohl die Aktion
            # noch lief — das Handy versuchte es erneut und loeste einen
            # Umschalter oder eine Cue doppelt aus. Was im UI-Thread begonnen
            # hat, endet dort auch (``_bearbeite`` setzt ``fertig`` im
            # ``finally``); bis dahin wird gewartet.
            auftrag.fertig.wait()
        if auftrag.ergebnis is None:
            return bei_fehler(FEHLER)
        return auftrag.ergebnis

    # ── Oeffentlich (aus jedem Thread) ───────────────────────────────────────

    def widgets(self, nur_handy_seiten: bool = False) -> list[dict]:
        """Alle fernbedienbaren Widgets mit Zustand. Leer, wenn es keine
        Konsole (mehr) gibt oder die Oberflaeche nicht antwortet.
        WEB-09: mit ``nur_handy_seiten`` nur die, die auf einer Handy-Seite
        liegen — so ruft es die Web-Schnittstelle."""
        def _liste():
            c = self.canvas()
            if c is None:
                return []
            frei = self._freigegeben(c) if nur_handy_seiten else None
            out = []
            for w in c.alle_widgets():
                if frei is not None and getattr(w, "widget_id", None) not in frei:
                    continue
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

    def aktion(self, kennung, aktion, wert=None, nur_handy_seiten: bool = False) -> dict:
        """Aktion auf dem Widget mit ``kennung``. Liefert immer ein Dict mit
        ``ok``; bei Ablehnung steht der Grund in ``fehler``.
        WEB-09: mit ``nur_handy_seiten`` wird ein Widget, das auf keiner
        Handy-Seite liegt, abgelehnt (``nicht_freigegeben``)."""
        def _tun():
            c = self.canvas()
            if c is None:
                return _nein(KEINE_KONSOLE)
            if not kennung_gueltig(kennung):
                return _nein(UNBEKANNTE_KENNUNG)
            w = c.widget_mit_kennung(kennung)
            if w is None:
                return _nein(UNBEKANNTE_KENNUNG)
            if nur_handy_seiten and kennung not in self._freigegeben(c):
                return _nein(NICHT_FREIGEGEBEN)
            return ausfuehren(w, aktion, wert)
        try:
            return self._im_ui_thread(_tun, _nein)
        except Exception as e:
            print(f"[vc_fernbedienung] ERROR: {e}")
            return _nein(FEHLER)

    # ── WEB-09: Handy-Seiten ─────────────────────────────────────────────────

    @staticmethod
    def _freigegeben(canvas) -> set:
        """Kennungen der Widgets auf den Handy-Seiten. Im Zweifel leer: was
        nicht nachweislich freigegeben ist, ist es nicht."""
        try:
            from src.core import handy_seiten as _hs
            return _hs.freigegebene_kennungen(canvas.handy_seiten())
        except Exception as e:
            print(f"[vc_fernbedienung] ERROR: Handy-Seiten: {e}")
            return set()

    def _konsole_jetzt(self) -> dict | None:
        """Seiten + Zustand der darauf liegenden Widgets + Grand Master +
        Blackout. Im UI-Thread aufrufen. None ohne Konsole."""
        c = self.canvas()
        if c is None:
            return None
        try:
            abschnitt = c.handy_seiten()
        except Exception as e:
            print(f"[vc_fernbedienung] ERROR: Handy-Seiten: {e}")
            abschnitt = {"version": 1, "seiten": []}
        # Einmal je Aufruf nachschlagen statt je Eintrag die ganze Konsole
        # abzusuchen — der Takt laeuft zehnmal je Sekunde.
        nach_kennung = {getattr(w, "widget_id", None): w for w in c.alle_widgets()}
        widgets: dict = {}
        seiten = []
        for seite in abschnitt.get("seiten", []):
            eintraege = []
            for e in seite.get("eintraege", []):
                kennung = e["widget"]
                if kennung not in widgets:
                    w = nach_kennung.get(kennung)
                    try:
                        auskunft = beschreibe(w) if w is not None else None
                    except Exception as err:
                        print(f"[vc_fernbedienung] ERROR: Auskunft "
                              f"{type(w).__name__}: {err}")
                        auskunft = None
                    # None = verwaist oder nicht (mehr) fernbedienbar. Die
                    # Zelle bleibt in der Seite stehen und wird am Handy leer
                    # gezeigt — die uebrige Anordnung verrutscht nicht.
                    widgets[kennung] = auskunft
                eintraege.append(dict(e))
            seiten.append({"name": seite.get("name", ""),
                           "spalten": seite.get("spalten"),
                           "zeilen": seite.get("zeilen"),
                           "eintraege": eintraege})
        return {"seiten": seiten,
                "widgets": {k: v for k, v in widgets.items() if v is not None},
                **self._pult_jetzt()}

    @staticmethod
    def _pult_jetzt() -> dict:
        """Grand Master (0..255) und Blackout — was am Handy fest unten steht."""
        try:
            from src.core.app_state import get_state
            state = get_state()
            om = state.output_manager
            from src.core.laser import fern_freigabe as _ff
            return {"gm": max(0, min(255, int(round(float(om.grand_master) * 255)))),
                    "blackout": bool(om.blackout),
                    # WEB-12 (QA96-37): der Laser-NOT-AUS ist am Handy sichtbar.
                    "notaus": bool(getattr(state, "laser_estop_active", False)),
                    "laser_erlaubt": bool(_ff.laser_erlaubt())}
        except Exception as e:
            print(f"[vc_fernbedienung] ERROR: Pult-Zustand: {type(e).__name__}")
            return {"gm": 255, "blackout": False, "notaus": False,
                    "laser_erlaubt": False}

    def konsole(self) -> dict | None:
        """Vollstaendiger Stand der Handy-Konsole (aus jedem Thread) — fuer den
        ersten Aufruf und den Abgleich nach einer Wiederverbindung. ``rev`` ist
        die Nummer der letzten Meldung, die in diesem Stand schon enthalten
        ist. None, wenn es keine Konsole gibt oder sie nicht antwortet."""
        def _stand():
            k = self._konsole_jetzt()
            if k is None:
                return {"_keine": True}
            k["rev"] = self._rev
            if self._gemeldet is None:
                # Der erste Zuschauer: sein Abgleich IST der gemeldete Stand.
                # Was sich bis zum naechsten Takt aendert, wird so gemeldet
                # statt stillschweigend zur neuen Vergleichsbasis.
                self._gemeldet = k
            return k
        try:
            k = self._im_ui_thread(_stand, lambda _code: None)
        except Exception as e:
            print(f"[vc_fernbedienung] ERROR: {e}")
            return None
        if not isinstance(k, dict) or k.get("_keine"):
            return None
        return k

    def pult(self, gm=None, blackout=None, geraet: str = "") -> dict:
        """WEB-09: Grand Master (0..255) und/oder Blackout setzen — dieselben
        Aufrufe wie der GM-Fader und der Blackout-Schalter am Pult.

        WEB-12: erst ALLES pruefen, dann setzen (eine Anfrage mit gueltigem
        GM und kaputtem Blackout verstellte frueher den GM und meldete dann
        den Fehler). Den Blackout hebt nur auf, wer ihn gesetzt hat; den Grand
        Master aus der Laser-Aus-Zone zieht ohne Schalter nur, wer ihn
        hineingezogen hat (``src.web.fern_pult``)."""
        def _tun():
            from src.core.app_state import get_state
            from src.core.laser import fern_freigabe as _ff
            from src.web import fern_pult
            state = get_state()
            om = state.output_manager
            v = None
            if gm is not None:
                v = _fader_wert(gm)
                if v is None or not 0 <= gm <= 255:
                    return _nein(WERT_UNGUELTIG)
            if blackout is not None and not isinstance(blackout, bool):
                return _nein(WERT_UNGUELTIG)
            if blackout is not None:
                r = fern_pult.blackout_setzen(om, blackout, geraet)
                if not r.get("ok"):
                    return dict(r, **self._pult_jetzt())
            if v is not None:
                r = fern_pult.gm_setzen(state, v / 255.0, geraet, _ff.laser_erlaubt())
                if not r.get("ok"):
                    return dict(r, **self._pult_jetzt())
            return {"ok": True, **self._pult_jetzt()}
        try:
            return self._im_ui_thread(_tun, _nein)
        except Exception as e:
            print(f"[vc_fernbedienung] ERROR: {e}")
            return _nein(FEHLER)

    def loslassen(self, kennungen) -> None:
        """Laesst die genannten Tasten los — fuer „Verbindung abgerissen".

        Wartet NICHT auf den UI-Thread und verwirft nichts: der Auftrag bleibt
        eingereiht, bis die Oberflaeche ihn abarbeitet. (``aktion`` gibt nach
        :attr:`ZEITLIMIT_S` auf — richtig fuer einen Druck, falsch fuer ein
        Loslassen: eine Flash-Taste bliebe sonst haengen, gerade wenn die
        Oberflaeche beschaeftigt ist.) Ohne Freigabe-Pruefung: loslassen darf
        man immer, auch wenn das Widget inzwischen von der Seite genommen wurde.
        """
        ziel = [k for k in (kennungen or []) if kennung_gueltig(k)]
        if not ziel:
            return

        def _tun():
            c = self.canvas()
            if c is None:
                return True
            for k in ziel:
                w = c.widget_mit_kennung(k)
                if w is None or _art(w) != "taste":
                    continue
                try:
                    from src.core.app_state import laser_notaus_nicht_loesbar
                    with laser_notaus_nicht_loesbar():
                        w.fern_taste(False)
                except Exception as e:
                    print(f"[vc_fernbedienung] ERROR: Loslassen: {e}")
            return True

        if threading.get_ident() == self._ui_thread:
            _tun()
            return
        try:
            self._auftrag_sig.emit(_Auftrag(_tun))
        except RuntimeError:                # Bruecke/Konsole schon geloescht
            pass

    # ── WEB-09: Rueckmeldung ans Handy ───────────────────────────────────────

    def _takt(self):
        """Stand mit dem zuletzt gemeldeten vergleichen, Aenderung melden.
        Laeuft im UI-Thread. Tut nichts, solange kein Handy zuschaut."""
        try:
            from src.web import vc_remote
            if vc_remote.bruecke() is not self or vc_remote.zuschauer() <= 0:
                self._gemeldet = None       # naechster Zuschauer: frischer Vergleich
                return
            jetzt = self._konsole_jetzt()
            if jetzt is None:
                return
            alt = self._gemeldet
            if (alt is None or jetzt["seiten"] != alt["seiten"]
                    or set(jetzt["widgets"]) != set(alt["widgets"])):
                # Die Seiten selbst haben sich geaendert (Editor, Rueckgaengig,
                # Show geladen) — oder es gibt noch keine Vergleichsbasis: alles neu.
                self._rev += 1
                self._gemeldet = jetzt
                vc_remote.melde("vc_konsole", {"aktiv": True, **jetzt,
                                               "rev": self._rev})
                return
            delta: dict = {}
            geaendert = {k: v for k, v in jetzt["widgets"].items()
                         if v != alt["widgets"].get(k)}
            if geaendert:
                delta["widgets"] = geaendert
            for feld in ("gm", "blackout", "notaus", "laser_erlaubt"):   # WEB-12
                if jetzt.get(feld) != alt.get(feld):
                    delta[feld] = jetzt[feld]
            if not delta:
                return
            self._rev += 1
            self._gemeldet = jetzt
            delta["rev"] = self._rev
            vc_remote.melde("vc_zustand", delta)
            self._takt_fehler = None
        except Exception as e:
            # Derselbe Fehler kaeme sonst zehnmal je Sekunde ins Protokoll.
            text = f"{type(e).__name__}: {e}"
            if text != getattr(self, "_takt_fehler", None):
                self._takt_fehler = text
                print(f"[vc_fernbedienung] ERROR: Rueckmeldung: {text}")
