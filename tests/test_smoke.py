from smoke_check import run_checks


def test_headless_smoke_check(tmp_path):
    report = run_checks(tmp_path)
    assert report == {
        "python": "3.11",
        "pid_count": 16,
        "demo_protocol": "DEMO — deterministic simulation",
        "csv_created": True,
        "settings_round_trip": True,
    }
