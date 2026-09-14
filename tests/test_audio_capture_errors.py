"""BPM-10 (S5): Capture-Fehlerpfade und Geraetelisten mit Fake-soundcard.

Uebernimmt ``test_audio_capture_records_missing_default_device`` aus der
entfallenen tests/test_audio_input_view.py. Kein echtes Audio: ``sc`` wird
durch ein Fake-Modul ersetzt, das PulseAudio (Monitore ``<sink>.monitor``,
``isloopback`` ueber device.class) bzw. WASAPI (Loopback = gleiche id wie der
Lautsprecher) nachbildet — inklusive der Namenssuche von soundcard, die einen
Monitor als Eingang mit IndexError ablehnt.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.core.audio import capture as capmod
from src.core.audio.level_meter import CaptureSnapshot


class _Dev:
    def __init__(self, id, name, isloopback=False):
        self.id = id
        self.name = name
        self.isloopback = isloopback


class _NoIdDev:
    """Backend ohne ``.id`` (Fallback: bisheriges Verhalten ueber den Namen)."""
    def __init__(self, name, isloopback=False):
        self.name = name
        self.isloopback = isloopback


class _FakePulse:
    """Zwei Sinks, deren Monitore, ein echtes Mikrofon."""
    def __init__(self, default_source="alsa_output.hdmi.monitor"):
        self.speakers = [_Dev("alsa_output.pci.analog-stereo", "Built-in Audio Analog Stereo"),
                         _Dev("alsa_output.hdmi", "HDMI Audio Analog Stereo")]
        self.sources = [_Dev("alsa_output.pci.analog-stereo.monitor",
                             "Monitor of Built-in Audio Analog Stereo", True),
                        _Dev("alsa_output.hdmi.monitor", "Monitor of HDMI Audio Analog Stereo", True),
                        _Dev("alsa_input.usb.analog-stereo", "USB Audio CODEC Analog Stereo")]
        self.default_source = default_source
        self.lookups: list = []

    def all_speakers(self):
        return list(self.speakers)

    def default_speaker(self):
        return self.speakers[0]

    def all_microphones(self, include_loopback=False):
        return [m for m in self.sources if include_loopback or not m.isloopback]

    def default_microphone(self):
        return self.get_microphone(self.default_source, include_loopback=True)

    def get_microphone(self, id, include_loopback=False):
        """Nachbau von soundcard._match_soundcard: id, Teilstring, sonst IndexError."""
        self.lookups.append((id, include_loopback))
        pool = self.all_microphones(include_loopback)
        for m in pool:
            if m.id == id:
                return m
        for m in pool:
            if id in m.name:
                return m
        raise IndexError(f"no soundcard with id {id}")


@pytest.fixture
def pulse(monkeypatch):
    fake = _FakePulse()
    monkeypatch.setattr(capmod, "HAS_SOUNDCARD", True)
    monkeypatch.setattr(capmod, "sc", fake)
    return fake


def test_audio_capture_records_missing_default_device(monkeypatch):
    monkeypatch.setattr(capmod, "HAS_SOUNDCARD", True)
    monkeypatch.setattr(capmod.AudioCapture, "default_loopback_sink", staticmethod(lambda: None))
    cap = capmod.AudioCapture()
    assert cap.start() is False
    assert cap.last_error() == "Kein Audio-Geraet gefunden"
    assert cap.snapshot().running is False


def test_eingaenge_ohne_monitore(pulse):
    assert capmod.AudioCapture.list_input_devices() == ["USB Audio CODEC Analog Stereo"]
    # Monitor, der sich nicht als isloopback ausweist, faellt ueber die id raus
    pulse.sources.append(_Dev("x.monitor", "Monitor of X"))
    assert capmod.AudioCapture.list_input_devices() == ["USB Audio CODEC Analog Stereo"]


def test_default_input_ist_nie_ein_monitor(pulse):
    """G16: Standardquelle = Monitor -> frueher ``Monitor of …`` als Eingang und
    IndexError in get_microphone(include_loopback=False)."""
    assert capmod.AudioCapture.default_input() == "USB Audio CODEC Analog Stereo"
    pulse.default_source = "alsa_input.usb.analog-stereo"
    assert capmod.AudioCapture.default_input() == "USB Audio CODEC Analog Stereo"
    pulse.sources = [s for s in pulse.sources if s.isloopback]
    pulse.default_source = "alsa_output.hdmi.monitor"
    assert capmod.AudioCapture.default_input() is None


def test_eingang_nicht_gefunden_ist_lesbarer_fehler(pulse):
    cap = capmod.AudioCapture()
    cap.source_mode = "input"
    cap._device_name = "Monitor of HDMI Audio Analog Stereo"
    cap._running = True
    cap._run(epoch=cap._epoch)
    assert cap.last_error() == "Eingang nicht gefunden: Monitor of HDMI Audio Analog Stereo"
    assert cap.is_running() is False


def test_sink_liste_ueber_id(pulse):
    assert capmod.AudioCapture.list_loopback_sinks() == [
        ("alsa_output.pci.analog-stereo", "Built-in Audio Analog Stereo"),
        ("alsa_output.hdmi", "HDMI Audio Analog Stereo"),
    ]
    assert capmod.AudioCapture.default_loopback_sink() == "alsa_output.pci.analog-stereo"


def test_sink_liste_ohne_id_faellt_auf_namen_zurueck(monkeypatch):
    class _Sc:
        def all_speakers(self):
            return [_NoIdDev("Lautsprecher"), _NoIdDev("Lautsprecher")]

        def default_speaker(self):
            return _NoIdDev("Lautsprecher")
    monkeypatch.setattr(capmod, "HAS_SOUNDCARD", True)
    monkeypatch.setattr(capmod, "sc", _Sc())
    assert capmod.AudioCapture.list_loopback_sinks() == [("Lautsprecher", "Lautsprecher")]
    assert capmod.AudioCapture.default_loopback_sink() == "Lautsprecher"


def test_loopback_je_sink_exakt_ueber_id_statt_teilstring(pulse):
    """Teilstring-Suche nahm bei aehnlichen Namen den falschen Monitor; die id
    trifft genau. Ein Mikrofonname lenkt den Loopback nie aufs Mikrofon."""
    lb = capmod.AudioCapture._loopback_microphone
    assert lb("alsa_output.hdmi").id == "alsa_output.hdmi.monitor"
    assert lb("alsa_output.pci.analog-stereo").id == "alsa_output.pci.analog-stereo.monitor"
    assert lb("HDMI Audio Analog Stereo").id == "alsa_output.hdmi.monitor"   # Sink-Name
    assert pulse.lookups == []                      # keine Namenssuche noetig
    with pytest.raises(RuntimeError, match="PC-Audio-Ausgang nicht gefunden"):
        lb("gibt es nicht")


def test_loopback_wasapi_gleiche_id(monkeypatch):
    spk = _Dev("{0.0.0.00000000}.{abc}", "Lautsprecher (Realtek)")

    class _Wasapi:
        def all_speakers(self):
            return [spk]

        def all_microphones(self, include_loopback=False):
            mic = _Dev("{0.0.1.00000000}.{def}", "Mikrofon (Realtek)")
            loop = _Dev(spk.id, spk.name, True)
            return ([loop] if include_loopback else []) + [mic]

        def get_microphone(self, id, include_loopback=False):  # pragma: no cover
            raise AssertionError("Namenssuche nicht erwartet")
    monkeypatch.setattr(capmod, "HAS_SOUNDCARD", True)
    monkeypatch.setattr(capmod, "sc", _Wasapi())
    m = capmod.AudioCapture._loopback_microphone(spk.id)
    assert m.id == spk.id and m.isloopback


def test_loopback_fallback_ohne_id_wie_bisher(monkeypatch):
    calls = []

    class _Sc:
        def all_speakers(self):
            return [_NoIdDev("Speaker")]

        def all_microphones(self, include_loopback=False):
            return [_NoIdDev("Speaker", True)]

        def get_microphone(self, id, include_loopback=False):
            calls.append((id, include_loopback))
            return _NoIdDev("Speaker", True)
    monkeypatch.setattr(capmod, "HAS_SOUNDCARD", True)
    monkeypatch.setattr(capmod, "sc", _Sc())
    assert capmod.AudioCapture._loopback_microphone("Speaker").name == "Speaker"
    assert calls == [("Speaker", True)]


def test_set_source_mode_loopback_merkt_sink_id(pulse):
    cap = capmod.AudioCapture()
    cap.set_source_mode("loopback", "alsa_output.hdmi")
    assert (cap.source_mode, cap._device_name) == ("loopback", "alsa_output.hdmi")
    s = cap.snapshot()
    assert isinstance(s, CaptureSnapshot)
    assert (s.running, s.device, s.source_mode) == (False, "alsa_output.hdmi", "loopback")


class _Rec:
    def __init__(self, cap, n):
        self.cap, self.n = cap, n

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def record(self, numframes):
        self.n -= 1
        if self.n <= 0:
            self.cap._running = False
        return np.full((numframes, 1), 0.5, np.float32)


def test_start_haengt_levelmeter_an_und_snapshot_fuellt_sich(pulse, monkeypatch):
    cap = capmod.AudioCapture()
    mon = pulse.sources[0]
    mon.recorder = lambda **kw: _Rec(cap, 5)
    got = []
    cap.subscribe(got.append)
    # Thread nicht wirklich starten: _run synchron nach start()
    started = []
    monkeypatch.setattr(capmod.threading.Thread, "start", lambda self: started.append(self))
    assert cap.start() is True
    assert cap._device_name == "alsa_output.pci.analog-stereo"
    assert cap.is_subscribed(cap._meter.on_chunk) and len(cap._subscribers) == 2
    cap._run(epoch=cap._epoch)
    s = cap.snapshot()
    assert s.chunks == 5 and s.peak_dbfs == pytest.approx(-6.02, abs=0.05)
    assert cap.volume_db() == pytest.approx(-6.02, abs=0.05)
    assert len(got) == 5
    cap._thread = None                  # nie wirklich gestartet
    cap.stop()
    assert not cap.is_subscribed(cap._meter.on_chunk)
    assert cap.snapshot().running is False
