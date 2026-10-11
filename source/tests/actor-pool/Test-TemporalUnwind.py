"""Export complete producer/rewind frames and executed stack contexts for Windows comparison."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode
from shape import ActorShape
from temporal_layout import TemporalLayout
from temporal_producer import PRODUCER_FUNCTION, prepare_producer
from temporal_rewind import REWIND_FUNCTION, PROBE_FUNCTION, prepare_rewind
from temporal_unwind import prepare_temporal_unwind


def run(module: Path, executable: Path, dependencies: Path, output: Path, actors: int) -> dict:
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    import unicorn.x86_const as x64
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab directory.')
    code = CapturedCode(module, executable)
    layout = TemporalLayout(ActorShape(actors))
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    stack, tib, stop = 0x50000000, 0x52000000, 0x51000000
    entry_rsp, return_pc = stack + 0x1F008, 0x1234567812345678
    registers = [getattr(x64, 'UC_X86_REG_' + name) for name in
                 ('RAX','RCX','RDX','RBX','RSP','RBP','RSI','RDI','R8','R9','R10','R11','R12','R13','R14','R15')]
    vectors = [getattr(x64, 'UC_X86_REG_XMM' + str(index)) for index in range(16)]
    data = bytearray(b'BO3TFUW1' + struct.pack('<I', 4))
    rows = []
    for guard, prepare, late_begin, late_end, epilog in (
        (PRODUCER_FUNCTION, prepare_producer, 0x1BFDF11, 0x1BFDF21, 0x1BFE27A),
        (REWIND_FUNCTION, prepare_rewind, 0x1BF9A00, 0x1BF9A30, 0x1BF9BAF),
    ):
        prepared = prepare(code, layout, code.base + 0x201F0000)
        for expanded in (False, True):
            start = prepared.stub_address if expanded else code.base + guard.rva
            body = prepared.stub if expanded else code.guarded(guard)
            mapping = dict(prepared.instruction_map) if expanded else {
                instruction.address:instruction.address for instruction in decoder.disasm(body, start)}
            mapping[code.base + guard.rva + guard.size] = start + len(body)
            frames = prepare_temporal_unwind(code, layout, prepared, expanded=expanded)
            machine = Uc(UC_ARCH_X86, UC_MODE_64)
            pages = set()
            regions = [(start, len(body)), (code.base + PROBE_FUNCTION.rva, PROBE_FUNCTION.size),
                       (code.base + 0x35EEA10, 8), (code.base + 0x2BC3AA0, 1), (stack, 0x20000), (tib, 4096), (stop, 4096)]
            for address, size in regions:
                pages.update(range(address & ~4095, (address + size + 4095) & ~4095, 4096))
            for page in sorted(pages):
                machine.mem_map(page, 4096)
            machine.mem_write(start, body)
            machine.mem_write(code.base + PROBE_FUNCTION.rva, code.guarded(PROBE_FUNCTION))
            machine.mem_write(code.base + 0x2BC3AA0, b'\xc3')
            machine.mem_write(stack, b'\xcc' * 0x20000)
            machine.mem_write(entry_rsp, struct.pack('<Q', return_pc))
            machine.mem_write(tib + 0x10, struct.pack('<Q', (entry_rsp - 56) & ~4095))
            machine.mem_write(code.base + 0x35EEA10, struct.pack('<Q', 0xABCDEF0123456789))
            for index, register in enumerate(registers):
                machine.reg_write(register, 0x100000000 + index)
            for index, register in enumerate(vectors):
                machine.reg_write(register, (index << 120) | 0x112233445566778899)
            machine.reg_write(x64.UC_X86_REG_RSP, entry_rsp)
            machine.reg_write(x64.UC_X86_REG_GS_BASE, tib)
            contexts = {}

            def state():
                return ([machine.reg_read(register) for register in registers],
                        [machine.reg_read(register) for register in vectors])

            def snapshot(engine, address, size, unused):
                if start <= address < start + len(body):
                    contexts[address] = state()
            machine.hook_add(UC_HOOK_CODE, snapshot)
            machine.emu_start(start, mapping[code.base + guard.rva + frames[0].source_prolog], count=1000)
            early_state = state()
            machine.emu_start(mapping[code.base + late_begin], mapping[code.base + late_end], count=1000)
            complete_state = state()
            machine.emu_start(mapping[code.base + epilog], return_pc, count=1000)
            assert machine.reg_read(x64.UC_X86_REG_RSP) == entry_rsp + 8
            assert machine.reg_read(x64.UC_X86_REG_RIP) == return_pc
            instructions = list(decoder.disasm(body, start))
            before_late = mapping[code.base + late_begin]
            for instruction in instructions:
                contexts.setdefault(instruction.address, early_state if instruction.address < before_late else complete_state)
            image = bytearray(body + b'\0' * (-len(body) % 4))
            offsets = {}
            for frame in frames:
                offsets[frame.source_runtime[2]] = len(image)
                image += frame.metadata
            functions = []
            for frame in frames:
                offset = offsets[frame.source_runtime[2]]
                metadata = frame.metadata
                if metadata[0] >> 3 == 4:
                    parent = frame.parent_runtime
                    tail = offset + len(metadata) - 12
                    struct.pack_into('<III', image, tail, parent[0] - start, parent[1] - start, offsets[parent[2]])
                else:
                    image[offset] = 1  # Native handler execution needs its own separate fixture.
                functions.append((frame.runtime[0] - start, frame.runtime[1] - start, offset))
            data += struct.pack('<4I', len(image), len(functions), len(contexts), int(expanded))
            data += image + b''.join(struct.pack('<III', *runtime) for runtime in functions)
            data += bytes(machine.mem_read(stack, 0x20000))
            for instruction in instructions:
                gprs, xmm = contexts[instruction.address]
                data += struct.pack('<I16Q', instruction.address - start, *gprs)
                data += b''.join(value.to_bytes(16, 'little') for value in xmm)
            rows.append({'function':hex(guard.rva),'expanded':expanded,'contexts':len(contexts),'frames':len(frames)})
    output.mkdir(parents=True)
    (output / 'temporal-unwind.bin').write_bytes(data)
    receipt = {'passedExport':True,'actors':actors,'cases':rows,'fixtureSha256':hashlib.sha256(data).hexdigest(),
               'scope':'Executed prologs, late saves, and epilogs. Body contexts reuse their active frame. Cookie-check endpoint is an authored RET. No game or handler execution.',
               'sourceFiles':{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in
                              [PATCHES/'temporal_unwind.py',PATCHES/'temporal_producer.py',PATCHES/'temporal_rewind.py',Path(__file__)]}}
    (output / 'input-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return {'output':str(output),'contexts':sum(row['contexts'] for row in rows)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=500)
    args = parser.parse_args()
    print(json.dumps(run(args.module,args.executable,args.dependencies,args.output,args.actors),indent=2))
