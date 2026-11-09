import asyncio
from types import SimpleNamespace

import pytest

from printdock.printer import send_print
from printdock.protocol import STATUS_UUID, WRITE_UUID

INITIAL = bytes.fromhex("0200000008ca00120319000005000000")
READY = bytes.fromhex("02000700089800260315010105000000")
PROCESSING = bytes.fromhex("0201ff00086600150315000105000000")
FAULT = bytes.fromhex("02000709089800280315000105000000")


class GattTransport:
    """Script the external BLE boundary; use the real packetizer and state machine."""

    def __init__(self, statuses, max_write_size=509):
        self.statuses = iter(statuses)
        self.writes = []
        self.characteristic = SimpleNamespace(
            uuid=WRITE_UUID,
            properties=["write-without-response"],
            max_write_without_response_size=max_write_size,
        )
        self.services = SimpleNamespace(get_characteristic=lambda uuid: self.characteristic if uuid == WRITE_UUID else None)

    async def read_gatt_char(self, uuid, *, use_cached):
        assert uuid == STATUS_UUID
        assert use_cached is False
        raw = next(self.statuses, None)
        if raw is None:
            raise TimeoutError("No further printer status")
        return raw

    async def write_gatt_char(self, characteristic, packet, *, response):
        assert characteristic.uuid == WRITE_UUID
        assert response is False
        self.writes.append(packet)


@pytest.fixture(autouse=True)
def no_poll_delay(monkeypatch):
    async def yield_control(seconds):
        return None
    monkeypatch.setattr("printdock.printer.asyncio.sleep", yield_control)


def test_completion_requires_processing_then_fresh_ready():
    transport = GattTransport([INITIAL, READY, PROCESSING, READY])
    asyncio.run(send_print(transport, b"jpeg", pace_ms=0))
    assert transport.writes == [bytes.fromhex("00000400000001000000"), bytes.fromhex("0000000004") + b"jpeg"]


def test_upload_followed_only_by_ready_is_not_a_completed_print():
    transport = GattTransport([READY, READY, READY])
    with pytest.raises(TimeoutError):
        asyncio.run(send_print(transport, b"jpeg", pace_ms=0))


def test_fault_before_print_prevents_all_writes():
    transport = GattTransport([FAULT])
    with pytest.raises(RuntimeError, match="attention"):
        asyncio.run(send_print(transport, b"jpeg", pace_ms=0))
    assert transport.writes == []


def test_post_upload_fault_fails_instead_of_reporting_success():
    transport = GattTransport([INITIAL, PROCESSING, FAULT])
    with pytest.raises(RuntimeError, match="0x09"):
        asyncio.run(send_print(transport, b"jpeg", pace_ms=0))


def test_invalid_payload_is_rejected_before_any_hardware_write():
    transport = GattTransport([READY])
    with pytest.raises(ValueError):
        asyncio.run(send_print(transport, b"", pace_ms=0))
    assert transport.writes == []


def test_negotiated_write_size_limits_each_hardware_packet():
    transport = GattTransport([READY, PROCESSING, READY], max_write_size=20)
    asyncio.run(send_print(transport, bytes(31), pace_ms=0))
    assert [len(packet) for packet in transport.writes] == [10, 20, 20, 6]


def test_fault_during_upload_stops_remaining_packets(monkeypatch):
    monkeypatch.setattr("printdock.printer.POLL_SECONDS", 0)
    transport = GattTransport([READY, FAULT])
    with pytest.raises(RuntimeError, match="transfer stopped"):
        asyncio.run(send_print(transport, bytes(450), pace_ms=0))
    assert len(transport.writes) == 1


def test_stalled_post_transfer_read_is_cancelled_by_print_deadline():
    class StalledTransport(GattTransport):
        async def read_gatt_char(self, uuid, *, use_cached):
            if not self.writes:
                return READY
            await asyncio.Event().wait()

    transport = StalledTransport([])
    with pytest.raises(TimeoutError):
        asyncio.run(send_print(transport, b"jpeg", pace_ms=0, timeout=0.01))
