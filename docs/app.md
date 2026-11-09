# Print Dock App

A SwiftUI macOS app built on PrintDockKit.

For Windows, use the [Python CLI and Explorer launcher](cli.md), which include the interactive crop editor. See the [support table](../README.md#platform-and-printer-support) for printer-generation coverage.

## Run in Xcode

1) Open `Package.swift` in Xcode
2) Select the **PrintDockApp** target
3) Run

## Package a clickable .app

```
./scripts/package_app.sh
open dist/PrintDock.app
```

## Bluetooth permissions

The packaging script embeds required Bluetooth usage strings in the app Info.plist.
