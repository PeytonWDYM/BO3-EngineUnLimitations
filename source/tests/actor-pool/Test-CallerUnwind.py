"""Export caller instruction contexts for actual Windows virtual unwinding in owned storage."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode
from temporal_layout import TemporalLayout
from temporal_caller import CALLER_FUNCTION, prepare_caller
from temporal_rewind import PROBE_FUNCTION
from caller_unwind import CALLER_UNWIND, prepare_caller_unwind


def run(module: Path, executable: Path, dependencies: Path, output: Path) -> dict:
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    import unicorn.x86_const as x64
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new directory inside the private BO3 lab.')
    code = CapturedCode(module, executable)
    native = code.guarded(CALLER_FUNCTION)
    old_metadata = code.guarded(CALLER_UNWIND)
    prepared_metadata = prepare_caller_unwind(code, TemporalLayout()).replacement
    probe = code.guarded(PROBE_FUNCTION)
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    instructions = list(decoder.disasm(native, code.base + CALLER_FUNCTION.rva))
    assert sum(item.size for item in instructions) == len(native)
    stack, tib, stop = 0x50000000, 0x52000000, 0x51000000
    entry_rsp = stack + 0x1F008
    return_pc = 0x1234567812345678
    names = ('RAX', 'RCX', 'RDX', 'RBX', 'RSP', 'RBP', 'RSI', 'RDI', 'R8', 'R9', 'R10', 'R11', 'R12', 'R13', 'R14', 'R15')
    registers = [getattr(x64, 'UC_X86_REG_' + name) for name in names]
    vectors = [getattr(x64, 'UC_X86_REG_XMM' + str(index)) for index in range(16)]
    expected_gprs = [0x100000000 + index for index in range(16)]
    expected_vectors = [(index << 120) | 0x112233445566778899 for index in range(16)]
    data = bytearray(b'BO3CFUW1' + struct.pack('<I', 2))
    rows = []
    for expanded in (False, True):
        body = bytearray(native)
        if expanded:
            for edit in prepare_caller(code, TemporalLayout()):
                offset = edit.guard.rva - CALLER_FUNCTION.rva
                body[offset:offset + edit.guard.size] = edit.replacement
        metadata = prepared_metadata if expanded else old_metadata
        machine = Uc(UC_ARCH_X86, UC_MODE_64)
        regions = [(code.base + CALLER_FUNCTION.rva, len(body)), (code.base + PROBE_FUNCTION.rva, len(probe)),
                   (code.base + 0x35EEA10, 8), (stack, 0x20000), (tib, 4096), (stop, 4096)]
        pages = set()
        for address, size in regions:
            pages.update(range(address & ~4095, (address + size + 4095) & ~4095, 4096))
        for page in sorted(pages):
            machine.mem_map(page, 4096)
        machine.mem_write(code.base + CALLER_FUNCTION.rva, bytes(body))
        machine.mem_write(code.base + PROBE_FUNCTION.rva, probe)
        machine.mem_write(stack, b'\xcc' * 0x20000)
        machine.mem_write(entry_rsp, struct.pack('<Q', return_pc))
        machine.mem_write(tib + 0x10, struct.pack('<Q', (entry_rsp - 56) & ~4095))
        machine.mem_write(code.base + 0x35EEA10, struct.pack('<Q', 0xABCDEF0123456789))
        for register, value in zip(registers, expected_gprs):
            machine.reg_write(register, value)
        for register, value in zip(vectors, expected_vectors):
            machine.reg_write(register, value)
        machine.reg_write(x64.UC_X86_REG_RSP, entry_rsp)
        machine.reg_write(x64.UC_X86_REG_GS_BASE, tib)
        contexts = {}

        def snapshot(engine, address, size, unused):
            if code.base + CALLER_FUNCTION.rva <= address < code.base + CALLER_FUNCTION.rva + len(body):
                contexts[address] = ([engine.reg_read(register) for register in registers],
                                     [engine.reg_read(register) for register in vectors])
        machine.hook_add(UC_HOOK_CODE, snapshot)
        machine.emu_start(code.base + CALLER_FUNCTION.rva, code.base + CALLER_FUNCTION.rva + 0x9B, count=1000)
        body_state = ([machine.reg_read(register) for register in registers], [machine.reg_read(register) for register in vectors])
        machine.emu_start(code.base + CALLER_FUNCTION.rva + 0x5EC, return_pc, count=1000)
        assert machine.reg_read(x64.UC_X86_REG_RSP) == entry_rsp + 8
        stack_bytes = bytes(machine.mem_read(stack, 0x20000))
        # Body contexts use the executed prolog's complete frame. No game instruction in the body executes.
        for instruction in instructions:
            contexts.setdefault(instruction.address, body_state)
        data += struct.pack('<5I', len(body), len(metadata), len(old_metadata), len(contexts), int(expanded))
        data += body + metadata + old_metadata + stack_bytes
        for instruction in instructions:
            gprs, xmm = contexts[instruction.address]
            data += struct.pack('<I16Q', instruction.address - code.base - CALLER_FUNCTION.rva, *gprs)
            data += b''.join(value.to_bytes(16, 'little') for value in xmm)
        rows.append({'expanded': expanded, 'contexts': len(contexts), 'executedPrologAndEpilogContexts': len(contexts) - sum(
            CALLER_FUNCTION.rva + 0x9B <= instruction.address - code.base < CALLER_FUNCTION.rva + 0x5EC for instruction in instructions),
                     'handlerOmittedForOwnedComparison': True, 'gameBodyExecuted': False})
    output.mkdir(parents=True)
    (output / 'caller-unwind.bin').write_bytes(data)
    receipt = {'passedExport': True, 'cases': rows, 'fixtureSha256': hashlib.sha256(data).hexdigest(),
               'scope': 'Executed prolog and epilog with owned memory. Body contexts reuse the complete prolog frame. Windows fixture omits handlers.',
               'sourceFiles': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in
                               [PATCHES / 'caller_unwind.py', PATCHES / 'temporal_caller.py', Path(__file__)]},
               'gameWrites': 0, 'activationAllowed': False}
    (output / 'input-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return {'output': str(output), 'contexts': sum(row['contexts'] for row in rows)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'dependencies', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.dependencies, args.output), indent=2))
