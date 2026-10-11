"""Relocate a guarded owned function with explicit instruction-span replacements."""
from dataclasses import dataclass
import struct

from capstone import Cs, CsInsn, CS_ARCH_X86, CS_MODE_64, CS_GRP_BRANCH_RELATIVE
from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
from x64_table import rel32


@dataclass(frozen=True)
class RelocatedFunction:
    code: bytes
    addresses: dict[int, int]


def replace_displacement(instruction: CsInsn, value: int) -> bytes:
    """Preserve a memory encoding, widening ModRM disp8 to disp32 when required."""
    raw = bytes(instruction.bytes)
    offset, size = instruction.disp_offset, instruction.disp_size
    if size == 4:
        return raw[:offset] + struct.pack('<i', value) + raw[offset + 4:]
    if size != 1 or raw[instruction.modrm_offset] & 0xC0 != 0x40:
        raise ValueError('A native memory operand has an unsupported displacement encoding.')
    if -128 <= value <= 127:
        return raw[:offset] + struct.pack('<b', value) + raw[offset + 1:]
    changed = bytearray(raw[:offset])
    changed[instruction.modrm_offset] = changed[instruction.modrm_offset] & 0x3F | 0x80
    return bytes(changed) + struct.pack('<i', value) + raw[offset + 1:]


def relocate_function(raw: bytes, source: int, destination: int,
                      replacements: dict[int, tuple[int, bytes]]) -> RelocatedFunction:
    """Widen local branches and rebase native calls and RIP operands; never write game memory."""
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    instructions = list(decoder.disasm(raw, source))
    if not instructions or sum(i.size for i in instructions) != len(raw):
        raise ValueError('The native function contains an incomplete instruction.')
    end = source + len(raw)
    boundaries = {i.address for i in instructions} | {end}
    intervals = []
    for start, (size, value) in sorted(replacements.items()):
        if start not in boundaries or start + size not in boundaries or size <= 0 or not source <= start < start + size <= end:
            raise ValueError('A replacement does not cover complete native instructions.')
        if intervals and start < intervals[-1][1]:
            raise ValueError('The replacement instruction spans overlap.')
        authored = list(decoder.disasm(value, 0))
        if not value or sum(i.size for i in authored) != len(value):
            raise ValueError('A replacement contains an incomplete instruction.')
        if any(i.group(CS_GRP_BRANCH_RELATIVE) or any(o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP
                                                    for o in i.operands) for i in authored):
            raise ValueError('Authored replacements must not contain relative operands.')
        intervals.append((start, start + size))
    fragments = []
    skip_until = source
    for instruction in instructions:
        if instruction.address < skip_until:
            continue
        if instruction.address in replacements:
            size, value = replacements[instruction.address]
            skip_until = instruction.address + size
            fragments.append((instruction, value, None))
            continue
        value = bytes(instruction.bytes)
        target = None
        if instruction.group(CS_GRP_BRANCH_RELATIVE):
            if len(instruction.operands) != 1 or instruction.operands[0].type != X86_OP_IMM:
                raise ValueError('A relative branch has an unsupported operand.')
            target = instruction.operands[0].imm
            if value[0] in (0xE8, 0xE9) and len(value) == 5:
                value = value[:1] + bytes(4)
            elif value[0] == 0xEB and len(value) == 2:
                value = b'\xe9' + bytes(4)
            elif 0x70 <= value[0] <= 0x7F and len(value) == 2:
                value = bytes([0x0F, value[0] + 0x10]) + bytes(4)
            elif value[:1] == b'\x0f' and len(value) == 6 and 0x80 <= value[1] <= 0x8F:
                value = value[:2] + bytes(4)
            else:
                raise ValueError('The function uses an unsupported relative control encoding.')
        fragments.append((instruction, value, target))
    addresses = {}
    position = destination
    for instruction, value, target in fragments:
        addresses[instruction.address] = position
        position += len(value)
    result = bytearray()
    for instruction, raw_value, target in fragments:
        value = bytearray(raw_value)
        new_address = addresses[instruction.address]
        if target is not None:
            if source <= target <= end:
                if target not in addresses:
                    raise ValueError('An internal branch targets a replaced or incomplete instruction.')
                target = addresses[target]
            value[-4:] = rel32(new_address + len(value), target)
        elif instruction.address not in replacements:
            for operand in instruction.operands:
                if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
                    target = instruction.address + instruction.size + operand.mem.disp
                    if source <= target < end or instruction.disp_size != 4:
                        raise ValueError('A RIP operand has an unclassified internal target or displacement.')
                    value[instruction.disp_offset:instruction.disp_offset + 4] = rel32(new_address + len(value), target)
        result.extend(value)
    return RelocatedFunction(bytes(result), addresses)
