# FAQ

**Does this fork support Windows and Hi-Print Gen 2?**

See the [platform and printer support table](../README.md#platform-and-printer-support). For setup, interactive cropping, and Windows right-click printing, see [CLI and Explorer usage](cli.md).

**Why doesn’t it show up as a normal macOS printer?**
The Hi·Print is designed for app-driven Bluetooth printing and doesn’t expose a standard macOS print queue.

**The printer disconnects quickly.**
The device auto-sleeps after short idle periods. Turn it on right before printing.

**macOS Bluetooth permission prompts never appear.**
Ensure you’re using the packaged app or Xcode target with Bluetooth usage strings.

**Printer blinks red after a send.**
That maps to a non-zero printer issue status in this stack (for example `0x09` is reported as printer attention). Run `printdock status` and check `ISSUE` and `READY` before sending another job.

**How can I tell if cartridge/media is empty?**
Use `printdock status`. If `READY false` with non-zero `ISSUE`, the printer is not ready for another job and usually needs cartridge/media/path attention.
