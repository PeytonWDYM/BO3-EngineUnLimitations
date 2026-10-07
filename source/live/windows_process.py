"""Read a verified Windows process with query and VM_READ permissions only."""

import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import struct


ACCESS_MASK = 0x1000 | 0x0010
GLOBAL_FORMATS = {"pool": "Q", "highWater": "I", "time": "i", "head": "Q", "tail": "Q"}
kernel = ctypes.WinDLL("kernel32", use_last_error=True)


class ModuleEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("th32ModuleID", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("GlblcntUsage", wintypes.DWORD),
                ("ProccntUsage", wintypes.DWORD), ("modBaseAddr", ctypes.c_void_p),
                ("modBaseSize", wintypes.DWORD), ("hModule", wintypes.HMODULE),
                ("szModule", wintypes.WCHAR * 256), ("szExePath", wintypes.WCHAR * 260)]


for name, arguments, result in (
    ("OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
    ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
    ("ReadProcessMemory", [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                           ctypes.POINTER(ctypes.c_size_t)], wintypes.BOOL),
    ("GetProcessTimes", [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4, wintypes.BOOL),
    ("GetExitCodeProcess", [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
    ("QueryFullProcessImageNameW", [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                    ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
    ("CreateToolhelp32Snapshot", [wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
    ("Module32FirstW", [wintypes.HANDLE, ctypes.POINTER(ModuleEntry)], wintypes.BOOL),
    ("Module32NextW", [wintypes.HANDLE, ctypes.POINTER(ModuleEntry)], wintypes.BOOL),
):
    function = getattr(kernel, name)
    function.argtypes = arguments
    function.restype = result


def require(success, operation: str) -> None:
    if not success:
        error = ctypes.get_last_error()
        raise OSError(error, f"{operation} failed: {ctypes.FormatError(error).strip()}")


class LiveProcess:
    def __init__(self, pid: int, profile: dict, expected_start_ticks: int | None = None):
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            raise ValueError("Use 64-bit Python for the live sampler.")
        layout = profile["layout"]
        if not (0 < layout["stride"] <= 65536 and 0 < layout["capacity"] <= 65536
                and layout["stride"] * layout["capacity"] <= 64 * 1024 * 1024):
            raise ValueError("The pool size exceeds the sampler bounds.")
        self.handle = kernel.OpenProcess(ACCESS_MASK, False, pid)
        require(self.handle, "OpenProcess")
        self.pid = pid
        try:
            created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
            require(kernel.GetProcessTimes(self.handle, ctypes.byref(created), ctypes.byref(exited),
                                           ctypes.byref(system), ctypes.byref(user)), "GetProcessTimes")
            self.started_ticks = created.dwHighDateTime << 32 | created.dwLowDateTime
            if expected_start_ticks is not None and self.started_ticks != expected_start_ticks:
                raise ValueError("The process start time differs from the requested process instance.")
            started = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=self.started_ticks // 10)
            self.started_utc = started.isoformat()
            buffer = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(buffer))
            require(kernel.QueryFullProcessImageNameW(self.handle, 0, buffer, ctypes.byref(length)),
                    "QueryFullProcessImageName")
            self.path = Path(buffer.value).resolve()
            if self.path.name.casefold() != profile["module"].casefold():
                raise ValueError("The executable name differs from the profile module.")
            with self.path.open("rb") as executable:
                digest = hashlib.file_digest(executable, "sha256").hexdigest()
            if digest.casefold() != profile["sha256"].casefold():
                raise ValueError("The executable hash differs from the profile.")
            self.sha256 = digest
            self.module = self.find_module(profile["module"])
            if not self.path.samefile(self.module.path):
                raise ValueError("The selected module differs from the process executable.")
            dos = self.read(self.module.baseaddress, 64)
            if dos[:2] != b"MZ":
                raise ValueError("The module has no DOS image header.")
            nt_offset = struct.unpack_from("<I", dos, 60)[0]
            if not 0 <= nt_offset <= self.module.size - 88:
                raise ValueError("The module PE header is outside its image.")
            nt = self.read(self.module.baseaddress + nt_offset, 88)
            if nt[:4] != b"PE\0\0" or struct.unpack_from("<H", nt, 24)[0] != 0x20B:
                raise ValueError("The module is not a 64-bit PE image.")
            self.module.timestamp = struct.unpack_from("<I", nt, 8)[0]
            image_size = struct.unpack_from("<I", nt, 80)[0]
            if (self.module.size != profile["imageSize"] or image_size != profile["imageSize"]
                    or self.module.timestamp != profile["timestamp"]):
                raise ValueError("The loaded module build differs from the profile.")
            if not self.alive():
                raise ProcessLookupError("The process exited during identity verification.")
            for name, code in GLOBAL_FORMATS.items():
                if not 0 <= profile["globals"][name] <= self.module.size - struct.calcsize("<" + code):
                    raise ValueError("A profile global is outside the selected module.")
        except BaseException:
            self.close()
            raise

    def find_module(self, name: str):
        snapshot = kernel.CreateToolhelp32Snapshot(0x18, self.pid)
        if snapshot == ctypes.c_void_p(-1).value:
            require(False, "CreateToolhelp32Snapshot")
        try:
            entry = ModuleEntry()
            entry.dwSize = ctypes.sizeof(entry)
            require(kernel.Module32FirstW(snapshot, ctypes.byref(entry)), "Module32First")
            matches = []
            while True:
                if entry.szModule.casefold() == name.casefold():
                    from types import SimpleNamespace
                    matches.append(SimpleNamespace(baseaddress=entry.modBaseAddr, size=entry.modBaseSize,
                                                   path=Path(entry.szExePath)))
                if not kernel.Module32NextW(snapshot, ctypes.byref(entry)):
                    if ctypes.get_last_error() != 18:
                        require(False, "Module32Next")
                    break
            if len(matches) != 1:
                raise ValueError("The selected live module is absent or ambiguous.")
            return matches[0]
        finally:
            kernel.CloseHandle(snapshot)

    def read(self, address: int, size: int) -> bytes:
        buffer = ctypes.create_string_buffer(size)
        count = ctypes.c_size_t()
        require(kernel.ReadProcessMemory(self.handle, address, buffer, size, ctypes.byref(count)), "ReadProcessMemory")
        if count.value != size:
            raise OSError("ReadProcessMemory returned a partial read.")
        return buffer.raw

    def number(self, address: int, format_code: str) -> int:
        return struct.unpack("<" + format_code, self.read(address, struct.calcsize("<" + format_code)))[0]

    def metadata(self, profile: dict) -> dict:
        return {name: self.number(self.module.baseaddress + profile["globals"][name], code)
                for name, code in GLOBAL_FORMATS.items()}

    def pool_ranges(self, profile: dict) -> list[tuple[int, int]]:
        metadata = self.metadata(profile)
        return [(self.module.baseaddress + profile["globals"][name], struct.calcsize("<" + code))
                for name, code in GLOBAL_FORMATS.items()] + [
                    (metadata["pool"], profile["layout"]["stride"] * profile["layout"]["capacity"])]

    def alive(self) -> bool:
        code = wintypes.DWORD()
        require(kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)), "GetExitCodeProcess")
        return code.value == 259

    def close(self) -> None:
        kernel.CloseHandle(self.handle)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
