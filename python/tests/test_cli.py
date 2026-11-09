import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest
from PIL import Image

from printdock import cli
from printdock.crop import Crop
from printdock.imaging import encode_crop
from printdock.protocol import SERVICE_UUID


def install_editor_boundary(monkeypatch, choose):
    editor = ModuleType("printdock.editor")
    editor.edit_jpeg = choose
    monkeypatch.setitem(sys.modules, "printdock.editor", editor)


def forbid_bluetooth(monkeypatch):
    async def unexpected_discovery(*args, **kwargs):
        pytest.fail("Bluetooth discovery must not run before crop approval")
    monkeypatch.setattr("printdock.printer.BleakScanner.discover", unexpected_discovery)


def test_cancelling_default_print_never_discovers_or_prints(monkeypatch, capsys):
    install_editor_boundary(monkeypatch, lambda *args, **kwargs: None)
    forbid_bluetooth(monkeypatch)
    asyncio.run(cli.run(cli.parser().parse_args(["print", "photo.jpg"])))
    assert capsys.readouterr().out == "CANCELLED\n"


def test_editor_failure_never_falls_back_to_automatic_printing(monkeypatch):
    def failed_editor(*args, **kwargs):
        raise RuntimeError("Editor failed")
    install_editor_boundary(monkeypatch, failed_editor)
    forbid_bluetooth(monkeypatch)
    with pytest.raises(RuntimeError, match="Editor failed"):
        asyncio.run(cli.run(cli.parser().parse_args(["print", "photo.jpg"])))


def test_preparation_saves_exact_approved_jpeg_without_recropping(monkeypatch, tmp_path):
    image = Image.new("RGB", (1280, 1024), "red")
    image.paste("blue", (640, 0, 1280, 1024))
    approved = encode_crop(image, Crop(image.size, center=(0.25, 0.5)))
    install_editor_boundary(monkeypatch, lambda *args, **kwargs: approved)
    forbid_bluetooth(monkeypatch)
    output = tmp_path / "selected.jpg"
    asyncio.run(cli.run(cli.parser().parse_args(["prepare", "photo.png", "--edit", "--output", str(output)])))
    assert output.read_bytes() == approved


def test_default_print_transports_exact_approved_jpeg(monkeypatch, capsys):
    approved = encode_crop(Image.new("RGB", (1280, 1024), "red"), Crop((1280, 1024), center=(0.25, 0.5)))
    install_editor_boundary(monkeypatch, lambda *args, **kwargs: approved)
    device = SimpleNamespace(address="test", name="Hi-Print test")
    advertisement = SimpleNamespace(local_name=device.name, service_uuids=[SERVICE_UUID])
    written = []
    statuses = iter([
        bytes.fromhex("0200000008ca00120319000005000000"),
        bytes.fromhex("0201ff0008ca00120319000105000000"),
        bytes.fromhex("0201070008ca00250319010105000000"),
    ])

    async def scan(**kwargs):
        return {device.address: (device, advertisement)}

    class BluetoothConnection:
        def __init__(self, selected, **kwargs):
            assert selected is device
            char = SimpleNamespace(properties=["write-without-response"], max_write_without_response_size=509)
            self.services = SimpleNamespace(get_service=lambda uuid: object(), get_characteristic=lambda uuid: char)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def read_gatt_char(self, *args, **kwargs):
            return next(statuses)

        async def write_gatt_char(self, char, packet, *, response):
            written.append(packet)

    async def no_delay(seconds):
        pass

    monkeypatch.setattr("printdock.printer.BleakScanner.discover", scan)
    monkeypatch.setattr("printdock.printer.BleakClient", BluetoothConnection)
    monkeypatch.setattr("printdock.printer.asyncio.sleep", no_delay)
    asyncio.run(cli.run(cli.parser().parse_args(["print", "photo.png", "--pace", "0"])))
    assert b"".join(frame[5:] for frame in written[1:]) == approved
    assert capsys.readouterr().out.endswith("PRINT_DONE\n")
