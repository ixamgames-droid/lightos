"""VIZ-71: Push-Kanal fuer die Lichtdaten — eine Instanz je Seite.

Bis VIZ-70 holte sich die Seite die DMX-Werte alle 130 ms ueber ``pollControl``
(QWebChannel stellt Python->JS-Signale nach dem Laden nicht zu, Slot-Rueckgaben
schon). Das kostete im Mittel rund 100 ms Verzoegerung, schlimmstenfalls ueber
200 ms, und begrenzte die Szene auf rund acht Updates je Sekunde.

``page().runJavaScript`` kommt dagegen zuverlaessig an (Spike S0 2026-10-04:
187 von 187 Rueckrufen im 33-ms-Takt, p50 2,4 ms — auch offscreen und bei
verstecktem Widget). Der Service ruft :meth:`DmxPushChannel.push` deshalb
direkt aus seinem Tick; der Kanal schiebt die Werte an
``window.__lightos.applyDmx``.

Regeln:
  * Hoechstens EIN Batch je Seite unterwegs. Was in der Zwischenzeit kommt,
    wird je Geraet als GANZER Eintrag zusammengefuehrt (A3D-04: nie per
    ``dict.update`` — sonst ueberlebt ein altes ``heads``-Array einen
    Moduswechsel). Ein voller Batch ersetzt den Puffer.
  * Jeder Eintrag traegt die Tick-Nummer des Service; JS verwirft Aelteres.
  * Rueckgabe ``-1`` (Seite noch nicht bereit) -> Puffer verwerfen, der Service
    liefert beim naechsten Tick den vollen Bestand (``on_need_full``). Das
    VIZ-70-Gate laesst ``needs_full`` durch — ein Wiederholversuch laeuft NUR
    so, sonst ueberspraenge das Gate ihn.
  * Kein Rueckruf nach ``timeout_s`` (Reload, Renderer-Absturz) -> wie ``-1``.
    Ein spaeter Rueckruf eines verworfenen Batches wird ignoriert.
  * Bis zur ersten Bestaetigung laeuft der Poll weiter mit (``poll``-Bruecke,
    ``_poll_merge_entries``); danach wird sein Puffer geleert. Die
    Sequenznummern machen das Nebeneinander sicher.
  * Takt je Qualitaetsstufe: ``min_interval_s`` (Niedrig 15 Hz, Hoch 30 Hz,
    Maximal 44 Hz). Ein Batch, der zu frueh kaeme, wartet im Puffer.

Threads: alles hier laeuft im UI-Thread (Service-Tick, Rueckrufe). Die Werte
kommen aus dem Display-Frame (``VisualizerService._collect_attrs``) — Blackout,
Grand-Master und NOT-AUS sind darin schon enthalten.
"""
from __future__ import annotations

import json
import time
import weakref
from typing import Callable, Optional

PUSH_TIMEOUT_S = 0.5
# Ein Tick, der ein paar Millisekunden vor dem Soll-Abstand kommt, darf schon
# senden — sonst fiele bei Timer-Jitter jeder zweite Tick aus.
_TAKT_TOLERANZ_S = 0.008


# VIZ-86: Zeitgeber mit Qt.PreciseTimer. Der Standard-QTimer ist ein
# CoarseTimer — unter Windows rastet er auf das 15,6-ms-Systemraster ein, und
# aus 33 ms werden 46,9 ms (gemessen: 21 statt 30 Pushes je Sekunde). Die
# Funktor-Form von ``QTimer.singleShot`` legt in PySide6 keinen Typ fest, und
# die Ueberladung mit ``timerType`` nimmt dort nur Slot-Namen, keine Funktion —
# daher ein eigener Einmal-Zeitgeber. Die Timer leben bis zum Ausloesen in
# einer Menge (sonst raeumte die GC sie vorher ab) und werden danach per
# ``deleteLater`` freigegeben.
_PRAEZISE_TIMER: set = set()


def precise_single_shot(ms: int, fn: Callable[[], None]) -> None:
    """Wie ``QTimer.singleShot(ms, fn)``, aber mit ``Qt.PreciseTimer``."""
    from PySide6.QtCore import QTimer, Qt
    t = QTimer()
    t.setTimerType(Qt.TimerType.PreciseTimer)
    t.setSingleShot(True)

    def _los():
        _PRAEZISE_TIMER.discard(t)
        try:
            t.deleteLater()
        except RuntimeError:
            pass
        fn()
    t.timeout.connect(_los)
    _PRAEZISE_TIMER.add(t)
    t.start(max(0, int(ms)))


