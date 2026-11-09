import sys
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest

from printdock import windows_shell


def test_shell_command_quotes_launcher_and_selected_image_argument():
    launcher = Path("C:/User Photos/Hi & Print/printdock-hi-print.exe")
    assert windows_shell.shell_command(launcher) == f'"{launcher}" "%1"'


def test_cancel_from_explorer_never_creates_a_print_progress_job(monkeypatch):
    editor = ModuleType("printdock.editor")
    editor.edit_jpeg = lambda path: None
    monkeypatch.setitem(sys.modules, "printdock.editor", editor)
    def unexpected_job(*args):
        pytest.fail("Cancelled crop must not start a print job")
    monkeypatch.setattr(windows_shell, "PrintProgress", unexpected_job)
    windows_shell.launch_image(Path("image with spaces.jpg"))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry integration")
def test_install_and_idempotent_uninstall_use_only_owned_current_user_keys(monkeypatch, tmp_path):
    import winreg
    key_path = rf"Software\PrintDockTest_{uuid4().hex}"
    monkeypatch.setattr(windows_shell, "MENU_KEY", key_path)
    launcher = tmp_path / "Hi & Print ž" / "printdock-hi-print.exe"
    launcher.parent.mkdir()
    launcher.touch()
    try:
        windows_shell.install_context_menu(launcher)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            assert winreg.QueryValueEx(key, "")[0] == "Print using Hi-Print"
            assert winreg.QueryValueEx(key, "MultiSelectModel")[0] == "Single"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path + r"\command") as key:
            command, kind = winreg.QueryValueEx(key, "")
            assert command == f'"{launcher.resolve()}" "%1"'
            assert kind == winreg.REG_SZ
        windows_shell.uninstall_context_menu()
        windows_shell.uninstall_context_menu()
        with pytest.raises(FileNotFoundError):
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
    finally:
        windows_shell.uninstall_context_menu()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry integration")
def test_missing_launcher_does_not_create_a_broken_menu(monkeypatch, tmp_path):
    import winreg
    key_path = rf"Software\PrintDockTest_{uuid4().hex}"
    monkeypatch.setattr(windows_shell, "MENU_KEY", key_path)
    with pytest.raises(RuntimeError, match="launcher missing"):
        windows_shell.install_context_menu(tmp_path / "missing.exe")
    with pytest.raises(FileNotFoundError):
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
