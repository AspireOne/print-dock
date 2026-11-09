# Print Dock

Print Dock provides Bluetooth printing for the Polaroid Hi·Print 2×3, with a native macOS app and Windows CLI and File Explorer integration.

## What this fork adds

This fork extends [petergpt/print-dock](https://github.com/petergpt/print-dock), the original macOS implementation for Hi-Print Gen 1, with:

- **Windows 11 and Hi-Print Gen 2 support**, verified with a real print over Bluetooth without a phone or ADB.
- An interactive crop editor with positioning, zoom, orientation controls, and a preview of the JPEG sent to the printer.
- A **Print using Hi-Print** image context-menu entry in Windows File Explorer, with print progress and error dialogs.

See [CLI and Explorer usage](docs/cli.md) to get started, and [connectivity](docs/connectivity.md) for the Gen 2 validation evidence and remaining protocol unknowns.

## Platform and printer support

| Implementation | Platform | Printer support |
| --- | --- | --- |
| Native Swift app, CLI, and PrintDockKit | macOS | Original Gen 1 implementation; Gen 2 has not been hardware-tested on macOS |
| Python CLI, crop editor, and Explorer launcher | Windows 11 | Gen 2 printing verified; Gen 1 hardware has not been tested with this client |

The Python Bluetooth backend also supports macOS and Linux, but this fork has not verified printing on those platforms. The native SwiftUI app remains macOS-only.

## Choose your path

This repo is intentionally split so each module can be used independently.

### 1) Connectivity only (library + CLI)
Use **PrintDockKit** on macOS, or the **Python CLI** on Windows, to discover/connect to the printer and send print jobs.

- Docs: [Connectivity](docs/connectivity.md)
- Native Swift technical handoff: [Deep dive](docs/agent-connectivity-deep-dive.md)
- API entry point: `PrintDockKit/HiPrintBLEClient`
- CLI and Windows Explorer docs: [Usage](docs/cli.md)

### 2) Full macOS app (Print Dock)

A native SwiftUI app built on top of PrintDockKit. On Windows, use the Python CLI or Explorer launcher above.

- Docs: `docs/app.md`
- Build/Package: `scripts/package_app.sh`

### 3) Surprise Print skill
An end-to-end “news to image to print” workflow script that can call `printdock` safely with readiness checks.

- Module docs: `skills/surprise-print/README.md`

## Repository layout

- `Sources/PrintDockKit` — BLE client, packetizer, image pipeline
- `Sources/PrintDockApp` — SwiftUI app
- `Sources/PrintDockCLI` — command-line tool
- `python/printdock` — portable Bluetooth CLI
- `python/tests` — portable CLI tests
- `skills/surprise-print` — optional surprise-print workflow
- `Tests/PrintDockKitTests` — unit tests
- `scripts/` — packaging + validation
- `assets/` — icon source + generated assets

## Quick start

### Use the CLI on Windows

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from this checkout:

```powershell
uv sync
uv run printdock scan
uv run printdock status
uv run printdock print "C:\Photos\photo.jpg"
```

To make `printdock` available outside this checkout, run `uv tool install --editable .`. Printing opens an interactive crop editor before connecting. See [CLI usage](docs/cli.md) for the editor, previews, automation, and printer selection.

For right-click printing, install the tool and register its Explorer entry:

```powershell
uv tool install --editable .
printdock context-menu install
```

Then right-click an image, choose **Show more options**, and select **Print using Hi-Print**.

### Use the native macOS CLI
```
swift run printdock scan
swift run printdock status
swift run printdock print /path/to/photo.jpg
```

### Build and run the macOS app

Run `swift build`, or open the package in Xcode and run the **PrintDockApp** target.

To package a clickable `.app`:

```sh
./scripts/package_app.sh
open dist/PrintDock.app
```

## Validation

For the Python CLI and Windows integration:

```sh
uv run pytest -q
```

For the native macOS targets:

```sh
./scripts/verify.sh
```

The macOS script runs `swift build` and, if Xcode is installed, `swift test`. It cannot validate the Swift app on Windows.

## License

MIT — see `LICENSE`.
