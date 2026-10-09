"""Verify the fixed integrity profile through read-only, repeated live image reads."""
from dataclasses import dataclass
from bisect import bisect_left
import hashlib
import json
from pathlib import Path
import struct

from profile import integer

GAME_SHA256 = "0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0"
ORIGINAL = {"Xor": bytes.fromhex("8b0c8b330c82"), "NegAdd": bytes.fromhex("8b0c8bf7d9030c82"),
            "Compare": bytes.fromhex("8b04828b148b3bc2"), "InputTransform": bytes.fromhex("8b0c8b330c82")}
REPLACEMENT = {"Xor": bytes.fromhex("8b0c8b31c990"), "NegAdd": bytes.fromhex("8b0c8b31c9909090"),
               "Compare": bytes.fromhex("8b04828b148b3bc0")}


def _digest(value: str) -> bytes:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("An integrity SHA-256 digest is invalid.")
    result = bytes.fromhex(value)
    if len(result) != 32:
        raise ValueError("An integrity SHA-256 digest is invalid.")
    return result


@dataclass(frozen=True)
class Endpoint:
    rva: int
    original: bytes
    replacement: bytes


@dataclass(frozen=True)
class Guard:
    rva: int
    size: int
    digest: bytes
    image_addresses: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class IntegrityProfile:
    digest: str
    original_digest: str
    replacement_digest: str
    attribution_verified: bool
    endpoints: tuple[Endpoint, ...]
    retained: tuple[tuple[int, bytes], ...]
    guards: tuple[Guard, ...]
    windows: tuple[tuple[int, int], ...]

    def normalize(self, code: bytearray, start: int) -> None:
        """Restore only admitted endpoint suffixes for original code-evidence hashes."""
        index = max(0, bisect_left(self.endpoints, start, key=lambda row: row.rva)-1)
        for index in range(index,len(self.endpoints)):
            endpoint = self.endpoints[index]
            if endpoint.rva >= start + len(code):
                break
            low, high = max(start, endpoint.rva), min(start + len(code), endpoint.rva + len(endpoint.original))
            if low < high:
                if code[low-start:high-start] != endpoint.replacement[low-endpoint.rva:high-endpoint.rva]:
                    raise ValueError("A live integrity endpoint changed during normalization.")
                code[low-start:high-start] = endpoint.original[low-endpoint.rva:high-endpoint.rva]

    def verify(self, process) -> bytes:
        """Coalesce fixed guard ranges. This read does not stop or change any thread."""
        base = process.module.baseaddress
        reads = tuple(process.read(base + start, end - start) for start, end in self.windows)
        signature = hashlib.sha256()
        for row in reads:
            signature.update(row)
        window = 0
        for guard in self.guards:
            while self.windows[window][1] <= guard.rva:
                window += 1
            start, end = self.windows[window]
            if not start <= guard.rva < guard.rva + guard.size <= end:
                raise ValueError("An integrity guard is outside its fixed read window.")
            code = bytearray(reads[window][guard.rva-start:guard.rva-start+guard.size])
            self.normalize(code, guard.rva)
            for offset, target in guard.image_addresses:
                if struct.unpack_from("<Q", code, offset)[0] != base + target:
                    raise ValueError("A live integrity image address differs.")
                code[offset:offset+8] = b"\0" * 8
            if hashlib.sha256(code).digest() != guard.digest:
                raise ValueError("A live integrity instruction or context guard differs.")
        return signature.digest()


