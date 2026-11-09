"""Wire contract shared with Sources/PrintDockKit/HiPrintPacketizer.swift."""

from dataclasses import dataclass
from collections.abc import Iterator

SERVICE_UUID = "c3d1e0cb-9c4e-434e-a915-12097cd84f81"
WRITE_UUID = "c3d1e0cc-9c4e-434e-a915-12097cd84f81"
STATUS_UUID = "c3d1e0cd-9c4e-434e-a915-12097cd84f81"
IMAGE_SIZE = (640, 1024)
HEADER_TAIL = bytes.fromhex("00000001000000")
MAX_PAYLOAD = 0xFFFFFF
MAX_CHUNK = 200
FRAME_OVERHEAD = 5
STATUS_SIZE = 16
PRINTING_PHASES = {0x01, 0x02, 0x03, 0xFF}
PHASE_LABELS = {
    0x00: "initial/preparing",
    0x01: "layer 1",
    0x02: "layer 2",
    0x03: "layer 3",
    0x07: "ready",
    0xFF: "processing",
}


def packets(payload: bytes, chunk_size: int = MAX_CHUNK) -> Iterator[bytes]:
    if not 0 < len(payload) <= MAX_PAYLOAD:
        raise ValueError("Image payload must contain 1..16777215 bytes")
    if not 1 <= chunk_size <= MAX_CHUNK:
        raise ValueError("Chunk size must be 1..200 bytes")
    yield len(payload).to_bytes(3, "big") + HEADER_TAIL
    for offset in range(0, len(payload), chunk_size):
        chunk = payload[offset : offset + chunk_size]
        yield offset.to_bytes(3, "big") + bytes((0, len(chunk))) + chunk


@dataclass(frozen=True)
class PrinterStatus:
    raw: bytes

    def __post_init__(self) -> None:
        if len(self.raw) != STATUS_SIZE:
            raise ValueError(f"Unrecognized status length {len(self.raw)}: {self.raw.hex()}")

    @property
    def phase(self) -> int:
        return self.raw[2]

    @property
    def issue(self) -> int:
        return self.raw[3]

    @property
    def label(self) -> str:
        return PHASE_LABELS.get(self.phase, f"unknown phase 0x{self.phase:02x}")

    @property
    def ready(self) -> bool:
        return self.phase == 0x07 and self.issue == 0

    def require_startable(self, generation: int) -> None:
        if generation not in {1, 2}:
            raise ValueError("Generation must be 1 or 2")
        if self.issue:
            raise RuntimeError(f"Printer needs attention: issue 0x{self.issue:02x} ({self.raw.hex()})")
        # Gen 2 has phase 0x00 both at initial idle and during a print. The
        # recorded initial idle has byte 1 == 0; in-job preparing has it == 1.
        initial_idle = generation == 2 and self.phase == 0x00 and self.raw[1] == 0
        if not self.ready and not initial_idle:
            raise RuntimeError(f"Printer is not ready: {self.label} ({self.raw.hex()})")
