"""DMX-Universe Verwaltung — 512 Kanäle, Thread-safe."""
import threading


class Universe:
    SIZE = 512

    def __init__(self, number: int = 1):
        self.number = number
        self._data = bytearray(self.SIZE)
        self._lock = threading.Lock()

    def set_channel(self, channel: int, value: int):
        """Setzt einen Kanal (1-basiert, Wert 0-255).

        Robuste Validierung statt ``assert``: Eingaben kommen u. a. ungeprueft
        aus Netzwerk-Quellen (OSC/Web/ArtNet-Merge). Out-of-range-Kanaele werden
        verworfen, der Wert wird auf 0-255 geklemmt. ``assert`` waere unter
        ``python -O`` entfernt und wuerde dann zu stillem Negativ-Index-Wraparound
        (channel<=0) bzw. IndexError/ValueError fuehren.
        """
        try:
            channel = int(channel)
        except (TypeError, ValueError):
            return
        if not (1 <= channel <= self.SIZE):
            return
        try:
            value = int(value)
        except (TypeError, ValueError):
            return
        value = 0 if value < 0 else 255 if value > 255 else value
        with self._lock:
            self._data[channel - 1] = value

    def set_range(self, start: int, values: bytes | bytearray):
        """Setzt mehrere Kanäle ab Startadresse (1-basiert)."""
        end = start - 1 + len(values)
        assert end <= self.SIZE
        with self._lock:
            self._data[start - 1:end] = values

    def get_channel(self, channel: int) -> int:
        with self._lock:
            return self._data[channel - 1]

    def get_all(self) -> bytes:
        with self._lock:
            return bytes(self._data)

    def clear(self):
        with self._lock:
            self._data = bytearray(self.SIZE)
