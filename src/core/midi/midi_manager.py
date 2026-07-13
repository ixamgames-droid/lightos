"""MIDI Manager — Geräte auflisten, empfangen, senden, virtueller Port.

Backend-Priorität:
  1. python-rtmidi  (plattformübergreifend, falls installiert)
  2. WinMM via ctypes  (Windows ARM64 / kein Compiler nötig)
"""
from __future__ import annotations
import threading
import queue
from dataclasses import dataclass
from typing import Callable

try:
    import rtmidi
    RTMIDI_OK = True
except ImportError:
    RTMIDI_OK = False

try:
    from .midi_backend_winmm import (
        WINMM_OK,
        list_inputs as _winmm_list_inputs,
        list_outputs as _winmm_list_outputs,
        WinMMInput,
        WinMMOutput,
    )
except Exception:
    WINMM_OK = False

# Welches Backend ist aktiv?
_USE_WINMM = (not RTMIDI_OK) and WINMM_OK

# Groesse der bounded RX-Queue (Treiber-Callback -> MidiDispatch-Thread).
_RX_QUEUE_MAX = 4096


@dataclass
class MidiMessage:
    port_name: str
    channel: int       # 1-16
    msg_type: str      # "note_on", "note_off", "cc", "pc", "pitchbend"
    data1: int         # Note / CC-Nummer / PC-Nummer
    data2: int         # Velocity / CC-Wert / 0


def _decode(raw: list[int], port_name: str) -> MidiMessage | None:
    if not raw:
        return None
    status = raw[0]
    msg_type_code = status & 0xF0
    channel = (status & 0x0F) + 1
    d1 = raw[1] if len(raw) > 1 else 0
    d2 = raw[2] if len(raw) > 2 else 0

    types = {
        0x90: "note_on" if d2 > 0 else "note_off",
        0x80: "note_off",
        0xB0: "cc",
        0xC0: "pc",
        0xE0: "pitchbend",
    }
    msg_type = types.get(msg_type_code)
    if msg_type is None:
        return None
    return MidiMessage(port_name, channel, msg_type, d1, d2)


