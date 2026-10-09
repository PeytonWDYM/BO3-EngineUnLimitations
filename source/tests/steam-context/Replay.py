"""Read exact SDK bytes; emulate only the bounded fast path with owned callbacks."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--sdk', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--dependencies', type=Path, required=True)
args = parser.parse_args()
assert not args.output.exists()
assert not args.output.resolve().is_relative_to(Path(__file__).resolve().parents[3])
sys.path.insert(0, str(args.dependencies))
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RSP, UC_X86_REG_RIP, UC_X86_REG_RAX, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_RBP, UC_X86_REG_RDI
blob = args.sdk.read_bytes()
digest = hashlib.sha256(blob).hexdigest()
assert digest == '71af8666392acad2080a816b9f1196fe9ccb950e1db8a549f8312c4d231f55a8'
pe = pefile.PE(data=blob)
base = pe.OPTIONAL_HEADER.ImageBase
assert base == 0x3b400000
exports = {row.name.decode(): row.address for row in pe.DIRECTORY_ENTRY_EXPORT.symbols if row.name}
assert exports['SteamAPI_RestartAppIfNecessary'] == 0x7e30
imports = [(module.dll.decode(), entry.address-base) for module in pe.DIRECTORY_ENTRY_IMPORT
           for entry in module.imports if entry.name == b'GetEnvironmentVariableA']
assert len(imports) == 1 and imports[0][1] == 0x1c058
image = pe.get_memory_mapped_image()
assert image[0x1d020:0x1d020+11] == b'SteamAppId\0'
md = Cs(CS_ARCH_X86, CS_MODE_64)
instructions = list(md.disasm(image[0x7e30:0x7e87], base+0x7e30))
by_rva = {row.address-base: row for row in instructions}
expected = {0x7e40: ('call', hex(base+0xa770)), 0x7e4e: ('xor', 'al, al'),
            0x7e66: ('mov', 'r8d, 0x20'), 0x7e6c: ('call', 'qword ptr [rip + 0x141e6]'),
            0x7e72: ('dec', 'eax'), 0x7e74: ('cmp', 'eax, 0x1e'),
            0x7e77: ('ja', hex(base+0x7e87)), 0x7e7e: ('call', hex(base+0xa044)),
            0x7e83: ('test', 'eax, eax'), 0x7e85: ('jne', hex(base+0x7e4e))}
for rva, pair in expected.items():
    assert (by_rva[rva].mnemonic, by_rva[rva].op_str) == pair, (hex(rva), pair)
assert by_rva[0x7e5f].mnemonic == 'lea' and base+0x7e66+0x151ba == base+0x1d020

def replay(label, value, expected_false):
    emulator = Uc(UC_ARCH_X86, UC_MODE_64)
    emulator.mem_map(base, (len(image)+4095) & ~4095)
    emulator.mem_write(base, image)
    stack, callbacks, sentinel = 0x70000000, 0x71000000, 0x72000000
    emulator.mem_map(stack, 0x10000)
    emulator.mem_map(callbacks, 4096)
    emulator.mem_map(sentinel, 4096)
    emulator.mem_write(base+imports[0][1], struct.pack('<Q', callbacks))
    start_rsp = stack+0xfff8
    emulator.mem_write(start_rsp, struct.pack('<Q', sentinel))
    emulator.reg_write(UC_X86_REG_RSP, start_rsp)
    emulator.reg_write(UC_X86_REG_RCX, 311210)
    emulator.reg_write(UC_X86_REG_RBP, 0x1122334455667788)
    emulator.reg_write(UC_X86_REG_RDI, 0x9988776655443322)
    trace = {'label': label, 'inputBytes': len(value), 'envCalls': 0, 'atoiCalls': 0,
             'chkstkCalls': 0, 'nativeFalse': False, 'laterBranchRequired': False}

    def return_owned(result):
        rsp = emulator.reg_read(UC_X86_REG_RSP)
        target = struct.unpack('<Q', emulator.mem_read(rsp, 8))[0]
        emulator.reg_write(UC_X86_REG_RAX, result & 0xffffffff)
        emulator.reg_write(UC_X86_REG_RSP, rsp+8)
        emulator.reg_write(UC_X86_REG_RIP, target)

    def on_code(_, address, size, __):
        if address == base+0xa770:
            trace['chkstkCalls'] += 1
            assert emulator.reg_read(UC_X86_REG_RAX) == 0x2598
            return_owned(0x2598)
        elif address == callbacks:
            trace['envCalls'] += 1
            assert emulator.reg_read(UC_X86_REG_RCX) == base+0x1d020
            assert emulator.reg_read(UC_X86_REG_R8) == 32
            destination = emulator.reg_read(UC_X86_REG_RDX)
            if len(value) < 32:
                emulator.mem_write(destination, value+b'\0')
                return_owned(len(value))
            else:
                return_owned(len(value)+1)
        elif address == base+0xa044:
            trace['atoiCalls'] += 1
            pointer = emulator.reg_read(UC_X86_REG_RCX)
            text = bytes(emulator.mem_read(pointer, 32)).split(b'\0', 1)[0]
            assert text == value
            return_owned(int(text.strip() or b'0'))
        elif address == base+0x7e87:
            trace['laterBranchRequired'] = True
            emulator.emu_stop()
        elif address == sentinel:
            trace['nativeFalse'] = emulator.reg_read(UC_X86_REG_RAX) & 255 == 0
            assert emulator.reg_read(UC_X86_REG_RSP) == start_rsp+8
            assert emulator.reg_read(UC_X86_REG_RBP) == 0x1122334455667788
            assert emulator.reg_read(UC_X86_REG_RDI) == 0x9988776655443322
            emulator.emu_stop()
        else:
            assert base+0x7e30 <= address < base+0x7e87, hex(address)

    emulator.hook_add(UC_HOOK_CODE, on_code)
    emulator.emu_start(base+0x7e30, sentinel+1, count=256)
    assert trace['envCalls'] == trace['chkstkCalls'] == 1
    assert trace['nativeFalse'] == expected_false
    assert trace['laterBranchRequired'] != expected_false
    return trace

positive = [replay('fixed-app-id', b'311210', True), replay('31-byte-upper-bound', b'311210'+b' '*25, True)]
negative = [replay('empty', b'', False), replay('zero', b'0', False), replay('32-byte-overlength', b'3'*32, False)]
assert positive[0]['atoiCalls'] == positive[1]['atoiCalls'] == 1
assert negative[0]['atoiCalls'] == negative[2]['atoiCalls'] == 0 and negative[1]['atoiCalls'] == 1
assert hashlib.sha256(args.sdk.read_bytes()).hexdigest() == digest
report = {'scope': 'Read-only exact installed SDK fast-path replay. Owned environment/atoi/chkstk callbacks; later SDK branch never executes.',
          'sdkSha256': digest, 'preferredBase': hex(base), 'exportRva': '0x7e30',
          'environmentImport': {'module': imports[0][0], 'rva': hex(imports[0][1]), 'name': 'GetEnvironmentVariableA'},
          'fastPath': {'startRva': '0x7e30', 'stopRvaExclusive': '0x7e87', 'sha256': hashlib.sha256(image[0x7e30:0x7e87]).hexdigest(),
                       'instructions': [f'{row.address-base:08x} {row.mnemonic} {row.op_str}' for row in instructions]},
          'groupCount': 2, 'positive': positive, 'negative': negative,
          'realSdkFunctionCalls': 0, 'sdkFileUnchanged': True}
args.output.write_text(json.dumps(report, indent=2))
