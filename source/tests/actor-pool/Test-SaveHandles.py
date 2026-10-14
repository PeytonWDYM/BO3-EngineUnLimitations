"""Replay paired native typed-pointer descriptors against legacy and expanded save handles."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode
from load_counts import LoadCounts, LoadShape
from runtime_recipe import prepare_recipe


def run(module, executable, dependencies, output, candidate):
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    import unicorn.x86_const as x
    output = output.resolve()
    if output.exists() or (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents:
        raise ValueError('Use a new private BO3 lab result directory.')
    code = CapturedCode(module, executable)
    arena = code.base + 0x20000000
    counts = LoadCounts(arena + 0x2C40000)
    storage_edits = [edit for edit in prepare_recipe(code, arena).edits
                     if edit.guard.rva in (0xCF97A, 0x159A2CE, 0x159A2DF)]
    edits = ()
    if candidate:
        from save_handles import prepare_save_handles
        edits = prepare_save_handles(code, counts, arena + 0x1A2000)
    data, stack, stop, old_pool, new_pool = 0x10000000, 0x20000000, 0x30000000, 0x40000000, 0x42000000
    cases, artifacts = [], bytearray()
    saved = {name: 0x66660000 + i for i, name in enumerate(('RBX','RBP','RSI','RDI','R12','R13','R14','R15'))}

    class Refused(Exception):
        pass

    for family, selector, stride, stock, expanded, pointer in (
        ('actor', 19, 0x2110, 64, 500, 0xA1B0798),
        ('sentient', 20, 0x3088, 104, 540, 0xA1B0790),
        ('sentient-word', 3, 0x3088, 104, 540, 0xA1B0790),
    ):
        machine = Uc(UC_ARCH_X86, UC_MODE_64)
        for address, size in ((code.base + 0xC0000, 0x13000), (code.base + 0xA1B0000, 0x1000),
                              (code.base + 0x2277000, 0x1000), (code.base + 0x20EC000, 0x1000),
                              (arena + 0x1A2000, 0x1000), (counts.base, 0x1000),
                              (code.base + 0x159A000, 0x1000), (code.base + 0x1595000, 0x1000),
                              (code.base + 0x1593000, 0x1000), (arena + 0x2600000, 0x1000),
                              (arena + 0x400000, 0x700000),
                              (data, 0x10000), (stack, 0x20000), (stop, 0x1000),
                              (old_pool, 0x700000), (new_pool, 0x700000)):
            machine.mem_map(address, size)
        machine.mem_write(code.base + 0xC0000, code.read(0xC0000, 0x13000))
        for rva in (0x159A000, 0x1595000):
            machine.mem_write(code.base + rva, code.read(rva, 4096))
        for edit in storage_edits:
            machine.mem_write(code.base + edit.guard.rva, edit.replacement)
        for edit in edits:
            machine.mem_write(code.base + edit.guard.rva, edit.replacement)
            machine.mem_write(edit.stub_address, edit.stub)
        descriptor, record, file = data, data + 0x100, data + 0x200
        machine.mem_write(descriptor + 8, struct.pack('<QI', 8, selector))
        stream, cursor = bytearray(), 0
        word = selector == 3
        current_pool = arena + 0x400000 if word else new_pool

        def endpoint(current, address, size, unused):
            nonlocal cursor
            if address == code.base + 0x20EC0B0:
                raise Refused('The native pointer descriptor rejected this handle.')
            if address == code.base + 0x1593580:
                index = (current.reg_read(x.UC_X86_REG_RCX) - arena - 0x2600000) // 2
                assert 0 <= index < 540 and current.reg_read(x.UC_X86_REG_RDX) == record + 8
                current.reg_write(x.UC_X86_REG_RAX, 0x5000 + index)
            else:
                assert current.reg_read(x.UC_X86_REG_RDX) == 4
                assert cursor + 4 <= len(stream)
                current.mem_write(current.reg_read(x.UC_X86_REG_R8), bytes(stream[cursor:cursor + 4]))
                cursor += 4
            rsp = current.reg_read(x.UC_X86_REG_RSP)
            pc = struct.unpack('<Q', current.mem_read(rsp, 8))[0]
            current.reg_write(x.UC_X86_REG_RSP, rsp + 8)
            current.reg_write(x.UC_X86_REG_RIP, pc)

        for rva in (0x22778B0, 0x20EC0B0, 0x1593580):
            machine.hook_add(UC_HOOK_CODE, endpoint, begin=code.base + rva, end=code.base + rva)

        def call(rva):
            rsp = stack + 0x1F008
            machine.mem_write(rsp, struct.pack('<Q', stop) + bytes(0xF0))
            machine.reg_write(x.UC_X86_REG_RSP, rsp)
            for name, value in saved.items():
                machine.reg_write(getattr(x, 'UC_X86_REG_' + name), value)
            for name, value in (('RCX', descriptor), ('RDX', record), ('R8', file)):
                machine.reg_write(getattr(x, 'UC_X86_REG_' + name), value)
            try:
                machine.emu_start(code.base + rva, stop, count=10000)
            except Refused:
                return False
            assert machine.reg_read(x.UC_X86_REG_RIP) == stop
            assert machine.reg_read(x.UC_X86_REG_RSP) == rsp + 8
            assert all(machine.reg_read(getattr(x, 'UC_X86_REG_' + name)) == value for name, value in saved.items())
            return True

        # Write once and decode against a different current pool, as saved state and migration require.
        for handle in (0, 1, stock, stock + 1, 128, 256, expanded, expanded + 1):
            stream.clear()
            machine.mem_write(file, bytes(0x100))
            machine.mem_write(code.base + pointer, struct.pack('<Q', current_pool if word else old_pool))
            machine.mem_write(record, b'\xA5' * 64)
            value = 0 if handle == 0 else old_pool + (handle - 1) * stride
            machine.mem_write(record + 8, struct.pack('<HH', handle, 0) if word else struct.pack('<Q', value))
            written = call(0xCF8C0)
            pending = struct.unpack('<I', machine.mem_read(file + 0x18, 4))[0]
            stream.extend(machine.mem_read(file + 0x38, pending))
            expected_write = handle <= (expanded if candidate else stock)
            assert written == expected_write, (family, handle, 'writer', written)
            if written:
                assert stream == (struct.pack('<I', handle) if handle or word else b''), (family, handle, stream.hex())
                artifacts += struct.pack('<III', selector, handle, len(stream)) + stream
            cases.append({'family': family, 'handle': handle, 'writerAdmitted': written})
            for shape in (LoadShape.Legacy64, LoadShape.Expanded500):
                bound = stock if shape is LoadShape.Legacy64 else expanded
                machine.mem_write(counts.base, counts.values(shape))
                machine.mem_write(code.base + pointer, struct.pack('<Q', current_pool))
                stream[:] = struct.pack('<I', handle) + b'NEXT-SECTION'
                cursor = 0
                before = bytearray(b'\x5A' * 64)
                if word:
                    struct.pack_into('<HH', before, 8, 0, 0)
                else:
                    struct.pack_into('<Q', before, 8, 0 if handle == 0 else value)
                machine.mem_write(record, bytes(before))
                read = call(0xC0410)
                expected_read = handle <= (bound if candidate else stock)
                assert read == expected_read, (family, shape.name, handle, 'reader', read)
                expected = bytearray(before)
                if read and handle:
                    if word:
                        struct.pack_into('<HH', expected, 8, handle, 0x5000 + handle - 1)
                    else:
                        struct.pack_into('<Q', expected, 8, current_pool + (handle - 1) * stride)
                assert machine.mem_read(record, 64) == expected
                assert cursor == (0 if handle == 0 and not word else 4)
                if read and handle:
                    assert stream[cursor:] == b'NEXT-SECTION'
                cases.append({'family': family, 'shape': shape.name, 'handle': handle, 'readerAdmitted': read,
                              'currentPoolExact': read, 'bytesRead': cursor})
        if candidate and not word:
            stream[:] = struct.pack('<I', 0)
            cursor = 0
            machine.mem_write(record + 8, struct.pack('<Q', new_pool))
            before = bytes(machine.mem_read(record, 64))
            assert not call(0xC0410) and machine.mem_read(record, 64) == before
            stream.clear()
            machine.mem_write(file, bytes(0x100))
            machine.mem_write(record + 8, struct.pack('<Q', new_pool - stride))
            assert not call(0xCF8C0) and not stream
            cases.append({'family': family, 'zeroNonNullAndBeforePoolRefused': True})
    output.mkdir(parents=True)
    artifact = output / 'typed-save-handles.bin'
    artifact.write_bytes(artifacts)
    result = {'passed': True, 'candidate': candidate, 'cases': cases,
              'executableSha256': code.executable_sha256,
              'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'artifactSha256': hashlib.sha256(artifacts).hexdigest(), 'gameWrites': 0,
              'scope': 'Complete captured native descriptor dispatch, pointer/index conversion, four-byte writer, sentient handle clear/set, and native returns. Scalar read I/O, list allocation, and diagnostic stop are authored. Per-load count selection is modeled. Whole-game saves and host migration remain unverified.'}
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return {'passed': True, 'candidate': candidate, 'cases': len(cases), 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'dependencies', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--candidate', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.dependencies, args.output, args.candidate)))
