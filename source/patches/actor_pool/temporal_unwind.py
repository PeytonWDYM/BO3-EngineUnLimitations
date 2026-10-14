"""Prepare all guarded temporal runtime fragments. Live registration and handlers need separate admission."""
from dataclasses import dataclass, replace
import struct

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from captured_code import CapturedCode, CodeGuard, Rewrite
from native_unwind import read_frame
from temporal_layout import TemporalLayout
from temporal_producer import PRODUCER_FUNCTION, producer_frame
from temporal_rewind import REWIND_FUNCTION, rewind_frame
from unwind import native_frames

FRAGMENTS = (
    (0x1BFDE70,0x1BFDF11,0x3165F4C,28,'d757574ec97dc638b4aeadeb03bcf899f91d97972fdb9b222bf5b4ae91ce78f7'),
    (0x1BFDF11,0x1BFE0D3,0x3165F68,24,'b9d486e1c306e111bd6746efff27fe9c2a6ba1897e5344a618f6cbbade8731b0'),
    (0x1BFE0D3,0x1BFE298,0x3165F80,16,'75a3f665a68b9804c16534e282e19662e17912224f7c9ebd9eaf40fcde66c8ba'),
    (0x1BF9940,0x1BF9A00,0x3165D2C,20,'a73e3e4179f78ea5377aad338b4541eaa94952ea5e808f630e8a16b707954575'),
    (0x1BF9A00,0x1BF9BAF,0x3165D40,40,'9c65ca72c66c010e275fdef20b5f8e2b101fda55a2001524441fc609eb3ae664'),
    (0x1BF9BAF,0x1BF9BC9,0x3165D68,16,'3e066d18effcf31cf23762c6b18077b23ffdf7660e244a441a09142e6b11e6e3'),
)


@dataclass(frozen=True)
class TemporalFrame:
    source_runtime: tuple[int,int,int]
    runtime: tuple[int,int,int]
    source_prolog: int
    metadata: bytes
    parent_runtime: tuple[int,int,int] | None


def prepare_temporal_unwind(code: CapturedCode, layout: TemporalLayout, edit: Rewrite,
                            *, expanded: bool = True) -> tuple[TemporalFrame,...]:
    if edit.name == 'temporal_producer':
        guard, first, allocation, original_allocation, original_cookie = PRODUCER_FUNCTION, 0, producer_frame(layout).allocation, 0x108, 0xE0
    elif edit.name == 'temporal_rewind':
        guard, first, allocation, original_allocation, original_cookie = REWIND_FUNCTION, 3, rewind_frame(layout).allocation, 0x6B8, 0x680
    else:
        raise ValueError('Only guarded complete temporal relocations have this frame contract.')
    original = code.guarded(guard)
    for handler in (CodeGuard(0x2BC3A04,29,'53989c4a3df823fa742c0bebda04d4729c810916a7f81899cc2b885ae9c8997c'),
                    CodeGuard(0x2BC3A24,99,'b17460e875c3ee6c6e0ea3ad52fa5c3b2d83c39f2a7a3547dcb87eb185dd1b0d')):
        code.guarded(handler)
    selected = FRAGMENTS[first:first+3]
    expected = tuple(item[:3] for item in selected)
    observed = tuple(runtime for runtime in native_frames(code) if guard.rva <= runtime[0] < guard.rva + guard.size)
    if observed != expected:
        raise ValueError('The complete temporal runtime-fragment inventory differs.')
    if expanded:
        if edit.stub_address is None or not edit.instruction_map:
            raise ValueError('The temporal relocation has no complete instruction-boundary map.')
        mapping = dict(edit.instruction_map)
    else:
        decoder = Cs(CS_ARCH_X86,CS_MODE_64)
        mapping = {instruction.address:instruction.address for instruction in decoder.disasm(original,code.base+guard.rva)}
        mapping[code.base+guard.rva+guard.size] = code.base+guard.rva+guard.size
        allocation = original_allocation
    growth = allocation-original_allocation

    def mapped(rva: int) -> int:
        try:
            return mapping[code.base+rva]
        except KeyError as error:
            raise ValueError('A native unwind boundary is missing from the complete relocation map.') from error

    result = []
    for begin,end,rva,size,digest in selected:
        raw = code.guarded(CodeGuard(rva,size,digest))
        frame = read_frame(code,(begin,end,rva))
        prolog = mapped(begin+frame.prolog)-mapped(begin)
        operations = []
        for operation in frame.operations:
            offset = mapped(begin+operation.offset)-mapped(begin)
            changed = replace(operation,offset=offset)
            if operation.opcode == 1:
                if operation.info or operation.allocation != original_allocation:
                    raise ValueError('The temporal root has an unknown allocation encoding.')
                changed = replace(changed,value=allocation//8)
            elif operation.opcode == 4:
                changed = replace(changed,value=operation.value+growth//8)
            elif operation.opcode != 0:
                raise ValueError('The temporal frame has an unclassified native operation.')
            operations.append(changed)
        codes = b''.join(bytes((operation.offset,operation.opcode | operation.info << 4))+operation.payload for operation in operations)
        if prolog > 255 or len(codes)//2 > 255 or mapped(begin) >= mapped(end):
            raise ValueError('The relocated frame exceeds its native metadata encoding.')
        metadata = bytes((raw[0],prolog,len(codes)//2,0))+codes
        metadata += b'\0' * (-len(metadata)%4)
        parent_runtime = None
        if frame.flags == 4:
            parent = frame.parent
            if parent is None or parent.runtime != expected[0]:
                raise ValueError('The temporal fragment has an unknown chained parent.')
            parent_runtime = (mapped(parent.runtime[0]),mapped(parent.runtime[1]),parent.runtime[2])
            metadata += raw[-12:]
        elif frame.flags == 3:
            handler,cookie = struct.unpack('<II',raw[-8:])
            if handler != 0x2BC3A04 or cookie != original_cookie:
                raise ValueError('The temporal root has an unknown native cookie-handler contract.')
            metadata += struct.pack('<II',handler,cookie+growth)
        else:
            raise ValueError('The temporal frame has an unknown handler flag contract.')
        result.append(TemporalFrame((begin,end,rva),(mapped(begin),mapped(end),rva),frame.prolog,metadata,parent_runtime))
    return tuple(result)
