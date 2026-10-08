"""Replay selected captured table consumers and the shared handle-node capacity.

Owned memory separates table entries from their sentient records. No game starts.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


def run(module: Path, dependencies: Path, output: Path):
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    from unicorn.x86_const import UC_X86_REG_RAX, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_RSP

    output = output.resolve()
    lab = (Path.home() / '.codex/labs/bo3-engine').resolve()
    if lab not in output.parents or output.exists():
        raise ValueError('Use a new result file inside the private BO3 lab.')
    meta = json.loads(module.read_text())
    base = int(meta['baseAddress'], 0)
    specifications = [
        (0x2507830, 0x250785e, '728526da1af3017d0b9ae00dacd2bf64a2f7b1e6ca50b28d24b6192c4fad38d3'),
        (0x2506aa0, 0x2506ac1, '97eee6d4c700e161716ea95b09903c27a6c175716c2e841e2ab83342fdc12185'),
        (0x1593580, 0x1593639, '986e9fce57b7f4ae5dfbbd4ea05926d269d53ad07364e7e7281bab59e9c52e96'),
        (0x1595110, 0x159515b, '6d726f0be59f7240c37845c38a52ecc5bf3022f1c22108a622b641a30a7e2f3c'),
    ]
    machine = Uc(UC_ARCH_X86, UC_MODE_64)
    for start, end, digest in specifications:
        item = next(x for x in meta['ranges'] if int(x['moduleOffset'], 0) <= start
                    and end <= int(x['moduleOffset'], 0) + x['size'])
        raw = (module.parent / item['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('A captured module range differs from its manifest.')
        offset = start - int(item['moduleOffset'], 0)
        code = raw[offset:offset + end-start]
        if hashlib.sha256(code).hexdigest() != digest:
            raise ValueError('A consumer differs from the verified capture.')
        machine.mem_map((base+start) & ~4095, 4096)
        machine.mem_write(base+start, code)
    machine.mem_map(0x300000, 0x4000)
    machine.mem_map(0x400000, 4096)
    machine.mem_map(0x500000, 0x4000)
    machine.mem_map(0x600000, 0x10000)
    clock = base+0xa1b6c14
    machine.mem_map(clock & ~4095, 4096)
    machine.mem_write(clock, struct.pack('<I', 12345))

    results = []
    owner, table, position = 0x500000, 0x600040, 0x603000
    owner_bytes = bytes([0xA5])*0x3088
    machine.mem_write(owner, owner_bytes)
    machine.mem_write(position, struct.pack('<III', 11, 22, 33))
    for enabled in (0, 1):
        initial = bytes([0x5A])*0x100
        machine.mem_write(0x600000, initial)
        machine.mem_write(0x302000, struct.pack('<Q', 0x400000))
        machine.reg_write(UC_X86_REG_RSP, 0x302000)
        machine.reg_write(UC_X86_REG_RCX, table)
        machine.reg_write(UC_X86_REG_RDX, enabled)
        machine.reg_write(UC_X86_REG_R8, position)
        machine.emu_start(base+0x2507830, 0x400000, count=30)
        expected = bytearray(initial)
        expected[0x40] = enabled
        struct.pack_into('<I', expected, 0x44, 12345)
        if enabled:
            struct.pack_into('<IIII', expected, 0x48, 12345, 11, 22, 33)
        assert bytes(machine.mem_read(0x600000, len(initial))) == bytes(expected)
        assert bytes(machine.mem_read(owner, len(owner_bytes))) == owner_bytes
        results.append({'case': 'external_entry_state', 'enabled': bool(enabled), 'ownerUnchanged': True})

    entity = 0x603100
    machine.mem_write(owner, struct.pack('<Q', entity))
    machine.mem_write(entity+0x230, struct.pack('<III', 101, 202, 303))
    machine.mem_write(0x600000, bytes([0x5A])*0x100)
    machine.mem_write(0x302000, struct.pack('<Q', 0x400000))
    machine.reg_write(UC_X86_REG_RSP, 0x302000)
    machine.reg_write(UC_X86_REG_RCX, owner)
    machine.reg_write(UC_X86_REG_RDX, table+0x28)
    machine.emu_start(base+0x2506aa0, 0x400000, count=15)
    expected = bytearray(bytes([0x5A])*0x100)
    struct.pack_into('<III', expected, 0x68, 101, 202, 303)
    assert bytes(machine.mem_read(0x600000, len(expected))) == bytes(expected)
    results.append({'case': 'external_entry_position', 'bytesWritten': 12})

    nodes = base+0x9ebb810
    machine.mem_map((nodes-4) & ~4095, 0x11000)
    machine.reg_write(UC_X86_REG_RSP, 0x302000)
    machine.emu_start(base+0x1595110, base+0x1595156, count=20000)
    assert struct.unpack('<I', machine.mem_read(nodes-4, 4))[0] == 1
    assert struct.unpack('<H', machine.mem_read(nodes+2047*16+8, 2))[0] == 0
    exhausted = []

    def stop_on_exhaustion(uc, address, size, user_data):
        if address == base+0x159359f:
            exhausted.append(True)
            uc.emu_stop()

    machine.hook_add(UC_HOOK_CODE, stop_on_exhaustion)
    # Use 240 head slots and 2,047 independent handles, with native circular lists.
    for index in range(2048):
        machine.mem_write(0x302000, struct.pack('<Q', 0x400000))
        machine.reg_write(UC_X86_REG_RSP, 0x302000)
        machine.reg_write(UC_X86_REG_RCX, 0x604000+(index % 240)*2)
        machine.reg_write(UC_X86_REG_RDX, 0x605000+index*4)
        machine.emu_start(base+0x1593580, 0x400000, count=100)
        if index < 2047:
            assert machine.reg_read(UC_X86_REG_RAX) & 0xffff == index+1
            assert not exhausted
        else:
            assert exhausted == [True]
    assert struct.unpack('<I', machine.mem_read(nodes-4, 4))[0] == 0
    results.append({'case': 'shared_handle_nodes', 'usableNodes': 2047,
                    'headSlots': 240, 'nextAllocationReachedNativeExhaustion': True})
    report = {'status': 'selected_native_consumer_replay_passed', 'cases': results,
              'codeGuards': [{'rva': hex(s), 'size': e-s, 'sha256': h} for s,e,h in specifications],
              'capacity200Implemented': False, 'gameLaunched': False,
              'limit': 'Selected leaf calls and shared-node boundary only. No complete pointer coverage or live patch validation.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--dependencies', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.dependencies, args.output), indent=2))
