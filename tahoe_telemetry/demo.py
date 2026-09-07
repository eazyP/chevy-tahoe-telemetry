"""Deterministic, no-hardware telemetry source for demonstrations and testing."""

from __future__ import annotations

import math
import random

from .obd import DTCRecord, PID_DEFINITIONS


class DTCCommunicationError(RuntimeError):
    """One or more required diagnostic groups could not be read."""


class DemoSource:
    protocol = "DEMO — deterministic simulation"

    def __init__(self, seed: int = 2004):
        self._random = random.Random(seed)
        self._step = 0
        self.connected = False
        self._dtcs = {
            "Stored": [DTCRecord("P0171", "System Too Lean (Bank 1)")],
            "Pending": [DTCRecord("P0442", "Evaporative Emission System Leak Detected (small leak)")],
            "Permanent": [],
        }

    def connect(self) -> str:
        self.connected = True
        return self.protocol

    def close(self) -> None:
        self.connected = False

    def discover_supported_pids(self) -> set[int]:
        # Fuel type intentionally unavailable to exercise honest Unsupported UI.
        return set(PID_DEFINITIONS) - {0x51}

    def read_pid(self, pid: int) -> float | str | None:
        if pid not in self.discover_supported_pids():
            return None
        phase = self._step / 8.0
        self._step += 1
        wave = math.sin(phase)
        values: dict[int, float | str] = {
            0x04: 27 + 12 * wave, 0x05: 91 + 2 * wave,
            0x06: 1.5 + 2 * wave, 0x07: -1.0 + wave,
            0x08: 1.0 + 1.7 * wave, 0x09: -0.5 + 0.8 * wave,
            0x0B: 39 + 8 * wave, 0x0C: 680 + 420 * max(0, wave),
            0x0D: 35 + 25 * wave, 0x0F: 30 + 3 * wave,
            0x10: 5.1 + 8 * max(0, wave), 0x11: 18 + 12 * max(0, wave),
            0x2F: 68.0, 0x42: 14.1 + 0.15 * wave,
            0x52: 55.0,
        }
        value = values[pid]
        return round(value, 2) if isinstance(value, float) else value

    def read_dtcs(self) -> dict[str, list[DTCRecord]]:
        return {group: list(records) for group, records in self._dtcs.items()}

    def clear_dtcs(self) -> None:
        self._dtcs = {group: [] for group in self._dtcs}


class HardwareSource:
    """OBD service over an already-configured ELM transport."""

    def __init__(self, transport):
        self.transport = transport
        self.supported: set[int] = set()

    def connect(self, port: str, baudrate: int, protocol: str) -> str:
        return self.transport.connect(port, baudrate, protocol)

    def close(self) -> None:
        self.transport.close()

    def discover_supported_pids(self) -> set[int]:
        from .obd import parse_supported_pids
        supported: set[int] = set()
        base = 0
        while base <= 0xE0:
            frames = self.transport.query(f"01{base:02X}")
            responses = [f for f in frames if len(f) >= 6 and f[0] == 0x41 and f[1] == base]
            if not responses:
                break
            block: set[int] = set()
            for response in responses:
                block.update(parse_supported_pids(base, response[2:6]))
            supported.update(block)
            if base + 0x20 not in block:
                break
            base += 0x20
        self.supported = supported
        return supported

    def read_pid(self, pid: int):
        from .obd import decode_pid
        if pid not in self.supported:
            return None
        frames = self.transport.query(f"01{pid:02X}")
        response = next((f for f in frames if len(f) >= 3 and f[0] == 0x41 and f[1] == pid), None)
        if response is None:
            return None
        return decode_pid(pid, response[2:])

    def read_dtcs(self):
        from .obd import decode_dtc_payload
        groups = {"Stored": "03", "Pending": "07", "Permanent": "0A"}
        result = {}
        failures = []
        for label, mode in groups.items():
            expected = 0x40 + int(mode, 16)
            try:
                frames = self.transport.query(mode)
                payload = b"".join(frame[1:] for frame in frames if frame and frame[0] == expected)
                result[label] = decode_dtc_payload(payload)
            except Exception as error:
                if label == "Permanent" and "NO DATA" in str(error).upper():
                    result[label] = None
                else:
                    failures.append(f"{label}: {error}")
        if failures:
            raise DTCCommunicationError("DTC scan incomplete — " + "; ".join(failures))
        return result

    def clear_dtcs(self) -> None:
        frames = self.transport.query("04")
        if not any(frame == b"\x44" for frame in frames):
            raise RuntimeError("ECU did not acknowledge Mode 04 clear request.")
