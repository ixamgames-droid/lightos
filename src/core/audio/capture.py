"""Audio Loopback Capture - greift PC-Wiedergabe ab ohne zu blockieren."""
from __future__ import annotations
import threading
import numpy as np
import time

try:
    import soundcard as sc
    HAS_SOUNDCARD = True
except ImportError:
    HAS_SOUNDCARD = False

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
        self._subscribers: list = []  # callables(numpy.ndarray)
        self._sample_rate = SAMPLE_RATE
        self._latest_volume: float = 0.0
        self._lock = threading.Lock()
        # Quelle: "loopback" (PC-Wiedergabe) oder "input" (Mikro/Line-In)
        self.source_mode: str = "loopback"
        self._error: str | None = None

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
        """Echte Eingaenge (Mikro / Line-In), ohne Loopback-Geraete."""
        if not HAS_SOUNDCARD:
            return []
        try:
            return [m.name for m in sc.all_microphones(include_loopback=False)]
        except Exception:
            return []

    @staticmethod
    def default_input() -> str | None:
        if not HAS_SOUNDCARD:
            return None
        try:
            return sc.default_microphone().name
        except Exception:
            return None

    def set_device(self, name: str):
        """Wechselt das Geraet. Capture muss gestoppt werden falls aktiv."""
        was_running = self._running
        if was_running:
            self.stop()
        self._device_name = name
        if was_running:
            self.start()

    def set_source_mode(self, mode: str, device_name: str | None = None):
        """Wechselt die Quelle ("loopback" oder "input"). Optional auch das Geraet.

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

    def is_running(self) -> bool:
        return self._running

    def volume_db(self) -> float:
        """Aktueller Volume-Level in dB (-60..0)."""
        with self._lock:
            v = self._latest_volume
        if v < 1e-6:
            return -60.0
        return 20.0 * np.log10(min(1.0, v))

    def start(self):
        if not HAS_SOUNDCARD:
            self._set_error("soundcard nicht verfuegbar")
            print("[AudioCapture] soundcard nicht verfügbar")
            return False
        if self._running:
            return True
        self._set_error(None)
        if self._device_name is None:
            # Default je nach Quelle waehlen
            if self.source_mode == "input":
                self._device_name = self.default_input()
            else:
                self._device_name = self.default_speaker()
        if self._device_name is None:
            self._set_error("Kein Audio-Geraet gefunden")
            return False
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="AudioCapture")
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self):
        try:
            # Quelle bestimmen: Loopback (PC-Wiedergabe) vs. echter Eingang
            if self.source_mode == "input":
                mic = sc.get_microphone(self._device_name, include_loopback=False)
            else:
                mic = sc.get_microphone(self._device_name, include_loopback=True)
            with mic.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS,
                              blocksize=CHUNK_SIZE) as rec:
                # Recorder offen -> letzter Fehler ist obsolet
                with self._lock:
                    self._error = None
                fails = 0
                while self._running:
                    try:
                        data = rec.record(numframes=CHUNK_SIZE)
                        if data.ndim > 1:
                            data = data.mean(axis=1)  # zu mono
                        fails = 0
                        # Volume
                        rms = float(np.sqrt(np.mean(data**2)))
                        with self._lock:
                            self._latest_volume = rms
                        # Subscribern verteilen
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
