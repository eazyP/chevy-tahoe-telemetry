import pytest
import threading
import time

from tahoe_telemetry.transport import (
    ConnectionFailure,
    ELM327Transport,
    list_serial_ports,
    parse_obd_frames,
)


class FakeSerial:
    def __init__(self, responses=None, **kwargs):
        self.responses = list(responses or [])
        self.kwargs = kwargs
        self.writes = []
        self.is_open = True

    def reset_input_buffer(self):
        pass

    def write(self, data):
        self.writes.append(data)

    def read_until(self, marker):
        return self.responses.pop(0)

    def close(self):
        self.is_open = False


def test_parse_obd_frames_removes_echo_noise_and_headers():
    raw = "01 0C\rSEARCHING...\r41 0C 1A F8\r>"
    assert parse_obd_frames(raw, "010C") == [bytes.fromhex("410C1AF8")]


def test_parse_obd_frames_accepts_compact_can_header_line():
    assert parse_obd_frames("7E804410C1AF8\r>", "010C") == [bytes.fromhex("410C1AF8")]


def test_parse_obd_frames_accepts_29_bit_can_header_line():
    raw = "18DAF110 04 41 0C 1A F8\r>"
    assert parse_obd_frames(raw, "010C") == [bytes.fromhex("410C1AF8")]


def test_transport_initializes_auto_and_reports_protocol():
    fake = FakeSerial([
        b"ELM327 v1.5\r>", b"OK\r>", b"OK\r>", b"OK\r>",
        b"OK\r>", b"AUTO, SAE J1850 VPW\r>",
    ])
    transport = ELM327Transport(serial_factory=lambda **kw: fake)
    protocol = transport.connect("COM7", 38400, protocol="AUTO")
    assert protocol == "AUTO, SAE J1850 VPW"
    assert fake.writes == [b"ATZ\r", b"ATE0\r", b"ATL0\r", b"ATS0\r", b"ATSP0\r", b"ATDP\r"]


def test_transport_uses_vpw_fallback_command():
    fake = FakeSerial([b"ELM327\r>", b"OK\r>", b"OK\r>", b"OK\r>", b"OK\r>", b"SAE J1850 VPW\r>"])
    ELM327Transport(serial_factory=lambda **kw: fake).connect("COM2", 9600, protocol="VPW")
    assert b"ATSP2\r" in fake.writes


def test_connection_errors_are_exact():
    def denied(**kwargs):
        raise PermissionError("denied")

    with pytest.raises(ConnectionFailure) as exc:
        ELM327Transport(serial_factory=denied).connect("COM4", 38400)
    assert str(exc.value) == "Could not open COM4: access denied. Close other diagnostic software and try again."


def test_no_prompt_is_exact_timeout_error():
    fake = FakeSerial([b""])
    with pytest.raises(ConnectionFailure) as exc:
        ELM327Transport(serial_factory=lambda **kw: fake).connect("COM4", 38400)
    assert str(exc.value) == "ELM327 did not respond on COM4. Check power, USB connection, COM port, and baud rate."


def test_query_raises_on_adapter_error():
    fake = FakeSerial([b"NO DATA\r>"])
    transport = ELM327Transport(serial_factory=lambda **kw: fake)
    transport._serial = fake
    with pytest.raises(ConnectionFailure, match="Vehicle returned NO DATA"):
        transport.query("010C")


def test_port_enumeration_is_sorted(monkeypatch):
    class Port:
        def __init__(self, device, description):
            self.device, self.description = device, description

    monkeypatch.setattr("tahoe_telemetry.transport.comports", lambda: [Port("COM9", "B"), Port("COM2", "A")])
    assert list_serial_ports() == [("COM2", "A"), ("COM9", "B")]


def test_close_waits_for_in_flight_command_io():
    entered = threading.Event()
    release = threading.Event()

    class BlockingSerial(FakeSerial):
        def read_until(self, marker):
            entered.set()
            release.wait(1)
            return b"41 0C 1A F8\r>"

    fake = BlockingSerial()
    transport = ELM327Transport()
    transport._serial = fake
    command_thread = threading.Thread(target=transport.command, args=("010C",))
    command_thread.start()
    assert entered.wait(1)
    close_thread = threading.Thread(target=transport.close)
    close_thread.start()
    time.sleep(0.02)
    assert close_thread.is_alive()
    assert fake.is_open
    release.set()
    command_thread.join(1)
    close_thread.join(1)
    assert not fake.is_open
