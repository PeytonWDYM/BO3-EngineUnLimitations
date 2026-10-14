"""Replay native callback producers, dispatch, and resets against the complete expanded backing."""
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
from pending_callbacks import prepare, CAPACITY, STORAGE_BYTES


def run(module: Path, executable: Path, dependencies: Path, output: Path) -> dict:
    sys.path.insert(0,str(dependencies))
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
    import unicorn.x86_const as x64
    output = output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab result file.')
    code = CapturedCode(module,executable)
    pool, stack, tib, tls_array, tls_block = code.base+0x30000000,0x50000000,0x51000000,0x51100000,0x51200000
    context,schema,field,stop = 0x51300000,0x51400000,0x51500000,0x51600000
    edits = prepare(code,pool)
    inventory = json.loads((SOURCE/'patches/clientfields/pending_inventory.json').read_text())
    cases = []

    def machine(omit: str | None = None):
        uc = Uc(UC_ARCH_X86,UC_MODE_64)
        fragments = [(code.base+row['rva'],code.read(row['rva'],row['size'])) for row in inventory['guards']]
        fragments += [(code.base+edit.guard.rva,edit.replacement) for edit in edits if omit is None or f'-{omit}-' not in edit.name]
        callback_addresses = [stop+0x100+index*16 for index in range(8)]
        regions = [(pool,STORAGE_BYTES+16),(stack,0x20000),(tib,4096),(tls_array,4096),(tls_block,4096),
                   (context,0x3D000),(schema,0x39000),(field,4096),(stop,4096),(code.base+0x1A8258E0,4),
                   (code.base+0x4992590,8),(code.base+0x49925A0,0x20008),
                   (code.base+0x2BC53B0,1),(code.base+0x12D7180,1),
                   (code.base+0x20EC0B0,1),(code.base+0x20F0B60,1)]
        pages = set()
        for address,size in regions+[(address,len(raw)) for address,raw in fragments]:
            pages.update(range(address&~4095,(address+size+4095)&~4095,4096))
        for page in sorted(pages): uc.mem_map(page,4096)
        for address,raw in fragments: uc.mem_write(address,raw)
        for address in callback_addresses+[code.base+rva for rva in (0x2BC53B0,0x12D7180,0x20EC0B0,0x20F0B60)]:
            uc.mem_write(address,b'\xc3')
        uc.mem_write(tib+0x58,struct.pack('<Q',tls_array))
        uc.mem_write(tls_array,struct.pack('<Q',tls_block))
        uc.mem_write(tls_block+0x2F8,struct.pack('<Q',context))
        uc.mem_write(context+8,struct.pack('<Q',schema))
        uc.mem_write(schema+0x38160,struct.pack('<Q',pool))
        for index,offset in enumerate((0x3CC48,0x3CC50,0x3CC58,0x3CC60,0x3CC68,0x3CC70)):
            uc.mem_write(context+offset,struct.pack('<Q',callback_addresses[index]))
        uc.mem_write(field,struct.pack('<Q',0x1122334455667788))
        uc.mem_write(pool,b'\xa5'*STORAGE_BYTES+b'\xcc'*16)
        uc.mem_write(pool+CAPACITY*64,b'\0'*8)
        uc.reg_write(x64.UC_X86_REG_GS_BASE,tib)
        return uc,callback_addresses

    def call(uc,entry: int,bank: int,kind: str):
        rsp = stack+0x1E008
        uc.mem_write(rsp,struct.pack('<Q',stop))
        uc.mem_write(rsp+0x28,struct.pack('<I',0x41200000 if kind=='float' else 98765))
        for offset,value in zip((0x30,0x38,0x40,0x48),(1,0,1,1)):
            uc.mem_write(rsp+offset,struct.pack('<Q',value))
        for register,value in ((x64.UC_X86_REG_RSP,rsp),(x64.UC_X86_REG_RCX,bank),(x64.UC_X86_REG_RDX,771),
                               (x64.UC_X86_REG_R8,field),(x64.UC_X86_REG_R9,12345),(x64.UC_X86_REG_XMM3,0x40A00000)):
            uc.reg_write(register,value)
        uc.emu_start(code.base+entry,stop,count=CAPACITY*256)
        assert uc.reg_read(x64.UC_X86_REG_RIP)==stop

    for kind,entry in (('integer',0x132EF0),('float',0x132FF0)):
        for bank in (0,1):
            for index in (0,2047,2048,8191):
                uc,_ = machine()
                uc.mem_write(pool+CAPACITY*64+bank*4,struct.pack('<I',index))
                call(uc,entry,bank,kind)
                destination=pool+(bank*CAPACITY+index)*32
                old,new=(0x40A00000,0x41200000) if kind=='float' else (12345,98765)
                expected=struct.pack('<Q6I',field,old,new,bank,771,0xA5A5A5AE,0xA5A5A5A5)
                assert bytes(uc.mem_read(destination,32))==expected
                assert struct.unpack('<I',uc.mem_read(pool+CAPACITY*64+bank*4,4))[0]==index+1
                assert bytes(uc.mem_read(pool+CAPACITY*64+8,16))==b'\xcc'*16
                assert struct.unpack('<I',uc.mem_read(pool+CAPACITY*64+(1-bank)*4,4))[0]==0
                cases.append({'kind':kind,'bank':bank,'index':index,'recordAndCountsMatch':True})
            uc,_=machine()
            for index in range(CAPACITY):
                uc.mem_write(pool+(bank*CAPACITY+index)*32,struct.pack('<Q6I',field,index,index+1,bank,771,0,0))
            uc.mem_write(pool+CAPACITY*64+bank*4,struct.pack('<I',CAPACITY))
            before=bytes(uc.mem_read(pool,STORAGE_BYTES+16));errors=[]
            def refuse(engine,address,size,unused):
                if address==code.base+0x20EC0B0:
                    errors.append(address);engine.reg_write(x64.UC_X86_REG_RIP,stop);engine.emu_stop()
                elif address==code.base+0x12D7180: engine.reg_write(x64.UC_X86_REG_RAX,stop)
            uc.hook_add(UC_HOOK_CODE,refuse)
            call(uc,entry,bank,kind)
            assert errors and bytes(uc.mem_read(pool,STORAGE_BYTES+16))==before
            cases.append({'kind':kind,'bank':bank,'overflowRefused':True})

    for bank in (0,1):
        uc,callbacks=machine()
        for index in range(CAPACITY):
            uc.mem_write(pool+(bank*CAPACITY+index)*32,struct.pack('<Q6I',field,index,index+1,bank,771,0,0))
        uc.mem_write(pool+CAPACITY*64+bank*4,struct.pack('<I',CAPACITY))
        uc.mem_write(pool+CAPACITY*64+(1-bank)*4,struct.pack('<I',17))
        other=bytes(uc.mem_read(pool+(1-bank)*CAPACITY*32,CAPACITY*32))
        notified=[]
        def record(engine,address,size,unused):
            if address==callbacks[4]:
                notified.append((engine.reg_read(x64.UC_X86_REG_RDI)-pool)//32-bank*CAPACITY)
            elif address==code.base+0x12D7180: engine.reg_write(x64.UC_X86_REG_RAX,stop)
        uc.hook_add(UC_HOOK_CODE,record)
        call(uc,0x133790,bank,'integer')
        assert notified==list(range(CAPACITY))
        assert struct.unpack('<I',uc.mem_read(pool+CAPACITY*64+bank*4,4))[0]==0
        assert struct.unpack('<I',uc.mem_read(pool+CAPACITY*64+(1-bank)*4,4))[0]==17
        assert bytes(uc.mem_read(pool+(1-bank)*CAPACITY*32,CAPACITY*32))==other
        assert bytes(uc.mem_read(pool+CAPACITY*64+8,16))==b'\xcc'*16
        cases.append({'bank':bank,'nativeDispatchCount':len(notified),'countsReset':True})

    for omit in ('shift','counts'):
        uc,_=machine(omit)
        uc.mem_write(pool+0x20000,b'\0'*8)
        uc.mem_write(pool+CAPACITY*64+4,struct.pack('<I',2048))
        destination=pool+(CAPACITY+2048)*32
        original=bytes(uc.mem_read(destination,32))
        call(uc,0x132EF0,1,'integer')
        assert bytes(uc.mem_read(destination,32))==original
        cases.append({'omittedOperand':omit,'incompleteRecipeDetected':True})

    uc,_=machine()
    uc.emu_start(code.base+0x8F26E3,code.base+0x8F26F1,count=2)
    assert struct.unpack('<Q',uc.mem_read(code.base+0x4992590,8))[0]==pool
    cases.append({'staticBindingRelocated':True})

    uc,_=machine();clears=[]
    def static_clear(engine,address,size,unused):
        if address==code.base+0x2BC53B0:
            assert engine.reg_read(x64.UC_X86_REG_RCX)==pool
            assert engine.reg_read(x64.UC_X86_REG_R8)==STORAGE_BYTES
            assert engine.reg_read(x64.UC_X86_REG_RDX)==0
            engine.mem_write(pool,b'\0'*STORAGE_BYTES);clears.append(STORAGE_BYTES)
    uc.hook_add(UC_HOOK_CODE,static_clear);uc.reg_write(x64.UC_X86_REG_RSP,stack+0x1E008)
    uc.emu_start(code.base+0x8F2DB0,code.base+0x8F2DC4,count=20)
    assert clears==[STORAGE_BYTES] and bytes(uc.mem_read(pool,STORAGE_BYTES))==b'\0'*STORAGE_BYTES
    assert bytes(uc.mem_read(pool+STORAGE_BYTES,16))==b'\xcc'*16
    cases.append({'staticInitializerCompleteClear':True})

    for start,end,register in ((0x134446,0x13446F,'R14'),(0x137149,0x137172,'RDI')):
        uc,_=machine();uc.reg_write(getattr(x64,'UC_X86_REG_'+register),tls_block+0x2F8)
        uc.reg_write(x64.UC_X86_REG_RBX,pool)
        clears=[]
        def clear(engine,address,size,unused):
            if address==code.base+0x2BC53B0:
                address=engine.reg_read(x64.UC_X86_REG_RCX);size=engine.reg_read(x64.UC_X86_REG_R8)
                assert address==pool and size==STORAGE_BYTES and engine.reg_read(x64.UC_X86_REG_RDX)==0
                engine.mem_write(address,b'\0'*size);clears.append(size)
        uc.hook_add(UC_HOOK_CODE,clear)
        uc.reg_write(x64.UC_X86_REG_RSP,stack+0x1E008)
        uc.emu_start(code.base+start,code.base+end,count=100)
        assert clears==[STORAGE_BYTES] and bytes(uc.mem_read(pool,STORAGE_BYTES))==b'\0'*STORAGE_BYTES
        assert bytes(uc.mem_read(pool+STORAGE_BYTES,16))==b'\xcc'*16
        cases.append({'resetRva':hex(start),'completeAllocationCleared':True})
    report={'passed':True,'capacityPerLocalClient':CAPACITY,'storageBytes':STORAGE_BYTES,'cases':cases,
            'scope':'Captured native producers and dispatch. TLS, callbacks, name resolution, error, and memset endpoints are authored. No game or peer execution.',
            'sourceFiles':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in
                           [SOURCE/'patches/clientfields/pending_callbacks.py',SOURCE/'patches/clientfields/pending_inventory.json',Path(__file__)]}}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
    return {'passed':True,'cases':len(cases),'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.module,args.executable,args.dependencies,args.output),indent=2))
