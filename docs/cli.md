# printdock CLI

The portable Python CLI supports Windows Bluetooth through Bleak. It has been verified with a Hi-Print 2×3 Gen 2 on Windows 11. Its macOS and Linux backends, and printing on Gen 1 hardware, have not been verified here. The native Swift CLI remains available on macOS.

## Install the Python CLI

From the repository, using [uv](https://docs.astral.sh/uv/getting-started/installation/):

```powershell
uv sync
uv run printdock --help
```

For a command available from any directory:

```powershell
uv tool install --editable .
printdock --help
```

The editable installation uses this checkout. Keep it in place; rerun the installation if dependencies change.

## Everyday printing

Wake the printer immediately before connecting. Disconnect the phone app if it holds the Bluetooth connection.

```powershell
printdock scan
printdock status
printdock print "C:\Photos\photo.jpg"
```

`print` opens a crop editor before Bluetooth connects. Drag the image to position it, scroll to zoom around the pointer, or enter a zoom percentage. With the image focused, arrow keys move it by one output pixel; Shift moves ten. The frame uses the printer raster's exact aspect ratio, with an optional thirds grid and dimmed surroundings. Switching orientation changes the frame; **Fill frame** and **Fit whole photo** reset the composition. The editor also shows the source crop coordinates and indicates when the selection requires upscaling.

Click **Print** to approve the crop and start connecting, or **Cancel** / Escape / close the window to stop without Bluetooth discovery. Wake the printer before approving if it has gone to sleep while editing. The displayed crop is decoded from the exact final JPEG that is sent; it is not cropped or encoded again after approval. Screen colors and the printer's physical edge tolerances are not calibrated by this preview.

Landscape photos initially use the long edge. `--fit cover` starts with a centered crop that fills the frame; `--fit contain` starts with the whole photo and white margins. `--orientation portrait` or `--orientation landscape` sets the initial orientation. These are starting points that you can change in the editor.

```powershell
printdock print "C:\Photos\photo.jpg" --fit contain
```

Preview the prepared JPEG without connecting or consuming paper:

```powershell
printdock prepare "C:\Photos\photo.jpg" --fit contain --output "C:\Photos\preview.jpg"
```

Add `--edit` to choose a crop interactively and save it without printing:

```powershell
printdock prepare "C:\Photos\photo.jpg" --edit --output "C:\Photos\preview.jpg"
```

The editor requires Python with Tk support (included in the tested Windows installation). If it cannot open, the command fails without printing. For scripts, `print --no-edit` explicitly skips the editor and uses automatic fitting. Plain `prepare` also remains noninteractive.

Prepared JPEGs always have the printer's portrait raster orientation, so landscape previews appear rotated. Images are EXIF-oriented, converted from embedded color profiles to sRGB, flattened onto white, and rendered to the protocol dimensions. JPEG quality defaults to 98 with no chroma subsampling.

## Printer selection and diagnostics

```powershell
printdock status --address "F8:5B:1B:A0:4A:FE"
printdock inspect --address "F8:5B:1B:A0:4A:FE"
```

Use an address reported by `scan` (a peripheral UUID on macOS). Without an address, multiple matching printers cause an error rather than an arbitrary selection. `inspect` emits JSON containing services, characteristic properties, negotiated write sizes, and raw status. It sends no print commands.

`status` reports raw bytes, phase, issue, `READY`, and `STARTABLE`. `READY` means the completed-job ready phase; `STARTABLE` also recognizes Gen 2's observed initial idle state. The default generation is 2. Use `--generation 1` with `status` or `print` for the stricter Gen 1 preflight policy. See [connectivity](connectivity.md) for the validated status observations and their limits.

Connection commands accept `--timeout` (12 seconds by default) and `--prefix` (`Hi-Print` by default). `print` additionally accepts `--pace` (12 milliseconds between packets) and `--print-timeout` (180 seconds for upload and processing). Logs go to stderr; command results and transfer progress go to stdout.

`PROGRESS 100%` means upload finished. `PRINT_DONE` requires observed processing followed by a fresh ready status. A failed or interrupted transfer is never automatically retried: inspect the printer before resending because it may already have received the job.

## Native macOS CLI

The Swift CLI wraps PrintDockKit:

```sh
swift run printdock scan
swift run printdock status
swift run printdock print ~/Pictures/photo.jpg
```

It accepts `--prefix`, `--timeout`, and `--pace` for printing. It reconnects to the last successful peripheral when possible, uses centered portrait cropping, and waits at least 90 seconds for completion. Python-only options above do not apply to the Swift executable. Its Gen 1 status policy is documented in the [native connectivity deep dive](agent-connectivity-deep-dive.md).
