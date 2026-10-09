"""Execute compiled admission guards with captured BO3 handlers in owned memory."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

p = argparse.ArgumentParser()
for name in ('manifest', 'executable', 'dependencies', 'fixture', 'output'):
    p.add_argument('--' + name, type=Path, required=True)
args = p.parse_args()
sys.path.insert(0, str(args.dependencies))
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import *

EXPECTED = '0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0'
with args.executable.open('rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == EXPECTED
output = args.output.resolve()
assert not output.is_relative_to(Path(__file__).resolve().parents[3])
output.mkdir(exist_ok=False)
meta = json.loads(args.manifest.read_text())
base = int(meta['baseAddress'], 0)
image = bytearray(meta['imageSize'])
for part in meta['ranges']:
    data = (args.manifest.parent / part['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == part['sha256']
    start = int(part['moduleOffset'], 0)
    image[start:start + len(data)] = data
pe = pefile.PE(str(args.fixture))
helper = pe.OPTIONAL_HEADER.ImageBase
exports = {s.name.decode(): helper+s.address for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name}
STACK, OWNED, STOP = 0x50000000, 0x52000000, 0x51000000
MSG, PAYLOAD, BUFFER, OBJECT, TIME = OWNED, OWNED+0x1000, 0x60000000, OWNED+0x3000, OWNED+0x3100
HEADER, RECEIVE_CAP, WRITE_STATE = base+0x16dbb644, base+0x16dbb640, base+0x16d7b5f0
TAG, BUDGET = 0xc6000000 | (18 << 20) | 500001, 32*1024*1024
REGISTERS = (UC_X86_REG_RAX, UC_X86_REG_RBX, UC_X86_REG_RCX, UC_X86_REG_RDX,
             UC_X86_REG_RSI, UC_X86_REG_RDI, UC_X86_REG_R8, UC_X86_REG_R9,
             UC_X86_REG_R10, UC_X86_REG_R11, UC_X86_REG_R12, UC_X86_REG_R13,
             UC_X86_REG_R14, UC_X86_REG_R15)

class Replay:
    def __init__(self, native_budget=BUDGET, actual_compressor=False):
        self.u = Uc(UC_ARCH_X86, UC_MODE_64)
        self.events, self.ack, self.outcome = [], b'', None
        self.compressed_result = 0
        self.actual_compressor = actual_compressor
        self.native_budget = native_budget
        self.u.mem_map(helper, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
        self.u.mem_write(helper, pe.get_memory_mapped_image())
        for rva, size in ((0x1361000,0x2000),(0x21f9000,0x2000),(0x20fc000,0x4000),
                          (0x12e000,0x1000),(0xb2000,0x1000),(0x5359000,0x2000),
                          (0x17756000,0x1000),(0x16dbb000,0x1000),(0x16d7b000,0x1000),
                          (0x2f3a000,0x1000),(0x2bc4000,0x2000),(0x2277000,0x1000),
                          (0x19c3000,0x1000),(0x23f4000,0x1000),(0x211a000,0x1000),(0x35ee000,0x1000),
                          (0x2bc3000,0x1000),(0x227b000,0x2000),(0x17cad000,0x1000),(0x2258000,0x1000),
                          (0x20ec000,0x1000),(0x6000,0x2000)):
            self.u.mem_map(base+rva,size)
            self.u.mem_write(base+rva,bytes(image[rva:rva+size]))
        self.u.mem_map(STACK,0x10000); self.u.mem_map(OWNED,0x10000); self.u.mem_map(STOP,0x1000)
        self.u.mem_map(BUFFER,BUDGET)
        self.u.mem_write(RECEIVE_CAP,b'\0'*28)
        self.u.mem_write(base+0x5359bd0+0x1078,struct.pack('<I',1))
        self.u.mem_write(base+0x17756fa8,struct.pack('<I',7))
        self.u.mem_write(base+0x17756be8+7*32,struct.pack('<I',2))
        self.u.mem_write(base+0x17756be0,struct.pack('<I',2))
        bindings = struct.pack('<II7Q',TAG,BUDGET,
            exports['MigrationHeaderReentry'],exports['MigrationDataReentry'],
            exports['MigrationHeaderAckReentry'],exports['MigrationSendHeaderReentry'],
            base+0x1362330,base+0x20fc7d0,base+0x20fc7c0)
        self.u.mem_write(exports['Bo3MigrationBindings'],bindings)
        self.u.mem_write(exports['Bo3MigrationReentries'],struct.pack('<7Q',
            base+0x13619e5,base+0x13617f5,base+0x21f9aa8,base+0x17756fa8,
            base+0x21fa755,base+0x12e1c5,base+0x21f9ac9))
        self.u.mem_write(exports['Bo3MigrationVersionBranches'],struct.pack('<QQ',base+0x12e24a,base+0x12e22b))
        self.u.mem_write(exports['Bo3MigrationLoadBindings'],struct.pack('<QQ',exports['MigrationLoadReentry'],STOP+0x100))
        self.u.mem_write(exports['Bo3MigrationFlushBindings'],struct.pack('<QQ',exports['MigrationFlushReentry'],base+0x2277a66))
        # Near indirect relays retain registers even when the helper is outside REL32 range.
        relay = base+0x30000000
        self.u.mem_map(relay,0x1000)
        for site, target, index in ((0x1361a50,'SendHeaderAck',0),(0x12e226,'MigrationVersionGate',1)):
            address = relay+index*16
            self.u.mem_write(address,b'\xff\x25\0\0\0\0'+struct.pack('<Q',exports[target]))
            opcode = b'\xe8' if index==0 else b'\xe9'
            self.u.mem_write(base+site,opcode+struct.pack('<i',address-(base+site+5)))
        self.u.hook_add(UC_HOOK_CODE,self.callback)
        self.copy_addresses = {base+0x2bc4eb0}
        for line in args.fixture.with_suffix('.map').read_text().splitlines():
            fields = line.split()
            if len(fields)>2 and fields[1] == 'memcpy': self.copy_addresses.add(int(fields[2],16))

    def ret(self, value=0):
        rsp = self.u.reg_read(UC_X86_REG_RSP)
        address, = struct.unpack('<Q',self.u.mem_read(rsp,8))
        self.u.reg_write(UC_X86_REG_RSP,rsp+8)
        self.u.reg_write(UC_X86_REG_RAX,value)
        self.u.reg_write(UC_X86_REG_RIP,address)

    def callback(self,u,address,size,context):
        if address in self.copy_addresses:
            dst,src,count = (u.reg_read(r) for r in (UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8))
            u.mem_write(dst,bytes(u.mem_read(src,count))); self.ret(dst)
        elif address == base+0xb2410: self.ret(self.native_budget)
        elif address == base+0xb23f0: self.ret(BUFFER)
        elif address == base+0x20fc7e0:
            assert u.reg_read(UC_X86_REG_RCX)==BUFFER
            capacity=u.reg_read(UC_X86_REG_RDX)
            u.mem_write(base+0x16dbb638,struct.pack('<QI',BUFFER,capacity))
            self.events.append({'bufferPublished':capacity}); self.ret()
        elif address == base+0x1362330:
            assert u.reg_read(UC_X86_REG_RCX)==1
            ptr,count = u.reg_read(UC_X86_REG_R8),u.reg_read(UC_X86_REG_R9)
            self.ack=bytes(u.mem_read(ptr,count)) if count else b''
            self.events.append({'ackBytes':self.ack.hex()}); self.ret()
        elif address == base+0x2bc3aa0: self.ret(u.reg_read(UC_X86_REG_RAX))
        elif address == base+0x23f4e90:
            self.events.append({'nativeCrcInputBytes':u.reg_read(UC_X86_REG_RDX)})
            self.ret(0x12345678)
        elif address == base+0x20fcb80:
            obj,ptr,count=(u.reg_read(r) for r in (UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8))
            u.mem_write(obj,struct.pack('<iiQQiiii',0,0,ptr,0,count,0,0,0)); self.ret()
        elif address == base+0x211a2d0:
            obj,value=u.reg_read(UC_X86_REG_RCX),u.reg_read(UC_X86_REG_RDX)
            ptr,=struct.unpack('<Q',u.mem_read(obj+8,8))
            u.mem_write(ptr,struct.pack('<I',value)); u.mem_write(obj+0x1c,struct.pack('<I',4)); self.ret()
        elif address == base+0x2bc57a0: self.ret(u.reg_read(UC_X86_REG_RAX))
        elif address == base+0x2bc53b0:
            dst,value,count=(u.reg_read(r) for r in (UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8))
            u.mem_write(dst,bytes([value&255])*count); self.ret(dst)
        elif address == base+0x22587a0 and not self.actual_compressor:
            dst,count=u.reg_read(UC_X86_REG_R8),u.reg_read(UC_X86_REG_R9)&0xffffffff
            self.events.append({'compressorCapacity':count,'compressorResult':self.compressed_result})
            assert self.compressed_result<=count
            if self.compressed_result: u.mem_write(dst,bytes([0x71])*self.compressed_result)
            self.ret(self.compressed_result)
        elif address == base+0x20ec0b0:
            raise AssertionError('Unexpected native overflow error in the owned flush scenario')
        elif address == base+0x21fa9b0:
            self.events.append({'nativeDataStartup':True}); self.ret()
        elif address == base+0x19c32c0: self.ret()
        elif address == base+0x2277630:
            self.events.append({'memFileInitBytes':u.reg_read(UC_X86_REG_RDX)}); self.ret()
        elif address in (base+0x12e24a,base+0x12e22b,STOP+0x100):
            self.outcome={base+0x12e24a:'accepted',base+0x12e22b:'rejected',STOP+0x100:'dropped'}[address]
            u.emu_stop()

    def message(self, payload):
        self.u.mem_write(PAYLOAD,payload or b'\0')
        self.u.mem_write(MSG,struct.pack('<iiQQiiii',0,0,PAYLOAD,0,len(payload),len(payload),0,0))

    def run(self, name, *arguments):
        rsp=STACK+0xff08
        self.u.mem_write(rsp,struct.pack('<Q',STOP))
        self.u.reg_write(UC_X86_REG_RSP,rsp)
        for register,value in zip((UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9),arguments):
            self.u.reg_write(register,value)
        try:
            self.u.emu_start(exports[name],STOP,count=100000)
        except Exception:
            print(json.dumps({'entry':name,'rip':hex(self.u.reg_read(UC_X86_REG_RIP)), 'rsp':hex(self.u.reg_read(UC_X86_REG_RSP)), 'events':self.events}))
            raise
        assert self.u.reg_read(UC_X86_REG_RIP)==STOP or self.outcome

cases=[]
def record(name, replay): cases.append({'name':name,'passed':True,'events':replay.events})

for version, size, expected in ((4,1000,False),(TAG+1,1000,False),(TAG,BUDGET+1,False),(TAG,25000000,True),(3,0x280000,True)):
    r=Replay(); r.message(struct.pack('<6I',size,version,123,0x4864,456,789))
    r.run('ReceiveMigrationHeader',1,OBJECT,MSG)
    assert bool(r.events)==expected
    if expected:
        assert bytes(r.u.mem_read(HEADER,24))==struct.pack('<6I',size,version,123,0x4864,456,789)
        assert r.ack==(struct.pack('<I',TAG) if version==TAG else b'')
        assert struct.unpack('<I',r.u.mem_read(MSG+0x24,4))[0]==24
    else: assert bytes(r.u.mem_read(HEADER,24))==bytes(24)
    record(f'header-{version:x}-{size}',r)

# A stock handler accepts the larger header into a stock-size backing buffer,
# but sends an empty ACK. The compiled enhanced sender must stop before native mdata startup.
r=Replay(0x280000); r.message(struct.pack('<6I',25000000,TAG,123,0x4864,456,789))
r.u.mem_write(base+0x1361a50,bytes(image[0x1361a50:0x1361a55]))
r.run('MigrationHeaderReentry',1,OBJECT,MSG)
assert r.ack==b'' and r.events[0]=={'bufferPublished':0x280000}
r.message(r.ack); r.run('ReceiveMigrationHeaderAck',7,MSG)
assert not any('nativeDataStartup' in e for e in r.events)
record('stock-receiver-empty-ack-blocks-expanded-data',r)

for echo, peer, phase, expected in ((b'',7,2,False),(struct.pack('<I',TAG+1),7,2,False),
                                   (struct.pack('<I',TAG),6,2,False),(struct.pack('<I',TAG),7,1,False),
                                   (struct.pack('<I',TAG),7,2,True)):
    r=Replay(); r.message(echo); r.u.mem_write(base+0x17756be0,struct.pack('<I',phase))
    r.run('ReceiveMigrationHeaderAck',peer,MSG)
    assert any('nativeDataStartup' in e for e in r.events)==expected
    record(f'ack-{echo.hex()}-peer{peer}-phase{phase}',r)

for version,size,outcome in ((3,0x280000,'accepted'),(TAG,25000000,'accepted'),(4,1000,'dropped'),(TAG,BUDGET+1,'dropped')):
    r=Replay(); r.u.mem_write(HEADER,struct.pack('<6I',size,version,123,0x4864,456,789))
    r.run('LoadMigrationState',OBJECT,TIME)
    assert r.outcome==outcome
    assert any('memFileInitBytes' in e for e in r.events)==(outcome=='accepted')
    record(f'load-{version:x}-{size}',r)

for index,length,expected in ((-1,10,False),(0,0,False),(0,1201,False),(27962,33,False),
                              (32767,1200,False),(27962,32,True)):
    r=Replay(); r.u.mem_write(HEADER,struct.pack('<6I',BUDGET,TAG,123,0x4864,456,789))
    r.u.mem_write(base+0x16dbb638,struct.pack('<QI',BUFFER,BUDGET))
    r.message(struct.pack('<hh',index,length)+bytes([0x5a])*length+struct.pack('<I',0x12345678))
    r.run('ReceiveMigrationData',1,OBJECT,MSG)
    assert any('nativeCrcInputBytes' in e for e in r.events)==expected
    assert bool(r.ack)==expected
    if expected:
        assert bytes(r.u.mem_read(BUFFER+index*1200,length))==bytes([0x5a])*length
        assert r.ack==struct.pack('<I',index)
    record(f'data-index{index}-length{length}',r)

for version, expected in ((3,'accepted'),(TAG,'accepted'),(TAG+1,'rejected'),(4,'rejected')):
    r=Replay()
    for i,reg in enumerate(REGISTERS): r.u.reg_write(reg,0x11110000+i)
    r.u.reg_write(UC_X86_REG_RAX,version); r.u.reg_write(UC_X86_REG_RSP,STACK+0x8000)
    before=[r.u.reg_read(reg) for reg in REGISTERS]+[r.u.reg_read(UC_X86_REG_RSP)]
    r.u.emu_start(exports['MigrationVersionGate'],STOP,count=1000)
    assert r.outcome==expected and before==[r.u.reg_read(reg) for reg in REGISTERS]+[r.u.reg_read(UC_X86_REG_RSP)]
    record(f'version-register-preservation-{version:x}',r)

def flush_state(replay, remaining):
    state=bytearray(48)
    struct.pack_into('<QII',state,0,BUFFER,128,128-remaining)
    struct.pack_into('<I',state,0x18,10); state[0x2e]=1
    replay.u.mem_write(WRITE_STATE,bytes(state))
    replay.u.mem_write(BUFFER+128,bytes([0xa5])*16)

# Fail-first replay: even a compressor that writes no bytes leaves the native
# four-byte length prefix crossing the declared boundary when only three remain.
r=Replay(); flush_state(r,3); r.run('MigrationFlushReentry',WRITE_STATE)
assert r.events==[{'compressorCapacity':0xffffffff,'compressorResult':0}]
assert bytes(r.u.mem_read(BUFFER+128,16))!=bytes([0xa5])*16
record('stock-compressed-flush-three-byte-room-overruns-prefix',r)
for remaining,result,expected_calls,overflow in ((0,0,0,1),(1,0,0,1),(2,0,0,1),(3,0,0,1),
                                                (4,0,1,1),(24,20,1,0),(40,20,1,0)):
    r=Replay(); flush_state(r,remaining); r.compressed_result=result
    r.run('FlushMigrationState',WRITE_STATE)
    assert len(r.events)==expected_calls
    assert bytes(r.u.mem_read(BUFFER+128,16))==bytes([0xa5])*16
    assert r.u.mem_read(WRITE_STATE+0x2d,1)[0]==overflow
    assert struct.unpack('<I',r.u.mem_read(WRITE_STATE+0x18,4))[0]==0
    record(f'guarded-compressed-flush-room{remaining}-result{result}',r)

for payload,remaining in ((bytes(120),128),(bytes(120),4),(bytes(range(120)),128),(bytes(range(120)),64)):
    r=Replay(actual_compressor=True); flush_state(r,remaining)
    r.u.mem_write(WRITE_STATE+0x18,struct.pack('<I',len(payload)))
    r.u.mem_write(WRITE_STATE+0x38,payload)
    r.run('FlushMigrationState',WRITE_STATE)
    assert bytes(r.u.mem_read(BUFFER+128,16))==bytes([0xa5])*16
    written,=struct.unpack('<I',r.u.mem_read(WRITE_STATE+0xc,4))
    overflow=r.u.mem_read(WRITE_STATE+0x2d,1)[0]
    assert written<=128 and overflow==(remaining in (4,64))
    prefix,=struct.unpack('<I',r.u.mem_read(BUFFER+128-remaining,4))
    r.events.append({'actualCompressor':True,'literalPayload':bool(payload[1]),'capacityAfterPrefix':remaining-4,'compressedBytes':prefix,'overflow':overflow})
    record(f'actual-compressor-{hashlib.sha256(payload).hexdigest()[:8]}-room{remaining}',r)

receipt={'passed':True,'cases':cases,'executableSha256':EXPECTED,
         'fixtureSha256':hashlib.sha256(args.fixture.read_bytes()).hexdigest(),
         'harnessSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'scope':'Compiled guards and static reentries execute with captured BO3 mhead, mdata, MSG_ReadData/short/long, mhack, compressed flush, compressor and pre-CRC loader instructions. Owned buffer getters/publication, byte copy/fill, stack probe/security-cookie return, CRC callback, ACK encoding/sink, mdata startup, MemFile init and errors. Includes native compressed-prefix overflow baseline, bounded callbacks and four actual-compressor outcomes. No actual game, networking, completed whole-state load or deadline evidence.'}
(output/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'passed':True,'cases':len(cases),'result':str(output/'result.json')}))
