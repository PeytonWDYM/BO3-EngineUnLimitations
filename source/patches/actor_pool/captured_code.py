"""Read exact captured code and describe guarded owned rewrites."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

EXECUTABLE_SHA256 = '0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0'
MANIFEST_SHA256 = '01d292edca086aeca406a9171feba2dac8aea80df2e867026ff78f441bab4511'


def executable_identity(path: Path) -> str:
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream,'sha256').hexdigest()
    if digest != EXECUTABLE_SHA256:
        raise ValueError('The executable does not match the admitted SHA-256.')
    return digest


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
    def __init__(self, manifest: Path, executable: Path):
        self.executable_sha256 = executable_identity(executable)
        if hashlib.sha256(manifest.read_bytes()).hexdigest() != MANIFEST_SHA256:
            raise ValueError('The module manifest does not match the pinned private capture.')
        self.manifest = manifest
        self.meta = json.loads(manifest.read_text())
        self.base = int(self.meta['baseAddress'],0)
        if (self.meta['imageSize'],self.meta['timestamp']) != (494186496,1765634846):
            raise ValueError('The capture has an unsupported native layout.')
        self.cache: dict[str, bytes] = {}

    def read(self, rva: int, size: int) -> bytes:
        if rva < 0 or size <= 0 or rva+size > self.meta['imageSize']:
            raise ValueError('The requested captured interval is outside the native image.')
        chunks = []
        position = rva
        while position < rva+size:
            item = next((item for item in self.meta['ranges']
                         if int(item['moduleOffset'],0)<=position<int(item['moduleOffset'],0)+item['size']),None)
            if item is None:
                raise ValueError('The requested captured interval contains a missing range.')
            name = item['file']
            if name not in self.cache:
                raw = (self.manifest.parent/name).read_bytes()
                if len(raw) != item['size'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
                    raise ValueError('A captured range differs from its recorded source guard.')
                self.cache[name] = raw
            offset = position-int(item['moduleOffset'],0)
            count = min(item['size']-offset,rva+size-position)
            chunks.append(self.cache[name][offset:offset+count])
            position += count
        return b''.join(chunks)

    def guarded(self, guard: CodeGuard) -> bytes:
        raw = self.read(guard.rva,guard.size)
        if hashlib.sha256(raw).hexdigest() != guard.sha256:
            raise ValueError(f'The native guard differs at RVA {guard.rva:#x}.')
        return raw

    def guard(self, rva: int, size: int) -> CodeGuard:
        return CodeGuard(rva,size,hashlib.sha256(self.read(rva,size)).hexdigest())
