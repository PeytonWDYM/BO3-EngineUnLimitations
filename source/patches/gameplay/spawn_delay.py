"""Remove the stock after-spawn pacing delay without changing saved settings.

Both counter branches retain the existing network-frame yield.
"""
from pathlib import Path

from patches.grenade_cleanup.fastfile_candidate import decode
from patches.gameplay.script_features import ScriptPlan, _apply, rebuild


NORMAL_SPAWN = ScriptPlan(
    b"scripts/zm/_zm.gsc\0", 126432,
    "4bc0bec345b2f08c0653d3884435f7bcbb5e794436c5178ce3b477fbd0ad50d5",
    (
        (0xDE34, bytes.fromhex("b3090e00"), bytes.fromhex("b3092000")),
        (0xDE3C, bytes.fromhex("cdcccc3d"), bytes(4)),
    ),
)


def apply(decoded: bytearray) -> dict:
    """Remove after-spawn delay and retain the separate pre-spawn waits."""
    return _apply(decoded, NORMAL_SPAWN)


def transform(source: bytes, resources: Path) -> bytes:
    """Transform the admitted stock Zombies patch fastfile in memory."""
    decoded, _ = decode(source)
    apply(decoded)
    return rebuild(source, decoded)
