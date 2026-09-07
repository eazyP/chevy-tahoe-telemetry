"""Streaming CSV telemetry logger."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path


class CSVLogger:
    def __init__(self, directory: Path, fields: list[str], clock=None):
        self._clock = clock or (lambda: datetime.now(timezone.utc).astimezone())
        self.fields = list(fields)
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"tahoe_telemetry_{self._clock():%Y%m%d_%H%M%S}.csv"
        self._handle = self.path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._handle, fieldnames=["timestamp", *self.fields])
        self._writer.writeheader()
        self._handle.flush()

    def write(self, values: dict[str, object]) -> None:
        row = {"timestamp": self._clock().isoformat(timespec="seconds")}
        row.update({field: "Unsupported" if values.get(field) is None else values.get(field) for field in self.fields})
        self._writer.writerow(row)
        self._handle.flush()

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
