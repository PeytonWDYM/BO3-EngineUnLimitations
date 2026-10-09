"""Independently execute saved setup paths. Publish metadata, never captured code."""
import argparse
import collections
import hashlib
import json
import struct
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--evidence', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--unicorn', type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.unicorn))
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_MEM_UNMAPPED, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.x86_const import *

audit = args.evidence / 'integrity-input-audit-sol-03'
review = args.evidence / 'integrity-semantic-review-sol-01'
image = (audit / 'runtime-image.bin').read_bytes()
assert hashlib.sha256(image).hexdigest() == 'fcc35afd9b9a13d656f1b15a3d0fd5536429aca3dd7457e4f0ed148771f4ce79'
profile = json.loads((audit / 'frozen-site-profile.json').read_text())
states = json.loads((review / 'computed-store-state.json').read_text())['rows']
installer = json.loads((audit / 'captured-aae-installer-proof.json').read_text())
assert hashlib.sha256((audit / 'captured-aae-installer-proof.json').read_bytes()).hexdigest() == '46af4f98eda54d63bfc402e1a106d89ea2a9a6c8797e8e0e8f07c669a46d8633'
prefixes = {p['storeRva']: p for p in installer['prefixes']}
kinds = {e['gameRva']: t['kind'] for t in installer['tables'] for e in t['entries']}
installer_image = (audit / 'captured-aae-image.bin').read_bytes()
assert hashlib.sha256(installer_image).hexdigest() == 'd71c88061bfb1dd05730e2f5ac21483a51286d336935cacb903c35b58b9296dd'
scanner_block = installer['blocks'][0]
assert installer_image[scanner_block['moduleRva']:scanner_block['moduleRva']+scanner_block['size']].hex() == scanner_block['bytes']
scanner_entry, scanner_selected, scanner_failed = 0x116fad, 0x116fe9, 0x117039
mapping = json.loads((review/'setup-endpoint-mapping.json').read_text())
endpoints = {r['setup']['rva']: r['mapping']['endpointRva'] for r in mapping['rows']}
base = int(profile['captureIdentity']['imageBase'], 16)
frame, stack, arena = 0x400000000, 0x500008000, base - 0x10000000
registers = [UC_X86_REG_RAX, UC_X86_REG_RBX, UC_X86_REG_RCX, UC_X86_REG_RDX,
             UC_X86_REG_RBP, UC_X86_REG_RSP, UC_X86_REG_RSI, UC_X86_REG_RDI,
             UC_X86_REG_R8, UC_X86_REG_R9, UC_X86_REG_R10, UC_X86_REG_R11,
             UC_X86_REG_R12, UC_X86_REG_R13, UC_X86_REG_R14, UC_X86_REG_R15, UC_X86_REG_EFLAGS]

def scan(raw):
    """Run the captured AAE first-target search, stopping before wrapper construction."""
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    module_base, source_base = 0x180000000, 0x400000000
    page = scanner_entry & ~4095
    uc.mem_map(module_base+page, 8192)
    uc.mem_write(module_base+page, installer_image[page:page+8192])
    uc.mem_map(source_base, 4096)
    uc.mem_write(source_base, raw)
    uc.reg_write(UC_X86_REG_RDI, source_base)
    reads, trace = [], []
    def read(uc, access, address, size, value, user):
        assert source_base <= address and address+size <= source_base+67, 'Unexpected AAE scan read'
        reads.append((address-source_base, bytes(uc.mem_read(address, size)).hex()))
    def code(uc, address, size, user):
        trace.append(address-module_base)
        if address in (module_base+scanner_selected, module_base+scanner_failed):
            uc.emu_stop()
    uc.hook_add(UC_HOOK_MEM_READ, read)
    uc.hook_add(UC_HOOK_CODE, code)
    uc.emu_start(module_base+scanner_entry, 0, count=1000)
    assert trace[-1] == scanner_selected, 'AAE scanner did not select its first target'
    offset = uc.reg_read(UC_X86_REG_RCX)-source_base
    required = max(at+len(bytes.fromhex(value)) for at, value in reads)
    assert required == offset+10 and required in (19, 20), 'AAE scanner read prefix differs'
    return {'reads': reads, 'trace': trace, 'offset': offset, 'requiredPrefixBytes': required,
            'targetRelativeToStore': uc.reg_read(UC_X86_REG_RDX)-source_base}

