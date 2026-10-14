"""Replay exact stock and prepared actor restoration in owned x64 memory."""
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
from temporal_restore import prepare_restore
from x64_table import Emitter


def run(module: Path, executable: Path, dependencies: Path, output: Path) -> dict:
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    import unicorn.x86_const as x64
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new result file inside the private BO3 lab.')
    code = CapturedCode(module, executable)
    layout = TemporalLayout(ActorShape())
    stub_address = code.base + 0x20180000
    edits = prepare_restore(code, layout, stub_address)
    entry, end = 0x1BDEF50, 0x1BDEFF6
    original = code.read(entry, end - entry)
    actors, entities, state, stack, stop = 0x40000000, 0x48000000, 0x49000000, 0x50000000, 0x51000000
    cases = []

    def replay(name: str, mode: str, valid: tuple[int, ...]):
        machine = Uc(UC_ARCH_X86, UC_MODE_64)
        raw = bytearray(original)
        stubs = []
        if mode == 'prepared':
            for edit in edits:
                start = edit.guard.rva - entry
                raw[start:start + edit.guard.size] = edit.replacement
                if edit.stub:
                    stubs.append((edit.stub_address, edit.stub))
        elif mode == 'count-only':
            # Keep both original vector offsets and the original validity offset in this rejected candidate.
            emitter = Emitter(stub_address)
            emitter.put(original[0x14:0x24] + b'\xbd' + struct.pack('<I', 300))
            emitter.rip(b'\xe9', code.base + 0x1BDEF77)
            raw[0x14:0x27] = b'\xe9' + struct.pack('<i', stub_address - (code.base + 0x1BDEF64 + 5)) + b'\x90' * 14
            stubs.append((stub_address, bytes(emitter.code)))
        fragments = [(code.base + entry, bytes(raw)), *stubs]
        regions = [(actors, 0x280000), (entities, 0x100000), (state, 0x4000), (stack, 0x10000), (stop, 0x1000),
                   (code.base + 0xA1B0000, 0x1000), (code.base + 0x2206000, 0x1000)]
        pages = set()
        for address, size in regions + [(address, len(data)) for address, data in fragments]:
            pages.update(range(address & ~4095, (address + size + 4095) & ~4095, 4096))
        for page in sorted(pages):
            machine.mem_map(page, 4096)
        for address, data in fragments:
            machine.mem_write(address, data)
        machine.mem_write(code.base + 0x2206F70, b'\xc3')
        machine.mem_write(code.base + 0xA1B0798, struct.pack('<Q', actors))
        count, vector_bytes = (64, 64 * 12) if mode == 'stock' else (300, layout.vector_bytes)
        image = bytearray(vector_bytes * 2 + count + 16)
        image[-16:] = b'\xcc' * 16
        before, target = [], []
        for index in range(count):
            before.append(tuple(100000 + index * 10 + field for field in range(6)))
            target.append(tuple(200000 + index * 10 + field for field in range(6)))
            machine.mem_write(actors + index * 0x2110 + 8, struct.pack('<Q', entities + index * 0x4F8))
            machine.mem_write(entities + index * 0x4F8 + 0x230, struct.pack('<6I', *before[-1]))
            struct.pack_into('<3I', image, index * 12, *target[-1][:3])
            struct.pack_into('<3I', image, vector_bytes + index * 12, *target[-1][3:])
        for index in valid:
            image[vector_bytes * 2 + index] = 1
        machine.mem_write(state, bytes(image))
        registers = {getattr(x64, 'UC_X86_REG_' + name): 0x100000000 + index
                     for index, name in enumerate(('RBX', 'RBP', 'RSI', 'RDI', 'R12', 'R13', 'R14', 'R15'))}
        for register, value in registers.items():
            machine.reg_write(register, value)
        initial_rsp = stack + 0xF008
        machine.reg_write(x64.UC_X86_REG_RSP, initial_rsp)
        machine.mem_write(initial_rsp, struct.pack('<Q', stop))
        machine.reg_write(x64.UC_X86_REG_RCX, state)
        relinks = []

        def relink(engine, address, size, unused):
            relinks.append((engine.reg_read(x64.UC_X86_REG_RCX) - entities) // 0x4F8)
            rsp = engine.reg_read(x64.UC_X86_REG_RSP)
            destination = struct.unpack('<Q', engine.mem_read(rsp, 8))[0]
            engine.reg_write(x64.UC_X86_REG_RSP, rsp + 8)
            engine.reg_write(x64.UC_X86_REG_RIP, destination)

        machine.hook_add(UC_HOOK_CODE, relink, begin=code.base + 0x2206F70, end=code.base + 0x2206F70)
        try:
            machine.emu_start(code.base + entry, stop, count=100000)
        except Exception:
            print(json.dumps({'case': name, 'rip': hex(machine.reg_read(x64.UC_X86_REG_RIP)),
                              'rsp': hex(machine.reg_read(x64.UC_X86_REG_RSP)), 'relinks': relinks}), file=sys.stderr)
            raise
        assert machine.reg_read(x64.UC_X86_REG_RIP) == stop
        assert machine.reg_read(x64.UC_X86_REG_RSP) == initial_rsp + 8
        assert all(machine.reg_read(register) == value for register, value in registers.items())
        matches = relinks == list(valid)
        for index in range(count):
            actual = struct.unpack('<6I', machine.mem_read(entities + index * 0x4F8 + 0x230, 24))
            matches &= actual == (target[index] if index in valid else before[index])
        expected_image = bytearray(image)
        for index in valid:
            expected_image[vector_bytes * 2 + index] = 0
        matches &= machine.mem_read(state, len(image)) == bytes(expected_image)
        assert matches == (mode != 'count-only'), 'The temporal restoration candidate outcome differs.'
        cases.append({'case': name, 'actors': count, 'valid': list(valid), 'nativeRelinks': len(relinks),
                      'layoutMatches': bool(matches), 'countOnlyCandidateRefused': mode == 'count-only',
                      'stackAndNonvolatileRegistersPreserved': True})

    replay('stock64', 'stock', (0, 31, 63))
    replay('count-only300-rejected', 'count-only', (0, 63, 64, 199, 299))
    replay('wide300-boundaries', 'prepared', (0, 63, 64, 199, 299))
    replay('wide300-all-valid', 'prepared', tuple(range(300)))
    replay('wide300-none-valid', 'prepared', ())
    result = {'scope': 'Owned captured restore replay. Native relink is an authored callback. Producer, caller buffers, history, saves and runtime activation remain unverified.',
              'passed': True, 'cases': cases, 'rewrites': len(edits), 'stubs': sum(bool(edit.stub) for edit in edits),
              'originalFunctionSha256': hashlib.sha256(original).hexdigest(),
              'sourceFiles': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in [PATCHES / 'temporal_restore.py', PATCHES / 'temporal_layout.py', Path(__file__)]},
              'gameWrites': 0, 'activationAllowed': False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    return {'passed': True, 'cases': len(cases), 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--dependencies', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.dependencies, args.output), indent=2))
