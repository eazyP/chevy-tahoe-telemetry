"""Persistent application preferences."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    port: str = ""
    baudrate: int = 38400
    protocol: str = "AUTO"
    poll_interval_ms: int = 500
    log_directory: str = ""


def default_settings_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return root / "TahoeTelemetry" / "settings.json"


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_settings_path()

    def load(self) -> AppSettings:
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
            allowed = {field: values[field] for field in AppSettings.__dataclass_fields__ if field in values}
            return AppSettings(**allowed)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
        temporary.replace(self.path)

