# Hi-Print connectivity

Print Dock contains two BLE clients for the Polaroid Hi·Print 2×3: the original macOS PrintDockKit implementation and this fork's portable Python client, verified with Gen 2 on Windows 11. The [support table](../README.md#platform-and-printer-support) distinguishes the supported and untested combinations.

The portable Python client in `python/printdock` implements the same packet contract through Bleak. For installation and everyday use, see [CLI usage](cli.md).

## Gen 2 validation on Windows

A white Hi-Print 2×3 Gen 2 was tested on Windows 11 on 2026-11-09. Direct BLE discovery, uncached status reads, image transfer, processing, and return to ready all succeeded without Android, ADB, or the official app. One diagnostic sheet was printed; the owner confirmed correct output with slight unevenness in some very small text. This establishes working printing for the tested device, not complete knowledge of every status field, fault, or firmware revision.

The printer exposes the same service and write/status UUIDs as Gen 1. The negotiated ATT MTU was 512, with a 509-byte write capacity; the client retained the existing protocol's 200-byte image chunks. The successful image used the existing dimensions, header, and frame layout documented in the [protocol deep dive](agent-connectivity-deep-dive.md).

Recorded status evidence:

| Situation | Raw status |
| --- | --- |
| Initial idle, before any print in the session | `0200000008ca00120319000005000000` |
| Processing after upload | `0201ff0008ca00120319000105000000` |
| Preparing during the job | `0201000008ca00190319000105000000` |
| Layer 1 | `0201010008ca001b0319000105000000` |
| Layer 2 | `0201020008ca001d0319000105000000` |
| Layer 3 | `0201030008ca001d0319000105000000` |
| Ready after the completed job | `0201070008ca00250319010105000000` |

Phase `0x00` alone cannot distinguish initial idle from in-job preparation. The Python Gen 2 preflight accepts it only with byte 1 equal to zero and no issue; recorded in-job preparation has byte 1 equal to one and is rejected. Phase `0x07` with no issue is also accepted. Completion requires a processing phase observed during this transfer and a fresh post-transfer `0x07` status. These policies avoid inheriting the native client's rejection of Gen 2 initial idle or treating unchanged ready status as evidence that a job printed.

Phase `0x05` also occurred before the print layers; its meaning remains unknown. Other bytes are preserved without assigning unverified battery, paper-count, temperature, or firmware meanings. A second job, fault recovery, alternate firmware, and native macOS Gen 2 behavior have not been hardware-tested. Android app analysis or an HCI capture may help with those remaining protocol details, but is unnecessary for the verified Windows print path.

## Native macOS API

For the Swift client's state machine, packet protocol, and troubleshooting runbook, see the [native connectivity deep dive](agent-connectivity-deep-dive.md).

```swift
import PrintDockKit

let client = HiPrintBLEClient(targetNamePrefix: "Hi-Print")
client.connect()

// Later, after connected:
switch client.send(jpeg: jpegData, paceMs: 12) {
case .started:
    break
case .rejected(let reason):
    print("Could not start send: \(reason)")
}
```

### Native client behavior

- The printer auto-sleeps quickly. Expect to power it on right before connecting.
- Connect uses a service-filtered scan first, then falls back to name matching.
- The last successful peripheral UUID is reused to speed up reconnects.
- `lastStatus` is polled once per second once connected and GATT-ready.

### Native client troubleshooting

- **Bluetooth permissions**: the app must declare Bluetooth usage strings.
- **No device found**: confirm the printer is in pairing mode and within range.
- **Send rejected**: ensure the connection state is `connected`, printer status is ready, and no printer issue code is active.
