"""Replay the captured counter allocator, consumer, and reset against owned expanded storage."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SOURCE/'patches/actor_pool'))
sys.path.insert(0,str(SOURCE/'patches/clientfields'))
from captured_code import CapturedCode
from counters import CAPACITY,STORAGE_BYTES,load_inventory,prepare


def run(module: Path,executable: Path,dependencies: Path,output: Path) -> dict:
    sys.path.insert(0,str(dependencies))
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
    import unicorn.x86_const as x64
    output = output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab result file.')
    code = CapturedCode(module,executable)
    pool,stack,field,state,stop = code.base+0x30080010,0x50000000,0x51000000,0x51100000,0x51200000
    tib,tls_array,tls_block,context,schema = 0x51300000,0x51400000,0x51500000,0x51600000,0x51700000
    inventory = load_inventory(SOURCE/'patches/clientfields/counter_inventory.json')
    edits = prepare(code,pool)
    cases = []

    def machine(omit: int | None = None):
        uc = Uc(UC_ARCH_X86,UC_MODE_64)
        fragments = [(code.base+row['rva'],code.read(row['rva'],row['size'])) for row in inventory['guards']]
        fragments += [(code.base+edit.guard.rva,edit.replacement) for edit in edits if edit.guard.rva!=omit]
        regions = [(pool-16,STORAGE_BYTES+32),(stack,0x20000),(field,4096),(state,4096),(stop,4096),
                   (tib,4096),(tls_array,4096),(tls_block,4096),(context,4096),(schema,4096),
                   (code.base+0x1A8258E0,4),(code.base+0x1686E8B0,8),
                   (code.base+0x41C9C30,49152),(code.base+0x2BC53B0,1),(code.base+0x2260A70,1)]
        pages = set()
        for address,size in regions+[(address,len(raw)) for address,raw in fragments]:
            pages.update(range(address&~4095,(address+size+4095)&~4095,4096))
        for page in sorted(pages):uc.mem_map(page,4096)
        for address,raw in fragments:uc.mem_write(address,raw)
        for rva in (0x2BC53B0,0x2260A70):uc.mem_write(code.base+rva,b'\xc3')
        uc.mem_write(pool-16,b'\xcc'*16+b'\0'*STORAGE_BYTES+b'\xdd'*16)
        uc.mem_write(code.base+0x41C9C30,b'\xa5'*49152)
        uc.mem_write(tib+0x58,struct.pack('<Q',tls_array))
        uc.mem_write(tls_array,struct.pack('<Q',tls_block))
        uc.mem_write(tls_block+0x2F8,struct.pack('<Q',context))
        uc.mem_write(context+8,struct.pack('<Q',schema))
        uc.mem_write(schema,struct.pack('<I',1))
        uc.mem_write(field+0x1C,struct.pack('<II',0,0xF0))
        uc.mem_write(field+0x24,b'\x04')
        uc.mem_write(field+0x28,struct.pack('<I',4))
        uc.reg_write(x64.UC_X86_REG_GS_BASE,tib)
        def endpoint(engine,address,size,unused):
            if address==code.base+0x2260A70:engine.reg_write(x64.UC_X86_REG_RAX,0)
            elif address==code.base+0x2BC53B0:
                destination=engine.reg_read(x64.UC_X86_REG_RCX)
                count=engine.reg_read(x64.UC_X86_REG_R8)
                assert destination==pool and engine.reg_read(x64.UC_X86_REG_RDX)==0
                engine.mem_write(destination,b'\0'*count)
                engine.reg_write(x64.UC_X86_REG_RAX,destination)
        uc.hook_add(UC_HOOK_CODE,endpoint)
        return uc

    def call(uc,entry: int,field_pointer: int=field,state_pointer: int=state):
        rsp=stack+0x1E008
        uc.mem_write(rsp,struct.pack('<Q',stop))
        for register,value in ((x64.UC_X86_REG_RSP,rsp),(x64.UC_X86_REG_RCX,field_pointer),
                               (x64.UC_X86_REG_RDX,state_pointer),(x64.UC_X86_REG_R8,state_pointer)):
            uc.reg_write(register,value)
        if entry==0x1342E0:
            uc.reg_write(x64.UC_X86_REG_RCX,0)
            uc.reg_write(x64.UC_X86_REG_RDX,field_pointer)
        uc.emu_start(code.base+entry,stop,count=CAPACITY*32)
        assert uc.reg_read(x64.UC_X86_REG_RIP)==stop
        assert uc.reg_read(x64.UC_X86_REG_RSP)==rsp+8
        assert bytes(uc.mem_read(pool-16,16))==b'\xcc'*16
        assert bytes(uc.mem_read(pool+STORAGE_BYTES,16))==b'\xdd'*16
        assert bytes(uc.mem_read(code.base+0x41C9C30,49152))==b'\xa5'*49152
        return uc.reg_read(x64.UC_X86_REG_RAX)

    def occupy(uc,count: int):
        raw=b''.join(struct.pack('<QQII',field+32+(i%32)*8,state+32+(i//32)*8,3,0xAABBCCDD) for i in range(count))
        uc.mem_write(pool,raw)

    for index in (0,2047,2048,8191):
        uc=machine();occupy(uc,index)
        assert call(uc,0x133CA0)==pool+index*24
        expected=struct.pack('<QQII',field,state,0,0)
        assert bytes(uc.mem_read(pool+index*24,24))==expected
        before=bytes(uc.mem_read(pool,STORAGE_BYTES))
        assert call(uc,0x133CA0)==pool+index*24
        assert bytes(uc.mem_read(pool,STORAGE_BYTES))==before
        cases.append({'index':index,'allocatedAndReused':True})

    uc=machine()
    for fp,sp,index in ((field,state,0),(field,state+4,1),(field+8,state,2)):
        assert call(uc,0x133CA0,fp,sp)==pool+index*24
    cases.append({'distinctPairsRemainSeparate':True})
    uc=machine();occupy(uc,CAPACITY)
    before=bytes(uc.mem_read(pool,STORAGE_BYTES-24))
    assert call(uc,0x133CA0)==pool+STORAGE_BYTES-24
    assert bytes(uc.mem_read(pool,STORAGE_BYTES-24))==before
    assert bytes(uc.mem_read(pool+STORAGE_BYTES-24,20))==struct.pack('<QQI',field,state,0)
    assert bytes(uc.mem_read(pool+STORAGE_BYTES-4,4))==struct.pack('<I',0xAABBCCDD)
    cases.append({'fullTableNativeFallbackWithinLastRecord':True})

    for index in (2048,8191):
        uc=machine();occupy(uc,index)
        uc.mem_write(state,struct.pack('<I',0xABCDEFE5))
        call(uc,0x1342E0)
        assert struct.unpack('<I',uc.mem_read(state,4))[0]==0xABCDEFF5
        assert struct.unpack('<I',uc.mem_read(pool+index*24+16,4))[0]==1
        call(uc,0x1342E0)
        assert struct.unpack('<I',uc.mem_read(state,4))[0]==0xABCDEF05
        uc.mem_write(pool+index*24+16,struct.pack('<I',15))
        before=bytes(uc.mem_read(state,4))
        call(uc,0x1342E0)
        assert bytes(uc.mem_read(state,4))==before
        assert struct.unpack('<I',uc.mem_read(pool+index*24+16,4))[0]==15
        cases.append({'index':index,'nativeConsumerWrapAndLimit':True})

    uc=machine();uc.mem_write(pool,b'\xaa'*STORAGE_BYTES)
    call(uc,0x133560)
    assert bytes(uc.mem_read(pool,STORAGE_BYTES))==b'\0'*STORAGE_BYTES
    cases.append({'completeNativeReset':True})
    uc=machine(0x133569);uc.mem_write(pool,b'\xaa'*STORAGE_BYTES)
    call(uc,0x133560)
    assert bytes(uc.mem_read(pool+49152,STORAGE_BYTES-49152))==b'\xaa'*(STORAGE_BYTES-49152)
    cases.append({'oldClearExtentDetected':True})
    refusals=0
    for bad in (0,pool+1,code.base+0x41C9C30,2**64-16,code.base+2**32):
        try:prepare(code,bad)
        except ValueError:refusals+=1
        else:raise AssertionError('Invalid counter backing was accepted.')
    for guard in inventory['guards']:
        old=code.guarded
        def altered(row):
            if row.rva==guard['rva']:raise ValueError('Authored changed owner guard.')
            return old(row)
        code.guarded=altered
        try:prepare(code,pool)
        except ValueError:refusals+=1
        else:raise AssertionError('Changed counter guard was accepted.')
        finally:code.guarded=old
    paths=[Path(__file__),SOURCE/'patches/clientfields/counters.py',SOURCE/'patches/clientfields/counter_inventory.json']
    result={'passed':True,'capacity':CAPACITY,'storageBytes':STORAGE_BYTES,'cases':cases,'refusals':refusals,
            'scope':'Exact captured native bodies. TLS, dvar lookup, and memset endpoints are authored. No game or peer execution.',
            'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n')
    return {'passed':True,'cases':len(cases),'refusals':refusals,'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.dependencies,args.output),indent=2))
