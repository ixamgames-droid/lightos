"""„Eingang 30 s aufnehmen" (BPM-11, S6) — Diagnose-Mitschnitt des Capture-Eingangs.

``AudioRecorder.start(seconds=30)`` abonniert den ``AudioCapture``. Der Callback im
Capture-Thread legt den Chunk (Kopie) NUR in eine Queue — sonst nichts, damit der
Detektor keinen Rueckstand bekommt. Ein eigener Worker-Thread (weder Audio- noch
UI-Thread) schreibt fortlaufend eine WAV-Datei (PCM 16 bit, mono, Abtastrate aus
dem Capture, Standardmodul ``wave``) und am Ende eine Sidecar-JSON nach

    app_data_dir()/audio_diag/lightos_eingang_<YYYYmmdd-HHMMSS>.wav / .json

Abbruch (``cancel()``) oder ein gestoppter Capture beenden die Aufnahme sauber: die
WAV ist kuerzer, aber gueltig, die JSON traegt ``"abgebrochen": true``. Der Abschluss
wird ueber ``on_finished(wav_pfad)`` gemeldet — AUS DEM WORKER-THREAD; die View
marshallt per Qt-Signal.

Datenschutz: die JSON enthaelt keinen Benutzerpfad (nur ``datei`` relativ zum
Datenordner) und keine Namen — Geraetename, Quelle, Pegel, Version, Zeit.
"""
from __future__ import annotations

import json
import math
import os
import queue
import re
import sys
import threading
import time
import wave
from datetime import datetime, timezone

import numpy as np

SIDECAR_VERSION = 1
UNTERORDNER = "audio_diag"
PRAEFIX = "lightos_eingang_"
STANDARD_DAUER_S = 30.0
_CLIP_LIN = 10.0 ** (-0.1 / 20.0)      # wie level_meter.CLIP_SAMPLE_DBFS


def _dbfs(lin: float) -> float:
    return round(20.0 * math.log10(lin), 2) if lin > 1e-6 else -120.0


