"""Prepare only the native pose restore. Producers, save framing, and activation remain gated."""
import struct

from captured_code import CapturedCode, CodeGuard, Rewrite
from temporal_layout import TemporalLayout
from x64_table import Emitter, continuation_jump

RESTORE_FUNCTION = CodeGuard(0x1BDEF50, 0xA6, 'b3885b7ab2ec36e3d62d15fcf326ee726557488931a3e27b43d7038853c80872')


def prepare_restore(code: CapturedCode, layout: TemporalLayout, stub_address: int) -> tuple[Rewrite, ...]:
    code.guarded(RESTORE_FUNCTION)
    prefix = code.guarded(CodeGuard(0x1BDEF64, 19, 'e99cd7c7ab82d4de187100ab0359819f0dd138279eb5fc5bc84d7075f98b33c5'))
    emitter = Emitter(stub_address)
    emitter.put(b'\x33\xf6\x48\x8d\xb9' + struct.pack('<I', layout.output_valid_offset))
    emitter.put(b'\x48\x8d\x99' + struct.pack('<I', layout.vector_bytes + 8))
    emitter.put(b'\xbd' + struct.pack('<I', layout.shape.actors))
    # The native loop returns to its compare at 0x1BDEF77. Keep that instruction in place.
    emitter.rip(b'\xe9', code.base + 0x1BDEF77)
    hook = continuation_jump(code.base+0x1BDEF64,stub_address,len(prefix))
    edits = [Rewrite('temporal_restore_prefix', code.guard(0x1BDEF64, len(prefix)), hook, stub_address, bytes(emitter.code))]
    for rva, displacement in ((0x1BDEF88, -layout.vector_bytes - 8),
                              (0x1BDEF94, -layout.vector_bytes - 4), (0x1BDEFA0, -layout.vector_bytes)):
        original = code.read(rva, 6)
        edits.append(Rewrite('temporal_restore_vector_offset', code.guard(rva, 6), original[:2] + struct.pack('<i', displacement)))
    return tuple(edits)
