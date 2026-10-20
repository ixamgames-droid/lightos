"""WEB-12: Trifft eine Fern-Aktion einen Laser?

Entscheidung des Projektinhabers (12.10.2026, Befund QA96-05): Elemente mit
Laser-Inhalt duerfen vom Handy aus nur bedient werden, wenn am Pult der
Schalter „Laser vom Handy erlauben“ an ist (Vorgabe AUS, Einstellung
``remote_settings.laser_vom_handy``). Dieses Modul beantwortet die Frage
„hat dieses Ziel Laser-Inhalt?“ fuer die Bausteine, aus denen Fern-Aktionen
bestehen: Geraete (fids), Funktionen, Cuelisten, DMX-Adressen.

Was als Laser zaehlt, entscheidet NICHT dieses Modul: es nimmt dieselbe
Erkennung wie der Laser-NOT-AUS (``AppState._laser_fids`` und
``AppState._laser_estop_addrs``, LAS-37) plus die Netzwerk-Laser (Ether Dream
/ IDN, ``laser_output._STREAM_PROTOCOLS``). Ein Geraet, das der NOT-AUS als
Laser dunkel schaltet, ist hier ebenfalls ein Laser — keine zweite Regel, die
auseinanderlaufen koennte.

**Im Zweifel Laser.** Jede Frage, die sich nicht sicher beantworten laesst
(Fehler beim Nachschlagen, Ziel erst zur Laufzeit bekannt), gilt als „trifft
einen Laser“ — sofern ueberhaupt ein Laser im Patch steht. Ohne Laser im
Patch gibt es nichts zu schuetzen.

Geprueft wird bei JEDER Aktion neu (nicht beim Ablegen auf der Handy-Seite):
eine Taste, die nachtraeglich auf eine Laser-Szene umgestellt wird, oder ein
Laser, der spaeter gepatcht wird, ist sofort gesperrt.

Reines Python ohne Qt; wirft nie.
"""
from __future__ import annotations

#: Fehlercode fuer die Web-Schicht (HTTP 403).
LASER_GESPERRT = "laser_gesperrt"


def laser_erlaubt() -> bool:
    """Steht der Schalter „Laser vom Handy erlauben“ auf AN? Im Zweifel nein."""
    try:
        from src.web import remote_settings
        return bool(remote_settings.is_laser_vom_handy_erlaubt())
    except Exception as e:
        print(f"[fern_freigabe] ERROR: Einstellung nicht lesbar: {type(e).__name__}")
        return False


def laser_fids(state) -> frozenset:
    """Alle gepatchten Laser (fids): DMX-Laser wie beim NOT-AUS plus
    Netzwerk-Laser."""
    fids = set(getattr(state, "_laser_fids", frozenset()) or ())
    try:
        from .laser_output import _STREAM_PROTOCOLS
        for f in list(getattr(state, "_patch_cache", None) or ()):
            if (getattr(f, "protocol", "") or "").lower() in _STREAM_PROTOCOLS:
                fids.add(getattr(f, "fid", None))
    except Exception:
        pass
    raus = set()
    for f in fids:
        try:
            raus.add(int(f))
        except (TypeError, ValueError):
            continue
    return frozenset(raus)


def laser_adressen(state) -> dict:
    """``{universum: frozenset(adressen 1..512)}`` der DMX-Laser."""
    try:
        return {int(u): frozenset(a) for u, a in
                (getattr(state, "_laser_estop_addrs", {}) or {}).items() if a}
    except Exception:
        return {}


def gibt_laser(state) -> bool:
    """Steht ueberhaupt ein Laser im Patch?"""
    return bool(laser_fids(state)) or bool(laser_adressen(state))


def fids_treffen_laser(state, fids) -> bool:
    lf = laser_fids(state)
    if not lf:
        return False
    for f in fids or ():
        try:
            if int(f) in lf:
                return True
        except (TypeError, ValueError):
            continue
    return False


def funktion_trifft_laser(state, function_id) -> bool:
    """Steuert die Funktion (auch ueber Chaser/Collection/Sequence) einen
    Laser an? Unbekannte Funktion: nein (sie tut nichts)."""
    if function_id is None:
        return False
    if not gibt_laser(state):
        return False
    try:
        fm = state.function_manager
        if fm.get(int(function_id)) is None:
            return False
        return fids_treffen_laser(state, fm.affected_fids(int(function_id)))
    except Exception as e:
        print(f"[fern_freigabe] ERROR: Funktion {function_id}: {type(e).__name__}")
        return True                         # im Zweifel Laser


def cueliste_trifft_laser(state, stack, _gesehen=None) -> bool:
    """Steuert eine Cue der Liste (auch ueber eine mitlaufende Unter-Liste)
    einen Laser an?"""
    if stack is None or not gibt_laser(state):
        return False
    gesehen = _gesehen if _gesehen is not None else set()
    if id(stack) in gesehen:
        return False
    gesehen.add(id(stack))
    try:
        for cue in list(getattr(stack, "cues", None) or ()):
            werte = getattr(cue, "values", None) or {}
            if fids_treffen_laser(state, list(werte)):
                return True
            ref = getattr(cue, "sub_stack_ref", None)
            if ref is not None:
                stacks = list(getattr(state, "cue_stacks", None) or ())
                if 0 <= int(ref) < len(stacks) and cueliste_trifft_laser(
                        state, stacks[int(ref)], gesehen):
                    return True
        return False
    except Exception as e:
        print(f"[fern_freigabe] ERROR: Cueliste: {type(e).__name__}")
        return True


def executor_trifft_laser(state, executor) -> bool:
    if executor is None:
        return False
    return cueliste_trifft_laser(state, getattr(executor, "stack", None))


def adresse_ist_laser(state, universum, kanal) -> bool:
    try:
        return int(kanal) in laser_adressen(state).get(int(universum), frozenset())
    except (TypeError, ValueError):
        return False
