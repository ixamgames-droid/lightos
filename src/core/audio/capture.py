"""Audio Loopback Capture - greift PC-Wiedergabe ab ohne zu blockieren.

BPM-10 (S5): Der Capture haengt beim Start seinen eingebauten ``LevelMeter``
als Abonnent an; ``snapshot()`` liefert dessen unveraenderlichen
``CaptureSnapshot`` plus ``running``/``device``/``source_mode``. Im Betrieb
gibt es genau zwei Abonnenten: ``det.process_chunk`` (ueber den BPM-Manager)
und ``LevelMeter.on_chunk``.

Geraete: ``list_input_devices()``/``default_input()`` liefern nur echte
Eingaenge (keine Monitore — ein Monitor als Eingang endete frueher im
IndexError von soundcard). PC-Audio wird je Ausgabegeraet (Sink) gewaehlt:
``list_loopback_sinks()`` -> ``[(id, name)]`` ueber soundcards ``.id``;
``set_source_mode("loopback", sink_id)`` loest den Monitor exakt ueber die id
auf (PulseAudio ``<sink>.monitor``, WASAPI gleiche id). Fehlt ``.id`` oder
passt nichts, gilt das bisherige Verhalten (Namenssuche von soundcard).
"""
from __future__ import annotations
import threading
import numpy as np
import time
from dataclasses import replace

from src.core.audio.level_meter import CaptureSnapshot, LevelMeter

try:
    import soundcard as sc
    HAS_SOUNDCARD = True
except Exception as exc:
    # soundcard initialisiert PulseAudio bereits beim Import. Ist der Pulse-
    # Server beim Start noch nicht bereit (oder in einer Headless-Sitzung nicht
    # erreichbar), wirft das Paket unter Linux u. a. AssertionError statt
    # ImportError. Audio-Capture ist optional und darf deshalb weder LightOS
    # noch die Testsuite schon beim Modulimport beenden.
    sc = None
    HAS_SOUNDCARD = False
    print(f"[AudioCapture] soundcard nicht verfügbar: {exc}")

SAMPLE_RATE = 44100
CHUNK_SIZE = 1024
CHANNELS = 1


