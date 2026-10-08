"""Compose admitted AAE gameplay changes before one complete fastfile rebuild."""

import hashlib
from pathlib import Path

from patches.gameplay.script_features import apply_spawn_delay, rebuild
from patches.grenade_cleanup.fastfile_candidate import (
    SCRIPT_SIZE, SOURCE_HASH, change_script, decode, find_script,
)
from patches.weapon_tuning.weapon_tuning import apply_decoded
from patches.weapon_tuning.sprint_fire import apply_decoded as apply_sprint


def transform(source: bytes, resources: Path) -> bytes:
    """Compose cleanup, War Machine tuning, ordinary Stamin-Up sprint, and /spawn 0."""
    if hashlib.sha256(source).hexdigest() != SOURCE_HASH:
        raise ValueError("This full-AAE core asset is not a supported original.")
    decoded, _ = decode(source)
    start = find_script(decoded)
    cleanup, _ = change_script(decoded[start:start + SCRIPT_SIZE])
    decoded[start:start + SCRIPT_SIZE] = cleanup
    apply_spawn_delay(decoded)
    apply_sprint(decoded)
    desired = apply_decoded(decoded)
    return rebuild(source, desired)
