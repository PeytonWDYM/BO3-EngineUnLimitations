"""Enroll one verified handle for the optional 500k launcher, using read-only evidence."""

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import struct
from typing import Protocol

from profile import integer
from integrity_evidence import IntegrityProfile, load_integrity_profile
from early_checksum_evidence import EarlyChecksum, METHOD as EARLY_METHOD, load_early_checksum


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
_LATE_HELPER_SHA256 = "09b947ba384837853d5f4061a8fc3e2b61dee6b2663a751d6e7a2fb974c803c1"
_INTEGRITY_METHOD = "late-crt-job-freeze-code-integrity"


class ReceiptOrigin(Enum):
    LEGACY = ""
    LATE = "-late"
    JOB = "-job"


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
    integrity: IntegrityProfile | None = field(default=None, repr=False)
    _receipt_data: bytes = field(default=b"", repr=False)
    early_checksum: EarlyChecksum | None = field(default=None, repr=False)

    def authorize(self, profile: dict, process: Process | None = None) -> None:
        if self._seal is not _SEAL or _fingerprint(profile) != self._profile_fingerprint:
            raise ValueError("Enhanced enrollment is not bound to this VM profile.")
        current = self._process if process is None else process
        if (current is not self._process or current.pid != self.process_id
                or current.started_ticks != self.process_created_filetime
                or current.module.baseaddress != self.image_base or not current.alive()):
            raise ValueError("Enhanced enrollment no longer identifies the verified process.")
        if self.integrity is not None or self.early_checksum is not None:
            _verify_integrity_session(self, profile, current)


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


def _selected_receipt(process: Process, directory: Path) -> tuple[Path, bytes, ReceiptOrigin] | None:
    stem = f"{process.started_ticks}-{process.pid}"
    paths = tuple((directory / f"{stem}{origin.value}.json", origin) for origin in ReceiptOrigin)
    present = tuple((path, origin) for path, origin in paths if path.exists())
    if len(present) > 1:
        raise ValueError("Enhanced session has ambiguous exact-process receipts.")
    if not present:
        return None
    path, origin = present[0]
    return path, _receipt(path), origin


