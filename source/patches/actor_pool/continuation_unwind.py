"""Prepare owned stack phases over complete active native frames. Handler dispatch stays gated."""
from dataclasses import dataclass, replace

from captured_code import Rewrite
from leaf_frames import NONVOLATILE
from native_unwind import Operation, NONVOLATILE_GPRS, encode
from table_plan import normalize_register
from x64_table import REGISTERS


@dataclass(frozen=True)
class ContinuationPhase:
    begin: int
    end: int
    stack_bytes: int
    saved_registers: tuple[tuple[int, int], ...]
    unwind_info: bytes
    native_unwind_info: bytes
    unscaled_xmm_phase: bool


def prepare_continuation_phases(edit: Rewrite, native: tuple[Operation, ...]) -> tuple[ContinuationPhase, ...]:
    import capstone
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    instructions = list(decoder.disasm(edit.stub, edit.stub_address))
    if not instructions or sum(item.size for item in instructions) != len(edit.stub):
        raise ValueError('The continuation stub does not decode completely.')
    native_gprs = {operation.info for operation in native if operation.opcode in (0, 4, 5)}
    native_vectors = {operation.info for operation in native if operation.opcode in (8, 9)}
    slots: list[int | None] = []
    phases = []
    native_metadata = encode(native)
    for instruction in instructions:
        depth = len(slots) * 8
        if depth > 128:
            raise ValueError('The continuation temporary stack exceeds its admitted extent.')
        saved = tuple((register, index * 8) for index, register in enumerate(reversed(slots)) if register in NONVOLATILE_GPRS)
        if len({register for register, _ in saved}) != len(saved):
            raise ValueError('Repeated temporary nonvolatile saves need a separate contract.')
        # SAVE_NONVOL restores the temporary values before ALLOC_SMALL removes their complete allocation.
        temporary = tuple(Operation(0, 4, register, offset // 8) for register, offset in saved)
        if depth:
            temporary += (Operation(0, 2, depth // 8 - 1),)
        adjusted = []
        unscaled_xmm = False
        for operation in native:
            if operation.opcode in (4, 5, 8, 9):
                scale = 16 if operation.opcode in (8, 9) else 8
                offset = operation.value * scale if operation.opcode in (4, 8) else operation.value
                offset += depth
                # RtlVirtualUnwind uses its initial fixed frame base for SAVE operations.
                # Unscaled XMM offsets at odd eight-byte phases need separate runtime ABI admission.
                short = offset % scale == 0 and offset // scale <= 65535
                unscaled_xmm |= scale == 16 and offset % 16 != 0
                operation = replace(operation, opcode=(8 if scale == 16 else 4) + (not short),
                                    value=offset // scale if short else offset)
            adjusted.append(operation)
        begin = instruction.address - edit.stub_address
        metadata = encode(temporary + tuple(adjusted))
        phases.append(ContinuationPhase(begin, begin + instruction.size, depth, saved,
                                        bytes(metadata), native_metadata, unscaled_xmm))
        written = {instruction.reg_name(register) for register in instruction.regs_access()[1]}
        for register in written & NONVOLATILE:
            if register.startswith(('xmm', 'ymm', 'zmm')):
                if register[:3] != 'xmm' or int(register[3:]) not in native_vectors:
                    raise ValueError('The continuation vector write lacks an active native save.')
            else:
                number = REGISTERS.index(normalize_register(register))
                if number not in native_gprs | {value for value, _ in saved}:
                    raise ValueError('The continuation nonvolatile write lacks an active save.')
        if instruction.group(capstone.CS_GRP_CALL) or instruction.group(capstone.CS_GRP_RET):
            raise ValueError('The continuation has an unclassified call or return frame.')
        mnemonic = instruction.mnemonic
        if mnemonic in ('push', 'pushfq'):
            operand = instruction.operands[0] if instruction.operands else None
            number = REGISTERS.index(instruction.reg_name(operand.reg)) if operand and operand.type == capstone.x86.X86_OP_REG else None
            if number == 4:
                raise ValueError('The continuation needs a separate stack-pointer save contract.')
            slots.append(number)
        elif mnemonic in ('pop', 'popfq'):
            if not slots:
                raise ValueError('The continuation pop exceeds its temporary stack.')
            expected = slots.pop()
            if mnemonic == 'popfq' and expected is not None:
                raise ValueError('The continuation uses a saved register as flags.')
            if mnemonic == 'pop' and (instruction.operands[0].type != capstone.x86.X86_OP_REG
                    or REGISTERS.index(instruction.reg_name(instruction.operands[0].reg)) != expected):
                raise ValueError('The continuation restores a different temporary register.')
        elif mnemonic == 'lea' and instruction.op_str == 'rsp, [rsp + 8]':
            if not slots or slots.pop() is not None:
                raise ValueError('The continuation discards a saved register.')
        elif mnemonic in ('add', 'sub') and instruction.op_str.startswith('rsp, '):
            operand = instruction.operands[1]
            if operand.type != capstone.x86.X86_OP_IMM or operand.imm < 0 or operand.imm % 8:
                raise ValueError('The continuation has an unclassified stack allocation.')
            count = operand.imm // 8
            if mnemonic == 'sub':
                slots.extend([None] * count)
            else:
                if count > len(slots) or any(value is not None for value in slots[len(slots) - count:]):
                    raise ValueError('The continuation releases saved temporary registers.')
                if count:
                    del slots[-count:]
        elif written & {'rsp', 'esp', 'sp', 'spl'}:
            raise ValueError('The continuation has an unclassified stack transition.')
        if instruction.group(capstone.CS_GRP_JUMP) and slots:
            raise ValueError('The continuation branches with temporary stack storage active.')
    if slots or instructions[-1].mnemonic != 'jmp':
        raise ValueError('The continuation does not restore its stack before the native branch.')
    return tuple(phases)
