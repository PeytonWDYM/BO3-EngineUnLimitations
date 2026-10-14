"""Export six exact pose owner frames for owned Windows unwind and exception tests."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode, CodeGuard
from native_unwind import read_frame, active_operations
from temporal_rewind import PROBE_FUNCTION
from crash_frame import prepare_crash_frames
from shape import ActorShape
from temporal_layout import TemporalLayout
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_GRP_CALL, CS_GRP_JUMP
from capstone.x86_const import X86_OP_IMM

# Complete root code and complete GS/EH metadata from the pinned private capture.
OWNERS = (
    (0x15F5A0, 0x15F8AC, 0x3104D9C, 32, '9c1497fc3d47eec4fbfa5d144e47c8e52b59fe93734123e910af57f614058736', 'ce0d1e876589f37db3922d062a37990de610defa683716314b527e05dc242147', 0x30),
    (0x1580000, 0x158063F, 0x31480F0, 80, '61c8fd6755aea6255e4c9a4c2107b9b0138d75c81feba84adf0bc6ca03ee180b', '0bd9ef33a28f7ba3a903dc9e500a7916396bc17dc51dbc8854c76dd2acbe796b', 0xD0),
    (0x1C05E00, 0x1C09CA0, 0x3165878, 60, 'cfc97d6ab7e6833256b0ea665626eeeaac991011e46104dd0dfe1f9d3a803ed9', '3ccc558472e565134108fa783db4db9075e4eb915ca69be9b13a6744f34578b7', 0xC0),
    (0x1C09CA0, 0x1C09DC6, 0x31659D0, 36, '52f56ebb35a5bdd27f89d00dd2095d467ea62a2d98d399ec2e9a6017fc28850a', '8c2007d62c650d5b93c981daa234acd7f5d922b1c2afa80853bcf61b01aff76f', 0x50),
    (0x1C0E330, 0x1C104F4, 0x3165918, 68, '171957313dd28fba99acac5bc8b43d2f862d46c81822507dd788005ed3a4b65d', 'e70d7d406c2fc8e5d0a8aac32d3c6ca403fbc124b0315232f4ece196274a9188', 0xD0),
    (0x1C10540, 0x1C14424, 0x3165AA4, 60, 'b3d6ad09be2d3ebbca7db96daa5789724d33f899b839c210a70bdc79fa1f70bd', 'aa875c48b92f09ed88b0ae2a6cd3c693c182b231a48e89b3869021464829b46e', 0xC0),
)
HANDLER = CodeGuard(0x2BC8714, 143, 'f4eea106230124b30b7de1996a3a475c29bb3982d11f446bcca07ac0484b96b4')
COMMON = CodeGuard(0x2BC3A24, 99, 'b17460e875c3ee6c6e0ea3ad52fa5c3b2d83c39f2a7a3547dcb87eb185dd1b0d')
HANDLER_UNWIND = CodeGuard(0x3243364, 24, '884da46584569a54a577b24a56bacaf087b23a0492ae60398b44ab8c145f53ae')
COMMON_UNWIND = CodeGuard(0x3242F10, 8, 'eb874a2d5756386f3a7d463290a08f132ac00fa4e4080cfb811bafc05b2569b2')
PROBE_UNWIND = CodeGuard(0x32431E0, 8, 'dfe5ee239990e1d937b2731ee5f4016a954e31e1caec0bbf76bf32c1432c8003')


def stack_contract(operations):
    cursor, saves = 0, []
    for operation in operations:
        if operation.opcode == 0:
            saves.append((cursor, 8, operation.info))
            cursor += 8
        elif operation.opcode in (1, 2):
            cursor += operation.allocation
        elif operation.opcode in (4, 5, 8, 9):
            width = 16 if operation.opcode in (8, 9) else 8
            offset = operation.value * width if operation.opcode in (4, 8) else operation.value
            saves.append((offset, width, operation.info))
        else:
            raise ValueError('A pose frame has an unknown stack operation.')
    if cursor >= 65536 or any(offset + width >= 65536 for offset, width, _ in saves):
        raise ValueError('A pose stack exceeds the owned comparison allocation.')
    return tuple(saves), cursor


def rebase(raw, origin, destination, targets):
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    result = bytearray(raw)
    instructions = list(decoder.disasm(raw, origin))
    if sum(item.size for item in instructions) != len(raw):
        raise ValueError('The guarded helper does not decode completely.')
    for item in instructions:
        if (item.group(CS_GRP_CALL) or item.group(CS_GRP_JUMP)) and item.operands[0].type == X86_OP_IMM:
            target = item.operands[0].imm
            target = destination + target - origin if origin <= target < origin + len(raw) else targets[target]
            offset = item.address - origin + item.imm_offset
            result[offset:offset + item.imm_size] = (target - (destination + item.address - origin + item.size)).to_bytes(item.imm_size, 'little', signed=True)
    return bytes(result)


def run(module, executable, output, expanded=False):
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new output directory inside the private BO3 lab.')
    code = CapturedCode(module, executable)
    plan = prepare_crash_frames(code, TemporalLayout(ActorShape(500)), code.base + code.meta['imageSize'] + 0x1B0000) if expanded else None
    guards = [HANDLER, COMMON, PROBE_FUNCTION, HANDLER_UNWIND, COMMON_UNWIND, PROBE_UNWIND]
    captured = {guard.rva: code.guarded(guard) for guard in guards}
    handler = rebase(captured[HANDLER.rva], HANDLER.rva, 0x5000, {COMMON.rva: 0x5100, 0x2BC3920: 0x5420})
    common = rebase(captured[COMMON.rva], COMMON.rva, 0x5100, {0x2BC3AA0: 0x5410})
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    data = bytearray(b'BO3POSE1' + struct.pack('<I', len(OWNERS)))
    inventory = []
    for start, end, unwind, metadata_size, body_hash, unwind_hash, object_offset in OWNERS:
        body_guard, unwind_guard = CodeGuard(start, end - start, body_hash), CodeGuard(unwind, metadata_size, unwind_hash)
        guards.extend((body_guard, unwind_guard))
        native_body = code.guarded(body_guard)
        native_metadata = code.guarded(unwind_guard)
        probe_edit = None
        if plan:
            native_body = bytearray(native_body)
            for edit in plan.edits:
                if start <= edit.guard.rva < end:
                    offset = edit.guard.rva - start
                    native_body[offset:offset + edit.guard.size] = edit.replacement
                    if edit.stub: probe_edit = edit
                elif edit.guard.rva == unwind:
                    native_metadata = edit.replacement
            native_body = bytes(native_body)
        class FrameSource:
            meta = code.meta
            def read(self, rva, size):
                if unwind <= rva and rva + size <= unwind + len(native_metadata):
                    return native_metadata[rva - unwind:rva - unwind + size]
                return code.read(rva, size)
        frame = read_frame(FrameSource(), (start, end, unwind))
        tail = metadata_size - 12
        handler_rva, function_info_rva, cookie_word = struct.unpack_from('<III', native_metadata, tail)
        if frame.flags != 3 or handler_rva != HANDLER.rva:
            raise ValueError('A pose owner has an unknown GS/EH handler.')
        function_info = bytearray(code.read(function_info_rva, 40))
        fields = struct.unpack('<10I', function_info)
        if fields[0] != 0x19930522 or fields[1] != 1 or fields[3] or fields[9] != 1:
            raise ValueError('A pose owner has an unknown C++ cleanup map.')
        cleanup_map_rva, state_map_rva, state_count = fields[2], fields[6], fields[5]
        cleanup_state, cleanup_rva = struct.unpack('<iI', code.read(cleanup_map_rva, 8))
        if cleanup_state != -1:
            raise ValueError('A pose owner has an unknown cleanup state.')
        cleanup = code.read(cleanup_rva, 12)
        expected_cleanup = bytes.fromhex('488d8a') + struct.pack('<I', object_offset)
        if cleanup[:7] != expected_cleanup:
            raise ValueError('A pose cleanup selects a different stack object.')
        cleanup = rebase(cleanup, cleanup_rva, 0x5300, {0x15E5B0: 0x5430})
        state_map = list(struct.iter_unpack('<Ii', code.read(state_map_rva, state_count * 8)))
        body_pc = next(pc for (pc, state), (next_pc, _) in zip(state_map, state_map[1:]) if state == 0 and next_pc - pc >= 24)
        instructions = list(decoder.disasm(native_body, start))
        cookie_call = next(item for item in instructions if item.mnemonic == 'call' and item.op_str == '0x2bc3aa0')
        cookie_load = next(item.address for item in instructions if item.address < cookie_call.address and item.mnemonic == 'mov' and item.op_str.startswith('rcx, qword ptr') and instructions[instructions.index(item) + 1].mnemonic == 'xor')
        body = bytearray(native_body)
        # The fixture executes captured prolog and epilog. It replaces only the body and its external endpoints.
        body[frame.prolog:frame.prolog + 5] = b'\xe9' + struct.pack('<i', body_pc - start - frame.prolog - 5)
        authored = bytes.fromhex('488d8c24') + struct.pack('<I', object_offset)
        call_offset = body_pc - start + len(authored)
        authored += b'\xe8' + struct.pack('<i', 0x5400 - call_offset - 5)
        jump_offset = body_pc - start + len(authored)
        authored += b'\xe9' + struct.pack('<i', cookie_load - start - jump_offset - 5)
        body[body_pc - start:body_pc - start + len(authored)] = authored
        for item in decoder.disasm(native_body[:frame.prolog], start):
            offset = item.address - start
            if item.mnemonic == 'call':
                if item.op_str != '0x2bc57a0' and not (probe_edit and item.address == probe_edit.guard.rva):
                    raise ValueError('A pose prolog calls an unknown helper.')
                target = 0x6000 if probe_edit and item.address == probe_edit.guard.rva else 0x5200
                struct.pack_into('<i', body, offset + item.imm_offset, target - offset - item.size)
            if item.mnemonic == 'mov' and item.op_str.startswith('rax, qword ptr [rip + '):
                struct.pack_into('<i', body, offset + item.disp_offset, 0x9000 - offset - item.size)
        struct.pack_into('<i', body, cookie_call.address - start + cookie_call.imm_offset, 0x5410 - (cookie_call.address - start + cookie_call.size))
        metadata = bytearray(native_metadata)
        struct.pack_into('<II', metadata, tail, 0x5000, 0x9100)
        struct.pack_into('<II', function_info, 8, 0x9140, fields[3])
        struct.pack_into('<I', function_info, 24, 0x9180)
        map_bytes = b''.join(struct.pack('<Ii', pc - start, state) for pc, state in state_map)
        blobs = ((0, bytes(body)), (0x5000, handler), (0x5100, common), (0x5200, captured[PROBE_FUNCTION.rva]), (0x5300, cleanup),
                 (0x8000, bytes(metadata)), (0x8100, captured[HANDLER_UNWIND.rva]), (0x8140, captured[COMMON_UNWIND.rva]),
                 (0x8180, captured[PROBE_UNWIND.rva]), (0x9100, bytes(function_info)), (0x9140, struct.pack('<iI', -1, 0x5300)), (0x9180, map_bytes))
        runtimes = [(0, end - start, 0x8000), (0x5000, 0x508F, 0x8100), (0x5100, 0x5163, 0x8140), (0x5200, 0x524E, 0x8180)]
        probe_points = []
        if probe_edit:
            probe_body = rebase(probe_edit.stub, probe_edit.stub_address, 0x6000, {code.base + PROBE_FUNCTION.rva: 0x5200})
            blobs += ((0x6000, probe_body),)
            phases = [phase for phase in plan.probes if probe_edit.stub_address <= phase.begin < probe_edit.stub_address + len(probe_edit.stub)]
            for index, phase in enumerate(phases):
                begin, end_phase = phase.begin - probe_edit.stub_address + 0x6000, phase.end - probe_edit.stub_address + 0x6000
                metadata_offset = 0x8200 + index * 64
                blobs += ((metadata_offset, phase.metadata),)
                runtimes.append((begin, end_phase, metadata_offset))
                saves, return_offset = stack_contract(phase.operations)
                probe_points.append((begin, return_offset, saves, len(runtimes) - 1))
        points = [item.address - start for item in decoder.disasm(native_body[:frame.prolog], start)] + [frame.prolog, body_pc - start]
        allocation = sum(op.allocation for op in frame.operations)
        data += struct.pack('<9I', start, end - start, frame.prolog, object_offset, 500 if expanded else 64, allocation, len(blobs), len(points) + len(probe_points), len(runtimes))
        for runtime in runtimes:
            data += struct.pack('<III', *runtime)
        for rva, raw in blobs:
            data += struct.pack('<II', rva, len(raw)) + raw
        contracts = []
        for point in points:
            saves, return_offset = stack_contract(active_operations(frame, start + point))
            contracts.append((point, return_offset, saves, 0, 0, 0, 0xFFFFFFFF))
        body_saves, body_return = stack_contract(frame.operations)
        delta, gpr_mask, xmm_mask, r11_active = 0, 0, 0, False
        for item in decoder.disasm(native_body[cookie_call.address - start + 5:], cookie_call.address + 5):
            saves = tuple((offset - delta, width, reg) for offset, width, reg in body_saves if offset >= delta)
            contracts.append((item.address - start, body_return - delta, saves, 0, gpr_mask, xmm_mask,
                              (allocation - delta) & 0xFFFFFFFF if r11_active else 0xFFFFFFFF))
            if item.mnemonic == 'ret': break
            destination = item.op_str.split(',')[0]
            if item.mnemonic == 'pop':
                names = ('rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi','r8','r9','r10','r11','r12','r13','r14','r15')
                gpr_mask |= 1 << names.index(destination)
                delta += 8
            elif item.mnemonic == 'add' and destination == 'rsp': delta += item.operands[1].imm
            elif item.mnemonic == 'mov' and item.op_str == 'rsp, r11': delta = allocation
            elif item.mnemonic == 'lea' and destination == 'r11': r11_active = True
            elif item.mnemonic == 'mov' and destination == 'rbx': gpr_mask |= 1 << 3
            elif item.mnemonic == 'movaps' and destination.startswith('xmm'): xmm_mask |= 1 << int(destination[3:])
        contracts += [(point, return_offset, saves, function_index, 0, 0, 0xFFFFFFFF) for point, return_offset, saves, function_index in probe_points]
        # The header precedes the variable contracts, so update its point count after the epilog inventory.
        header_offset = len(data) - sum(8 + len(raw) for _, raw in blobs) - len(runtimes) * 12 - 36
        struct.pack_into('<I', data, header_offset + 28, len(contracts))
        for point, return_offset, saves, function_index, gpr_mask, xmm_mask, r11_offset in contracts:
            data += struct.pack('<7I', point, return_offset, len(saves), function_index, gpr_mask, xmm_mask, r11_offset)
            for offset, width, register in saves:
                data += struct.pack('<III', offset, width, register)
        inventory.append({'beginRva': hex(start), 'endRva': hex(end), 'unwindRva': hex(unwind), 'allocation': allocation,
                          'prologBytes': frame.prolog, 'cookieWord': cookie_word, 'objectOffset': object_offset,
                          'functionInfoRva': hex(function_info_rva), 'cleanupRva': hex(cleanup_rva), 'instructionBoundaryCount': len(contracts)})
        for rva, size in ((function_info_rva, 40), (cleanup_map_rva, 8), (state_map_rva, state_count * 8), (cleanup_rva, 12)):
            guards.append(code.guard(rva, size))
    output.mkdir(parents=True)
    (output / 'pose-backup-frames.bin').write_bytes(data)
    receipt = {'scope': 'Six guarded Windows frame shells, captured GS/EH handlers and cleanup funclets with authored body, cookie and destructor endpoints and fixture CRT.',
               'executableSha256': code.executable_sha256, 'fixtureSha256': hashlib.sha256(data).hexdigest(), 'frames': inventory,
               'guards': [{'rva': hex(guard.rva), 'bytes': guard.size, 'sha256': guard.sha256} for guard in guards],
               'actors': 500 if expanded else 64, 'gameWrites': 0, 'gameCrtVerified': False, 'activationAllowed': False}
    (output / 'input-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return {'output': str(output), 'frames': len(OWNERS)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expanded', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.output, args.expanded), indent=2))
