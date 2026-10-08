"""Transform the owner's packed AAE module into the reviewed Lua guard."""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import pefile

from patches.native_input.guard_image import build_image


ORIGINAL_SHA256 = "dbaed33f51853ffdf2be390dacc50e8af442506f603f331df15f4381ca775261"
PATCHED_SHA256 = "a4834cc251cfcba413bd80d783eec854c0c3f31d14651703a8d7a9e718e1576c"
UPX_SHA256 = "d20ebe0b7b22b6be968c8c34be61f94ddea12cb11462e2cec27f548ef9574df8"


def transform(source: bytes, resources: Path) -> bytes:
    """Repair packing metadata on a temporary copy, then build the guard."""
    if hashlib.sha256(source).hexdigest() != ORIGINAL_SHA256:
        raise ValueError("This native AAE module is not a supported original.")
    upx = resources / "upx" / "upx.exe"
    if hashlib.sha256(upx.read_bytes()).hexdigest() != UPX_SHA256:
        raise ValueError("The UPX executable differs from the pinned release tool.")
    repaired = bytearray(source)
    pe = pefile.PE(data=source)
    if repaired[0x3E0:0x3E4] != b"XYZ?" or [section.Name.rstrip(b"\0") for section in pe.sections] != [b".wolf", b".code", b".rsrc"]:
        raise ValueError("The supported native packing metadata has changed.")
    repaired[0x3E0:0x3E4] = b"UPX!"
    for section, name in zip(pe.sections[:2], (b"UPX0", b"UPX1")):
        offset = section.get_file_offset()
        repaired[offset:offset + 8] = name.ljust(8, b"\0")
    with tempfile.TemporaryDirectory(prefix="aae-native-") as temporary:
        directory = Path(temporary)
        packed = directory / "packed.dll"
        unpacked = directory / "unpacked.dll"
        packed.write_bytes(repaired)
        for arguments in (("-t", str(packed)), ("-d", "-o", str(unpacked), str(packed))):
            subprocess.run([str(upx), *arguments], check=True, capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
        profile = json.loads((resources / "patchplans" / "native_profile.json").read_text())
        candidate, _ = build_image(unpacked.read_bytes(), profile)
    if hashlib.sha256(candidate).hexdigest() != PATCHED_SHA256:
        raise ValueError("The native guard differs from the reviewed release identity.")
    return candidate