def _session(data: bytes, process: Process, *, origin: ReceiptOrigin = ReceiptOrigin.LEGACY,
             integrity: IntegrityProfile | None = None, early_checksum: EarlyChecksum | None = None) -> dict:
    session = json.loads(data)
    if not isinstance(session, dict):
        raise ValueError("Enhanced session receipt must be an object.")
    early_method = session.get("startupMethod") == EARLY_METHOD
    if early_method != (early_checksum is not None) or (early_method and origin is not ReceiptOrigin.JOB):
        raise ValueError("Early checksum enrollment requires its exact job receipt route.")
    if not early_method and any(name.startswith(("checksum", "earlyChecksum")) for name in session):
        raise ValueError("Early checksum metadata cannot use an older startup method.")
    new_method = session.get("startupMethod") == _INTEGRITY_METHOD
    if new_method != (integrity is not None) or (new_method and origin is not ReceiptOrigin.JOB):
        raise ValueError("Integrity enrollment requires its exact job receipt method and route.")
    if not new_method and any(name.startswith("integrity") for name in session):
        raise ValueError("Integrity metadata cannot use an older startup method.")
    expected = {"schema": 1, "candidate": "0.1.0-test.3", "processId": process.pid,
                "processCreatedFileTime": process.started_ticks, "imageBase": process.module.baseaddress,
                "serverTotal": 500001, "clientTotal": 65000, "clientRoots": 18, "stockClientRoots": 8,
                "migrationBufferBytes": 33554432, "editsWritten": 42}
    if origin is ReceiptOrigin.LATE:
        expected |= {"startupMethod": "late-crt-gate", "attached": True, "committed": True,
                     "detached": True, "debuggerAbsent": True, "released": True,
                     "terminated": False, "rollbackCompleted": False,
                     "debugRegisterWrites": 0, "liveAllocationValidated": False, "generation": 1}
    elif origin is ReceiptOrigin.JOB:
        expected |= {"startupMethod": "late-crt-job-freeze", "jobOwned": True,
                     "jobMembershipVerified": True, "primaryOnlyAdmitted": True,
                     "frozenForTransaction": True, "thawed": True, "committed": True,
                     "released": True, "debuggerAbsent": True, "freezeStatus": 0, "thawStatus": 0,
                     "threadsObserved": 1, "attached": False, "detached": False,
                     "debugRegisterWrites": 0, "liveAllocationValidated": False,
                     "terminated": False, "rollbackCompleted": False, "generation": 1}
        if integrity is not None:
            expected |= {"startupMethod": _INTEGRITY_METHOD, "editsWritten": 1395,
                         "integrityProfile": integrity.digest, "integrityOriginalDigest": integrity.original_digest,
                         "integrityReplacementDigest": integrity.replacement_digest,
                         "integrityAdmitted": True, "integrityInputAttributionVerified": True,
                         "integrityPatternsAdmitted": 1365, "integrityEditsPrepared": 1353,
                         "integrityTransformsRetained": 12, "nativeEditsRequired": 42,
                         "combinedEditsRequired": 1395, "integrityReapplication": False,
                         "jobParentOnly": True, "killOnJobClose": True, "freezeAttempted": True,
                         "thawAttempted": True, "cleanupFailed": False, "relayFreed": False,
                         "runtimeMetadataMask": 3, "stage": "released", "refusalReason": "", "unwindReason": "",
                         "executableSha256": process.sha256}
            if not integrity.attribution_verified:
                raise ValueError("The fixed integrity profile has no verified input attribution.")
        if early_checksum is not None:
            expected |= {"startupMethod": EARLY_METHOD, "editsWritten": 1121,
                         "earlyChecksumProfile": early_checksum.digest, "checksumAdmitted": True,
                         "checksumSitesRequired": 1069, "checksumEditsPrepared": 1079,
                         "checksumArena": early_checksum.arena, "checksumArenaBytes": 36864,
                         "nativeEditsRequired": 42, "combinedEditsRequired": 1121,
                         "checksumReapplication": False, "aaeStoreSitesPreserved": True,
                         "jobParentOnly": True, "killOnJobClose": True, "freezeAttempted": True,
                         "thawAttempted": True, "cleanupFailed": False, "relayFreed": False,
                         "runtimeMetadataMask": 3, "stage": "released", "refusalReason": "", "unwindReason": "",
                         "executableSha256": process.sha256}
    else:
        expected |= {"status": "ready", "activated": True}
    for name, value in expected.items():
        if type(session.get(name)) is not type(value) or session[name] != value:
            raise ValueError(f"Enhanced session receipt disagrees with {name}.")
    integer(session["helperBase"], "helper base", 1, (1 << 64) - 1)
    if origin is ReceiptOrigin.LATE:
        for name in ("primaryThreadId", "attachThread", "writeEventThread"):
            integer(session[name], name, 1, 0xFFFFFFFF)
        if session["attachThread"] != session["writeEventThread"]:
            raise ValueError("Late receipt write event differs from its attach thread.")
        for name in ("gateBase", "attachBreakpoint", "attachThreadEntry"):
            integer(session[name], name, 1, (1 << 64) - 1)
        integer(session["threadsObserved"], "observed thread count", 2, 0xFFFFFFFF)
    elif origin is ReceiptOrigin.JOB:
        integer(session["primaryThreadId"], "primary thread ID", 1, 0xFFFFFFFF)
        integer(session["gateBase"], "gate base", 1, (1 << 64) - 1)
        if integrity is not None or early_checksum is not None:
            integer(session["runtimeMetadataReads"], "runtime unwind metadata reads", 4, 64)
            for name in ("primaryPc", "relay"):
                integer(session[name], name, 1, (1 << 64)-1)
            frames = session["frames"]
            if not isinstance(frames, list) or not 1 <= len(frames) <= 64:
                raise ValueError("Integrity enrollment requires the recorded native wait frames.")
            for frame in frames:
                integer(frame, "native wait frame", 1, (1 << 64)-1)
            observations = session["threadObservations"]
            if not isinstance(observations, list) or len(observations) != 1:
                raise ValueError("Integrity enrollment requires one native primary observation.")
            observation = observations[0]
            if observation["threadId"] != session["primaryThreadId"] or observation["pc"] != session["primaryPc"]:
                raise ValueError("The integrity primary observation differs from its receipt.")
            integer(observation["threadId"], "observed primary thread", 1, 0xFFFFFFFF)
            integer(observation["start"], "observed primary entry", 1, (1 << 64)-1)
            if Path(session["imagePath"]).resolve() != process.path.resolve():
                raise ValueError("The integrity receipt executable path differs.")
    if session.get("exited", False) is not False or session.get("rollbackCompleted", False) is not False:
        raise ValueError("Enhanced session receipt records exit or rollback.")
    return session


