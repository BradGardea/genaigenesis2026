"""Virtual simulation clock with configurable tick interval."""

from __future__ import annotations


class SimulationClock:
    """Tracks virtual time progression for a simulation run."""

    def __init__(self, max_ticks: int, tick_interval_seconds: float = 2.0) -> None:
        self.max_ticks = max_ticks
        self.tick_interval_seconds = tick_interval_seconds
        self._current_tick = 0

    @property
    def current_tick(self) -> int:
        return self._current_tick

    @property
    def elapsed_virtual_seconds(self) -> float:
        return self._current_tick * self.tick_interval_seconds

    @property
    def is_expired(self) -> bool:
        return self._current_tick >= self.max_ticks

    def advance(self) -> int:
        """Advance clock by one tick. Returns the new tick number."""
        self._current_tick += 1
        return self._current_tick
