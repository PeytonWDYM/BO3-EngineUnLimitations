"""Export guarded continuations for Windows comparison with their original native frames."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from dataclasses import replace

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode
from shape import ActorShape
from table_layout import TableLayout, NativeSentientAddress, ExternalTableAddress
from storage_plan import StorageLayout
from table_plan import prepare
from unwind import native_frames
from native_unwind import NativeFrame, read_frame, active_operations, reference_image, stack_contract
from continuation_unwind import prepare_continuation_phases
from temporal_layout import TemporalLayout
from temporal_restore import prepare_restore
from native_handlers import prepare_native_handler
import capstone


def run(module: Path, executable: Path, output: Path, include_temporal_restore: bool = False, actors: int = 300) -> dict:
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new output directory inside the private BO3 lab.')
    code = CapturedCode(module, executable)
    layout = TableLayout(NativeSentientAddress(code.base + 0x21000000), ExternalTableAddress(code.base + 0x22000000), ActorShape(actors))
    storage = StorageLayout(*(code.base + offset for offset in (0x24000000, 0x26000000, 0x28000000, 0x2A000000, 0x2C000000)))
    plan = prepare(code, layout, code.base + 0x20000000, storage)
    edits = plan.rewrites
    if include_temporal_restore:
        edits += prepare_restore(code, TemporalLayout(layout.shape), code.base + 0x20180000)
    frames = native_frames(code)
    handler_frames = [read_frame(code, owner) for owner in frames if owner[0] in
                      (0x15147A0, 0x1646AB0, 0x16471A0, 0x1C3E150, 0x1C3E860, 0x24D2FC0,
                       0x24EC870, 0x24F0BE0, 0x1C2F320, 0x24E7400, 0x24EA750, 0x24ED5F0)]
    assert len(handler_frames) == 12
    refusals = 0

    def refuse(changed_code: CapturedCode, changed_frame: NativeFrame) -> None:
        nonlocal refusals
        try:
            prepare_native_handler(changed_code, changed_frame)
        except ValueError:
            refusals += 1
        else:
            raise AssertionError('An unknown or altered native handler owner escaped refusal.')

    first = handler_frames[0]
    refuse(code, replace(first, runtime=(first.runtime[0] + 1, first.runtime[1], first.runtime[2])))

    class ChangedCode(CapturedCode):
        def read(self, rva: int, size: int) -> bytes:
            raw = bytearray(super().read(rva, size))
            if rva <= self.mutation < rva + size:
                raw[self.mutation - rva] ^= 1
            return bytes(raw)

    for frame, mutation in [(first, 0x2BC3A04), (first, 0x2BC3A24),
                            *((frame, frame.runtime[2] + 4 + ((code.read(frame.runtime[2], 4)[2] + 1) & ~1) * 2 + 4)
                              for frame in handler_frames)]:
        changed = object.__new__(ChangedCode)
        changed.__dict__.update(code.__dict__)
        changed.mutation = mutation
        refuse(changed, frame)
    assert refusals == 15
    expected = 66 if include_temporal_restore else 65
    data = bytearray(b'BO3NFUW2' + struct.pack('<I', expected))
    rows = []
    for edit in edits:
        if not edit.stub:
            continue
        owner = next((frame for frame in frames if frame[0] <= edit.guard.rva < frame[1]), None)
        if owner is None:
            continue
        frame = read_frame(code, owner)
        handler = prepare_native_handler(code, frame) if frame.has_handler else None
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
        source = bytearray(edit.replacement)
        decoded = list(decoder.disasm(source, code.base + edit.guard.rva))
        if sum(instruction.size for instruction in decoded) != len(source):
            raise ValueError('The complete native replacement does not decode.')
        for instruction in decoded:
            if instruction.group(capstone.CS_GRP_JUMP):
                target = 0x10000 if instruction.operands[0].imm == edit.stub_address else instruction.operands[0].imm - code.base - origin
                offset = instruction.address - code.base - edit.guard.rva
                struct.pack_into('<i', source, offset + instruction.imm_offset,
                                 target - (control + offset + instruction.size))
        data += struct.pack('<I',len(source)) + source
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
        if handler:
            rows[-1]['nativeHandlerRecipe'] = {
                'kind': 'gs_only', 'imageBase': hex(handler.image_base), 'runtime': [hex(value) for value in handler.runtime],
                'handlerAddress': hex(handler.handler_address), 'handlerDataAddress': hex(handler.handler_data_address),
                'prologBytes': handler.prolog_bytes, 'cookieOffset': handler.cookie_offset, 'runtimeBindingAllowed': False}
    if len(rows) != expected:
        raise ValueError('The guarded native continuation inventory is incomplete.')
    output.mkdir(parents=True)
    (output / 'native-unwind.bin').write_bytes(data)
    receipt = {'scope': 'Owned Windows native frame comparison only. Handler dispatch and game registration remain gated.',
               'continuations': rows, 'fixtureSha256': hashlib.sha256(data).hexdigest(),
               'includeTemporalRestore': include_temporal_restore,
               'actors': actors,
               'preparedNativeHandlerSites': sum('nativeHandlerRecipe' in row for row in rows),
               'nativeHandlerAdmissionRefusals': refusals,
               'sourceFiles': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in [PATCHES / 'native_unwind.py', PATCHES / 'continuation_unwind.py',
                                            PATCHES / 'temporal_layout.py', PATCHES / 'temporal_restore.py',
                                            PATCHES / 'native_handlers.py', PATCHES / 'native_handlers.json', Path(__file__)]},
               'moduleManifestSha256': hashlib.sha256(module.read_bytes()).hexdigest(), 'gameWrites': 0}
    (output / 'input-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return {'output': str(output), 'continuations': len(rows), 'fixtureSha256': receipt['fixtureSha256']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include-temporal-restore', action='store_true')
    parser.add_argument('--actors', type=int, choices=(300, 500), default=300)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.output, args.include_temporal_restore, args.actors), indent=2))
