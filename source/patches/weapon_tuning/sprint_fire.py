"""Use ordinary Stamin-Up ownership for the existing sprint-fire eligibility branch.

This changes one eligibility query across weapons. It does not grant a perk to players
outside AAE's existing Stamin-Up, beast-mode, or shock-hands eligibility branch.
"""
import hashlib
import struct
from .weapon_tuning import WeaponEdit

SCRIPT_NAME = b'scripts/zm/motherfucker.gsc\0'
SCRIPT_SIZE = 212348
SCRIPT_HASH = '245c7d155b6a87a088e1744887157de058f2839a492d3de50449f51be29b223d'
TARGET_OFFSET = 0x2ADBC
EXPECTED = bytes.fromhex('01426e3a8fe03c5401000104')
REPLACEMENT = bytes.fromhex('cf2f54885ce7d7d401000124')


def planned_edits(decoded: bytes | bytearray) -> tuple[WeaponEdit, ...]:
    """Validate before composition and return the fixed-size import-target edit."""
    starts = []
    cursor = 0
    magic = bytes.fromhex('804753430d0a001c')
    while (cursor := decoded.find(magic, cursor)) != -1:
        start = cursor
        cursor += len(magic)
        script = bytes(decoded[start:start + SCRIPT_SIZE])
        if len(script) != SCRIPT_SIZE:
            continue
        name_offset = struct.unpack_from('<I', script, 52)[0]
        if script[name_offset:name_offset + len(SCRIPT_NAME)] != SCRIPT_NAME:
            continue
        canonical = bytearray(script)
        # Permit the independently verified literal-zero spawn command edit.
        if canonical[0x1864E:0x18652] == bytes.fromhex('bd362c00'):
            canonical[0x1864E:0x18652] = bytes.fromhex('0e20e32d')
        if hashlib.sha256(canonical).hexdigest() == SCRIPT_HASH:
            starts.append(start)
    if len(starts) != 1:
        raise ValueError('The exact original or admitted zero-delay commands script is absent or repeated.')
    start = starts[0]
    script = decoded[start:start + SCRIPT_SIZE]
    # Both imports are one-argument methods. The existing native method namespace
    # and resolution flags replace the external upgrade query for this one reference.
    if script[TARGET_OFFSET:TARGET_OFFSET + 16] != bytes.fromhex('01426e3a8fe03c54010001041ef50000'):
        raise ValueError('The Stamin-Up upgrade-query import differs from the inspected source.')
    if script[0x2B6DC:0x2B6EC] != bytes.fromhex('cf2f54885ce7d7d4010001240e170100'):
        raise ValueError('The existing hasperk prototype differs from the inspected source.')
    return (WeaponEdit('ordinary Stamin-Up owners', 'staminupEligibilityImport', start + TARGET_OFFSET, EXPECTED, REPLACEMENT),)


def apply_decoded(decoded: bytearray) -> dict:
    """Change one ownership query; preserve code, grant/removal wrappers and tables."""
    edit, = planned_edits(decoded)
    decoded[edit.offset:edit.offset + len(edit.expected)] = edit.replacement
    return {'script': SCRIPT_NAME[:-1].decode(), 'scriptStart': edit.offset - TARGET_OFFSET,
            'field': edit.field, 'offset': edit.offset, 'before': edit.expected.hex(),
            'after': edit.replacement.hex(), 'scope': 'ordinary Stamin-Up sprint-fire/unlimited-sprint eligibility across weapons',
            'codeAndTableLengthsPreserved': True}
