"""Read pinned private captures. This module does not open a game process."""
import hashlib
import json
from pathlib import Path


EXACT_EXECUTABLE = "0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0"
EXACT_MANIFEST = "01d292edca086aeca406a9171feba2dac8aea80df2e867026ff78f441bab4511"
EXACT_NATIVE_CODE = "ea5fec6d262eaf01c2c9e83bae33e1d53a44f48807661869cf6785ad592afc04"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class NativeCapture:
    def __init__(self, manifest: Path, executable: Path):
        require(file_digest(executable) == EXACT_EXECUTABLE, "Unknown executable. Audit refused.")
        require(file_digest(manifest) == EXACT_MANIFEST, "Unknown capture manifest. Audit refused.")
        self.root = manifest.parent
        self.metadata = json.loads(manifest.read_text(encoding="utf-8"))
        require(self.metadata["timestamp"] == 1765634846
                and self.metadata["imageSize"] == 494186496, "The capture PE identity differs.")
        self.base = int(self.metadata["baseAddress"], 0)
        self.ranges = [(int(row["moduleOffset"], 0), row) for row in self.metadata["ranges"]]
        self.cache = {}
        self.code = self.read(0x12d9000, 0x8000)
        require(hashlib.sha256(self.code).hexdigest() == EXACT_NATIVE_CODE, "The native code capture differs.")

    def read(self, rva: int, size: int) -> bytes:
        output = bytearray()
        while len(output) < size:
            offset = rva + len(output)
            start, row = next((start, row) for start, row in self.ranges
                              if start <= offset < start + row["size"])
            name = row["file"]
            if name not in self.cache:
                data = (self.root / name).read_bytes()
                require(len(data) == row["size"] and hashlib.sha256(data).hexdigest() == row["sha256"],
                        "A captured range changed or is incomplete.")
                self.cache[name] = data
            begin = offset - start
            output.extend(self.cache[name][begin:begin + size - len(output)])
        return bytes(output)