def relay(row, at):
    lea_at = at + 9
    return (bytes([0x48, 0x8b, 0x55, row['expectedTableSlot'], 0x8b, 0x02,
                   0x89, 0x45, row['computedLocalSlot'], 0x48, 0x8d, 0x15])
            + struct.pack('<i', base + row['chainDestinationRva'] - (lea_at + 7))
            + b'\xe9' + struct.pack('<i', base + row['leaRva'] + 7 - (at + 21)))

def execute(row, computed, expected, corrected):
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    pages = set()
    def page(address):
        address &= ~4095
        if address in pages:
            return
        uc.mem_map(address, 4096)
        pages.add(address)
        if base <= address < base + len(image):
            uc.mem_write(address, image[address-base:address-base+4096])
    def missing(uc, access, address, size, value, user):
        if not (base <= address < base + len(image)
                or frame-4096 <= address < frame+8192
                or stack-32768 <= address < stack+32768):
            raise RuntimeError(f'Unowned memory at {address:x}')
        page(address)
        page(address+size-1)
        return True
    uc.hook_add(UC_HOOK_MEM_UNMAPPED, missing)
    page(frame)
    page(stack-1024)
    page(stack+1023)
    page(base + row['expectedRva'])
    uc.mem_write(frame + row['computedLocalSlot'], struct.pack('<I', computed))
    uc.mem_write(base + row['expectedRva'], struct.pack('<I', expected))
    for index, reg in enumerate(registers[:-1]):
        uc.reg_write(reg, 0x100000 + index * 0x1000)
    uc.reg_write(UC_X86_REG_RBP, frame)
    uc.reg_write(UC_X86_REG_RSP, stack)
    uc.reg_write(UC_X86_REG_EFLAGS, 0x202)
    pre = None
    trace = []
    continuation = False
    reads = []
    writes = []
    def read(uc, access, address, size, value, user):
        if continuation:
            reads.append((address, bytes(uc.mem_read(address, size)).hex()))
    def write(uc, access, address, size, value, user):
        if continuation:
            writes.append((address, size, value & ((1 << (size*8))-1)))
    uc.hook_add(UC_HOOK_MEM_READ, read)
    uc.hook_add(UC_HOOK_MEM_WRITE, write)
    def code(uc, address, size, user):
        nonlocal pre, continuation
        trace.append((address-base, bytes(uc.mem_read(address, size)).hex()))
        if address == base + row['leaRva']:
            pre = [uc.reg_read(r) for r in registers]
            assert pre[0] == computed and pre[2] == 0 and pre[3] == frame+row['computedLocalSlot']
            assert pre[4] == frame
            assert struct.unpack('<Q', uc.mem_read(frame+row['expectedTableSlot'], 8))[0] == base+row['expectedRva']
            assert struct.unpack('<I', uc.mem_read(frame+row['indexSlot'], 4))[0] == 0
        if address == base + row['leaRva'] + 7:
            continuation = True
        if address == base + row['endpointRva']:
            uc.emu_stop()
    uc.hook_add(UC_HOOK_CODE, code)
    if corrected:
        page(base+row['leaRva'])
        page(base+row['leaRva']+6)
        page(arena)
        uc.mem_write(arena, relay(row, arena))
        uc.mem_write(base+row['leaRva'], b'\xe9'+struct.pack('<i', arena-(base+row['leaRva']+5))+b'\x90\x90')
    uc.emu_start(base+row['setupRva'], 0, count=1024)
    assert pre is not None and trace[-1][0] == row['endpointRva']
    assert struct.unpack('<I', uc.mem_read(base+row['chainDestinationRva'], 4))[0] == expected
    assert struct.unpack('<I', uc.mem_read(frame+row['computedLocalSlot'], 4))[0] == expected
    current_stack = uc.reg_read(UC_X86_REG_RSP)
    return [uc.reg_read(r) for r in registers], bytes(uc.mem_read(frame, 256)), (reads,writes), trace, current_stack

