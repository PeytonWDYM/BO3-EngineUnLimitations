"""Replay captured save-buffer allocation and publication in owned memory."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--manifest', type=Path, required=True)
parser.add_argument('--executable', type=Path, required=True)
parser.add_argument('--dependencies', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.dependencies))
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RSP, UC_X86_REG_RIP, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_RAX

EXPECTED = '0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0'
with args.executable.open('rb') as executable:
    if hashlib.file_digest(executable, 'sha256').hexdigest() != EXPECTED:
        raise ValueError('Unsupported executable identity')
output = args.output.resolve()
repo = Path(__file__).resolve().parents[3]
if output.is_relative_to(repo):
    raise ValueError('Keep native replay artifacts outside the repository')
output.mkdir(exist_ok=False)
meta = json.loads(args.manifest.read_text())
base = int(meta['baseAddress'], 0)
image = bytearray(meta['imageSize'])
for part in meta['ranges']:
    raw = (args.manifest.parent / part['file']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != part['sha256']:
        raise ValueError('Exported native range changed')
    start = int(part['moduleOffset'], 0)
    image[start:start + len(raw)] = raw
if hashlib.sha256(image[0xb24c0:0xb2625]).hexdigest() != '6f36668965994c5971dd0cff91d7dc6bb81a8f80a0d402bb09d23aef8e52421e':
    raise ValueError('Native buffer initializer changed')
if image[0xb253f:0xb2544] != bytes.fromhex('bf00002800'):
    raise ValueError('Native server buffer instruction changed')

STACK, STOP, ARENA = 0x50000000, 0x51000000, 0x52000000

def replay(mode, enhanced):
    uc = Uc(UC_ARCH_X86, UC_MODE_64)
    for start, size in ((0xb2000, 4096), (0x20ea000, 4096), (0x2277000, 4096),
                        (0x2bc5000, 4096), (0x3ec4000, 4096), (0x3fc4000, 0x4000)):
        uc.mem_map(base + start, size)
        uc.mem_write(base + start, bytes(image[start:start + size]))
    for address in (STACK, STOP):
        uc.mem_map(address, 0x1000)
    # Initialization starts from owned data, not live save-buffer pointers.
    uc.mem_write(base + 0x3ec4000, bytes(4096))
    uc.mem_write(base + 0x3fc4000, bytes(0x4000))
    if enhanced:
        uc.mem_write(base + 0xb253f, b'\xbf' + struct.pack('<I', 32 * 1024 * 1024))
    requests = []
    def returned(value):
        rsp = uc.reg_read(UC_X86_REG_RSP)
        target = struct.unpack('<Q', uc.mem_read(rsp, 8))[0]
        uc.reg_write(UC_X86_REG_RSP, rsp + 8)
        uc.reg_write(UC_X86_REG_RAX, value)
        uc.reg_write(UC_X86_REG_RIP, target)
    def owned_call(emu, address, size, context):
        rva = address - base
        if rva == 0x20eac70:
            returned(mode)
        elif rva == 0x2bc53b0:
            start = emu.reg_read(UC_X86_REG_RCX)
            count = emu.reg_read(UC_X86_REG_R8)
            assert start == base + 0x3fc4ff0 and count == 0x2448
            emu.mem_write(start, bytes(count))
            returned(start)
        else:
            assert rva == 0x22773a0 and emu.reg_read(UC_X86_REG_RCX) == ARENA
            assert emu.reg_read(UC_X86_REG_R8) == 16
            count = emu.reg_read(UC_X86_REG_RDX)
            pointer = 0x60000000 + len(requests) * 0x4000000 if count else 0
            requests.append({'bytes': count, 'pointer': pointer})
            returned(pointer)
    for rva in (0x20eac70, 0x2bc53b0, 0x22773a0):
        uc.hook_add(UC_HOOK_CODE, owned_call, begin=base+rva, end=base+rva)
    rsp = STACK + 0x808
    uc.mem_write(rsp, struct.pack('<Q', STOP))
    uc.reg_write(UC_X86_REG_RSP, rsp)
    uc.reg_write(UC_X86_REG_RCX, ARENA)
    uc.reg_write(UC_X86_REG_RDX, 0)
    uc.emu_start(base+0xb24c0, STOP, count=10000)
    assert uc.reg_read(UC_X86_REG_RIP) == STOP
    size = 32 * 1024 * 1024 if enhanced else 0x280000
    expected_sizes = [0, 0, size] if mode in (0, 1) else [0x280000, 0x280000, 0x480000, 0x480000] if mode == 2 else []
    assert [request['bytes'] for request in requests] == expected_sizes
    def number(rva, shape):
        return struct.unpack('<'+shape, uc.mem_read(base+rva, struct.calcsize(shape)))[0]
    pointer_fields = [0x3ec4ee8, 0x3ec4ef0, 0x3ec4ed8, 0x3ec4ee0]
    expected_pointers = [request['pointer'] for request in requests] + [0] * (4-len(requests))
    assert [number(field, 'Q') for field in pointer_fields] == expected_pointers
    server_capacity, local_capacity = number(0x3ec4ef8, 'I'), number(0x3ec4efc, 'I')
    assert server_capacity == (size if mode in (0,1) else 0x480000 if mode == 2 else 0)
    assert local_capacity == (0x280000 if mode == 2 else 0)
    return {'mode': mode, 'enhanced': enhanced, 'requests': requests, 'serverCapacity': server_capacity,
            'localCapacity': local_capacity, 'passed': True}

results = [replay(mode, False) for mode in (0, 1, 2, 3)] + [replay(0, True), replay(1, True)]
receipt = {'scope': 'Captured buffer initializer with owned arena allocation, memory clear and mode getter. The 32 MiB instruction affects both modes zero and one. Enhanced launch admits Zombies only. No game, native compression, memory-file transfer, network or peer admission executes.',
           'sourceSha256': EXPECTED, 'manifestSha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
           'harnessSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'cases': results}
(output / 'result.json').write_text(json.dumps(receipt, indent=2)+'\n')
print(json.dumps({'cases': len(results), 'passed': True, 'result': str(output/'result.json')}))
