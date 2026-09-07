import csv
import json
from datetime import datetime, timezone

from tahoe_telemetry.csvlog import CSVLogger
from tahoe_telemetry.demo import DemoSource
from tahoe_telemetry.settings import AppSettings, SettingsStore


def test_demo_is_deterministic_and_reports_unsupported_fuel_type():
    first, second = DemoSource(seed=7), DemoSource(seed=7)
    assert first.connect() == "DEMO — deterministic simulation"
    assert first.discover_supported_pids() == second.discover_supported_pids()
    assert [first.read_pid(0x0C) for _ in range(4)] == [second.read_pid(0x0C) for _ in range(4)]
    assert first.read_pid(0x51) is None


def test_demo_dtcs_include_all_status_groups_and_clear():
    demo = DemoSource(seed=1)
    assert set(demo.read_dtcs()) == {"Stored", "Pending", "Permanent"}
    assert demo.read_dtcs()["Stored"][0].code == "P0171"
    demo.clear_dtcs()
    assert all(not records for records in demo.read_dtcs().values())


def test_settings_round_trip_and_invalid_json_falls_back(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    expected = AppSettings(port="COM8", baudrate=115200, protocol="VPW", poll_interval_ms=250)
    store.save(expected)
    assert store.load() == expected
    assert json.loads(path.read_text(encoding="utf-8"))["protocol"] == "VPW"
    path.write_text("not json", encoding="utf-8")
    assert store.load() == AppSettings()


def test_csv_logger_has_timestamped_name_header_and_rows(tmp_path):
    now = datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
    logger = CSVLogger(tmp_path, ["rpm", "speed"], clock=lambda: now)
    assert logger.path.name == "tahoe_telemetry_20260203_040506.csv"
    logger.write({"rpm": 700.0, "speed": None})
    logger.close()
    with logger.path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows == [
        ["timestamp", "rpm", "speed"],
        ["2026-02-03T04:05:06+00:00", "700.0", "Unsupported"],
    ]
