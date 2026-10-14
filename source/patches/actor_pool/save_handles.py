"""Keep native typed save handles within the selected actor and sentient load shape."""
from captured_code import CapturedCode, CodeGuard, Rewrite
from load_counts import LoadCounts
import struct
from x64_table import Emitter, continuation_jump

OWNER_GUARDS = (
    CodeGuard(0xC0410, 15808, '68a1ab4775b1c498c2b2fcb6dbc18c20b6ec9c2713e6aa806c9d3f0bb7f509a7'),
    CodeGuard(0xCF8C0, 8452, '421e1e5ce664e47857940df04a315e1db2b81b7ba8748c123533a310ad4a23ff'),
    CodeGuard(0xC40C0, 152, 'f32c6491cabc5d50fe1d5fef1b3b268e47d1fdf2e06bbc538fa08bf8d21486a3'),
    CodeGuard(0xD18F0, 152, '6460a12b93329d581d1c41178365341db399240ade3ffd23976bf1cbbbd12b4a'),
    CodeGuard(0xD2870, 98, '84f3d6110173a3530bd61d94c394cb354f188fc4e232fb7302307c74d157c5fc'),
)


def prepare_save_handles(code: CapturedCode, counts: LoadCounts, stub_address: int) -> tuple[Rewrite, ...]:
    """Readers use admitted legacy/expanded counts. Writers emit the existing expanded four-byte format."""
    for guard in OWNER_GUARDS:
        code.guarded(guard)
    edits = []
    for index, (name, source, original, accepted, sentient, reader, nullable) in enumerate((
        ('actor_pointer_read_bound', 0xC3C90, '83fb40761d33d2', 0xC3CB2, False, True, False),
        ('sentient_pointer_read_bound', 0xC3CEF, '83fb68761d33d2', 0xC3D11, True, True, False),
        ('actor_pointer_write_bound', 0xD166F, '83fb400f86e1e2ffff', 0xCF959, False, False, False),
        ('sentient_pointer_write_bound', 0xD16B7, '83fb680f8699e2ffff', 0xCF959, True, False, False),
        ('sentient_handle_read_bound', 0xC1F0B, '83fb68761d33d2', 0xC1F2D, True, True, True),
        ('sentient_handle_write_bound', 0xCF9B2, '83fb6876a24c8d0daac2e402', 0xCF959, True, False, False),
    )):
        expected = bytes.fromhex(original)
        if code.read(source, len(expected)) != expected:
            raise ValueError('A native typed save-handle bound differs.')
        address = stub_address + index * 128
        emitter = Emitter(address)
        if reader:
            # The secondary count is also the actor count. The sentient pool reserves forty additional rows.
            emitter.rip(b'\x8b\x05', counts.base + 16)
            if sentient:
                emitter.put(bytes.fromhex('83c028'))
            if nullable:
                emitter.put(bytes.fromhex('39c3'))
            else:
                emitter.put(bytes.fromhex('8d4bff39c1'))
        else:
            emitter.put(bytes.fromhex('8d4bff81f9') + (540 if sentient else 500).to_bytes(4, 'little'))
        # A nonnull pointer stores index + 1. Subtract one before an unsigned comparison to refuse zero.
        emitter.rip(b'\x0f\x86' if nullable else b'\x0f\x82', code.base + accepted)
        if reader:
            emitter.put(bytes.fromhex('33d2'))
        elif source == 0xCF9B2:
            emitter.rip(bytes.fromhex('4c8d0d'), code.base + source + len(expected) + struct.unpack_from('<i', expected, 8)[0])
        emitter.rip(b'\xe9', code.base + source + len(expected))
        replacement = continuation_jump(code.base + source, address, len(expected))
        edits.append(Rewrite(name, code.guard(source, len(expected)), replacement, address, bytes(emitter.code)))
    return tuple(edits)
