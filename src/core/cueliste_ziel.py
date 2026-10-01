"""UI-62/UI-66: welche Cueliste ein Befehl ohne ausdrueckliche Listenangabe trifft.

Es gibt ZWEI Regeln — bewusst verschieden, weil Aufnehmen und Abspielen
verschiedene Risiken haben.

1. AUFNAHME-Regel (UI-62, ``ziel_cueliste``) — "Cue aufnehmen" (Taste R, Menue
   Show, Kommandozeile ``record cue``): die im Playback gewaehlte Cueliste
   (``state.gewaehlte_cueliste``), solange sie noch in ``state.cue_stacks``
   steckt — sonst Rueckfall auf die erste Cueliste; None, wenn es keine gibt.
   Aufnehmen in eine Liste ohne Executor ist gewollt (Vorbereiten einer Liste).

2. TRANSPORT-Regel (UI-66, ``transport_cueliste`` / ``bediene_cueliste``) — die
   globalen Befehle GO / Zurueck / Stop ohne Listenangabe: Leertaste/
   Shift+Leertaste im Hauptfenster, Kommandozeile ``go``/``back`` ohne Nummer,
   Web-Remote ``/api/go|back|stop`` (+ Socket-Events), OSC ``/lightos/go|back``.
   Reihenfolge (die erste passende gewinnt):
     a) die gewaehlte Cueliste, WENN sie auf einem Executor (irgendeiner Page)
        liegt;
     b) sonst die Liste des ersten Executors der AKTUELLEN Page, auf dem eine
        Liste liegt (das alte Leertasten-Verhalten);
     c) sonst die erste Cueliste (Reihenfolge ``cue_stacks``), die auf irgendeinem
        Executor irgendeiner Page liegt;
     d) sonst die gewaehlte bzw. erste Cueliste (Aufnahme-Regel) — diese gibt
        KEIN Licht aus; Aufrufer melden das als Warnung
        (``liegt_auf_executor`` == False).

   Begruendung (Live-Sicherheit): Licht erzeugt nur eine Liste, die auf einem
   Executor liegt — ``PlaybackEngine.compute_merged`` tickt ausschliesslich
   Executor-Stacks. Die Playback-Auswahl ist dagegen fluechtig: nach Show-Laden
   setzt ``PlaybackView._refresh_stack_combo`` sie auf ``cue_stacks[0]``, und
   jedes Bearbeiten im Playback-Combo verschiebt sie. Folgte GO blind der
   Auswahl, haette die Leertaste (bzw. Tablet-/OSC-GO) nach Show-Laden bei einer
   ungebundenen Liste an Index 0 kein Licht mehr gemacht, obwohl die Hauptliste
   auf Executor 1 liegt. Deshalb zaehlt die Auswahl nur, wenn sie spielbar ist.

Bewusst NICHT betroffen (ausdrueckliches Ziel): Executor-Knoepfe in der
Playback-Ansicht, VC-Cuelist/VC-Buttons (Slot), MIDI-Executor-Mappings,
Kommandozeile ``go N``/``back N``/``stop N`` (Executor N), Web
``/api/executor/N/go``, OSC ``/lightos/exec/N/...``. Kommandozeile ``stop`` ohne
Nummer bleibt "Stop All" (Panik-Superset), nicht nur eine Liste.

Das Modul ist absichtlich frei von Qt/AppState-Importen, damit Web-, OSC- und
Kommandozeilen-Pfade (und deren Test-Attrappen) es ohne Nebenwirkungen nutzen.
"""
from __future__ import annotations


def _stacks_snapshot(state) -> list:
    # A3D-40: Snapshot ziehen — show_file leert cue_stacks beim Laden IN-PLACE;
    # ohne Kopie koennte zwischen Pruefung und Index ein IndexError fliegen.
    try:
        return list(getattr(state, "cue_stacks", None) or [])
    except Exception:
        return []


def _pages(state) -> list:
    pe = getattr(state, "playback_engine", None)
    pages = getattr(pe, "pages", None)
    if not isinstance(pages, (list, tuple)):
        return []
    try:
        return [list(p) for p in pages]
    except Exception:
        return []


def ziel_cueliste(state):
    """AUFNAHME-Regel (UI-62): gewaehlte Liste, Rueckfall erste (oder None)."""
    stacks = _stacks_snapshot(state)
    gew = getattr(state, "gewaehlte_cueliste", None)
    if gew is not None and any(st is gew for st in stacks):
        return gew
    return stacks[0] if stacks else None


def liegt_auf_executor(state, stack) -> bool:
    """True, wenn ``stack`` auf irgendeinem Executor irgendeiner Page liegt (nur
    dann tickt die PlaybackEngine ihn und er gibt Licht aus)."""
    if stack is None:
        return False
    try:
        return any(getattr(ex, "stack", None) is stack
                   for page in _pages(state) for ex in page)
    except Exception:
        return False


def transport_cueliste(state):
    """TRANSPORT-Regel (UI-66, Faelle a–d im Modul-Docstring) — oder None."""
    stacks = _stacks_snapshot(state)
    pages = _pages(state)
    gebunden = [getattr(ex, "stack", None) for page in pages for ex in page]
    gebunden_ids = {id(st) for st in gebunden if st is not None}

    # a) gewaehlte Liste, wenn sie lebt UND auf einem Executor liegt
    gew = getattr(state, "gewaehlte_cueliste", None)
    if (gew is not None and id(gew) in gebunden_ids
            and any(st is gew for st in stacks)):
        return gew

    # b) erster Executor der aktuellen Page mit Liste (alte Leertaste)
    pe = getattr(state, "playback_engine", None)
    try:
        aktuelle = list(pe.executors) if pe is not None else []
    except Exception:
        aktuelle = []
    for ex in aktuelle:
        st = getattr(ex, "stack", None)
        if st is not None:
            return st

    # c) erste Liste, die auf irgendeinem Executor liegt
    for st in stacks:
        if id(st) in gebunden_ids:
            return st

    # d) nichts spielbar: Aufnahme-Regel (Aufrufer warnen "kein Licht")
    return ziel_cueliste(state)


def bediene_cueliste(state, aktion: str):
    """Fuehrt ``aktion`` ("go" | "back" | "stop") auf der Transport-Ziel-Liste
    aus und liefert die getroffene Liste (None, wenn es keine gibt). Ob sie Licht
    macht, sagt ``liegt_auf_executor``."""
    if aktion not in ("go", "back", "stop"):
        raise ValueError(f"unbekannte Aktion {aktion!r}")
    stack = transport_cueliste(state)
    if stack is not None:
        getattr(stack, aktion)()
    return stack


def listen_name(stack) -> str:
    return str(getattr(stack, "name", "") or "Cueliste")
