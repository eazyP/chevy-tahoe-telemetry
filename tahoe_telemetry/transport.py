"""Thread-safe serial transport for ELM327-compatible adapters."""

from __future__ import annotations

import re
import threading
import time
from typing import Callable

import serial
from serial.tools.list_ports import comports


class ConnectionFailure(RuntimeError):
    """A user-actionable adapter or vehicle communication error."""


def list_serial_ports() -> list[tuple[str, str]]:
    return sorted(((port.device, port.description or "Serial port") for port in comports()), key=lambda item: item[0])


def _clean_lines(raw: str, command: str) -> list[str]:
    command = re.sub(r"\s+", "", command).upper()
    lines = []
    for line in raw.replace(">", "").splitlines():
        value = line.strip().upper()
        compact = re.sub(r"\s+", "", value)
        if not value or compact == command or value.startswith("SEARCHING"):
            continue
        lines.append(value)
    return lines


def parse_obd_frames(raw: str, command: str = "") -> list[bytes]:
    frames: list[bytes] = []
    for line in _clean_lines(raw, command):
        compact = re.sub(r"[^0-9A-F]", "", line)
        # Common 11-bit CAN header plus DLC: 7E8 04 41 0C 1A F8.
        if len(compact) >= 10 and compact[:3] in {f"7E{x:X}" for x in range(8, 16)}:
            compact = compact[5:]
        # Common ISO 15765-4 29-bit response header plus DLC.
        elif len(compact) >= 12 and re.fullmatch(r"18D[AB][0-9A-F]{4}", compact[:8]):
            compact = compact[10:]
        if len(compact) % 2 or len(compact) < 2:
            continue
        try:
            frames.append(bytes.fromhex(compact))
        except ValueError:
            continue
    return frames


class ELM327Transport:
    def __init__(self, serial_factory: Callable[..., object] = serial.Serial, timeout: float = 2.0):
        self._serial_factory = serial_factory
        self._timeout = timeout
        self._serial = None
        self._lock = threading.Lock()
        self.port = ""
        self.protocol = ""

    @property
    def connected(self) -> bool:
        return bool(self._serial and getattr(self._serial, "is_open", True))

    def connect(self, port: str, baudrate: int, protocol: str = "AUTO") -> str:
        self.close()
        self.port = port
        try:
            self._serial = self._serial_factory(
                port=port, baudrate=baudrate, timeout=self._timeout, write_timeout=self._timeout,
            )
        except PermissionError as error:
            raise ConnectionFailure(
                f"Could not open {port}: access denied. Close other diagnostic software and try again."
            ) from error
        except (serial.SerialException, OSError) as error:
            raise ConnectionFailure(f"Could not open {port}: {error}") from error

        try:
            self.command("ATZ", pause=0.05)
            for command in ("ATE0", "ATL0", "ATS0"):
                self.command(command)
            self.command("ATSP2" if protocol.upper() == "VPW" else "ATSP0")
            detected = self.command("ATDP")
        except TimeoutError as error:
            self.close()
            raise ConnectionFailure(
                f"ELM327 did not respond on {port}. Check power, USB connection, COM port, and baud rate."
            ) from error
        self.protocol = detected[0] if detected else "Unknown protocol"
        return self.protocol

    def command(self, command: str, pause: float = 0.0) -> list[str]:
        with self._lock:
            if not self._serial:
                raise ConnectionFailure("Not connected to an ELM327 adapter.")
            self._serial.reset_input_buffer()
            self._serial.write((command.strip() + "\r").encode("ascii"))
            if pause:
                time.sleep(pause)
            raw = self._serial.read_until(b">")
        if not raw or b">" not in raw:
            raise TimeoutError("ELM327 prompt not received")
        return _clean_lines(raw.decode("ascii", errors="replace"), command)

    def query(self, command: str) -> list[bytes]:
        try:
            lines = self.command(command)
        except TimeoutError as error:
            raise ConnectionFailure("ELM327 response timed out.") from error
        joined = " ".join(lines)
        for marker in ("NO DATA", "UNABLE TO CONNECT", "BUS ERROR", "STOPPED", "?"):
            if marker in joined:
                raise ConnectionFailure(f"Vehicle returned {marker} for command {command}.")
        frames = parse_obd_frames("\r".join(lines), command)
        if not frames:
            raise ConnectionFailure(f"No valid OBD-II response for command {command}.")
        return frames

    def close(self) -> None:
        with self._lock:
            if self._serial:
                try:
                    self._serial.close()
                finally:
                    self._serial = None
