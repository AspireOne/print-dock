import argparse
import asyncio
import json
import logging
import math
import sys
from pathlib import Path

from bleak import BleakClient

from .imaging import printable_jpeg
from .printer import discover, read_status, select_device, send_print
from .protocol import IMAGE_SIZE, SERVICE_UUID, STATUS_UUID


def positive_seconds(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Must be a finite positive number")
    return number


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Print Dock Bluetooth CLI")
    commands = root.add_subparsers(dest="command", required=True)
    connection = argparse.ArgumentParser(add_help=False)
    connection.add_argument("--address", help="Bluetooth address (macOS: peripheral UUID)")
    connection.add_argument("--prefix", default="Hi-Print")
    connection.add_argument("--timeout", type=positive_seconds, default=12, help="Scan/connect timeout in seconds")
    image = argparse.ArgumentParser(add_help=False)
    image.add_argument("image", type=Path)
    image.add_argument("--fit", choices=("cover", "contain"), default="cover", help="Cover crops centrally; contain adds white margins")
    image.add_argument("--orientation", choices=("auto", "portrait", "landscape"), default="auto", help="Auto fits landscape photos across the long edge")
    image.add_argument("--quality", type=int, choices=range(1, 101), metavar="1..100", default=98)
    commands.add_parser("scan", parents=[connection], help="List visible Hi-Print printers")
    commands.add_parser("inspect", parents=[connection], help="Read GATT services and raw status; no print writes")
    status = commands.add_parser("status", parents=[connection], help="Read raw and decoded printer status")
    status.add_argument("--generation", type=int, choices=(1, 2), default=2)
    prepare = commands.add_parser("prepare", parents=[image], help="Save a printable JPEG for review without Bluetooth")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--edit", action="store_true", help="Choose the crop in the GUI before saving")
    send = commands.add_parser("print", parents=[connection, image], help="Send one image and verify printer completion")
    send.add_argument("--generation", type=int, choices=(1, 2), default=2)
    send.add_argument("--no-edit", action="store_true", help="Skip the crop GUI and use automatic fitting (for scripts)")
    send.add_argument("--pace", type=int, default=12, help="Milliseconds between packets")
    send.add_argument("--print-timeout", type=positive_seconds, default=180, help="Total upload/processing deadline in seconds")
    return root


async def run(args: argparse.Namespace) -> None:
    jpeg = None
    if args.command in {"prepare", "print"}:
        if args.command == "prepare" and args.output.resolve() == args.image.resolve():
            raise ValueError("Choose an output path different from the source image")
        if args.command == "print" and args.pace < 0:
            raise ValueError("Pace must be nonnegative")
        interactive = args.command == "print" and not args.no_edit or args.command == "prepare" and args.edit
        if interactive:
            try:
                from .editor import edit_jpeg
            except ImportError as error:
                raise RuntimeError("The crop editor needs Python with Tk support. Install Tk, or use print --no-edit for automatic fitting.") from error
            jpeg = edit_jpeg(args.image, fit=args.fit, quality=args.quality, orientation=args.orientation,
                             action="Print" if args.command == "print" else "Save preview")
            if jpeg is None:
                print("CANCELLED")
                return
        else:
            jpeg = printable_jpeg(args.image, fit=args.fit, quality=args.quality, orientation=args.orientation)
        if args.command == "prepare":
            args.output.write_bytes(jpeg)
            print(f"PREPARED {args.output} {IMAGE_SIZE[0]}x{IMAGE_SIZE[1]} {len(jpeg)} bytes")
            return
    if args.command == "scan":
        devices = await discover(args.timeout, args.prefix, args.address)
        if not devices:
            raise RuntimeError("No Hi-Print found. Wake the printer and disconnect the phone app, then try again.")
        for device in devices:
            print(f"FOUND {device.address} {device.name}")
        return
    device = await select_device(args.timeout, args.prefix, args.address)
    logging.info("Connecting to %s %s", device.name, device.address)
    async with BleakClient(device, timeout=args.timeout, winrt={"use_cached_services": False}) as client:
        service = client.services.get_service(SERVICE_UUID)
        if service is None:
            raise RuntimeError("Hi-Print service missing; this device does not match the known protocol")
        if args.command == "inspect":
            status = await read_status(client) if client.services.get_characteristic(STATUS_UUID) else None
            print(json.dumps({
                "name": device.name,
                "address": device.address,
                "mtu": client.mtu_size,
                "status": status.raw.hex() if status else None,
                "services": [
                    {"uuid": s.uuid, "characteristics": [
                        {"uuid": c.uuid, "properties": c.properties, "max_write_without_response_size": c.max_write_without_response_size}
                        for c in s.characteristics
                    ]} for s in client.services
                ],
            }, indent=2))
        elif args.command == "status":
            status = await read_status(client)
            print(f"STATUS {status.raw.hex()}")
            print(f"PHASE 0x{status.phase:02x} {status.label}")
            print(f"ISSUE 0x{status.issue:02x}")
            print(f"READY {str(status.ready).lower()}")
            try:
                status.require_startable(args.generation)
            except RuntimeError:
                print("STARTABLE false")
            else:
                print("STARTABLE true")
        else:
            try:
                await send_print(
                    client, jpeg, generation=args.generation, pace_ms=args.pace,
                    timeout=args.print_timeout,
                    progress=lambda percent: print(f"PROGRESS {percent}%", flush=True),
                )
            except BaseException:
                logging.error("Check the printer before retrying; it may have received part or all of the job.")
                raise
            print("PRINT_DONE", flush=True)


def main() -> None:
    args = parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Interrupted; check printer status before sending another job.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        detail = "Timed out before verified completion" if isinstance(error, TimeoutError) else str(error) or type(error).__name__
        print(f"ERROR {detail}", file=sys.stderr)
        raise SystemExit(1)