class AudioCapture:
    """Captures audio from a Windows speaker via WASAPI loopback in a thread.

    Doesn't interfere with normal playback. Provides FFT-ready chunks to subscribers.
    """
    def __init__(self):
        self._device_name: str | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        # Zaehlt bei jedem stop() hoch. Jeder Capture-Thread merkt sich seine
        # Epoch; eine veraltete Loop beendet sich beim naechsten Chunk selbst,
        # selbst wenn _running spaeter wieder True wird -> keine Doppel-Capture.
        self._epoch = 0
        self._subscribers: list = []  # callables(numpy.ndarray)
        self._sample_rate = SAMPLE_RATE
        # Pegelmeter: haengt ab start() als Abonnent am Capture (BPM-10).
        self._meter = LevelMeter(SAMPLE_RATE)
        self._lock = threading.Lock()
        # Quelle: "loopback" (PC-Wiedergabe) oder "input" (Mikro/Line-In)
        self.source_mode: str = "loopback"
        self._error: str | None = None

    @staticmethod
    def _is_monitor(dev) -> bool:
        """True fuer Loopback-/Monitor-Quellen (PulseAudio ``device.class ==
        monitor`` bzw. ``<sink>.monitor``; WASAPI ``isloopback``)."""
        try:
            if bool(getattr(dev, "isloopback", False)):
                return True
        except Exception:
            pass
        try:
            return str(getattr(dev, "id", "") or "").endswith(".monitor")
        except Exception:
            return False

    @staticmethod
    def _dev_id(dev) -> str | None:
        """soundcard-``.id`` als Text, oder None wenn das Backend keine hat."""
        try:
            v = getattr(dev, "id", None)
        except Exception:
            return None
        return None if v is None or v == "" else str(v)

    @staticmethod
    def list_loopback_sinks() -> list[tuple[str, str]]:
        """PC-Audio-Quellen je Ausgabegeraet: ``[(sink_id, name)]``.

        ``sink_id`` ist soundcards ``.id`` (PulseAudio-Sinkname, WASAPI-id);
        fehlt sie, steht der Name an ihrer Stelle (bisheriges Verhalten)."""
        if not HAS_SOUNDCARD:
            return []
        try:
            speakers = list(sc.all_speakers())
        except Exception:
            return []
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for s in speakers:
            try:
                name = str(s.name)
            except Exception:
                continue
            sid = AudioCapture._dev_id(s) or name
            if sid in seen:
                continue
            seen.add(sid)
            out.append((sid, name))
        return out

    @staticmethod
    def default_loopback_sink() -> str | None:
        """id des Standard-Ausgabegeraets (Name, wenn das Backend keine id kennt)."""
        if not HAS_SOUNDCARD:
            return None
        try:
            spk = sc.default_speaker()
        except Exception:
            return None
        if spk is None:
            return None
        try:
            return AudioCapture._dev_id(spk) or spk.name
        except Exception:
            return None

    @staticmethod
    def list_speakers() -> list[str]:
        if not HAS_SOUNDCARD:
            return []
        try:
            return [s.name for s in sc.all_speakers()]
        except Exception:
            return []

    @staticmethod
    def default_speaker() -> str | None:
        if not HAS_SOUNDCARD:
            return None
        try:
            return sc.default_speaker().name
        except Exception:
            return None

    def last_error(self) -> str | None:
        """Letzter Fehler beim Starten/Aufnehmen, oder None."""
        with self._lock:
            return self._error

    def _set_error(self, text: str | None):
        with self._lock:
            self._error = text

    def clear_error(self):
        """Vergisst den letzten Capture-Fehler, z. B. nach einem manuellen Stop."""
        self._set_error(None)

    @staticmethod
    def list_input_devices() -> list[str]:
        """Echte Eingaenge (Mikro / Line-In), ohne Loopback-/Monitor-Geraete."""
        if not HAS_SOUNDCARD:
            return []
        try:
            return [m.name for m in sc.all_microphones(include_loopback=False)
                    if not AudioCapture._is_monitor(m)]
        except Exception:
            return []

    @staticmethod
    def default_input() -> str | None:
        """Standard-Eingang ohne Monitore. Ist die Standardquelle des Systems ein
        Monitor (PulseAudio: kein Mikrofon eingestellt), gilt der erste echte
        Eingang — sonst endete ``get_microphone(include_loopback=False)`` im
        IndexError."""
        if not HAS_SOUNDCARD:
            return None
        try:
            mic = sc.default_microphone()
            if mic is not None and not AudioCapture._is_monitor(mic):
                return mic.name
        except Exception:
            pass
        inputs = AudioCapture.list_input_devices()
        return inputs[0] if inputs else None

    def set_device(self, name: str):
        """Wechselt das Geraet. Capture muss gestoppt werden falls aktiv."""
        was_running = self._running
        if was_running:
            self.stop()
        self._device_name = name
        if was_running:
            self.start()

    def set_source_mode(self, mode: str, device_name: str | None = None):
        """Wechselt die Quelle ("loopback" oder "input"). Optional auch das Geraet:
        bei ``input`` der Eingangsname, bei ``loopback`` die ``sink_id`` aus
        ``list_loopback_sinks()`` (None = Standard-Ausgabegeraet).

        Bei laufendem Capture wird sauber neu gestartet (analog set_device).
        """
        if mode not in {"loopback", "input"}:
            return
        self.source_mode = mode
        # Explizites Geraet gewinnt; sonst None setzen, damit start() den
        # passenden Default der NEUEN Quelle neu aufloest (sonst bliebe beim
        # Wechsel input->loopback der alte Mikro-Geraetename haengen).
        self._device_name = device_name
        if self._running:
            self.stop()
            self.start()

    def subscribe(self, cb):
        """Callback bekommt numpy.ndarray (mono, float32 -1..+1) pro Chunk."""
        if cb not in self._subscribers:
            self._subscribers.append(cb)

    def unsubscribe(self, cb):
        if cb in self._subscribers:
            self._subscribers.remove(cb)

    def is_subscribed(self, cb) -> bool:
        """True, wenn ``cb`` bereits Chunks bekommt — Abgleich gegen Doppel-Fuetterung
        (der Detektor zaehlt Samples; zwei Zubringer liessen seine Uhr doppelt laufen)."""
        return cb in self._subscribers

    def is_running(self) -> bool:
        return self._running

    def volume_db(self) -> float:
        """Aktueller Pegel in dB (-60..0) — kompatibel, jetzt RMS ueber 300 ms
        aus dem LevelMeter-Snapshot."""
        v = self._meter.snapshot().rms_dbfs_300ms
        return max(-60.0, min(0.0, float(v)))

    def snapshot(self) -> CaptureSnapshot:
        """Unveraenderlicher Pegel-/Capture-Zustand, ohne Lock lesbar (BPM-10)."""
        return replace(self._meter.snapshot(), running=bool(self._running),
                       device=self._device_name, source_mode=self.source_mode)

    def start(self):
        if not HAS_SOUNDCARD:
            self._set_error("soundcard nicht verfuegbar")
            print("[AudioCapture] soundcard nicht verfügbar")
            return False
        if self._running:
            return True
        # Ein vorheriger stop() konnte den alten Thread evtl. nicht sauber
        # joinen (Geraet haengt in rec.record()). Laeuft er noch, darf hier
        # KEIN zweiter Capture-Thread aufmachen -> sonst Doppel-Capture. Ihm
        # eine letzte kurze Chance geben zu sterben, sonst koaleszieren.
        old = self._thread
        if old is not None and old.is_alive():
            old.join(timeout=0.5)
            if old.is_alive():
                self._set_error("Vorheriger Audio-Thread haengt noch")
                return False
            self._thread = None
        self._set_error(None)
        if self._device_name is None:
            # Default je nach Quelle waehlen
            if self.source_mode == "input":
                self._device_name = self.default_input()
            else:
                self._device_name = self.default_loopback_sink()
        if self._device_name is None:
            self._set_error("Kein Audio-Geraet gefunden")
            return False
        self._meter.reset()
        self.subscribe(self._meter.on_chunk)
        self._running = True
        my_epoch = self._epoch
        self._thread = threading.Thread(target=self._run, args=(my_epoch,),
                                        daemon=True, name="AudioCapture")
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        self.unsubscribe(self._meter.on_chunk)
        # Epoch hochzaehlen: markiert die aktuelle Loop dauerhaft als veraltet,
        # falls sie den Join-Timeout ueberlebt und _running spaeter wieder True
        # wird -> sie sieht den Mismatch und beendet sich beim naechsten Chunk.
        self._epoch += 1
        if self._thread:
            self._thread.join(timeout=2.0)
            if not self._thread.is_alive():
                self._thread = None
            # Sonst haengt der Thread (Geraet weg): Referenz behalten, damit ein
            # folgender start() ihn erkennt statt einen zweiten zu starten.

    @staticmethod
    def _loopback_microphone(device):
        """Loopback-Aufnahmequelle zu einem Ausgabegeraet.

        1. exakt ueber ``.id``: PulseAudio-Monitor ``<sink_id>.monitor`` bzw.
           WASAPI-Loopback mit derselben id wie der Lautsprecher;
        2. ``device`` ist ein Sink-NAME: dessen id wie in 1., sonst der Monitor
           „Monitor of <Name>";
        3. Fallback = bisheriges Verhalten (``get_microphone`` mit Namenssuche),
           z. B. wenn das Backend keine ``.id`` kennt.
        """
        dev = str(device)
        try:
            mics = list(sc.all_microphones(include_loopback=True))
        except Exception:
            mics = []
        monitors = [m for m in mics if AudioCapture._is_monitor(m)]

        def _by_id(sid: str):
            for m in monitors:
                mid = AudioCapture._dev_id(m)
                if mid is not None and mid in (sid, f"{sid}.monitor"):
                    return m
            return None

        hit = _by_id(dev)
        if hit is not None:
            return hit
        for sid, name in AudioCapture.list_loopback_sinks():
            if name == dev:
                hit = _by_id(sid)
                if hit is None:
                    for m in monitors:
                        try:
                            if m.name == f"Monitor of {name}":
                                hit = m
                                break
                        except Exception:
                            continue
                if hit is not None:
                    return hit
                break
        try:
            return sc.get_microphone(dev, include_loopback=True)
        except IndexError:
            raise RuntimeError(f"PC-Audio-Ausgang nicht gefunden: {dev}") from None

    def _run(self, epoch: int | None = None):
        try:
            # Quelle bestimmen: Loopback (PC-Wiedergabe) vs. echter Eingang
            if self.source_mode == "input":
                try:
                    mic = sc.get_microphone(self._device_name, include_loopback=False)
                except IndexError:
                    raise RuntimeError(f"Eingang nicht gefunden: {self._device_name}") from None
            else:
                mic = self._loopback_microphone(self._device_name)
            with mic.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS,
                              blocksize=CHUNK_SIZE) as rec:
                # Recorder offen -> letzter Fehler ist obsolet
                with self._lock:
                    self._error = None
                fails = 0
                while self._running and (epoch is None or epoch == self._epoch):
                    try:
                        data = rec.record(numframes=CHUNK_SIZE)
                        if data.ndim > 1:
                            data = data.mean(axis=1)  # zu mono
                        fails = 0
                        # Subscribern verteilen (u. a. LevelMeter.on_chunk)
                        for cb in list(self._subscribers):
                            try:
                                cb(data)
                            except Exception as e:
                                print(f"[AudioCapture] subscriber error: {e}")
                    except Exception as e:
                        # Geraet weg / Treiber-Hickup: nicht ewig stumm weiterdrehen,
                        # sonst zeigt die UI faelschlich „laeuft" (last_error bleibt None).
                        fails += 1
                        print(f"[AudioCapture] record error ({fails}): {e}")
                        if fails >= 20:   # ~2 s durchgehende Fehler -> aufgeben
                            with self._lock:
                                self._error = f"Aufnahme abgebrochen: {e}"
                            self._running = False
                            break
                        time.sleep(0.1)
        except Exception as e:
            print(f"[AudioCapture] init error: {e}")
            with self._lock:
                self._error = str(e)
            self._running = False


_capture: AudioCapture | None = None


def get_audio_capture() -> AudioCapture:
    global _capture
    if _capture is None:
        _capture = AudioCapture()
    return _capture
