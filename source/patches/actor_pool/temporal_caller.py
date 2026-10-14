"""Prepare the caller's actor/corpse buffer separation. Native frame metadata and cleanup remain gated."""
from dataclasses import dataclass
import struct

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import X86_OP_MEM, X86_REG_RBP, X86_REG_RSP
from captured_code import CapturedCode, CodeGuard, Rewrite
from relocate_function import replace_displacement
from temporal_layout import TemporalLayout

CALLER_FUNCTION = CodeGuard(0x1580000, 1599, '61c8fd6755aea6255e4c9a4c2107b9b0138d75c81feba84adf0bc6ca03ee180b')


@dataclass(frozen=True)
class CallerFrame:
    allocation: int
    growth: int
    corpse: int
    cookie: int


def caller_frame(layout: TemporalLayout) -> CallerFrame:
    # Keep the 16-byte-aligned actor start at RBP+0x2F90 and the unchanged 1,600-byte corpse buffer after it.
    aligned_output = (layout.output_bytes + 15) & ~15
    growth = aligned_output - 0x640
    return CallerFrame(0x3DD0 + growth, growth, 0x35D0 + growth, 0x3C20 + growth)


def prepare_caller(code: CapturedCode, layout: TemporalLayout) -> tuple[Rewrite, ...]:
    original = code.guarded(CALLER_FUNCTION)
    frame = caller_frame(layout)
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    edits = []
    for instruction in decoder.disasm(original, code.base + CALLER_FUNCTION.rva):
        rva = instruction.address - code.base
        replacement = None
        if rva == 0x1580014:
            replacement = b'\xb8' + struct.pack('<I', frame.allocation)
        else:
            for operand in instruction.operands:
                if operand.type != X86_OP_MEM:
                    continue
                member = operand.mem
                value = None
                if member.base == X86_REG_RSP and member.disp == -0x3CD0:
                    value = member.disp - frame.growth
                elif member.base == X86_REG_RSP and member.disp >= 0x3D30:
                    value = member.disp + frame.growth
                elif member.base == X86_REG_RBP and member.disp >= 0x35D0:
                    value = member.disp + frame.growth
                if value is not None:
                    replacement = replace_displacement(instruction, value)
        if replacement is not None:
            if len(replacement) != instruction.size:
                raise ValueError('The caller expansion needs a different instruction-relocation contract.')
            edits.append(Rewrite('temporal_caller_frame', code.guard(rva, instruction.size), replacement))
    if len(edits) != 22:
        raise ValueError('The caller frame member inventory differs from the researched body.')
    return tuple(edits)
