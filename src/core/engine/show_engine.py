"""Show function — timeline-based triggering of child functions."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from .function import Function, FunctionType

if TYPE_CHECKING:
    from src.core.dmx.universe import Universe
    from src.core.database.models import PatchedFixture


@dataclass
class ShowFunction:
    """A function placed on a track at a specific time."""
    function_id: int
    start_time: float       # seconds from show start
    duration: float         # seconds (0 = use child function's natural duration)
    color: str = "#4A90D9"  # display color for timeline
    _started: bool = field(default=False, init=False, repr=False)
    _stopped: bool = field(default=False, init=False, repr=False)

    def reset(self):
        self._started = False
        self._stopped = False

    def end_time(self) -> float:
        return self.start_time + self.duration


@dataclass
class ShowTrack:
    name: str = "Track"
    muted: bool = False
    show_functions: list[ShowFunction] = field(default_factory=list)

    def add_function(self, sf: ShowFunction):
        self.show_functions.append(sf)
        self.show_functions.sort(key=lambda x: x.start_time)

    def remove_function(self, function_id: int, start_time: float):
        self.show_functions = [
            sf for sf in self.show_functions
            if not (sf.function_id == function_id and
                    abs(sf.start_time - start_time) < 0.001)
        ]


class Show(Function):
    """
    QLC+ Show: timeline that triggers child functions at specific times.
    Tracks contain ShowFunctions each with a start_time and duration.
    """

    function_type = FunctionType.Show

    def __init__(self, name: str = "Neue Show", fid: int | None = None):
        super().__init__(name, fid)
        self.tracks: list[ShowTrack] = []
        self.total_duration: float = 60.0   # seconds
        self.loop: bool = False

    # ── Track management ──────────────────────────────────────────────────────

    def add_track(self, name: str = "Track") -> ShowTrack:
        track = ShowTrack(name=name)
        self.tracks.append(track)
        return track

    def remove_track(self, track: ShowTrack):
        self.tracks = [t for t in self.tracks if t is not track]

    def recalc_duration(self):
        """Set total_duration to the end time of the last ShowFunction."""
        max_end = 0.0
        for track in self.tracks:
            for sf in track.show_functions:
                max_end = max(max_end, sf.end_time())
        self.total_duration = max(max_end, 1.0)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_start(self):
        for track in self.tracks:
            for sf in track.show_functions:
                sf.reset()

    def _on_stop(self):
        pass

    # ── write ─────────────────────────────────────────────────────────────────

    def write(self, universes: dict[int, "Universe"],
              patch_cache: list["PatchedFixture"],
              dt: float,
              function_registry: dict[int, Function] | None = None):
        if not self._running:
            return

        prev_elapsed = self._elapsed
        self._elapsed += dt

        if function_registry is None:
            return

        for track in self.tracks:
            if track.muted:
                continue
            for sf in track.show_functions:
                # Trigger start
                if (not sf._started and
                        prev_elapsed <= sf.start_time <= self._elapsed):
                    sf._started = True
                    child = function_registry.get(sf.function_id)
                    if child is not None:
                        child.start()

                # Write while active
                if sf._started and not sf._stopped:
                    child = function_registry.get(sf.function_id)
                    if child is not None:
                        child.write(universes, patch_cache, dt, function_registry)

                # Trigger stop
                if (sf._started and not sf._stopped and
                        self._elapsed >= sf.end_time()):
                    sf._stopped = True
                    child = function_registry.get(sf.function_id)
                    if child is not None:
                        child.stop()

        # Handle end / loop
        if self._elapsed >= self.total_duration:
            if self.loop:
                self._elapsed = 0.0
                for track in self.tracks:
                    for sf in track.show_functions:
                        sf.reset()
            else:
                self._running = False

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "total_duration": self.total_duration,
            "loop": self.loop,
            "tracks": [
                {
                    "name": t.name,
                    "muted": t.muted,
                    "functions": [
                        {
                            "function_id": sf.function_id,
                            "start_time": sf.start_time,
                            "duration": sf.duration,
                            "color": sf.color,
                        }
                        for sf in t.show_functions
                    ],
                }
                for t in self.tracks
            ],
        })
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Show":
        s = cls(name=d.get("name", "Show"), fid=d.get("id"))
        s.total_duration = d.get("total_duration", 60.0)
        s.loop = d.get("loop", False)
        for td in d.get("tracks", []):
            track = s.add_track(td.get("name", "Track"))
            track.muted = td.get("muted", False)
            for fd in td.get("functions", []):
                track.add_function(ShowFunction(
                    function_id=fd["function_id"],
                    start_time=fd["start_time"],
                    duration=fd["duration"],
                    color=fd.get("color", "#4A90D9"),
                ))
        return s
