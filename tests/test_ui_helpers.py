import queue
import threading
import time

from tahoe_telemetry.ui import UILifecycle, chart_points, format_value


def test_format_value_handles_unsupported_text_and_precision():
    assert format_value(None, "%", 1) == "Unsupported"
    assert format_value("Ethanol", "", 0) == "Ethanol"
    assert format_value(14.126, "V", 2) == "14.13 V"


def test_chart_points_maps_values_and_handles_flat_series():
    assert chart_points([5.0, 5.0], 100, 50, padding=10) == [(10.0, 25.0), (90.0, 25.0)]
    points = chart_points([0.0, 10.0, 5.0], 100, 60, padding=10)
    assert points == [(10.0, 50.0), (50.0, 10.0), (90.0, 30.0)]


def test_shutdown_during_connect_closes_late_source_without_connected_event():
    release = threading.Event()
    events = queue.Queue()

    class Source:
        closed = False

        def connect(self):
            release.wait(1)
            return "protocol"

        def close(self):
            self.closed = True

    source = Source()
    lifecycle = UILifecycle(events.put)
    assert lifecycle.start_connect(source, source.connect)
    lifecycle.shutdown(None)
    release.set()
    deadline = time.monotonic() + 1
    while not source.closed and time.monotonic() < deadline:
        time.sleep(0.005)
    assert source.closed
    assert events.empty()


def test_operation_interlock_rejects_duplicate_clear_and_disconnect_is_nonblocking():
    release = threading.Event()
    calls = []
    events = queue.Queue()

    class Source:
        def clear_dtcs(self):
            calls.append("04")
            release.wait(1)

    class Controller:
        def stop(self):
            calls.append("stop")

    lifecycle = UILifecycle(events.put)
    source = Source()
    assert lifecycle.start_operation(source, "clear_dtcs", "cleared")
    deadline = time.monotonic() + 1
    while not calls and time.monotonic() < deadline:
        time.sleep(0.005)
    assert not lifecycle.start_operation(source, "clear_dtcs", "cleared")
    started = time.monotonic()
    lifecycle.disconnect(Controller())
    assert time.monotonic() - started < 0.2
    assert calls == ["04", "stop"]
    assert not lifecycle.start_operation(source, "clear_dtcs", "cleared")
    release.set()


def test_controller_terminal_events_require_disconnected_state():
    lifecycle = UILifecycle(lambda event: None)
    assert lifecycle.controller_event_is_terminal("error")
    assert lifecycle.controller_event_is_terminal("stopped")
    assert not lifecycle.controller_event_is_terminal("warning")
