import pytest

from tahoe_telemetry.demo import DTCCommunicationError, HardwareSource
from tahoe_telemetry.transport import ConnectionFailure, ELM327Transport


class FakeTransport:
    def __init__(self):
        self.commands = []

    def query(self, command):
        self.commands.append(command)
        if command == "0100":
            # ECU A supports PID 0C; ECU B supports 0D and continuation PID 20.
            return [bytes.fromhex("410000100000"), bytes.fromhex("410000080001")]
        if command == "0120":
            return [bytes.fromhex("412000000000")]
        if command == "010C":
            return [bytes.fromhex("410C1AF8")]
        if command == "03":
            return [bytes.fromhex("430133")]
        if command in ("07", "0A"):
            return [bytes([0x40 + int(command, 16), 0, 0])]
        if command == "04":
            return [bytes.fromhex("44")]
        raise AssertionError(command)

    def close(self):
        pass


def test_supported_pid_discovery_unions_ecu_responses_and_follows_continuation():
    transport = FakeTransport()
    source = HardwareSource(transport)
    assert source.discover_supported_pids() == {0x0C, 0x0D, 0x20}
    assert transport.commands == ["0100", "0120"]
    assert source.read_pid(0x0C) == 1726.0


def test_hardware_dtc_modes_and_clear_command():
    transport = FakeTransport()
    source = HardwareSource(transport)
    groups = source.read_dtcs()
    assert groups["Stored"][0].code == "P0133"
    assert groups["Pending"] == groups["Permanent"] == []
    source.clear_dtcs()
    assert transport.commands == ["03", "07", "0A", "04"]


def test_mode_04_one_byte_elm_response_reaches_hardware_clear():
    class Serial:
        is_open = True

        def reset_input_buffer(self):
            pass

        def write(self, data):
            assert data == b"04\r"

        def read_until(self, marker):
            return b"04\r44\r>"

        def close(self):
            self.is_open = False

    transport = ELM327Transport()
    transport._serial = Serial()
    HardwareSource(transport).clear_dtcs()


def test_dtc_link_failures_raise_aggregated_error_instead_of_clean_groups():
    class FailingTransport(FakeTransport):
        def query(self, command):
            if command in ("03", "07"):
                raise ConnectionFailure(f"link down for {command}")
            return super().query(command)

    with pytest.raises(DTCCommunicationError) as exc:
        HardwareSource(FailingTransport()).read_dtcs()
    assert "Stored: link down for 03" in str(exc.value)
    assert "Pending: link down for 07" in str(exc.value)


def test_unsupported_permanent_dtcs_are_unavailable_not_clean():
    class NoPermanentTransport(FakeTransport):
        def query(self, command):
            if command == "0A":
                raise ConnectionFailure("Vehicle returned NO DATA for command 0A.")
            return super().query(command)

    groups = HardwareSource(NoPermanentTransport()).read_dtcs()
    assert groups["Stored"][0].code == "P0133"
    assert groups["Pending"] == []
    assert groups["Permanent"] is None
