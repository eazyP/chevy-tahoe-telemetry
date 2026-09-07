"""Headless application smoke check; no serial port or Tk display is required."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from tahoe_telemetry.csvlog import CSVLogger
from tahoe_telemetry.demo import DemoSource
from tahoe_telemetry.obd import PID_DEFINITIONS
from tahoe_telemetry.settings import AppSettings, SettingsStore


def run_checks(work_directory: Path) -> dict[str, object]:
    work_directory = Path(work_directory)
    demo = DemoSource(seed=2004)
    protocol = demo.connect()
    supported = demo.discover_supported_pids()
    values = {PID_DEFINITIONS[pid].key: demo.read_pid(pid) for pid in sorted(supported)}
    logger = CSVLogger(work_directory, ["rpm", "speed"])
    logger.write(values)
    logger.close()
    settings = AppSettings(port="COM3", protocol="AUTO")
    store = SettingsStore(work_directory / "settings.json")
    store.save(settings)
    report = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "pid_count": len(PID_DEFINITIONS),
        "demo_protocol": protocol,
        "csv_created": logger.path.is_file(),
        "settings_round_trip": store.load() == settings,
    }
    demo.close()
    return report


def main() -> int:
    if sys.version_info[:2] != (3, 11):
        print(f"FAIL: Python 3.11 required; running {sys.version.split()[0]}")
        return 1
    with tempfile.TemporaryDirectory(prefix="tahoe_smoke_", dir=Path.cwd()) as directory:
        report = run_checks(Path(directory))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    passed = all((report["csv_created"], report["settings_round_trip"], report["pid_count"] == 16))
    print("SMOKE CHECK PASSED (headless/demo only; no hardware tested)" if passed else "SMOKE CHECK FAILED")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

