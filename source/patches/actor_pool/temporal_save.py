"""Prepare temporal save framing. Root format binding and complete game saves remain required."""
from dataclasses import dataclass
from enum import Enum
import struct

from captured_code import CapturedCode, CodeGuard, Rewrite
from temporal_layout import TemporalLayout
from x64_table import rel32

HISTORY_WRITE = CodeGuard(0x11669E, 223, '032c2431301523f5fd10fbc70b79fb354ad4c4c5c44c27599e390cc62b34e641')
HISTORY_COUNTER_WRITE = CodeGuard(0x11677D, 52, 'd7e3f3d72a9ec831445120ff4120fd8ae34b5c21684c21a76151b56c9434d28b')
LEGACY_HISTORY_BYTES = 20 * 0x684


class HistoryFormat(Enum):
    # These are internal context values, not assigned on-disk format identifiers.
    Legacy64 = 64
    Expanded300 = 300
    Expanded500 = 500


@dataclass(frozen=True)
class ImportedHistory:
    data: bytes
    consumed: int


def import_history(source: bytes, layout: TemporalLayout, format_value: HistoryFormat) -> ImportedHistory:
    """Return complete bytes before publication. The root loader must supply its admitted format."""
    if not isinstance(format_value, HistoryFormat):
        raise ValueError('The temporal history format is unknown.')
    legacy = format_value is HistoryFormat.Legacy64
    if not legacy and format_value.value != layout.shape.actors:
        raise ValueError('The temporal history shape differs from its admitted format.')
    consumed = LEGACY_HISTORY_BYTES if legacy else layout.history_bytes
    if len(source) < consumed:
        raise ValueError('The temporal history input is incomplete.')
    if not legacy:
        return ImportedHistory(bytes(source[:consumed]), consumed)
    expanded = bytearray(layout.history_bytes)
    members = ((0, 0, 0x300), (0x300, layout.vector_bytes, 0x300),
               (0x600, layout.history_state_offset, 64), (0x640, layout.history_valid_offset, 64),
               (0x680, layout.history_time_offset, 4))
    for row in range(20):
        for old, new, size in members:
            old_start, new_start = row * 0x684 + old, row * layout.history_row_bytes + new
            expanded[new_start:new_start + size] = source[old_start:old_start + size]
    return ImportedHistory(bytes(expanded), consumed)


def prepare_history_write(code: CapturedCode, layout: TemporalLayout, history_address: int) -> Rewrite:
    """Use the existing stream writer without changing its outer frame or the following corpse section."""
    end = history_address + layout.history_bytes
    if (history_address < 0x10000 or history_address % 16 or end > 2**64
            or not (end <= code.base or history_address >= code.base + code.meta['imageSize'])):
        raise ValueError('The complete temporal save storage must be aligned and outside the native image.')
    code.guarded(HISTORY_WRITE)
    code.guarded(HISTORY_COUNTER_WRITE)
    # The following stock corpse section reuses RBX as its 128-byte copy-group count.
    body = bytearray(b'\xBB' + struct.pack('<I', 0x104))
    body += b'\x49\x8B\xCD\xBA' + struct.pack('<I', layout.history_bytes)
    body += b'\x49\xB8' + struct.pack('<Q', history_address)
    # Preserve the original call's language-state location and owning Windows frame.
    body += b'\x90' * (0x1166C3 - HISTORY_WRITE.rva - len(body))
    body += b'\xE8' + rel32(code.base + HISTORY_WRITE.rva + len(body) + 5, code.base + 0x2277B80)
    body += b'\xE9' + rel32(code.base + HISTORY_WRITE.rva + len(body) + 5,
                           code.base + HISTORY_COUNTER_WRITE.rva)
    replacement = bytes(body) + b'\x90' * (HISTORY_WRITE.size - len(body))
    return Rewrite('temporal_history_save_write', HISTORY_WRITE, replacement)