rows, proofs = [], []
for index, state in enumerate(states):
    prefix = prefixes[state['storeRva']]
    row = {k: state[k] for k in ['setupRva', 'storeRva', 'computedLocalSlot', 'computedTableSlot',
                                'expectedTableSlot', 'expectedRva', 'chainDestinationRva', 'indexSlot']}
    row.update(leaRva=prefix['destinationLeaRva'], adjacent=prefix['physicallyAdjacent'], installerKind=kinds[state['storeRva']])
    row['endpointRva'] = endpoints[row['setupRva']]
    reads = [int(t.split()[0], 16) for t in state['trace'] if t.split()[1] == '8b0482']
    assert len(reads) == 1
    row['computedReadRva'] = reads[0]
    assert image[row['leaRva']:row['leaRva']+3] == bytes.fromhex('488d15')
    assert row['leaRva']+7+struct.unpack_from('<i', image, row['leaRva']+3)[0] == row['chainDestinationRva']
    assert image[row['storeRva']:row['storeRva']+3] == bytes.fromhex('89048a')
    assert all(0 <= row[k] < 128 for k in ['computedLocalSlot', 'computedTableSlot', 'expectedTableSlot', 'indexSlot'])
    for expected in [int.from_bytes(image[row['expectedRva']:row['expectedRva']+4], 'little'), 0, 0xffffffff]:
        healthy = execute(row, expected, expected, False)
        fixed = execute(row, expected ^ 0xa5a55a5a, expected, True)
        assert healthy[:3] == fixed[:3], (index, hex(row['leaRva']), 'machine or frame mismatch')
    proofs.append({'leaRva': row['leaRva'], 'storeRva': row['storeRva'], 'scenarios': 3,
                   'allRegistersFlagsRspFrameAndContinuationReadsWritesMatchHealthy': True,
                   'transportInstructions': len(healthy[3])})
    rows.append(row)
assert len(rows) == len({r['leaRva'] for r in rows}) == 1069
assert sum(r['adjacent'] for r in rows) == 998

# Preserve all 67 potential scan bytes against patch overlap. Hash only the bytes
# actually read through the first selected target; later transport has its own guards.
scan_proofs = []
for row in rows:
    scan_end = row['storeRva'] + (67 if row['installerKind'] == 'split' else 7)
    assert not any(r['leaRva'] < scan_end and row['storeRva'] < r['leaRva']+7 for r in rows)
    if row['installerKind']=='split':
        raw = image[row['storeRva']:row['storeRva']+67]
        proof = scan(raw)
        count = proof['requiredPrefixBytes']
        for fill in (0, 0xff, 0xa5):
            assert scan(raw[:count]+bytes([fill])*(67-count)) == proof, 'AAE scanner consumed an unguarded tail'
        row['installerScanBytes'] = count
        target = row['storeRva']+proof['targetRelativeToStore']
        mapped=next(r['mapping']['trace'] for r in mapping['rows'] if r['setup']['rva']==row['setupRva'])
        assert target in {int(line.split()[0],16) for line in mapped}, 'AAE split target leaves the verified continuation'
        scan_proofs.append({'storeRva': row['storeRva'], 'targetRva': target, 'scanner': proof,
                            'tailMutationScenarios': 3})
assert len(scan_proofs) == 69
for row in rows:
    assert not any(row['leaRva']<site['rva']+site['size'] and site['rva']<row['leaRva']+7
                   for site in profile['sites']), 'A source hook overlaps an original evaluator'

expected_rvas = {r['expectedRva'] for r in rows}
guards = {}
private_guards = {}
def add_guard(rva, raw, fields=(), kind='code'):
    masked = bytearray(raw)
    pointers = []
    for field in fields:
        off, target = field['offset'], field['targetRva']
        assert struct.unpack_from('<Q', raw, off)[0] == base+target
        masked[off:off+8] = bytes(8)
        pointers.append({'offset': off, 'targetRva': target})
    key = (rva, len(raw))
    guard = {'rva': rva, 'size': len(raw), 'sha256': hashlib.sha256(masked).hexdigest(),
             'pointers': pointers, 'kind': kind}
    if key in guards:
        assert guards[key] == guard or {k:v for k,v in guards[key].items() if k!='kind'} == {k:v for k,v in guard.items() if k!='kind'}
    else:
        guards[key] = guard
        private_guards[key] = {'rva': rva, 'bytes': raw.hex(), 'pointers': pointers}
