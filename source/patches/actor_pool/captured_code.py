"""Read exact captured code and describe guarded owned rewrites."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


@dataclass(frozen=True)
class CodeGuard:
    rva: int
    size: int
    sha256: str


@dataclass(frozen=True)
class Rewrite:
    name: str
    guard: CodeGuard
    replacement: bytes
    stub_address: int | None = None
    stub: bytes = b''
    owner_register: str | None = None


class CapturedCode:
    def __init__(self, manifest: Path):
        self.manifest = manifest
        self.meta = json.loads(manifest.read_text())
        self.base = int(self.meta['baseAddress'],0)
        self.cache: dict[str, bytes] = {}

    def read(self, rva: int, size: int) -> bytes:
        item = next(r for r in self.meta['ranges'] if int(r['moduleOffset'],0) <= rva
                    and rva+size <= int(r['moduleOffset'],0)+r['size'])
        name = item['file']
        if name not in self.cache:
            raw = (self.manifest.parent/name).read_bytes()
            if len(raw) != item['size'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
                raise ValueError('A captured range differs from its recorded source guard.')
            self.cache[name] = raw
        offset = rva-int(item['moduleOffset'],0)
        return self.cache[name][offset:offset+size]

    def guarded(self, guard: CodeGuard) -> bytes:
        raw = self.read(guard.rva,guard.size)
        if hashlib.sha256(raw).hexdigest() != guard.sha256:
            raise ValueError(f'The native guard differs at RVA {guard.rva:#x}.')
        return raw

    def guard(self, rva: int, size: int) -> CodeGuard:
        return CodeGuard(rva,size,hashlib.sha256(self.read(rva,size)).hexdigest())
