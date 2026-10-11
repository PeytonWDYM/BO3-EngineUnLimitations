"""Compare guarded native actor packets in owned memory. No game or peer execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES=Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from captured_code import CapturedCode
from shape import ActorShape
from actor_wire import prepare_actor_wire


def run(module: Path,executable: Path,dependencies: Path,output: Path,actors: int) -> dict:
    sys.path.insert(0,str(dependencies))
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
    import unicorn.x86_const as x64
    output=output.resolve()
    packet=output.with_name(output.name+'.packet.bin')
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists() or packet.exists():
        raise ValueError('Use a new result file in the private BO3 lab.')
    code=CapturedCode(module,executable)
    shape=ActorShape(actors)
    plan=prepare_actor_wire(code,shape)
    base=code.base
    data,stack,stop=0x10000000,0x20000000,0x30000000
    msg,buffer,info,old,new,destination=data,data+0x1000,data+0x21000,data+0x22000,data+0x23000,data+0x24000
    cases=[]
    data_pages=(0x35EE000,0x33A3000,0x2FC6000,0x33B1000)
    span=code.read(0x20F0000,0x40000)

    def machine(expanded: bool):
        engine=Uc(UC_ARCH_X86,UC_MODE_64)
        engine.mem_map(base+0x20F0000,0x40000)
        engine.mem_write(base+0x20F0000,span)
        for page in data_pages:
            engine.mem_map(base+page,4096)
            engine.mem_write(base+page,code.read(page,4096))
        engine.mem_map(base+0x1365000,4096)
        engine.mem_write(base+0x1365000,code.read(0x1365000,4096))
        if expanded:
            for edit in plan:
                engine.mem_write(base+edit.guard.rva,edit.replacement)
        for address,size in ((data,0x100000),(stack,0x10000),(stop,4096)):
            engine.mem_map(address,size)
        for rva in (0x2BC3AA0,0x2BC53B0,0x2587760):
            engine.mem_map((base+rva)&~4095,4096)
            engine.mem_write(base+rva,b'\xc3')
        cookie=0x123456780CACEBAD
        engine.mem_write(base+0x35EEA10,struct.pack('<Q',cookie))

        def returned(current):
            rsp=current.reg_read(x64.UC_X86_REG_RSP)
            pc=struct.unpack('<Q',current.mem_read(rsp,8))[0]
            current.reg_write(x64.UC_X86_REG_RSP,rsp+8)
            current.reg_write(x64.UC_X86_REG_RIP,pc)

        def clear(current,address,size,unused):
            target=current.reg_read(x64.UC_X86_REG_RCX)
            count=current.reg_read(x64.UC_X86_REG_R8)
            value=current.reg_read(x64.UC_X86_REG_RDX)&255
            current.mem_write(target,bytes([value])*count)
            current.reg_write(x64.UC_X86_REG_RAX,target)
            returned(current)

        def check_cookie(current,address,size,unused):
            assert current.reg_read(x64.UC_X86_REG_RCX)==cookie,'The native packet frame cookie differs.'
            returned(current)

        def alternate_table_flag(current,address,size,unused):
            current.reg_write(x64.UC_X86_REG_RAX,0)
            returned(current)

        for rva,callback in ((0x2BC3AA0,check_cookie),(0x2BC53B0,clear),(0x2587760,alternate_table_flag)):
            engine.hook_add(UC_HOOK_CODE,callback,begin=base+rva,end=base+rva)
        header=bytearray(64)
        struct.pack_into('<Q',header,8,buffer)
        struct.pack_into('<I',header,0x18,0x20000)
        struct.pack_into('<i',header,0x2C,-1)
        engine.mem_write(msg,bytes(header))
        return engine

    def call(engine,rva: int,arguments: tuple[int,...],extra: tuple[int,...]=()) -> int:
        rsp=stack+0xFF08
        engine.mem_write(rsp,struct.pack('<Q',stop)+bytes(0xF0))
        engine.reg_write(x64.UC_X86_REG_RSP,rsp)
        saved={getattr(x64,'UC_X86_REG_'+name):0x100000000+index for index,name in
               enumerate(('RBX','RBP','RSI','RDI','R12','R13','R14','R15'))}
        for register,value in saved.items():engine.reg_write(register,value)
        for register,value in zip((x64.UC_X86_REG_RCX,x64.UC_X86_REG_RDX,x64.UC_X86_REG_R8,x64.UC_X86_REG_R9),arguments):
            engine.reg_write(register,value)
        for index,value in enumerate(extra):engine.mem_write(rsp+0x28+index*8,struct.pack('<Q',value))
        engine.emu_start(base+rva,stop,count=100000)
        assert engine.reg_read(x64.UC_X86_REG_RIP)==stop and engine.reg_read(x64.UC_X86_REG_RSP)==rsp+8
        assert all(engine.reg_read(register)==value for register,value in saved.items())
        return engine.reg_read(x64.UC_X86_REG_RAX)&0xFFFFFFFF

    def record(number: int,changed: bool) -> bytes:
        raw=bytearray(80)
        struct.pack_into('<I',raw,0,number)
        if changed:
            for offset,value in ((4,(number+20)%1024),(12,0x13579BDF^number),(52,(number+37)%1024),(72,number&1),(76,(number>>1)&1)):
                struct.pack_into('<I',raw,offset,value)
        return bytes(raw)

    def client_number(engine) -> int:
        rsp=stack+0xFF00
        engine.reg_write(x64.UC_X86_REG_RSP,rsp)
        engine.reg_write(x64.UC_X86_REG_R13,msg)
        engine.emu_start(base+0x1365675,base+0x1365682,count=100000)
        assert engine.reg_read(x64.UC_X86_REG_RIP)==base+0x1365682
        assert engine.reg_read(x64.UC_X86_REG_RSP)==rsp and engine.reg_read(x64.UC_X86_REG_R13)==msg
        return engine.reg_read(x64.UC_X86_REG_RAX)&0xFFFFFFFF

    def decode(engine,previous: bytes) -> tuple[int,int,bytes]:
        assert call(engine,0x20FCE70,(msg,))==1
        number=client_number(engine)
        engine.mem_write(old,previous)
        engine.mem_write(destination,b'\xcc'*96)
        removed=call(engine,0x20FD190,(msg,1000,old,destination),(number,))
        actual=bytes(engine.mem_read(destination,96))
        assert actual[80:]==b'\xcc'*16
        return number,removed,actual[:80]

    def reset_reader(engine):
        engine.mem_write(msg+0x24,bytes(8))
        engine.mem_write(msg+0x2C,struct.pack('<i',-1))

    fields=(0,4,8,12,16,20,24,28,32,36,40,44,52,72,76)
    def same_fields(actual: bytes,expected: bytes) -> bool:
        return all(actual[offset:offset+4]==expected[offset:offset+4] for offset in fields)

    for number in (63,64,127,128,255,256,299,actors-1):
        for changed in (False,True):
            engine=machine(True)
            before=record(number,False);after=record(number,changed)
            engine.mem_write(old,before);engine.mem_write(new,after)
            call(engine,0x21268D0,(info,msg,1000,old),(new,1))
            reset_reader(engine)
            decoded,removed,actual=decode(engine,before)
            assert decoded==number and removed==0 and same_fields(actual,after)
            for offset in (48,56,60,64,68):assert actual[offset:offset+4]==b'\xcc'*4
            cases.append({'case':'changed' if changed else 'forced-unchanged','actorId':number,'roundTrip':True})
    engine=machine(True)
    for number in reversed(range(actors)):
        engine.mem_write(old,record(number,False));engine.mem_write(new,record(number,True))
        call(engine,0x21268D0,(info,msg,1000,old),(new,1))
    encoded=bytes(engine.mem_read(buffer,struct.unpack('<I',engine.mem_read(msg+0x1C,4))[0]))
    reset_reader(engine)
    for number in reversed(range(actors)):
        decoded,removed,actual=decode(engine,record(number,False))
        assert decoded==number and removed==0 and same_fields(actual,record(number,True))
    cases.append({'case':'all-reverse-order','actors':actors,'packetBytes':len(encoded),'packetSha256':hashlib.sha256(encoded).hexdigest()})
    engine=machine(True)
    for number in (actors-1,64,0):
        engine.mem_write(old,record(number,True))
        call(engine,0x21268D0,(info,msg,1000,old),(0,1))
    reset_reader(engine)
    for number in (actors-1,64,0):
        decoded,removed,actual=decode(engine,record(number,True))
        assert decoded==number and removed==1 and actual==b'\xcc'*80
    cases.append({'case':'sparse-removals','records':3})
    engine=machine(True)
    engine.mem_write(old,record(0,False));engine.mem_write(new,record(0,False))
    call(engine,0x21268D0,(info,msg,1000,old),(new,0))
    assert engine.mem_read(msg+0x1C,4)==bytes(4)
    cases.append({'case':'unchanged-without-force','packetBytes':0})
    for expanded,reader_width in ((False,6),(True,6)):
        engine=machine(expanded)
        engine.mem_write(old,record(actors-1,False));engine.mem_write(new,record(actors-1,True))
        call(engine,0x21268D0,(info,msg,1000,old),(new,1))
        reset_reader(engine)
        assert call(engine,0x20FCE70,(msg,))==1
        assert call(engine,0x20FDFC0,(msg,reader_width))!=actors-1
        cases.append({'case':'mismatched-reader' if expanded else 'stock-high-id-truncation','comparisonRejected':True})
    for descriptor,offset in ((0x33B1480,88),(0x33B1498,92)):
        for previous in (0,63):
            for value in (0,63,64,127,128,255,256,299,actors-1,actors):
                engine=machine(True)
                engine.mem_write(old,bytes(160));engine.mem_write(new,bytes(160));engine.mem_write(destination,b'\xcc'*176)
                engine.mem_write(old+offset,struct.pack('<I',previous));engine.mem_write(new+offset,struct.pack('<I',value))
                call(engine,0x212A480,(info,msg,base+descriptor,old+offset),(new+offset,))
                reset_reader(engine)
                call(engine,0x2105F20,(msg,old+offset,destination+offset,base+descriptor))
                assert engine.mem_read(destination+offset,4)==struct.pack('<I',value)
                assert engine.mem_read(destination+160,16)==b'\xcc'*16
                cases.append({'case':'entity-actor-field','descriptorRva':hex(descriptor),'old':previous,'new':value,'roundTrip':True})
    mutations=(0x21268D0,0x212698E,0x21269CA,0x1365675,0x20FD190,0x33A3608,0x2FC69F0,0x33B1480,0x33B1490,0x33B1498,0x33B14A8,0x2FCB3A8,0x2FCB3C8)
    class ChangedCode(CapturedCode):
        def read(self,rva: int,size: int) -> bytes:
            raw=bytearray(super().read(rva,size))
            if rva<=self.mutation<rva+size:raw[self.mutation-rva]^=1
            return bytes(raw)
    for mutation in mutations:
        altered=object.__new__(ChangedCode);altered.__dict__.update(code.__dict__);altered.mutation=mutation
        try:prepare_actor_wire(altered,shape)
        except ValueError:pass
        else:raise AssertionError('An altered actor wire owner or descriptor escaped refusal.')
    result={'passed':True,'actors':actors,'wireBits':9,'rewrites':len(plan),'cases':cases,'guardRefusals':len(mutations),
            'packetArtifact':str(packet),'packetSha256':hashlib.sha256(encoded).hexdigest(),
            'gameWrites':0,'activationAllowed':False,'scope':'Owned Unicorn replay of captured packet/field codecs. Clear, alternate field-table flag, and cookie endpoints are authored. Client arrays, peer admission, demos and migration remain required.',
            'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in
                       (Path(__file__),PATCHES/'actor_wire.py',PATCHES/'shape.py',PATCHES/'captured_code.py')},
            'executableSha256':code.executable_sha256,'codecSpanSha256':hashlib.sha256(span).hexdigest()}
    output.parent.mkdir(parents=True,exist_ok=True)
    packet.write_bytes(encoded)
    output.write_text(json.dumps(result,indent=2)+'\n')
    return {'passed':True,'cases':len(cases),'actors':actors,'guardRefusals':len(mutations),'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=500)
    args=parser.parse_args()
    print(json.dumps(run(args.module,args.executable,args.dependencies,args.output,args.actors)))
