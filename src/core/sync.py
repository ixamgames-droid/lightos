"""StateSync - Zentrale Validierung und Event-Verteilung.

Ein einziger Event-Bus fuer alle State-Aenderungen.
Validator prueft + repariert die App in einem Pass.

Wird beim Show-Laden automatisch ausgefuehrt; kann manuell via
Menue "Show pruefen & reparieren..." oder F5 angestossen werden.
"""
from __future__ import annotations
import weakref
from typing import Callable
from enum import Enum

try:
    # Prueft, ob das C++-Backing eines Qt-Widgets noch lebt (STAB-03-Guard unten).
    from shiboken6 import isValid as _qt_is_valid
except Exception:  # pragma: no cover - PySide6/shiboken ist im App-Run immer da
    _qt_is_valid = None


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
    LIVE_VIEW_CHANGED = "live_view_changed"    # Live-View-Layout (Positionen/Zoom/Grid) geaendert
    LASER_ARMED_CHANGED = "laser_armed_changed"  # Laser scharf/unscharf/Not-Aus (LAS-10) — Anzeige-Sync
    LASER_ESTOP = "laser_estop"                # Laser-NOT-AUS ausgelöst (UXT-09) — globale Bestätigung
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

    def subscribe_widget(self, event: SyncEvent, widget, callback: Callable):
        """Wie subscribe(), aber an die Lebenszeit eines QWidgets gebunden:
        beim destroyed()-Signal des Widgets wird der Callback automatisch
        abgemeldet.

        Hintergrund (Crash-Klasse, siehe crash.log 2026-06): Views, die bei
        jedem Programmer-Layout-Wechsel neu gebaut werden (eingebettete
        EFX-/Matrix-/Paletten-Seiten, SnapFilePanel), subscriben mit Lambdas
        und wurden nie abgemeldet. Der naechste Emit lief dann in geloeschte
        Qt-Objekte (RuntimeError bis Access Violation).

        STAB-03: Qt loescht das C++-Objekt mitunter, BEVOR sein destroyed-Signal
        die Abmeldung ausloest. Ein Emit in genau diesem Fenster fasst ein totes
        Qt-Objekt an -> native Access Violation, die KEIN try/except faengt. Darum
        prueft ein Guard vor jedem Aufruf die Gueltigkeit des Widgets und ueber-
        springt + entfernt den Subscriber, wenn es schon weg ist. Rein additiv:
        fuer lebende Widgets unveraendert; ohne shiboken faellt es aufs alte
        Verhalten zurueck."""
        # WICHTIG: nur eine SCHWACHE Referenz aufs Widget halten — eine starke
        # (z. B. als Default-Arg) wuerde das Widget am Leben halten, dessen
        # destroyed nie feuern und ein Leak erzeugen.
        _wref = None
        if _qt_is_valid is not None:
            try:
                _wref = weakref.ref(widget)
            except TypeError:
                _wref = None  # nicht referenzierbar -> Verhalten wie subscribe()
        if _wref is not None and _qt_is_valid is not None:
            def guarded(ev, data, _ref=_wref, _valid=_qt_is_valid):
                w = _ref()
                if w is None or not _valid(w):
                    self.unsubscribe(event, guarded)
                    return
                callback(ev, data)
            registered = guarded
        else:
            registered = callback
        self.subscribe(event, registered)
        try:
            widget.destroyed.connect(lambda *_: self.unsubscribe(event, registered))
        except Exception:
            pass  # kein Qt-Objekt -> Verhalten wie subscribe()

    def emit(self, event: SyncEvent, data=None):
        """Emit an event to all subscribers. Errors don't break other subscribers."""
        subs = list(self._subscribers.get(event, []))
        for cb in subs:
            try:
                cb(event, data)
            except RuntimeError as e:
                # PySide6 wirft "Internal C++ object ... already deleted", wenn
                # ein Subscriber an einem zerstoerten Widget haengt (Zombie).
                # Selbstheilung: abmelden, damit kein weiterer Emit ins
                # geloeschte Objekt laeuft (Vorstufe der Access-Violation-
                # Crashes aus crash.log).
                if "already deleted" in str(e).lower():
                    self.unsubscribe(event, cb)
                    print(f"[StateSync] toter Subscriber entfernt ({event.value}): {e}")
                else:
                    name = getattr(cb, "__name__", repr(cb))
                    print(f"[StateSync] error in {name} for {event.value}: {e}")
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
        from src.core.database.models import FixtureMode, FixtureProfile, PatchedFixture

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
                                    # UXT-08: Ist der alte Name nur eine Kurzform
                                    # des neuen (z. B. „34-Kanal" ⊂ „34-Kanal
                                    # (Professional DMX)"), ist das eine harmlose
                                    # Umbenennung — nicht als „fehlt" alarmieren.
                                    _renamed = bool(old) and old.strip().lower() in (
                                        fallback.name or "").strip().lower()
                                    issues.append(ValidationIssue(
                                        'warn', location,
                                        (f"Modus '{old}' zu '{fallback.name}' "
                                         "aktualisiert (nur umbenannt)."
                                         if _renamed else
                                         f"Mode '{old}' fehlt -> ersetzt durch "
                                         f"'{fallback.name}'"),
                                        auto_fixed=True,
                                    ))
                                except Exception as e_fix:
                                    issues.append(ValidationIssue(
                                        'error', location,
                                        f"Mode-Fix fehlgeschlagen: {e_fix}",
                                    ))
                            else:
                                _renamed = bool(mode_name) and mode_name.strip().lower() in (
                                    fallback.name or "").strip().lower()
                                issues.append(ValidationIssue(
                                    'warn', location,
                                    (f"Modus '{mode_name}' wird als "
                                     f"'{fallback.name}' geführt (umbenannt)."
                                     if _renamed else
                                     f"Mode '{mode_name}' fehlt - wäre ersetzt "
                                     f"durch '{fallback.name}'"),
                                ))
                        else:
                            issues.append(ValidationIssue(
                                'error', location,
                                f"FixtureProfile {profile_id} hat keine Modes",
                            ))

                    # 2b. fixture_type re-sync: copy from FixtureProfile when the
                    #     patched type is missing or the generic default ('other').
                    #     NEVER overwrites an already-specific type (e.g. 'moving_head',
                    #     'par') to avoid clobbering deliberate user choices.
                    try:
                        current_type = getattr(f, "fixture_type", None)
                        _GENERIC_TYPES = {None, "", "other"}
                        if current_type in _GENERIC_TYPES and profile_id is not None:
                            profile = s_fix.get(FixtureProfile, profile_id)
                            if profile is not None:
                                profile_type = getattr(profile, "fixture_type", None)
                                if profile_type not in _GENERIC_TYPES:
                                    # Profile has a more specific type — apply it.
                                    if fix:
                                        try:
                                            with state._session() as s_show:
                                                s_show.execute(
                                                    update(PatchedFixture)
                                                    .where(PatchedFixture.fid == fid)
                                                    .values(fixture_type=profile_type)
                                                )
                                                s_show.commit()
                                            # Update in-memory object so subsequent
                                            # checks within this pass see the new value.
                                            f.fixture_type = profile_type
                                            issues.append(ValidationIssue(
                                                'info', location,
                                                f"fixture_type '{current_type}' -> '{profile_type}' "
                                                f"(aus FixtureProfile {profile_id} übernommen)",
                                                auto_fixed=True,
                                            ))
                                        except Exception as e_type_fix:
                                            issues.append(ValidationIssue(
                                                'warn', location,
                                                f"fixture_type-Fix fehlgeschlagen: {e_type_fix}",
                                            ))
                                    else:
                                        issues.append(ValidationIssue(
                                            'info', location,
                                            f"fixture_type '{current_type}' wäre -> '{profile_type}' "
                                            f"(aus FixtureProfile {profile_id})",
                                        ))
                    except Exception as e_type:
                        # Defensive: profile lookup failure must not interrupt validation.
                        issues.append(ValidationIssue(
                            'warn', location,
                            f"fixture_type-Sync übersprungen: {e_type}",
                        ))

                    # 3. Universe gueltig?
                    if universe < 1 or universe > 32:
                        issues.append(ValidationIssue(
                            'error', location,
                            f"Ungültige Universe-Nummer: {universe}",
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
                            f"Ungültige Startadresse: {address}",
                        ))

                    if fid is not None:
                        valid_fids.add(fid)

                except Exception as e_inner:
                    issues.append(ValidationIssue(
                        'error', 'PatchedFixture',
                        f"Fehler beim Prüfen: {e_inner}",
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
                        b_end = b_addr + getattr(b, "channel_count", 0) - 1
                        if a_end >= b_addr:
                            # STAB-CURSHOW: Adress-Ueberlappung zwischen zwei
                            # DISTINKTEN fids wird nur GEMELDET, nie auto-geloescht
                            # (fid ist UNIQUE -> beide sind eigenstaendige Fixtures;
                            # am Startzeitpunkt nicht von einem legitimen Nutzer-
                            # Stapel unterscheidbar -> Auto-Delete = stiller Verlust).
                            # Meldung nennt beide fids + volle Adressbereiche +
                            # Universe, damit sie manuell aufloesbar ist.
                            issues.append(ValidationIssue(
                                'error', f"Universe {univ}",
                                f"Adresskonflikt (U{univ}): "
                                f"{getattr(a, 'label', '?')}[fid {getattr(a, 'fid', '?')}] "
                                f"@ {getattr(a, 'address', '?')}-{a_end} überlappt "
                                f"{getattr(b, 'label', '?')}[fid {getattr(b, 'fid', '?')}] "
                                f"@ {b_addr}-{b_end} — report-only, manuell aufloesen.",
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
