"""DMX-Universe Verwaltung — 512 Kanäle, Thread-safe."""
import threading


class Universe:
    SIZE = 512

    def __init__(self, number: int = 1):
        self.number = number
        self._data = bytearray(self.SIZE)
        self._lock = threading.Lock()

    def set_channel(self, channel: int, value: int):
        """Setzt einen Kanal (1-basiert, Wert 0-255)."""
        assert 1 <= channel <= self.SIZE, f"Kanal {channel} außerhalb Bereich"
        assert 0 <= value <= 255
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
