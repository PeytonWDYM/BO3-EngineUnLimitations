"""Prepare the complete pose producer in owned storage. Native history and runtime admission stay gated."""
from dataclasses import dataclass
import struct

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import X86_OP_MEM, X86_REG_RBP, X86_REG_RSP, X86_REG_R12, X86_REG_R13
from captured_code import CapturedCode, CodeGuard, Rewrite
from relocate_function import relocate_function, replace_displacement
from temporal_layout import TemporalLayout
from x64_table import rel32

PRODUCER_FUNCTION = CodeGuard(0x1BFDE70, 1064, 'e728ba4c1ec83b8b5956e94f23f3229fa038a7e99ec4f710a60e62fa5110a5f6')
CLEAR_START, CLEAR_END = 0x1BFDF30, 0x1BFDF74


@dataclass(frozen=True)
class ProducerFrame:
    allocation: int
    flags_b_rbp: int
    clear_bytes: int
    saved_rsi: int
    saved_rbx: int


def producer_frame(layout: TemporalLayout) -> ProducerFrame:
    flags_a = 0x60
    flags_b = (flags_a + layout.shape.actors + 15) & ~15
    cookie = (flags_b + layout.shape.actors + 15) & ~15
    growth = cookie - 0xE0
    allocation = 0x108 + growth
    if allocation >= 4096 or growth % 16:
        raise ValueError('The producer frame requires a different stack-probing or alignment contract.')
    # RBP is established before SUB RSP and therefore still addresses the native cookie.
    return ProducerFrame(allocation, flags_b - (allocation - 8), cookie - flags_a, 0xF8 + growth, 0x100 + growth)


def prepare_producer(code: CapturedCode, layout: TemporalLayout, stub_address: int) -> Rewrite:
    original = code.guarded(PRODUCER_FUNCTION)
    frame = producer_frame(layout)
    replacements = {
        code.base + 0x1BFDE80: (7, b'\x48\x81\xec' + struct.pack('<I', frame.allocation)),
        code.base + 0x1BFE286: (7, b'\x48\x81\xc4' + struct.pack('<I', frame.allocation)),
        code.base + 0x1BFE009: (7, b'\x48\x81\xfe' + struct.pack('<I', layout.shape.actor_bytes)),
        code.base + 0x1BFE0A9: (7, b'\x48\x81\xfe' + struct.pack('<I', layout.shape.actor_bytes)),
        code.base + 0x1BFE26E: (4, b'\x48\x81\xff' + struct.pack('<I', layout.shape.actors)),
    }
    # Keep AL/CL (row availability) while clearing both flags and their alignment padding.
    clear = b'\x50\x51\x48\x8d\x7c\x24\x70\x31\xc0\xb9' + struct.pack('<I', frame.clear_bytes // 8)
    clear += b'\xfc\xf3\x48\xab\x59\x58\x33\xff'
    replacements[code.base + CLEAR_START] = (CLEAR_END - CLEAR_START, clear)
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    changed_members = set()
    for instruction in decoder.disasm(original, code.base + PRODUCER_FUNCTION.rva):
        rva = instruction.address - code.base
        if CLEAR_START <= rva < CLEAR_END:
            continue
        for operand in instruction.operands:
            if operand.type != X86_OP_MEM:
                continue
            member = operand.mem
            replacement = None
            if member.base == X86_REG_RBP and member.disp == -0x60:
                replacement = frame.flags_b_rbp
            elif member.base == X86_REG_RSP and member.disp in (0xF8, 0x100):
                replacement = frame.saved_rsi if member.disp == 0xF8 else frame.saved_rbx
            elif (member.base in (X86_REG_R12, X86_REG_R13) or member.index in (X86_REG_R12, X86_REG_R13)):
                replacement = {0x300: layout.vector_bytes, 0x600: layout.history_state_offset,
                               0x640: layout.history_valid_offset}.get(member.disp)
            if replacement is not None:
                replacements[instruction.address] = (instruction.size, replace_displacement(instruction, replacement))
                changed_members.add(rva)
    expected_members = {0x1BFDF11, 0x1BFDF19, 0x1BFDF80, 0x1BFDFAD, 0x1BFDFB4, 0x1BFDFBE,
                        0x1BFDFCA, 0x1BFDFDC, 0x1BFDFFB, 0x1BFE01F, 0x1BFE054, 0x1BFE06A,
                        0x1BFE0BC, 0x1BFE0C4, 0x1BFE123}
    if changed_members != expected_members:
        raise ValueError('The producer member inventory differs from the researched native body.')
    relocated = relocate_function(original, code.base + PRODUCER_FUNCTION.rva, stub_address, replacements)
    hook = b'\xe9' + rel32(code.base + PRODUCER_FUNCTION.rva + 5, stub_address)
    return Rewrite('temporal_producer', code.guard(PRODUCER_FUNCTION.rva, 5), hook, stub_address, relocated.code,
                   instruction_map=tuple(relocated.addresses.items()))