def _lightos_version() -> str | None:
    """APP_VERSION aus main.py (ohne main zu importieren) — None, wenn nicht ermittelbar."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        with open(os.path.join(root, "main.py"), encoding="utf-8") as f:
            m = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', f.read(), re.M)
        return m.group(1) if m else None
    except Exception:
        return None


def _log(msg: str) -> None:
    print(f"[AudioRecorder] {msg}")


class AudioRecorder:
    """Ein Mitschnitt zur Zeit; ``start`` waehrend einer laufenden Aufnahme -> False."""

    def __init__(self, capture=None, detector=None, base_dir=None, on_finished=None):
        self._cap = capture
        self._det = detector
        self._base_dir = base_dir
        self.on_finished = on_finished
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._running = False
        self._samples = 0
        self._sr = 44100
        self.last_path: str | None = None
        self.last_info: dict | None = None

    # ── Backends ─────────────────────────────────────────────────────────────
    def _capture(self):
        if self._cap is None:
            from src.core.audio.capture import get_audio_capture
            self._cap = get_audio_capture()
        return self._cap

    def _detector(self):
        if self._det is None:
            try:
                from src.core.audio.beat_detector import get_beat_detector
                self._det = get_beat_detector()
            except Exception:
                return None
        return self._det

    def _dir(self) -> str:
        base = self._base_dir
        if base is None:
            from src.core.paths import app_data_dir
            base = app_data_dir()
        return os.path.join(base, UNTERORDNER)

    # ── API ──────────────────────────────────────────────────────────────────
    def is_running(self) -> bool:
        return self._running

    def progress_s(self) -> float:
        return self._samples / float(self._sr or 44100)

    def cancel(self) -> None:
        self._cancel.set()

    def wait(self, timeout: float | None = None) -> bool:
        """Auf das Ende warten (Tests/Beenden). True, wenn fertig."""
        t = self._thread
        if t is not None:
            t.join(timeout)
            return not t.is_alive()
        return True

    def start(self, seconds: float = STANDARD_DAUER_S) -> bool:
        with self._lock:
            if self._running:
                return False
            cap = self._capture()
            if cap is None:
                return False
            sr = 0
            try:
                sr = int(getattr(cap.snapshot(), "sample_rate", 0) or 0)
            except Exception:
                sr = 0
            self._sr = sr or int(getattr(cap, "_sample_rate", 0) or 44100)
            self._q = queue.SimpleQueue()
            self._cancel.clear()
            self._samples = 0
            self._running = True
            ziel = os.path.join(self._dir(), self._dateiname())
            self._thread = threading.Thread(target=self._worker, args=(ziel, float(seconds)),
                                            daemon=True, name="AudioRecorder")
            cap.subscribe(self._on_chunk)
            self._thread.start()
            return True

    # ── Capture-Thread: NUR Queue ────────────────────────────────────────────
    def _on_chunk(self, samples) -> None:
        self._q.put(np.array(samples, dtype=np.float32, copy=True))

    # ── Worker ───────────────────────────────────────────────────────────────
    def _dateiname(self) -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        d = self._dir()
        name, n = f"{PRAEFIX}{stamp}", 2
        while os.path.exists(os.path.join(d, name + ".wav")) or os.path.exists(os.path.join(d, name + ".json")):
            name, n = f"{PRAEFIX}{stamp}-{n}", n + 1
        return name + ".wav"

    def _worker(self, wav_path: str, seconds: float) -> None:
        cap = self._cap
        sr = self._sr
        soll = int(round(seconds * sr))
        zeit = datetime.now(timezone.utc).isoformat(timespec="seconds")
        abgebrochen = False
        grund = None
        sq, peak, clips, dc = 0.0, 0.0, 0, 0.0
        wf = None
        try:
            os.makedirs(os.path.dirname(wav_path), exist_ok=True)
            wf = wave.open(wav_path, "wb")
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            while self._samples < soll:
                if self._cancel.is_set():
                    abgebrochen, grund = True, "abgebrochen"
                    break
                try:
                    x = self._q.get(timeout=0.1)
                except queue.Empty:
                    try:
                        if not cap.is_running():
                            abgebrochen, grund = True, "capture_gestoppt"
                            break
                    except Exception:
                        pass
                    continue
                if x.ndim > 1:
                    x = x.mean(axis=1)
                x = x[: soll - self._samples]
                if x.size == 0:
                    continue
                xd = x.astype(np.float64)
                sq += float(np.dot(xd, xd))
                dc += float(xd.sum())
                ax = np.abs(x)
                peak = max(peak, float(ax.max()))
                clips += int(np.count_nonzero(ax >= _CLIP_LIN))
                wf.writeframes((np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2").tobytes())
                self._samples += int(x.size)
        except Exception as e:
            abgebrochen, grund = True, f"fehler: {e}"
            _log(f"Aufnahme-Fehler: {e}")
        finally:
            try:
                cap.unsubscribe(self._on_chunk)
            except Exception:
                pass
            if wf is not None:
                try:
                    wf.close()
                except Exception as e:
                    _log(f"WAV schliessen: {e}")
        n = self._samples
        info = {
            "version": SIDECAR_VERSION,
            "zeit_utc": zeit,
            "dauer_s": round(n / float(sr), 3),
            "soll_s": seconds,
            "sample_rate": sr,
            "format": "WAV PCM 16 bit mono",
            "quelle": getattr(cap, "source_mode", None),
            "geraet": None,
            "rms_dbfs": _dbfs(math.sqrt(sq / n)) if n else -120.0,
            "peak_dbfs": _dbfs(peak),
            "clip_samples": clips,
            "dc_offset": round(dc / n, 5) if n else 0.0,
            "datei": f"{UNTERORDNER}/{os.path.basename(wav_path)}",
            "plattform": sys.platform,
            "abgebrochen": abgebrochen,
        }
        if grund:
            info["grund"] = grund
        try:
            snap = cap.snapshot()
            info["geraet"] = getattr(snap, "device", None)
            info["chunk_ms_p95"] = round(float(getattr(snap, "chunk_ms_p95", 0.0)), 2)
        except Exception:
            info["geraet"] = getattr(cap, "_device_name", None)
        det = self._detector()
        if det is not None:
            try:
                ds = det.snapshot()
                info["hum_ratio"] = round(float(ds.hum_ratio), 3)
                info["hum_hz"] = int(ds.hum_hz)
                info["erkennung"] = {"zustand": ds.state, "bpm": round(float(ds.bpm), 2),
                                     "konfidenz": round(float(ds.confidence), 3),
                                     "backlog_ms": round(float(ds.backlog_ms), 1)}
            except Exception:
                pass
        ver = _lightos_version()
        if ver:
            info["lightos_version"] = ver
        json_path = os.path.splitext(wav_path)[0] + ".json"
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log(f"JSON schreiben: {e}")
        self.last_path, self.last_info = wav_path, info
        self._running = False
        cb = self.on_finished
        if cb is not None:
            try:
                cb(wav_path)
            except Exception as e:
                _log(f"on_finished: {e}")


_recorder: AudioRecorder | None = None


def get_audio_recorder() -> AudioRecorder:
    global _recorder
    if _recorder is None:
        _recorder = AudioRecorder()
    return _recorder
