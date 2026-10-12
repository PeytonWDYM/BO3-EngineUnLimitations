"""Prepare native twenty-row actor history in owned storage. No game allocation or save format is admitted."""
import struct

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import X86_OP_MEM, X86_REG_RDX, X86_REG_R9, X86_REG_R10
from captured_code import CapturedCode, CodeGuard, Rewrite
from relocate_function import relocate_function, replace_displacement
from temporal_layout import TemporalLayout
from x64_table import rel32

RECORDER_FUNCTION = CodeGuard(0x1BFBAB0, 1015, '37a556caefae375c6d4f96bd170e9dfc04bd9bb10eba40aeff641e822a482a0d')
SELECTOR_FUNCTION = CodeGuard(0x1BFDDB0, 188, '58c7d662e56fa7783bb983176c7396a8c906f570afec84ef99bda02167dd1065')


def prepare_history(code: CapturedCode, layout: TemporalLayout, history_address: int,
                    recorder_address: int, selector_address: int) -> tuple[Rewrite, Rewrite]:
    """Keep eight-lane recording with a four-lane tail, and preserve the native selector's time rules."""
    if history_address <= 0 or history_address % 16 or history_address + layout.history_bytes > 1 << 64:
        raise ValueError('The expanded history needs an aligned complete storage interval.')
    recorder = code.guarded(RECORDER_FUNCTION)
    selector = code.guarded(SELECTOR_FUNCTION)
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    replacements = {
        code.base + 0x1BFBAE1: (7, b'\x48\xb8' + struct.pack('<Q', history_address)),
        code.base + 0x1BFBAE8: (7, b'\x4d\x69\xd2' + struct.pack('<I', layout.history_row_bytes)),
        code.base + 0x1BFBE9B: (4, b'\x49\x81\xf9' + struct.pack('<I', layout.shape.actors)),
    }
    changed = 0
    for instruction in decoder.disasm(recorder, code.base + RECORDER_FUNCTION.rva):
        for operand in instruction.operands:
            if operand.type != X86_OP_MEM:
                continue
            member = operand.mem
            value = None
            if member.base == X86_REG_R10 and member.index == 0 and member.disp == 0x680:
                value = layout.history_time_offset
            elif member.base == X86_REG_R10 and member.index == 0 and member.disp == 0x308:
                value = layout.vector_bytes + 8
            elif member.base == X86_REG_RDX and -0x308 <= member.disp <= -0x2AC:
                value = member.disp - (layout.vector_bytes - 0x300)
            elif {member.base, member.index} == {X86_REG_R9, X86_REG_R10}:
                if 0x600 <= member.disp <= 0x607:
                    value = layout.history_state_offset + member.disp - 0x600
                elif 0x640 <= member.disp <= 0x647:
                    value = layout.history_valid_offset + member.disp - 0x640
            if value is not None:
                replacements[instruction.address] = (instruction.size, replace_displacement(instruction, value))
                changed += 1
    if changed != 42 or layout.shape.actors % 8 != 4:
        raise ValueError('The native history member or four-lane tail contract differs.')
    tail = code.base + 0x1BFBCC8
    # Reserve the local exit branch before relocation so every native branch gets its final address.
    replacements[tail] = (8, b'\x49\x81\xf9' + struct.pack('<I', layout.shape.actors - 4) + b'\x90' * 6 + code.read(0x1BFBCC8, 8))
    moved = relocate_function(recorder, code.base + RECORDER_FUNCTION.rva, recorder_address, replacements)
    body = bytearray(moved.code)
    branch_address = moved.addresses[tail] + 7
    offset = branch_address - recorder_address
    body[offset:offset + 6] = b'\x0f\x8d' + rel32(branch_address + 6, moved.addresses[code.base + 0x1BFBEA5])
    recorder_hook = b'\xe9' + rel32(code.base + RECORDER_FUNCTION.rva + 5, recorder_address) + b'\x90' * 2
    recorder_edit = Rewrite('temporal_history_recorder', code.guard(RECORDER_FUNCTION.rva, 7), recorder_hook, recorder_address, bytes(body),
                            instruction_map=tuple(moved.addresses.items()))
    selector_changes = {
        code.base + 0x1BFDE10: (7, b'\x49\xba' + struct.pack('<Q', history_address)),
        code.base + 0x1BFDE3D: (7, b'\x48\x69\xc0' + struct.pack('<I', layout.history_row_bytes)),
    }
    selected = relocate_function(selector, code.base + SELECTOR_FUNCTION.rva, selector_address, selector_changes)
    selector_hook = b'\xe9' + rel32(code.base + SELECTOR_FUNCTION.rva + 5, selector_address)
    return recorder_edit, Rewrite('temporal_history_selector', code.guard(SELECTOR_FUNCTION.rva, 5), selector_hook, selector_address, selected.code,
                                 instruction_map=tuple(selected.addresses.items()))
