"""Export guarded caller and handler bytes for an owned Windows C++ exception test."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode, CodeGuard
from temporal_layout import TemporalLayout
from temporal_caller import CALLER_FUNCTION, prepare_caller
from temporal_rewind import PROBE_FUNCTION
from caller_unwind import CALLER_UNWIND, FUNCTION_INFO, CLEANUP_MAP, STATE_MAP, CLEANUP_LEAF, prepare_caller_unwind
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_GRP_CALL, CS_GRP_JUMP
from capstone.x86_const import X86_OP_IMM

HANDLER = CodeGuard(0x2BC8714, 143, 'f4eea106230124b30b7de1996a3a475c29bb3982d11f446bcca07ac0484b96b4')
COMMON = CodeGuard(0x2BC3A24, 99, 'b17460e875c3ee6c6e0ea3ad52fa5c3b2d83c39f2a7a3547dcb87eb185dd1b0d')
HANDLER_UNWIND = CodeGuard(0x3243364, 24, '884da46584569a54a577b24a56bacaf087b23a0492ae60398b44ab8c145f53ae')
COMMON_UNWIND = CodeGuard(0x3242F10, 8, 'eb874a2d5756386f3a7d463290a08f132ac00fa4e4080cfb811bafc05b2569b2')
PROBE_UNWIND = CodeGuard(0x32431E0, 8, 'dfe5ee239990e1d937b2731ee5f4016a954e31e1caec0bbf76bf32c1432c8003')


def rebase(raw: bytes, origin: int, destination: int, targets: dict[int, int]) -> bytes:
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    result = bytearray(raw)
    instructions = list(decoder.disasm(raw, origin))
    if sum(instruction.size for instruction in instructions) != len(raw):
        raise ValueError('The guarded handler body does not decode completely.')
    for instruction in instructions:
        if (instruction.group(CS_GRP_CALL) or instruction.group(CS_GRP_JUMP)) and instruction.operands[0].type == X86_OP_IMM:
            target = instruction.operands[0].imm
            target = destination + target - origin if origin <= target < origin + len(raw) else targets[target]
            offset = instruction.address - origin
            value = target - (destination + offset + instruction.size)
            result[offset + instruction.imm_offset:offset + instruction.imm_offset + instruction.imm_size] = value.to_bytes(instruction.imm_size, 'little', signed=True)
    return bytes(result)


def run(module: Path, executable: Path, output: Path) -> dict:
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new directory inside the private BO3 lab.')
    code = CapturedCode(module, executable)
    guards = (CALLER_FUNCTION, CALLER_UNWIND, HANDLER, COMMON, PROBE_FUNCTION, CLEANUP_LEAF,
              FUNCTION_INFO, CLEANUP_MAP, STATE_MAP, HANDLER_UNWIND, COMMON_UNWIND, PROBE_UNWIND)
    captured = {guard.rva: code.guarded(guard) for guard in guards}
    handler = rebase(captured[HANDLER.rva], HANDLER.rva, 0x1000, {COMMON.rva: 0x1100, 0x2BC3920: 0x1410})
    common = rebase(captured[COMMON.rva], COMMON.rva, 0x1100, {0x2BC3AA0: 0x1400})
    cleanup = rebase(captured[CLEANUP_LEAF.rva], CLEANUP_LEAF.rva, 0x1300, {0x15E5B0: 0x1430})
    function_info = bytearray(captured[FUNCTION_INFO.rva])
    struct.pack_into('<I', function_info, 8, 0x3040)
    struct.pack_into('<I', function_info, 24, 0x3050)
    cleanup_map = struct.pack('<iI', -1, 0x1300)
    state_map = b''.join(struct.pack('<Ii', control - CALLER_FUNCTION.rva, state) for control, state in struct.iter_unpack('<Ii', captured[STATE_MAP.rva]))
    data = bytearray(b'BO3CEX01' + struct.pack('<I', 2))
    for expanded in (False, True):
        body = bytearray(captured[CALLER_FUNCTION.rva])
        if expanded:
            for edit in prepare_caller(code, TemporalLayout()):
                offset = edit.guard.rva - CALLER_FUNCTION.rva
                body[offset:offset + edit.guard.size] = edit.replacement
        metadata = bytearray(prepare_caller_unwind(code, TemporalLayout()).replacement if expanded else captured[CALLER_UNWIND.rva])
        struct.pack_into('<II', metadata, 68, 0x1000, 0x3000)
        struct.pack_into('<i', body, 0x1A, 0x1200 - 0x1E)
        struct.pack_into('<i', body, 0x8D, 0x4000 - 0x91)
        struct.pack_into('<i', body, 0x5E8, 0x1400 - 0x5EC)
        body[0x9B:0xA0] = b'\xe9' + struct.pack('<i', 0xAF - 0xA0)
        authored = b'\x48\x8d\x8c\x24\xd0\x00\x00\x00'
        if expanded:
            # Make the stale-cookie negative case deterministic without touching the expanded cookie.
            authored += bytes.fromhex('48c78424203d000000000000')
        call = 0xAF + len(authored)
        authored += b'\xe8' + struct.pack('<i', 0x1420 - (call + 5))
        jump = 0xAF + len(authored)
        authored += b'\xe9' + struct.pack('<i', 0x5DD - (jump + 5))
        body[0xAF:0xAF + len(authored)] = authored
        blobs = ((0, bytes(body)), (0x1000, handler), (0x1100, common), (0x1200, captured[PROBE_FUNCTION.rva]),
                 (0x1300, cleanup), (0x2000, bytes(metadata)), (0x2100, captured[HANDLER_UNWIND.rva]),
                 (0x2120, captured[COMMON_UNWIND.rva]), (0x2130, captured[PROBE_UNWIND.rva]),
                 (0x3000, bytes(function_info)), (0x3040, cleanup_map), (0x3050, state_map))
        data += struct.pack('<II', int(expanded), len(blobs))
        for rva, raw in blobs:
            data += struct.pack('<II', rva, len(raw)) + raw
    output.mkdir(parents=True)
    (output / 'caller-exception.bin').write_bytes(data)
    receipt = {'scope': 'Owned fixture. Complete captured caller prolog and epilog, native cookie handlers and cleanup leaf. Body, cookie endpoint, language CRT and destructor endpoint are authored.',
               'fixtureSha256': hashlib.sha256(data).hexdigest(), 'nativeGuards': [{'rva': hex(guard.rva), 'bytes': guard.size, 'sha256': guard.sha256} for guard in guards],
               'sourceFiles': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in
                               [PATCHES / 'caller_unwind.py', PATCHES / 'temporal_caller.py', Path(__file__)]},
               'gameWrites': 0, 'activationAllowed': False, 'gameCrtVerified': False}
    (output / 'input-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return {'output': str(output), 'variants': 2}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.output), indent=2))
