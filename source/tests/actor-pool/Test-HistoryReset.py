"""Replay original level reset plus full external history clearing in owned memory."""
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
from temporal_reset import LEVEL_CLEAR, prepare_history_reset


def run(module: Path, executable: Path, dependencies: Path, output: Path) -> dict:
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    import unicorn.x86_const as x64
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab result path.')
    code = CapturedCode(module, executable)
    original = code.guarded(LEVEL_CLEAR)
    start = code.base + LEVEL_CLEAR.rva
    stop = start + len(original)
    level, level_bytes = code.base + 0xA1B0730, 0x23A10
    history, stub = code.base + 0x20200000, code.base + 0x20400000
    memset, stack = code.base + 0x2BC53B0, 0x50000000
    cases = []
    for actors in (300, 500):
        layout = TemporalLayout(ActorShape(actors))
        prepared = prepare_history_reset(code, layout, history, stub)
        assert prepared.metadata == bytes.fromhex('0104010004420000')
        for mode in ('stock', 'expanded', 'stale-extent'):
            machine = Uc(UC_ARCH_X86, UC_MODE_64)
            body = original
            changed = prepared.rewrite.stub
            if mode != 'stock':
                body = body[:15] + prepared.rewrite.replacement
                if mode == 'stale-extent':
                    marker = b'\x41\xB8' + struct.pack('<I', layout.history_bytes)
                    assert changed.count(marker) == 1
                    changed = changed.replace(marker, b'\x41\xB8' + struct.pack('<I', 0x8250))
            regions = [(start, len(body)), (level - 16, level_bytes + 32), (history - 16, layout.history_bytes + 32),
                       (stub, len(changed)), (memset, 1), (stack, 4096)]
            pages = set()
            for address, size in regions:
                pages.update(range(address & ~4095, (address + size + 4095) & ~4095, 4096))
            for page in sorted(pages):
                machine.mem_map(page, 4096)
            machine.mem_write(start, body)
            machine.mem_write(stub, changed)
            machine.mem_write(memset, b'\xC3')
            entry_rsp = stack + 0x800
            machine.reg_write(x64.UC_X86_REG_RSP, entry_rsp)
            preserved = {}
            for index, name in enumerate(('RBX', 'RBP', 'RSI', 'RDI', 'R12', 'R13', 'R14', 'R15')):
                preserved[name] = 0x1234567800000000 | index
                machine.reg_write(getattr(x64, 'UC_X86_REG_' + name), preserved[name])
            calls = []
            def clear(engine, pc, size, unused):
                if pc != memset:
                    return
                destination = engine.reg_read(x64.UC_X86_REG_RCX)
                value = engine.reg_read(x64.UC_X86_REG_EDX)
                length = engine.reg_read(x64.UC_X86_REG_R8D)
                assert engine.reg_read(x64.UC_X86_REG_RSP) % 16 == 8
                assert value == 0
                engine.mem_write(destination, b'\0' * length)
                engine.reg_write(x64.UC_X86_REG_RAX, destination)
                calls.append((destination, length))
            machine.hook_add(UC_HOOK_CODE, clear)
            for repeat in range(2):
                calls.clear()
                machine.mem_write(level - 16, b'\xA5' * 16 + b'\xCC' * level_bytes + b'\x5A' * 16)
                machine.mem_write(history - 16, b'\xA5' * 16 + b'\xCC' * layout.history_bytes + b'\x5A' * 16)
                machine.emu_start(start, stop, count=500)
                assert bytes(machine.mem_read(level, level_bytes)) == b'\0' * level_bytes
                if mode == 'expanded':
                    assert bytes(machine.mem_read(history, layout.history_bytes)) == b'\0' * layout.history_bytes
                    assert calls == [(level, level_bytes), (history, layout.history_bytes)]
                elif mode == 'stock':
                    assert bytes(machine.mem_read(history, layout.history_bytes)) == b'\xCC' * layout.history_bytes
                    assert calls == [(level, level_bytes)]
                else:
                    assert bytes(machine.mem_read(history, layout.history_bytes)) != b'\0' * layout.history_bytes
                    assert bytes(machine.mem_read(history + 0x8250, layout.history_bytes - 0x8250)) == b'\xCC' * (layout.history_bytes - 0x8250)
                for address, size in ((level, level_bytes), (history, layout.history_bytes)):
                    assert bytes(machine.mem_read(address - 16, 16)) == b'\xA5' * 16
                    assert bytes(machine.mem_read(address + size, 16)) == b'\x5A' * 16
                assert machine.reg_read(x64.UC_X86_REG_RAX) == level
                assert machine.reg_read(x64.UC_X86_REG_RSP) == entry_rsp
                for name, value in preserved.items():
                    assert machine.reg_read(getattr(x64, 'UC_X86_REG_' + name)) == value
            cases.append({'actors': actors, 'mode': mode, 'repeatedResets': 2, 'staleExtentRefused': mode == 'stale-extent'})
    refusals = 0
    layout = TemporalLayout(ActorShape(500))
    for pool, address in ((0, stub), (history + 1, stub), (code.base, stub), (2**64 - 16, stub),
                          (history, history), (history, 0), (history, stub + 1), (history, code.base),
                          (history, code.base + 0x90000000)):
        try:
            prepare_history_reset(code, layout, pool, address)
        except ValueError:
            refusals += 1
        else:
            raise AssertionError('An invalid reset storage/stub interval escaped admission.')
    class ChangedCode(CapturedCode):
        def read(self, rva: int, size: int) -> bytes:
            raw = super().read(rva, size)
            return bytes((raw[0] ^ 1,)) + raw[1:] if rva == LEVEL_CLEAR.rva else raw
    try:
        prepare_history_reset(ChangedCode(module, executable), layout, history, stub)
    except ValueError:
        refusals += 1
    else:
        raise AssertionError('An altered native clear escaped admission.')
    result = {'passed': True, 'cases': cases, 'admissionRefusals': refusals,
              'scope': 'Owned native level-clear call path and expanded reset stub. Memset endpoint is authored.',
              'gameWrites': 0, 'activationAllowed': False, 'functionTableRegistrationVerified': False,
              'unverified': ['Computed reset consumers', 'Live storage ownership', 'Actual Windows stub unwind', 'Game map transitions'],
              'sourceFiles': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in
                              [PATCHES / 'temporal_reset.py', PATCHES / 'temporal_layout.py', Path(__file__)]}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    return {'passed': True, 'cases': len(cases), 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'dependencies', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.dependencies, args.output), indent=2))
