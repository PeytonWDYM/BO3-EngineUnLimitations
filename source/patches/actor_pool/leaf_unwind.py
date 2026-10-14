"""Describe instruction-boundary stack phases for the exact owned leaf stubs."""
from dataclasses import dataclass

from captured_code import Rewrite
from leaf_frames import NONVOLATILE


@dataclass(frozen=True)
class LeafPhase:
    begin: int
    end: int
    stack_bytes: int
    unwind_info: bytes


def prepare_leaf_phases(edit: Rewrite) -> tuple[LeafPhase, ...]:
    import capstone
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    instructions = list(decoder.disasm(edit.stub, edit.stub_address))
    if not instructions or sum(item.size for item in instructions) != len(edit.stub):
        raise ValueError('The leaf stub does not decode completely.')
    depth = 0
    phases = []
    for instruction in instructions:
        written = {instruction.reg_name(register) for register in instruction.regs_access()[1]}
        if written & NONVOLATILE or instruction.group(capstone.CS_GRP_CALL):
            raise ValueError('The leaf stub needs a nonvolatile or call-frame contract.')
        if depth < 0 or depth > 128 or depth % 8:
            raise ValueError('The leaf stub stack depth exceeds its admitted allocation contract.')
        # Each runtime entry starts in the already-established stack phase.
        # CodeOffset zero applies its ALLOC_SMALL even at that entry's first byte.
        metadata = bytes((1, 0, 1, 0, 0, ((depth // 8 - 1) << 4) | 2, 0, 0)) if depth else bytes((1, 0, 0, 0))
        begin = instruction.address - edit.stub_address
        phases.append(LeafPhase(begin, begin + instruction.size, depth, metadata))
        mnemonic = instruction.mnemonic
        if mnemonic in ('push', 'pushfq'):
            depth += 8
        elif mnemonic in ('pop', 'popfq'):
            depth -= 8
        elif mnemonic in ('add', 'sub') and instruction.op_str.startswith('rsp, '):
            if instruction.operands[1].type != capstone.x86.X86_OP_IMM:
                raise ValueError('The leaf stub has a dynamic stack allocation.')
            depth += instruction.operands[1].imm * (1 if mnemonic == 'sub' else -1)
        elif mnemonic == 'lea' and instruction.op_str == 'rsp, [rsp + 8]':
            depth -= 8
        elif instruction.group(capstone.CS_GRP_RET):
            if depth or instruction.operands:
                raise ValueError('The leaf stub returns before restoring its stack.')
        elif written & {'rsp', 'esp', 'sp', 'spl'}:
            raise ValueError('The leaf stub has an unclassified stack transition.')
        if instruction.group(capstone.CS_GRP_JUMP) and depth:
            raise ValueError('The leaf stub branches before restoring its stack.')
    if depth:
        raise ValueError('The leaf stub leaves a stack allocation active.')
    return tuple(phases)
