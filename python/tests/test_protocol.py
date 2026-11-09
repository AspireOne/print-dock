import pytest

from printdock.protocol import PrinterStatus, packets


def test_packet_bytes_match_gen1_wire_contract():
    frames = list(packets(bytes([0xAB]) * 450))
    assert frames[0] == bytes.fromhex("0001c200000001000000")
    assert frames[1] == bytes.fromhex("00000000c8") + bytes([0xAB]) * 200
    assert frames[2] == bytes.fromhex("0000c800c8") + bytes([0xAB]) * 200
    assert frames[3] == bytes.fromhex("0001900032") + bytes([0xAB]) * 50


def test_small_mtu_preserves_offsets_and_final_partial_frame():
    frames = list(packets(bytes(31), chunk_size=15))
    assert [frame[:5].hex() for frame in frames[1:]] == [
        "000000000f", "00000f000f", "00001e0001",
    ]


@pytest.mark.parametrize("payload,chunk_size", [(b"", 200), (b"a", 0), (b"a", 201)])
def test_invalid_transfer_is_rejected_before_header(payload, chunk_size):
    with pytest.raises(ValueError):
        next(packets(payload, chunk_size))


def test_recorded_gen2_initial_status_is_not_claimed_as_completed_print():
    status = PrinterStatus(bytes.fromhex("0200000008ca00120319000005000000"))
    assert not status.ready
    status.require_startable(generation=2)
    with pytest.raises(RuntimeError, match="not ready"):
        status.require_startable(generation=1)


def test_recorded_ready_status_and_fault_share_phase_but_not_readiness():
    ready = PrinterStatus(bytes.fromhex("02000700089800260315010105000000"))
    fault = PrinterStatus(bytes.fromhex("02000709089800280315000105000000"))
    assert ready.ready
    assert not fault.ready
    with pytest.raises(RuntimeError, match="0x09"):
        fault.require_startable(generation=2)


def test_recorded_gen2_in_job_preparing_rejects_another_print():
    status = PrinterStatus(bytes.fromhex("0201000008ca00190319000105000000"))
    with pytest.raises(RuntimeError, match="not ready"):
        status.require_startable(generation=2)


@pytest.mark.parametrize("raw", [b"", bytes(3), bytes(15), bytes(17)])
def test_unrecognized_status_fails_instead_of_claiming_ready(raw):
    with pytest.raises(ValueError, match="status length"):
        PrinterStatus(raw)
