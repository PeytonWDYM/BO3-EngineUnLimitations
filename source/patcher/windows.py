"""Read Steam locations and the process list without launching the game."""
import ctypes
from dataclasses import dataclass
from ctypes import wintypes
import os
from pathlib import Path
import re

from patcher.engine import PatchError


@dataclass(frozen=True)
class SteamContext:
    directory: Path
    active_user: int | None
    auto_login_name: str | None


def steam_context() -> SteamContext:
    """Read installation and account hints. This never changes Steam registry values."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
        directory = Path(winreg.QueryValueEx(key, 'SteamPath')[0])
        try:
            auto_login = winreg.QueryValueEx(key, 'AutoLoginUser')[0] or None
        except FileNotFoundError:
            auto_login = None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess") as key:
            active_user = winreg.QueryValueEx(key, 'ActiveUser')[0] or None
    except FileNotFoundError:
        active_user = None
    return SteamContext(directory, active_user, auto_login)


def game_running(executable_name: str = "BlackOps3.exe") -> bool:
    if os.name != "nt":
        raise PatchError("The game patcher requires Windows.")
    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    api.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    api.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    api.Process32FirstW.restype = wintypes.BOOL
    api.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    api.Process32NextW.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    handle = api.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        found = api.Process32FirstW(handle, ctypes.byref(entry))
        if not found:
            raise ctypes.WinError(ctypes.get_last_error())
        while found:
            if entry.szExeFile.casefold() == executable_name.casefold():
                return True
            found = api.Process32NextW(handle, ctypes.byref(entry))
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise ctypes.WinError(ctypes.get_last_error())
        return False
    finally:
        api.CloseHandle(handle)


def steam_installs() -> list[dict[str, Path]]:
    if os.name != "nt":
        return []
    try:
        steam = steam_context().directory
    except FileNotFoundError:
        return []
    libraries = [steam]
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        libraries.extend(Path(value.replace("\\\\", "\\")) for value in re.findall(r'"path"\s+"([^"\r\n]+)"', vdf.read_text(encoding="utf-8")))
    results = []
    seen = set()
    for library in libraries:
        identity = str(library.resolve()).casefold()
        if identity in seen:
            continue
        seen.add(identity)
        workshop = library / "steamapps/workshop/content/311210/2631943123"
        game = library / "steamapps/common/Call of Duty Black Ops III"
        if workshop.is_dir() or game.is_dir():
            results.append({"workshop": workshop, "game": game})
    return results
