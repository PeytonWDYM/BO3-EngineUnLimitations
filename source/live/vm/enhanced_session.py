"""Enroll one verified handle for the optional 500k launcher, using read-only evidence."""

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import struct
from typing import Protocol

from profile import integer


class Module(Protocol):
    baseaddress: int
    size: int
    timestamp: int
    path: Path


class Process(Protocol):
    pid: int
    started_ticks: int
    sha256: str
    path: Path
    module: Module
    def read(self, address: int, size: int) -> bytes: ...
    def alive(self) -> bool: ...
    def find_module(self, name: str) -> Module: ...


@dataclass(frozen=True)
class CapacitySite:
    rva: int
    original: bytes
    immediate_offset: int

    @property
    def patched(self) -> bytes:
        offset = self.immediate_offset
        return self.original[:offset] + struct.pack("<I", 500001) + self.original[offset + 4:]


_SEAL = object()


def _fingerprint(profile: dict) -> str:
    return hashlib.sha256(json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class EnhancedSession:
    """In-process proof, never an authority that can be restored from profile JSON."""
    process_id: int
    process_created_filetime: int
    image_base: int
    helper_base: int
    receipt_path: Path
    capacity_sites: tuple[CapacitySite, ...]
    _process: Process = field(repr=False, compare=False)
    _profile_fingerprint: str = field(repr=False)
    _seal: object = field(repr=False, compare=False)

    def authorize(self, profile: dict, process: Process | None = None) -> None:
        if self._seal is not _SEAL or _fingerprint(profile) != self._profile_fingerprint:
            raise ValueError("Enhanced enrollment is not bound to this VM profile.")
        current = self._process if process is None else process
        if (current is not self._process or current.pid != self.process_id
                or current.started_ticks != self.process_created_filetime
                or current.module.baseaddress != self.image_base or not current.alive()):
            raise ValueError("Enhanced enrollment no longer identifies the verified process.")


def _sites(process: Process, profile: dict, supplied: tuple[CapacitySite, ...] | None) -> tuple[CapacitySite, ...]:
    if supplied is not None:
        if profile["status"] != "fixture-only" or process.path.name.casefold() == "blackops3.exe":
            raise ValueError("Capacity inventory overrides are limited to owned fixtures.")
        sites = supplied
    else:
        path = Path(__file__).resolve().parents[2] / "patches/vm_pool/exact_build_inventory.json"
        inventory = json.loads(path.read_text(encoding="utf-8-sig"))
        if (process.sha256.casefold() != inventory["executableSha256"].casefold()
                or process.module.size != inventory["imageSize"]
                or process.module.timestamp != inventory["timestamp"]):
            raise ValueError("Enhanced enrollment requires the exact reviewed game build.")
        sites = tuple(CapacitySite(row["rva"], bytes.fromhex(row["bytes"]), row["immediateOffset"])
                      for row in inventory["serverCountInstructions"])
    if len(sites) != 19:
        raise ValueError("All nineteen capacity instructions are required.")
    occupied: set[int] = set()
    for site in sites:
        integer(site.rva, "capacity instruction RVA", 0, process.module.size - len(site.original))
        if len(site.original) not in (5, 6):
            raise ValueError("Unsupported capacity instruction width.")
        integer(site.immediate_offset, "capacity immediate offset", 1, len(site.original) - 4)
        if struct.unpack_from("<I", site.original, site.immediate_offset)[0] != 130000:
            raise ValueError("Capacity inventory must describe the stock total.")
        addresses = set(range(site.rva, site.rva + len(site.original)))
        if addresses & occupied:
            raise ValueError("Capacity inventory instructions overlap.")
        occupied.update(addresses)
    return tuple(sites)


def _receipt(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(16385)
    if not 1 <= len(data) <= 16384:
        raise ValueError("Enhanced session receipt exceeds its bound.")
    return data


def _session(data: bytes, process: Process) -> dict:
    session = json.loads(data)
    if not isinstance(session, dict):
        raise ValueError("Enhanced session receipt must be an object.")
    expected = {"schema": 1, "candidate": "0.1.0-test.3", "status": "ready", "processId": process.pid,
                "processCreatedFileTime": process.started_ticks, "imageBase": process.module.baseaddress,
                "serverTotal": 500001, "clientTotal": 65000, "clientRoots": 18, "stockClientRoots": 8,
                "migrationBufferBytes": 33554432, "editsWritten": 42, "activated": True}
    for name, value in expected.items():
        if type(session.get(name)) is not type(value) or session[name] != value:
            raise ValueError(f"Enhanced session receipt disagrees with {name}.")
    integer(session["helperBase"], "helper base", 1, (1 << 64) - 1)
    if session.get("exited", False) is not False or session.get("rollbackCompleted", False) is not False:
        raise ValueError("Enhanced session receipt records exit or rollback.")
    return session


def _helper(process: Process, profile: dict, session: dict) -> Module:
    evidence = profile.get("enhancedHelper")
    if not isinstance(evidence, dict):
        raise ValueError("Enhanced helper evidence is missing from the private profile.")
    helper = process.find_module("Bo3EnhancedHelper.dll")
    if helper.baseaddress != session["helperBase"] or helper.baseaddress > (1 << 64) - helper.size:
        raise ValueError("The loaded enhanced helper differs from the receipt.")
    with helper.path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    expected_hash = evidence["sha256"]
    if not isinstance(expected_hash, str) or len(expected_hash) != 64 or digest != expected_hash.casefold():
        raise ValueError("The enhanced helper file differs from the reviewed identity.")
    integer(evidence["bootRva"], "helper boot RVA", 0, helper.size - 24)
    integer(evidence["stateBindingsRva"], "helper state bindings RVA", 0, helper.size - 48)
    return helper


def _runtime(process: Process, profile: dict, helper: Module, sites: tuple[CapacitySite, ...]) -> tuple[bytes, ...]:
    codes = tuple(process.read(process.module.baseaddress + site.rva, len(site.original)) for site in sites)
    if any(code != site.patched for site, code in zip(sites, codes)):
        raise ValueError("An enhanced runtime capacity instruction differs.")
    evidence = profile["enhancedHelper"]
    boot = process.read(helper.baseaddress + evidence["bootRva"], 24)
    if struct.unpack("<IIQII", boot) != (1, 24, helper.baseaddress, 1, 0):
        raise ValueError("The enhanced helper is not loader-ready.")
    bindings = process.read(helper.baseaddress + evidence["stateBindingsRva"], 48)
    state = struct.unpack("<QIIIIQQQ", bindings)
    if state[:5] != (process.module.baseaddress, 500001, 18, 8, 1):
        raise ValueError("The enhanced helper state configuration differs.")
    if any(not helper.baseaddress < callback < helper.baseaddress + helper.size for callback in state[5:]):
        raise ValueError("An enhanced state callback is outside the verified helper.")
    return codes + (boot, bindings)


def resolve_enhanced_session(process: Process, profile: dict, sessions_directory: Path | None = None,
                             *, capacity_sites: tuple[CapacitySite, ...] | None = None) -> EnhancedSession | None:
    """Call after VerifiedProcess admission. Missing exact receipt means a stock session.

    Every existing but invalid/non-ready receipt refuses enrollment. No expanded pool is read.
    The inventory override exists only for fixture E2E; BlackOps3 always uses the fixed inventory.
    """
    directory = sessions_directory if sessions_directory is not None else (
        Path(os.environ["LOCALAPPDATA"]) / "BO3 Engine UnLimitations/sessions")
    path = directory / f"{process.started_ticks}-{process.pid}.json"
    try:
        before = _receipt(path)
    except FileNotFoundError:
        return None
    session = _session(before, process)
    sites = _sites(process, profile, capacity_sites)
    helper = _helper(process, profile, session)
    first = _runtime(process, profile, helper, sites)
    if first != _runtime(process, profile, helper, sites) or _receipt(path) != before or not process.alive():
        raise ValueError("Enhanced evidence changed during enrollment.")
    return EnhancedSession(process.pid, process.started_ticks, process.module.baseaddress, helper.baseaddress,
                           path, sites, process, _fingerprint(profile), _SEAL)


def verify_code_evidence(process: Process, profile: dict, enrollment: EnhancedSession | None = None) -> None:
    """Preserve the stock hashes; normalize only attested four-byte capacity immediates."""
    sites: tuple[CapacitySite, ...] = ()
    if enrollment is not None:
        enrollment.authorize(profile, process)
        sites = enrollment.capacity_sites
        receipt_before = _receipt(enrollment.receipt_path)
        session = _session(receipt_before, process)
        helper = _helper(process, profile, session)
        first = _runtime(process, profile, helper, sites)
    for evidence in profile.get("codeEvidence", []):
        start, end = int(evidence["startRva"], 0), int(evidence["endRva"], 0)
        if not 0 <= start < end <= process.module.size:
            raise ValueError("Invalid native code evidence range.")
        code = bytearray(process.read(process.module.baseaddress + start, end - start))
        for site in sites:
            immediate = site.rva + site.immediate_offset
            low, high = max(start, immediate), min(end, immediate + 4)
            if low < high:
                stock = site.original[site.immediate_offset:site.immediate_offset + 4]
                code[low - start:high - start] = stock[low - immediate:high - immediate]
        if hashlib.sha256(code).hexdigest() != evidence["sha256"].casefold():
            raise ValueError("The live native code differs from the reviewed profile.")
    if enrollment is not None:
        if (first != _runtime(process, profile, helper, sites)
                or _receipt(enrollment.receipt_path) != receipt_before or not process.alive()):
            raise ValueError("Enhanced runtime evidence changed during code verification.")
