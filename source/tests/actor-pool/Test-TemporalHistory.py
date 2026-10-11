"""Replay native history recording, selection, interpolation and restoration in owned memory."""
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


def run(module: Path, executable: Path, dependencies: Path, output: Path) -> dict:
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    import unicorn.x86_const as x64
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new result file inside the private BO3 lab.')
    code = CapturedCode(module, executable)
    layout = TemporalLayout()
    actors, entities, expanded_history, state, argument = 0x40000000, 0x48000000, code.base + 0x20200000, 0x49200000, 0x49300000
    stack, stop = 0x50000000, 0x51000000
    native_history = code.base + 0xA1C3484
    counter_address, time_address = code.base + 0xA1CB6D4, code.base + 0xA1B6C14
    recorder_stub, selector_stub, producer_stub, restore_stub = [code.base + 0x201A0000 + index * 0x10000 for index in range(4)]
    history_edits = prepare_history(code, layout, expanded_history, recorder_stub, selector_stub)
    producer = prepare_producer(code, layout, producer_stub)
    restore_edits = prepare_restore(code, layout, restore_stub)
    functions = [RECORDER_FUNCTION, SELECTOR_FUNCTION, PRODUCER_FUNCTION, RESTORE_FUNCTION]
    callbacks = [code.base + rva for rva in (0x27BC4C0, 0x2BC3AA0, 0x2206F70)]
    nonvolatile_names = ('RBX', 'RBP', 'RSI', 'RDI', 'R12', 'R13', 'R14', 'R15')
    cases = []

    def replay(name: str, mode: str, start_counter: int, frames: int, patterned: bool = False):
        machine = Uc(UC_ARCH_X86, UC_MODE_64)
        count = 64 if mode == 'stock' else 300
        vector_bytes = count * 12
        state_offset, valid_offset = vector_bytes * 2, vector_bytes * 2 + count
        time_offset = (valid_offset + count + 3) & ~3
        row_bytes = time_offset + 4
        history = native_history if mode == 'stock' else expanded_history
        blobs = [(code.base + guard.rva, code.guarded(guard)) for guard in functions]
        if mode != 'stock':
            for edit in (*history_edits, producer, *restore_edits):
                blobs.append((code.base + edit.guard.rva, edit.replacement))
                if edit.stub:
                    blob = edit.stub
                    if mode == 'unchecked-tail' and edit.name == 'temporal_history_recorder':
                        check = b'\x49\x81\xf9' + struct.pack('<I', 296) + b'\x0f\x8d'
                        assert blob.count(check) == 1
                        offset = blob.index(check)
                        blob = blob[:offset] + b'\x90' * 13 + blob[offset + 13:]
                    blobs.append((edit.stub_address, blob))
        regions = [(actors, 0x280000), (entities, 0x100000), (history - 16, row_bytes * 20 + 32),
                   (counter_address, 4), (time_address, 4), (code.base + 0xA1B0744, 4), (code.base + 0xA1B0798, 8),
                   (code.base + 0x35EEA10, 8), (state, 0x4000), (argument, 0x1000), (stack, 0x10000), (stop, 0x1000),
                   *[(address, 1) for address in callbacks]]
        pages = set()
        for address, size in regions + [(address, len(data)) for address, data in blobs]:
            pages.update(range(address & ~4095, (address + size + 4095) & ~4095, 4096))
        for page in sorted(pages):
            machine.mem_map(page, 4096)
        for address, data in blobs:
            machine.mem_write(address, data)
        for address in callbacks:
            machine.mem_write(address, b'\xc3')
        machine.mem_write(actors, b'\xcc' * (304 * 0x2110))
        machine.mem_write(code.base + 0xA1B0798, struct.pack('<Q', actors))
        machine.mem_write(code.base + 0xA1B0744, struct.pack('<I', 0x55AA))
        cookie = 0x123456789ABCDEF0
        machine.mem_write(code.base + 0x35EEA10, struct.pack('<Q', cookie))
        expected = bytearray(b'\xcc' * (row_bytes * 20))
        machine.mem_write(history - 16, b'\xcc' * (row_bytes * 20 + 32))
        # The stock counter is the first DWORD after its history array.
        machine.mem_write(counter_address, struct.pack('<I', start_counter))
        states = [index % 251 for index in range(count)]
        active = [not patterned or index % 11 != 0 for index in range(count)]
        relinks, cookies, predicate_calls = [], [], []

        def endpoint(engine, address, size, unused):
            if address == callbacks[0]:
                index = engine.reg_read(x64.UC_X86_REG_RCX)
                assert 0 <= index < count and engine.reg_read(x64.UC_X86_REG_RDX) == 0x55AA
                predicate_calls.append(index)
                engine.reg_write(x64.UC_X86_REG_RAX, int(patterned and index % 7 == 0))
            elif address == callbacks[1]:
                cookies.append(engine.reg_read(x64.UC_X86_REG_RCX))
            else:
                entity = engine.reg_read(x64.UC_X86_REG_RCX)
                assert (entity - entities) % 0x4F8 == 0
                relinks.append((entity - entities) // 0x4F8)
            rsp = engine.reg_read(x64.UC_X86_REG_RSP)
            engine.reg_write(x64.UC_X86_REG_RIP, struct.unpack('<Q', engine.mem_read(rsp, 8))[0])
            engine.reg_write(x64.UC_X86_REG_RSP, rsp + 8)

        for address in callbacks:
            machine.hook_add(UC_HOOK_CODE, endpoint, begin=address, end=address)

        def call(entry: int, args: tuple[int, ...] = ()) -> int:
            initial_rsp = stack + 0xF008
            saved = {getattr(x64, 'UC_X86_REG_' + name): 0x100000000 + index for index, name in enumerate(nonvolatile_names)}
            saved.update({getattr(x64, 'UC_X86_REG_XMM' + str(index)): (index << 120) | 0x112233445566778899
                          for index in range(6, 16)})
            for register, value in saved.items():
                machine.reg_write(register, value)
            machine.reg_write(x64.UC_X86_REG_RSP, initial_rsp)
            machine.mem_write(initial_rsp, struct.pack('<Q', stop))
            for name, value in zip(('RCX', 'RDX', 'R8', 'R9'), args):
                machine.reg_write(getattr(x64, 'UC_X86_REG_' + name), value)
            machine.emu_start(code.base + entry, stop, count=200000)
            assert machine.reg_read(x64.UC_X86_REG_RIP) == stop
            assert machine.reg_read(x64.UC_X86_REG_RSP) == initial_rsp + 8
            assert all(machine.reg_read(register) == value for register, value in saved.items())
            return machine.reg_read(x64.UC_X86_REG_RAX)

        now = 10000
        machine.mem_write(time_address, struct.pack('<I', now))
        for frame in range(frames):
            now = 10000 + frame * 50
            machine.mem_write(time_address, struct.pack('<I', now))
            row = (start_counter + frame) % 20
            struct.pack_into('<I', expected, row * row_bytes + time_offset, now)
            for index in range(count):
                xyz = tuple(float(frame * 4096 + index * 8 + field) for field in range(6))
                machine.mem_write(actors + index * 0x2110, bytes([int(active[index])]))
                machine.mem_write(actors + index * 0x2110 + 8, struct.pack('<Q', entities + index * 0x4F8))
                machine.mem_write(actors + index * 0x2110 + 0x798, struct.pack('<H', index))
                machine.mem_write(entities + index * 0x4F8 + 0x230, struct.pack('<6f', *xyz))
                machine.mem_write(entities + index * 0x4F8 + 0xC0, struct.pack('<H', states[index]))
                expected[row * row_bytes + valid_offset + index] = int(active[index])
                if active[index]:
                    struct.pack_into('<3f', expected, row * row_bytes + index * 12, *xyz[:3])
                    struct.pack_into('<3f', expected, row * row_bytes + vector_bytes + index * 12, *xyz[3:])
                    expected[row * row_bytes + state_offset + index] = states[index]
            call(RECORDER_FUNCTION.rva)
            matches = machine.mem_read(history, len(expected)) == bytes(expected)
            if mode == 'unchecked-tail':
                assert not matches, 'The unchecked eight-actor tail did not corrupt its timestamp.'
                corrupted = bytearray(expected)
                struct.pack_into('<I', corrupted, row * row_bytes + time_offset, 0)
                assert machine.mem_read(history, len(expected)) == bytes(corrupted)
                cases.append({'case': name, 'actors': count, 'uncheckedTailRefused': True, 'timestampPreserved': False})
                return
            assert matches, f'History differs after frame {frame} in {name}.'
            assert machine.mem_read(history - 16, 16) == b'\xcc' * 16
            following = (struct.pack('<I', start_counter + frame + 1) + b'\xcc' * 12) if mode == 'stock' else b'\xcc' * 16
            assert machine.mem_read(history + len(expected), 16) == following
            assert struct.unpack('<I', machine.mem_read(counter_address, 4))[0] == start_counter + frame + 1
        counter = start_counter + frames
        requests = (-50, 0, 1, 49, 50, 75, 100, 1000, 1001, 5000)
        for request in requests:
            machine.mem_write(argument, struct.pack('<i', request))
            actual = call(SELECTOR_FUNCTION.rva, (argument,))
            adjusted = request
            if request <= 0:
                selected = None
            else:
                selected = counter - request // 50 - 1
                if selected < counter - 20:
                    selected, adjusted = counter - 20, 1000
                if selected < 0:
                    selected, adjusted = 0, counter * 50
                if selected >= counter:
                    selected, adjusted = None, 0
            assert actual == (0 if selected is None else history + selected % 20 * row_bytes)
            assert struct.unpack('<i', machine.mem_read(argument, 4))[0] == adjusted
        machine.mem_write(state, b'\xcc' * (vector_bytes * 2) + b'\x00' * count + b'\xcc' * 16)
        wanted = bytearray(machine.mem_read(state, vector_bytes * 2 + count + 16))
        current = tuple(90000.0 + field for field in range(6))
        accepted = []
        for index in range(count):
            machine.mem_write(entities + index * 0x4F8 + 0x230, struct.pack('<6f', *current))
            state_matches = not patterned or index % 13 != 0
            machine.mem_write(entities + index * 0x4F8 + 0xC0, struct.pack('<H', states[index] if state_matches else states[index] + 1))
            if frames and active[index] and state_matches and (not patterned or index % 7 != 0):
                accepted.append(index)
                xyz = tuple(float((frames - 2.5) * 4096 + index * 8 + field) for field in range(6))
                struct.pack_into('<3f', wanted, index * 12, *xyz[:3])
                struct.pack_into('<3f', wanted, vector_bytes + index * 12, *xyz[3:])
                wanted[vector_bytes * 2 + index] = 1
        assert call(PRODUCER_FUNCTION.rva, (now - 75, state, state + vector_bytes, state + vector_bytes * 2)) & 255 == int(frames != 0)
        assert cookies == [cookie]
        assert machine.mem_read(state, len(wanted)) == bytes(wanted)
        call(RESTORE_FUNCTION.rva, (state,))
        assert relinks == accepted
        for index in range(count):
            wanted_pose = (struct.unpack_from('<3f', wanted, index * 12) +
                           struct.unpack_from('<3f', wanted, vector_bytes + index * 12)) if index in accepted else current
            assert machine.mem_read(entities + index * 0x4F8 + 0x230, 24) == struct.pack('<6f', *wanted_pose)
        wanted[vector_bytes * 2:vector_bytes * 2 + count] = b'\x00' * count
        assert machine.mem_read(state, len(wanted)) == bytes(wanted)
        assert machine.mem_read(history, len(expected)) == bytes(expected)
        cases.append({'case': name, 'actors': count, 'framesRecorded': frames, 'finalCounter': counter,
                      'selectorRequests': len(requests), 'restoredActors': len(accepted), 'actor299Restored': 299 in accepted,
                      'nativeHistoryAndPoseChainMatches': True, 'predicateCalls': len(predicate_calls)})

    replay('stock64-chain', 'stock', 0, 3)
    replay('stock64-filtered-wrap', 'stock', 19, 3, True)
    replay('wide300-empty-history', 'prepared', 0, 0)
    replay('wide300-chain', 'prepared', 0, 3)
    replay('wide300-filtered-wrap', 'prepared', 19, 3, True)
    replay('wide300-full-history-wrap', 'prepared', 0, 25)
    replay('wide300-large-counter', 'prepared', 100003, 3)
    replay('unchecked-eight-lane-tail-refused', 'unchecked-tail', 0, 1)
    result = {'passed': True, 'cases': cases,
              'scope': 'Owned captured recorder, selector, producer and restore chain. Only predicate, cookie and relink endpoints are authored.',
              'sourceFiles': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in
                              [PATCHES / 'temporal_history.py', PATCHES / 'temporal_producer.py', PATCHES / 'temporal_restore.py',
                               PATCHES / 'temporal_layout.py', PATCHES / 'relocate_function.py', Path(__file__)]},
              'gameWrites': 0, 'activationAllowed': False,
              'unverified': ['History construction and reset', 'Save translation', 'Rewind caller buffers', 'Windows unwind and handlers', 'Game behavior']}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    return {'passed': True, 'cases': len(cases), 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'dependencies', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.dependencies, args.output), indent=2))
