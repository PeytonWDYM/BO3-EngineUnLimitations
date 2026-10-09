"""Read an owned private Proton game's live pool; never attach a debugger or write game memory.

Run after the launcher commits and a map loads. Results describe one live snapshot,
not save compatibility, peer behavior, migration, or proof that every slot can be used.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True, help='Host Linux PID of the private BlackOps3.exe')
parser.add_argument('--game', type=Path, required=True, help='Private game executable')
parser.add_argument('--receipt', type=Path, required=True, help='Committed startup receipt from the private prefix')
parser.add_argument('--output', type=Path, required=True, help='New result file outside the repository')
args = parser.parse_args()
repo = Path(__file__).resolve().parents[3]
output = args.output.resolve()
if output.is_relative_to(repo) or output.exists():
    raise SystemExit('Use a new result file outside the repository.')
inventory = json.loads((repo / 'source/patches/vm_pool/exact_build_inventory.json').read_text())
receipt = json.loads(args.receipt.read_text())
assert receipt['committed'] and receipt['released'] and receipt['checksumAdmitted'], 'Startup was not admitted and released.'
intro_skipped = receipt.get('startupIntroSkipped', False)
assert type(intro_skipped) is bool, 'Invalid startup intro receipt.'
assert receipt['nativeEditsRequired'] == 42 + int(intro_skipped), 'Incomplete native transaction.'
assert receipt['editsWritten'] == receipt['combinedEditsRequired'] == 1121 + int(intro_skipped), 'Incomplete startup transaction.'
with args.game.open('rb') as game:
    digest = hashlib.file_digest(game, 'sha256').hexdigest()
assert digest == receipt['executableSha256'], 'Private executable differs from the launch receipt.'
base = receipt['imageBase']
proc = Path('/proc') / str(args.pid)
start = proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19]
command = proc.joinpath('cmdline').read_bytes().split(b'\0')[0].decode()
expected = 'Z:' + str(args.game.resolve()).replace('/', '\\')
assert command.casefold() == expected.casefold(), 'PID is outside the selected private game path.'
with proc.joinpath('mem').open('rb', buffering=0) as memory:
    def read(address, size):
        memory.seek(address)
        data = memory.read(size)
        assert len(data) == size, 'Incomplete live memory read.'
        return data

    def pointer(rva):
        return struct.unpack('<Q', read(base + rva, 8))[0]

    assert read(base, 2) == b'MZ', 'Image base differs.'
    pe = struct.unpack('<I', read(base + 0x3c, 4))[0]
    assert 64 <= pe <= inventory['imageSize'] - 264, 'Invalid PE offset.'
    header = read(base + pe, 264)
    assert header[:4] == b'PE\0\0' and struct.unpack_from('<H', header, 4)[0] == 0x8664
    assert struct.unpack_from('<I', header, 8)[0] == inventory['timestamp']
    assert struct.unpack_from('<H', header, 24)[0] == 0x20b
    assert struct.unpack_from('<I', header, 80)[0] == inventory['imageSize']
    if intro_skipped:
        assert read(base + 0x20f00a1, 5) == bytes.fromhex('33c0909090'), 'Startup intro edit differs.'
    counts = []
    for instruction in inventory['serverCountInstructions']:
        original = bytes.fromhex(instruction['bytes'])
        replacement = bytearray(original)
        offset = instruction['immediateOffset']
        replacement[offset:offset + 4] = struct.pack('<I', 500001)
        actual = read(base + instruction['rva'], len(original))
        assert actual == replacement, 'A complete server-count instruction differs.'
        counts.append(struct.unpack_from('<I', actual, offset)[0])
    assert len(counts) == 19
    pool, buckets = pointer(inventory['poolPointerRva']), pointer(inventory['hashPointerRva'])
    assert pool and buckets, 'Server pool is not allocated yet.'
    slots = read(pool, 500001 * 64)
    hashes = read(buckets, 500001 * 4)
    head = struct.unpack_from('<I', slots, 24)[0]
    assert pointer(inventory['poolPointerRva']) == pool and pointer(inventory['hashPointerRva']) == buckets
    assert read(pool + 24, 4) == struct.pack('<I', head), 'Pool changed while reading; retry.'
    current, seen = head, set()
    while current:
        assert 0 < current < 500001 and current not in seen, 'Invalid free-slot chain.'
        assert struct.unpack_from('<I', slots, current * 64 + 8)[0] == 27, 'Chain references an occupied slot.'
        seen.add(current)
        current = struct.unpack_from('<I', slots, current * 64 + 24)[0]
    declared = sum(struct.unpack_from('<I', slots, index * 64 + 8)[0] == 27 for index in range(1, 500001))
    assert len(seen) == declared, 'Free-slot chain is incomplete; retry during a quiet game state.'
assert proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19] == start, 'PID identity changed.'
result = {
    'checkedAtUtc': datetime.now(timezone.utc).isoformat(), 'passed': True, 'pid': args.pid,
    'processStartTicks': start, 'executableSha256': digest, 'receipt': str(args.receipt.resolve()),
    'serverCountInstructionsVerified': len(counts), 'serverTotal': 500001, 'serverUsable': 500000,
    'serverPoolBytesReadable': len(slots), 'serverHashBytesReadable': len(hashes),
    'freeSlots': len(seen), 'expandedFreeSlots': sum(index >= 130000 for index in seen),
    'highestFreeSlot': max(seen, default=0), 'poolAddress': pool, 'hashAddress': buckets,
    'startupIntroSkipped': intro_skipped,
    'scope': 'Read-only live allocation and free-chain snapshot. No game memory or files changed. No save or peer validation.',
}
with output.open('x') as target:
    json.dump(result, target, indent=2)
    target.write('\n')
print(f"500K pool verified: {len(slots)} slot bytes, {len(hashes)} hash bytes, {len(seen)} free slots.")
