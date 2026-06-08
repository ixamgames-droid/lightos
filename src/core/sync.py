"""StateSync - Zentrale Validierung und Event-Verteilung.

Ein einziger Event-Bus fuer alle State-Aenderungen.
Validator prueft + repariert die App in einem Pass.

Wird beim Show-Laden automatisch ausgefuehrt; kann manuell via
Menue "Show pruefen & reparieren..." oder F5 angestossen werden.
"""
from __future__ import annotations
from typing import Callable
from enum import Enum


# =============================================================================
# Event Bus
# =============================================================================

class SyncEvent(str, Enum):
    PATCH_CHANGED = "patch_changed"            # Fixtures hinzugefuegt/entfernt
    PROGRAMMER_CHANGED = "programmer_changed"  # Programmer-Werte aktualisiert
    DMX_CHANGED = "dmx_changed"                # Direktes Universe-Update (Simple Desk)
    PALETTE_CHANGED = "palette_changed"        # Paletten erstellt/geaendert
    FUNCTION_CHANGED = "function_changed"      # Funktionen erstellt/gestartet/gestoppt
    GROUP_CHANGED = "group_changed"            # Fixture-Gruppen erstellt/geaendert/geloescht
    CUE_STACK_CHANGED = "cue_stack_changed"    # CueStacks geaendert
    OUTPUT_CONFIG_CHANGED = "output_config_changed"  # Enttec/ArtNet/sACN
    SHOW_LOADED = "show_loaded"
    SHOW_SAVED = "show_saved"
    SELECTION_CHANGED = "selection_changed"    # Programmer-Geraeteauswahl geaendert
    REFRESH_ALL = "refresh_all"                # Globale "Alle neu laden"


class StateSync:
    """Single point of state change notifications across the whole app."""

    def __init__(self):
        self._subscribers: dict[SyncEvent, list[Callable]] = {ev: [] for ev in SyncEvent}

    def subscribe(self, event: SyncEvent, callback: Callable):
        """Abonniere ein Event. Callback wird mit (event, data) aufgerufen.

        Doppelte Anmeldungen desselben Callbacks fuer dasselbe Event werden
        verhindert (Idempotenz).
        """
        if event not in self._subscribers:
            self._subscribers[event] = []
        if callback not in self._subscribers[event]:
            self._subscribers[event].append(callback)

    def unsubscribe(self, event: SyncEvent, callback: Callable):
        if event in self._subscribers and callback in self._subscribers[event]:
            self._subscribers[event].remove(callback)

    def emit(self, event: SyncEvent, data=None):
        """Emit an event to all subscribers. Errors don't break other subscribers."""
        subs = list(self._subscribers.get(event, []))
        for cb in subs:
            try:
                cb(event, data)
            except Exception as e:
                name = getattr(cb, "__name__", repr(cb))
                print(f"[StateSync] error in {name} for {event.value}: {e}")

    def refresh_all(self):
        """Broadcast: alle Views sollen sich frisch aus dem State aufbauen."""
        self.emit(SyncEvent.REFRESH_ALL, None)


_sync: StateSync | None = None


def get_sync() -> StateSync:
    """Globaler Singleton-Zugriff auf den Event-Bus."""
    global _sync
    if _sync is None:
        _sync = StateSync()
    return _sync


# =============================================================================
# Validation
# =============================================================================

class ValidationIssue:
    """Ein gefundenes Problem mit Severity, Ort und Nachricht."""

    def __init__(self, severity: str, location: str, message: str, auto_fixed: bool = False):
        self.severity = severity   # 'info', 'warn', 'error'
        self.location = location
        self.message = message
        self.auto_fixed = auto_fixed

    def __str__(self):
        prefix = '[OK]' if self.auto_fixed else f'[{self.severity.upper()}]'
        return f"{prefix} {self.location}: {self.message}"

    def __repr__(self):
        return self.__str__()


