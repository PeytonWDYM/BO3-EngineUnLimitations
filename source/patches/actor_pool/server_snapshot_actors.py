"""Keep server actor snapshot production and native ring ownership at one capacity."""
import hashlib
import json
from pathlib import Path
import struct

from captured_code import CapturedCode, CodeGuard, Rewrite
from shape import ActorShape
from x64_table import Emitter, continuation_jump

SERVER_SNAPSHOT_OWNER = (0x2200960, 0x2200DF8, 0x31B5EA8)
ROUNDED_ACTORS = 512
_PATH = Path(__file__).with_name('server_snapshot_guards.json')
_INVENTORY_SHA256 = '09c4e59f2e6d4f18e3e7c6ff612d7874369145bc59ba668754da2e6ba59b6839'
_INVENTORY = json.loads(_PATH.read_text())
OWNER_GUARDS = tuple(CodeGuard(row['rva'], row['size'], row['sha256']) for row in _INVENTORY['guards'])
# These four globals occupy the exact executable's loader-zeroed .data tail.
PREALLOCATION_GLOBALS = ((0x1767A408, 8), (0x1767A3C8, 4),
                        (0x1767A460, 8), (0x1767A3B0, 4))


def prepare_server_snapshot_actors(code: CapturedCode, shape: ActorShape,
                                   stub_address: int) -> tuple[Rewrite, ...]:
    """Expand both native allocations before publication and retain native history/reset/free paths."""
    if shape.actors != 500:
        raise ValueError('The server snapshot profile requires 500 actors.')
    inventory_bytes = json.dumps(json.loads(_PATH.read_text()), sort_keys=True, separators=(',', ':')).encode()
    if hashlib.sha256(inventory_bytes).hexdigest() != _INVENTORY_SHA256:
        raise ValueError('The server snapshot guard inventory differs.')
    if _INVENTORY['executableSha256'] != code.executable_sha256:
        raise ValueError('The server snapshot inventory has another executable identity.')
    for guard in OWNER_GUARDS:
        code.guarded(guard)
    edits = []
    # Native shifts size history and worker staging, then publish their actual counts.
    # The worker-result copier must use the same rounded staging stride.
    for name, rva, expected, replacement in (
        ('server_actor_history_capacity', 0x21F469A, 'c1e706', 'c1e709'),
        ('server_actor_staging_capacity', 0x21F47B5, 'c1e006', 'c1e009'),
        ('server_actor_staging_modulo', 0x220069F, 'c1e106', 'c1e109'),
        ('server_actor_worker_number_bits', 0x2201E74, 'ba06000000', 'ba09000000'),
    ):
        original = bytes.fromhex(expected)
        if code.read(rva, len(original)) != original:
            raise ValueError('A native server actor snapshot operand differs.')
        edits.append(Rewrite(name, code.guard(rva, len(original)), bytes.fromhex(replacement)))
    rva = 0x2200CE4
    original = bytes.fromhex('83ff400f8c15ffffff')
    if code.read(rva, len(original)) != original:
        raise ValueError('The native server actor snapshot loop differs.')
    emitter = Emitter(stub_address)
    emitter.put(b'\x81\xff' + struct.pack('<I', shape.actors))
    emitter.rip(b'\x0f\x8c', code.base + 0x2200C02)
    emitter.rip(b'\xe9', code.base + rva + len(original))
    edits.append(Rewrite('server_actor_snapshot_count', code.guard(rva, len(original)),
                         continuation_jump(code.base + rva, stub_address, len(original)),
                         stub_address, bytes(emitter.code)))
    return tuple(edits)
