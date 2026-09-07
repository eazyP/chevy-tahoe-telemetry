"""OBD-II domain definitions and pure response decoders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PIDDefinition:
    pid: int
    key: str
    label: str
    unit: str
    length: int
    decode: Callable[[bytes], float | str]
    decimals: int = 1


def _pct(data: bytes) -> float:
    return data[0] * 100.0 / 255.0


def _trim(data: bytes) -> float:
    return (data[0] - 128) * 100.0 / 128.0


FUEL_TYPES = {
    0: "Not available", 1: "Gasoline", 2: "Methanol", 3: "Ethanol",
    4: "Diesel", 5: "LPG", 6: "CNG", 7: "Propane", 8: "Electric",
    9: "Bifuel gasoline", 10: "Bifuel methanol", 11: "Bifuel ethanol",
    12: "Bifuel LPG", 13: "Bifuel CNG", 14: "Bifuel propane",
    15: "Bifuel electric", 16: "Bifuel electric/combustion",
    17: "Hybrid gasoline", 18: "Hybrid ethanol", 19: "Hybrid diesel",
    20: "Hybrid electric", 21: "Hybrid electric/combustion",
    22: "Hybrid regenerative", 23: "Bifuel diesel",
}


PID_DEFINITIONS = {
    d.pid: d for d in (
        PIDDefinition(0x04, "load", "Engine load", "%", 1, _pct),
        PIDDefinition(0x05, "coolant", "Coolant temperature", "°C", 1, lambda d: d[0] - 40, 0),
        PIDDefinition(0x06, "stft_b1", "Short fuel trim B1", "%", 1, _trim),
        PIDDefinition(0x07, "ltft_b1", "Long fuel trim B1", "%", 1, _trim),
        PIDDefinition(0x08, "stft_b2", "Short fuel trim B2", "%", 1, _trim),
        PIDDefinition(0x09, "ltft_b2", "Long fuel trim B2", "%", 1, _trim),
        PIDDefinition(0x0B, "map", "Intake manifold pressure", "kPa", 1, lambda d: float(d[0]), 0),
        PIDDefinition(0x0C, "rpm", "Engine RPM", "rpm", 2, lambda d: ((d[0] << 8) + d[1]) / 4.0, 0),
        PIDDefinition(0x0D, "speed", "Vehicle speed", "km/h", 1, lambda d: float(d[0]), 0),
        PIDDefinition(0x0F, "intake_temp", "Intake air temperature", "°C", 1, lambda d: d[0] - 40, 0),
        PIDDefinition(0x10, "maf", "Mass air flow", "g/s", 2, lambda d: ((d[0] << 8) + d[1]) / 100.0, 2),
        PIDDefinition(0x11, "throttle", "Throttle position", "%", 1, _pct),
        PIDDefinition(0x2F, "fuel_level", "Fuel level", "%", 1, _pct),
        PIDDefinition(0x42, "voltage", "Control module voltage", "V", 2, lambda d: ((d[0] << 8) + d[1]) / 1000.0, 2),
        PIDDefinition(0x51, "fuel_type", "Fuel type", "", 1, lambda d: FUEL_TYPES.get(d[0], f"Unknown ({d[0]})"), 0),
        PIDDefinition(0x52, "ethanol", "Ethanol percentage", "%", 1, _pct),
    )
}


def decode_pid(pid: int, data: bytes) -> float | str:
    definition = PID_DEFINITIONS.get(pid)
    if definition is None:
        raise ValueError(f"Unknown PID 0x{pid:02X}")
    if len(data) < definition.length:
        raise ValueError(f"PID 0x{pid:02X} requires {definition.length} data bytes")
    return definition.decode(data[: definition.length])


def parse_supported_pids(base_pid: int, bitmap: bytes) -> set[int]:
    if len(bitmap) != 4:
        raise ValueError("Supported PID bitmap must contain exactly 4 bytes")
    bits = int.from_bytes(bitmap, "big")
    return {base_pid + offset for offset in range(1, 33) if bits & (1 << (32 - offset))}


@dataclass(frozen=True)
class DTCRecord:
    code: str
    description: str


DTC_DESCRIPTIONS = {
    "P0101": "Mass or Volume Air Flow Circuit Range/Performance",
    "P0128": "Coolant Thermostat (Coolant Temperature Below Regulating Temperature)",
    "P0133": "O2 Sensor Circuit Slow Response (Bank 1 Sensor 1)",
    "P0171": "System Too Lean (Bank 1)",
    "P0172": "System Too Rich (Bank 1)",
    "P0174": "System Too Lean (Bank 2)",
    "P0175": "System Too Rich (Bank 2)",
    "P0300": "Random/Multiple Cylinder Misfire Detected",
    "P0420": "Catalyst System Efficiency Below Threshold (Bank 1)",
    "P0430": "Catalyst System Efficiency Below Threshold (Bank 2)",
    "P0442": "Evaporative Emission System Leak Detected (small leak)",
    "P0455": "Evaporative Emission System Leak Detected (gross leak)",
}


def decode_dtc_payload(data: bytes) -> list[DTCRecord]:
    systems = "PCBU"
    records: list[DTCRecord] = []
    for index in range(0, len(data) - 1, 2):
        first, second = data[index], data[index + 1]
        if first == second == 0:
            continue
        code = f"{systems[first >> 6]}{(first >> 4) & 3}{first & 0x0F:X}{second:02X}"
        records.append(DTCRecord(code, DTC_DESCRIPTIONS.get(code, "Unknown code")))
    return records
