"""Quellen-Umschalter der BPM-Erkennung (BPM-09, S4) — EINE Stelle fuer alles,
was ein Eintrag der Quelle-Combo im Tab „Erkennung" schaltet.

Je Eintrag (``kind``, ``device``):

| kind        | Capture                              | OS2L   | Manager                                    |
|-------------|--------------------------------------|--------|--------------------------------------------|
| ``loopback``| ``set_source_mode("loopback", sink)``| stop   | ``use_audio_source(True)`` (startet Capture)|
| ``input``   | ``set_source_mode("input", device)`` | stop   | ``use_audio_source(True)``                 |
| ``os2l``    | stop                                 | start  | ``use_audio_source(False)``                |
| ``song``    | stop                                 | stop   | ``use_audio_source(False)`` + aktueller Player-Track (``request_bpm``, nur in AUTO) |
| ``off``     | stop                                 | stop   | ``use_audio_source(False)``                |

``sink`` (S5) ist die ``sink_id`` eines Ausgabegeraets aus
``AudioCapture.list_loopback_sinks()``; alles andere (z. B. ein Mikrofonname aus
alten Einstellungen) wird zu None = Standard-Ausgabegeraet — ein Eingangsname
darf den Loopback nie aufs Mikrofon lenken.

Bei JEDEM Wechsel: ``det.set_tempo_hint(None)`` (Suche wieder frei) und
``det.reset()`` (alter Tempo-Zustand gehoert zur alten Quelle). Der Manager-
Modus (AUTO/MANUAL) haengt NICHT an der Quelle: ``use_audio_source(True)``
erzwingt AUTO, danach wird der vorherige Modus wiederhergestellt (S2-Lehre:
Capture haengt an der Quelle, der Modus am Manager).

**Idempotent:** derselbe Eintrag zweimal hintereinander schaltet nichts ein
zweites Mal (S2-Befund: Radio-Wechsel feuerte doppelt und startete den Capture
zweimal). ``apply`` liefert False, wenn nichts zu tun war. Ausnahme (BPM-14-
Nacharbeit): ein Nicht-Audio-Eintrag (``os2l``/``song``/``off``) gilt nur als
aktiv, solange der Manager kein Live-Audio hoert (``mgr.audio_active``). Hat
jemand am Controller vorbei Audio eingeschaltet (bis BPM-16 die VC-Aktion
„Musik-BPM"), schaltet derselbe Eintrag erneut — sonst bliebe Audio am Manager und verwuerfe
jede ``request_bpm`` der gewaehlten Quelle. Fuer PC-Audio/Eingang bleibt es bei
der reinen Idempotenz: ein fehlgeschlagener Capture-Start laesst ``audio_active``
auf False, und bei jedem doppelt feuernden Signal neu zu starten waere wieder der
S2-Befund; zurueck geht es dort ueber Auto (``set_auto``) oder ``reconnect``.

Auto | Manuell (``set_auto``): Auto = ``mgr.set_mode("auto")`` und — falls die
Quelle Audio ist und der Manager sie nicht mehr hoert — ``use_audio_source(True)``;
bei Quelle ``song`` wird der Player-Track erneut angeboten. Manuell =
``mgr.set_mode("manual")``; der Capture laeuft weiter (Erkennung im Hintergrund
sichtbar, Rueckweg auf Auto sofort).

×½ / ×2 (``octave``): in AUTO ``det.set_octave_preference(-1/+1)``, in MANUAL
``mgr.set_manual_bpm(bpm/2 bzw. bpm*2)``. S6 (BPM-11): in AUTO wird vorher der
Tempo-Bereich geprueft (``mgr.min_bpm``/``max_bpm``) — liegt das Ziel ausserhalb,
passiert NICHTS und ``octave`` liefert ``(False, Grund)``; der Bereich wird nie
stumm veraendert (ui_diagnose 5.4). Die View zeigt den Grund als Statuszeilen-
Ereignis.

Fehlender Sink (S6): wird PC-Audio mit einer ``sink_id`` gewaehlt, die es gerade
nicht gibt, laeuft der Capture auf dem Standard-Ausgabegeraet; ``missing_sink``
nennt dann die gewuenschte id (Statuszeile), sonst None. ``wanted`` behaelt den
GEWUENSCHTEN Eintrag (mit der fehlenden id), ``current`` den angewandten.
``reconnect()`` wendet ``wanted`` erzwungen neu an: ist das Geraet inzwischen
angesteckt, laeuft der Capture wieder darauf; fehlt es weiter, bleibt
``missing_sink`` gesetzt.

Backends werden nur AUFGERUFEN (bpm_manager.py, capture.py, os2l.py,
beat_detector.py bleiben unangetastet); jeder Schritt ist einzeln abgesichert,
damit ein fehlendes Backend (kein soundcard/numpy) die uebrigen nicht blockiert.

**Wechsel melden (BPM-14):** ``subscribe_change(cb)`` — ``cb(kind, device)``
bekommt nach jedem wirksamen Wechsel (``apply`` liefert True, auch
``reconnect``) den GEWUENSCHTEN Eintrag (``wanted``), ebenso wenn sich nur
``wanted`` aendert (fehlender Sink bei schon laufendem Standard-Ausgabegeraet).
Ein idempotenter Aufruf meldet nichts. Damit spiegelt der Tab „Erkennung"
Wechsel, die nicht aus seiner eigenen Liste kommen (Generator-Knopf „Im Player
laden & als BPM-Quelle nutzen") — per Rueckruf statt Poll. Gerufen wird im
Thread des Schaltenden; Qt-Ansichten reichen ueber ein Signal in ihren Thread
weiter. Ein defekter Abonnent blockiert die uebrigen nicht.

**VC-Taste „Musik-BPM" (BPM-16):** ``toggle_audio()`` — vorher rief die Taste
``use_audio_source`` direkt am Manager, die Liste blieb stehen, OS2L lief weiter
und beim Ausschalten auch der Capture. Jetzt schaltet sie ueber ``apply``: an =
die zuletzt gewaehlte Audio-Quelle (sonst PC-Audio Systemstandard) plus Auto,
aus = die zuletzt gewaehlte Nicht-Audio-Quelle (sonst Aus). Gemerkt werden beide
in ``apply``; vorbelegt einmal aus ``bpm_settings`` (``_seed_memory``).
„BPM = 0/aus" (``BPMManager.turn_off``) bleibt ein Modus-Wechsel am Manager
(Manuell + 0) und laesst die Quelle stehen — zurueck ueber Auto (``set_auto``)
oder die Taste, beides ueber diesen Controller.
"""
from __future__ import annotations

