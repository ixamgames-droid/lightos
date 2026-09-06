"""Base Function class and enums for QLC+ v5 function types."""
from __future__ import annotations
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.dmx.universe import Universe
    from src.core.database.models import PatchedFixture

from .fade_curve import eval_named   # ARC-04/FW-4: Form der Hüllkurve (Leaf-Modul)


_UsesDmx = None


def gibt_ueber_dmx_aus(fixture) -> bool:
    """Darf fuer dieses Geraet ``address + channel`` gerechnet werden? (QA-78)

    Duenne, gecachte Huelle um ``app_state.fixture_uses_dmx``. Netzwerk-Laser
    (Ether Dream, IDN) tragen ``universe``/``address`` nur als bedeutungslose
    Platzhalter; wer damit rechnet, schreibt in die Spans ECHTER Geraete.

    ★ **Warum das hier steht und nicht sechsmal einzeln.** Die Regel stand seit
    LAS-04 nur im Docstring von ``fixture_uses_dmx`` — „JEDE Stelle, die
    ``fx.address + ch.channel_number`` rechnet, MUSS vorher hier fragen". Eine
    Regel, die nur im Docstring steht, ist nicht durchgesetzt, sondern eine
    Bitte: gemessen fragten **acht von neun** Schreibern nicht. ``scene.py``
    war der erste belegte Schaden (ENG-20b).

    ⚠️ **Spaet importiert und EINMAL gemerkt.** ``app_state`` zieht viel mit,
    und diese Funktion sitzt in Frame-Pfaden. Gemessen kostet der erste Aufruf
    in einem Prozess, der ``app_state`` noch nicht kennt, rund eine halbe
    Sekunde; danach ist es ein Attributzugriff. In der App ist das Modul
    laengst geladen, bevor eine Funktion laeuft.

    ⚠️ **Im Zweifel JA.** Faellt die Aufloesung aus, wird geschrieben wie
    bisher — eine Funktion, die stumm nichts mehr tut, ist auf der Buehne
    schlimmer als eine, die zu viel tut.
    """
    global _UsesDmx
    if _UsesDmx is None:
        try:
            from src.core.app_state import fixture_uses_dmx
        except Exception:
            return True
        _UsesDmx = fixture_uses_dmx
    try:
        return bool(_UsesDmx(fixture))
    except Exception:
        return True


class FunctionType(Enum):
    Scene = "Scene"
    Chaser = "Chaser"
    Sequence = "Sequence"
    Collection = "Collection"
    Show = "Show"
    EFX = "EFX"
    RGBMatrix = "RGBMatrix"
    Audio = "Audio"
    Script = "Script"
    MappedChannelChange = "MappedChannelChange"


class RunOrder(Enum):
    Loop = "Loop"
    SingleShot = "SingleShot"
    PingPong = "PingPong"
    Random = "Random"


class Direction(Enum):
    Forward = "Forward"
    Backward = "Backward"


_next_id = 1


def _alloc_id() -> int:
    global _next_id
    fid = _next_id
    _next_id += 1
    return fid


def bump_next_id(used_ids) -> None:
    """Hebt den globalen ID-Zaehler an, damit kuenftige _alloc_id()-Aufrufe
    keine bereits vergebene (z. B. aus einer geladenen Show stammende) ID
    erneut liefern. Verhindert stilles Ueberschreiben geladener Funktionen."""
    global _next_id
    for fid in used_ids:
        try:
            if int(fid) >= _next_id:
                _next_id = int(fid) + 1
        except (TypeError, ValueError):
            continue


