"""Size the complete pose backup object in its six guarded native owning frames."""
from dataclasses import dataclass, replace
import struct

from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_GRP_CALL, CS_GRP_JUMP, CS_GRP_RET
from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RBP, X86_REG_RSP
from captured_code import CodeGuard, Rewrite
from caller_unwind import CALLER_UNWIND, prepare_caller_unwind
from native_unwind import Operation, read_frame, encode
from relocate_function import replace_displacement
from temporal_caller import prepare_caller, caller_frame
from temporal_rewind import PROBE_FUNCTION

OWNERS = (
    (0x15F5A0, 0x15F8AC, 0x3104D9C, 32, '9c1497fc3d47eec4fbfa5d144e47c8e52b59fe93734123e910af57f614058736', 'ce0d1e876589f37db3922d062a37990de610defa683716314b527e05dc242147', 0x30),
    (0x1580000, 0x158063F, 0x31480F0, 80, '61c8fd6755aea6255e4c9a4c2107b9b0138d75c81feba84adf0bc6ca03ee180b', '0bd9ef33a28f7ba3a903dc9e500a7916396bc17dc51dbc8854c76dd2acbe796b', 0xD0),
    (0x1C05E00, 0x1C09CA0, 0x3165878, 60, 'cfc97d6ab7e6833256b0ea665626eeeaac991011e46104dd0dfe1f9d3a803ed9', '3ccc558472e565134108fa783db4db9075e4eb915ca69be9b13a6744f34578b7', 0xC0),
    (0x1C09CA0, 0x1C09DC6, 0x31659D0, 36, '52f56ebb35a5bdd27f89d00dd2095d467ea62a2d98d399ec2e9a6017fc28850a', '8c2007d62c650d5b93c981daa234acd7f5d922b1c2afa80853bcf61b01aff76f', 0x50),
    (0x1C0E330, 0x1C104F4, 0x3165918, 68, '171957313dd28fba99acac5bc8b43d2f862d46c81822507dd788005ed3a4b65d', 'e70d7d406c2fc8e5d0a8aac32d3c6ca403fbc124b0315232f4ece196274a9188', 0xD0),
    (0x1C10540, 0x1C14424, 0x3165AA4, 60, 'b3d6ad09be2d3ebbca7db96daa5789724d33f899b839c210a70bdc79fa1f70bd', 'aa875c48b92f09ed88b0ae2a6cd3c693c182b231a48e89b3869021464829b46e', 0xC0),
)
HELPERS = (
    CodeGuard(0x27C1880, 186, '07783c81341ab5062389d1722840e0a6a318f2c79d76521518f1a134bd377d9a'),
    CodeGuard(0x27C1940, 380, '09392634d3cc5aa409516001b12585661e8f4cc6d0b1e9c7c5fba6b6361f61da'),
)


@dataclass(frozen=True)
class ProbePhase:
    begin: int
    end: int
    metadata: bytes
    stack_bytes: int
    operations: tuple[Operation, ...]


@dataclass(frozen=True)
class FramePlan:
    edits: tuple[Rewrite, ...]
    probes: tuple[ProbePhase, ...]


