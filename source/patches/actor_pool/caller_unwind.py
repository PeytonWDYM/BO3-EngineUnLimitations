"""Prepare the guarded caller's frame metadata. Native handler dispatch remains gated."""
import struct

from captured_code import CapturedCode, CodeGuard, Rewrite
from native_unwind import read_frame
from temporal_caller import CALLER_FUNCTION, caller_frame
from temporal_layout import TemporalLayout

CALLER_UNWIND = CodeGuard(0x31480F0, 80, '0bd9ef33a28f7ba3a903dc9e500a7916396bc17dc51dbc8854c76dd2acbe796b')
FUNCTION_INFO = CodeGuard(0x2F4CD20, 40, 'a67285027f0266e278c516a6516e4a887d97c517cbb7616c52f949f692eafd71')
CLEANUP_MAP = CodeGuard(0x3148140, 8, '06e0d1924395153b6c8abc8f1f0c1a387e362997ebc830ee118a5ecb37c9cd6b')
STATE_MAP = CodeGuard(0x3148148, 24, '77ef13ab19b3171650653e91f0f6bca49757e15dbbe2cb4e16b9f470209ed67b')
CLEANUP_LEAF = CodeGuard(0x2C576C0, 12, '8ff17454127ddbc0cc32c6d0f1de1433f8a096cbb628edd94c3a33477224e63b')


def prepare_caller_unwind(code: CapturedCode, layout: TemporalLayout) -> Rewrite:
    code.guarded(CALLER_FUNCTION)
    for guard in (FUNCTION_INFO, CLEANUP_MAP, STATE_MAP, CLEANUP_LEAF):
        code.guarded(guard)
    metadata = bytearray(code.guarded(CALLER_UNWIND))
    native = read_frame(code, (CALLER_FUNCTION.rva, CALLER_FUNCTION.rva + CALLER_FUNCTION.size, CALLER_UNWIND.rva))
    frame = caller_frame(layout)
    slot = saves = allocations = 0
    for operation in native.operations:
        position = 4 + slot * 2
        if operation.opcode == 1:
            if operation.info or operation.allocation != 0x3DD0:
                raise ValueError('The caller allocation differs from its researched frame.')
            struct.pack_into('<H', metadata, position + 2, frame.allocation // 8)
            allocations += 1
        elif operation.opcode in (4, 8):
            scale = 16 if operation.opcode == 8 else 8
            struct.pack_into('<H', metadata, position + 2, operation.value + frame.growth // scale)
            saves += 1
        elif operation.opcode != 0:
            raise ValueError('The caller has an unclassified native unwind operation.')
        slot += 2 if operation.opcode in (1, 4, 8) else 1
    if (slot, saves, allocations) != (31, 11, 1):
        raise ValueError('The caller unwind inventory differs from its researched frame.')
    # The sole cleanup still receives the low-frame object at body RSP+0xD0.
    # In-place instruction sizes preserve the native C++ IP/state map and helper offset at RSP+0x70.
    cookie_word = struct.unpack_from('<I', metadata, 76)[0]
    struct.pack_into('<I', metadata, 76, (frame.cookie + 0x100) | (cookie_word & 7))
    return Rewrite('temporal_caller_unwind', CALLER_UNWIND, bytes(metadata))
