"""CueStack — Führt eine Cueliste aus mit Crossfades."""
from __future__ import annotations
import math
import threading
import time
from typing import Callable, Optional
from .cue import Cue
from .fade_curve import eval_named
from ..debug_log import debug_swallow

TICK = 0.02  # 50 Hz Fade-Update


class FadeState:
    """Laufender Fade zwischen zwei Cue-Zuständen."""

    def __init__(self, from_vals: dict, to_vals: dict,
                 duration: float, delay: float, curve: str = "scurve",
                 attr_delays: dict | None = None):
        self.from_vals = from_vals    # {fid: {attr: int}}
        self.to_vals = to_vals
        self.duration = max(duration, 0.001)
        self.delay = delay
        self.curve = curve            # F-5: benannter Fade-Verlauf
        # F-6: optionale Pro-Attribut-Verzögerung {fid: {attr: extra_delay_s}};
        # leer = ein gemeinsamer Fortschritt für die ganze Cue (bisheriges Verhalten).
        self.attr_delays = attr_delays or {}
        self.start_time = time.monotonic()
        self.done = False
        # Manueller Crossfade: wenn aktiv, treibt manual_pos (0..1) den Uebergang
        # statt der verstrichenen Zeit (Fader scrubbt von Hand).
        self.manual = False
        self.manual_pos = 0.0

    def _progress(self) -> float:
        """Roher Fortschritt 0..1 (oder -1 = noch in der Delay-Phase)."""
        if self.manual:
            return max(0.0, min(1.0, self.manual_pos))
        elapsed = time.monotonic() - self.start_time - self.delay
        if elapsed < 0:
            return -1.0
        return min(1.0, elapsed / self.duration)

    def current_values(self) -> dict[int, dict[str, int]]:
        # F-6: Mit Pro-Attribut-Verzögerungen bekommt jedes Attribut seinen eigenen
        # Fortschritt. Ohne (Normalfall) ODER beim manuellen Scrub gilt der bisherige
        # gemeinsame Fortschritt 1:1 (manueller Crossfade ignoriert Attr-Delays).
        if self.attr_delays and not self.manual:
            return self._blend_per_attr()
        raw = self._progress()
        if raw < 0:                       # Delay laeuft noch
            return self.from_vals
        if raw >= 1.0:                    # fertig -> exakt Zielwerte (kurvenunabhaengig)
            self.done = True
            # KOPIE der inneren dicts: to_vals ist die cue.values des Ziel-Cues
            # (per-Referenz in _fade_to uebergeben). Gaeben wir sie direkt zurueck,
            # aliast _own_output die gespeicherten Cue-Werte und ein spaeterer
            # In-Place-Merge (Sub-Cueliste, tick()) mutiert die persistente Cue —
            # korrumpiert die Show dauerhaft. Siehe tick()-Merge-Kommentar.
            return {fid: dict(attrs) for fid, attrs in self.to_vals.items()}
        # F-5: Fade-Verlauf der Cue (Default scurve = bisheriges Smoothstep-Verhalten)
        t = eval_named(self.curve, raw)
        return self._blend(t)

    def _blend_per_attr(self) -> dict[int, dict[str, int]]:
        """F-6: Blend mit eigener, um ``attr_delays`` verschobener Zeitachse je
        Attribut. ``done`` erst, wenn auch das am längsten verzögerte Attribut fertig
        ist. Attribute ohne Eintrag verhalten sich exakt wie im Normalpfad."""
        base = time.monotonic() - self.start_time - self.delay
        max_extra = 0.0
        result: dict[int, dict[str, int]] = {}
        all_fids = set(self.from_vals) | set(self.to_vals)
        for fid in all_fids:
            from_f = self.from_vals.get(fid, {})
            to_f = self.to_vals.get(fid, {})
            delays_f = self.attr_delays.get(fid, {})
            merged = {}
            for attr in set(from_f) | set(to_f):
                fv = from_f.get(attr, 0)
                tv = to_f.get(attr, fv)
                extra = delays_f.get(attr, 0.0)
                if extra > max_extra:
                    max_extra = extra
                e = base - extra
                if e < 0:                 # dieses Attribut noch in seiner Verzögerung
                    merged[attr] = fv
                elif e >= self.duration:  # dieses Attribut fertig -> exakt Ziel
                    merged[attr] = tv
                else:
                    t = eval_named(self.curve, e / self.duration)
                    merged[attr] = int(fv + (tv - fv) * t)
            result[fid] = merged
        if base - max_extra >= self.duration:
            self.done = True
        return result

    def _blend(self, t: float) -> dict[int, dict[str, int]]:
        result: dict[int, dict[str, int]] = {}
        all_fids = set(self.from_vals) | set(self.to_vals)
        for fid in all_fids:
            from_f = self.from_vals.get(fid, {})
            to_f = self.to_vals.get(fid, {})
            all_attrs = set(from_f) | set(to_f)
            merged = {}
            for attr in all_attrs:
                fv = from_f.get(attr, 0)
                tv = to_f.get(attr, fv)
                merged[attr] = int(fv + (tv - fv) * t)
            result[fid] = merged
        return result