def _probe(code, instruction, allocation, address, native_pushes):
    # The hook owns its temporary return slot. The native cookie is not set yet.
    raw = bytearray(b'\x50\xb8' + struct.pack('<I', allocation))
    raw += b'\xe8' + struct.pack('<i', code.base + PROBE_FUNCTION.rva - (address + len(raw) + 5))
    raw += bytes.fromhex('58415b4983c3024881ec') + struct.pack('<I', allocation) + bytes.fromhex('41ffe3')
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    instructions = list(decoder.disasm(bytes(raw), address))
    depth = 8
    phases = []
    for item in instructions:
        temporary = (Operation(0, 1, 0, depth // 8),) if depth >= 136 else (Operation(0, 2, depth // 8 - 1),) if depth else ()
        operations = temporary + tuple(replace(op, offset=0) for op in native_pushes)
        phases.append(ProbePhase(item.address, item.address + item.size, encode(operations), depth, operations))
        if item.mnemonic == 'push': depth += 8
        elif item.mnemonic == 'pop': depth -= 8
        elif item.mnemonic == 'sub': depth += allocation
    if depth != allocation:
        raise ValueError('The pose probe does not retain its complete native allocation.')
    hook = b'\xe8' + struct.pack('<i', address - instruction.address - 5) + b'\x90\x90'
    if instruction.size != len(hook):
        raise ValueError('The pose allocation hook has a different native extent.')
    return Rewrite('pose_backup_probe', code.guard(instruction.address - code.base, instruction.size), hook, address, bytes(raw)), tuple(phases)


def _verify_probe_scratch(instructions, entry):
    """Check every reachable path until a definition or native ABI call kills the incoming R11 value."""
    by_address = {item.address: item for item in instructions}
    pending, seen = [entry], set()
    while pending:
        address = pending.pop()
        if address in seen: continue
        seen.add(address)
        if address not in by_address:
            raise ValueError('A pose probe scratch path has an unknown instruction boundary.')
        item = by_address[address]
        reads, writes = item.regs_access()
        read_names, write_names = {item.reg_name(reg) for reg in reads}, {item.reg_name(reg) for reg in writes}
        if read_names & {'r11', 'r11d', 'r11w', 'r11b'}:
            raise ValueError('A pose allocation owner uses the incoming probe scratch register.')
        if write_names & {'r11', 'r11d'} or item.group(CS_GRP_CALL) or item.group(CS_GRP_RET):
            continue
        if item.group(CS_GRP_JUMP):
            if item.operands[0].type != X86_OP_IMM:
                raise ValueError('A pose probe scratch path contains an unclassified indirect branch.')
            pending.append(item.operands[0].imm)
            if item.mnemonic == 'jmp': continue
        pending.append(item.address + item.size)


def prepare_crash_frames(code, layout, stub_address: int) -> FramePlan:
    """Compose pose growth with the separate temporal output buffer in the shared caller."""
    growth = (layout.shape.actors - 64) * 24
    if layout.shape.actors != 500 or growth != 0x28E0:
        raise ValueError('The pose frame plan requires the admitted 500-actor layout.')
    code.guarded(PROBE_FUNCTION)
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    edits, probes = [], []
    caller_edits = {edit.guard.rva: edit for edit in prepare_caller(code, layout)}
    caller_metadata = prepare_caller_unwind(code, layout)
    for index, (start, end, unwind, size, body_hash, metadata_hash, object_offset) in enumerate(OWNERS):
        body = code.guarded(CodeGuard(start, end - start, body_hash))
        metadata = bytearray(code.guarded(CodeGuard(unwind, size, metadata_hash)))
        frame = read_frame(code, (start, end, unwind))
        if frame.flags != 3 or frame.parent:
            raise ValueError('A pose frame has a different native handler contract.')
        native_allocation = next(op.allocation for op in frame.operations if op.opcode == 1)
        temporal_growth = caller_frame(layout).growth if start == 0x1580000 else 0
        allocation = native_allocation + growth + temporal_growth
        flag_offset = object_offset + 0x600
        rbp_threshold = flag_offset - 0x100
        instructions = list(decoder.disasm(body, code.base + start))
        for item in instructions:
            rva = item.address - code.base
            replacement = caller_edits[rva].replacement if rva in caller_edits else None
            if item.mnemonic == 'sub' and item.op_str == f'rsp, {hex(native_allocation)}' and item.address < code.base + start + frame.prolog:
                _verify_probe_scratch(instructions, item.address + item.size)
                native_pushes = tuple(op for op in frame.operations if op.opcode == 0 and op.offset <= item.address - code.base - start)
                edit, phases = _probe(code, item, allocation, stub_address + index * 128, native_pushes)
                edits.append(edit); probes.extend(phases); continue
            if item.mnemonic == 'mov' and item.op_str == f'eax, {hex(native_allocation)}' and item.address < code.base + start + frame.prolog:
                replacement = b'\xb8' + struct.pack('<I', allocation)
            elif item.mnemonic == 'add' and item.op_str == f'rsp, {hex(native_allocation)}':
                replacement = bytes(item.bytes[:3]) + struct.pack('<I', allocation)
            else:
                for operand in item.operands:
                    if operand.type != X86_OP_MEM:
                        continue
                    member = operand.mem
                    value = None
                    if member.base == X86_REG_RSP and member.disp < 0 and item.mnemonic == 'lea' and item.op_str.startswith('rbp, '):
                        value = member.disp - growth - temporal_growth
                    elif item.mnemonic == 'lea' and item.op_str.startswith('rbp, ') and item.address < code.base + start + frame.prolog:
                        value = member.disp - growth
                    elif member.base == X86_REG_RSP and member.disp >= flag_offset:
                        value = member.disp + growth
                        if start == 0x1580000 and member.disp >= 0x3D30: value += temporal_growth
                    elif member.base == X86_REG_RBP and member.disp >= rbp_threshold:
                        value = member.disp + growth
                        if start == 0x1580000 and member.disp >= 0x35D0: value += temporal_growth
                    if value is not None:
                        replacement = replace_displacement(item, value)
            if replacement is not None and replacement != bytes(item.bytes):
                if len(replacement) != item.size:
                    raise ValueError('A pose frame member needs a different instruction extent.')
                edits.append(Rewrite('pose_backup_frame', code.guard(rva, item.size), replacement))
        if start == 0x1580000: metadata = bytearray(caller_metadata.replacement)
        slot = 0
        for op in frame.operations:
            position = 4 + slot * 2
            if op.opcode == 1:
                struct.pack_into('<H', metadata, position + 2, allocation // 8)
            elif op.opcode in (4, 8):
                scale = 16 if op.opcode == 8 else 8
                struct.pack_into('<H', metadata, position + 2, op.value + (growth + temporal_growth) // scale)
            elif op.opcode != 0:
                raise ValueError('A pose frame has an unknown native unwind operation.')
            slot += 2 if op.opcode in (1, 4, 8) else 1
        cookie = struct.unpack_from('<I', metadata, len(metadata) - 4)[0]
        struct.pack_into('<I', metadata, len(metadata) - 4, (cookie & ~7) + growth | (cookie & 7))
        edits.append(Rewrite('pose_backup_frame_unwind', CodeGuard(unwind, size, metadata_hash), bytes(metadata)))
        # Native IP/state maps and cleanup funclets keep their locations and low-frame object operands.
        function_info = struct.unpack_from('<I', metadata, len(metadata) - 8)[0]
        info = struct.unpack('<10I', code.guarded(code.guard(function_info, 40)))
        if info[0] != 0x19930522 or info[1] != 1 or info[3] or info[9] != 1:
            raise ValueError('A pose frame has an unknown native cleanup descriptor.')
        cleanup_map = code.guarded(code.guard(info[2], 8))
        code.guarded(code.guard(info[6], info[5] * 8))
        state, cleanup = struct.unpack('<iI', cleanup_map)
        leaf = code.guarded(code.guard(cleanup, 12))
        if state != -1 or leaf[:7] != bytes.fromhex('488d8a') + struct.pack('<I', object_offset):
            raise ValueError('A pose cleanup selects a different stack object.')
    for guard in HELPERS:
        body = code.guarded(guard)
        for item in decoder.disasm(body, code.base + guard.rva):
            for operand in item.operands:
                if operand.type != X86_OP_MEM: continue
                value = {0x308: layout.shape.actors * 12 + 8, -0x308: -layout.shape.actors * 12 - 8,
                         -0x304: -layout.shape.actors * 12 - 4, -0x300: -layout.shape.actors * 12,
                         0x600: layout.shape.actors * 24}.get(operand.mem.disp)
                if value is not None:
                    replacement = replace_displacement(item, value)
                    if len(replacement) != item.size: raise ValueError('A pose helper member has a different instruction extent.')
                    edits.append(Rewrite('pose_backup_helper_member', code.guard(item.address - code.base, item.size), replacement))
    ordered = tuple(sorted(edits, key=lambda edit: edit.guard.rva))
    if any(a.guard.rva + a.guard.size > b.guard.rva for a, b in zip(ordered, ordered[1:])):
        raise ValueError('The pose plan overlaps source edits.')
    return FramePlan(ordered, tuple(probes))
