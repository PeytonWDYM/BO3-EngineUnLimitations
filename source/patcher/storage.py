"""Publish complete, flushed files with a same-directory atomic replacement."""
import os
from pathlib import Path
import uuid

from patcher.paths import reject_redirects


def durable_write(path: Path, data: bytes) -> None:
    reject_redirects(path)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def replace_bytes(path: Path, data: bytes) -> None:
    reject_redirects(path)
    temporary = path.with_name(path.name + ".bo3patch-" + uuid.uuid4().hex)
    try:
        durable_write(temporary, data)
        reject_redirects(path)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
