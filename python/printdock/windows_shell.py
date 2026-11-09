"""Per-user Explorer registration and the console-free print entry point."""

import asyncio
import ctypes
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .printer import print_jpeg

MENU_KEY = r"Software\Classes\SystemFileAssociations\image\shell\PrintDock.HiPrint"
MENU_LABEL = "Print using Hi-Print"
LAUNCHER_NAME = "printdock-hi-print.exe"
logger = logging.getLogger(__name__)


def shell_command(launcher: Path) -> str:
    if '"' in str(launcher):
        raise ValueError("Launcher path cannot contain quotes")
    return f'"{launcher}" "%1"'


def notify_associations_changed() -> None:
    # SHCNE_ASSOCCHANGED, SHCNF_IDLIST: refresh associations without restarting Explorer.
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


def install_context_menu(launcher: Path | None = None) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Explorer context menus are available on Windows only")
    import winreg
    launcher = (launcher or Path(sys.executable).with_name(LAUNCHER_NAME)).resolve()
    if not launcher.is_file():
        raise RuntimeError("GUI launcher missing. Run uv tool install --force --editable . first.")
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, MENU_KEY) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, MENU_LABEL)
        winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Single")
        with winreg.CreateKeyEx(key, "command") as command:
            winreg.SetValueEx(command, "", 0, winreg.REG_SZ, shell_command(launcher))
    notify_associations_changed()
    logger.info("Registered Explorer image command: %s", launcher)


def uninstall_context_menu() -> None:
    if sys.platform != "win32":
        raise RuntimeError("Explorer context menus are available on Windows only")
    import winreg
    for key in (MENU_KEY + r"\command", MENU_KEY):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except FileNotFoundError:
            pass
    notify_associations_changed()
    logger.info("Removed Explorer image command")


class PrintProgress:
    def __init__(self, filename: str):
        import tkinter as tk
        from tkinter import ttk
        self.root = tk.Tk()
        self.root.title(MENU_LABEL)
        self.root.geometry("460x180")
        self.root.resizable(False, False)
        # Closing the progress window hides it; it must not interrupt a job
        # that may already be consuming paper. Crop-editor Cancel stops earlier.
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)
        panel = ttk.Frame(self.root, padding=20)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text=filename, wraplength=420).pack(anchor="w")
        self.status = tk.StringVar(value="Finding and connecting to Hi-Print…")
        ttk.Label(panel, textvariable=self.status).pack(anchor="w", pady=10)
        self.bar = ttk.Progressbar(panel, mode="indeterminate")
        self.bar.pack(fill="x")
        self.bar.start()
        self.close = ttk.Button(panel, text="Close", state="disabled", command=self.root.destroy)
        self.close.pack(anchor="e", pady=(12, 0))

    def transfer_progress(self, percent: int):
        if percent < 100:
            self.status.set(f"Sending photo: {percent}%")
            self.bar.stop()
            self.bar.configure(mode="determinate", value=percent)
        else:
            self.status.set("Photo sent. Waiting for the printer to finish…")
            self.bar.configure(mode="indeterminate")
            self.bar.start()

    async def send(self, jpeg: bytes):
        task = asyncio.create_task(print_jpeg(jpeg, progress=self.transfer_progress))
        try:
            while not task.done():
                self.root.update()
                await asyncio.sleep(0.05)
            await task
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.root.destroy()
            raise
        self.bar.stop()
        self.bar.configure(mode="determinate", value=100)
        self.status.set("Print completed successfully.")
        self.close.configure(state="normal")
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.root.deiconify()


def launch_image(path: Path) -> None:
    from .editor import edit_jpeg
    jpeg = edit_jpeg(path)
    if jpeg is None:
        logger.info("Explorer print cancelled before connecting")
        return
    dialog = PrintProgress(path.name)
    asyncio.run(dialog.send(jpeg))
    dialog.root.mainloop()


def main() -> None:
    log_path = None
    try:
        if sys.platform != "win32":
            raise RuntimeError("This launcher requires Windows")
        log_dir = Path(os.environ["LOCALAPPDATA"]) / "PrintDock"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "printdock.log"
        handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
        if len(sys.argv) != 2:
            raise ValueError("Select one image to print")
        launch_image(Path(sys.argv[1]))
    except Exception as error:
        logger.exception("Explorer print failed")
        if sys.platform != "win32":
            raise SystemExit(str(error))
        detail = "Timed out before verified completion. Check the printer before retrying." if isinstance(error, TimeoutError) else str(error) or type(error).__name__
        if log_path is not None:
            detail += f"\n\nLog: {log_path}"
        ctypes.windll.user32.MessageBoxW(None, detail, MENU_LABEL, 0x10)
        raise SystemExit(1)