class CueStack:
    # F-7: Ablauf-Modi am Ende der Liste.
    #   single   = am Ende stehen bleiben
    #   loop     = wieder bei Cue 1 beginnen
    #   bounce / pingpong = am Ende umkehren (… 3 → 2 → 1 → 2 → 3 …)
    MODES = ("single", "loop", "bounce", "pingpong")

    def __init__(self, name: str = "Neue Cueliste"):
        self.name = name
        self.cues: list[Cue] = []
        self.mode: str = "single"
        # Beat-Sync: statt der Zeit-`follow` der Cues schaltet der BPM-Manager die
        # aktive Cueliste alle ``beats_per_cue`` Beats eine Cue weiter (taktgenau
        # zur Musik). Treiber: BPMManager._emit_beat() → on_beat(). Default aus →
        # Alt-Shows verhalten sich unverändert (rein zeitbasiert).
        self.beat_sync: bool = False
        self.beats_per_cue: int = 4
        self._beat_count: int = 0
        self._dir: int = 1                # Laufrichtung für bounce/pingpong
        self._current_idx = -1
        self._fade: FadeState | None = None
        # _own_output = nur diese Cueliste (Fade/gehaltene Cue);
        # _output = sichtbares Ergebnis inkl. gemischter Sub-Cueliste (F-16).
        self._own_output: dict[int, dict[str, int]] = {}
        self._output: dict[int, dict[str, int]] = {}
        self._manual_target: int = -1     # Zielzeile eines laufenden manuellen Crossfades
        # A3D-16: zusaetzlich die Ziel-Cue als OBJEKT-Referenz (Identitaets-Anker).
        # Der reine Index verschiebt sich bei Live-Insert/-Remove waehrend des
        # Scrubs (bleibt in-bounds, zeigt aber auf eine ANDERE Cue) -> ein Commit
        # gegen den Index wuerde die falsche Cue aktivieren. Ueber die Referenz
        # wird der Index bei jeder Mutation identitaets-treu nachgefuehrt bzw. der
        # Fade verworfen, wenn die Ziel-Cue entfernt wurde.
        self._manual_target_cue: "Cue | None" = None
        self._manual_dir: int = 1
        self._lock = threading.Lock()
        self._follow_timer: threading.Timer | None = None
        self._on_cue_change: list = []        # callbacks(idx, cue)
        self._on_output_change: list = []     # callbacks(output_dict)
        # F-16: Sequence-in-Sequence. _resolve_sub(idx)->CueStack|None wird von
        # AppState injiziert; _active_sub ist die aktuell mitlaufende Sub-Cueliste;
        # _rendering bricht Zyklen (A→B→A) deadlockfrei (Check VOR dem Lock).
        self._resolve_sub: Optional[Callable[[int], "CueStack | None"]] = None
        self._active_sub: "CueStack | None" = None
        self._rendering: bool = False

    # ── Kompatibilität: loop ⇄ mode ────────────────────────────────────────────
    @property
    def loop(self) -> bool:
        """Rückwärtskompatibel: True, sobald NICHT 'single' (UI-Checkbox)."""
        return self.mode != "single"

    @loop.setter
    def loop(self, value: bool):
        # Bounce/Ping-Pong nicht überschreiben, wenn nur die alte Checkbox umschaltet.
        if value:
            if self.mode == "single":
                self.mode = "loop"
        else:
            self.mode = "single"

    # ── Navigation ────────────────────────────────────────────────────────────

    def go(self):
        with self._lock:
            self._cancel_follow()
            if not self.cues:
                return
            n = len(self.cues)
            if self._current_idx < 0:
                self._dir = 1
                self._fade_to(0)            # erster GO -> Cue 1
                return
            if self.mode in ("bounce", "pingpong") and n >= 2:
                next_idx = self._current_idx + self._dir
                if next_idx >= n:           # am Ende umkehren (ohne Endpunkt-Wiederholung)
                    self._dir = -1
                    next_idx = self._current_idx - 1
                elif next_idx < 0:          # am Anfang umkehren
                    self._dir = 1
                    next_idx = self._current_idx + 1
            else:                            # single / loop
                next_idx = self._current_idx + 1
                if next_idx >= n:
                    if self.mode == "loop":
                        next_idx = 0
                    else:
                        return               # single: am Ende stehen bleiben
            self._fade_to(next_idx)

    def back(self):
        with self._lock:
            self._cancel_follow()
            if not self.cues or self._current_idx <= 0:
                return
            self._fade_to(self._current_idx - 1, use_fade_out=True)

    def go_to(self, number: float):
        with self._lock:
            for i, cue in enumerate(self.cues):
                if abs(cue.number - number) < 0.001:
                    self._fade_to(i)
                    return

    def on_beat(self):
        """Vom BPMManager pro Beat aufgerufen. Schaltet bei aktiver Beat-Sync und
        laufender Cueliste alle ``beats_per_cue`` Beats eine Cue weiter (taktgenau).
        No-op, wenn Beat-Sync aus ist oder die Liste nicht läuft."""
        if not self.beat_sync:
            return
        with self._lock:
            if self._current_idx < 0 or not self.cues:
                return
            per = max(1, int(self.beats_per_cue or 1))
            self._beat_count += 1
            if self._beat_count < per:
                return
            self._beat_count = 0
        self.go()   # eigener Lock — daher außerhalb des with aufrufen

    def _peek_next(self) -> tuple[int | None, int]:
        """Liefert (naechster_index, neue_richtung) wie ein GO ihn waehlen wuerde,
        OHNE den Zustand zu aendern. (None, dir) wenn es kein Weiter gibt
        (single am Ende). Wird vom manuellen Crossfade genutzt."""
        n = len(self.cues)
        if n == 0:
            return None, self._dir
        if self._current_idx < 0:
            return 0, 1
        if self.mode in ("bounce", "pingpong") and n >= 2:
            nxt = self._current_idx + self._dir
            if nxt >= n:
                return self._current_idx - 1, -1
            if nxt < 0:
                return self._current_idx + 1, 1
            return nxt, self._dir
        nxt = self._current_idx + 1
        if nxt >= n:
            if self.mode == "loop":
                return 0, 1
            return None, self._dir
        return nxt, self._dir

    def peek_next(self) -> tuple[int | None, int]:
        """Public read-only: (naechster_index, richtung) wie ein GO ihn waehlen
        wuerde — fuer UI-Vorschauen (loop/bounce/pingpong-korrekt statt naivem
        idx+1)."""
        with self._lock:
            return self._peek_next()

    def manual_crossfade(self, pos: float) -> bool:
        """Manueller Crossfade: pos 0..1 scrubbt den Uebergang von der aktiven
        zur naechsten Cue von Hand (Fader). Bei pos>=1.0 wird der Uebergang
        uebernommen (Zielcue wird aktiv) und True zurueckgegeben — die UI sollte
        ihren Fader dann auf 0 zuruecksetzen, um den naechsten Schritt zu armieren.
        """
        pos = max(0.0, min(1.0, pos))
        committed = False
        commit_cb = None
        with self._lock:
            if not self.cues:
                return False
            # Manuellen Fade armieren, sobald der Fader 0 verlaesst.
            if self._fade is None or not self._fade.manual:
                if pos <= 0.0:
                    return False
                nxt, d = self._peek_next()
                if nxt is None:
                    return False
                self._cancel_follow()
                self._manual_target = nxt
                self._manual_target_cue = self.cues[nxt]
                self._manual_dir = d
                self._fade = FadeState(dict(self._own_output),
                                       self.cues[nxt].values, 1.0, 0.0)
                self._fade.manual = True
            if pos >= 1.0:
                # F4/A3D-16: Ziel-Cue per IDENTITAET aufloesen statt den evtl.
                # waehrend des Scrubs verschobenen Index blind zu uebernehmen.
                # Wurde die Ziel-Cue entfernt (oder ist sonst nicht mehr auffindbar),
                # den Fade sauber verwerfen statt die falsche/ungueltige Cue zu
                # aktivieren.
                target_idx = None
                if self._manual_target_cue is not None:
                    target_idx = next(
                        (i for i, c in enumerate(self.cues)
                         if c is self._manual_target_cue), None)
                if target_idx is None:
                    self._fade = None
                    self._manual_target = -1
                    self._manual_target_cue = None
                else:
                    # Uebernehmen: Zielcue wird aktiv, manueller Fade beendet.
                    self._dir = self._manual_dir
                    self._current_idx = target_idx
                    self._manual_target = target_idx
                    self._own_output = dict(self._fade.to_vals)
                    self._output = dict(self._own_output)
                    self._fade = None
                    self._manual_target_cue = None
                    committed = True
                    commit_cb = (self._current_idx, self.cues[self._current_idx])
            else:
                self._fade.manual_pos = pos
                self._own_output = self._fade.current_values()
                self._output = dict(self._own_output)
        self._emit_output()
        if committed and commit_cb is not None:
            for cb in self._on_cue_change:
                try:
                    cb(*commit_cb)
                except Exception as e:
                    debug_swallow("cue_stack.cue_cb", e)
        return committed

    def stop(self):
        sub = None
        with self._lock:
            self._cancel_follow()
            self._fade = None
            self._own_output = {}
            self._output = {}
            self._current_idx = -1
            self._dir = 1
            self._manual_target = -1
            self._manual_target_cue = None
            sub = self._active_sub        # F-16: mitlaufende Sub-Cueliste mit stoppen
            self._active_sub = None
        if sub is not None:
            sub.stop()
        self._emit_output()

    @property
    def current_cue(self) -> Cue | None:
        if 0 <= self._current_idx < len(self.cues):
            return self.cues[self._current_idx]
        return None

    @property
    def current_index(self) -> int:
        return self._current_idx

    # ── Cue-Verwaltung ────────────────────────────────────────────────────────

    def _active_cue_obj(self) -> "Cue | None":
        """Die aktuell aktive Cue als OBJEKT (oder None), fuer identitaets-
        basiertes Nachfuehren ueber eine Cues-Mutation hinweg."""
        if 0 <= self._current_idx < len(self.cues):
            return self.cues[self._current_idx]
        return None

    def _reindex_after_mutation(self, active_cue: "Cue | None"):
        """Nach jeder Mutation von ``self.cues`` (add/remove/sort) den laufenden
        Zustand konsistent halten: ``_current_idx`` der zuvor aktiven Cue per
        IDENTITAET nachfuehren (Cue ist ein value-eq dataclass -> ``.index()``
        traefe die falsche gleichwertige Cue), sonst in den gueltigen Bereich
        clampen. Stale ``_manual_target`` eines laufenden manuellen Crossfades
        entschaerfen. Behebt IndexError in go/back/manual_crossfade nach Live-
        Loeschen und die falsche Playback-Position nach Live-Insert."""
        n = len(self.cues)
        if active_cue is not None:
            idx = next((i for i, c in enumerate(self.cues) if c is active_cue), None)
            self._current_idx = idx if idx is not None else min(self._current_idx, n - 1)
        else:
            self._current_idx = min(self._current_idx, n - 1)
        if self._current_idx < 0:
            self._current_idx = -1
        # A3D-16: einen laufenden manuellen Crossfade identitaets-treu nachfuehren
        # (nicht nur bounds-klemmen) -- sonst zeigt der in-bounds gebliebene Index
        # nach einem Insert/Remove auf die falsche Cue.
        if self._manual_target_cue is not None:
            midx = next((i for i, c in enumerate(self.cues)
                         if c is self._manual_target_cue), None)
            if midx is None:
                self._manual_target = -1
                self._manual_target_cue = None
            else:
                self._manual_target = midx
        elif not (0 <= self._manual_target < n):
            self._manual_target = -1

    def add_cue(self, cue: Cue):
        with self._lock:
            active = self._active_cue_obj()
            self.cues.append(cue)
            self.cues.sort(key=lambda c: c.number)
            self._reindex_after_mutation(active)

    def remove_cue(self, number: float):
        with self._lock:
            active = self._active_cue_obj()
            self.cues = [c for c in self.cues if abs(c.number - number) > 0.001]
            self._reindex_after_mutation(active)

    def update_cue(self, cue: Cue):
        with self._lock:
            for i, c in enumerate(self.cues):
                if abs(c.number - cue.number) < 0.001:
                    # Gleiche Nummer -> Position in der sortierten Liste unveraendert,
                    # _current_idx bleibt gueltig (zeigt auf dieselbe Zeile).
                    # A3D-16: ersetzt die In-Place-Bearbeitung die Ziel-Cue eines
                    # laufenden manuellen Crossfades, den Identitaets-Anker mitziehen
                    # (sonst verwirft die naechste Mutation den Fade faelschlich) UND
                    # die Fade-Zielwerte auffrischen: _fade.to_vals haelt die alten
                    # cue.values by-ref (Arm-Snapshot); ohne Auffrischen zeigten
                    # Live-Scrub UND Commit sonst die VERALTETEN Werte, obwohl der
                    # Anker bereits die neue Cue trifft (Review-Fund A3D-16).
                    if self._manual_target_cue is c:
                        self._manual_target_cue = cue
                        if self._fade is not None and self._fade.manual:
                            self._fade.to_vals = cue.values
                    self.cues[i] = cue
                    return
        # Neue Nummer -> einsortieren. add_cue nimmt selbst den (nicht-reentranten)
        # Lock, daher AUSSERHALB des with-Blocks aufrufen.
        self.add_cue(cue)

    def renumber_cue(self, cue: Cue, new_number: float):
        """ENG-13: Die Nummer EINER bereits eingelisteten Cue aendern und die Liste
        konsistent neu sortieren. MUSS ueber diese API laufen — ``cue.number`` von
        aussen setzen + ``cues.sort()`` (wie der Playback-Editor es frueher tat) umging
        die einzige konsistenz-wahrende Stelle: nur ``_reindex_after_mutation`` fuehrt
        ``_current_idx``/``_manual_target`` einer LAUFENDEN Cueliste identitaets-treu
        nach (sonst zeigt der Index nach dem Re-Sort auf die falsche Cue -> Replay/Skip),
        und das ``_lock`` serialisiert die Mutation gegen den Engine-Tick-Thread."""
        try:
            num = round(float(new_number), 3)
        except (TypeError, ValueError):
            return
        # NaN/inf wuerde die Sortierung undefiniert machen (und ist ueber go_to eh nie
        # erreichbar) -> verwerfen statt die Liste zu korrumpieren.
        if not math.isfinite(num):
            return
        with self._lock:
            active = self._active_cue_obj()
            cue.number = num
            self.cues.sort(key=lambda c: c.number)
            self._reindex_after_mutation(active)

    # ── Tick (wird von Engine-Timer aufgerufen) ───────────────────────────────

    def tick(self) -> dict[int, dict[str, int]] | None:
        """Gibt aktuellen Output zurück oder None wenn weder Fade noch Sub läuft.

        F-16: Eine per ``sub_stack_ref`` referenzierte Sub-Cueliste der aktiven Cue
        wird hier gestartet, mitgetickt und in den Output gemischt. ``_rendering``
        bricht Zyklen (A→B→A) VOR dem Lock ab — ``get_output()`` nimmt keinen Lock,
        daher kein Deadlock auf der eigenen, nicht-reentranten ``_lock``."""
        if self._rendering:
            return self.get_output() or None
        self._rendering = True
        try:
            old_sub = None
            with self._lock:
                # WICHTIG: VOR dem Abräumen merken — sonst unterbleibt auf dem
                # Abschluss-Tick eines Fades der finale Emit/Return (alter Kontrakt:
                # der Tick, der den Fade beendet, liefert noch die Zielwerte).
                fade_active = self._fade is not None
                if self._fade is not None:
                    self._own_output = self._fade.current_values()
                    if self._fade.done:
                        self._fade = None
                # gewünschte Sub-Cueliste = sub_stack_ref der aktiven Cue
                desired = None
                if 0 <= self._current_idx < len(self.cues) and self._resolve_sub:
                    ref = getattr(self.cues[self._current_idx], "sub_stack_ref", None)
                    if ref is not None:
                        cand = self._resolve_sub(ref)
                        if cand is not None and cand is not self:
                            desired = cand
                if desired is not self._active_sub:
                    old_sub = self._active_sub
                    self._active_sub = desired
                sub = self._active_sub
            # Ausserhalb des Locks: alte Sub stoppen, neue treiben + mischen.
            if old_sub is not None and old_sub is not sub:
                old_sub.stop()
            sub_out = None
            if sub is not None:
                if sub.current_index < 0:
                    sub.go()              # beim Erreichen der Cue erstmals starten
                sub.tick()
                sub_out = sub.get_output()
            with self._lock:
                merged = dict(self._own_output)
                if sub_out:               # F-16: Sub mischt sich oben drauf (LTP)
                    for fid, attrs in sub_out.items():
                        # NEUES inneres dict bauen statt setdefault(...).update():
                        # _own_output[fid] kann das mit cue.values geteilte dict
                        # sein (FadeState.current_values liefert to_vals by-ref),
                        # ein .update() daran wuerde die gespeicherte Cue mutieren.
                        base = merged.get(fid)
                        merged[fid] = {**base, **attrs} if base else dict(attrs)
                self._output = merged
                active = fade_active or (sub is not None)
                out = dict(self._output)
        finally:
            self._rendering = False
        if not active:
            return None
        self._emit_output()
        return out

    def get_output(self) -> dict[int, dict[str, int]]:
        return dict(self._output)

    # ── Internes ──────────────────────────────────────────────────────────────

    def _fade_to(self, idx: int, use_fade_out: bool = False):
        cue = self.cues[idx]
        # Fade startet vom EIGENEN Stand (ohne Sub-Cueliste), damit Sub-Kanäle beim
        # Cue-Wechsel nicht nachhängen; ohne Sub ist _own_output == _output.
        from_vals = dict(self._own_output)
        # ENG-01: Richtung wählt Fade-Zeit, Cue-Delay-Basis UND die Pro-Attribut-
        # Delays symmetrisch — GO nutzt fade_in/delay_in/attr_delays, BACK (Fade-Out)
        # nutzt fade_out/delay_out/attr_delays_out. (Vorher nahm der Back-Fade immer
        # delay_in als Basis und die In-Attr-Delays — die Out-Seite griff nie.)
        if use_fade_out:
            fade_time = cue.fade_out
            base_delay = cue.delay_out
            attr_delays = getattr(cue, "attr_delays_out", None)
        else:
            fade_time = cue.fade_in
            base_delay = cue.delay_in
            attr_delays = getattr(cue, "attr_delays", None)
        self._fade = FadeState(
            from_vals, cue.values, fade_time, base_delay,
            getattr(cue, "fade_curve", "scurve"),
            attr_delays,
        )
        self._current_idx = idx
        # A3D-16: ein programmatischer GO/BACK bricht einen evtl. armierten
        # manuellen Crossfade ab -> Ziel-Anker verwerfen (Fader-Scrub hinfaellig).
        self._manual_target = -1
        self._manual_target_cue = None
        self._beat_count = 0          # Beat-Sync zählt ab dieser Cue neu
        for cb in self._on_cue_change:
            try:
                cb(idx, cue)
            except Exception as e:
                debug_swallow("cue_stack.cue_cb", e)
        # Bei Beat-Sync treibt der BPM-Manager (on_beat) das Weiterschalten —
        # dann keinen Zeit-Follow-Timer armieren.
        if not self.beat_sync and cue.follow is not None and cue.follow >= 0:
            self._follow_timer = threading.Timer(
                cue.follow + fade_time, self.go
            )
            self._follow_timer.daemon = True
            self._follow_timer.start()

    def _cancel_follow(self):
        if self._follow_timer:
            self._follow_timer.cancel()
            self._follow_timer = None

    def _emit_output(self):
        for cb in self._on_output_change:
            try:
                cb(self._output)
            except Exception as e:
                debug_swallow("cue_stack.output_cb", e)

    def subscribe_cue(self, cb):
        self._on_cue_change.append(cb)

    def subscribe_output(self, cb):
        self._on_output_change.append(cb)

    def set_sub_stack_resolver(self, fn):
        """F-16: Funktion idx→CueStack|None setzen, mit der ``sub_stack_ref`` einer
        Cue zur Laufzeit aufgelöst wird (von AppState injiziert). None = keine Subs."""
        self._resolve_sub = fn

    # ── Serialisierung ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "mode": self.mode,
            "loop": self.loop,          # Rückwärtskompatibel für alte Leser
            "beat_sync": self.beat_sync,
            "beats_per_cue": self.beats_per_cue,
            "cues": [c.to_dict() for c in self.cues],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CueStack":
        stack = cls(d.get("name", "Cueliste"))
        mode = d.get("mode")
        if mode in cls.MODES:
            stack.mode = mode
        else:                            # Alt-Shows: nur "loop"-Bool
            stack.mode = "loop" if d.get("loop", False) else "single"
        stack.beat_sync = bool(d.get("beat_sync", False))
        try:
            stack.beats_per_cue = max(1, int(d.get("beats_per_cue", 4)))
        except (TypeError, ValueError):
            stack.beats_per_cue = 4
        for cd in d.get("cues", []):
            stack.add_cue(Cue.from_dict(cd))
        return stack
