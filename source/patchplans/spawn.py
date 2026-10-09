"""Bind automatic normal-spawn pacing to the inspected stock Zombies asset."""

import hashlib
from pathlib import Path

from patches.gameplay.spawn_delay import transform as transform_spawn


ORIGINAL_SHA256 = "ed2134e10b1f57812bf8662926a269962a75b44d377cb5cca9245e86f2194a05"


def transform(source: bytes, resources: Path) -> bytes:
    if hashlib.sha256(source).hexdigest() != ORIGINAL_SHA256:
        raise ValueError("This Zombies patch asset is not a supported original.")
    return transform_spawn(source, resources)
