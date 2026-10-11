"""Prepare native actor rewind with complete temporary buffers and a guarded stack probe. Activation stays disabled."""
from dataclasses import dataclass
import struct

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import X86_OP_MEM, X86_REG_RSP, X86_REG_RBP
from captured_code import CapturedCode, CodeGuard, Rewrite
from relocate_function import relocate_function, replace_displacement
from temporal_layout import TemporalLayout
from x64_table import rel32

REWIND_FUNCTION = CodeGuard(0x1BF9940, 649, '6df07e1e1619760337da74438dce62e3e4b34c25604e4546a09bb57cbc3e0961')
PROBE_FUNCTION = CodeGuard(0x2BC57A0, 78, '24ba2f8e6f97e3f8dec9771f775f11294b7da43ba09efabbb1bd3c079ac25b6e')
CLEAR_START, CLEAR_END = 0x1BF99AC, 0x1BF99EC


@dataclass(frozen=True)
class RewindFrame:
    allocation: int
    positions: int
    valid: int
    cookie: int
    save_growth: int


def rewind_frame(layout: TemporalLayout) -> RewindFrame:
    positions = 0x40 + layout.vector_bytes
    valid = 0x40 + layout.output_valid_offset
    cookie = (valid + layout.shape.actors + 15) & ~15
    growth = cookie - 0x680
    return RewindFrame(0x6B8 + growth, positions, valid, cookie, growth)


def prepare_rewind(code: CapturedCode, layout: TemporalLayout, address: int) -> Rewrite:
    original = code.guarded(REWIND_FUNCTION)
    code.guarded(PROBE_FUNCTION)
    frame = rewind_frame(layout)
    # The guarded CRT probe preserves arguments and RAX, uses no caller shadow space, and returns before SUB RSP.
    allocation = b'\xb8' + struct.pack('<I', frame.allocation) + b'\x90' * 5 + b'\x48\x2b\xe0'
    clear = b'\x50\x51\x57\x48\x8d\xbc\x24' + struct.pack('<I', frame.valid + 24)
    clear += b'\x33\xc0\xb9' + struct.pack('<I', (frame.cookie - frame.valid) // 8)
    clear += b'\xfc\xf3\x48\xab\x5f\x59\x58'
    replacements = {
        code.base + 0x1BF9943: (7, allocation),
        code.base + 0x1BF9BBF: (7, b'\x48\x81\xc4' + struct.pack('<I', frame.allocation)),
        code.base + 0x1BF9961: (6, b'\x41\xb8' + struct.pack('<I', layout.output_bytes)),
        code.base + 0x1BF9A98: (3, b'\x8d\xae' + struct.pack('<I', layout.shape.actors)),
        code.base + CLEAR_START: (CLEAR_END - CLEAR_START, clear),
    }
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    changed = 0
    for instruction in decoder.disasm(original, code.base + REWIND_FUNCTION.rva):
        rva = instruction.address - code.base
        if CLEAR_START <= rva < CLEAR_END:
            continue
        for operand in instruction.operands:
            if operand.type != X86_OP_MEM:
                continue
            member = operand.mem
            value = None
            if member.base == X86_REG_RSP:
                if member.disp >= 0x680:
                    value = member.disp + frame.save_growth
                elif 0x340 <= member.disp <= 0x348:
                    value = frame.positions + member.disp - 0x340
                elif member.disp == 0x640:
                    value = frame.valid
            elif member.base == X86_REG_RBP and rva in (0x1BF9A78, 0x1BF9A7F):
                value = layout.output_valid_offset if rva == 0x1BF9A78 else layout.vector_bytes + 8
            elif member.disp in (-0x600, -0x308, -0x304, -0x300):
                value = {-0x600: -layout.output_valid_offset, -0x308: -layout.vector_bytes - 8,
                         -0x304: -layout.vector_bytes - 4, -0x300: -layout.vector_bytes}[member.disp]
            if value is not None:
                replacements[instruction.address] = (instruction.size, replace_displacement(instruction, value))
                changed += 1
    if changed != 32:
        raise ValueError('The native rewind member inventory differs from the researched body.')
    moved = relocate_function(original, code.base + REWIND_FUNCTION.rva, address, replacements)
    body = bytearray(moved.code)
    call_address = moved.addresses[code.base + 0x1BF9943] + 5
    offset = call_address - address
    body[offset:offset + 5] = b'\xe8' + rel32(call_address + 5, code.base + PROBE_FUNCTION.rva)
    # Both pushes and the complete native SUB instruction occupy the ten-byte entry span.
    hook = b'\xe9' + rel32(code.base + REWIND_FUNCTION.rva + 5, address) + b'\x90' * 5
    return Rewrite('temporal_rewind', code.guard(REWIND_FUNCTION.rva, 10), hook, address, bytes(body))
