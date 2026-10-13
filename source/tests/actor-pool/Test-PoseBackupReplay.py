"""Replay the complete native pose constructor and destructor with the published recipe operands."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode
from crash_frame import HELPERS
from runtime_recipe import prepare_recipe


def run(module, executable, dependencies, output):
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    import unicorn.x86_const as x64
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new result file inside the private BO3 lab.')
    code = CapturedCode(module, executable)
    recipe = prepare_recipe(code, code.base + 0x20000000)
    helper_edits = [edit for edit in recipe.edits if any(guard.rva <= edit.guard.rva < guard.rva + guard.size for guard in HELPERS)]
    stack, actors, entities, stop = 0x20000000, 0x30000000, 0x40000000, 0x50000000
    object_address, rsp = stack + 0x12000, stack + 0x10008
    cases = []
    for mode, count, active in (('stock', 64, tuple(range(64))), ('count-only', 500, (0,63,64,65,129,299,499)),
                               ('prepared-boundaries', 500, (0,63,64,65,99,129,283,284,299,300,499)),
                               ('prepared-100', 500, tuple(range(100))),
                               ('prepared-284', 500, tuple(range(284))),
                               ('prepared-300', 500, tuple(range(300))),
                               ('prepared-all', 500, tuple(range(500)))):
        machine = Uc(UC_ARCH_X86, UC_MODE_64)
        for address, size in ((stack, 0x20000), (actors, 0x500000), (entities, 0x100000), (stop, 4096),
                              (code.base + 0x27C1000, 4096), (code.base + 0xA1B0000, 4096), (code.base + 0x2206000, 4096)):
            machine.mem_map(address, size)
        for guard in HELPERS:
            machine.mem_write(code.base + guard.rva, code.guarded(guard))
        applied = []
        if mode != 'stock':
            for edit in helper_edits:
                if mode == 'count-only' and edit.name == 'pose_backup_helper_member': continue
                machine.mem_write(code.base + edit.guard.rva, edit.replacement)
                applied.append(edit.guard.rva)
        machine.mem_write(code.base + 0xA1B0798, struct.pack('<Q', actors))
        machine.mem_write(code.base + 0x2206F70, b'\xc3')
        paired = mode.startswith('prepared')
        vector_bytes = count * 12 if paired else 0x300
        object_bytes = vector_bytes * 2 + 1
        machine.mem_write(stack, b'\xA7' * 0x20000)
        machine.mem_write(object_address + object_bytes, b'\x7B' * 15)
        expected = {}
        for index in active:
            entity = entities + index * 0x4F8
            values = struct.pack('<6f', index + 0.25, index + 0.5, index + 0.75, -index - 0.25, -index - 0.5, -index - 0.75)
            expected[index] = values
            machine.mem_write(actors + index * 0x2110, b'\x01')
            machine.mem_write(actors + index * 0x2110 + 8, struct.pack('<Q', entity))
            machine.mem_write(entity + 0x1AA, struct.pack('<H', 1022))
            machine.mem_write(entity + 0x230, values)
        relinks = []
        def observe(current, address, size, state):
            if address == code.base + 0x2206F70:
                relinks.append(current.reg_read(x64.UC_X86_REG_RCX))
        machine.hook_add(UC_HOOK_CODE, observe)
        def call(rva, arguments):
            machine.mem_write(rsp, struct.pack('<Q', stop))
            machine.reg_write(x64.UC_X86_REG_RSP, rsp)
            for register, value in zip((x64.UC_X86_REG_RCX, x64.UC_X86_REG_RDX, x64.UC_X86_REG_R8, x64.UC_X86_REG_R9), arguments):
                machine.reg_write(register, value)
            machine.emu_start(code.base + rva, stop, count=1000000)
            if machine.reg_read(x64.UC_X86_REG_RIP) != stop: raise ValueError('A native pose helper did not return.')
        call(0x27C1940, (object_address, 0, 0, 1023))
        positions = all(bytes(machine.mem_read(object_address + index * 12, 12)) == expected[index][:12] for index in active)
        angles = all(bytes(machine.mem_read(object_address + vector_bytes + index * 12, 12)) == expected[index][12:] for index in active)
        canary = bytes(machine.mem_read(object_address + object_bytes, 15)) == b'\x7B' * 15
        flag_set = bytes(machine.mem_read(object_address + vector_bytes * 2, 1)) == b'\x01'
        for index in active: machine.mem_write(entities + index * 0x4F8 + 0x230, b'\x00' * 24)
        call(0x27C1880, (object_address,))
        restored = all(bytes(machine.mem_read(entities + index * 0x4F8 + 0x230, 24)) == expected[index] for index in active)
        flag_clear = bytes(machine.mem_read(object_address + vector_bytes * 2, 1)) == b'\x00'
        passed = positions and angles and restored and canary and flag_set and flag_clear and len(relinks) == len(active)
        if passed == (mode == 'count-only'): raise ValueError('The native pose replay differs from its expected outcome.')
        cases.append({'mode': mode, 'activeActors': len(active), 'lastActor': active[-1], 'objectBytes': object_bytes,
                      'positionsExact': positions, 'anglesExact': angles, 'restoreExact': restored, 'canaryExact': canary,
                      'oneObjectFlagSet': flag_set, 'oneObjectFlagCleared': flag_clear, 'nativeRelinks': len(relinks),
                      'expectedOutcome': passed if mode != 'count-only' else 'refused', 'appliedSourceRvas': [hex(rva) for rva in applied]})
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {'passed': True, 'scope': 'Complete captured pose constructor and destructor with the prepared recipe operands. Synthetic actor and entity tables and authored relink return. No game body or game compatibility claim.',
              'cases': cases, 'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'frameSourceSha256': hashlib.sha256((PATCHES / 'crash_frame.py').read_bytes()).hexdigest(),
              'executableSha256': code.executable_sha256, 'gameWrites': 0, 'activationAllowed': False}
    output.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'): parser.add_argument('--' + name, type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.module, arguments.executable, arguments.dependencies, arguments.output), indent=2))