def _helper(process: Process, profile: dict, session: dict, *, late: bool = False) -> Module:
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
    if session.get("startupMethod") in (_INTEGRITY_METHOD, EARLY_METHOD) and session["helperSha256"] != digest:
        raise ValueError("The integrity receipt helper hash differs from its loaded helper.")
    if (late and (profile["status"] != "fixture-only" or process.path.name.casefold() == "blackops3.exe")
            and digest != _LATE_HELPER_SHA256):
        raise ValueError("Late enrollment requires the deployed original VM helper.")
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
                             *, capacity_sites: tuple[CapacitySite, ...] | None = None,
                             integrity_profile: Path | None = None,
                             early_checksum_profile: Path | None = None) -> EnhancedSession | None:
    """Call after VerifiedProcess admission. Missing exact receipt means a stock session.

    Every existing but invalid/non-ready receipt refuses enrollment. No expanded pool is read.
    The inventory override exists only for fixture E2E; BlackOps3 always uses the fixed inventory.
    """
    directory = sessions_directory if sessions_directory is not None else (
        Path(os.environ["LOCALAPPDATA"]) / "BO3 Engine UnLimitations/sessions")
    selected = _selected_receipt(process, directory)
    if selected is None:
        return None
    path, before, origin = selected
    parsed = json.loads(before)
    integrity = (load_integrity_profile(process, profile, integrity_profile)
                 if isinstance(parsed, dict) and parsed.get("startupMethod") == _INTEGRITY_METHOD else None)
    early = (load_early_checksum(process, profile, parsed, early_checksum_profile)
             if isinstance(parsed, dict) and parsed.get("startupMethod") == EARLY_METHOD else None)
    session = _session(before, process, origin=origin, integrity=integrity, early_checksum=early)
    sites = _sites(process, profile, capacity_sites)
    helper = _helper(process, profile, session, late=origin is not ReceiptOrigin.LEGACY)
    first = _runtime(process, profile, helper, sites)
    publication = early if early is not None else integrity
    integrity_first = publication.verify(process) if publication is not None else None
    if (first != _runtime(process, profile, helper, sites)
            or (publication is not None and integrity_first != publication.verify(process))
            or _selected_receipt(process, directory) != selected or not process.alive()):
        raise ValueError("Enhanced evidence changed during enrollment.")
    return EnhancedSession(process.pid, process.started_ticks, process.module.baseaddress, helper.baseaddress,
                           path, sites, process, _fingerprint(profile), _SEAL, integrity, before, early)


def _verify_integrity_session(enrollment: EnhancedSession, profile: dict, process: Process) -> None:
    selected = _selected_receipt(process, enrollment.receipt_path.parent)
    if selected is None or selected[0] != enrollment.receipt_path or selected[1] != enrollment._receipt_data:
        raise ValueError("The enrolled integrity receipt changed.")
    path, before, origin = selected
    session = _session(before, process, origin=origin, integrity=enrollment.integrity, early_checksum=enrollment.early_checksum)
    helper = _helper(process, profile, session, late=True)
    first = _runtime(process, profile, helper, enrollment.capacity_sites)
    publication = enrollment.early_checksum if enrollment.early_checksum is not None else enrollment.integrity
    guards = publication.verify(process)
    if (first != _runtime(process, profile, helper, enrollment.capacity_sites)
            or guards != publication.verify(process)
            or _selected_receipt(process, path.parent) != selected or not process.alive()):
        raise ValueError("The enrolled integrity evidence changed during repeated reads.")


def verify_code_evidence(process: Process, profile: dict, enrollment: EnhancedSession | None = None) -> None:
    """Preserve stock hashes; normalize attested capacity immediates and verified checksum hooks."""
    sites: tuple[CapacitySite, ...] = ()
    if enrollment is not None:
        enrollment.authorize(profile, process)
        sites = enrollment.capacity_sites
        selected = _selected_receipt(process, enrollment.receipt_path.parent)
        if selected is None or selected[0] != enrollment.receipt_path:
            raise ValueError("The enrolled enhanced receipt route changed.")
        path, receipt_before, origin = selected
        session = _session(receipt_before, process, origin=origin, integrity=enrollment.integrity, early_checksum=enrollment.early_checksum)
        helper = _helper(process, profile, session, late=origin is not ReceiptOrigin.LEGACY)
        first = _runtime(process, profile, helper, sites)
    for evidence in profile.get("codeEvidence", []):
        start, end = int(evidence["startRva"], 0), int(evidence["endRva"], 0)
        if not 0 <= start < end <= process.module.size:
            raise ValueError("Invalid native code evidence range.")
        code = bytearray(process.read(process.module.baseaddress + start, end - start))
        if enrollment is not None:
            publication = enrollment.early_checksum if enrollment.early_checksum is not None else enrollment.integrity
            if publication is not None:publication.normalize(code, start)
        for site in sites:
            immediate = site.rva + site.immediate_offset
            low, high = max(start, immediate), min(end, immediate + 4)
            if low < high:
                stock = site.original[site.immediate_offset:site.immediate_offset + 4]
                code[low - start:high - start] = stock[low - immediate:high - immediate]
        if hashlib.sha256(code).hexdigest() != evidence["sha256"].casefold():
            raise ValueError("The live native code differs from the reviewed profile.")
    if enrollment is not None:
        if enrollment.integrity is not None or enrollment.early_checksum is not None:
            enrollment.authorize(profile, process)
        if (first != _runtime(process, profile, helper, sites)
                or _selected_receipt(process, path.parent) != selected or not process.alive()):
            raise ValueError("Enhanced runtime evidence changed during code verification.")
