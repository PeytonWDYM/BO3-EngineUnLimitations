"""Export all six typed save-handle comparisons for Windows native-frame comparison."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import capstone

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode
from load_counts import LoadCounts
from save_handles import prepare_save_handles
from native_unwind import read_frame, active_operations, reference_image, stack_contract
from continuation_unwind import prepare_continuation_phases
from unwind import native_frames


def run(module, executable, output):
    output = output.resolve()
    if output.exists() or (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents:
        raise ValueError('Use a new private BO3 lab result directory.')
    code = CapturedCode(module, executable)
    arena = code.base + 0x20000000
    edits = prepare_save_handles(code, LoadCounts(arena + 0x2C40000), arena + 0x1A2000)
    frames = native_frames(code)
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    data = bytearray(b'BO3NFUW2' + struct.pack('<I', len(edits)))
    rows = []
    for edit in edits:
        owner = next(row for row in frames if row[0] <= edit.guard.rva < row[1])
        frame = read_frame(code, owner)
        assert frame.flags == 0 and not frame.parent
        operations = active_operations(frame, edit.guard.rva)
        reference, function, control = reference_image(code, frame, edit.guard.rva)
        stack, return_offset = stack_contract(operations)
        phases = prepare_continuation_phases(edit, operations)
        rebased = bytearray(edit.stub)
        for instruction in decoder.disasm(edit.stub, edit.stub_address):
            if instruction.group(capstone.CS_GRP_JUMP):
                assert instruction.imm_size == 4
                offset = instruction.address - edit.stub_address
                target = instruction.operands[0].imm - code.base - owner[0]
                struct.pack_into('<i', rebased, offset + instruction.imm_offset,
                                 target - (0x10000 + offset + instruction.size))
        source = bytearray(edit.replacement)
        for instruction in decoder.disasm(edit.replacement, code.base + edit.guard.rva):
            if instruction.group(capstone.CS_GRP_JUMP):
                struct.pack_into('<i', source, instruction.imm_offset, 0x10000 - control - instruction.size)
        data += struct.pack('<11I', edit.guard.rva, len(reference), *function, control,
                            len(stack), return_offset, len(edit.stub), len(phases), owner[1] - owner[0])
        data += reference + rebased + struct.pack('<I', len(source)) + source
        for offset, width, register in stack:
            data += struct.pack('<III', offset, width, register)
        for phase in phases:
            assert phase.stack_bytes == 0 and not phase.saved_registers
            data += struct.pack('<6I', phase.begin, phase.end, 0, len(phase.unwind_info), 0, len(phase.native_unwind_info))
            data += phase.unwind_info + phase.native_unwind_info
        rows.append({'site': hex(edit.guard.rva), 'owner': [hex(value) for value in owner],
                     'instructionBoundaryProbes': len(phases), 'nativeReturnOffset': return_offset})
    output.mkdir(parents=True)
    (output / 'native-unwind.bin').write_bytes(data)
    result = {'frames': rows, 'fixtureSha256': hashlib.sha256(data).hexdigest(), 'gameWrites': 0,
              'scope': 'Six typed save-handle compare stubs, complete active native frames, and instruction boundaries. No game execution.',
              'sources': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in
                          (Path(__file__), PATCHES / 'save_handles.py', PATCHES / 'native_unwind.py', PATCHES / 'continuation_unwind.py')}}
    (output / 'input-receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    return {'output': str(output), 'continuations': len(rows)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.output)))
