"""Execute the complete native demo actor writer with guarded temporary and prior-record storage."""
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
from demo_writer import DemoWriter,prepare_demo_writer


def run(module: Path,executable: Path,dependencies: Path,output: Path,actors: int) -> dict:
    sys.path.insert(0,str(dependencies))
    import capstone
    from unicorn import Uc,UcError,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
    import unicorn.x86_const as x64
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab result file.')
    code=CapturedCode(module,executable);shape=ActorShape(actors)
    storage=DemoWriter(code.base+0x32000000,shape);helper=code.base+0x201F0000
    edits=prepare_demo_writer(code,storage,helper);wire=prepare_actor_wire(code,shape)
    assert len(edits)==7 and sum(bool(edit.stub) for edit in edits)==1
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    pages=set(range(0x20F0000,0x2130000,4096));pages.update((0x25CE000,0x35EE000,0x33A3000,0x2FC6000,0x33B1000,0x1365000,0x24AE000,0x31DB000))
    for instruction in decoder.disasm(code.read(0x25CE9D0,0x2B9),code.base+0x25CE9D0):
        for operand in instruction.operands:
            if operand.type==capstone.x86.X86_OP_MEM and operand.mem.base==capstone.x86.X86_REG_RIP:
                pages.add((instruction.address+instruction.size+operand.mem.disp-code.base)&~4095)
    pages.add(0x196C8000);pages.update(range(0x196C7000,0x196C9000,4096))
    original={page:code.read(page,4096) for page in sorted(pages)}
    data,stack,stop,pool,connection,ring=0x10000000,0x20000000,0x30000000,0x40000000,0x60000000,0x70000000
    msg,buffer,info,states=data,data+0x1000,data+0x21000,data+0x22000
    saved={name:0x66660000+index for index,name in enumerate(('RBX','RBP','RSI','RDI','R12','R13','R14','R15'))}
    cookie=0x123456780CACEBAD
    class CookieLost(AssertionError):pass
    def record(actor: int,phase: int=0) -> bytes:
        raw=bytearray(80);struct.pack_into('<II',raw,0,actor,(actor+phase+1)%1024)
        for offset in (48,56,60,64,68):struct.pack_into('<I',raw,offset,0xABCD0000+actor+offset)
        return bytes(raw)
    def execute(count_only: bool=False) -> tuple[list[dict],bytes]:
        engine=Uc(UC_ARCH_X86,UC_MODE_64)
        for page,raw in original.items():engine.mem_map(code.base+page,4096);engine.mem_write(code.base+page,raw)
        for address,size in ((data,0x100000),(stack,0x20000),(stop,4096),(pool,(shape.actor_bytes+4095)&~4095),
                             (connection,0x30000),(ring,0xA0000),(helper,4096),(storage.base-4096,((storage.bytes+16+4095)&~4095)+4096)):
            engine.mem_map(address,size)
        engine.mem_write(stack,b'\xcc'*0x20000);engine.mem_write(storage.base-16,b'\xa5'*(storage.bytes+32))
        engine.mem_write(code.base+0x196C75FC,b'\x5a'*0x1400);engine.mem_write(code.base+0x196C89FC,bytes(4))
        engine.mem_write(code.base+0x1768E598,struct.pack('<Q',pool));engine.mem_write(code.base+0x35EEA10,struct.pack('<Q',cookie))
        engine.mem_write(code.base+0x17887690,struct.pack('<I',1000))
        for edit in (*wire,*edits):
            if count_only and edit.name.startswith('demo_writer_frame_'):continue
            engine.mem_write(code.base+edit.guard.rva,edit.replacement)
            if edit.stub:engine.mem_write(edit.stub_address,edit.stub)
        callbacks=[]
        def endpoint(current,address,size,unused):
            result=0
            if address==code.base+0x19AEE40:
                actor=current.reg_read(x64.UC_X86_REG_RCX)&0xFFFFFFFF;assert actor<actors
                callbacks.append(actor);result=states+actor*80
            elif address in (code.base+0x227B480,code.base+0x227B490):result=current.reg_read(x64.UC_X86_REG_RCX)&0xFFFFFFFF
            elif address==code.base+0x2BC3AA0:
                if current.reg_read(x64.UC_X86_REG_RCX)!=cookie:raise CookieLost('The enlarged demo ID list overwrote the native frame cookie.')
            elif address==code.base+0x2BC53B0:
                pointer=current.reg_read(x64.UC_X86_REG_RCX);length=current.reg_read(x64.UC_X86_REG_R8)
                current.mem_write(pointer,bytes([current.reg_read(x64.UC_X86_REG_RDX)&255])*length);result=pointer
            if address!=code.base+0x2BC3AA0:
                for name in ('RCX','RDX','R8','R9','R10','R11'):current.reg_write(getattr(x64,'UC_X86_REG_'+name),0xBAD00000)
                current.reg_write(x64.UC_X86_REG_RAX,result)
            rsp=current.reg_read(x64.UC_X86_REG_RSP);pc=struct.unpack('<Q',current.mem_read(rsp,8))[0]
            current.reg_write(x64.UC_X86_REG_RSP,rsp+8);current.reg_write(x64.UC_X86_REG_RIP,pc)
        endpoints=(0x19AEE40,0x2BC3AA0,0x2BC53B0,0x2587760,0x227B480,0x227B490)
        for page in sorted({(code.base+rva)&~4095 for rva in endpoints}):engine.mem_map(page,4096)
        for rva in endpoints:
            engine.hook_add(UC_HOOK_CODE,endpoint,begin=code.base+rva,end=code.base+rva)
        def call(rva: int,args: tuple[int,...],extra: tuple[int,...]=()) -> int:
            rsp=stack+0x1F008;engine.mem_write(rsp,struct.pack('<Q',stop)+bytes(0xF0));engine.reg_write(x64.UC_X86_REG_RSP,rsp)
            for name,value in saved.items():engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
            for name,value in zip(('RCX','RDX','R8','R9'),args):engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
            for index,value in enumerate(extra):engine.mem_write(rsp+0x28+index*8,struct.pack('<Q',value))
            try:engine.emu_start(code.base+rva,stop,count=2000000)
            except UcError as error:
                arguments=tuple(hex(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))) for name in ('RCX','RDX','R8','R9'))
                raise AssertionError(f'Native demo replay fault at {engine.reg_read(x64.UC_X86_REG_RIP)-code.base:#x} from {rva:#x}, arguments {arguments}.') from error
            assert engine.reg_read(x64.UC_X86_REG_RSP)==rsp+8
            assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in saved.items())
            return engine.reg_read(x64.UC_X86_REG_RAX)&0xFFFFFFFF
        all_ids=set(range(actors));sparse=all_ids-{64,255};phases={actor:0 for actor in all_ids}
        frame_ids=(all_ids,sparse,sparse,all_ids-{126},set(),all_ids)
        engine.mem_write(connection+0x50,struct.pack('<QI',ring,8192));previous=0
        expected_storage=bytearray(b'\xa5'*storage.bytes);cases=[];bundle=bytearray(b'BO3DMAP1'+struct.pack('<II',actors,len(frame_ids)))
        fields=(0,4,8,12,16,20,24,28,32,36,40,44,52,72,76)
        for frame,active in enumerate(frame_ids):
            if frame==3:
                for actor in (64,256,actors-1):phases[actor]=3
            if frame==5:phases={actor:5 for actor in all_ids}
            engine.mem_write(msg,bytes(64));engine.mem_write(buffer,bytes(0x20000))
            engine.mem_write(msg+8,struct.pack('<Q',buffer));engine.mem_write(msg+0x18,struct.pack('<I',0x20000));engine.mem_write(msg+0x2C,struct.pack('<i',-1))
            for actor in range(actors):
                engine.mem_write(pool+actor*0x2110,bytes([int(actor in active)]));engine.mem_write(states+actor*80,record(actor,phases[actor]))
            exports=len(callbacks);call(0x25CE9D0,(msg,))
            records=[record(actor,phases[actor]) for actor in sorted(active)];copied=b''.join(records)
            expected_storage[:len(copied)]=copied
            assert engine.mem_read(storage.base,storage.bytes)==expected_storage
            assert engine.mem_read(storage.base-16,16)==b'\xa5'*16 and engine.mem_read(storage.base+storage.bytes,16)==b'\xa5'*16
            assert engine.mem_read(code.base+0x196C75FC,0x1400)==b'\x5a'*0x1400
            assert engine.mem_read(code.base+0x196C89FC,4)==struct.pack('<I',len(active))
            count=struct.unpack('<I',engine.mem_read(msg+0x1C,4))[0];packet=bytes(engine.mem_read(buffer,count))
            engine.mem_write(msg+0x24,bytes(8));engine.mem_write(msg+0x2C,struct.pack('<i',-1))
            assert call(0x20FE510,(msg,))==len(active)
            cursor=struct.unpack('<I',engine.mem_read(connection+0xB788,4))[0];row=connection+0x10000+(frame&1)*0xC000
            call(0x13655C0,(connection,msg,1000,previous),(row,))
            assert engine.mem_read(row+0xB598,4)==struct.pack('<I',len(active))
            for index,expected in enumerate(records):
                actual=engine.mem_read(ring+((cursor+index)%8192)*80,80)
                assert all(actual[offset:offset+4]==expected[offset:offset+4] for offset in fields)
            assert set(callbacks[exports:])==active
            cases.append({'frame':frame,'activeActors':len(active),'stateExports':len(callbacks)-exports,'packetBytes':count})
            bundle+=struct.pack('<II',count,len(active))+packet+copied;previous=row
        return cases,bytes(bundle)
    cases,packet=execute()
    try:execute(True)
    except CookieLost:count_only_refused=True
    else:raise AssertionError('A count-only demo writer preserved its original frame cookie.')
    class ChangedCode(CapturedCode):
        def read(self,rva: int,size: int) -> bytes:
            raw=bytearray(super().read(rva,size))
            if rva<=self.mutation<rva+size:raw[self.mutation-rva]^=1
            return bytes(raw)
    mutations=(0x25CE9D0,0x25CE9E8,0x25CE9F9,0x25CEA37,0x25CEA3C,0x25CEA6B,0x25CEC58,0x25CEC68,0x31DBB00,0x31DBB24)
    for mutation in mutations:
        changed=object.__new__(ChangedCode);changed.__dict__.update(code.__dict__);changed.mutation=mutation
        try:prepare_demo_writer(changed,storage,helper)
        except ValueError:pass
        else:raise AssertionError('An altered demo writer frame escaped refusal.')
    output.parent.mkdir(parents=True,exist_ok=True);binary=output.with_suffix('.packet.bin');binary.write_bytes(packet)
    paths=(Path(__file__),PATCHES/'demo_writer.py',PATCHES/'actor_wire.py',PATCHES/'native_unwind.py',PATCHES/'x64_table.py',PATCHES/'shape.py',PATCHES/'captured_code.py')
    addresses=((code.base,helper),(storage.base,helper+1),(helper,helper),
               (storage.base,code.base+0x90000000),(code.base+0x90000000,helper),
               (0x800000000000-4096,helper),(0,helper),(storage.base,0))
    for address,stub in addresses:
        try:prepare_demo_writer(code,DemoWriter(address,shape),stub)
        except ValueError:pass
        else:raise AssertionError('An invalid demo code or complete storage interval escaped refusal.')
    report={'passed':True,'actors':actors,'cases':cases,'frameBytes':storage.frame,'countOnlyRefused':count_only_refused,
            'guardRefusals':len(mutations),'addressRefusals':len(addresses),
            'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
            'artifact':{'path':str(binary),'sha256':hashlib.sha256(packet).hexdigest()},'gameWrites':0,'activationAllowed':False,
            'scope':'Complete native demo writer, framing, and actor parser. Actor state export, little-endian long dispatch, clear, cookie and field flag endpoints are authored. Windows frames, helper/handler game binding, demo reader/reset, saves and peers remain.'}
    output.write_text(json.dumps(report,indent=2)+'\n');return {'passed':True,'actors':actors,'frames':len(cases),'guardRefusals':len(mutations),'addressRefusals':len(addresses),'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=500)
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.dependencies,args.output,args.actors)))
