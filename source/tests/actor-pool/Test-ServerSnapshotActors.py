"""Replay native server actor snapshot allocation, production, wrap and teardown."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode


def run(module, executable, dependencies, output, candidate):
    sys.path.insert(0, str(dependencies))
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_MEM, CS_OP_IMM
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    import unicorn.x86_const as x
    output = output.resolve()
    if output.exists() or (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents:
        raise ValueError('Use a new private BO3 lab result directory.')
    output.mkdir(parents=True)
    code = CapturedCode(module, executable)
    base = code.base
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    bodies = ((0x21F4510, 910), (0x21F4DC0, 548), (0x2200960, 1176),
              (0x19AEE40, 25), (0x2200390, 1481), (0x2201640, 4028))
    stub = base + 0x20000000
    edits = ()
    if candidate:
        from server_snapshot_actors import prepare_server_snapshot_actors
        from shape import ActorShape
        edits = prepare_server_snapshot_actors(code, ActorShape(500), stub)
    pages = set()
    calls = set()
    for rva, size in bodies:
        for instruction in decoder.disasm(code.read(rva, size), base + rva):
            for operand in instruction.operands:
                if operand.type == CS_OP_MEM and instruction.reg_name(operand.mem.base) == 'rip':
                    pages.add((instruction.address + instruction.size + operand.mem.disp) & ~4095)
            if instruction.mnemonic == 'call' and instruction.operands[0].type == CS_OP_IMM:
                calls.add(instruction.operands[0].imm)

    class Machine:
        def __init__(self, clients, short_history):
            self.u = Uc(UC_ARCH_X86, UC_MODE_64)
            self.mapped = set()
            self.allocations = []
            self.frees = []
            self.clients = clients
            self.short_history = short_history
            self.actor = 0x10000000
            self.zero = 0x11000000
            self.stack = 0x12000000
            self.stop = 0x13000000
            for address, size in ((self.actor, 500 * 0x2110 + 4096), (self.zero, 4096),
                                  (self.stack, 0x20000), (self.stop, 4096), (stub, 4096)):
                self.map(address, size)
            for page in pages:
                self.map(page, 4096)
            for rva, size in bodies:
                self.map(base + rva, size)
                self.u.mem_write(base + rva, code.read(rva, size))
            for edit in edits:
                self.u.mem_write(base + edit.guard.rva, edit.replacement)
                if edit.stub:
                    self.map(edit.stub_address, len(edit.stub))
                    self.u.mem_write(edit.stub_address, edit.stub)
            for address in calls:
                if address == base + 0x19AEE40:
                    continue
                self.map(address, 1)
                self.u.mem_write(address, b'\xc3')
                self.u.hook_add(UC_HOOK_CODE, self.endpoint, begin=address, end=address)
            self.call(0x21F4510, (self.zero, clients))
            self.capacity = self.number(base + 0x1767A3C8, 'I')
            self.ring = self.number(base + 0x1767A408, 'Q')
            self.current_capacity = self.number(base + 0x1767A3B0, 'I')
            self.current = self.number(base + 0x1767A460, 'Q')
            self.put(base + 0xA1B0798, 'Q', self.actor)
            self.put(base + 0x1768E598, 'Q', self.actor)
            # Empty unrelated special/player state does not replace the actor getter.
            self.records = {}

        def map(self, address, size):
            needed = [page for page in range(address & ~4095, (address + size + 4095) & ~4095, 4096)
                      if page not in self.mapped]
            if not needed:
                return
            start = previous = needed[0]
            for page in needed[1:]:
                if page != previous + 4096:
                    self.u.mem_map(start, previous + 4096 - start)
                    start = page
                previous = page
            self.u.mem_map(start, previous + 4096 - start)
            self.mapped.update(needed)

        def number(self, address, fmt):
            return struct.unpack('<' + fmt, self.u.mem_read(address, struct.calcsize('<' + fmt)))[0]

        def put(self, address, fmt, value):
            self.u.mem_write(address, struct.pack('<' + fmt, value))

        def endpoint(self, u, address, size, unused):
            r = lambda name: u.reg_read(getattr(x, 'UC_X86_REG_' + name))
            rsp = r('RSP')
            return_pc = self.number(rsp, 'Q')
            result = 0
            if address == base + 0x20EB290:
                result = int(self.short_history)
            elif address == base + 0x22773A0:
                length = r('RDX')
                if length > 0x4000000:
                    raise AssertionError(f'Invalid native allocation request {length:#x}')
                result = 0x40000000 + len(self.allocations) * 0x2000000
                self.map(result - 4096, length + 8192)
                self.u.mem_write(result - 16, b'\xa5' * 16)
                self.u.mem_write(result + length, b'\xa5' * 16)
                self.allocations.append({'address': result, 'bytes': length, 'returnRva': hex(return_pc - base)})
            elif address == base + 0x2BC53B0:
                u.mem_write(r('RCX'), bytes([r('RDX') & 255]) * r('R8'))
                result = r('RCX')
            elif address == base + 0x2BC4EB0:
                u.mem_write(r('RCX'), bytes(r('R8')))
                result = r('RCX')
            elif address in (base + 0x19CA460, base + 0x19CA4D0, base + 0x19CA430, base + 0x19B0990):
                result = self.zero
            elif address == base + 0x22774E0:
                self.frees.append(r('RDX'))
            elif address not in (base + 0x21FFBA0, base + 0x20EC0B0, base + 0x23F8200, base + 0x20C4F70):
                raise AssertionError(f'Unowned helper endpoint {address - base:#x}')
            u.reg_write(x.UC_X86_REG_RAX, result)
            u.reg_write(x.UC_X86_REG_RSP, rsp + 8)
            u.reg_write(x.UC_X86_REG_RIP, return_pc)

        def call(self, rva, arguments=()):
            sp = self.stack + 0x1F008
            self.u.mem_write(sp, struct.pack('<Q', self.stop) + bytes(0x100))
            self.u.reg_write(x.UC_X86_REG_RSP, sp)
            for name, value in zip(('RCX', 'RDX', 'R8', 'R9'), arguments):
                self.u.reg_write(getattr(x, 'UC_X86_REG_' + name), value)
            self.u.emu_start(base + rva, self.stop, count=2000000)
            assert self.u.reg_read(x.UC_X86_REG_RIP) == self.stop
            assert self.u.reg_read(x.UC_X86_REG_RSP) == sp + 8

        def actors(self, ids):
            self.u.mem_write(self.actor, bytes(500 * 0x2110))
            self.records = {}
            for index in ids:
                record = bytearray(((index + offset) & 255) for offset in range(80))
                struct.pack_into('<II', record, 0, index, (index * 7 + 184) % 1022)
                self.put(self.actor + index * 0x2110, 'I', 1)
                self.u.mem_write(self.actor + index * 0x2110 + 0x78, bytes(record))
                self.records[index] = bytes(record)

        def produce(self, start):
            self.put(base + 0x1767A3E0, 'I', start)
            slot = self.number(base + 0x1767A378, 'I')
            self.call(0x2200960, (1234,))
            header = base + 0x176797B8 + slot * 0xB8
            count = self.number(header + 0x98, 'I')
            actual = [bytes(self.u.mem_read(self.ring + ((start + i) % self.capacity) * 80, 80)) for i in range(count)]
            expected = [self.records[i] for i in sorted(self.records) if candidate or i < 64]
            assert actual == expected
            assert self.number(base + 0x1767A3E0, 'I') == start + count
            for allocation in self.allocations:
                assert bytes(self.u.mem_read(allocation['address'] - 16, 16)) == b'\xa5' * 16
                assert bytes(self.u.mem_read(allocation['address'] + allocation['bytes'], 16)) == b'\xa5' * 16
            return count

        def copy_worker_actors(self, wrong_modulo=False):
            ids = list(self.records)
            source_start = self.current_capacity - 3
            target_start = self.capacity - 5
            for ordinal, index in enumerate(ids):
                self.u.mem_write(self.current + ((source_start + ordinal) % self.current_capacity) * 80,
                                 self.records[index])
            descriptor = self.zero + 0x400
            self.put(descriptor + 0x14, 'I', len(ids))
            self.put(descriptor + 0x20, 'I', source_start)
            self.put(base + 0x17679780, 'I', self.clients)
            self.put(base + 0x1767A3E0, 'I', target_start)
            self.u.reg_write(x.UC_X86_REG_RDI, descriptor)
            self.u.reg_write(x.UC_X86_REG_R15, 0)
            if wrong_modulo:
                self.u.mem_write(base + 0x220069F, bytes.fromhex('c1e106'))
            self.u.emu_start(base + 0x2200670, base + 0x220077B, count=100000)
            actual = [bytes(self.u.mem_read(self.ring + ((target_start + i) % self.capacity) * 80, 80))
                      for i in range(len(ids))]
            expected = [self.records[i] for i in ids]
            if wrong_modulo:
                assert actual != expected
                self.u.mem_write(base + 0x220069F, bytes.fromhex('c1e109'))
            else:
                assert actual == expected
            assert self.u.reg_read(x.UC_X86_REG_R15) == len(ids)

        def shutdown(self):
            self.call(0x21F4DC0, (self.zero,))
            assert self.ring in self.frees and self.current in self.frees
            assert self.number(base + 0x1767A408, 'Q') == 0
            assert self.number(base + 0x1767A460, 'Q') == 0

    cases = []
    final = None
    for clients in (1, 2, 4, 18):
        for short in (False, True):
            print(f'Native server snapshot: clients={clients}, shortHistory={short}', flush=True)
            machine = Machine(clients, short)
            frames = 8 if short else 16
            rows = 512 if candidate else 64
            assert machine.capacity == frames * clients * rows
            assert machine.current_capacity == clients * rows
            machine.actors(range(500))
            count = machine.produce(machine.capacity - 3)
            assert count == (500 if candidate else 64)
            if candidate:
                machine.copy_worker_actors(wrong_modulo=True)
                machine.copy_worker_actors()
            machine.actors((0, 63, 64, 127, 128, 255, 256, 383, 499))
            sparse = machine.produce(11)
            assert sparse == (9 if candidate else 2)
            cases.append({'clients': clients, 'historyFrames': frames, 'capacity': machine.capacity,
                          'currentCapacity': machine.current_capacity, 'allActors': count, 'sparseActors': sparse})
            final = machine
    artifact = output / 'final-server-ring.bin'
    artifact.write_bytes(bytes(final.u.mem_read(final.ring, final.capacity * 80)))
    final.shutdown()
    report = {'passed': True, 'candidate': candidate, 'cases': cases,
              'identity': {'executableSha256': code.executable_sha256,
                           'manifestSha256': hashlib.sha256(module.read_bytes()).hexdigest()},
              'artifact': {'path': str(artifact), 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()},
              'authoredEndpoints': ['native allocation/free transport', 'native history-mode predicate',
                                   'memset/zero-fill', 'empty unrelated player/special state', 'diagnostics',
                                   'empty worker barrier',
                                   'physics allocation sizing, verified by its separate native fixture'],
              'scope': 'Complete native allocation provider, snapshot producer and teardown with actual native actor getter. Native worker actor-copy block includes all record payload writes. No game or peer proof.'}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return {'passed': True, 'candidate': candidate, 'cases': len(cases), 'report': str(output / 'report.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'dependencies', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--candidate', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.dependencies, args.output, args.candidate)))