class Function:
    """Abstract base for all QLC+ function types."""

    function_type: FunctionType = FunctionType.Scene  # overridden by subclasses
    # Zeitbasierte Effekt-Subtypen setzen dies auf True. Neue Effekte folgen dann
    # standardmaessig der globalen BPM; statische Funktionen bleiben unberuehrt.
    # Alt-Shows ohne tempo_bus_id laedt FunctionManager weiterhin als Free-Run.
    tempo_sync_default: bool = False

    def __init__(self, name: str = "Neue Funktion", fid: int | None = None):
        self.id: int = fid if fid is not None else _alloc_id()
        self.name: str = name
        self._running: bool = False
        self._elapsed: float = 0.0
        # Per-Effekt-Master (Block B). intensity skaliert die Ausgabe (0..1,
        # angewandt im FunctionManager.tick), speed ist ein Zeit-Multiplikator
        # (0.1..4.0, von zeitbasierten Subtypen selbst angewandt). Chaser und
        # Sequence definieren self.speed bereits eigenstaendig (gleicher Name).
        self.intensity: float = 1.0
        self.speed: float = 1.0
        # Bibliotheks-Ordner (verschachtelbar, "/"-getrennt). "" = Wurzel.
        # Pro Show gespeichert; siehe docs/PROGRAMMER_REBUILD.md (Phase 1).
        self.folder: str = ""
        # F-17: Layer-Prioritaet beim Engine-Merge. Hoehere Prioritaet gewinnt bei
        # Kanal-/Attribut-Ueberschneidung (tickt zuletzt -> LTP). Gleiche Prioritaet
        # faellt auf die Start-Reihenfolge zurueck (Verhalten wie bisher, Default 0).
        self.priority: int = 0
        # ARC-04: zeitbasierte Ein-/Ausblend-Huellkurve (Sekunden, 0 = aus). Wirkt als
        # Output-Multiplikator ueber ALLE Kanaele der Funktion (nicht nur Dimmer),
        # angewandt im FunctionManager.tick. Eigene Namen (env_*), um Scene.fade_in
        # (kurvenbasierte Wert-Interpolation, andere Semantik) NICHT zu kollidieren.
        self.env_fade_in: float = 0.0
        self.env_fade_out: float = 0.0
        self._env_elapsed: float = 0.0     # laeuft seit (Re-)Start -> Fade-In
        self._releasing: bool = False      # True = Fade-Out laeuft (nach release())
        self._release_elapsed: float = 0.0
        # FW-4: Form der Hüllkurve (kurzer Name aus fade_curve.CURVE_NAMES;
        # "linear" = unveränderter, gerader Verlauf).
        self.env_curve: str = "linear"
        # WP-Tempo: Anbindung an einen Tempo-Bus (core/engine/tempo_bus.py +
        # docs/TEMPO_SYNC_PLAN.md). Neue zeitbasierte Effekte folgen standardmaessig
        # "Global"; "" ist die bewusste Abwahl = Free-Run (Subtyp liest KEINEN Bus).
        # Sonst leitet ein zeitbasierter Subtyp seine Phase aus der Bus-Position ab:
        #   effect_pos = (bus.position - _beat_anchor) * tempo_multiplier + phase_offset
        # tempo_multiplier = harmonisches Verhältnis (×¼…×4), phase_offset in Beats,
        # sync_group bündelt Effekte, die per "Sync" gemeinsam re-ankern.
        self.tempo_bus_id: str = "Global" if self.tempo_sync_default else ""
        # ENG-21: ueber Properties gefuehrt (siehe unten) — die Zuweisung SELBST
        # zieht den Anker nach. Hier deshalb ueber das private Feld, denn beim
        # Aufbau gibt es noch keine Phase, die man erhalten koennte.
        self._tempo_multiplier: float = 1.0
        self.phase_offset: float = 0.0
        self.sync_group: str = ""
        self._beat_anchor: float = 0.0     # Bus-Position beim letzten Sync/Start (privat, nicht serialisiert)
        # ENG-23: Per-Effekt-„Einfrieren". Haelt DIESEN Effekt an, waehrend alle
        # anderen weiterlaufen (der globale Freeze aus F3 haelt dagegen ALLE an,
        # ueber den Tempo-Bus). Laufzeit-Zustand wie ``_running`` — nicht
        # serialisiert: eine geladene Show soll nicht heimlich eingefroren sein.
        self._frozen: bool = False
        # Die beim Einfrieren festgehaltene Position (in Beats), damit das
        # AUFTAUEN nicht springt. None = frei laufend oder nicht bus-gebunden.
        self._frozen_local: float | None = None
        # WP-Tempo „taktgleich": startet dieser Effekt auf dem gemeinsamen Beat-Raster
        # seines Bus (True, Default) oder bewusst frei bei seinem eigenen Null (False)?
        # Wirkt nur, wenn der Effekt auf einem Bus liegt (tempo_bus_id != ""); Free-Run
        # bleibt unberuehrt. Alt-Shows ohne Key laden als True -> ein bus-gebundener
        # Effekt wird damit taktgleich (siehe FunctionManager.from_dict).
        self.align_on_start: bool = True

    # ── ENG-21: Tempo aendern, ohne zu springen ───────────────────────────────
    #
    # Alle vier zeitbasierten Subtypen leiten ihre Position aus DERSELBEN Formel ab:
    #
    #     local = (bus.position - _beat_anchor) * tempo_multiplier + phase_offset
    #
    # `local` steht fuer die Phase (EFX/Matrix) bzw. fuer den Ziel-Step
    # (Chaser/Sequence). Aendert man `tempo_multiplier` im Betrieb, skaliert der neue
    # Faktor die GANZE seit dem Anker verstrichene Beat-Distanz **rueckwirkend** —
    # der Effekt springt in EINEM Frame an eine Stelle, an der er nie war.
    #
    # Gemessen (Bus 120 BPM, 3,1 s nach dem Anker, x1,0 -> x1,25):
    #     EFX/Matrix       local 6,200 -> 7,750   (+1,550 Beats, harter Sprung)
    #     Chaser/Sequence  Ziel-Step 6 -> 7       (Step-Burst)
    #
    # ★★★ Die Regel ist NICHT „auf die Bus-Position re-ankern". Das tat der
    # F5-Fix (`_reanchor_bus_target`: `_beat_anchor = bus.position()`), und es
    # traegt nur bei Chaser/Sequence — dort ist `_step_idx` EIGENER Zustand, der
    # den Sprung ueberlebt. Bei EFX/Matrix wird die Phase AUS dem Anker
    # ABGELEITET; verbatim uebernommen erzeugt derselbe Code einen anderen harten
    # Sprung (gemessen: Phase 0,200 -> 0,000).
    #
    # Richtig ist, `local` zu ERHALTEN und nur die Rate zu wechseln:
    #
    #     anker_neu = pos - (local_alt - phase_offset) / mult_neu
    #
    # Damit ist der Wechsel-Frame stetig (Delta 0,000) und ab dem naechsten Frame
    # laeuft es mit der neuen Rate.
    #
    # ⚠️ **Warum Properties und nicht `set_param`:** die Tempo-Spinboxen der vier
    # Editoren schreiben das Attribut DIREKT aufs Objekt und gehen an `set_param`
    # vorbei (`efx_view.py`, `rgb_matrix_view.py`, `chaser_editor.py`,
    # `sequence_editor.py`). Ein Fix in `set_param` wirkt fuer VC-Speed-Dial, MIDI
    # und `effect_live` — aber nicht dort, wo man am Tempo dreht. Die Zuweisung
    # ist die einzige Stelle, die ALLE Schreiber sieht, heutige wie kuenftige.

    @property
    def tempo_multiplier(self) -> float:
        return self._tempo_multiplier

    @tempo_multiplier.setter
    def tempo_multiplier(self, wert) -> None:
        try:
            neu = float(wert)
        except (TypeError, ValueError):
            return
        self._tempo_umankern(mult_neu=neu,
                             mult_alt=getattr(self, "_tempo_multiplier", 1.0))
        self._tempo_multiplier = neu

    # ⚠️ ``phase_offset`` bleibt bewusst ein GEWOEHNLICHES Attribut. Es ist der
    # Regler, der die Phase VERSCHIEBEN soll — ihn „stetig" zu machen hiesse, ihn
    # wirkungslos zu machen. Stetig gehoert die RATE, nicht der Versatz.

    def _tempo_umankern(self, *, mult_neu: float, mult_alt: float) -> None:
        """Zieht ``_beat_anchor`` so nach, dass ``local`` beim Wechsel STETIG bleibt.

        No-op ausserhalb des Betriebs: ein Effekt, der nicht laeuft, hat keine
        Phase zu verlieren, und ``start()``/``sync_phase()`` ankern ihn ohnehin neu.
        Das haelt vor allem den Show-Ladepfad unveraendert — ``from_dict`` setzt
        beide Werte, und ein Anker, der beim LADEN aus einem laufenden Bus
        abgeleitet wird, waere frei erfunden.

        ★ Die Ausnahmebehandlung liegt bewusst NUR um den fremden Zugriff (Import
        und Bus-Aufloesung). Ein erster Entwurf hatte auch die Rechnung in einem
        breiten ``except Exception`` — die Mutationsprobe hat das aufgedeckt: die
        Wache gegen ``mult_neu <= 0`` liess sich entfernen, ohne dass ein Test
        rot wurde, weil die Division durch Null anschliessend still geschluckt
        wurde. Eine Wache, deren einzige Wirkung das Vermeiden einer ohnehin
        verschluckten Ausnahme ist, ist keine Wache, sondern Zierde.
        """
        if not getattr(self, "_running", False):
            return
        if mult_neu <= 0:
            # F7-Parity: die Leser behandeln ``<= 0`` als 1.0 und frieren nicht
            # ein. Hier waere es eine Division durch Null — also gar nicht
            # ankern und die Entscheidung dem Leser lassen.
            return
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            # ``bus_for_effect`` ist DIE Antwort auf „liegt der Effekt auf einem
            # Bus?" — leere id heisst dort Free-Run und liefert None. Eine eigene
            # Abfrage davor waere ein zweites Tor fuer dieselbe Frage.
            bus = get_tempo_bus_manager().bus_for_effect(
                getattr(self, "tempo_bus_id", "") or "")
            pos = float(bus.position()) if bus is not None else None
        except Exception:
            return
        if pos is None:
            return
        anker_alt = float(getattr(self, "_beat_anchor", 0.0) or 0.0)
        # ``0`` lesen BEIDE Leser als 1.0 (EFX/Matrix ueber ``or 1.0``,
        # Chaser/Sequence ueber ``if mult <= 0: mult = 1.0``) — die Vorgeschichte
        # ist damit eindeutig, und das Reparieren eines aus einer Alt-Show
        # geladenen Nullwerts darf nicht springen.
        m_alt = float(mult_alt or 1.0)
        if m_alt < 0:
            # ⚠️ Bei einem NEGATIVEN Altwert lesen die beiden Familien
            # unterschiedlich: ``or 1.0`` laesst -2 stehen, ``<= 0`` macht 1.0
            # daraus. Ohne eindeutige Vorgeschichte gibt es keine Phase, die man
            # erhalten koennte — dann lieber gar nicht ankern als eine erfinden.
            # (Die Uneinigkeit der Leser selbst ist ein eigener Befund, siehe
            # Backlog-Eintrag zu ENG-21.)
            return
        # ``local = (pos - anker) * mult + phase_offset``. Der Versatz steht auf
        # BEIDEN Seiten der Gleichung — er aendert sich hier ja nicht — und
        # kuerzt sich deshalb heraus. Er taucht in dieser Zeile bewusst NICHT
        # auf; ihn mitzurechnen sah symmetrisch aus und war eine Zeile ohne
        # Wirkung (von der Mutationsprobe gefunden). Genau deshalb ist
        # ``phase_offset`` auch kein Fall fuer diese Regel: waere er es, wuerde
        # er sich nicht kuerzen — und der Regler waere wirkungslos.
        self._beat_anchor = pos - (pos - anker_alt) * m_alt / float(mult_neu)

    # ── ENG-23: Per-Effekt-Einfrieren ─────────────────────────────────────────
    #
    # Der GLOBALE Freeze (F3) haelt alles an, indem er die Tempo-Buses auf 0 BPM
    # setzt. Der Per-Effekt-Freeze haelt NUR diesen Effekt an, waehrend sein Bus
    # weiterlaeuft — und genau daraus folgt die Schwierigkeit: waehrend des
    # Einfrierens wandert die Bus-Position weiter, und beim Auftauen wuerde die
    # aus ihr abgeleitete Position um die verstrichenen Beats SPRINGEN.
    #
    # Gemessen vor dem Fix (bus-synchrone Matrix, 120 BPM, 2 s eingefroren):
    #     _step vor dem Freeze  2,0000
    #     _step waehrend Freeze 2,0000   (gehalten)
    #     _step nach Unfreeze   6,0000   (+4,0000 — genau die vergangenen Beats)
    #
    # Deshalb merkt sich das Einfrieren die Position und das Auftauen zieht den
    # Anker nach. Es ist dieselbe Rechnung wie bei ENG-21, nur mit einem
    # festgehaltenen statt einem umgerechneten ``local`` — und sie steht hier
    # EINMAL fuer alle vier Typen, weil alle vier dieselbe Formel benutzen.

    #: Die drei Aktionen, die jeder zeitbasierte Effekt beherrscht.
    #: ★ ``freeze``/``unfreeze`` sind ABSOLUT und gehoeren deshalb in jede Liste:
    #: ein reiner Toggle ist ein Zustand, den nur er selbst wieder aufhebt — wer
    #: den Knopf nicht mehr findet (anderes VC-Blatt, MIDI-Pad umbelegt), sitzt
    #: fest. Absolute Aktionen sind auch fuer Szenenabrufe die richtige Form.
    FREEZE_ACTIONS: list[tuple[str, str]] = [
        ("freeze",        "Einfrieren"),
        ("unfreeze",      "Weiterlaufen"),
        ("toggle_freeze", "Einfrieren an/aus"),
    ]

    def _local_beats(self) -> "float | None":
        """Die Groesse, aus der ALLE vier Typen ihre Position ableiten.

        ``(bus.position - _beat_anchor) * tempo_multiplier + phase_offset`` —
        Phase bei EFX/Matrix, Ziel-Step bei Chaser/Sequence. ``None``, wenn der
        Effekt nicht bus-gebunden ist (Free-Run rechnet aus ``dt`` und braucht
        beim Auftauen nichts nachgezogen).
        """
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            bus = get_tempo_bus_manager().bus_for_effect(
                getattr(self, "tempo_bus_id", "") or "")
            if bus is None:
                return None
            pos = float(bus.position())
        except Exception:
            return None
        mult = float(getattr(self, "tempo_multiplier", 1.0) or 1.0)
        if mult <= 0:
            mult = 1.0
        anker = float(getattr(self, "_beat_anchor", 0.0) or 0.0)
        return (pos - anker) * mult + float(getattr(self, "phase_offset", 0.0) or 0.0)

    def _einfrieren(self) -> None:
        if self._frozen:
            return                      # schon eingefroren: Position NICHT neu merken
        self._frozen_local = self._local_beats()
        self._frozen = True

    def _auftauen(self) -> None:
        """Hebt den Freeze auf und setzt den Anker so, dass es NICHT springt."""
        gehalten, self._frozen_local = self._frozen_local, None
        war = self._frozen
        self._frozen = False
        if not war or gehalten is None:
            return
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            bus = get_tempo_bus_manager().bus_for_effect(
                getattr(self, "tempo_bus_id", "") or "")
            if bus is None:
                return
            pos = float(bus.position())
        except Exception:
            return
        mult = float(getattr(self, "tempo_multiplier", 1.0) or 1.0)
        if mult <= 0:
            return
        off = float(getattr(self, "phase_offset", 0.0) or 0.0)
        self._beat_anchor = pos - (gehalten - off) / mult

    def do_action(self, action: str, **kw) -> bool:
        """Die drei Freeze-Aktionen, gemeinsam fuer alle Funktionstypen.

        ⚠️ Bis 2026-09-06 kannte nur ``RgbMatrixInstance`` ueberhaupt ein
        ``_frozen``. Die VC bot „Einfrieren an/aus" aber als allgemeine
        Effekt-Aktion an — auf einem Chaser, einem EFX oder einer Sequenz
        lieferte ``do_action`` deshalb schlicht ``False``, und der Knopf tat
        **nichts**, ohne es zu sagen. Ein Bedienelement, das nur manchmal wirkt,
        ist schlimmer als eines, das fehlt.

        Untertypen rufen das hier ueber ``super().do_action(...)`` als letzten
        Zweig auf — so bleibt die Zustaendigkeit an EINER Stelle.
        """
        a = (action or "").strip()
        if a == "freeze":
            self._einfrieren(); return True
        if a == "unfreeze":
            self._auftauen(); return True
        if a in ("toggle_freeze", "toggleFreeze"):
            self._auftauen() if self._frozen else self._einfrieren()
            return True
        return False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        """Called when function is started."""
        # ENG-23: ★★ Ein Zustand, aus dem nur GENAU EIN Knopf herausfuehrt, ist
        # im Live-Betrieb eine Falle. Bis 2026-09-06 ueberlebte ``_frozen`` das
        # Aus- und Wiedereinschalten des Effekts — gemessen: nach
        # ``stop() + start()`` stand ``_frozen`` weiter auf True, und weil
        # ``_on_start`` gleichzeitig ``_step = 0.0`` setzt, klemmte der Effekt
        # danach auf Frame 0 (Vollrot 255/0/0). Aus- und Wiedereinschalten ist
        # der Griff, zu dem jeder greift, wenn etwas haengt.
        self._auftauen()
        self._running = True
        self._elapsed = 0.0
        self._env_elapsed = 0.0
        self._releasing = False
        self._release_elapsed = 0.0
        self._on_start()

    def stop(self):
        """Called when function is stopped."""
        self._running = False
        self._elapsed = 0.0
        self._releasing = False
        self._release_elapsed = 0.0
        self._on_stop()

    def _on_start(self):
        pass

    def _on_stop(self):
        pass

    @property
    def is_running(self) -> bool:
        return self._running

    # ── ARC-04: Ein-/Ausblend-Huellkurve ───────────────────────────────────────

    def release(self):
        """Fade-Out einleiten — die Funktion bleibt laufend und blendet ueber
        env_fade_out Sekunden aus (vom FunctionManager getickt), statt sofort zu
        stoppen. Ohne env_fade_out wirkungslos (der Caller stoppt dann hart)."""
        if not self._releasing:
            self._releasing = True
            self._release_elapsed = 0.0

    def env_factor(self, dt: float) -> float:
        """Output-Multiplikator 0..1 fuer diesen Frame; treibt die Huellkurven-Uhr
        um dt weiter. MUSS pro Frame genau einmal aufgerufen werden. Fade-In rampt
        nach (Re-)Start ueber env_fade_in hoch; Fade-Out rampt nach release() ueber
        env_fade_out auf 0."""
        if self._releasing:
            if self.env_fade_out <= 0.0:
                return 0.0
            self._release_elapsed += dt
            remaining = max(0.0, 1.0 - self._release_elapsed / self.env_fade_out)
            return eval_named(self.env_curve, remaining)   # FW-4: Form anwenden
        self._env_elapsed += dt
        if self.env_fade_in <= 0.0:
            return 1.0
        prog = max(0.0, min(1.0, self._env_elapsed / self.env_fade_in))
        return eval_named(self.env_curve, prog)            # FW-4: Form anwenden

    def env_release_done(self) -> bool:
        """True, wenn der Fade-Out fertig ist (Funktion darf entfernt werden)."""
        return self._releasing and (self.env_fade_out <= 0.0
                                    or self._release_elapsed >= self.env_fade_out)

    # ── Per-frame tick ────────────────────────────────────────────────────────

    def write(self, universes: dict[int, "Universe"],
              patch_cache: list["PatchedFixture"],
              dt: float,
              function_registry: dict[int, "Function"] | None = None):
        """
        Called every frame while running.
        Subclasses override this to produce DMX output.
        dt: delta time in seconds since last call.
        """
        raise NotImplementedError

    # ── Serialisation ─────────────────────────────────────────────────────────

    def shift_clock(self, seconds: float) -> None:
        """Interne Zeitanker um ``seconds`` nach vorn schieben (Freeze-Auftauen).

        BUG-FBW Slice 3: Der globale Freeze haelt den Output an, indem der
        Renderer den Frame nicht mehr neu berechnet — die Funktionen werden also
        gar nicht getickt. Wer seinen Fortschritt aus ``dt`` zieht, haelt damit
        von selbst. Wer ihn aus ``time.monotonic()`` zieht (Matrix, EFX,
        Cue-Fades), rechnet beim ersten Tick nach dem Auftauen die GANZE
        eingefrorene Dauer auf einmal ab und springt nach vorn.

        Diese Methode verschiebt den Anker um genau diese Dauer, damit der erste
        Tick nach dem Auftauen wieder ein normaler Frame ist. Basis-Fassung: nichts
        zu tun (die allermeisten Funktionen haengen an ``dt``).
        """
        return

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.function_type.value,
            "intensity": self.intensity,
            "speed": self.speed,
            "folder": self.folder,
            "priority": self.priority,
            "env_fade_in": self.env_fade_in,
            "env_fade_out": self.env_fade_out,
            "env_curve": self.env_curve,
            "tempo_bus_id": self.tempo_bus_id,
            "tempo_multiplier": self.tempo_multiplier,
            "phase_offset": self.phase_offset,
            "sync_group": self.sync_group,
            "align_on_start": self.align_on_start,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Function":
        raise NotImplementedError
