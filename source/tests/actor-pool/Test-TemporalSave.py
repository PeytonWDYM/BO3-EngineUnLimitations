"""Replay the native temporal save section and legacy imports in owned memory."""
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
from temporal_save import HISTORY_WRITE, HISTORY_COUNTER_WRITE, HistoryFormat, import_history, prepare_history_write


def history_bytes(actors: int) -> bytes:
    vectors = actors * 12
    time = (vectors * 2 + actors * 2 + 3) & ~3
    result = bytearray((time + 4) * 20)
    for row in range(20):
        offset = row * (time + 4)
        for actor in range(actors):
            for base, tag in ((0, 0x7FC00000), (vectors, 0x80000000)):
                struct.pack_into('<III', result, offset + base + actor * 12,
                                 tag | (row << 10) | actor, 0x12340000 | actor, 0xAABB0000 | row)
            result[offset + vectors * 2 + actor] = (row + actor) & 255
            result[offset + vectors * 2 + actors + actor] = (row ^ actor) & 1
        struct.pack_into('<I', result, offset + time, 0xF0000000 | row)
    return bytes(result)


def run(module: Path, executable: Path, dependencies: Path, output: Path) -> dict:
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    import unicorn.x86_const as x64
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab result path.')
    code = CapturedCode(module, executable)
    native = code.guarded(HISTORY_WRITE) + code.guarded(HISTORY_COUNTER_WRITE)
    start = code.base + HISTORY_WRITE.rva
    stop = start + len(native)
    stream_writer = code.base + 0x2277B80
    copy = code.base + 0x2BC4EB0
    pool = code.base + 0x20200000
    counter = code.base + 0xA1CB6D4
    stack, file = 0x50000000, 0x51000000
    following = b'FOLLOWING-CORPSE-HISTORY-AND-SECTION'
    cases = []

    def write(actors: int, cursor: int, expanded: bool, stale: bool = False) -> bytes:
        machine = Uc(UC_ARCH_X86, UC_MODE_64)
        layout = TemporalLayout(ActorShape(actors)) if expanded else None
        data = history_bytes(actors if expanded else 64)
        address = pool if expanded else code.base + 0xA1C3484
        body = bytearray(native)
        if expanded:
            edit = prepare_history_write(code, layout, pool)
            assert edit.replacement[0x25:0x2A] == code.read(0x1166C3, 5), 'The native stream call moved across its original state map.'
            body[:edit.guard.size] = edit.replacement
            if stale:
                marker = b'\xBA' + struct.pack('<I', layout.history_bytes)
                assert body.count(marker) == 1
                offset = body.index(marker)
                body[offset:offset + 5] = b'\xBA' + struct.pack('<I', 0x8250)
        regions = [(start, len(body)), (address - 16, len(data) + 32), (counter, 4),
                   (stack, 4096), (file, 0x90000), (stream_writer, 1), (copy, 1)]
        pages = set()
        for address_start, size in regions:
            pages.update(range(address_start & ~4095, (address_start + size + 4095) & ~4095, 4096))
        for page in sorted(pages):
            machine.mem_map(page, 4096)
        machine.mem_write(start, bytes(body))
        machine.mem_write(address - 16, b'\xA5' * 16 + data + b'\x5A' * 16)
        machine.mem_write(counter, struct.pack('<I', 0xDEADBEEF))
        machine.mem_write(file, b'\xCC' * 0x90000)
        machine.mem_write(file + 0x18, struct.pack('<I', cursor))
        machine.mem_write(file + 0x38 + cursor + len(data) + 4, following)
        machine.mem_write(stream_writer, b'\xC3')
        machine.mem_write(copy, b'\xC3')
        machine.reg_write(x64.UC_X86_REG_R13, file)
        machine.reg_write(x64.UC_X86_REG_RSP, stack + 0x808)
        calls = []

        def endpoint(engine, pc, size, unused):
            if pc == stream_writer:
                owner = engine.reg_read(x64.UC_X86_REG_RCX)
                length = engine.reg_read(x64.UC_X86_REG_EDX)
                source = engine.reg_read(x64.UC_X86_REG_R8)
                assert owner == file
                position = struct.unpack('<I', engine.mem_read(file + 0x18, 4))[0]
                engine.mem_write(file + 0x38 + position, bytes(engine.mem_read(source, length)))
                engine.mem_write(file + 0x18, struct.pack('<I', position + length))
                calls.append(length)
            elif pc == copy:
                destination = engine.reg_read(x64.UC_X86_REG_RCX)
                source = engine.reg_read(x64.UC_X86_REG_RDX)
                length = engine.reg_read(x64.UC_X86_REG_R8)
                engine.mem_write(destination, bytes(engine.mem_read(source, length)))
        machine.hook_add(UC_HOOK_CODE, endpoint)
        machine.emu_start(start, stop, count=30000)
        written = struct.unpack('<I', machine.mem_read(file + 0x18, 4))[0] - cursor
        encoded = bytes(machine.mem_read(file + 0x38 + cursor, written))
        if stale:
            assert written != len(data) + 4 and encoded != data + struct.pack('<I', 0xDEADBEEF)
        else:
            assert written == len(data) + 4
            assert encoded == data + struct.pack('<I', 0xDEADBEEF)
            assert bytes(machine.mem_read(file + 0x38 + cursor + written, len(following))) == following
        assert bytes(machine.mem_read(address - 16, 16)) == b'\xA5' * 16
        tail_canary = b'\x5A' * 16 if expanded else struct.pack('<I', 0xDEADBEEF) + b'\x5A' * 12
        assert bytes(machine.mem_read(address + len(data), 16)) == tail_canary
        assert machine.reg_read(x64.UC_X86_REG_R13) == file
        assert machine.reg_read(x64.UC_X86_REG_RBX) == 0x104
        assert machine.reg_read(x64.UC_X86_REG_RSP) == stack + 0x808
        cases.append({'actors': actors if expanded else 64, 'cursor': cursor,
                      'staleExtentRefused': stale, 'streamCalls': calls, 'writtenBytes': written})
        return encoded

    for cursor in (0, 8, 0x3FFF0):
        write(64, cursor, False)
        for actors in (300, 500):
            write(actors, cursor, True)
    write(500, 0, True, True)
    for actors, expanded_format in ((300, HistoryFormat.Expanded300), (500, HistoryFormat.Expanded500)):
        layout = TemporalLayout(ActorShape(actors))
        legacy = history_bytes(64)
        imported = import_history(legacy + following, layout, HistoryFormat.Legacy64)
        assert imported.consumed == 0x8250
        assert (legacy + following)[imported.consumed:] == following
        for row in range(20):
            source = row * 0x684
            target = row * layout.history_row_bytes
            for source_offset, target_offset, size in ((0, 0, 0x300), (0x300, layout.vector_bytes, 0x300),
                    (0x600, layout.history_state_offset, 64), (0x640, layout.history_valid_offset, 64),
                    (0x680, layout.history_time_offset, 4)):
                assert imported.data[target + target_offset:target + target_offset + size] == legacy[source + source_offset:source + source_offset + size]
            for offset, used, total in ((0, 0x300, layout.vector_bytes), (layout.vector_bytes, 0x300, layout.vector_bytes),
                    (layout.history_state_offset, 64, actors), (layout.history_valid_offset, 64, actors)):
                assert imported.data[target + offset + used:target + offset + total] == b'\0' * (total - used)
        expanded = history_bytes(actors)
        decoded = import_history(expanded + following, layout, expanded_format)
        assert decoded.data == expanded and decoded.consumed == layout.history_bytes
        assert (expanded + following)[decoded.consumed:] == following
        for data, format_value in ((legacy[:-1], HistoryFormat.Legacy64), (expanded[:-1], expanded_format),
                                  (expanded, HistoryFormat.Expanded500 if actors == 300 else HistoryFormat.Expanded300),
                                  (expanded, 'unknown')):
            try:
                import_history(data, layout, format_value)
            except ValueError:
                pass
            else:
                raise AssertionError('An invalid temporal import escaped admission.')
        cases.append({'importActors': actors, 'legacyBytesConsumed': imported.consumed,
                      'expandedBytesConsumed': decoded.consumed, 'importRefusals': 4, 'unusedActorsZeroed': True})
    refusals = 0
    layout = TemporalLayout(ActorShape(500))
    for address in (0, pool + 1, code.base + 0xA1C3484, 2**64 - 16):
        try:
            prepare_history_write(code, layout, address)
        except ValueError:
            refusals += 1
        else:
            raise AssertionError('An invalid temporal save address escaped admission.')
    class ChangedCode(CapturedCode):
        changed_rva: int
        def read(self, rva: int, size: int) -> bytes:
            raw = super().read(rva, size)
            return bytes((raw[0] ^ 1,)) + raw[1:] if rva == self.changed_rva else raw
    changed = ChangedCode(module, executable)
    for guard in (HISTORY_WRITE, HISTORY_COUNTER_WRITE):
        changed.changed_rva = guard.rva
        try:
            prepare_history_write(changed, layout, pool)
        except ValueError:
            refusals += 1
        else:
            raise AssertionError('An altered native writer escaped admission.')
    result = {'passed': True, 'cases': cases, 'addressAndGuardRefusals': refusals,
              'scope': 'Owned exact native writer block and pure legacy-history import. Stream-write and copy endpoints are authored.',
              'gameWrites': 0, 'activationAllowed': False, 'rootSaveFormatAdmitted': False,
              'unverified': ['Native compression and flush behavior', 'Root header binding', 'Complete actor save attachments', 'Game saves and migration'],
              'sourceFiles': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in
                              [PATCHES / 'temporal_save.py', PATCHES / 'temporal_layout.py', Path(__file__)]}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    return {'passed': True, 'cases': len(cases), 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'dependencies', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.dependencies, args.output), indent=2))