def load_integrity_profile(process, profile: dict, supplied: Path | None = None) -> IntegrityProfile:
    """Retain the comparison prototype for owned fixtures. Never enroll its game route."""
    if supplied is None:
        raise ValueError("The retired comparison route cannot enroll game monitoring.")
    if (profile["status"] != "fixture-only" or process.path.name.casefold() == "blackops3.exe"
            or process.sha256 == GAME_SHA256):
        raise ValueError("Integrity profile overrides are limited to exact owned fixtures.")
    data = supplied.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if _digest(profile["integrityFixtureSha256"]) != hashlib.sha256(data).digest():
        raise ValueError("The fixed integrity profile differs from its pinned digest.")
    manifest = json.loads(data)
    if (manifest["executableSha256"] != process.sha256 or manifest["timestamp"] != process.module.timestamp
            or manifest["imageSize"] != process.module.size):
        raise ValueError("The integrity profile does not identify this exact executable.")
    if manifest["module"].casefold() != process.path.name.casefold():
        raise ValueError("The owned integrity module name differs.")
    counts = {"schema": 1, "patternCount": 1365, "editCount": 1353, "retainedTransformCount": 12}
    if any(type(manifest.get(key)) is not int or manifest[key] != value for key, value in counts.items()):
        raise ValueError("The integrity inventory counts differ.")
    if type(manifest["productionInputAttributionVerified"]) is not bool:
        raise ValueError("The integrity input-attribution flag is invalid.")
    regions = tuple((integer(row["rva"], "integrity region RVA", 0, process.module.size-1),
                     integer(row["size"], "integrity region size", 1, process.module.size-row["rva"]))
                    for row in manifest["regions"])
    if len(regions) != 2 or any(a < b+s and b < a+n for i, (a,n) in enumerate(regions) for b,s in regions[i+1:]):
        raise ValueError("Both disjoint integrity code regions are required.")
    def guard_for(row, record=False):
        size = integer(row["guardSize" if record else "size"], "integrity guard width", 1, 256)
        rva = integer(row["rva"], "integrity guard RVA", 0, process.module.size-size)
        if not any(start <= rva and rva+size <= start+length for start, length in regions):
            raise ValueError("An integrity guard exceeds its fixed code regions.")
        addresses = []
        for field in row["imageAddresses"]:
            offset = integer(field["offset"], "integrity image address offset", 0, size-8)
            target = integer(field["targetRva"], "integrity image address target", 0, process.module.size-1)
            if addresses and addresses[-1][0]+8 > offset:
                raise ValueError("Integrity image address fields overlap or are unordered.")
            addresses.append((offset,target))
        if len(addresses) > 2:
            raise ValueError("The integrity image address inventory exceeds its bound.")
        return Guard(rva,size,_digest(row["guardSha256" if record else "sha256"]),tuple(addresses))
    endpoints, retained, guards, families = [], [], [], {name: 0 for name in ORIGINAL}
    originals, replacements = hashlib.sha256(), hashlib.sha256()
    previous_end = 0
    if len(manifest["sites"]) != 1365 or not manifest["contextGuards"]:
        raise ValueError("The complete integrity site and context inventories are required.")
    for row in manifest["sites"]:
        family = row["family"]
        original = ORIGINAL[family]
        expected_flags = "ZeroCarry" if family == "Compare" else "Zero"
        if row["liveFlags"] != expected_flags:
            raise ValueError("The integrity endpoint flags differ.")
        guard = guard_for(row,True)
        if (guard.size < len(original) or guard.rva < previous_end
                or any(offset < len(original) for offset, _ in guard.image_addresses)):
            raise ValueError("Integrity instructions overlap or contain an invalid address field.")
        previous_end = guard.rva + len(original)
        guards.append(guard)
        families[family] += 1
        if family == "InputTransform":
            retained.append((guard.rva,original))
        else:
            offset = 6 if family == "Compare" else 3
            endpoint = Endpoint(guard.rva+offset,original[offset:],REPLACEMENT[family][offset:])
            endpoints.append(endpoint)
            header = struct.pack("<II",endpoint.rva,len(endpoint.original))
            originals.update(header+endpoint.original)
            replacements.update(header+endpoint.replacement)
    if families != {"Xor":247,"NegAdd":259,"Compare":847,"InputTransform":12}:
        raise ValueError("The integrity evaluator family counts differ.")
    guards.extend(guard_for(row) for row in manifest["contextGuards"])
    guards.sort(key=lambda row: row.rva)
    windows = []
    for guard in guards:
        end = guard.rva+guard.size
        if windows and guard.rva <= windows[-1][1]+64 and end-windows[-1][0] <= 4096:
            windows[-1] = (windows[-1][0],max(windows[-1][1],end))
        elif windows and guard.rva < windows[-1][1]:
            windows[-1] = (windows[-1][0],max(windows[-1][1],end))
        else:
            windows.append((guard.rva,end))
    return IntegrityProfile(digest,originals.hexdigest(),replacements.hexdigest(),
                            manifest["productionInputAttributionVerified"],tuple(endpoints),tuple(retained),
                            tuple(guards),tuple(windows))