def push_script(entries, gen=None) -> str:
    """Skript fuer ``runJavaScript``. ``entries``: ``[(seq, payload), ...]``,
    ``gen``: Show-Generation der Werte (``None`` = ohne, Alt-Aufrufer).

    Das JSON steht direkt als JS-Literal im Skript (kein zweites
    ``JSON.parse``), mit ``ensure_ascii`` — Geraete- und Gobo-Namen koennen
    Umlaute tragen. Rueckgabe in JS ist eine ZAHL: Arrays kommen in PySide 6.11
    als ``''`` an (VIZ-65)."""
    payloads = [d for _s, d in entries]
    seqs = [s for s, _d in entries]
    arr = json.dumps(payloads, ensure_ascii=True, separators=(",", ":"))
    if seqs and all(s == seqs[0] for s in seqs):
        seq = json.dumps(seqs[0])
    else:
        seq = json.dumps(seqs, separators=(",", ":"))
    if gen is not None:
        seq = "%s,%d" % (seq, int(gen))
    return ("(function(){var L=window.__lightos;"
            "return(L&&L.applyDmx)?L.applyDmx(%s,%s):-1;})()" % (arr, seq))


class DmxPushChannel:
    """Push der Lichtdaten an EINE Seite (Fenster oder Live-View-Spiegel)."""

    def __init__(self, view, *, on_need_full: Callable[[], None], poll=None,
                 min_interval_s: float = 1.0 / 30,
                 clock: Callable[[], float] = time.monotonic,
                 schedule: Optional[Callable[[int, Callable[[], None]], None]] = None,
                 timeout_s: float = PUSH_TIMEOUT_S):
        # Die View nur schwach halten — wie ``_nachsehen`` im Szenen-Start-
        # Waechter: ein starker Bezug View -> Kanal -> View waere der GC-Zyklus
        # um den Owner, den STAB-10 als native AV-Klasse beim Teardown kennt.
        self._view_ref = weakref.ref(view)
        self._poll_ref = None
        if poll is not None:
            try:
                self._poll_ref = weakref.ref(poll)
            except TypeError:            # Attrappe ohne weakref-Slot
                self._poll_ref = (lambda p=poll: p)
        self._on_need_full = on_need_full
        self.min_interval_s = float(min_interval_s)
        self._clock = clock
        self._schedule = schedule
        self.timeout_s = float(timeout_s)
        self._pending: dict = {}          # fid -> (seq, payload)
        # Show-Generation der Werte in ``_pending`` (Review VIZ-71). Gelesen
        # beim Eingang, nicht beim Senden: ein Nachlauf-Timer koennte sonst
        # Werte der alten Show mit der neuen Generation stempeln.
        self._gen = None
        # (Sendenummer, gesendet_um). Die Nummer steckt im Rueckruf: eine
        # verspaetete Antwort auf einen schon als verloren gewerteten Batch
        # (Timeout) oder auf die alte Seite (Reload) passt nicht mehr.
        self._inflight: Optional[tuple] = None
        self._send_nr = 0
        self._last_send = float("-inf")
        self._timer_armed = False
        self._waechter_aktiv = False
        #: hat die Seite einen Push bestaetigt? Bis dahin laeuft der Poll mit.
        self.confirmed = False
        self.stats = {"batches": 0, "bytes": 0, "nicht_bereit": 0,
                      "timeouts": 0, "resets": 0}
        self._verbinden(view)

    # ── Lebenszyklus ─────────────────────────────────────────────────────────
    def _verbinden(self, view) -> None:
        ref = weakref.ref(self)

        def _reset(*_a):
            kanal = ref()
            if kanal is not None:
                kanal.reset()
        for quelle, signal in ((view, "loadStarted"),
                               (getattr(view, "page", lambda: None)(),
                                "renderProcessTerminated")):
            sig = getattr(quelle, signal, None) if quelle is not None else None
            if sig is None:
                continue
            try:
                sig.connect(_reset)
            except Exception:                            # noqa: BLE001
                pass

    def reset(self) -> None:
        """Seite laedt neu / Renderer weg: alles Schwebende verwerfen, ein
        spaeter Rueckruf der alten Seite zaehlt nicht mehr, der Service liefert
        den vollen Bestand."""
        self._inflight = None
        self._pending = {}
        self.confirmed = False
        self.stats["resets"] += 1
        self._need_full()

    def _need_full(self) -> None:
        try:
            self._on_need_full()
        except Exception as e:                           # noqa: BLE001
            print(f"[DmxPush] ERROR: Voll-Resync anfordern: {e}")

    # ── Eingang (Service-Tick) ───────────────────────────────────────────────
    def _show_gen(self):
        poll = self._poll_ref() if self._poll_ref is not None else None
        gen = getattr(poll, "_show_gen", None) if poll is not None else None
        return gen if isinstance(gen, int) else None

    def push(self, payloads: list, full: bool, seq: int) -> None:
        gen = self._show_gen()
        if full or gen != self._gen:
            # Neue Show: was noch wartet, gehoert zur alten.
            self._pending = {}
            self._gen = gen
        for d in payloads:
            fid = d.get("fid") if isinstance(d, dict) else None
            if fid is None:
                continue
            # pop + setzen: der Eintrag wird GANZ ersetzt (A3D-04).
            self._pending.pop(fid, None)
            self._pending[fid] = (seq, d)
        if not self.confirmed:
            poll = self._poll_ref() if self._poll_ref is not None else None
            if poll is not None:
                try:
                    poll._poll_merge_entries((seq, d) for d in payloads)
                except Exception as e:                   # noqa: BLE001
                    print(f"[DmxPush] ERROR: Poll-Rueckfall: {e}")
        self._try_flush()

    # ── Senden ───────────────────────────────────────────────────────────────
    def _try_flush(self) -> None:
        jetzt = self._clock()
        if self._inflight is not None:
            if jetzt - self._inflight[1] < self.timeout_s:
                return
            # Der Rueckruf ist verloren (Reload, Renderer weg, Seite haengt).
            self.stats["timeouts"] += 1
            self._inflight = None
            self._pending = {}
            self.confirmed = False
            self._need_full()
            return
        if not self._pending:
            return
        warten = self.min_interval_s - (jetzt - self._last_send)
        if warten > _TAKT_TOLERANZ_S:
            self._nachher(warten)
            return
        self._senden(jetzt)

    def _nachher(self, warten_s: float) -> None:
        if self._timer_armed:
            return
        self._timer_armed = True
        ref = weakref.ref(self)

        def _los():
            kanal = ref()
            if kanal is not None:
                kanal._timer_armed = False
                kanal._try_flush()
        schedule = self._schedule or precise_single_shot   # VIZ-86
        schedule(max(1, int(warten_s * 1000)), _los)

    def _senden(self, jetzt: float) -> None:
        view = self._view_ref()
        if view is None:
            self._pending = {}
            return
        eintraege = list(self._pending.values())
        self._pending = {}
        skript = push_script(eintraege, self._gen)
        self._send_nr += 1
        nr = self._send_nr
        self._inflight = (nr, jetzt)
        self._last_send = jetzt
        self.stats["batches"] += 1
        self.stats["bytes"] += len(skript)
        ref = weakref.ref(self)

        def _antwort(r, nr=nr):
            kanal = ref()
            if kanal is not None:
                kanal._on_result(nr, r)
        try:
            view.page().runJavaScript(skript, _antwort)
        except Exception as e:                           # noqa: BLE001
            # Kein Page-Objekt mehr (Teardown mitten im Tick).
            self._inflight = None
            print(f"[DmxPush] runJavaScript fehlgeschlagen: {e}")
            self._need_full()
            return
        # Waechter: bleibt der Rueckruf aus und steht die Szene danach still,
        # kaeme kein Tick mehr, der den Verlust bemerkt — das Bild bliebe auf
        # dem Stand VOR dem verlorenen Batch stehen.
        self._waechter(self.timeout_s)

    def _waechter(self, warten_s: float) -> None:
        """Hoechstens EIN Waechter-Zeitgeber zur Zeit (bei 44 Hz waeren es
        sonst gut 20 gleichzeitig). Beim Ausloesen: ist der Batch, der jetzt
        unterwegs ist, ueberfaellig, behandelt ``_try_flush`` den Verlust; ist
        er juenger, wird fuer seine Restzeit neu gestellt."""
        if self._waechter_aktiv:
            return
        self._waechter_aktiv = True
        ref = weakref.ref(self)

        def _pruefen():
            kanal = ref()
            if kanal is None:
                return
            kanal._waechter_aktiv = False
            if kanal._inflight is None:
                return
            rest = kanal.timeout_s - (kanal._clock() - kanal._inflight[1])
            if rest > 0:
                kanal._waechter(rest)
            else:
                kanal._try_flush()
        schedule = self._schedule or precise_single_shot   # VIZ-86
        schedule(int(warten_s * 1000) + 20, _pruefen)

    def _on_result(self, nr: int, r) -> None:
        if self._inflight is None or self._inflight[0] != nr:
            return                       # Antwort auf einen verworfenen Batch
        self._inflight = None
        try:
            n = int(r)
        except (TypeError, ValueError):
            n = -1                       # Wurf in der Seite / unbekannte Antwort
        if n < 0:
            # Seite (noch) nicht bereit: was wir hatten, ist dort nicht
            # angekommen. Beim naechsten Tick den vollen Bestand.
            self.stats["nicht_bereit"] += 1
            self._pending = {}
            self.confirmed = False
            self._need_full()
            return
        if not self.confirmed:
            self.confirmed = True
            poll = self._poll_ref() if self._poll_ref is not None else None
            if poll is not None:
                try:
                    poll._poll_clear_dmx()
                except Exception:                        # noqa: BLE001
                    pass
        self._try_flush()
