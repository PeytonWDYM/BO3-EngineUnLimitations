"""Build the exact Lua callback guard without executing the native module."""

import hashlib
import struct
from typing import TypedDict

import pefile


GuardProfile = TypedDict("GuardProfile", {
    "sourceSha256": str, "entry": int, "patch": int,
    "patchBytes": str, "continue": int, "unavailable": int,
})


def align(value: int, boundary: int) -> int:
    return (value + boundary - 1) & -boundary


def jump(source: int, target: int) -> bytes:
    return b"\xe9" + struct.pack("<i", target - source - 5)


def build_image(original: bytes, profile: GuardProfile) -> tuple[bytes, dict[str, str | int | bool]]:
    if hashlib.sha256(original).hexdigest() != profile["sourceSha256"]:
        raise ValueError("The source differs from the inspected image.")
    raw = bytearray(original)
    pe = pefile.PE(data=raw)
    expected = bytes.fromhex(profile["patchBytes"])
    if pe.get_data(profile["patch"], len(expected)) != expected:
        raise ValueError("The native patch site differs from the inspected instructions.")
    functions = [entry.struct for entry in pe.DIRECTORY_ENTRY_EXCEPTION if entry.struct.BeginAddress == profile["entry"]]
    if len(functions) != 1:
        raise ValueError("The inspected native entry has no unique unwind record.")
    function = functions[0]
    header = pe.sections[-1].get_file_offset() + 40
    if header + 40 > pe.OPTIONAL_HEADER.SizeOfHeaders or any(raw[header:header + 40]):
        raise ValueError("The PE header has no free section record.")
    directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    pdata = next(section for section in pe.sections if section.VirtualAddress <= directory.VirtualAddress < section.VirtualAddress + section.Misc_VirtualSize)
    table_end = directory.VirtualAddress + directory.Size
    offset = pe.get_offset_from_rva(table_end)
    if table_end + 12 > pdata.VirtualAddress + pdata.SizeOfRawData or any(raw[offset:offset + 12]):
        raise ValueError("The unwind table has no verified free trailing record.")
    guard_rva = align(pe.OPTIONAL_HEADER.SizeOfImage, pe.OPTIONAL_HEADER.SectionAlignment)
    # A missing global context exits through the existing unlock and string destructor.
    guard = expected[:4] + b"\x48\x85\xc0\x74\x0d" + expected[4:]
    # Conditional transfers keep Windows from classifying these branches as tail-call epilogues.
    guard += b"\x0f\x85" + struct.pack("<i", profile["continue"] - guard_rva - len(guard) - 6)
    guard += b"\x31\xed"
    guard += b"\x0f\x84" + struct.pack("<i", profile["unavailable"] - guard_rva - len(guard) - 6)
    unwind_offset = align(len(guard), 4)
    chained = bytes.fromhex("21000000") + struct.pack("<III", function.BeginAddress, function.EndAddress, function.UnwindData)
    payload = guard.ljust(unwind_offset, b"\x90") + chained
    raw_offset = align(len(raw), pe.OPTIONAL_HEADER.FileAlignment)
    raw_size = align(len(payload), pe.OPTIONAL_HEADER.FileAlignment)
    raw.extend(b"\0" * (raw_offset - len(raw)))
    raw.extend(payload.ljust(raw_size, b"\0"))
    patch_offset = pe.get_offset_from_rva(profile["patch"])
    raw[patch_offset:patch_offset + len(expected)] = jump(profile["patch"], guard_rva).ljust(len(expected), b"\x90")
    raw[offset:offset + 12] = struct.pack("<III", guard_rva, guard_rva + len(guard), guard_rva + unwind_offset)
    struct.pack_into("<I", raw, pdata.get_field_absolute_offset("Misc_VirtualSize"), max(pdata.Misc_VirtualSize, table_end + 12 - pdata.VirtualAddress))
    struct.pack_into("<I", raw, directory.get_field_absolute_offset("Size"), directory.Size + 12)
    raw[header:header + 40] = struct.pack("<8sIIIIIIHHI", b".luafix\0", len(payload), guard_rva, raw_size, raw_offset, 0, 0, 0, 0, 0x60000020)
    struct.pack_into("<H", raw, pe.FILE_HEADER.get_field_absolute_offset("NumberOfSections"), pe.FILE_HEADER.NumberOfSections + 1)
    struct.pack_into("<I", raw, pe.OPTIONAL_HEADER.get_field_absolute_offset("SizeOfImage"), align(guard_rva + len(payload), pe.OPTIONAL_HEADER.SectionAlignment))
    struct.pack_into("<I", raw, pe.OPTIONAL_HEADER.get_field_absolute_offset("SizeOfCode"), pe.OPTIONAL_HEADER.SizeOfCode + raw_size)
    struct.pack_into("<I", raw, pe.OPTIONAL_HEADER.get_field_absolute_offset("CheckSum"), 0)
    candidate = bytes(raw)
    report = {
        "sourceSha256": profile["sourceSha256"],
        "candidateSha256": hashlib.sha256(candidate).hexdigest(),
        "guardRva": guard_rva, "guardLength": len(guard),
        "chainedUnwindRva": guard_rva + unwind_offset,
        "normalDeployment": False, "gameValidated": False,
    }
    return candidate, report
