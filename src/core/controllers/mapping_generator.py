"""MIDI-8: MIDI-Mapping-Profil aus einem Controller-Bibliotheksprofil erzeugen.

Bis MIDI-8 gab es nur den festen Generator fuer den APC mini
(``mapping_template == "apc_mini_default"``); jedes andere Profil meldete
„noch kein Generator hinterlegt". Jetzt baut ein allgemeiner Generator aus den
Bedienelementen des Profils eine Startbelegung, die man in der MIDI-Konsole
weiter anpasst:

- jede **Note** (Bloecke vom Typ ``note``, in Profil-Reihenfolge) -> GO von
  Executor 1, 2, 3 …
- jeder **CC** (Bloecke vom Typ ``cc``) -> Fader von Executor 1, 2, 3 …

je hoechstens so viele, wie eine Executor-Seite hat. Andere Typen (Encoder,
Pitchbend, Bloecke mit Kanal je Spur, Tasten) sind in der Bibliothek nicht
eindeutig genug beschrieben und bleiben unbelegt. Der Geraetefilter bleibt
leer (jedes Geraet) — der Portname eines Geraets steht nicht im Profil.

Pult-Vorlagen (``console_template``) beschreiben ihre Noten genauso; dort gilt
„Note n auf Kanal 1 = GO von Executor n".
"""
from __future__ import annotations

import re

from src.core.input.profile import InputProfile, create_default_apc_mini_profile

# Executor-Slots je Seite (``PlaybackEngine.MAX_EXECUTORS``).
_MAX_SLOTS = 20

_UNERLAUBT = re.compile(r'[\\/:*?"<>|]+')


def _bloecke(profile, typ: str):
    for c in getattr(profile, "controls", None) or []:
        if c.type != typ:
            continue
        a, b = int(c.range[0]), int(c.range[1])
        if 0 <= a <= b <= 127:
            yield c, a, b


def kann_mapping_erzeugen(profile) -> bool:
    if profile is None:
        return False
    if profile.mapping_template == "apc_mini_default":
        return True
    return any(True for _ in _bloecke(profile, "note")) or \
        any(True for _ in _bloecke(profile, "cc"))


def _kanal(control) -> int:
    """Bibliothek: 0-basiert, -1 = beliebig. Mapping: 1-basiert, 0 = jeder."""
    return 0 if control.channel < 0 else int(control.channel) + 1


def erzeuge_mapping_profil(profile) -> InputProfile:
    """Mapping-Profil fuer ``profile``; ``ValueError``, wenn es nichts gibt."""
    if profile.mapping_template == "apc_mini_default":
        return create_default_apc_mini_profile()
    from src.core.midi.midi_mapper import (ACTION_EXECUTOR_FADER,
                                           ACTION_EXECUTOR_GO, MidiMapping)
    # Pult-Vorlagen heissen schon „… (Pult-Vorlage)“ — kein zweites „Vorlage“.
    roh = profile.label if "Vorlage" in profile.label else f"{profile.label} Vorlage"
    name = _UNERLAUBT.sub("_", roh).strip() or "Vorlage"
    prof = InputProfile(
        name=name, device_hint="",
        description=(f"Aus der Controller-Bibliothek erzeugt ({profile.id}): "
                     "Noten -> GO, CCs -> Fader der Executoren 1.."
                     f"{_MAX_SLOTS}. Geraetefilter leer = jedes Geraet."))
    for typ, msg_type, aktion, art in (
            ("note", "note_on", ACTION_EXECUTOR_GO, "GO"),
            ("cc", "cc", ACTION_EXECUTOR_FADER, "Fader")):
        slot = 0
        for c, a, b in _bloecke(profile, typ):
            for nummer in range(a, b + 1):
                if slot >= _MAX_SLOTS:
                    break
                slot += 1
                prof.mappings.append(MidiMapping(
                    name=f"{c.name or typ} {nummer} -> {art} Exec {slot}",
                    msg_type=msg_type, channel=_kanal(c), data1=nummer,
                    action=aktion, param=str(slot), port_filter=""))
    if not prof.mappings:
        raise ValueError(f"{profile.label}: keine Noten oder CCs im Profil")
    return prof