def validate_and_repair(state, fix: bool = True) -> list[ValidationIssue]:
    """Pruefe und repariere den App-State.

    Pruefungen:
    1. Jede PatchedFixture hat einen gueltigen FixtureProfile + Mode
    2. Wenn Mode nicht existiert: ersetze durch Mode mit passender Kanalanzahl
    3. Jedes Fixture hat eine gueltige Universe-Nummer (1-32)
    4. Address + ChannelCount darf 512 nicht ueberschreiten
    5. Keine Adress-Konflikte innerhalb eines Universe
    6. Programmer enthaelt nur fids von gepatchten Fixtures
    7. CueStack-Cues referenzieren nur gepatchte Fixtures
    8. Function-Manager Functions referenzieren nur gepatchte Fixtures

    Returns: Liste von Issues. Wenn fix=True werden auto-fixable Issues behoben.
    Validation darf NIE crashen - alle Fehler werden abgefangen.
    """
    issues: list[ValidationIssue] = []

    try:
        from sqlalchemy import select, update
        from sqlalchemy.orm import Session
        from src.core.database.fixture_db import engine as fdb_engine
        from src.core.database.models import FixtureMode, PatchedFixture

        # Hole alle PatchedFixtures
        try:
            patched = state.get_patched_fixtures()
        except Exception as e:
            issues.append(ValidationIssue('error', 'AppState', f"get_patched_fixtures failed: {e}"))
            return issues

        valid_fids: set[int] = set()

        with Session(fdb_engine()) as s_fix:
            for f in patched:
                try:
                    fid = getattr(f, "fid", None)
                    label = getattr(f, "label", "?")
                    location = f"PatchedFixture[{fid}] '{label}'"

                    profile_id = getattr(f, "fixture_profile_id", None)
                    mode_name = getattr(f, "mode_name", "")
                    channel_count = getattr(f, "channel_count", 0)
                    universe = getattr(f, "universe", 0)
                    address = getattr(f, "address", 0)

                    # 1. Mode existiert?
                    mode = None
                    if profile_id is not None:
                        mode = s_fix.execute(
                            select(FixtureMode)
                            .where(FixtureMode.fixture_id == profile_id)
                            .where(FixtureMode.name == mode_name)
                        ).scalar_one_or_none()

                    if not mode:
                        # 2. Fallback: Mode mit passender Kanalanzahl
                        fallback = None
                        if profile_id is not None:
                            fallback = s_fix.execute(
                                select(FixtureMode)
                                .where(FixtureMode.fixture_id == profile_id)
                                .where(FixtureMode.channel_count == channel_count)
                            ).scalar_one_or_none()

                            if not fallback:
                                fallback = s_fix.execute(
                                    select(FixtureMode)
                                    .where(FixtureMode.fixture_id == profile_id)
                                ).scalars().first()

                        if fallback:
                            if fix:
                                old = mode_name
                                try:
                                    with state._session() as s_show:
                                        s_show.execute(
                                            update(PatchedFixture)
                                            .where(PatchedFixture.fid == fid)
                                            .values(
                                                mode_name=fallback.name,
                                                channel_count=fallback.channel_count,
                                            )
                                        )
                                        s_show.commit()
                                    # In-memory Cache auch updaten
                                    f.mode_name = fallback.name
                                    f.channel_count = fallback.channel_count
                                    issues.append(ValidationIssue(
                                        'warn', location,
                                        f"Mode '{old}' fehlt -> ersetzt durch '{fallback.name}'",
                                        auto_fixed=True,
                                    ))
                                except Exception as e_fix:
                                    issues.append(ValidationIssue(
                                        'error', location,
                                        f"Mode-Fix fehlgeschlagen: {e_fix}",
                                    ))
                            else:
                                issues.append(ValidationIssue(
                                    'warn', location,
                                    f"Mode '{mode_name}' fehlt - waere ersetzt durch '{fallback.name}'",
                                ))
                        else:
                            issues.append(ValidationIssue(
                                'error', location,
                                f"FixtureProfile {profile_id} hat keine Modes",
                            ))

                    # 3. Universe gueltig?
                    if universe < 1 or universe > 32:
                        issues.append(ValidationIssue(
                            'error', location,
                            f"Ungueltige Universe-Nummer: {universe}",
                        ))

                    # 4. Adresse + Channels <= 512?
                    end = address + channel_count - 1
                    if end > 512:
                        issues.append(ValidationIssue(
                            'error', location,
                            f"Adresse {address} + {channel_count}ch = {end} > 512",
                        ))
                    if address < 1:
                        issues.append(ValidationIssue(
                            'error', location,
                            f"Ungueltige Startadresse: {address}",
                        ))

                    if fid is not None:
                        valid_fids.add(fid)

                except Exception as e_inner:
                    issues.append(ValidationIssue(
                        'error', 'PatchedFixture',
                        f"Fehler beim Pruefen: {e_inner}",
                    ))

            # 5. Adresskonflikte innerhalb eines Universe
            try:
                by_univ: dict[int, list] = {}
                for f in patched:
                    u = getattr(f, "universe", 0)
                    by_univ.setdefault(u, []).append(f)
                for univ, fxs in by_univ.items():
                    sorted_fxs = sorted(fxs, key=lambda x: getattr(x, "address", 0))
                    for i in range(len(sorted_fxs) - 1):
                        a = sorted_fxs[i]
                        b = sorted_fxs[i + 1]
                        a_end = getattr(a, "address", 0) + getattr(a, "channel_count", 0) - 1
                        b_addr = getattr(b, "address", 0)
                        if a_end >= b_addr:
                            issues.append(ValidationIssue(
                                'error', f"Universe {univ}",
                                f"Konflikt: {getattr(a, 'label', '?')}[{getattr(a, 'fid', '?')}] "
                                f"@ {getattr(a, 'address', '?')}-{a_end} ueberlappt "
                                f"{getattr(b, 'label', '?')}[{getattr(b, 'fid', '?')}] @ {b_addr}",
                            ))
            except Exception as e:
                issues.append(ValidationIssue(
                    'error', 'Address-Conflict-Check',
                    f"Fehler: {e}",
                ))

        # 6. Programmer cleanup
        try:
            programmer = getattr(state, "programmer", {}) or {}
            stale_progs = [fid for fid in list(programmer.keys()) if fid not in valid_fids]
            if stale_progs:
                if fix:
                    for fid in stale_progs:
                        programmer.pop(fid, None)
                    issues.append(ValidationIssue(
                        'info', 'Programmer',
                        f"{len(stale_progs)} verwaiste fids entfernt: {stale_progs}",
                        auto_fixed=True,
                    ))
                else:
                    issues.append(ValidationIssue(
                        'info', 'Programmer',
                        f"{len(stale_progs)} verwaiste fids: {stale_progs}",
                    ))
        except Exception as e:
            issues.append(ValidationIssue('error', 'Programmer', f"Fehler: {e}"))

        # 7. CueStack-Cues bereinigen
        try:
            stacks = getattr(state, "cue_stacks", []) or []
            for stack in stacks:
                cues = getattr(stack, "cues", []) or []
                stack_name = getattr(stack, "name", "?")
                for cue in cues:
                    cue_values = getattr(cue, "values", None)
                    if not isinstance(cue_values, dict):
                        continue
                    stale_in_cue = [fid for fid in list(cue_values.keys()) if fid not in valid_fids]
                    if stale_in_cue:
                        if fix:
                            for fid in stale_in_cue:
                                cue_values.pop(fid, None)
                            issues.append(ValidationIssue(
                                'info',
                                f"Cue {getattr(cue, 'number', '?')} '{getattr(cue, 'label', '')}' "
                                f"(Stack '{stack_name}')",
                                f"{len(stale_in_cue)} verwaiste fids entfernt",
                                auto_fixed=True,
                            ))
                        else:
                            issues.append(ValidationIssue(
                                'info',
                                f"Cue {getattr(cue, 'number', '?')} '{getattr(cue, 'label', '')}' "
                                f"(Stack '{stack_name}')",
                                f"{len(stale_in_cue)} verwaiste fids",
                            ))
        except Exception as e:
            issues.append(ValidationIssue('error', 'CueStacks', f"Fehler: {e}"))

        # 8. Function Manager - Scenes
        try:
            from src.core.engine.function_manager import get_function_manager
            from src.core.engine.scene import Scene
            fm = get_function_manager()
            for func in fm.all():
                try:
                    if isinstance(func, Scene):
                        stale_vals = [sv for sv in func._values
                                      if getattr(sv, "fixture_id", None) not in valid_fids]
                        if stale_vals:
                            if fix:
                                func._values = [sv for sv in func._values
                                                if getattr(sv, "fixture_id", None) in valid_fids]
                                issues.append(ValidationIssue(
                                    'info', f"Scene '{getattr(func, 'name', '?')}'",
                                    f"{len(stale_vals)} verwaiste SceneValues entfernt",
                                    auto_fixed=True,
                                ))
                            else:
                                issues.append(ValidationIssue(
                                    'info', f"Scene '{getattr(func, 'name', '?')}'",
                                    f"{len(stale_vals)} verwaiste SceneValues",
                                ))
                except Exception as e_func:
                    issues.append(ValidationIssue(
                        'error', f"Function '{getattr(func, 'name', '?')}'",
                        f"Fehler: {e_func}",
                    ))
        except Exception as e:
            issues.append(ValidationIssue('error', 'FunctionManager', f"Fehler: {e}"))

    except Exception as e_outer:
        # Top-level Safety-Net - validation darf NIE crashen
        issues.append(ValidationIssue(
            'error', 'validate_and_repair',
            f"Unerwarteter Fehler: {e_outer}",
        ))

    return issues
