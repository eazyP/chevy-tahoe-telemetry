"""Threaded polling controller; it never calls Tk from a worker thread."""

from __future__ import annotations

import queue
import threading
from collections import defaultdict, deque

from .obd import PID_DEFINITIONS


def validate_clear_request(typed: str, confirmed: bool) -> None:
    if typed != "CLEAR":
        raise ValueError("Type CLEAR exactly to enable diagnostic trouble code clearing.")
    if not confirmed:
        raise ValueError("Clearing cancelled; no command was sent.")


class TelemetryController:
    def __init__(self, source, poll_interval: float = 0.5, history_size: int = 120):
        self.source = source
        self.poll_interval = max(0.05, poll_interval)
        self.history_size = history_size
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.values: dict[str, object] = {}
        self.history = defaultdict(lambda: deque(maxlen=self.history_size))
        self.supported: set[int] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.logger = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="OBD-Polling", daemon=True)
        self._thread.start()

    def _poll_loop(self) -> None:
        try:
            self.supported = self.source.discover_supported_pids()
            self.events.put(("supported", set(self.supported)))
            while not self._stop.is_set():
                sample = {}
                for pid, definition in PID_DEFINITIONS.items():
                    if self._stop.is_set():
                        break
                    if pid not in self.supported:
                        sample[definition.key] = None
                        continue
                    try:
                        sample[definition.key] = self.source.read_pid(pid)
                    except Exception as error:
                        sample[definition.key] = None
                        self.events.put(("warning", f"{definition.label}: {error}"))
                if sample:
                    self.events.put(("sample", sample))
                self._stop.wait(self.poll_interval)
        except Exception as error:
            self.events.put(("error", str(error)))
        finally:
            self.source.close()
            self.events.put(("stopped", None))
            self._thread = None

    def apply_sample(self, sample: dict[str, object]) -> None:
        self.values.update(sample)
        for key, value in sample.items():
            if isinstance(value, (int, float)):
                self.history[key].append(float(value))
        if self.logger:
            self.logger.write(sample)

    def set_logger(self, logger) -> None:
        if self.logger:
            self.logger.close()
        self.logger = logger

    def stop_logging(self) -> None:
        if self.logger:
            self.logger.close()
            self.logger = None

    def stop(self) -> None:
        self._stop.set()
        self.stop_logging()
        if not self._thread:
            self.source.close()
