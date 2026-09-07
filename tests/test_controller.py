import threading
import time

import pytest

from tahoe_telemetry.controller import TelemetryController, validate_clear_request


class Source:
    def __init__(self):
        self.closed = False
        self.calls = []

    def discover_supported_pids(self):
        return {0x0C, 0x0D}

    def read_pid(self, pid):
        self.calls.append((pid, threading.current_thread().name))
        return {0x0C: 725.0, 0x0D: 12.0}[pid]

    def close(self):
        self.closed = True


def test_polling_occurs_off_main_thread_and_ui_events_are_queued():
    source = Source()
    controller = TelemetryController(source, poll_interval=0.01, history_size=3)
    controller.start()
    deadline = time.time() + 1
    while controller.events.empty() and time.time() < deadline:
        time.sleep(0.005)
    controller.stop()
    deadline = time.monotonic() + 1
    while controller.running and time.monotonic() < deadline:
        time.sleep(0.005)
    event, payload = controller.events.get_nowait()
    assert event == "supported"
    assert all(thread_name != threading.current_thread().name for _, thread_name in source.calls)
    assert source.closed
    assert not controller.running


def test_apply_sample_tracks_values_and_bounded_chart_history():
    controller = TelemetryController(Source(), history_size=2)
    controller.apply_sample({"rpm": 700.0, "speed": 1.0})
    controller.apply_sample({"rpm": 710.0, "speed": 2.0})
    controller.apply_sample({"rpm": 720.0, "speed": 3.0})
    assert list(controller.history["rpm"]) == [710.0, 720.0]
    assert list(controller.history["speed"]) == [2.0, 3.0]


@pytest.mark.parametrize(
    ("typed", "confirmed", "message"),
    [
        ("clear", True, "Type CLEAR exactly to enable diagnostic trouble code clearing."),
        ("CLEAR", False, "Clearing cancelled; no command was sent."),
    ],
)
def test_clear_validation(typed, confirmed, message):
    with pytest.raises(ValueError, match=message):
        validate_clear_request(typed, confirmed)


def test_clear_validation_accepts_both_gates():
    validate_clear_request("CLEAR", True)


def test_stop_is_nonblocking_and_worker_owns_close_after_blocking_io():
    entered = threading.Event()
    release = threading.Event()

    class BlockingSource(Source):
        def discover_supported_pids(self):
            entered.set()
            release.wait(1)
            return set()

    source = BlockingSource()
    controller = TelemetryController(source)
    controller.start()
    assert entered.wait(1)
    started = time.monotonic()
    controller.stop()
    assert time.monotonic() - started < 0.2
    assert controller.running
    assert not source.closed
    release.set()
    deadline = time.monotonic() + 1
    while controller.running and time.monotonic() < deadline:
        time.sleep(0.005)
    assert not controller.running
    assert source.closed


def test_fatal_poll_error_closes_source_and_emits_terminal_events():
    class FailingSource(Source):
        def discover_supported_pids(self):
            raise RuntimeError("adapter vanished")

    source = FailingSource()
    controller = TelemetryController(source)
    controller.start()
    deadline = time.monotonic() + 1
    while controller.running and time.monotonic() < deadline:
        time.sleep(0.005)
    assert source.closed
    assert list(controller.events.queue) == [
        ("error", "adapter vanished"),
        ("stopped", None),
    ]
