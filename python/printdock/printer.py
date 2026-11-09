import asyncio
import logging
from collections.abc import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from .protocol import (
    FRAME_OVERHEAD,
    MAX_CHUNK,
    PRINTING_PHASES,
    SERVICE_UUID,
    STATUS_UUID,
    WRITE_UUID,
    PrinterStatus,
    packets,
)

logger = logging.getLogger(__name__)
POLL_SECONDS = 1


async def discover(timeout: float, prefix: str, address: str | None = None) -> list[BLEDevice]:
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    return [
        device
        for device, adv in found.values()
        if (
            device.address.casefold() == address.casefold()
            if address
            else prefix.casefold() in (adv.local_name or device.name or "").casefold()
            or SERVICE_UUID in adv.service_uuids
        )
    ]


async def select_device(timeout: float, prefix: str, address: str | None) -> BLEDevice:
    devices = await discover(timeout, prefix, address)
    if not devices:
        raise RuntimeError("No Hi-Print found. Wake the printer and disconnect the phone app, then try again.")
    if len(devices) > 1:
        raise RuntimeError("Multiple printers found; select one with --address: " + ", ".join(d.address for d in devices))
    return devices[0]


async def read_status(client: BleakClient) -> PrinterStatus:
    return PrinterStatus(bytes(await client.read_gatt_char(STATUS_UUID, use_cached=False)))


async def send_print(
    client: BleakClient,
    jpeg: bytes,
    *,
    generation: int = 2,
    pace_ms: int = 12,
    timeout: float = 180,
    progress: Callable[[int], None] = lambda percent: None,
) -> None:
    if pace_ms < 0 or timeout <= 0:
        raise ValueError("Pace must be nonnegative and timeout must be positive")
    write_char = client.services.get_characteristic(WRITE_UUID)
    if write_char is None or "write-without-response" not in write_char.properties:
        raise RuntimeError("Hi-Print write-without-response characteristic missing")
    chunk_size = min(MAX_CHUNK, write_char.max_write_without_response_size - FRAME_OVERHEAD)
    if chunk_size < 1:
        raise RuntimeError("Bluetooth write size is too small for Hi-Print frames")
    # Validate the full payload before making the first hardware write.
    transfer = list(packets(jpeg, chunk_size))
    status = await read_status(client)
    logger.info("Before print: %s %s", status.raw.hex(), status.label)
    status.require_startable(generation)
    logger.info("Sending %d JPEG bytes in %d packets (chunk %d, pace %d ms)", len(jpeg), len(transfer), chunk_size, pace_ms)
    last_status = status.raw
    saw_processing = False
    async with asyncio.timeout(timeout):
        last_poll = asyncio.get_running_loop().time()
        last_progress = -1
        for index, packet in enumerate(transfer):
            await client.write_gatt_char(write_char, packet, response=False)
            percent = (index + 1) * 100 // len(transfer)
            if percent // 10 != last_progress:
                last_progress = percent // 10
                progress(percent)
            if pace_ms:
                await asyncio.sleep(pace_ms / 1000)
            now = asyncio.get_running_loop().time()
            if now - last_poll >= POLL_SECONDS:
                status = await read_status(client)
                if status.raw != last_status:
                    logger.info("Status: %s %s", status.raw.hex(), status.label)
                    last_status = status.raw
                if status.issue:
                    raise RuntimeError(f"Printer issue 0x{status.issue:02x}; transfer stopped")
                saw_processing |= status.phase in PRINTING_PHASES
                last_poll = now
        logger.info("Upload complete; waiting for printer processing and return to ready")
        while True:
            status = await read_status(client)
            if status.raw != last_status:
                logger.info("Status: %s %s", status.raw.hex(), status.label)
                last_status = status.raw
            if status.issue:
                raise RuntimeError(f"Printer issue 0x{status.issue:02x} after upload ({status.raw.hex()})")
            saw_processing |= status.phase in PRINTING_PHASES
            if saw_processing and status.ready:
                return
            await asyncio.sleep(POLL_SECONDS)
