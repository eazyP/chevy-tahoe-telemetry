import pytest

from tahoe_telemetry.obd import (
    PID_DEFINITIONS,
    decode_dtc_payload,
    decode_pid,
    parse_supported_pids,
)


@pytest.mark.parametrize(
    ("pid", "data", "expected"),
    [
        (0x0C, bytes([0x1A, 0xF8]), 1726.0),
        (0x0D, bytes([88]), 88.0),
        (0x05, bytes([100]), 60.0),
        (0x04, bytes([128]), pytest.approx(50.196, abs=0.001)),
        (0x11, bytes([64]), pytest.approx(25.098, abs=0.001)),
        (0x10, bytes([1, 244]), 5.0),
        (0x0F, bytes([70]), 30.0),
        (0x42, bytes([0x36, 0xB0]), 14.0),
        (0x06, bytes([140]), pytest.approx(9.375, abs=0.001)),
        (0x07, bytes([116]), pytest.approx(-9.375, abs=0.001)),
        (0x2F, bytes([128]), pytest.approx(50.196, abs=0.001)),
        (0x52, bytes([128]), pytest.approx(50.196, abs=0.001)),
    ],
)
def test_decode_pid(pid, data, expected):
    assert decode_pid(pid, data) == expected


def test_fuel_type_text_and_unknown_pid():
    expected_fuel_types = [
        "Not available",
        "Gasoline",
        "Methanol",
        "Ethanol",
        "Diesel",
        "LPG",
        "CNG",
        "Propane",
        "Electric",
        "Bifuel gasoline",
        "Bifuel methanol",
        "Bifuel ethanol",
        "Bifuel LPG",
        "Bifuel CNG",
        "Bifuel propane",
        "Bifuel electric",
        "Bifuel electric/combustion",
        "Hybrid gasoline",
        "Hybrid ethanol",
        "Hybrid diesel",
        "Hybrid electric",
        "Hybrid electric/combustion",
        "Hybrid regenerative",
        "Bifuel diesel",
    ]
    assert [decode_pid(0x51, bytes([value])) for value in range(24)] == expected_fuel_types
    with pytest.raises(ValueError, match="Unknown PID"):
        decode_pid(0x99, b"\x00")


def test_pid_definitions_cover_requested_values():
    assert set(PID_DEFINITIONS) == {
        0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0B, 0x0C, 0x0D, 0x0F,
        0x10, 0x11, 0x2F, 0x42, 0x51, 0x52,
    }


def test_parse_supported_pid_bitmap_uses_msb_for_first_pid():
    # 41 00 80 18 00 01 => PIDs 01, 0C, 0D, 20 supported.
    assert parse_supported_pids(0x00, bytes.fromhex("80180001")) == {1, 12, 13, 32}


def test_decode_dtcs_preserves_unknown_codes_and_skips_zero_padding():
    payload = bytes.fromhex("013301710000C123")
    records = decode_dtc_payload(payload)
    assert [(r.code, r.description) for r in records] == [
        ("P0133", "O2 Sensor Circuit Slow Response (Bank 1 Sensor 1)"),
        ("P0171", "System Too Lean (Bank 1)"),
        ("U0123", "Unknown code"),
    ]


def test_decode_pid_rejects_short_payload():
    with pytest.raises(ValueError, match="requires 2 data bytes"):
        decode_pid(0x0C, b"\x12")
