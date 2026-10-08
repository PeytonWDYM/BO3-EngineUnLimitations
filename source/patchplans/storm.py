"""Bind the Storm Bow transform to the inspected Der Eisendrache asset."""

import hashlib
from pathlib import Path

from patches.gameplay.script_features import transform_storm


ORIGINAL_SHA256 = "06f95fa4a2826d26747a54c8b13484c1067b379c9c8f0887f706a9f1431e7138"


def transform(source: bytes, resources: Path) -> bytes:
    if hashlib.sha256(source).hexdigest() != ORIGINAL_SHA256:
        raise ValueError("This Der Eisendrache asset is not a supported original.")
    return transform_storm(source, resources)
