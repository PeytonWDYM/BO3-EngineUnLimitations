"""Replay the complete no-fire caller with native pose functions in owned memory."""
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
from temporal_producer import PRODUCER_FUNCTION, prepare_producer
from temporal_restore import RESTORE_FUNCTION, prepare_restore
from temporal_history import RECORDER_FUNCTION, SELECTOR_FUNCTION, prepare_history
from temporal_rewind import REWIND_FUNCTION, PROBE_FUNCTION, prepare_rewind
from temporal_caller import CALLER_FUNCTION, caller_frame, prepare_caller
from shape import ActorShape


def run(module: Path, executable: Path, dependencies: Path, output: Path, actor_count: int = 300) -> dict:
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
    import unicorn.x86_const as x64
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86_const import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new result file inside the private BO3 lab.')
    code = CapturedCode(module, executable)
    layout = TemporalLayout(ActorShape(actor_count))
    frame = caller_frame(layout)
    edits = prepare_caller(code, layout)
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    guards = (CALLER_FUNCTION, REWIND_FUNCTION, PRODUCER_FUNCTION, RESTORE_FUNCTION, PROBE_FUNCTION, SELECTOR_FUNCTION, RECORDER_FUNCTION)
    originals = [(guard, code.guarded(guard)) for guard in guards]
    native_entries = {guard.rva for guard in guards}
    rip_regions, endpoints = [], set()
    for guard, raw in originals:
        for instruction in decoder.disasm(raw, code.base + guard.rva):
            for operand in instruction.operands:
                if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
                    rip_regions.append((instruction.address + instruction.size + operand.mem.disp, max(operand.size, 8)))
            if instruction.mnemonic == 'call' and instruction.operands[0].type == X86_OP_IMM:
                target = instruction.operands[0].imm - code.base
                if target not in native_entries:
                    endpoints.add(target)
    # The corpse restore is unchanged. Its buffer ownership is observed with an authored endpoint.
    endpoints.add(0x1BF7E70)
    actors, entities, player, weapon, stats, definition = 0x40000000, 0x48000000, 0x4B000000, 0x4B100000, 0x4B200000, 0x4B300000
    history, stack, tib, stop = code.base + 0x20200000, 0x50000000, 0x52000000, 0x51000000
    cookie = 0x123456789ABCDEF0
    cases = []

    def replay(name: str, mode: str):
        count = 64 if mode == 'stock' else actor_count
        width, state_offset = count * 12, count * 24
        valid_offset, time_offset = count * 25, count * 26
        row_bytes = time_offset + 4
        machine = Uc(UC_ARCH_X86, UC_MODE_64)
        blobs = [(code.base + guard.rva, raw) for guard, raw in originals]
        history_base = code.base + 0xA1C3484 if mode == 'stock' else history
        if mode != 'stock':
            temporal = (*prepare_history(code, layout, history, code.base + 0x201A0000, code.base + 0x201B0000),
                        prepare_producer(code, layout, code.base + 0x201C0000),
                        prepare_rewind(code, layout, code.base + 0x201E0000),
                        *prepare_restore(code, layout, code.base + 0x201D0000))
            for edit in (*temporal, *edits):
                replacement = edit.replacement
                if mode == 'old-corpse-buffer' and edit.guard.rva in (0x1580131, 0x1580583):
                    replacement = code.read(edit.guard.rva, edit.guard.size)
                blobs.append((code.base + edit.guard.rva, replacement))
                if edit.stub:
                    blobs.append((edit.stub_address, edit.stub))
        regions = [(actors, count * 0x2110), (entities, count * 0x4F8), (player, 0x4000), (weapon, 0x4000), (stats, 0x4000),
                   (definition, 0x4000), (history_base, row_bytes * 20), (stack, 0x20000), (tib, 4096), (stop, 4096),
                   (code.base + 0xA1CB6D4, 4), *rip_regions, *[(code.base + target, 1) for target in endpoints]]
        pages = set()
        for address, size in regions + [(address, len(raw)) for address, raw in blobs]:
            pages.update(range(address & ~4095, (address + size + 4095) & ~4095, 4096))
        for page in sorted(pages):
            machine.mem_map(page, 4096)
        for address, raw in blobs:
            machine.mem_write(address, raw)
        for target in endpoints:
            machine.mem_write(code.base + target, b'\xc3')
        machine.mem_write(code.base + 0x35EEA10, struct.pack('<Q', cookie))
        machine.mem_write(code.base + 0xA1B0798, struct.pack('<Q', actors))
        machine.mem_write(code.base + 0xA1B0744, struct.pack('<I', 0x55AA))
        machine.mem_write(code.base + 0xA1B6C14, struct.pack('<I', 10100))
        machine.mem_write(code.base + 0xA1CB6D4, struct.pack('<I', 3))
        machine.mem_write(weapon + 0x50, struct.pack('<Q', stats))
        machine.mem_write(weapon + 0x40, struct.pack('<Q', definition))
        machine.mem_write(stats + 0x70, struct.pack('<I', 3))
        # A zero shot count isolates the temporal caller and its complete save/restore epilog.
        machine.mem_write(stats + 0x900, struct.pack('<I', 0))
        current = []
        for index in range(count):
            values = tuple(float(90000 + index * 8 + field) for field in range(6))
            current.append(values)
            machine.mem_write(actors + index * 0x2110, b'\x01')
            machine.mem_write(actors + index * 0x2110 + 8, struct.pack('<Q', entities + index * 0x4F8))
            machine.mem_write(actors + index * 0x2110 + 0x798, struct.pack('<H', index))
            machine.mem_write(entities + index * 0x4F8 + 0x230, struct.pack('<6f', *values))
            machine.mem_write(entities + index * 0x4F8 + 0xC0, struct.pack('<H', index % 251))
            for row in range(3):
                raw = history_base + row * row_bytes
                past = tuple(float(row * 4096 + index * 8 + field) for field in range(6))
                machine.mem_write(raw + index * 12, struct.pack('<3f', *past[:3]))
                machine.mem_write(raw + width + index * 12, struct.pack('<3f', *past[3:]))
                machine.mem_write(raw + state_offset + index, bytes([index % 251]))
                machine.mem_write(raw + valid_offset + index, b'\x01')
                machine.mem_write(raw + time_offset, struct.pack('<I', 10000 + row * 50))
        initial_rsp = stack + 0x1F008
        allocation = 0x3DD0 if mode == 'stock' else frame.allocation
        body_rsp = initial_rsp - 56 - allocation
        rbp = body_rsp + 0x100
        actor_output = rbp + 0x2F90
        corpse_output = rbp + (0x35D0 if mode in ('stock', 'old-corpse-buffer') else frame.corpse)
        cookies, relinks, corpses, probes = [], [], [], []

        def endpoint(engine, address, size, unused):
            target = address - code.base
            if target == 0x2BC3AA0:
                cookies.append(engine.reg_read(x64.UC_X86_REG_RCX))
                assert cookies[-1] == cookie
            elif target == 0x2BC53B0:
                destination, amount = engine.reg_read(x64.UC_X86_REG_RCX), engine.reg_read(x64.UC_X86_REG_R8)
                assert destination == actor_output and amount == count * 25
                engine.mem_write(destination, bytes(amount))
                engine.reg_write(x64.UC_X86_REG_RAX, destination)
            elif target == 0x1BF9BD0:
                destination = engine.reg_read(x64.UC_X86_REG_RDX)
                assert destination == corpse_output
                engine.mem_write(destination, b'\xb5' * 1600)
                corpses.append('rewind64')
            elif target == 0x1BF7E70:
                assert engine.reg_read(x64.UC_X86_REG_RCX) == corpse_output
                assert engine.mem_read(corpse_output, 1600) == b'\xb5' * 1600
                corpses.append('restore64')
            elif target == 0x2206F70:
                entity = engine.reg_read(x64.UC_X86_REG_RCX)
                assert (entity - entities) % 0x4F8 == 0
                relinks.append((entity - entities) // 0x4F8)
            else:
                engine.reg_write(x64.UC_X86_REG_RAX, int(target == 0x2260A70))
                engine.reg_write(x64.UC_X86_REG_XMM0, 0)
            rsp = engine.reg_read(x64.UC_X86_REG_RSP)
            engine.reg_write(x64.UC_X86_REG_RIP, struct.unpack('<Q', engine.mem_read(rsp, 8))[0])
            engine.reg_write(x64.UC_X86_REG_RSP, rsp + 8)

        for target in endpoints:
            machine.hook_add(UC_HOOK_CODE, endpoint, begin=code.base + target, end=code.base + target)

        def page_touch(engine, access, address, size, value, unused):
            if engine.reg_read(x64.UC_X86_REG_RIP) == code.base + 0x2BC57D7:
                probes.append(address)
                engine.mem_write(tib + 0x10, struct.pack('<Q', address))
        machine.hook_add(UC_HOOK_MEM_WRITE, page_touch)
        saved = {getattr(x64, 'UC_X86_REG_' + name): 0x100000000 + index
                 for index, name in enumerate(('RBX', 'RBP', 'RSI', 'RDI', 'R12', 'R13', 'R14', 'R15'))}
        saved.update({getattr(x64, 'UC_X86_REG_XMM' + str(index)): (index << 120) | 0x112233445566778899 for index in range(6, 16)})
        for register, value in saved.items():
            machine.reg_write(register, value)
        machine.mem_write(initial_rsp, struct.pack('<Q', stop))
        machine.mem_write(initial_rsp + 0x28, struct.pack('<I', 10025))
        machine.mem_write(tib + 0x10, struct.pack('<Q', (initial_rsp - 56) & ~4095))
        machine.reg_write(x64.UC_X86_REG_GS_BASE, tib)
        machine.reg_write(x64.UC_X86_REG_RSP, initial_rsp)
        machine.reg_write(x64.UC_X86_REG_RCX, player)
        machine.reg_write(x64.UC_X86_REG_R8, weapon)
        machine.reg_write(x64.UC_X86_REG_R9, 0)
        machine.reg_write(x64.UC_X86_REG_XMM1, 0)
        machine.emu_start(code.base + CALLER_FUNCTION.rva, stop, count=300000)
        assert machine.reg_read(x64.UC_X86_REG_RIP) == stop
        assert machine.reg_read(x64.UC_X86_REG_RSP) == initial_rsp + 8
        assert all(machine.reg_read(register) == value for register, value in saved.items())
        assert cookies == [cookie] * 3 and corpses == ['rewind64', 'restore64'], (name, cookies, corpses, relinks)
        assert relinks == list(range(count)) * 2
        assert struct.unpack('<I', machine.mem_read(initial_rsp + 0x28, 4))[0] == 10025
        matches = all(machine.mem_read(entities + index * 0x4F8 + 0x230, 24) == struct.pack('<6f', *values)
                      for index, values in enumerate(current))
        assert matches == (mode != 'old-corpse-buffer')
        cases.append({'case': name, 'actors': count, 'corpseCapacity': 64, 'frameBytes': allocation,
                      'posesRestored': matches, 'oldCorpseAddressRefused': mode == 'old-corpse-buffer',
                      'stackCookieAndSavedRegistersMatch': True, 'nativeRelinks': len(relinks),
                      'probePages': [hex(page) for page in probes]})

    replay('stock64-complete-no-fire-caller', 'stock')
    replay(f'wide{actor_count}-complete-no-fire-caller', 'prepared')
    replay(f'wide{actor_count}-old-corpse-address-refused', 'old-corpse-buffer')
    result = {'passed': True, 'cases': cases,
              'scope': 'Owned complete no-fire caller with native selection, production, rewind, restore and probing. Corpse and other external helper endpoints are authored.',
              'sourceFiles': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in
                              [PATCHES / 'temporal_caller.py', PATCHES / 'temporal_rewind.py', PATCHES / 'temporal_producer.py',
                               PATCHES / 'temporal_history.py', PATCHES / 'temporal_restore.py', Path(__file__)]},
              'gameWrites': 0, 'activationAllowed': False,
              'unverified': ['Firing paths', 'Language function-info and cleanup funclets', 'Native Windows unwind and handler dispatch', 'Saves', 'Game and peer behavior']}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    return {'passed': True, 'cases': len(cases), 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'dependencies', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--actors', type=int, choices=(300,500), default=300)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.dependencies, args.output, args.actors), indent=2))
