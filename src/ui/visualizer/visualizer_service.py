"""VisualizerService — EIN page-freier Kern fuer Takt, Dirty-Diff und

Serialisierung des 3D-Visualizers (VIZ-12).

Design: ``docs/VIZ12_SERVICE_DESIGN.md``. Kernidee: heute baut JEDES
Render-Target (Fenster + Live-View-Spiegel) seinen eigenen ``QTimer(33ms)``,
sein eigenes State-Subscribe und serialisiert bei JEDEM Tick ALLE Fixtures neu
— unabhaengig davon, ob sich etwas geaendert hat. Der Service ersetzt das durch
EINEN Takt, EIN State-Subscribe und ein Dirty-Diff pro Fixture: nur GEAENDERTE
Fixtures werden pro Tick serialisiert und nur an AKTIVE Targets gepusht.

Kritische Invarianten (siehe CLAUDE.md / Design-Dokument):
  1. Der Service arbeitet AUSSCHLIESSLICH ueber die 5 dict-only Legacy-State-
     Felder (``visualizer_positions`` etc. via ``AppState``) — NIE ueber
     ``state._scene`` direkt. Tests duerfen den State per ``SimpleNamespace``
     faken.
  2. Pro-Target-Zustand (Reload-Token, Echo-Guard, RenderCrashGuard) gehoert
     NICHT hierher — der Service kennt nur ``needs_full`` (ob ein Target beim
     naechsten Tick den vollen Bestand statt nur das Diff braucht).
  3. Der Timer laeuft HART nur, wenn mindestens ein Target aktiv ist
     (Orchestrator-Entscheidung 2) — 0 aktive Targets stoppen ihn sofort.

Dieser Schritt (Schritt 1) haengt den Service NOCH NICHT an echte Fenster/Views
an — ``VisualizerTarget`` ist ein einfacher Emit-Empfaenger (Duck-Type: braucht
nur ``emit_batch(json_str)``); Fenster/View-Anbindung folgt in einem
Folgeschritt.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional


class VisualizerTarget:
    """Duenner Handle fuer ein Render-Ziel (Fenster oder Live-View-Spiegel).

    Der Service haelt pro Target nur, was er fuer Takt-Gating und Dirty-Diff
    braucht: ob es aktiv ist (sichtbar/push-relevant) und ob es beim naechsten
    Tick den vollen Bestand statt nur das Diff braucht. Die eigentliche
    Zustellung (``emit_batch``) ist absichtlich ein einfacher Callback/Duck-
    Type-Slot — in Schritt 1 ein Stub, spaeter die echte Bridge-Signal-Emit.

    Pro-Target-Zustand wie Reload-Token/Echo-Guard/RenderCrashGuard gehoert
    NICHT hierher (bleibt in der jeweiligen Bridge/im jeweiligen Fenster).
    """

    def __init__(self, name: str, emit_batch: Callable[[str], None]):
        self.name = name
        self.emit_batch = emit_batch
        self.active: bool = False
        self.needs_full: bool = True


def _build_fixture_payload(fixture, attrs: dict[str, int]) -> dict[str, object]:
    """Baut den Pro-Fixture-Payload — 1:1 identisch zur heutigen
    ``VisualizerBridge.push_dmx_update``-Logik (inkl. Spider-``heads``-Array),
    nur ohne die JSON-Verpackung/den Signal-Emit (das macht der Service selbst,
    einmal pro Tick fuer das gesamte Batch-Array statt pro Fixture)."""
    r = attrs.get("color_r", 0)
    g = attrs.get("color_g", 0)
    b = attrs.get("color_b", 0)
    w = attrs.get("color_w", 0)
    intensity = attrs.get("intensity", 255)
    pan = attrs.get("pan", 128)
    tilt = attrs.get("tilt", 128)
    payload: dict[str, object] = {
        "fid": fixture.fid,
        "r": min(255, r + w),
        "g": min(255, g + w),
        "b": min(255, b + w),
        "intensity": intensity,
        "pan": pan,
        "tilt": tilt,
    }
    # ── Mehrkopf (Spider): zweite Bar separat senden ────────────────────────
    # Multi-Head-Konvention: Kopf 0 = "attr", Kopf N = "attr#N". Ein Spider hat
    # zwei Tilts + zwei RGBW-Banks -> je Bar eine eigene Farbe + eigener Tilt.
    # JS rendert daraus zwei einzeln tiltbare Bars. (1:1 aus
    # VisualizerBridge.push_dmx_update uebernommen, siehe dort fuer Details.)
    if ("tilt#1" in attrs) or ("color_r#1" in attrs):
        heads = []
        head_count = 2
        tilt_keys = ["tilt"] + [f"tilt#{h}" for h in range(1, head_count)]
        tilt_sources = [attrs[k] for k in tilt_keys if k in attrs]
        if len(tilt_sources) < head_count and "pan" in attrs:
            tilt_sources = [attrs["pan"]] + tilt_sources
        while len(tilt_sources) < head_count:
            tilt_sources.append(tilt_sources[-1] if tilt_sources else tilt)
        for h in range(head_count):
            sfx = "" if h == 0 else f"#{h}"
            hr = attrs.get(f"color_r{sfx}", 0)
            hg = attrs.get(f"color_g{sfx}", 0)
            hb = attrs.get(f"color_b{sfx}", 0)
            hw = attrs.get(f"color_w{sfx}", 0)
            heads.append({
                "r": min(255, hr + hw),
                "g": min(255, hg + hw),
                "b": min(255, hb + hw),
                "cr": hr, "cg": hg, "cb": hb, "cw": hw,
                "tilt": tilt_sources[h],
            })
        payload["heads"] = heads
    return payload


class VisualizerService:
    """Page-freier Takt-/Dirty-Diff-/Serialisierungs-Kern (VIZ-12).

    Ein Service pro ``AppState`` (Singleton via ``get_visualizer_service``,
    siehe unten) — NICHT modul-global, damit Tests mit frischem State auch
    einen frischen Service bekommen (Orchestrator-Entscheidung 5).
    """

    TICK_MS = 33

    def __init__(self, state):
        self._state = state
        self._targets: list[VisualizerTarget] = []
        # Service-globaler Snapshot-Cache: {fid: payload_dict}. Wird pro Tick
        # gegen den frisch gebauten Payload verglichen (value-equality, nicht
        # Objekt-Identitaet) -> nur GEAENDERTE Fixtures wandern ins Batch-Array.
        self._last_payload: dict[int, dict[str, object]] = {}
        self._timer: Optional[Any] = None
        self._subscribed = False

    # ── Timer-Lazy-Init (Qt-Objekt erst bei Bedarf, damit Tests ohne
    #    QApplication den Service instanzieren koennen) ─────────────────────
    def _ensure_timer(self):
        if self._timer is not None:
            return
        from PySide6.QtCore import QTimer
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)

    def _ensure_subscribed(self):
        if self._subscribed:
            return
        self._state.subscribe(self._on_state)
        self._subscribed = True

    # ── Target-Registrierung ─────────────────────────────────────────────────
    def attach_target(self, target: VisualizerTarget) -> None:
        """Neues Render-Ziel andocken. Braucht beim ersten Tick den vollen
        Bestand (Design-Risiko: frisch geoeffnetes Target darf bei statischer
        Szene nicht leer bleiben, da eine unveraenderte Szene sonst gar kein
        Batch mehr ausloest)."""
        if target not in self._targets:
            self._targets.append(target)
        target.needs_full = True
        self._ensure_subscribed()

    def detach_target(self, target: VisualizerTarget) -> None:
        if target in self._targets:
            self._targets.remove(target)
        self._update_timer_gate()

    def set_target_active(self, target: VisualizerTarget, active: bool) -> None:
        was_active = target.active
        target.active = active
        if active and not was_active:
            # Erneut aktiv gewordenes Target (z.B. nach hide/show) braucht
            # wieder den vollen Bestand -> siehe attach_target-Begruendung.
            target.needs_full = True
        self._update_timer_gate()

    def _update_timer_gate(self) -> None:
        """Timer laeuft HART nur bei >=1 aktivem Target (Orchestrator-
        Entscheidung 2). Der State-Patch-Prune haengt NICHT am Timer, sondern
        am State-Subscribe (bleibt auch bei gestopptem Timer aktiv)."""
        any_active = any(t.active for t in self._targets)
        if any_active:
            self._ensure_timer()
            if not self._timer.isActive():
                self._timer.start(self.TICK_MS)
        else:
            if self._timer is not None and self._timer.isActive():
                self._timer.stop()

    @property
    def timer_running(self) -> bool:
        return self._timer is not None and self._timer.isActive()

    # ── Dirty-Diff + Batch-Payload-Bau ───────────────────────────────────────
    def _collect_attrs(self, fixture) -> dict[str, int]:
        """1:1 aus der heutigen ``_push_dmx_updates``-Schleife (Bridge/View)
        uebernommen: baut die rohen Attribut-Kanaele fuer EIN Fixture."""
        from src.core.app_state import get_channels_for_patched

        attrs: dict[str, int] = {}
        seen: dict[str, int] = {}
        universe = self._state.universes[fixture.universe]
        channels = get_channels_for_patched(fixture)
        for ch in channels:
            dmx_addr = fixture.address + ch.channel_number - 1
            if 1 <= dmx_addr <= 512:
                a = ch.attribute
                h = seen.get(a, 0)
                seen[a] = h + 1
                key = a if h == 0 else f"{a}#{h}"
                attrs[key] = universe.get_channel(dmx_addr)
        return attrs

    def _build_snapshot(self) -> dict[int, dict[str, object]]:
        """Baut den Payload fuer JEDES aktuell platzierte, gepatchte Fixture.
        Dict-only: liest nur ueber ``get_patched_fixtures``/``universes``/
        ``visualizer_positions`` — nie ``state._scene`` direkt."""
        snapshot: dict[int, dict[str, object]] = {}
        for fixture in self._state.get_patched_fixtures():
            if fixture.fid not in self._state.visualizer_positions:
                continue
            if fixture.universe not in self._state.universes:
                continue
            attrs = self._collect_attrs(fixture)
            snapshot[fixture.fid] = _build_fixture_payload(fixture, attrs)
        return snapshot

    def _tick(self) -> None:
        if not any(t.active for t in self._targets):
            return
        snapshot = self._build_snapshot()

        # Diff ggue. dem service-globalen Cache: nur GEAENDERTE Fixtures.
        changed: dict[int, dict[str, object]] = {}
        for fid, payload in snapshot.items():
            if self._last_payload.get(fid) != payload:
                changed[fid] = payload
        # Fixtures, die aus dem Snapshot verschwunden sind (unpatched/entfernt),
        # werden hier bewusst NICHT nachgeschickt — das Aufraeumen laeuft ueber
        # den State-Patch-Prune (_on_state), nicht ueber den Tick.
        self._last_payload = snapshot

        for target in self._targets:
            if not target.active:
                continue
            if target.needs_full:
                arr = list(snapshot.values())
                target.needs_full = False
            else:
                arr = list(changed.values())
            if arr:
                target.emit_batch(json.dumps(arr))

    def force_full_resync(self, target: Optional[VisualizerTarget] = None) -> None:
        """Leert den Dirty-Cache (nach Reload/Stage-Wechsel/Target-Attach), so
        dass der naechste Tick wieder ALLES pusht statt nur das Diff. Ohne
        ``target`` betrifft es die globale Baseline UND alle Targets; mit
        ``target`` nur dieses eine (z.B. nach Page-Reload eines einzelnen
        Fensters)."""
        if target is None:
            self._last_payload = {}
            for t in self._targets:
                t.needs_full = True
        else:
            target.needs_full = True

    # ── State-Subscribe (aus der Bridge gehobene Prune-Logik, dict-only) ────
    def _on_state(self, event: str, data) -> None:
        if event != "patch_changed":
            return
        current_fids = {f.fid for f in self._state.get_patched_fixtures()}
        stale = [fid for fid in list(self._state.visualizer_positions)
                 if fid not in current_fids]
        for fid in stale:
            self._state.visualizer_positions.pop(fid, None)
            self._state.visualizer_docks.pop(fid, None)
            self._state.visualizer_rotations.pop(fid, None)
            self._last_payload.pop(fid, None)
        lv = getattr(self._state, "live_view_positions", None)
        if isinstance(lv, dict):
            for fid in [f for f in list(lv) if f not in current_fids]:
                lv.pop(fid, None)

    def shutdown(self) -> None:
        """Einziger vollstaendiger Teardown-Pfad (App-Ende): meldet den EINEN
        Service-Subscriber ab und stoppt den Timer. ``hide()``/``detach_target``
        melden bewusst NICHTS ab (Hintergrund-Updates fuer andere Targets
        bleiben moeglich)."""
        if self._subscribed:
            self._state.unsubscribe(self._on_state)
            self._subscribed = False
        if self._timer is not None:
            self._timer.stop()
        self._targets.clear()
        self._last_payload = {}


# ── Singleton am AppState (Orchestrator-Entscheidung 5) ─────────────────────
def get_visualizer_service(state) -> VisualizerService:
    """Lazy-Singleton, gehalten als Attribut AM uebergebenen ``state`` (nicht
    modul-global) — ein frischer State (z.B. in Tests) bekommt automatisch
    einen frischen Service."""
    svc = getattr(state, "_visualizer_service", None)
    if svc is None:
        svc = VisualizerService(state)
        state._visualizer_service = svc
    return svc