setup_guards = json.loads((review / 'input-setup-path-guards.json').read_text())
for g in setup_guards['guards']:
    if g['kind'] == 'constantWord' and g['rva'] in expected_rvas:
        continue
    add_guard(g['rva'], bytes.fromhex(g['capturedBytes']), g['imageAddressFields'], g['kind'])
for site in profile['sites']:
    g=site['guard']
    add_guard(site['rva'], bytes.fromhex(g['capturedBytes']), g['imageAddressFields'])
    prefix=site['typedSourcePrefix']
    if prefix:
        add_guard(prefix['rva'], bytes.fromhex(prefix['bytes']))
eq = json.loads((review/'equality-path-guards.json').read_text())
for rec in eq['records']:
    for g in rec['equalityPathGuards']:
        add_guard(g['rva'], bytes.fromhex(g['capturedBytes']), g['imageAddressFields'])
for row in rows:
    add_guard(row['computedReadRva'], image[row['computedReadRva']:row['computedReadRva']+3])
    add_guard(row['leaRva'], image[row['leaRva']:row['leaRva']+7])
    size = row['installerScanBytes'] if row['installerKind']=='split' else 7
    add_guard(row['storeRva'], image[row['storeRva']:row['storeRva']+size])

# Every executed transport instruction retains admission independent of the scan prefix.
for row in rows:
    if row['installerKind'] != 'split':
        continue
    mapped = next(r['mapping']['trace'] for r in mapping['rows'] if r['setup']['rva']==row['setupRva'])
    for line in mapped:
        at, raw = int(line.split()[0], 16), bytes.fromhex(line.split()[1])
        if at < row['storeRva']+67 and row['storeRva'] < at+len(raw):
            assert any(start <= at and at+len(raw) <= start+size
                       and (start, size) != (row['storeRva'], row['installerScanBytes'])
                       for start, size in guards), 'Executed AAE transport lost independent admission'

result = {'schema': 1, 'executableSha256': profile['executableSha256'], 'timestamp': profile['timestamp'],
          'imageSize': len(image), 'siteCount': 1069, 'relayStride': 32, 'arenaSize': 36864,
          'publicationCount': 1079, 'regions': [{k:r[k] for k in ['rva','size']} for r in profile['regions']],
          'sites': sorted(rows,key=lambda r:r['leaRva']), 'guards': sorted(guards.values(), key=lambda g:(g['rva'],g['size']))}
args.output.mkdir(exist_ok=True)
public_bytes=(json.dumps(result,indent=2)+'\n').encode()
(args.output/'exact_build_profile.json').write_bytes(public_bytes)
(args.output/'private-guards.json').write_text(json.dumps(list(private_guards.values()))+'\n')
(args.output/'scan-input-proof.json').write_text(json.dumps({'passed': True, 'splitSites': 69,
    'scenarios': 276, 'scope': 'Captured AAE first-target scanner emulator. No game execution.',
    'scannerEntryModuleRva': scanner_entry, 'scannerSelectedModuleRva': scanner_selected,
    'fullOverlapExclusionBytes': 67, 'executedTransportIndependentlyGuarded': True,
    'proofs': scan_proofs}, indent=2)+'\n')
(args.output/'flow-proof.json').write_text(json.dumps({'passed':True,'sites':1069,'transported':71,
    'scenarios':3207,'scope':'Independent Unicorn execution of exact saved setup instructions. No game execution.',
    'profileSha256':hashlib.sha256(public_bytes).hexdigest(),'proofs':proofs},indent=2)+'\n')
print(json.dumps({'passed':True,'sites':1069,'transported':71,'scenarios':3207,'guardCount':len(guards),
                  'profileSha256':hashlib.sha256(public_bytes).hexdigest()}))
