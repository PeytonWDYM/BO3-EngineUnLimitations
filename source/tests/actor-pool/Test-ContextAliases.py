"""Replay five context aliases with native TLS providers and distinct owned banks."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode, CodeGuard
from client_actors import ClientActors, ACTOR_BANK_OFFSET, NATIVE_CLIENT_STRIDE
from shape import ActorShape
from runtime_templates import make_template, render_template

INDICES = (0, 63, 64, 68, 499)
CONTEXT = 0x2E78B0
OLD_CLIENT = 0x2F84E0
OLD_SERVER = 0xA1846C0
SERVER_CONTEXT = 0xA173A90
STRIDE = 0xB00
NATIVE_GUARDS = (
    CodeGuard(0x188DF0, 12564, '7fff5f2a4328d7287bf152818e467daabb95857bb7b11f3e1abbdde4a07514a0'),
    CodeGuard(0x4746D0, 18912, '4592b93652e069bd3027c58c4999770ab8a48506bb9b895311c55ee86b41e58e'),
    CodeGuard(0x93E90, 334, 'eaa89ef724f67c5ae3f263b0fc47c7f2ec6d628eee7c41aa1e39b94c09a72c14'),
    CodeGuard(0x1013020, 49612, 'c2f7daa9e6dd65adeb080ded5c21ec8b8efed2625b0a117a86e303bc894d5c8f'),
    CodeGuard(0x8ED490, 24328, '6a067e7a03998c4108abe707c5b7e2d83b73681747d537c2f5d5f7c7081205d8'),
    CodeGuard(0x20F5ED0, 44, '0e99c51446805ed8fa9915efda2dd4b55c2c1a2953e7bfb3030ba65d1282f82a'),
)


def run(module: Path, executable: Path, dependencies: Path, cg_inputs: Path, output: Path, stock: bool) -> dict:
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_MEM_INVALID, UC_HOOK_MEM_WRITE
    import unicorn.x86_const as reg

    output = output.resolve()
    if output.exists() or (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents:
        raise ValueError('Use a new result directory in the private BO3 lab.')
    output.mkdir(parents=True)
    code = CapturedCode(module, executable)
    for guard in NATIVE_GUARDS:
        code.guarded(guard)
    inputs = json.loads(cg_inputs.read_text())
    game, root, peb = (int(inputs[key], 0) for key in ('game', 'root', 'peb'))
    encoded = bytes.fromhex(inputs['encodedRoot'])
    arena = code.base + 0x20000000
    layout = ClientActors(arena + 0x2E00000, arena + 0x2E00000 + ACTOR_BANK_OFFSET, ActorShape(500))
    recipe = SimpleNamespace(arena=arena, arena_bytes=0x3000000)
    templates = {}
    if not stock:
        from context_aliases import prepare_context_aliases, GUARDS
        from runtime_recipe import prepare_recipe
        edits = prepare_context_aliases(code, layout, arena + 0x2400000)
        assert len(edits) == 5 and all(not edit.stub for edit in edits)
        combined = prepare_recipe(code, arena)
        sites = {edit.guard.rva for edit in edits}
        assert tuple(edit for edit in combined.edits if edit.guard.rva in sites) == edits
        selected = tuple(edit for edit in combined.edits
                         if edit.guard.rva in sites or edit.name.startswith('client_actor_member_'))
        for edit in selected:
            templates[edit.guard.rva] = make_template(code, recipe, 'game', edit.guard.rva, edit.replacement,
                context_relative_operands=edit.context_relative_operands)
    saved = {name: 0x77770000 + index for index, name in
             enumerate(('RBX', 'RBP', 'RSI', 'RDI', 'R12', 'R13', 'R14', 'R15'))}

    class Machine:
        """Map only owned fixtures and verified native image pages."""
        def __init__(self, client=0, shift=0, delta=0x24000000):
            self.uc = Uc(UC_ARCH_X86, UC_MODE_64)
            self.game = game + shift
            self.arena = self.game + delta
            self.client = client
            self.cg = root + client * NATIVE_CLIENT_STRIDE
            self.pages = set()
            self.writes = []
            self.stack, self.teb, self.tls, self.thread = (0x20000000, 0x21000000, 0x22000000, 0x23000000)

            def invalid(machine, access, address, size, value, data):
                if self.game <= address < self.game + code.meta['imageSize']:
                    self.image(address)
                    return True
                return False

            def observe(machine, access, address, size, value, data):
                self.writes.append({'address': hex(address), 'size': size,
                                    'rva': hex(machine.reg_read(reg.UC_X86_REG_RIP) - self.game)})

            self.uc.hook_add(UC_HOOK_MEM_INVALID, invalid)
            self.uc.hook_add(UC_HOOK_MEM_WRITE, observe)
            for address, size in ((root, 4 * NATIVE_CLIENT_STRIDE), (self.stack, 0x20000),
                                  (self.teb, 0x1000), (self.tls, 0x1000), (self.thread, 0x1000)):
                self.map(address, size)
            self.put(self.teb + 0x30, self.teb, 8)
            self.put(self.teb + 0x58, self.tls, 8)
            self.put(self.teb + 0x60, peb, 8)
            self.put(self.tls, self.thread, 8)
            self.uc.reg_write(reg.UC_X86_REG_GS_BASE, self.teb)
            self.put(self.game + 0x1A8258E0, 0, 4)
            self.put(self.game + 0x4C98C80, int.from_bytes(encoded, 'little'), 8)
            self.put(self.game + 0x5323720, 2, 4)
            self.put(self.cg + 0x11A8D0, 6, 1)
            self.put(self.cg + 0x11A8B0, 777, 4)
            self.entity = self.cg + 0x125E28
            self.set('RSI', self.cg)
            self.execute(0x8F26BD, 0x8F26C4)
            self.execute(0x8F278A, 0x8F2798)
            self.set('RCX', self.tls)
            self.set('RDX', 0)
            self.execute(0x8F2C5D, 0x8F2C6A)
            assert self.get(self.thread + 0x2F8, 8) == self.cg + CONTEXT
            for rva, template in templates.items():
                self.image(self.game + rva)
                self.write(self.game + rva, render_template(template, code, self.game, self.arena))

        def map(self, address, size):
            pending = [page for page in range(address & ~4095, (address + size + 4095) & ~4095, 4096)
                       if page not in self.pages]
            while pending:
                count = 1
                while count < len(pending) and pending[count] == pending[0] + count * 4096:
                    count += 1
                self.uc.mem_map(pending[0], count * 4096)
                self.pages.update(pending[:count])
                pending = pending[count:]

        def write(self, address, data):
            self.map(address, len(data))
            self.uc.mem_write(address, data)

        def image(self, address):
            page = address & ~4095
            if page not in self.pages:
                self.write(page, code.read(page - self.game, 4096))

        def put(self, address, value, width):
            self.write(address, value.to_bytes(width, 'little'))

        def get(self, address, width):
            return int.from_bytes(self.uc.mem_read(address, width), 'little')

        def set(self, name, value):
            self.uc.reg_write(getattr(reg, 'UC_X86_REG_' + name), value)

        def value(self, name):
            return self.uc.reg_read(getattr(reg, 'UC_X86_REG_' + name))

        def execute(self, begin, end):
            self.uc.emu_start(self.game + begin, self.game + end, count=100000)
            assert self.value('RIP') == self.game + end, (hex(begin), hex(end), hex(self.value('RIP') - self.game))

        def call(self, begin, return_rva, ecx, edx):
            rsp = self.stack + 0x18000
            self.put(rsp, self.game + return_rva, 8)
            for name, value in saved.items():
                self.set(name, value)
            self.set('RSP', rsp)
            self.set('RCX', ecx)
            self.set('RDX', edx)
            self.execute(begin, return_rva)
            assert self.value('RSP') == rsp + 8
            assert all(self.value(name) == value for name, value in saved.items())
            return self.value('RAX')

    report = {'passed': False, 'phase': 'RED' if stock else 'GREEN', 'gameWrites': 0,
              'providerAuthoredEndpoints': 0, 'cases': [], 'refusals': [], 'renderCases': [],
              'scope': 'Complete native client providers and the actor reset through its cache writes. '
                       'Exact native server TLS/write windows and DObj getter. Complete DObj callbacks and live game play are not tested.'}

    def record(kind, client, index, actual, expected, **extra):
        report['cases'].append({'kind': kind, 'client': client, 'index': index,
                                'actual': hex(actual), 'expected': hex(expected), 'matched': actual == expected, **extra})

    for client in (0, 1):
        for index in INDICES:
            m = Machine(client)
            m.put(m.entity + 0x598, 18, 2)
            m.put(m.entity + 0x450, index, 4)
            old = m.cg + OLD_CLIENT + index * STRIDE
            new = m.cg + ACTOR_BANK_OFFSET + index * STRIDE
            state = m.call(0x188DF0, 0x74A270, 777, client)
            record('client-state-provider', client, index, state, new + 0xB8, preservedRegisters=True)
            selected = old if stock else new
            m.put(selected + 0xC0, 1, 4)
            m.write(selected + 0x388, bytes(16))
            cache = m.cg + OLD_CLIENT + 64 * STRIDE + 0x388
            m.write(cache, bytes(8))
            before = bytes(m.uc.mem_read(m.cg + OLD_CLIENT, 65 * STRIDE))
            m.put(m.entity + 0x3E0, 1, 2)
            m.put(m.entity + 0x4B8, 2, 2)
            m.put(m.entity + 0x3F8, 777, 4)
            m.put(m.stack + 0x17000, m.game + 0x10130A7, 8)
            for name, value in (('RSP', m.stack + 0x17000), ('RCX', client), ('RDX', m.entity), ('R8', 1), ('R9', 0)):
                m.set(name, value)
            m.execute(0x1013020, 0x93FB2)
            after = bytes(m.uc.mem_read(m.cg + OLD_CLIENT, 65 * STRIDE))
            cache_value = m.get(cache, 8)
            writer = [w for w in m.writes if w['rva'] == '0x93fac'][-1]
            assert int(writer['address'], 0) == selected + 0x38C
            record('client-cache-write', client, index, int(writer['address'], 0), new + 0x38C,
                   viewmodelCache318=hex(cache_value), oldBankUnchanged=before == after)
            if not stock:
                assert before == after and cache_value == 0
            (output / f'client-{client}-actor-{index}-old-bank.bin').write_bytes(after)
            pointer = m.call(0x4746D0, 0x104F94F, client, 777)
            record('client-record-provider', client, index, pointer, new, preservedRegisters=True)
            for old_value, new_value in ((0, 1), (1, 0)):
                m.put(old + 0xC8, old_value, 8)
                m.put(new + 0xC8, new_value, 8)
                m.set('RSI', m.entity)
                m.set('RBX', index)
                m.set('RCX', m.cg)
                m.execute(0x49B02B, 0x49B068)
                zf = (m.value('EFLAGS') >> 6) & 1
                record('client-state-pointer-read', client, index, zf, int(new_value == 0))

        m = Machine(client)
        m.put(m.entity + 0x598, 0, 2)
        assert m.call(0x188DF0, 0x74A270, 777, client) == 0
        assert m.call(0x4746D0, 0x104F94F, client, 777) == 0
        m.put(m.entity + 0x598, 18, 2)
        m.put(m.entity + 0x450, 64, 4)
        m.put(m.thread + 0x2F8, 0, 8)
        fallback = m.call(0x4746D0, 0x104F94F, client, 777)
        record('client-null-TLS-fallback', client, 64, fallback,
               m.cg + (OLD_CLIENT if stock else ACTOR_BANK_OFFSET) + 64 * STRIDE,
               preservedRegisters=True)

    for shift, delta in ((0, 0x20000000), (0x100000000, 0x24000000), (-0x100000000, 0x28000000)):
        for index in INDICES:
            for assigned in (0, 0x123456789ABC):
                m = Machine(shift=shift, delta=delta)
                old = m.game + OLD_SERVER
                new = m.arena + 0x2400000
                for bank, fill in ((old, 0xCC), (new, 0x5A)):
                    m.write(bank - 16, bytes([0xA5]) * 16 + bytes([fill]) * (500 * STRIDE) + bytes([0xA5]) * 16)
                before = bytes(m.uc.mem_read(old - 16, 500 * STRIDE + 32))
                expected_new = bytearray(m.uc.mem_read(new - 16, 500 * STRIDE + 32))
                struct.pack_into('<Q', expected_new, 16 + index * STRIDE + 0xA88, assigned)
                m.put(m.thread + 0x2F8, m.game + SERVER_CONTEXT, 8)
                m.put(m.entity + 0x58, index, 4)
                for name, value in saved.items():
                    m.set(name, value)
                m.set('RDI', m.entity)
                m.set('R12', assigned)
                m.execute(0x1B6496C, 0x1B6499B)
                actual_bank = old if stock else new
                assert m.get(actual_bank + index * STRIDE + 0xA88, 8) == assigned
                record('server-model-write-1', None, index, actual_bank + index * STRIDE + 0xA88,
                       new + index * STRIDE + 0xA88, assigned=hex(assigned))
                assert all(m.value(name) == (m.entity if name == 'RDI' else assigned if name == 'R12' else value)
                           for name, value in saved.items())
                dobj = m.game + 0x16C759C0 + 42 * 0x128
                m.put(m.game + 0x16D561E0 + 700 * 2, 42, 2)
                m.put(dobj, assigned, 8)
                assert m.call(0x20F5ED0, 0x20F5EFC, 700, 0) == dobj
                for name, value in saved.items():
                    m.set(name, value)
                m.set('RBX', m.entity)
                m.execute(0x24B25A7, 0x24B25DA)
                assert m.get(actual_bank + index * STRIDE + 0xA88, 8) == assigned
                record('server-model-write-2', None, index, actual_bank + index * STRIDE + 0xA88,
                       new + index * STRIDE + 0xA88, assigned=hex(assigned), nativeDObjGetter=True)
                assert all(m.value(name) == (m.entity if name == 'RBX' else value) for name, value in saved.items())
                if not stock:
                    assert before == bytes(m.uc.mem_read(old - 16, 500 * STRIDE + 32))
                    assert bytes(expected_new) == bytes(m.uc.mem_read(new - 16, 500 * STRIDE + 32))
                assert m.get(new - 16, 16) == int.from_bytes(bytes([0xA5]) * 16, 'little')
                assert m.get(new + 500 * STRIDE, 16) == int.from_bytes(bytes([0xA5]) * 16, 'little')

    if not stock:
        from folded_sentients import prepare_folded_sentient_storage
        folded = prepare_folded_sentient_storage(code, arena + 0x400000)
        folded_template = make_template(code, recipe, 'game', folded.guard.rva, folded.replacement,
                                        image_relative_operands=folded.image_relative_operands)
        assert folded_template.relocations[0].image_anchor == 0
        for shift, delta in ((0, 0x20000000), (0x100000000, 0x24000000), (-0x100000000, 0x28000000)):
            actual_game, actual_arena = code.base + shift, code.base + shift + delta
            for rva in (0x1B64993, 0x24B25D2):
                template = templates[rva]
                assert template.relocations[0].target.space == 'arena'
                assert template.relocations[0].target.offset == 0x2400A88
                raw = render_template(template, code, actual_game, actual_arena)
                operand = struct.unpack_from('<i', raw, 4)[0]
                assert actual_game + SERVER_CONTEXT + operand == actual_arena + 0x2400A88
                report['renderCases'].append({'rva': hex(rva), 'game': hex(actual_game),
                                              'arena': hex(actual_arena), 'operand': hex(operand)})
            raw = render_template(folded_template, code, actual_game, actual_arena)
            assert struct.unpack_from('<i', raw, 4)[0] == actual_arena + 0x400000 - 0x3088 - actual_game
            report['renderCases'].append({'kind': 'folded sentient anchor zero',
                                          'game': hex(actual_game), 'arena': hex(actual_arena)})

        template = templates[0x1B64993]
        for anchor in (-1, code.meta['imageSize'], code.meta['imageSize'] + 1):
            try:
                make_template(code, recipe, 'game', 0x1B64993, edits[3].replacement,
                              context_relative_operands=((4, arena + 0x2400A88, anchor),))
            except ValueError:
                report['refusals'].append({'kind': 'bad context anchor during preparation', 'anchor': anchor})
            else:
                raise AssertionError('An invalid image anchor escaped template admission.')
            invalid = replace(template, relocations=(replace(template.relocations[0], image_anchor=anchor),))
            try:
                render_template(invalid, code, code.base, arena)
            except ValueError:
                report['refusals'].append({'kind': 'bad context anchor during rendering', 'anchor': anchor})
            else:
                raise AssertionError('An invalid image anchor escaped actual rendering.')
        try:
            render_template(template, code, code.base, code.base + 0xA0000000)
        except ValueError:
            report['refusals'].append({'kind': 'actual arena displacement overflow'})
        else:
            raise AssertionError('An overflowing actual displacement escaped rendering.')

        class ChangedCode(CapturedCode):
            def read(self, rva, size):
                raw = bytearray(super().read(rva, size))
                if rva <= self.mutation < rva + size:
                    raw[self.mutation - rva] ^= 1
                return bytes(raw)

        changed = object.__new__(ChangedCode)
        changed.__dict__.update(code.__dict__)
        for guard in GUARDS:
            changed.mutation = guard.rva + guard.size // 2
            try:
                prepare_context_aliases(changed, layout, arena + 0x2400000)
            except ValueError:
                report['refusals'].append({'rva': hex(changed.mutation), 'kind': 'changed native guard'})
            else:
                raise AssertionError('A changed context source escaped admission.')
        for field in (0x3162A7C, 0x31CF568):
            changed.mutation = field
            try:
                prepare_context_aliases(changed, layout, arena + 0x2400000)
            except ValueError:
                report['refusals'].append({'rva': hex(field), 'kind': 'complete GS handler data'})
            else:
                raise AssertionError(f'The native GS handler data is unguarded at {field:#x}.')
        changed.mutation = -1
        changed.executable_sha256 = 'unknown'
        try:
            prepare_context_aliases(changed, layout, arena + 0x2400000)
        except ValueError:
            report['refusals'].append({'kind': 'unknown executable'})
        else:
            raise AssertionError('An unknown executable escaped admission.')
        for bank in (0x10000000, code.base + 0x90000000):
            try:
                prepare_context_aliases(code, layout, bank)
            except ValueError:
                report['refusals'].append({'kind': 'unencodable server context displacement'})
            else:
                raise AssertionError('An unencodable context displacement escaped admission.')

    report['passed'] = all(case['matched'] for case in report['cases'])
    report['sources'] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in (Path(__file__), PATCHES / 'runtime_recipe.py')}
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    assert report['passed'], 'Native context aliases still select the old banks. See the RED receipt.'
    return {'passed': True, 'cases': len(report['cases']), 'refusals': len(report['refusals']),
            'renderCases': len(report['renderCases']), 'result': str(output / 'result.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'dependencies', 'cg-inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--stock', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.dependencies, args.cg_inputs, args.output, args.stock)))
