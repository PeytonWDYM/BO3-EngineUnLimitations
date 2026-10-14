"""Verify original frameless leaf contracts at sites absent from static pdata."""

from captured_code import CapturedCode, CodeGuard

NONVOLATILE = frozenset((
    'rbx', 'ebx', 'bx', 'bl', 'bh', 'rbp', 'ebp', 'bp', 'bpl',
    'rsi', 'esi', 'si', 'sil', 'rdi', 'edi', 'di', 'dil',
    *(f'r{index}{suffix}' for index in range(12, 16) for suffix in ('', 'd', 'w', 'b')),
    *(f'{prefix}{index}' for index in range(6, 16) for prefix in ('xmm', 'ymm', 'zmm')),
))
UNCLASSIFIED_STATE = frozenset((
    'vzeroall', 'ldmxcsr', 'vldmxcsr', 'fldcw', 'fldenv', 'frstor', 'fninit',
    'finit', 'fxrstor', 'fxrstor64', 'xrstor', 'xrstor64', 'xrstors', 'xrstors64',
))


def verify_leaves(code: CapturedCode, frames: tuple[tuple[int,int,int], ...], leaves: list[dict]) -> list[dict]:
    import capstone
    decoder = capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    decoder.detail = True
    for leaf in leaves:
        start,end = int(leaf['beginRva'],0),int(leaf['endRva'],0)
        raw = code.guarded(CodeGuard(start,end-start,leaf['sha256']))
        instructions = list(decoder.disasm(raw,code.base+start))
        if sum(item.size for item in instructions)!=len(raw):
            raise ValueError('An original leaf body does not decode completely.')
        if any(start<frame[1] and frame[0]<end for frame in frames):
            raise ValueError('An original leaf body overlaps a native frame record.')
        boundaries = {instruction.address for instruction in instructions}
        for instruction in instructions:
            written = {instruction.reg_name(register) for register in instruction.regs_access()[1]}
            # Capstone reports full vector aliases for VZEROUPPER. It preserves the nonvolatile low 128 bits.
            if instruction.mnemonic != 'vzeroupper' and written & NONVOLATILE:
                raise ValueError('An original leaf body changes a nonvolatile register.')
            if instruction.mnemonic in UNCLASSIFIED_STATE or instruction.group(capstone.CS_GRP_PRIVILEGE):
                raise ValueError('An original leaf body has unclassified ABI state effects.')
            if instruction.group(capstone.CS_GRP_RET):
                if instruction.mnemonic not in ('ret', 'repz ret') or instruction.operands:
                    raise ValueError('An original leaf return changes the native return contract.')
            elif written & {'rsp','esp','sp','spl'}:
                raise ValueError('An original leaf body changes its stack pointer.')
            if instruction.group(capstone.CS_GRP_CALL):
                raise ValueError('An original leaf body has a call.')
            if any(operand.type==capstone.x86.X86_OP_MEM and instruction.reg_name(operand.mem.base) in ('rsp','rbp')
                   for operand in instruction.operands):
                raise ValueError('An original leaf body depends on a local stack frame.')
            if instruction.group(capstone.CS_GRP_JUMP):
                destination = instruction.operands[0]
                if destination.type != capstone.x86.X86_OP_IMM:
                    raise ValueError('An original leaf body has an unclassified indirect branch.')
                inside = code.base+start<=destination.imm<code.base+end
                if inside and destination.imm not in boundaries:
                    raise ValueError('An original leaf branch misses an instruction boundary.')
                if not inside and instruction.mnemonic!='jmp':
                    raise ValueError('An original leaf conditional branch escapes its guarded body.')
        final = instructions[-1]
        if not final.group(capstone.CS_GRP_RET) and final.mnemonic != 'jmp':
            raise ValueError('An original leaf body falls through its guarded end.')
    return leaves