AUDIO_KINDS = ("loopback", "input")


def _known_sink(device: str | None) -> str | None:
    """``device`` nur zurueckgeben, wenn es eine aktuelle ``sink_id`` ist."""
    if not device:
        return None
    try:
        from src.core.audio.capture import AudioCapture
        ids = {str(i) for i, _n in (AudioCapture.list_loopback_sinks() or [])}
    except Exception:
        return None
    return device if device in ids else None
KINDS = ("loopback", "input", "os2l", "song", "off")


def _log(msg: str) -> None:
    print(f"[SourceController] {msg}")


def _is_auto(mgr) -> bool:
    """AUTO-Modus des Managers (BpmMode oder str, fuer Fakes in Tests)."""
    m = getattr(mgr, "mode", None)
    return str(getattr(m, "name", m)).lower() == "auto"


class SourceController:
    """Schaltet Capture / OS2L / Manager je Quelle — genau eine Stelle, idempotent."""

    def __init__(self, mgr=None, cap=None, os2l=None, det=None, player=None):
        self._mgr, self._cap, self._os2l, self._det, self._player = mgr, cap, os2l, det, player
        self._current: tuple[str, str | None] | None = None
        self._wanted: tuple[str, str | None] | None = None
        self.missing_sink: str | None = None
        self._listeners: list = []      # BPM-14: cb(kind, device) nach jedem Wechsel
        # BPM-16: zuletzt gewaehlte Audio- bzw. Nicht-Audio-Quelle (``wanted``-Form),
        # fuer die VC-Taste „Musik-BPM" (``toggle_audio``); einmal aus den
        # Einstellungen vorbelegt (``_seed_memory``).
        self._last_audio: tuple[str, str | None] | None = None
        self._last_other: tuple[str, str | None] | None = None
        self._seeded = False

    # ── Backends lazily (Singletons; Tests reichen Fakes herein) ────────────
    def _manager(self):
        if self._mgr is None:
            from src.core.engine.bpm_manager import get_bpm_manager
            self._mgr = get_bpm_manager()
        return self._mgr

    def _capture(self):
        if self._cap is None:
            try:
                from src.core.audio.capture import get_audio_capture
                self._cap = get_audio_capture()
            except Exception as e:
                _log(f"kein Capture: {e}")
        return self._cap

    def _server(self):
        if self._os2l is None:
            try:
                from src.core.audio.os2l import get_os2l_server
                self._os2l = get_os2l_server()
            except Exception as e:
                _log(f"kein OS2L: {e}")
        return self._os2l

    def _detector(self):
        if self._det is None:
            try:
                from src.core.audio.beat_detector import get_beat_detector
                self._det = get_beat_detector()
            except Exception:
                self._det = None
        return self._det

    def _media(self):
        if self._player is None:
            try:
                from src.core.audio.media_player import get_media_player
                self._player = get_media_player()
            except Exception as e:
                _log(f"kein Player: {e}")
        return self._player

    # ── API ──────────────────────────────────────────────────────────────────
    @property
    def current(self) -> tuple[str, str | None] | None:
        """Zuletzt angewandter Eintrag ``(kind, device)`` oder None."""
        return self._current

    @property
    def wanted(self) -> tuple[str, str | None] | None:
        """Zuletzt GEWUENSCHTER Eintrag ``(kind, device)`` — bei fehlendem Sink mit dessen id."""
        return self._wanted

    def subscribe_change(self, cb) -> None:
        """``cb(kind, device)`` nach jedem wirksamen Wechsel (BPM-14, s. Modulkopf)."""
        if cb not in self._listeners:
            self._listeners.append(cb)

    def unsubscribe_change(self, cb) -> None:
        if cb in self._listeners:
            self._listeners.remove(cb)

    def reconnect(self) -> bool:
        """„erneut verbinden": den gewuenschten Eintrag erzwungen neu anwenden."""
        if self._wanted is None:
            return False
        return self.apply(*self._wanted, force=True)

    @property
    def kind(self) -> str | None:
        return self._current[0] if self._current else None

    def is_audio(self) -> bool:
        return self.kind in AUDIO_KINDS

    def apply(self, kind: str, device: str | None = None, force: bool = False) -> bool:
        """Quelle schalten. Liefert False, wenn der Eintrag schon aktiv war (idempotent)."""
        if kind not in KINDS:
            _log(f"unbekannte Quelle {kind!r} ignoriert")
            return False
        if kind not in AUDIO_KINDS:
            device = None
        wanted = device
        if kind == "loopback":
            device = _known_sink(device)   # nur echte sink_id, sonst Standard-Ausgabegeraet
        key = (kind, device)
        self._remember(kind, wanted)
        old_wanted = self._wanted
        self._wanted = (kind, wanted)
        self.missing_sink = wanted if (kind == "loopback" and wanted and device is None) else None
        if key == self._current and not force and not self._audio_drift(kind):
            if self._wanted != old_wanted:
                self._notify()
            return False
        self._current = key
        mgr = self._manager()
        det = self._detector()
        if det is not None:
            self._safe("tempo_hint", lambda: det.set_tempo_hint(None))
            self._safe("reset", det.reset)
        if kind in AUDIO_KINDS:
            self._os2l_stop()
            cap = self._capture()
            if cap is not None:
                self._safe("set_source_mode", lambda: cap.set_source_mode(kind, device))
            mode_before = mgr.mode
            self._safe("use_audio_source", lambda: mgr.use_audio_source(True))
            self._safe("set_mode", lambda: mgr.set_mode(mode_before))
        else:
            self._safe("use_audio_source", lambda: mgr.use_audio_source(False))
            self._capture_stop()
            if kind == "os2l":
                srv = self._server()
                if srv is not None and not srv.is_running():
                    self._safe("os2l start", srv.start)
            else:
                self._os2l_stop()
            if kind == "song":
                self.apply_player_track()
        self._notify()
        return True

    def set_auto(self, auto: bool) -> None:
        """Zweizustand Auto | Manuell (der Manager-Modus, unabhaengig von der Quelle)."""
        mgr = self._manager()
        if auto:
            self._safe("set_mode auto", lambda: mgr.set_mode("auto"))
            if self.is_audio() and not getattr(mgr, "audio_active", False):
                self._safe("use_audio_source", lambda: mgr.use_audio_source(True))
            elif self.kind == "song":
                self.apply_player_track()
        else:
            self._safe("set_mode manual", lambda: mgr.set_mode("manual"))

    def toggle_audio(self) -> bool:
        """VC-Taste „Musik-BPM" (``ButtonAction.AUDIO_BPM``, BPM-16): Live-Audio an
        bzw. aus — ueber ``apply`` wie eine Auswahl in der Liste, damit Liste,
        Capture und OS2L zusammenbleiben. Liefert, ob geschaltet wurde.

        Die Richtung folgt ``mgr.audio_active`` (dasselbe, was Tastenrahmen und
        APC-LED zeigen). **an** = die zuletzt gewaehlte Audio-Quelle samt Geraet,
        sonst PC-Audio (Systemstandard), und Auto wie bisher — ohne Auto folgte die
        BPM der Musik nicht, und ``use_audio_source(True)`` erzwang es schon immer.
        Ist genau dieser Eintrag schon angewandt, hoert der Manager aber nicht zu
        (nach „BPM = 0/aus" oder einem gescheiterten Capture-Start), wird er
        erzwungen neu angewandt: EIN Schaltvorgang. **aus** = die zuletzt gewaehlte
        Nicht-Audio-Quelle (OS2L, Lied-Analyse, Aus), sonst Aus; der Modus bleibt."""
        self._seed_memory()
        mgr = self._manager()
        if getattr(mgr, "audio_active", False) is True:
            kind, device = self._last_other or ("off", None)
            return self.apply(kind, device)
        kind, device = self._last_audio or ("loopback", None)
        if not _is_auto(mgr):
            self._safe("set_mode auto", lambda: mgr.set_mode("auto"))
        return self.apply(kind, device, force=True)

    def octave_target(self, step: int) -> float:
        """Tempo, auf das ×½ (step < 0) / ×2 (step > 0) fuehren wuerde (0 = unbekannt)."""
        mgr = self._manager()
        bpm = float(getattr(mgr, "bpm", 0.0) or 0.0)
        if bpm <= 0 and _is_auto(mgr):
            det = self._detector()
            try:
                bpm = float(det.snapshot().bpm) if det is not None else 0.0
            except Exception:
                bpm = 0.0
        if bpm <= 0:
            return 0.0
        return bpm / 2.0 if step < 0 else bpm * 2.0

    def octave(self, step: int) -> tuple[bool, str | None]:
        """×½ (step < 0) / ×2 (step > 0): in AUTO Oktav-Vorzug des Detektors, in
        MANUAL das manuelle Tempo halbieren/verdoppeln. Liefert ``(True, None)``
        oder ``(False, Grund)``, wenn das Ziel in AUTO ausserhalb des Tempo-Bereichs
        liegt (dann kein Aufruf)."""
        mgr = self._manager()
        if _is_auto(mgr):
            ziel = self.octave_target(step)
            lo = float(getattr(mgr, "min_bpm", 0.0) or 0.0)
            hi = float(getattr(mgr, "max_bpm", 0.0) or 0.0)
            if ziel > 0 and hi > lo and not (lo <= ziel <= hi):
                knopf = "×2" if step > 0 else "×½"
                return False, (f"{knopf} nicht möglich: {ziel:.0f} BPM außerhalb des "
                               f"Tempo-Bereichs {lo:.0f}–{hi:.0f}")
            det = self._detector()
            if det is not None:
                self._safe("set_octave_preference",
                           lambda: det.set_octave_preference(-1 if step < 0 else 1))
        else:
            bpm = float(mgr.bpm or 0.0)
            if bpm > 0:
                self._safe("set_manual_bpm",
                           lambda: mgr.set_manual_bpm(bpm / 2.0 if step < 0 else bpm * 2.0))
        return True, None

    def apply_player_track(self) -> float:
        """Quelle „Lied-Analyse": den AKTUELLEN Player-Track als Timeline-Quelle
        anbieten (Median der Analyse als Start-BPM, ``request_bpm`` greift nur in
        AUTO). Liefert die angebotene BPM (0 = kein analysierter Track)."""
        mp = self._media()
        if mp is None:
            return 0.0
        try:
            t = mp.current_track
            if t is None or not getattr(t, "bpm_timeline", None):
                return 0.0
            from src.core.audio.offline_timeline import BpmTimeline
            med = float(BpmTimeline.from_dict(t.bpm_timeline or {}).summary().get("median", 0) or 0)
            if med > 0:
                self._manager().request_bpm(med, "timeline")
            return med
        except Exception as e:
            _log(f"Player-Track: {e}")
            return 0.0

    # ── intern ───────────────────────────────────────────────────────────────
    def _remember(self, kind: str, wanted: str | None) -> None:
        """Eintrag als zuletzt gewaehlte Audio- bzw. Nicht-Audio-Quelle merken (BPM-16)."""
        self._seed_memory()
        if kind in AUDIO_KINDS:
            self._last_audio = (kind, wanted)
        else:
            self._last_other = (kind, None)

    def _seed_memory(self) -> None:
        """Einmal je Controller: die gespeicherte Quelle (``bpm_settings``) als zuletzt
        gewaehlte vorbelegen — beim ersten ``apply``/``toggle_audio``, solange die
        Datei noch den Stand vom Start traegt (die Ansicht speichert nach jedem
        Wechsel). Wichtig fuer „Lied-Analyse"/„Aus": dafuer schaltet der Auto-Start
        nichts, der Controller haette sonst keine Vorgeschichte."""
        if self._seeded:
            return
        self._seeded = True
        try:
            from src.core.audio.bpm_settings import load_settings
            s = load_settings()
        except Exception as e:
            _log(f"Einstellungen: {e}")
            return
        kind = s.get("source")
        if kind in AUDIO_KINDS:
            if self._last_audio is None:
                self._last_audio = (kind, s.get("device") or None)
        elif kind in KINDS and self._last_other is None:
            self._last_other = (kind, None)

    def _audio_drift(self, kind: str) -> bool:
        """Nicht-Audio-Eintrag angewandt, aber der Manager hoert noch Live-Audio:
        jemand hat am Controller vorbei geschaltet (bis BPM-16 die VC-Aktion
        „Musik-BPM"; heute nur noch ein direkter ``use_audio_source``-Aufruf). Dann
        ist der Eintrag nicht mehr aktiv, und ``apply`` schaltet erneut (BPM-14-
        Nacharbeit). Nur ``is True`` zaehlt — Fakes ohne ``audio_active`` (oder ein
        Mock) loesen nichts aus."""
        if kind in AUDIO_KINDS:
            return False
        try:
            return getattr(self._manager(), "audio_active", False) is True
        except Exception:
            return False

    def _notify(self) -> None:
        """Abonnenten den gewuenschten Eintrag melden; jeder einzeln abgesichert."""
        kind, device = self._wanted if self._wanted else (None, None)
        for cb in list(self._listeners):
            try:
                cb(kind, device)
            except Exception as e:
                _log(f"Abonnent: {e}")

    def _os2l_stop(self):
        srv = self._server()
        if srv is not None and srv.is_running():
            self._safe("os2l stop", srv.stop)

    def _capture_stop(self):
        cap = self._capture()
        if cap is not None and cap.is_running():
            self._safe("capture stop", cap.stop)

    @staticmethod
    def _safe(what: str, fn) -> None:
        try:
            fn()
        except Exception as e:
            _log(f"{what}: {e}")


_controller: SourceController | None = None


def get_source_controller() -> SourceController:
    """Der eine Umschalter fuer den Tab „Erkennung" (und Auto-Start)."""
    global _controller
    if _controller is None:
        _controller = SourceController()
    return _controller
