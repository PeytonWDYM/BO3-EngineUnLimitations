"""Replay the native actor member getter with recipe bytes and distinct old/new banks."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode, CodeGuard
from runtime_recipe import prepare_recipe

SITE = CodeGuard(0x15C509E, 7, '971e7245bbc4168951a1f22c914e66f9c19a1f5a0e63c0893dea6e68e667f676')
OWNER = CodeGuard(0x15C3670, 6808, 'bf9ecdfc6945e8192d8eaa03e1acc270219a44b8f8ebae9d59134a6525a28670')
METADATA = CodeGuard(0x3149210, 8, '37cca59ce09d4c4b86dcb65c3d88ba663f80423fc3641c731b1aba874dc5fb49')
STRIDE = 0xB00
MEMBER = 0xB8
COUNT = 500


def run(module: Path, executable: Path, dependencies: Path, output: Path, stock: bool) -> dict:
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64
    import unicorn.x86_const as registers

    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new result directory inside the private BO3 lab.')
    output.mkdir(parents=True)
    code = CapturedCode(module, executable)
    for guard in (SITE, OWNER, METADATA):
        code.guarded(guard)
    arena = (code.base + code.meta['imageSize'] + 65535) & ~65535
    recipe = prepare_recipe(code, arena)
    selected = tuple(edit for edit in recipe.edits if OWNER.rva <= edit.guard.rva < OWNER.rva + OWNER.size)
    old_bank = code.base + 0xA1846C0
    new_bank = arena + 0x2400000
    entity_pool, binding, vehicle, stack, stop = (0x10000000, 0x20000000, 0x30000000, 0x40000000, 0x50000000)
    engine = Uc(UC_ARCH_X86, UC_MODE_64)
    pages = set()

    def map_interval(address: int, size: int) -> None:
        for page in range(address & ~4095, (address + size + 4095) & ~4095, 4096):
            if page not in pages:
                engine.mem_map(page, 4096)
                pages.add(page)

    for address, size in ((code.base + OWNER.rva, OWNER.size),
                          (old_bank - 4096, COUNT * STRIDE + 8192),
                          (new_bank - 4096, COUNT * STRIDE + 8192),
                          (entity_pool, 2048 * 0x4F8), (binding, 4096),
                          (vehicle, 0x3000), (stack, 0x20000), (stop, 4096)):
        map_interval(address, size)
    engine.mem_write(code.base + OWNER.rva, code.guarded(OWNER))
    if not stock:
        for edit in selected:
            engine.mem_write(code.base + edit.guard.rva, edit.replacement)
            if edit.stub:
                map_interval(edit.stub_address, len(edit.stub))
                engine.mem_write(edit.stub_address, edit.stub)
    # Extend this owned poison replica to 500 records so stale high IDs have a deterministic oracle.
    engine.mem_write(old_bank, b'\xCC' * (COUNT * STRIDE))
    engine.mem_write(new_bank, b'\x5A' * (COUNT * STRIDE))
    for index in range(COUNT):
        engine.mem_write(old_bank + index * STRIDE + MEMBER,
                         struct.pack('<III', 0xBAD00000 + index, 0xBAD10000 + index, 0xBAD20000 + index))
        engine.mem_write(new_bank + index * STRIDE + MEMBER,
                         struct.pack('<III', 0x12340000 + index, 0x33440000 + index, 0x55660000 + index))
    canaries = {address: b'\xA5' * 16 for bank in (old_bank, new_bank)
                for address in (bank - 16, bank + COUNT * STRIDE)}
    for address, value in canaries.items():
        engine.mem_write(address, value)
    old_before = bytes(engine.mem_read(old_bank, COUNT * STRIDE))
    new_before = bytes(engine.mem_read(new_bank, COUNT * STRIDE))
    engine.mem_write(binding + 0x20, struct.pack('<Q', entity_pool))
    entity_id = 700
    entity = entity_pool + entity_id * 0x4F8
    saved = {name: 0x77770000 + index for index, name in
             enumerate(('RBX', 'RBP', 'RSI', 'RDI', 'R12', 'R13', 'R14', 'R15'))}

    def native_tail(entity_type: int, actor_index: int) -> int:
        engine.mem_write(entity, struct.pack('<I', entity_id))
        engine.mem_write(entity + 0x1A0, struct.pack('<H', entity_type))
        engine.mem_write(entity + 0x58, struct.pack('<I', actor_index))
        engine.mem_write(entity + 0x270, struct.pack('<Q', vehicle))
        rsp = stack + 0x1F000
        engine.mem_write(rsp, struct.pack('<QQ', saved['RBP'], stop))
        engine.reg_write(registers.UC_X86_REG_RSP, rsp)
        for name, value in saved.items():
            engine.reg_write(getattr(registers, 'UC_X86_REG_' + name), value)
        engine.reg_write(registers.UC_X86_REG_RBP, binding)
        engine.reg_write(registers.UC_X86_REG_R9, entity_id)
        engine.emu_start(code.base + 0x15C507C, stop, count=1000)
        assert engine.reg_read(registers.UC_X86_REG_RSP) == rsp + 16
        assert all(engine.reg_read(getattr(registers, 'UC_X86_REG_' + name)) == value
                   for name, value in saved.items())
        assert bytes(engine.mem_read(old_bank, COUNT * STRIDE)) == old_before
        assert bytes(engine.mem_read(new_bank, COUNT * STRIDE)) == new_before
        assert all(bytes(engine.mem_read(address, 16)) == value for address, value in canaries.items())
        return engine.reg_read(registers.UC_X86_REG_RAX)

    artifact = output / 'owned-secondary-bank.bin'
    artifact.write_bytes(new_before)
    source_paths = (Path(__file__), PATCHES / 'runtime_recipe.py', PATCHES / 'storage_plan.py',
                    PATCHES / 'consumer_inventory.json', PATCHES / 'captured_code.py')
    report = {
        'passed': False, 'phase': 'RED', 'stockReplay': stock, 'gameWrites': 0,
        'executableSha256': code.executable_sha256,
        'manifestSha256': hashlib.sha256(module.read_bytes()).hexdigest(),
        'sources': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths},
        'guards': [{'rva': hex(guard.rva), 'size': guard.size, 'sha256': guard.sha256}
                   for guard in (SITE, OWNER, METADATA)],
        'selectedRecipeEdits': [{'rva': hex(edit.guard.rva), 'replacement': edit.replacement.hex()}
                                for edit in selected],
        'cases': [], 'refusals': [],
        'artifact': {'path': str(artifact), 'sha256': hashlib.sha256(new_before).hexdigest()},
        'scope': 'Captured native tail 15C507C..15C50C9 with actual recipe source edits. '
                 'The decoded entity-pool pointer and native return stack are authored entry bindings. '
                 'The protected decoder, full owner prologue, callers, physics/model/lifecycle paths, '
                 'and live game are not executed. This is not a complete publication or compatibility test.',
    }
    receipt = output / 'result.json'
    try:
        for index in (0, 63, 64, 299, 499):
            actual = native_tail(18, index)
            expected = new_bank + index * STRIDE + MEMBER
            actual_value = bytes(engine.mem_read(actual, 12))
            expected_value = struct.pack('<III', 0x12340000 + index, 0x33440000 + index, 0x55660000 + index)
            report['cases'].append({'actorIndex': index, 'entityId': entity_id,
                                    'actualPointer': hex(actual), 'expectedPointer': hex(expected),
                                    'actualValue': actual_value.hex(), 'expectedValue': expected_value.hex(),
                                    'allocationCanaries': True, 'stackAndNonvolatile': True})
            assert actual == expected and actual_value == expected_value, 'The getter still returns the old secondary actor member.'
        for entity_type, expected in ((15, vehicle + 0x1C18), (0, 0)):
            assert native_tail(entity_type, 499) == expected
            report['cases'].append({'entityType': entity_type, 'preservedReturn': hex(expected),
                                    'allocationCanaries': True, 'stackAndNonvolatile': True})

        class ChangedCode(CapturedCode):
            def read(self, rva: int, size: int) -> bytes:
                data = bytearray(super().read(rva, size))
                if rva <= self.mutation < rva + size:
                    data[self.mutation - rva] ^= 1
                return bytes(data)

        for guard in (SITE, OWNER, METADATA):
            changed = object.__new__(ChangedCode)
            changed.__dict__.update(code.__dict__)
            changed.mutation = guard.rva
            try:
                changed.guarded(guard)
            except ValueError:
                report['refusals'].append({'rva': hex(guard.rva), 'oracle': 'pinned complete native guard'})
            else:
                raise AssertionError('A changed native source guard escaped refusal.')
        changed.mutation = SITE.rva + 3
        try:
            prepare_recipe(changed, arena)
        except ValueError:
            report['refusals'].append({'rva': hex(changed.mutation), 'oracle': 'complete recipe source admission'})
        else:
            raise AssertionError('A changed member displacement escaped recipe admission.')
        report['passed'] = True
        report['phase'] = 'GREEN'
    except Exception as error:
        report['failure'] = str(error)
        receipt.write_text(json.dumps(report, indent=2) + '\n')
        raise
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    return {'passed': True, 'cases': len(report['cases']), 'refusals': len(report['refusals']),
            'result': str(receipt)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'dependencies', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--stock', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.dependencies, args.output, args.stock)))
