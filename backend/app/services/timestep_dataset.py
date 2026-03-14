from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TimestepDataset:
    """Generic helper for timestep-style JSON datasets."""

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._payload = self._load()

    def _load(self) -> dict[str, Any]:
        with self._file_path.open("r", encoding="utf-8") as source:
            data = json.load(source)
        if not isinstance(data, dict):
            raise ValueError("Timestep dataset root must be a JSON object.")
        if "timesteps" not in data or not isinstance(data["timesteps"], list):
            raise ValueError("Timestep dataset must include a 'timesteps' list.")
        return data

    @property
    def timesteps(self) -> list[dict[str, Any]]:
        return self._payload["timesteps"]

    @property
    def total_steps(self) -> int:
        return len(self.timesteps)

    def metadata(self) -> dict[str, Any]:
        return {key: value for key, value in self._payload.items() if key != "timesteps"}

    def get_step(self, step_index: int) -> dict[str, Any]:
        if step_index < 0 or step_index >= self.total_steps:
            raise IndexError("Step index out of range.")
        step = self.timesteps[step_index]
        if not isinstance(step, dict):
            raise ValueError("Timestep entries must be JSON objects.")
        return step

    def get_next_step_index(self, current_step: int) -> int:
        if current_step < 0:
            return 0
        return min(current_step + 1, max(self.total_steps - 1, 0))
