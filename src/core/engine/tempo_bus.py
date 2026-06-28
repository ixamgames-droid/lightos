"""Tempo-Buses — benannte, unabhängige Tempo-Uhren mit kontinuierlicher Beat-Position.

Hintergrund / Designentscheidung (siehe docs/TEMPO_SYNC_PLAN.md):

- Bisher akkumuliert jeder zeitbasierte Effekt (EFX._phase, RGBMatrix._step) seine
  Phase selbst aus ``dt`` → zwei "gleich schnelle" Effekte driften auseinander, und
  der globale :class:`BPMManager` liefert nur DISKRETE Beats, keine kontinuierliche
  Position innerhalb eines Beats.
- Dieses Modul stellt benannte **Tempo-Buses** bereit. Jeder Bus hat eine eigene BPM
  (manual / tap / extern) und liefert eine fortlaufende ``position() = beat_count +
  beat_phase`` (Einheit: Beats). Ein Effekt, der auf einen Bus synchronisiert ist,
  leitet seine Render-Position daraus ab statt aus privatem ``dt`` → exakte,
  phasenkohärente Kopplung (×2, ×½, …), unabhängig von Startzeitpunkt und Frame-Jitter.
- Der reservierte Bus ``"default"`` PROXYt den bestehenden globalen :class:`BPMManager`
  (nur lesend über dessen vorhandene ``bpm``/``subscribe_beat``-API), damit das gesamte
  Alt-Verhalten (Carousel, audio_triggered Chaser, beat_sync CueStack) unverändert bleibt.
- Externe Quellen (der künftige eigene Wave-/Audio-Analyzer, OS2L, BeatDetector) docken
  über das schlanke :class:`TempoSource`-Protocol an, OHNE dieses Modul zu ändern.

Threading-Vertrag:

- :meth:`TempoBusManager.advance_frame` wird EINMAL pro Frame vom Render-Thread
  (``AppState._render_frame``) aufgerufen, BEVOR die Funktionen rendern. manual/tap/
  bpm_global-Buses werden AUSSCHLIESSLICH hier (auf dem Render-Thread) fortgeschrieben →
  alle Effekte sehen im selben Frame exakt dieselbe Position (within-frame-kohärent —
  die "nie Rot+dunkel"-Garantie hängt daran).
- Externe Quellen melden Beats auf FREMD-Threads; ``_on_external_beat`` mutiert nur unter
  ``_lock``. (Phase-6-TODO: zusätzlicher pro-Frame-Latch, damit auch ``external``
  within-frame-kohärent ist.) ``snapshot()``/``position()`` lesen unter ``_lock``.

Reine Zusatzschicht: ``advance_frame`` schreibt KEINE Universen und berührt weder den
Per-Frame-Clear noch das Write-Log (EE-02/WP-6).
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Protocol, runtime_checkable

from src.core.engine.bpm_manager import get_bpm_manager


# ── Externe Tempoquelle (Protocol) ──────────────────────────────────────────────

@runtime_checkable
class TempoSource(Protocol):
    """Vertrag für eine externe Tempoquelle (Wave-Analyzer, OS2L, BeatDetector …).

    Eine Quelle MUSS nur ``current_bpm()`` liefern und ``register_beat()`` unterstützen.

    OPTIONAL kann sie zusätzlich ``beat_phase() -> float | None`` implementieren: liefert
    sie eine kontinuierliche 0..1-Phase, lockt der Bus sich exakt darauf; fehlt die Methode
    (oder gibt sie ``None``), interpoliert der Bus die Phase selbst zwischen den gemeldeten
    Beats aus ``current_bpm()``. Der Bus entdeckt die Methode zur Laufzeit per ``getattr``,
    daher ist sie bewusst NICHT Teil des Pflicht-Protokolls.

    Der künftige eigene Analyzer implementiert einfach diese Methoden und ruft
    ``bus.attach_source(analyzer)`` — am Tempo-System muss dafür NICHTS geändert werden.
    """

    def current_bpm(self) -> float:
        """Aktuelle BPM-Schätzung (0 wenn unbekannt)."""
        ...

    def register_beat(self, cb: "Callable[[float], None]") -> None:
        """Registriert ``cb(monotonic_ts)``, aufgerufen pro erkanntem Beat/Downbeat."""
        ...


# ── Ein einzelner Tempo-Bus ─────────────────────────────────────────────────────

class TempoBus:
    """Eine benannte Tempo-Uhr mit kontinuierlicher Beat-Position.

    ``source``:
      * ``"manual"``     — BPM per :meth:`set_bpm` (VC-Tempo-Fader / Zahl), Free-Run.
      * ``"tap"``        — BPM per :meth:`tap` (eigene Historie, Mathematik wie BPMManager).
      * ``"bpm_global"`` — Proxy über den globalen :class:`BPMManager` (Bus ``"default"``).
      * ``"external"``   — folgt einer angedockten :class:`TempoSource`.

    ``role`` (Phase A — Master/Sub-Hierarchie, siehe docs/SPEED_MASTER_SUB_PLAN.md):
      * ``"master"`` (Default) — eigenständiges Tempo (eigene BPM via ``source``). Verhält
        sich exakt wie bisher (rückwärtskompatibel).
      * ``"sub"`` — folgt einem Master (``parent_id``) mit dem Faktor ``bus_multiplier``.
        Ein Sub integriert KEINE eigene Phase; ``position()``/``snapshot()``/``bpm`` werden
        beim Lesen aus dem Parent abgeleitet (``parent.position() × bus_multiplier``, über
        einen Anker stetig gehalten). Dadurch ist der Sub exakt phasen-gekoppelt an seinen
        Master — genau wie Effekte untereinander im Tempo-Sync-Plan, nur eine Ebene höher.
        ``parent_id == ""`` → der Default-Bus (Sound-BPM/globaler Leader).
    """

    # Spiegelt BPMManager (bewusst dupliziert, um Kopplung zu vermeiden).
    MIN_BPM = 20.0
    MAX_BPM = 999.0
    TAP_WINDOW_SEC = 2.0
    MAX_TAP_HISTORY = 4
    MAX_PARENT_CHAIN = 8   # Lese-Schutz gegen ringförmige Sub→Parent-Ketten

    def __init__(self, bus_id: str, source: str = "manual"):
        self.bus_id: str = str(bus_id)
        self.source: str = source
        self._bpm: float = 0.0            # 0 == aus / Free-Run gestoppt
        self._beat_count: int = 0         # ganze Beats seit Bus-Start (Integer-Anteil)
        self._beat_phase: float = 0.0     # [0,1) — Bruchteil in den aktuellen Beat
        self._last_beat_mono: float = 0.0 # monotonic des letzten (Re-)Anker-Beats
        self._last_taps: list[float] = []
        self._ext_source: "TempoSource | None" = None
        self._running: bool = True
        # ── Master/Sub-Hierarchie (Phase A) ──────────────────────────────────────
        self.role: str = "master"          # "master" | "sub"
        self.parent_id: str = ""           # bei sub: Master-ID ("" → Default/Sound-BPM)
        self.bus_multiplier: float = 1.0   # Faktor zum Parent: effektive Rate = parent × m
        self._sub_local_origin: float = 0.0   # Anker: eigene Position beim letzten Re-Anker
        self._sub_parent_origin: float = 0.0  # Anker: Parent-Position beim letzten Re-Anker
        self._sync_origin: float | None = None  # Auto-Sync: gemeinsamer Beat-Raster-Ursprung
        self._lock = threading.RLock()

    # ── BPM-Quellen ─────────────────────────────────────────────────────────────

    @property
    def bpm(self) -> float:
        # Ein Sub hat keine eigene BPM — sie ist parent × bus_multiplier.
        if self.role == "sub":
            return self._eff_bpm()
        # Master: bei scharfem Grand-Master gilt dessen Takt, sonst die eigene BPM.
        gm = self._grandmaster_drive()
        if gm > 0:
            return gm
        return self._bpm

    def _parent_bus(self) -> "TempoBus | None":
        """Der Master-Bus, dem dieser Sub folgt (``parent_id``; "" → Default-Bus)."""
        try:
            mgr = get_tempo_bus_manager()
        except Exception:
            return None
        return mgr.get(self.parent_id or TempoBusManager.DEFAULT_BUS)

    def _grandmaster_drive(self) -> float:
        """Grand-Master-Takt, falls scharf und gesetzt (>0), sonst 0.0. Reiner
        Attribut-Lesezugriff am Manager (kein Lock) → keine verschachtelte Sperre,
        wenn dies aus ``advance_frame`` unter dem Bus-Lock aufgerufen wird."""
        try:
            mgr = get_tempo_bus_manager()
        except Exception:
            return 0.0
        if mgr is not None and getattr(mgr, "_grandmaster_armed", False):
            gb = float(getattr(mgr, "_grandmaster_bpm", 0.0) or 0.0)
            if gb > 0:
                return gb
        return 0.0

    def _effective_bpm(self) -> float:
        """BPM der EIGENEN Quelle (Master-Pfad) — je nach ``source``."""
        if self.source == "bpm_global":
            return get_bpm_manager().bpm
        if self.source == "external" and self._ext_source is not None:
            try:
                return float(self._ext_source.current_bpm())
            except Exception:
                return 0.0
        return self._bpm

    def _eff_bpm(self, depth: int = 0) -> float:
        """Effektive BPM inkl. Master/Sub-Kette: sub = parent × bus_multiplier.
        Auf Master-Ebene gilt der Grand-Master-Takt, sobald er scharf ist — Subs
        erben ihn dadurch automatisch über ihren Parent (relativ × Faktor)."""
        if self.role == "sub" and depth < self.MAX_PARENT_CHAIN:
            parent = self._parent_bus()
            if parent is not None and parent is not self:
                return max(0.0, parent._eff_bpm(depth + 1)) * max(0.0, float(self.bus_multiplier))
            return 0.0
        gm = self._grandmaster_drive()
        if gm > 0:
            return gm
        return self._effective_bpm()

    def set_bpm(self, bpm: float) -> None:
        """Setzt die Bus-BPM (0 = aus).

        Für ``bpm_global`` ist dies nur eine ANFRAGE an den globalen
        :class:`BPMManager` über ``request_bpm`` — der Leader behält die Hoheit:
        steht er auf MANUAL oder ist er per Lock eingefroren, wird die Anfrage
        ignoriert (ein ``bpm_global``-Bus SPIEGELT die globale BPM, überschreibt
        sie aber nicht und untergräbt damit nicht Lock/Präzedenz). Anschließend
        wird die lokale BPM auf den TATSÄCHLICHEN globalen Wert nachgezogen
        (analog zu :meth:`tap`), damit ``bpm``/``snapshot`` konsistent bleiben.

        Ein **Sub** hat keine eigene BPM (sie ist abgeleitet) → no-op; sein Tempo
        wird über :meth:`set_bus_multiplier` relativ zum Master eingestellt."""
        if self.role == "sub":
            return
        bpm = float(bpm)
        if bpm < 0:
            bpm = 0.0
        if bpm > 0 and (bpm < self.MIN_BPM or bpm > self.MAX_BPM):
            bpm = max(self.MIN_BPM, min(self.MAX_BPM, bpm))
        with self._lock:
            if self.source == "bpm_global":
                mgr = get_bpm_manager()
                mgr.request_bpm(bpm, "tempobus")
                self._bpm = mgr.bpm   # bei Lock/MANUAL bleibt die globale BPM stehen
            else:
                self._bpm = bpm

    def tap(self) -> float:
        """Tap-Tempo auf DIESEN Bus. Gleiche Mathematik wie ``BPMManager.tap``
        (Mittel der letzten 4 Intervalle). Liefert die aktuelle Bus-BPM zurück.

        Ein **Sub** ignoriert Tap (Tempo kommt vom Master) → liefert nur die
        abgeleitete BPM zurück."""
        if self.role == "sub":
            return self.bpm
        now = time.monotonic()
        if self.source == "bpm_global":
            # Leader-Lock respektieren (s. set_bpm): gesperrt -> kein Tap-Override.
            mgr = get_bpm_manager()
            if not getattr(mgr, "is_locked", False):
                mgr.tap()
            with self._lock:
                self._bpm = mgr.bpm
                return self._bpm
        bpm = 0.0
        with self._lock:
            if self._last_taps and (now - self._last_taps[-1] > self.TAP_WINDOW_SEC):
                self._last_taps = []
            self._last_taps.append(now)
            if len(self._last_taps) > self.MAX_TAP_HISTORY + 1:
                self._last_taps = self._last_taps[-(self.MAX_TAP_HISTORY + 1):]
            self.source = "tap"
            if len(self._last_taps) < 2:
                return self._bpm
            intervals = [self._last_taps[i + 1] - self._last_taps[i]
                         for i in range(len(self._last_taps) - 1)]
            avg = sum(intervals) / len(intervals)
            if avg <= 0:
                return self._bpm
            bpm = 60.0 / avg
        self.set_bpm(bpm)
        return self._bpm

    def attach_source(self, src: "TempoSource") -> None:
        """Dockt eine externe Tempoquelle an (Wave-Analyzer/OS2L/BeatDetector)."""
        with self._lock:
            self._ext_source = src
            self.source = "external"
            self._last_beat_mono = 0.0
        try:
            src.register_beat(self._on_external_beat)
        except Exception as exc:  # pragma: no cover - defensiv
            print(f"[TempoBus {self.bus_id}] attach_source error: {exc}")

    def detach_source(self) -> None:
        with self._lock:
            self._ext_source = None
            if self.source == "external":
                self.source = "manual"

    # ── Phase / Position ────────────────────────────────────────────────────────

    def advance_frame(self, dt: float) -> None:
        """Schreibt die Beat-Phase um ``dt`` (Sekunden) fort. Einmal pro Frame vom
        Render-Thread.

        - sub: integriert NICHTS — Position wird beim Lesen aus dem Parent abgeleitet
          (``_position``), daher Reihenfolge-unabhaengig und within-frame-kohaerent.
        - Grand-Master scharf (Master-Bus): der Bus integriert mit dem Grand-Master-Takt
          (uebertrumpft die eigene Quelle); ``_bpm`` bleibt unangetastet, damit beim
          Entschaerfen die eigene BPM zurueckkehrt.
        - manual/tap/bpm_global: integriert aus der effektiven BPM und zaehlt ganze Beats.
        - external: kontinuierliche ``beat_phase()`` der Quelle oder interpolierte Phase
          (bei 1.0 geklemmt — ganze Beats zaehlt ``_on_external_beat``).

        TODO Phase 6 (externe Quellen): pro-Frame eingefrorene Position latchen, damit
        external within-frame-kohaerent ist, auch wenn ein Beat-Callback im tick() landet."""
        with self._lock:
            if not self._running:
                return
            if self.role == "sub":
                return  # Position wird lazy aus dem Parent abgeleitet
            gm = self._grandmaster_drive()
            if gm > 0:
                # Grand-Master uebertrumpft die eigene Quelle (auch external/bpm_global).
                self._beat_phase += (gm / 60.0) * max(0.0, float(dt))
                while self._beat_phase >= 1.0:
                    self._beat_phase -= 1.0
                    self._beat_count += 1
                return
            if self.source == "external" and self._ext_source is not None:
                bp = getattr(self._ext_source, "beat_phase", None)
                ov = None
                if callable(bp):
                    try:
                        ov = bp()
                    except Exception:
                        ov = None
                if isinstance(ov, (int, float)):
                    self._beat_phase = float(ov) % 1.0
                    return
                bpm = self._effective_bpm()
                self._bpm = bpm
                if bpm <= 0:
                    return
                self._beat_phase += (bpm / 60.0) * max(0.0, float(dt))
                if self._beat_phase >= 1.0:
                    self._beat_phase = 1.0 - 1e-9  # ganze Beats zaehlt _on_external_beat
                return
            if self.source == "manual":
                bpm = self._bpm
            else:  # bpm_global
                bpm = self._effective_bpm()
                self._bpm = bpm
            if bpm <= 0:
                return  # aus → Position eingefroren (Effekt nutzt Free-Run-Fallback)
            self._beat_phase += (bpm / 60.0) * max(0.0, float(dt))
            while self._beat_phase >= 1.0:
                self._beat_phase -= 1.0
                self._beat_count += 1

    def _on_global_beat(self, beat_index: int) -> None:
        """Optionaler FORWARD-Re-Anker auf einen globalen Beat. NICHT standardmaessig
        verdrahtet (der Default-Bus integriert die globale BPM monoton, s. _ensure_default).
        Relativ (+1) statt absolut, damit die Position auch bei BPMManager.reset() nie
        rueckwaerts springt, falls dieser Hook spaeter explizit genutzt wird."""
        with self._lock:
            self._beat_count += 1
            self._beat_phase = 0.0
            self._last_beat_mono = time.monotonic()

    def _on_external_beat(self, ts: float) -> None:
        """Re-Anker auf einen Beat der externen Quelle (läuft auf Audio-Thread)."""
        with self._lock:
            self._beat_count += 1
            self._beat_phase = 0.0
            try:
                self._last_beat_mono = float(ts)
            except Exception:
                self._last_beat_mono = time.monotonic()

    def reset_phase(self) -> None:
        """Setzt die Bus-Position auf die Eins zurück (neuer Downbeat-Ursprung).

        Bei einem Sub bedeutet das: jetzt ist sein Downbeat — der Anker wird so
        gesetzt, dass seine Position bei 0 startet (relativ zum aktuellen Parent)."""
        if self.role == "sub":
            pp = self._parent_position(0)
            with self._lock:
                self._sub_local_origin = 0.0
                self._sub_parent_origin = pp
                self._last_beat_mono = time.monotonic()
            return
        with self._lock:
            self._beat_count = 0
            self._beat_phase = 0.0
            self._last_beat_mono = time.monotonic()

    def _parent_position(self, depth: int) -> float:
        """Position des Parents (für Subs). 0, wenn kein/zyklischer Parent."""
        if depth >= self.MAX_PARENT_CHAIN:
            return 0.0
        parent = self._parent_bus()
        if parent is None or parent is self:
            return 0.0
        return parent._position(depth + 1)

    def _position(self, depth: int = 0) -> float:
        """Kontinuierliche Position in Beats (rollenabhängig, mit Ketten-Schutz)."""
        if self.role == "sub" and depth < self.MAX_PARENT_CHAIN:
            pp = self._parent_position(depth)
            with self._lock:
                return self._sub_local_origin + (pp - self._sub_parent_origin) * max(0.0, float(self.bus_multiplier))
        with self._lock:
            return self._beat_count + self._beat_phase

    def position(self) -> float:
        """Kontinuierliche, monoton steigende Position in Beats."""
        return self._position(0)

    def snapshot(self) -> tuple[float, int, float, float]:
        """Atomarer (bpm, beat_count, beat_phase, position)-Schnappschuss."""
        if self.role == "sub":
            pos = self._position(0)
            if pos < 0:
                pos = 0.0
            bc = int(pos)
            return (self._eff_bpm(0), bc, pos - bc, pos)
        with self._lock:
            pos = self._beat_count + self._beat_phase
            return (self._bpm, self._beat_count, self._beat_phase, pos)

    def sync(self, reset_downbeat: bool = False) -> None:
        """Bus-Sync (SYNC-Knopf): optional Downbeat-Reset, dann re-ankert ALLE Effekte,
        die auf DIESEM Bus liegen, auf ``jetzt`` -> sie beginnen ihren Zyklus gemeinsam
        auf demselben Schlag, auch bei unterschiedlichen ``tempo_multiplier`` (z. B. ×1
        und ×0.5 starten zusammen und laufen danach harmonisch). Setzt zugleich den
        Auto-Sync-Ursprung neu.

        WICHTIG: Zugehoerigkeit wird ueber den Manager AUFGELOEST (``get(id) is self``),
        nicht per String-Vergleich — sonst greifen die Alias-IDs ``""``/``"default"``/
        ``"Global"`` (alle = Default-Bus) nicht und der Sync waere ein stiller No-op."""
        if reset_downbeat:
            self.reset_phase()
        pos = self.position()
        self._sync_origin = pos
        try:
            mgr = get_tempo_bus_manager()
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
            for f in fm.all():
                if not hasattr(f, "_beat_anchor"):
                    continue
                try:
                    if mgr.get(getattr(f, "tempo_bus_id", "")) is self:
                        setattr(f, "_beat_anchor", pos)
                except Exception:
                    continue
        except Exception:
            pass

    def take_anchor(self) -> float:
        """Anker fuer einen STARTENDEN Effekt auf diesem Bus.

        Auto-Sync AUS (Default): liefert die aktuelle Bus-Position -> der Effekt
        beginnt bei seinem eigenen Null (altes Verhalten, byte-identisch).
        Auto-Sync AN: liefert den gemeinsamen ``_sync_origin`` -> der erste Effekt legt
        ihn fest, spaeter startende Effekte uebernehmen ihn und liegen damit automatisch
        phasengleich auf demselben Beat-Raster (egal wann sie gedrueckt werden). Der
        SYNC-Knopf (``sync()``) re-basiert den Ursprung auf ``jetzt``."""
        try:
            auto = get_tempo_bus_manager().auto_sync
        except Exception:
            auto = False
        if not auto:
            return self.position()
        if self._sync_origin is None:
            self._sync_origin = self.position()
        return self._sync_origin

    # ── Master/Sub-Konfiguration ──────────────────────────────────────────────────

    def _would_cycle(self, new_parent_id: str) -> bool:
        """True, wenn ``new_parent_id`` (über die Sub-Kette) auf diesen Bus zurückführt."""
        pid = (new_parent_id or TempoBusManager.DEFAULT_BUS)
        try:
            mgr = get_tempo_bus_manager()
        except Exception:
            return False
        seen: set[str] = set()
        steps = 0
        while pid and pid not in seen and steps < self.MAX_PARENT_CHAIN + 2:
            if pid == self.bus_id:
                return True
            seen.add(pid)
            p = mgr.get(pid)
            if p is None or p.role != "sub":
                break  # ein Master beendet die Kette
            pid = (p.parent_id or TempoBusManager.DEFAULT_BUS)
            steps += 1
        return False

    def set_role(self, role: str) -> None:
        """Schaltet zwischen Master (eigene BPM) und Sub (folgt Parent × Faktor) um.
        Die Position bleibt dabei stetig — ein angehängter Effekt springt nicht."""
        new_role = "sub" if str(role) == "sub" else "master"
        if new_role == self.role:
            return
        if new_role == "sub":
            with self._lock:
                cur = self._beat_count + self._beat_phase   # bisherige Master-Position
            pp = self._parent_position(0)
            with self._lock:
                self.role = "sub"
                self._sub_local_origin = cur                # stetig fortsetzen
                self._sub_parent_origin = pp
        else:
            pos = self._position(0)         # aktuelle abgeleitete Sub-Position …
            bpm = self._eff_bpm(0)          # … und Rate übernehmen
            if pos < 0:
                pos = 0.0
            with self._lock:
                self.role = "master"
                self.source = "manual"
                self._bpm = max(0.0, min(self.MAX_BPM, float(bpm)))
                self._beat_count = int(pos)
                self._beat_phase = pos - int(pos)

    def set_parent(self, parent_id: str) -> bool:
        """Wählt den Master, dem dieser Sub folgt. Verweigert Selbst-/Ringbezug.
        Hält die Position über den Parentwechsel stetig. Liefert True bei Erfolg."""
        pid = str(parent_id or "")
        if pid == self.bus_id or self._would_cycle(pid):
            return False
        cur = self._position(0)             # Position relativ zum ALTEN Parent
        with self._lock:
            self.parent_id = pid
        pp = self._parent_position(0)        # NEUER Parent
        with self._lock:
            self._sub_local_origin = cur     # stetig: keine Sprünge beim Umhängen
            self._sub_parent_origin = pp
        return True

    def set_bus_multiplier(self, mult: float) -> None:
        """Faktor zum Parent (``½ ¼ ×2 ×4`` …). Re-ankert stetig, sodass die Rate
        ab jetzt umschaltet, die Position aber nicht springt."""
        try:
            m = float(mult)
        except (TypeError, ValueError):
            return
        if m <= 0:
            return
        if self.role == "sub":
            cur = self._position(0)
            pp = self._parent_position(0)
            with self._lock:
                self._sub_local_origin = cur
                self._sub_parent_origin = pp
                self.bus_multiplier = m
        else:
            with self._lock:
                self.bus_multiplier = m

    def reanchor_to_parent(self) -> None:
        """Frischer Downbeat-Bezug zum aktuellen Parent (z. B. nach Show-Load):
        die Sub-Position startet bei 0, relativ zur jetzigen Parent-Position."""
        if self.role != "sub":
            return
        pp = self._parent_position(0)
        with self._lock:
            self._sub_local_origin = 0.0
            self._sub_parent_origin = pp

    # ── Persistenz ────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        # Hierarchie-Felder nur emittieren, wenn sie vom Default abweichen → Alt-Form
        # (und Alt-Shows / bestehende Round-Trip-Tests) bleiben byte-genau erhalten.
        with self._lock:
            d = {"bus_id": self.bus_id, "source": self.source, "bpm": self._bpm}
            if self.role != "master":
                d["role"] = self.role
            if self.parent_id:
                d["parent_id"] = self.parent_id
            if self.bus_multiplier != 1.0:
                d["bus_multiplier"] = self.bus_multiplier
            return d

    @classmethod
    def from_dict(cls, data: dict) -> "TempoBus":
        bus = cls(str(data.get("bus_id", "")), source=str(data.get("source", "manual")))
        raw = data.get("bpm", 0.0)
        if isinstance(raw, (int, float, str)):
            try:
                bus._bpm = float(raw)
            except (TypeError, ValueError):
                bus._bpm = 0.0
        bus.role = "sub" if str(data.get("role", "master")) == "sub" else "master"
        bus.parent_id = str(data.get("parent_id", "") or "")
        try:
            bus.bus_multiplier = float(data.get("bus_multiplier", 1.0))
        except (TypeError, ValueError):
            bus.bus_multiplier = 1.0
        if bus.bus_multiplier <= 0:
            bus.bus_multiplier = 1.0
        return bus


# ── Manager / Singleton ─────────────────────────────────────────────────────────

class TempoBusManager:
    """Verwaltet alle Tempo-Buses. Der reservierte Bus ``"default"`` existiert immer
    und proxyt den globalen :class:`BPMManager`."""

    DEFAULT_BUS = "default"
    # Feste Buses fuer die VC (Entscheidung: A/B/C/D als feste Chips). Werden bei
    # Bedarf lazy erzeugt (manual, bpm 0, bis ein Tempo-/Tap-Widget sie setzt).
    FIXED_BUSES = ("A", "B", "C", "D")

    def __init__(self):
        self._buses: dict[str, TempoBus] = {}
        self._lock = threading.RLock()
        self._armed_bus_id: str = ""   # vom VCBusSelector gesetzter "scharfer" Bus
        # ── Grand-Master-Override (Phase B) ──────────────────────────────────────
        # Wenn "scharf", liefert JEDER Master-Bus den Grand-Master-Takt (Subs bleiben
        # relativ über ihren Parent). Default aus → keine Wirkung. Eigene Tap-Historie.
        self._grandmaster_armed: bool = False
        self._grandmaster_bpm: float = 0.0
        self._gm_taps: list[float] = []
        # Auto-Sync: neu startende bus-gekoppelte Effekte uebernehmen den gemeinsamen
        # Beat-Raster-Ursprung ihres Bus -> phasengleich, egal wann gedrueckt.
        # Taktgleich ist der sichere Show-Default. Bewusst frei laufende Effekte
        # waehlen Tempo-Bus ""; Auto-Sync selbst bleibt im BPM-Tab abschaltbar.
        self._auto_sync: bool = True
        self._ensure_default()

    def _ensure_default(self) -> None:
        # Der Default-Bus folgt der globalen BPM per reiner, MONOTONER Integration in
        # advance_frame (KEIN subscribe_beat-Re-Anker). So springt seine Position nie
        # rueckwaerts, auch wenn BPMManager._beat_index per reset() auf 0 faellt, und
        # kein Fremd-Thread-Callback mutiert ihn (within-frame-kohaerent). Audio-/
        # Beat-genaues Locken liefert stattdessen eine angedockte externe Quelle.
        with self._lock:
            if self.DEFAULT_BUS not in self._buses:
                self._buses[self.DEFAULT_BUS] = TempoBus(self.DEFAULT_BUS, source="bpm_global")

    def get(self, bus_id: str | None) -> "TempoBus | None":
        """Liefert den Bus. ``""``/``None``/``"default"``/``"global"`` → Default-Bus. Unbekannt → None.

        ``"global"`` (case-insensitiv) ist ein UI-freundlicher Alias fuer den
        Default-Bus, der die globale BPM spiegelt — so kann ein Effekt im
        Tempo-Bus-Dropdown sichtbar an den Master-BPM gekoppelt werden (F7).
        """
        bid = bus_id or self.DEFAULT_BUS
        if isinstance(bid, str) and bid.strip().lower() in ("", "default", "global"):
            bid = self.DEFAULT_BUS
        with self._lock:
            return self._buses.get(bid)

    def toggle_freeze(self) -> bool:
        """Freeze-Toggle (F3): friert ALLE Tempi ein (alle Master-Buses + globaler
        BPM-Leader → 0) bzw. taut wieder auf. Sub-Buses folgen ihren Parents.
        Bus-gekoppelte Effekte HALTEN dann ihre Position (F5-Hold). Speichert die
        vorigen BPMs/Leader-Zustand fuer das Auftauen. Returns True = jetzt eingefroren.
        """
        from src.core.engine.bpm_manager import get_bpm_manager
        st = getattr(self, "_freeze_state", None)
        if st is None:
            saved: dict[str, float] = {}
            with self._lock:
                for b in list(self._buses.values()):
                    if b.role != "sub" and b.source != "bpm_global":
                        saved[b.bus_id] = b._bpm
                        b.set_bpm(0.0)
            gstate = None
            try:
                mgr = get_bpm_manager()
                gstate = (mgr.bpm, bool(mgr.is_locked), mgr.mode)
                mgr.set_bpm(0.0)
                mgr.set_locked(True)
            except Exception:
                pass
            self._freeze_state = {"buses": saved, "global": gstate}
            return True
        # auftauen
        with self._lock:
            for bid, bpm in (st.get("buses") or {}).items():
                b = self._buses.get(bid)
                if b is not None:
                    b.set_bpm(bpm)
        g = st.get("global")
        if g is not None:
            try:
                mgr = get_bpm_manager()
                bpm0, locked0, mode0 = g
                mgr.set_locked(bool(locked0))
                try:
                    mgr.set_mode(mode0)
                except Exception:
                    pass
                if bpm0 and bpm0 > 0:
                    mgr.set_bpm(bpm0)
            except Exception:
                pass
        self._freeze_state = None
        return False

    def is_frozen(self) -> bool:
        """True, wenn gerade per toggle_freeze() eingefroren."""
        return getattr(self, "_freeze_state", None) is not None

    def ensure_bus(self, bus_id: str, source: str = "manual") -> TempoBus:
        """Holt oder erzeugt einen benannten Bus."""
        bid = bus_id or self.DEFAULT_BUS
        with self._lock:
            bus = self._buses.get(bid)
            if bus is None:
                bus = TempoBus(bid, source=source)
                self._buses[bid] = bus
            return bus

    @property
    def armed_bus_id(self) -> str:
        """Der vom VCBusSelector 'scharf geschaltete' Bus (Standard '' = Default)."""
        return self._armed_bus_id

    @armed_bus_id.setter
    def armed_bus_id(self, bus_id: str) -> None:
        self._armed_bus_id = str(bus_id or "")

    def resolve(self, bus_id: "str | None") -> "TempoBus | None":
        """Effektiver Bus fuer ein VC-Widget bzw. einen Effekt: explizite ``bus_id``,
        sonst der scharfe Bus (VCBusSelector), sonst der Default-Bus. Feste Buses
        (A/B/C/D) werden bei Bedarf erzeugt. Das ist der Haupt-Hook fuer die VC:
        ``get_tempo_bus_manager().resolve(widget.tempo_bus_id).tap()/.sync()/.set_bpm(x)``."""
        bid = (bus_id or "").strip() or self._armed_bus_id or self.DEFAULT_BUS
        if bid in self.FIXED_BUSES:
            return self.ensure_bus(bid)
        return self.get(bid)

    def remove_bus(self, bus_id: str) -> None:
        if not bus_id or bus_id == self.DEFAULT_BUS:
            return
        with self._lock:
            self._buses.pop(bus_id, None)

    def all_buses(self) -> list[TempoBus]:
        with self._lock:
            return list(self._buses.values())

    def named_buses(self) -> list[TempoBus]:
        """Alle Buses außer dem reservierten Default-Bus."""
        with self._lock:
            return [b for b in self._buses.values() if b.bus_id != self.DEFAULT_BUS]

    def master_buses(self) -> list[TempoBus]:
        """Alle Master-Buses außer dem reservierten Default-Bus (für Parent-Auswahl
        eines Subs in der Konfig-GUI; der Default/Sound-BPM-Bus wird dort separat als
        Standard-Parent angeboten)."""
        with self._lock:
            return [b for b in self._buses.values()
                    if b.bus_id != self.DEFAULT_BUS and getattr(b, "role", "master") == "master"]

    # ── Grand-Master-Override ──────────────────────────────────────────────────────

    @property
    def grandmaster_armed(self) -> bool:
        """True → alle Master-Buses laufen auf dem Grand-Master-Takt (Subs relativ)."""
        return self._grandmaster_armed

    @property
    def grandmaster_bpm(self) -> float:
        return self._grandmaster_bpm

    @property
    def auto_sync(self) -> bool:
        """True → neu startende bus-gekoppelte Effekte uebernehmen den gemeinsamen
        Beat-Raster-Ursprung ihres Bus (phasengleicher Start, egal wann gedrueckt)."""
        return self._auto_sync

    def set_auto_sync(self, enabled: bool) -> None:
        self._auto_sync = bool(enabled)

    def set_grandmaster_armed(self, armed: bool) -> None:
        """Schärft/entschärft den Grand-Master. Scharf + bpm>0 übertrumpft alle Master.
        Beim Entschärfen kehren die Master zu ihrer eigenen Quelle zurück (ihr ``_bpm``
        wurde währenddessen NICHT überschrieben)."""
        with self._lock:
            self._grandmaster_armed = bool(armed)

    def set_grandmaster_bpm(self, bpm: float) -> None:
        """Setzt den Grand-Master-Takt direkt (Zahlenfeld). 0 = aus (keine Wirkung)."""
        try:
            b = float(bpm)
        except (TypeError, ValueError):
            return
        if b < 0:
            b = 0.0
        if b > 0:
            b = max(TempoBus.MIN_BPM, min(TempoBus.MAX_BPM, b))
        with self._lock:
            self._grandmaster_bpm = b

    def tap_grandmaster(self) -> float:
        """Tap-Tempo für den Grand-Master (gleiche Mathematik wie ``BPMManager.tap`` /
        ``TempoBus.tap``: Mittel der letzten 4 Intervalle). Liefert die neue BPM."""
        now = time.monotonic()
        with self._lock:
            if self._gm_taps and (now - self._gm_taps[-1] > TempoBus.TAP_WINDOW_SEC):
                self._gm_taps = []
            self._gm_taps.append(now)
            if len(self._gm_taps) > TempoBus.MAX_TAP_HISTORY + 1:
                self._gm_taps = self._gm_taps[-(TempoBus.MAX_TAP_HISTORY + 1):]
            if len(self._gm_taps) < 2:
                return self._grandmaster_bpm
            intervals = [self._gm_taps[i + 1] - self._gm_taps[i]
                         for i in range(len(self._gm_taps) - 1)]
            avg = sum(intervals) / len(intervals)
            if avg <= 0:
                return self._grandmaster_bpm
            bpm = 60.0 / avg
        self.set_grandmaster_bpm(bpm)
        return self._grandmaster_bpm

    def grandmaster_to_dict(self) -> dict:
        """Persistierbarer Grand-Master-Zustand (eigener Show-Block, additiv).
        Traegt auch das Auto-Sync-Flag mit (der Default-Bus selbst wird nicht serialisiert)."""
        with self._lock:
            return {"armed": self._grandmaster_armed, "bpm": self._grandmaster_bpm,
                    "auto_sync": self._auto_sync}

    def load_grandmaster(self, data) -> None:
        """Lädt den Grand-Master-Zustand.

        Fehlt ``auto_sync`` (Alt-Show/neue leere Show), gilt der sichere Default
        True. Ein explizit gespeichertes False bleibt eine bewusste Abwahl.
        """
        d = data if isinstance(data, dict) else {}
        self.set_grandmaster_bpm(d.get("bpm", 0.0))
        self.set_grandmaster_armed(bool(d.get("armed", False)))
        self.set_auto_sync(bool(d.get("auto_sync", True)))

    def advance_frame(self, dt: float) -> None:
        """Schreibt ALLE Buses um ``dt`` fort (einmal pro Frame, Render-Thread)."""
        for bus in self.all_buses():
            bus.advance_frame(dt)

    # ── Persistenz ────────────────────────────────────────────────────────────────

    def to_dict(self) -> list[dict]:
        """Serialisiert die benannten Buses (Default-Bus wird nicht gespeichert)."""
        return [b.to_dict() for b in self.named_buses()]

    def load_dict(self, data) -> None:
        """Lädt Buses aus einer Show. Entfernt vorhandene benannte Buses, Default bleibt."""
        with self._lock:
            for bid in list(self._buses.keys()):
                if bid != self.DEFAULT_BUS:
                    self._buses.pop(bid, None)
        for entry in (data or []):
            try:
                bus = TempoBus.from_dict(entry)
                if bus.bus_id and bus.bus_id != self.DEFAULT_BUS:
                    with self._lock:
                        self._buses[bus.bus_id] = bus
            except Exception:
                continue
        # Subs frisch auf ihren (jetzt vollständig geladenen) Parent ankern, damit ihre
        # Position bei 0 startet — unabhängig von der Lade-Reihenfolge.
        for bus in self.all_buses():
            if getattr(bus, "role", "master") == "sub":
                try:
                    bus.reanchor_to_parent()
                except Exception:
                    continue


_mgr: TempoBusManager | None = None


def get_tempo_bus_manager() -> TempoBusManager:
    global _mgr
    if _mgr is None:
        _mgr = TempoBusManager()
    return _mgr


def reset_tempo_bus_manager() -> None:
    """Test-Hilfe: verwirft den Singleton (nächster Zugriff baut ihn neu).

    Der Default-Bus abonniert KEINE globalen Beats mehr (reine Integration), daher
    sammeln sich auch keine Beat-Callbacks an — es genügt, den Singleton zu verwerfen."""
    global _mgr
    _mgr = None
