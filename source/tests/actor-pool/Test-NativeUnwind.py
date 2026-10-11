"""Export guarded continuations for Windows comparison with their original native frames."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode
from table_layout import TableLayout, NativeSentientAddress, ExternalTableAddress
from storage_plan import StorageLayout
from table_plan import prepare
from unwind import native_frames
from native_unwind import read_frame, active_operations, reference_image, stack_contract
from continuation_unwind import prepare_continuation_phases
from temporal_layout import TemporalLayout
from temporal_restore import prepare_restore
import capstone


def run(module: Path, executable: Path, output: Path, include_temporal_restore: bool = False) -> dict:
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new output directory inside the private BO3 lab.')
    code = CapturedCode(module, executable)
    layout = TableLayout(NativeSentientAddress(code.base + 0x21000000), ExternalTableAddress(code.base + 0x22000000))
    storage = StorageLayout(*(code.base + offset for offset in (0x23000000, 0x24000000, 0x25000000, 0x26000000, 0x27000000)))
    plan = prepare(code, layout, code.base + 0x20000000, storage)
    edits = plan.rewrites
    if include_temporal_restore:
        edits += prepare_restore(code, TemporalLayout(layout.shape), code.base + 0x20180000)
    frames = native_frames(code)
    expected = 79 if include_temporal_restore else 78
    data = bytearray(b'BO3NFUW1' + struct.pack('<I', expected))
    rows = []
    for edit in edits:
        if not edit.stub:
            continue
        owner = next((frame for frame in frames if frame[0] <= edit.guard.rva < frame[1]), None)
        if owner is None:
            continue
        frame = read_frame(code, owner)
        operations = active_operations(frame, edit.guard.rva)
        reference, function, control = reference_image(code, frame, edit.guard.rva)
        stack, return_offset = stack_contract(operations)
        phases = prepare_continuation_phases(edit, operations)
        lineage = []
        current = frame
        while current is not None:
            lineage.append(current.runtime)
            current = current.parent
        origin = min(item[0] for item in lineage)
        procedure_end = max(item[1] for item in lineage) - origin
        # The owned allocation uses one base: native code at zero and stubs at 0x10000.
        # Rebase branch operands so Windows sees the same logical native destinations.
        decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        decoder.detail = True
        rebased = bytearray(edit.stub)
        for instruction in decoder.disasm(edit.stub, edit.stub_address):
            if instruction.group(capstone.CS_GRP_JUMP):
                destination = instruction.operands[0]
                if destination.type != capstone.x86.X86_OP_IMM or instruction.imm_size != 4:
                    raise ValueError('The guarded stub branch requires a different owned relocation contract.')
                offset = instruction.address - edit.stub_address
                target = destination.imm - code.base - origin
                struct.pack_into('<i', rebased, offset + instruction.imm_offset, target - (0x10000 + offset + instruction.size))
        data += struct.pack('<11I', edit.guard.rva, len(reference), *function, control,
                            len(stack), return_offset, len(edit.stub), len(phases), procedure_end)
        data += reference + rebased
        for offset, width, register in stack:
            data += struct.pack('<III', offset, width, register)
        for phase in phases:
            data += struct.pack('<6I', phase.begin, phase.end, phase.stack_bytes, len(phase.unwind_info),
                                len(phase.saved_registers), len(phase.native_unwind_info))
            data += phase.unwind_info + phase.native_unwind_info
            for register, offset in phase.saved_registers:
                data += struct.pack('<II', register, offset)
        rows.append({'siteRva': hex(edit.guard.rva), 'stubSha256': hashlib.sha256(edit.stub).hexdigest(),
                     'ownedRebasedStubSha256': hashlib.sha256(rebased).hexdigest(),
                     'nativeFrame': list(owner), 'partialProlog': edit.guard.rva - owner[0] < frame.prolog,
                     'handlerOmittedForOwnedComparison': frame.has_handler,
                     'unscaledXmmPhasesNotRuntimeAdmitted': sum(phase.unscaled_xmm_phase for phase in phases),
                     'instructionBoundaryProbes': len(phases), 'nativeReturnOffset': return_offset})
    if len(rows) != expected:
        raise ValueError('The guarded native continuation inventory is incomplete.')
    output.mkdir(parents=True)
    (output / 'native-unwind.bin').write_bytes(data)
    receipt = {'scope': 'Owned Windows native frame comparison only. Handler dispatch and game registration remain gated.',
               'continuations': rows, 'fixtureSha256': hashlib.sha256(data).hexdigest(),
               'includeTemporalRestore': include_temporal_restore,
               'sourceFiles': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in [PATCHES / 'native_unwind.py', PATCHES / 'continuation_unwind.py',
                                            PATCHES / 'temporal_layout.py', PATCHES / 'temporal_restore.py', Path(__file__)]},
               'moduleManifestSha256': hashlib.sha256(module.read_bytes()).hexdigest(), 'gameWrites': 0}
    (output / 'input-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return {'output': str(output), 'continuations': len(rows), 'fixtureSha256': receipt['fixtureSha256']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include-temporal-restore', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.output, args.include_temporal_restore), indent=2))
