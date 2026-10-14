"""Prepare original level clear plus external history reset. Live registration remains required."""
from dataclasses import dataclass
import struct

from captured_code import CapturedCode, CodeGuard, Rewrite
from temporal_layout import TemporalLayout
from x64_table import rel32

LEVEL_CLEAR = CodeGuard(0x19D160D, 20, '133653893a66bcde6c880e42018fb4945063c37a38d6fd05d14449bb51a668e4')
LEVEL_CLEAR_CALL = CodeGuard(0x19D161C, 5, 'eb427c876c31ed917cc56d3003e2afec1cd340322f9dff277d534368ac36bb61')


@dataclass(frozen=True)
class CalledHistoryReset:
    rewrite: Rewrite
    metadata: bytes


def prepare_history_reset(code: CapturedCode, layout: TemporalLayout, history_address: int,
                          stub_address: int) -> CalledHistoryReset:
    """Use a called function with its own frame, retaining the original memset and return value."""
    regions = ((history_address, layout.history_bytes), (stub_address, 4096))
    for start, size in regions:
        if (start < 0x10000 or start % 16 or start + size > 2**64
                or not (start + size <= code.base or start >= code.base + code.meta['imageSize'])):
            raise ValueError('The complete reset storage and stub must be aligned and outside the native image.')
    ordered = sorted(regions)
    if ordered[0][0] + ordered[0][1] > ordered[1][0]:
        raise ValueError('The temporal history overlaps its called reset stub.')
    code.guarded(LEVEL_CLEAR)
    code.guarded(LEVEL_CLEAR_CALL)
    native_clear = code.base + 0x2BC53B0
    body = bytearray(b'\x48\x83\xEC\x28')
    body += b'\xE8' + rel32(stub_address + len(body) + 5, native_clear)
    body += b'\x48\xB9' + struct.pack('<Q', history_address)
    body += b'\x33\xD2\x41\xB8' + struct.pack('<I', layout.history_bytes)
    body += b'\xE8' + rel32(stub_address + len(body) + 5, native_clear)
    body += b'\x48\xB8' + struct.pack('<Q', code.base + 0xA1B0730)
    body += b'\x48\x83\xC4\x28\xC3'
    hook = b'\xE8' + rel32(code.base + LEVEL_CLEAR_CALL.rva + 5, stub_address)
    rewrite = Rewrite('temporal_history_level_reset', LEVEL_CLEAR_CALL, hook, stub_address, bytes(body))
    # A regular called function needs ALLOC_SMALL40, rather than a continuation's inherited native frame.
    return CalledHistoryReset(rewrite, bytes.fromhex('0104010004420000'))