class MidiManager:
    def __init__(self):
        self._inputs: dict[str, object] = {}
        self._output: object | None = None
        self._output_name: str = ""
        self._virtual_out: object | None = None
        self._io_lock = threading.RLock()
        self._callbacks: list[Callable[[MidiMessage], None]] = []
        self._log_callbacks: list[Callable[[str], None]] = []
        self._rx_queue: queue.Queue[tuple[list[int], str]] = queue.Queue(maxsize=_RX_QUEUE_MAX)
        self._rx_dropped = 0  # Zaehler fuer bei Overflow verworfene Nachrichten (F2)
        self._rx_running = True
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True, name="MidiDispatch")
        self._rx_thread.start()
        self.available = RTMIDI_OK or WINMM_OK
        if _USE_WINMM:
            self._log("MIDI: rtmidi nicht verfügbar — nutze Windows WinMM Backend (ARM-kompatibel)")

    # ── Port-Listing ─────────────────────────────────────────────────────────

    def list_inputs(self) -> list[str]:
        if _USE_WINMM:
            return _winmm_list_inputs()
        if not RTMIDI_OK:
            return []
        m = rtmidi.MidiIn()
        ports = [m.get_port_name(i) for i in range(m.get_port_count())]
        del m
        return ports

    def list_outputs(self) -> list[str]:
        if _USE_WINMM:
            return _winmm_list_outputs()
        if not RTMIDI_OK:
            return []
        m = rtmidi.MidiOut()
        ports = [m.get_port_name(i) for i in range(m.get_port_count())]
        del m
        return ports

    # ── Verbinden ────────────────────────────────────────────────────────────

    def _input_handle_alive(self, handle: object, port_name: str) -> bool:
        """Prueft, ob ein bereits geoeffneter Input-Handle noch lebt (F3).

        Ein Backend-Handle darf optional eine ``is_alive()``-Methode anbieten
        (wird bevorzugt). Fehlt sie, gilt der Handle als lebendig, solange sein
        Port noch in ``list_inputs()`` auftaucht — verschwundene Ports werden von
        ``open_all_inputs`` separat evakuiert."""
        checker = getattr(handle, "is_alive", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                return False
        try:
            return port_name in self.list_inputs()
        except Exception:
            return True

    def _evict_input(self, port_name: str):
        """Schliesst einen (toten/verschwundenen) Input-Handle und entfernt ihn."""
        handle = self._inputs.pop(port_name, None)
        if handle is None:
            return
        try:
            handle.close_port()
        except Exception:
            pass

    def open_input(self, port_name: str):
        existing = self._inputs.get(port_name)
        if existing is not None:
            if self._input_handle_alive(existing, port_name):
                return
            # Toter Handle (z.B. nach USB-Unplug/Replug) -> evakuieren + neu oeffnen,
            # sonst bleibt der Controller stumm bis App-Neustart trotz Auto-Connect.
            print(f"[midi_manager] toter Input-Handle fuer '{port_name}' erkannt "
                  f"-> schliesse + oeffne neu")
            self._evict_input(port_name)
        if _USE_WINMM:
            ports = _winmm_list_inputs()
            if port_name not in ports:
                return
            idx = ports.index(port_name)
            try:
                m = WinMMInput(idx, port_name, self._on_message)
                self._inputs[port_name] = m
                self._log(f"MIDI Input geöffnet (WinMM): {port_name}")
            except Exception as e:
                self._log(f"MIDI Input Fehler: {e}")
            return
        if not RTMIDI_OK:
            return
        m = rtmidi.MidiIn()
        ports = [m.get_port_name(i) for i in range(m.get_port_count())]
        if port_name not in ports:
            del m
            return
        idx = ports.index(port_name)
        m.open_port(idx)
        m.set_callback(lambda msg, _: self._on_message(msg[0], port_name))
        self._inputs[port_name] = m
        self._log(f"MIDI Input geöffnet: {port_name}")

    def open_all_inputs(self) -> int:
        """Öffnet alle verfügbaren MIDI-Eingänge (Auto-Connect, idempotent).

        open_input() prüft bei bereits offenen Ports die Handle-Lebendigkeit und
        ersetzt tote Handles; verschwundene Ports (USB-Unplug) werden hier
        evakuiert. Damit ist der periodische Aufruf echt Hot-(Re-)Plug-tauglich.
        Gibt die Anzahl offener Eingänge zurück."""
        try:
            names = self.list_inputs()
        except Exception:
            names = []
        # Verschwundene Ports evakuieren: ein während des Betriebs abgezogenes
        # Gerät hinterlässt sonst einen toten Handle im Dict, der beim Replug
        # (Name taucht wieder auf) die Neuverbindung blockiert.
        for open_name in list(self._inputs.keys()):
            if open_name.startswith("Virtual:"):
                continue
            if open_name not in names:
                print(f"[midi_manager] Input-Port verschwunden -> evakuiere '{open_name}'")
                self._evict_input(open_name)
        for name in names:
            if name and not name.startswith("("):
                try:
                    self.open_input(name)
                except Exception as e:
                    self._log(f"Auto-Connect Fehler ({name}): {e}")
        return len(self._inputs)

    def open_output(self, port_name: str):
        with self._io_lock:
            if self._output is not None and self._output_name == port_name:
                return

            if _USE_WINMM:
                ports = _winmm_list_outputs()
                if port_name not in ports:
                    return
                idx = ports.index(port_name)
                try:
                    if self._output is not None:
                        try:
                            self._output.close_port()
                        except Exception:
                            pass
                        self._output = None
                    self._output = WinMMOutput(idx)
                    self._output_name = port_name
                    self._log(f"MIDI Output geöffnet (WinMM): {port_name}")
                except Exception as e:
                    self._log(f"MIDI Output Fehler: {e}")
                return

            if not RTMIDI_OK:
                return
            m = rtmidi.MidiOut()
            ports = [m.get_port_name(i) for i in range(m.get_port_count())]
            if port_name not in ports:
                del m
                return
            idx = ports.index(port_name)
            m.open_port(idx)
            if self._output is not None:
                try:
                    self._output.close_port()
                except Exception:
                    pass
            self._output = m
            self._output_name = port_name
            self._log(f"MIDI Output geöffnet: {port_name}")

    def open_virtual_input(self, name: str = "LightOS Virtual IN"):
        """Erstellt einen virtuellen MIDI-Eingang (andere Apps können darauf senden)."""
        if _USE_WINMM:
            self._log("Virtueller MIDI-Port: WinMM unterstützt keine virtuellen Ports. loopMIDI installieren.")
            return False
        if not RTMIDI_OK:
            return False
        try:
            m = rtmidi.MidiIn()
            m.open_virtual_port(name)
            m.set_callback(lambda msg, _: self._on_message(msg[0], f"Virtual:{name}"))
            self._inputs[f"Virtual:{name}"] = m
            self._log(f"Virtueller MIDI-Eingang erstellt: {name}")
            return True
        except Exception as e:
            self._log(f"Virtueller Port fehlgeschlagen: {e}")
            return False

    def open_virtual_output(self, name: str = "LightOS Virtual OUT"):
        """Erstellt einen virtuellen MIDI-Ausgang."""
        if _USE_WINMM:
            self._log("Virtueller MIDI-Port: WinMM unterstützt keine virtuellen Ports. loopMIDI installieren.")
            return False
        if not RTMIDI_OK:
            return False
        try:
            m = rtmidi.MidiOut()
            m.open_virtual_port(name)
            self._virtual_out = m
            self._log(f"Virtueller MIDI-Ausgang erstellt: {name}")
            return True
        except Exception as e:
            self._log(f"Virtueller Port fehlgeschlagen: {e}")
            return False

    def close_all(self):
        self._rx_running = False
        try:
            self._rx_queue.put_nowait(([], ""))
        except Exception:
            pass
        try:
            self._rx_thread.join(timeout=0.5)
        except Exception:
            pass
        for m in self._inputs.values():
            try:
                m.close_port()
            except Exception:
                pass
        self._inputs.clear()
        with self._io_lock:
            if self._output:
                try:
                    self._output.close_port()
                except Exception:
                    pass
            if self._virtual_out:
                try:
                    self._virtual_out.close_port()
                except Exception:
                    pass
            self._output = None
            self._output_name = ""
            self._virtual_out = None

    # ── Senden ───────────────────────────────────────────────────────────────

    def send_cc(self, channel: int, cc: int, value: int, virtual: bool = False):
        status = 0xB0 | ((channel - 1) & 0x0F)
        msg = [status, cc & 0x7F, value & 0x7F]
        with self._io_lock:
            out = self._virtual_out if virtual else self._output
            if out:
                out.send_message(msg)

    def send_note(self, channel: int, note: int, velocity: int = 127):
        status = 0x90 | ((channel - 1) & 0x0F)
        with self._io_lock:
            self._output and self._output.send_message([status, note & 0x7F, velocity & 0x7F])

    def send_note_off(self, channel: int, note: int):
        status = 0x80 | ((channel - 1) & 0x0F)
        with self._io_lock:
            self._output and self._output.send_message([status, note & 0x7F, 0])

    def current_output_name(self) -> str:
        with self._io_lock:
            return self._output_name

    # ── Callbacks ────────────────────────────────────────────────────────────

    def subscribe(self, cb: Callable[[MidiMessage], None]):
        self._callbacks.append(cb)

    def unsubscribe(self, cb: Callable[[MidiMessage], None]):
        """Entfernt einen zuvor registrierten Callback (z.B. beim Schliessen
        eines temporaeren Subscribers wie dem MIDI-Teach-Dialog)."""
        try:
            self._callbacks.remove(cb)
        except ValueError:
            pass

    def subscribe_log(self, cb: Callable[[str], None]):
        self._log_callbacks.append(cb)

    def unsubscribe_log(self, cb: Callable[[str], None]):
        """Entfernt einen Log-Subscriber, etwa beim Schliessen einer View."""
        try:
            self._log_callbacks.remove(cb)
        except ValueError:
            pass

    @staticmethod
    def _is_release(raw: list[int]) -> bool:
        """True für 'Loslass'-Nachrichten, die einen Zustand zurücknehmen:
        Note-Off, Note-On mit Velocity 0 (== Note-Off) und CC-Wert 0
        (Moment-/Flash-Button-Release). Diese dürfen NIE still verloren gehen,
        sonst bleibt ein Flash/Moment-Button dauerhaft an (F2)."""
        if not raw:
            return False
        status = raw[0] & 0xF0
        d2 = raw[2] if len(raw) > 2 else 0
        if status == 0x80:              # Note-Off
            return True
        if status == 0x90 and d2 == 0:  # Note-On Velocity 0 == Note-Off
            return True
        if status == 0xB0 and d2 == 0:  # CC-Wert 0 -> Button-Release
            return True
        return False

    def _make_room_for_release(self) -> bool:
        """Verwirft das älteste Nicht-Release-Element der RX-Queue, um Platz für
        eine ankommende Release-Nachricht zu schaffen. Dabei herausgezogene
        Release-Nachrichten werden wieder eingereiht, damit KEIN Note-Off/CC-0
        verloren geht. Gibt True zurück, wenn ein Platz frei wurde."""
        held: list[tuple[list[int], str]] = []
        dropped = False
        while True:
            try:
                item = self._rx_queue.get_nowait()
            except queue.Empty:
                break
            if self._is_release(item[0]):
                held.append(item)   # Release behalten
                continue
            dropped = True           # ältestes Nicht-Release gefunden -> verwerfen
            break
        for it in held:              # zurückgehaltene Releases wieder einreihen
            try:
                self._rx_queue.put_nowait(it)
            except queue.Full:
                break
        return dropped

    def _on_message(self, raw: list[int], port_name: str):
        item = (list(raw), port_name)
        try:
            self._rx_queue.put_nowait(item)
            return
        except queue.Full:
            pass
        # Queue voll: NICHT still verwerfen. Release-Nachrichten (Note-Off/CC-0)
        # bevorzugt zustellen, indem eine ältere Nicht-Release-Nachricht weicht.
        if self._is_release(raw) and self._make_room_for_release():
            try:
                self._rx_queue.put_nowait(item)
                self._rx_dropped += 1
                print(f"[midi_manager] RX-Queue voll — ältere Nachricht verworfen, "
                      f"damit Note-Off/CC-0 zugestellt wird (drops={self._rx_dropped})")
                return
            except queue.Full:
                pass
        # Sonst: diese Nachricht verwerfen, aber zählen + (gedrosselt) warnen.
        self._rx_dropped += 1
        if self._rx_dropped == 1 or self._rx_dropped % 64 == 0:
            print(f"[midi_manager] RX-Queue voll (maxsize={_RX_QUEUE_MAX}) — "
                  f"Nachricht verworfen (drops={self._rx_dropped})")

    def _rx_loop(self):
        while self._rx_running:
            try:
                raw, port_name = self._rx_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if not self._rx_running:
                break
            if not raw and not port_name:
                continue
            msg = _decode(raw, port_name)
            if msg:
                # Kopie: subscribe/unsubscribe aus dem UI-Thread darf die Liste
                # waehrend der Iteration veraendern (sonst RuntimeError/Skips).
                for cb in list(self._callbacks):
                    try:
                        cb(msg)
                    except Exception:
                        pass
                # Kein Per-Nachricht-Log hier: die MIDI-View zeigt eingehende Nachrichten
                # thread-sicher und gedrosselt im Monitor an. Ein zusätzliches Log pro
                # Event würde die Anzeige duplizieren und die Qt-Event-Loop fluten.

    def _log(self, text: str):
        for cb in list(self._log_callbacks):
            try:
                cb(text)
            except Exception:
                pass


# Singleton
_manager: MidiManager | None = None


def get_midi_manager() -> MidiManager:
    global _manager
    if _manager is None:
        _manager = MidiManager()
    return _manager
