"""Replay stock and prepared pose production with authored native endpoints in owned memory."""
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
from relocate_function import relocate_function


def run(module: Path, executable: Path, dependencies: Path, output: Path) -> dict:
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    import unicorn.x86_const as x64
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new result file inside the private BO3 lab.')
    code = CapturedCode(module, executable)
    layout = TemporalLayout()
    stub_address = code.base + 0x20190000
    prepared = prepare_producer(code, layout, stub_address)
    original = code.guarded(PRODUCER_FUNCTION)
    entry = PRODUCER_FUNCTION.rva
    count_only = relocate_function(original, code.base + entry, stub_address, {
        code.base + 0x1BFE009: (7, b'\x48\x81\xfe' + struct.pack('<I', 300 * 0x2110)),
        code.base + 0x1BFE0A9: (7, b'\x48\x81\xfe' + struct.pack('<I', 300 * 0x2110)),
        code.base + 0x1BFE26E: (4, b'\x48\x81\xff' + struct.pack('<I', 300)),
    })
    actors, entities, history_a, history_b = 0x40000000, 0x48000000, 0x49000000, 0x49100000
    positions, angles, validity, stack, stop = 0x49200000, 0x49300000, 0x49400000, 0x50000000, 0x51000000
    selector, predicate, cookie_check = [code.base + rva for rva in (0x1BFDDB0, 0x27BC4C0, 0x2BC3AA0)]
    cookie_address = code.base + 0x35EEA10
    time_address = code.base + 0xA1B6C14
    actor_address = code.base + 0xA1B0798
    predicate_argument = code.base + 0xA1B0744
    cookie = 0x123456789ABCDEF0
    cases = []

    def replay(name: str, mode: str, rows: tuple[int | None, int | None], patterned: bool = False,
               only: tuple[int, ...] | None = None):
        machine = Uc(UC_ARCH_X86, UC_MODE_64)
        count = 64 if mode == 'stock' else 300
        vector_bytes = count * 12
        state_offset, valid_offset = vector_bytes * 2, vector_bytes * 2 + count
        row_bytes = (valid_offset + count + 3) & ~3
        blobs = [(code.base + entry, original)]
        start = code.base + entry
        if mode != 'stock':
            body = prepared.stub if mode == 'prepared' else count_only.code
            blobs.append((stub_address, body))
            start = stub_address
        regions = [(actors, 0x280000), (entities, 0x100000), (history_a, 0x4000), (history_b, 0x4000),
                   (positions, 0x4000), (angles, 0x4000), (validity, 0x4000), (stack, 0x10000), (stop, 0x1000),
                   (cookie_address, 8), (time_address, 4), (actor_address, 8), (predicate_argument, 4),
                   *[(target, 1) for target in (selector, predicate, cookie_check)]]
        pages = set()
        for address, size in regions + [(address, len(data)) for address, data in blobs]:
            pages.update(range(address & ~4095, (address + size + 4095) & ~4095, 4096))
        for page in sorted(pages):
            machine.mem_map(page, 4096)
        for address, data in blobs:
            machine.mem_write(address, data)
        for target in (selector, predicate, cookie_check):
            machine.mem_write(target, b'\xc3')
        machine.mem_write(cookie_address, struct.pack('<Q', cookie))
        machine.mem_write(time_address, struct.pack('<I', 10000))
        machine.mem_write(actor_address, struct.pack('<Q', actors))
        machine.mem_write(predicate_argument, struct.pack('<I', 0x55AA))
        row_images = [bytearray(row_bytes + 20), bytearray(row_bytes + 20)]
        initial_vectors = [(90000.0, 90001.0, 90002.0), (91000.0, 91001.0, 91002.0)]
        for address, values in ((positions, initial_vectors[0]), (angles, initial_vectors[1])):
            machine.mem_write(address, struct.pack('<3f', *values) * count + b'\xcc' * 16)
        machine.mem_write(validity, b'\x00' * count + b'\xcc' * 16)
        expected_valid, expected_vectors, expected_calls = [], [], []
        for index in range(count):
            active = not patterned or index % 11 != 0
            rejected = patterned and index % 7 == 0
            state_value = index % 251
            machine.mem_write(actors + index * 0x2110, bytes([int(active)]))
            machine.mem_write(actors + index * 0x2110 + 8, struct.pack('<Q', entities + index * 0x4F8))
            machine.mem_write(actors + index * 0x2110 + 0x798, struct.pack('<H', index))
            machine.mem_write(entities + index * 0x4F8 + 0xC0, struct.pack('<H', state_value))
            row_valid = []
            values = []
            for row in range(2):
                history_valid = (not patterned or index % (5 + row) != 0) and (only is None or index in only)
                matches_state = not patterned or index % (13 + row) != 0
                image = row_images[row]
                xyz = tuple(float(row * 4096 + index * 8 + field) for field in range(6))
                struct.pack_into('<3f', image, index * 12, *xyz[:3])
                struct.pack_into('<3f', image, vector_bytes + index * 12, *xyz[3:])
                image[state_offset + index] = state_value if matches_state else (state_value + 1) % 251
                image[valid_offset + index] = int(history_valid)
                values.append(xyz)
                row_valid.append(active and history_valid and matches_state and not rejected)
            # The native function drops the first result if both selector pointers are equal.
            available = [rows[0] is not None and rows[0] != rows[1], rows[1] is not None]
            valid = [available[row] and row_valid[rows[row]] for row in range(2)]
            expected_valid.append(int(any(valid)))
            if all(valid):
                first, second = values[rows[0]], values[rows[1]]
                expected_vectors.append(tuple((a + b) * 0.5 for a, b in zip(first, second)))
            elif valid[0]:
                expected_vectors.append(values[rows[0]])
            elif valid[1]:
                expected_vectors.append(values[rows[1]])
            else:
                expected_vectors.append(initial_vectors[0] + initial_vectors[1])
            for slot in range(2):
                if available[slot] and active and (row_images[rows[slot]][valid_offset + index] != 0) and (
                        row_images[rows[slot]][state_offset + index] == state_value):
                    expected_calls.append((slot, index))
        # Calls visit all indices of the first row before the second row.
        expected_calls.sort()
        for image, address in zip(row_images, (history_a, history_b)):
            image[-16:] = b'\xcc' * 16
            machine.mem_write(address, bytes(image))
        nonvolatile = {getattr(x64, 'UC_X86_REG_' + name): 0x100000000 + index
                       for index, name in enumerate(('RBX', 'RBP', 'RSI', 'RDI', 'R12', 'R13', 'R14', 'R15'))}
        for register, value in nonvolatile.items():
            machine.reg_write(register, value)
        saved_xmm = {getattr(x64, 'UC_X86_REG_XMM' + str(index)): (index << 120) | 0x112233445566778899
                     for index in range(6, 16)}
        for register, value in saved_xmm.items():
            machine.reg_write(register, value)
        initial_rsp = stack + 0xF008
        machine.mem_write(stack, b'\xaa' * 0x10000)
        machine.mem_write(initial_rsp, struct.pack('<Q', stop))
        machine.reg_write(x64.UC_X86_REG_RSP, initial_rsp)
        machine.reg_write(x64.UC_X86_REG_RCX, 9925)
        machine.reg_write(x64.UC_X86_REG_RDX, positions)
        machine.reg_write(x64.UC_X86_REG_R8, angles)
        machine.reg_write(x64.UC_X86_REG_R9, validity)
        selections, calls, cookie_values = [], [], []

        def endpoint(engine, address, size, unused):
            if address == selector:
                selections.append(struct.unpack('<i', engine.mem_read(engine.reg_read(x64.UC_X86_REG_RCX), 4))[0])
                row = rows[len(selections) - 1]
                engine.reg_write(x64.UC_X86_REG_RAX, 0 if row is None else (history_a, history_b)[row])
            elif address == predicate:
                index = engine.reg_read(x64.UC_X86_REG_RCX)
                assert engine.reg_read(x64.UC_X86_REG_RDX) == 0x55AA
                # R13 still holds the first pointer while it is being validated.
                first = engine.reg_read(x64.UC_X86_REG_R13) != engine.reg_read(x64.UC_X86_REG_R12)
                calls.append((0 if first else 1, index))
                engine.reg_write(x64.UC_X86_REG_RAX, int(patterned and index % 7 == 0))
            else:
                cookie_values.append(engine.reg_read(x64.UC_X86_REG_RCX))
            rsp = engine.reg_read(x64.UC_X86_REG_RSP)
            engine.reg_write(x64.UC_X86_REG_RIP, struct.unpack('<Q', engine.mem_read(rsp, 8))[0])
            engine.reg_write(x64.UC_X86_REG_RSP, rsp + 8)

        for target in (selector, predicate, cookie_check):
            machine.hook_add(UC_HOOK_CODE, endpoint, begin=target, end=target)
        execution_failure = None
        try:
            machine.emu_start(start, stop, count=200000)
        except UcError as error:
            if mode != 'count-only':
                raise
            execution_failure = str(error)
        matches = machine.reg_read(x64.UC_X86_REG_RIP) == stop
        matches &= machine.reg_read(x64.UC_X86_REG_RSP) == initial_rsp + 8
        matches &= all(machine.reg_read(register) == value for register, value in nonvolatile.items())
        matches &= all(machine.reg_read(register) == value for register, value in saved_xmm.items())
        matches &= selections == [100, 50] and calls == expected_calls and cookie_values == [cookie]
        matches &= machine.mem_read(validity, count + 16) == bytes(expected_valid) + b'\xcc' * 16
        for index, vectors in enumerate(expected_vectors):
            matches &= machine.mem_read(positions + index * 12, 12) == struct.pack('<3f', *vectors[:3])
            matches &= machine.mem_read(angles + index * 12, 12) == struct.pack('<3f', *vectors[3:])
        matches &= machine.mem_read(positions + vector_bytes, 16) == b'\xcc' * 16
        matches &= machine.mem_read(angles + vector_bytes, 16) == b'\xcc' * 16
        matches &= all(machine.mem_read(address, len(image)) == bytes(image)
                       for address, image in zip((history_a, history_b), row_images))
        matches &= machine.reg_read(x64.UC_X86_REG_RAX) & 255 == int(rows != (None, None))
        assert bool(matches) == (mode != 'count-only'), f'Producer contract differs in {name}.'
        cases.append({'case': name, 'actors': count, 'validOutputs': sum(expected_valid), 'predicateCalls': len(calls),
                      'contractMatches': bool(matches), 'countOnlyRefused': mode == 'count-only',
                      'executionFailure': execution_failure, 'cookieMatches': cookie_values == [cookie],
                      'finalRip': hex(machine.reg_read(x64.UC_X86_REG_RIP))})

    for mode in ('stock', 'prepared'):
        for name, rows in (('interpolate', (0, 1)), ('first-only', (0, None)), ('second-only', (None, 1)),
                           ('same-row', (1, 1)), ('no-rows', (None, None))):
            replay(mode + '-' + name, mode, rows)
        replay(mode + '-filter-pattern', mode, (0, 1), patterned=True)
    replay('prepared-boundaries', 'prepared', (0, 1), only=(0, 63, 64, 199, 299))
    replay('prepared-no-valid-actors', 'prepared', (0, 1), only=())
    replay('count-only300-refused', 'count-only', (0, 1), only=(0, 63, 64, 199, 299))
    result = {'passed': True, 'scope': 'Owned full-function replay; selector, actor predicate and cookie endpoints are authored callbacks.',
              'cases': cases, 'nativeBytes': len(original), 'preparedBytes': len(prepared.stub),
              'sourceFiles': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in
                              [PATCHES / 'temporal_producer.py', PATCHES / 'temporal_layout.py', PATCHES / 'relocate_function.py', Path(__file__)]},
              'originalFunctionSha256': hashlib.sha256(original).hexdigest(), 'gameWrites': 0, 'activationAllowed': False,
              'unverified': ['Native selector and recorder', 'History save framing', 'Caller buffers', 'Windows unwind and handlers', 'Game behavior']}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    return {'passed': True, 'cases': len(cases), 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'dependencies', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.dependencies, args.output), indent=2))
