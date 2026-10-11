"""Read exact native unwind frames and build owned comparison inputs. No game registration."""
from dataclasses import dataclass
import struct

from captured_code import CapturedCode

NONVOLATILE_GPRS = frozenset((3, 5, 6, 7, 12, 13, 14, 15))


@dataclass(frozen=True)
class Operation:
    offset: int
    opcode: int
    info: int
    value: int = 0

    @property
    def payload(self) -> bytes:
        if self.opcode in (4, 8) or self.opcode == 1 and self.info == 0:
            return struct.pack('<H', self.value)
        if self.opcode in (5, 9) or self.opcode == 1 and self.info == 1:
            return struct.pack('<I', self.value)
        return b''

    @property
    def allocation(self) -> int:
        if self.opcode == 2:
            return self.info * 8 + 8
        if self.opcode == 1:
            return self.value * 8 if self.info == 0 else self.value
        return 0


@dataclass(frozen=True)
class NativeFrame:
    runtime: tuple[int, int, int]
    prolog: int
    flags: int
    operations: tuple[Operation, ...]
    parent: 'NativeFrame | None'

    @property
    def has_handler(self) -> bool:
        return bool(self.flags & 3) or self.parent is not None and self.parent.has_handler


def read_frame(code: CapturedCode, runtime: tuple[int, int, int], seen: tuple[int, ...] = ()) -> NativeFrame:
    begin, end, rva = runtime
    if not (0 <= begin < end <= code.meta['imageSize']) or rva in seen or len(seen) >= 64:
        raise ValueError('The native runtime frame interval or chain is invalid.')
    header = code.read(rva, 4)
    version, flags, prolog, count, frame_register = header[0] & 7, header[0] >> 3, header[1], header[2], header[3]
    if version != 1 or flags not in (0, 1, 2, 3, 4) or frame_register:
        raise ValueError('The owned continuation requires version-one frames without a frame pointer.')
    raw = code.read(rva + 4, ((count + 1) & ~1) * 2) if count else b''
    operations = []
    slot = 0
    previous_offset = 255
    while slot < count:
        offset, tag = raw[slot * 2:slot * 2 + 2]
        opcode, info = tag & 15, tag >> 4
        if opcode not in (0, 1, 2, 4, 5, 8, 9) or offset > previous_offset or offset > prolog:
            raise ValueError('The native unwind operation or prolog ordering is unsupported.')
        if (opcode in (0, 4, 5) and info not in NONVOLATILE_GPRS
                or opcode in (8, 9) and not 6 <= info <= 15 or opcode == 1 and info not in (0, 1)):
            raise ValueError('The native unwind operation has an unsupported register or allocation.')
        extra = 1 if opcode in (4, 8) or opcode == 1 and info == 0 else 2 if opcode in (5, 9) or opcode == 1 and info == 1 else 0
        if slot + extra >= count:
            raise ValueError('The native unwind operation has incomplete operand slots.')
        value = int.from_bytes(raw[(slot + 1) * 2:(slot + extra + 1) * 2], 'little')
        operation = Operation(offset, opcode, info, value)
        if opcode == 1 and (operation.allocation == 0 or operation.allocation % 8):
            raise ValueError('The native large allocation is invalid.')
        operations.append(operation)
        previous_offset = offset
        slot += extra + 1
    tail = rva + 4 + ((count + 1) & ~1) * 2
    parent = read_frame(code, struct.unpack('<III', code.read(tail, 12)), (*seen, rva)) if flags & 4 else None
    return NativeFrame(runtime, prolog, flags, tuple(operations), parent)


def active_operations(frame: NativeFrame, control_rva: int) -> tuple[Operation, ...]:
    if not frame.runtime[0] <= control_rva < frame.runtime[1]:
        raise ValueError('The hook is outside its native runtime frame.')
    result = tuple(operation for operation in frame.operations if operation.offset <= control_rva - frame.runtime[0])
    parent = frame.parent
    while parent is not None:
        # Windows applies all chained parent codes after the active fragment codes.
        result += parent.operations
        parent = parent.parent
    return result


def encode(operations: tuple[Operation, ...]) -> bytes:
    codes = b''.join(bytes((0, operation.opcode | operation.info << 4)) + operation.payload for operation in operations)
    if len(codes) // 2 > 255:
        raise ValueError('The flattened unwind codes exceed the native slot count.')
    metadata = bytes((1, 0, len(codes) // 2, 0)) + codes
    return metadata + b'\0' * (-len(metadata) % 4)


def stack_contract(operations: tuple[Operation, ...]) -> tuple[tuple[tuple[int, int, int], ...], int]:
    cursor = 0
    saves = []
    for operation in operations:
        if operation.opcode == 0:
            saves.append((cursor, 8, operation.info))
            cursor += 8
        elif operation.opcode in (1, 2):
            cursor += operation.allocation
        elif operation.opcode in (4, 5, 8, 9):
            width = 16 if operation.opcode in (8, 9) else 8
            offset = operation.value * width if operation.opcode in (4, 8) else operation.value
            saves.append((offset, width, operation.info))
    if cursor >= 32768 or any(offset + width >= 40000 for offset, width, _ in saves):
        raise ValueError('The native stack exceeds the owned comparison contract.')
    return tuple(saves), cursor


def reference_image(code: CapturedCode, frame: NativeFrame, control_rva: int) -> tuple[bytes, tuple[int, int, int], int]:
    frames = []
    current = frame
    while current is not None:
        frames.append(current)
        current = current.parent
    origin = min(item.runtime[0] for item in frames)
    extent = max(item.runtime[1] for item in frames) - origin
    image = bytearray(extent + (-extent % 4))
    for item in frames:
        begin, end, _ = item.runtime
        image[begin - origin:end - origin] = code.read(begin, end - begin)
    unwind_offsets = {}
    for item in reversed(frames):
        unwind_offsets[item.runtime[2]] = len(image)
        # Handlers are deliberately omitted only in this owned oracle. Game admission remains blocked.
        flags = item.flags & 4
        header = code.read(item.runtime[2], 4)
        metadata = bytearray(code.read(item.runtime[2], 4 + ((header[2] + 1) & ~1) * 2))
        metadata[0] = 1 | flags << 3
        if item.parent:
            begin, end, unwind = item.parent.runtime
            metadata += struct.pack('<III', begin - origin, end - origin, unwind_offsets[unwind])
        image += metadata
    if len(image) >= 65536:
        raise ValueError('The original native oracle exceeds its owned allocation.')
    begin, end, unwind = frame.runtime
    return bytes(image), (begin - origin, end - origin, unwind_offsets[unwind]), control_rva - origin
