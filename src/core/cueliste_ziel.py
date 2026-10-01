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

3. AUTO-BINDUNG (UI-68, ``binde_an_freien_executor``) — GO/Zurueck im
   Playback-Tab auf eine sichtbar gewaehlte Liste OHNE Executor legt sie auf den
   ERSTEN FREIEN Executor der AKTUELLEN Page (nie einen belegten
   ueberschreiben); ist keiner frei, gibt es kein GO, nur einen Hinweis. Die
   Belegung ist eine normale Executor-Zuweisung und wird mit der Show
   gespeichert (``PlaybackEngine.to_dict``).

   Die globalen Wege (Leertaste, Kommandozeile, Web, OSC) bleiben im Fall d
   bewusst bei der Warnung "kein Licht" und binden NICHT: dort trifft der Befehl
   eine Liste, die der Bediener nicht vor Augen hat (Fall d faellt auf die
   Aufnahme-Regel zurueck, nach Show-Laden also ``cue_stacks[0]``). Ein Tablet-
   oder OSC-GO wuerde sonst unbemerkt die Executor-Belegung der Show aendern und
   ggf. eine Vorbereitungs-Liste live schalten. Im Playback-Tab dagegen sieht
   der Bediener genau die Liste, auf die er GO drueckt — dort ist das Binden
   die erwartete Wirkung. Die Funktion liegt trotzdem hier zentral, damit ein
   spaeterer Weg sie mit derselben Regel nutzen kann.

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


def _hat_eigene_konfiguration(ex) -> bool:
    """UI-68: ein leerer Slot mit eigenem Label ist vom Bediener reserviert —
    der wird nicht automatisch belegt."""
    slot = getattr(ex, "slot", None)
    label = str(getattr(ex, "label", "") or "").strip()
    return label not in ("", f"Exec {slot}")


def _fader_zu(ex) -> bool:
    """UI-68: Volume-Fader steht auf ~0 (z. B. per MIDI/OSC/Web/VC-Slider
    heruntergezogen) — eine dort gebundene Liste machte kein Licht und sprang
    spaeter beim Hochziehen ungewollt live."""
    try:
        wert = float(getattr(ex, "fader_value", 1.0))
    except (TypeError, ValueError):
        return False
    return getattr(ex, "fader_function", "volume") == "volume" and wert < 0.01


def _leere_executoren(state, max_slot: int | None):
    """Executoren der AKTUELLEN Page ohne Liste und ohne eigene Konfiguration,
    kleinste Slot-Nummer zuerst; ``max_slot`` begrenzt auf die sichtbaren Slots."""
    pe = getattr(state, "playback_engine", None)
    try:
        aktuelle = list(pe.executors) if pe is not None else []
    except Exception:
        return []
    leer = []
    for ex in aktuelle:
        slot = getattr(ex, "slot", None)
        if max_slot is not None and isinstance(slot, int) and slot > max_slot:
            continue
        if getattr(ex, "stack", None) is None and not _hat_eigene_konfiguration(ex):
            leer.append(ex)
    return leer


def freier_executor(state, max_slot: int | None = None):
    """UI-68: erster Executor der AKTUELLEN Page ohne Liste (kleinste Slot-
    Nummer zuerst) — oder None. ``max_slot`` begrenzt auf die sichtbaren Slots
    (die Playback-Leiste zeigt nur Ex 1–10). Nicht als frei gelten Slots mit
    eigenem Label (reserviert) und Slots, deren Volume-Fader auf ~0 steht
    (GO machte dort kein Licht) — siehe ``executor_mit_fader_zu``."""
    for ex in _leere_executoren(state, max_slot):
        if not _fader_zu(ex):
            return ex
    return None


def executor_mit_fader_zu(state, max_slot: int | None = None):
    """UI-68: erster sonst freier Executor, der nur wegen Fader auf ~0 nicht
    belegt wird — fuer den Hinweis "Fader hochziehen". None, wenn es keinen
    gibt."""
    for ex in _leere_executoren(state, max_slot):
        if _fader_zu(ex):
            return ex
    return None


def binde_an_freien_executor(state, stack, max_slot: int | None = None):
    """UI-68: legt ``stack`` auf den ersten freien Executor der aktuellen Page
    und liefert dessen Slot-Nummer. None, wenn ``stack`` None ist, schon auf
    einem Executor liegt (nichts zu tun) oder kein Executor frei ist — Aufrufer
    unterscheiden per ``liegt_auf_executor`` bzw. ``executor_mit_fader_zu``.
    Belegte, reservierte (eigenes Label) und auf 0 gezogene Executoren werden
    NIE belegt."""
    if stack is None or liegt_auf_executor(state, stack):
        return None
    ex = freier_executor(state, max_slot)
    if ex is None:
        return None
    ex.stack = stack
    return getattr(ex, "slot", None)


def listen_name(stack) -> str:
    return str(getattr(stack, "name", "") or "Cueliste")
