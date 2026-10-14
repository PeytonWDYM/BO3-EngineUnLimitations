"""Round-trip entity actor fields through captured cleanup and one-based clone consumers."""
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
from client_actors import ClientActors,prepare_client_actors,ACTOR_BANK_OFFSET,NATIVE_CLIENT_STRIDE


def run(module: Path,executable: Path,dependencies: Path,output: Path,actors: int) -> dict:
    sys.path.insert(0,str(dependencies))
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
    import unicorn.x86_const as x64
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab result file.')
    code=CapturedCode(module,executable);shape=ActorShape(actors)
    wire=prepare_actor_wire(code,shape)
    sentinel=next((edit for edit in wire if edit.guard.rva==0x24AE77F),None)
    assert sentinel is not None,'The expanded actor invalid value is absent from the coordinated entity wire preparation.'
    assert len(wire)==6 and len(sentinel.replacement)==8 and not sentinel.stub
    cg,data,stack,stop=0x40000000,0x10000000,0x20000000,0x30000000
    banks=ClientActors(cg,cg+ACTOR_BANK_OFFSET,shape)
    client_edits=prepare_client_actors(code,banks)
    engine=Uc(UC_ARCH_X86,UC_MODE_64)
    pages=set(range(0x20F0000,0x2130000,4096))
    pages.update(range(0x488000,0x48E000,4096));pages.update((0x497000,0x24AE000,0x33B1000,0x33A3000,0x2FC6000))
    for page in sorted(pages):engine.mem_map(code.base+page,4096);engine.mem_write(code.base+page,code.read(page,4096))
    for address,size in ((cg,(4*NATIVE_CLIENT_STRIDE+4095)&~4095),(data,0x100000),(stack,0x20000),(stop,4096)):
        engine.mem_map(address,size)
    for edit in wire:
        if edit.guard.rva!=0x1365675:engine.mem_write(code.base+edit.guard.rva,edit.replacement)
    for edit in client_edits:
        if edit.guard.rva in (0x48B64B,0x48B666):engine.mem_write(code.base+edit.guard.rva,edit.replacement)
    engine.mem_map((code.base+0x2587760)&~4095,4096)
    def flag(current,address,size,unused):
        rsp=current.reg_read(x64.UC_X86_REG_RSP);pc=struct.unpack('<Q',current.mem_read(rsp,8))[0]
        for name in ('RCX','RDX','R8','R9','R10','R11'):current.reg_write(getattr(x64,'UC_X86_REG_'+name),0xBAD00000)
        current.reg_write(x64.UC_X86_REG_RAX,0);current.reg_write(x64.UC_X86_REG_RSP,rsp+8);current.reg_write(x64.UC_X86_REG_RIP,pc)
    engine.hook_add(UC_HOOK_CODE,flag,begin=code.base+0x2587760,end=code.base+0x2587760)
    msg,buffer,old,new,entity,actor,info=data,data+0x1000,data+0x21000,data+0x22000,data+0x23000,data+0x25000,data+0x28000
    saved={name:0x66660000+index for index,name in enumerate(('RBX','RBP','RSI','RDI','R12','R13','R14','R15'))}
    cases=[];packet=b''
    def call(rva: int,args: tuple[int,...],extra: tuple[int,...]=()) -> None:
        rsp=stack+0x1F008;engine.mem_write(rsp,struct.pack('<Q',stop)+bytes(0xF0));engine.reg_write(x64.UC_X86_REG_RSP,rsp)
        for name,value in saved.items():engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
        for name,value in zip(('RCX','RDX','R8','R9'),args):engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
        for index,value in enumerate(extra):engine.mem_write(rsp+0x28+index*8,struct.pack('<Q',value))
        engine.emu_start(code.base+rva,stop,count=100000)
        assert engine.reg_read(x64.UC_X86_REG_RSP)==rsp+8
        assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in saved.items())
    def round_trip(descriptor: int,offset: int,value: int) -> None:
        nonlocal packet
        engine.mem_write(msg,bytes(64));engine.mem_write(buffer,bytes(0x20000))
        engine.mem_write(msg+8,struct.pack('<Q',buffer));engine.mem_write(msg+0x18,struct.pack('<I',0x20000));engine.mem_write(msg+0x2C,struct.pack('<i',-1))
        engine.mem_write(old,bytes(160));engine.mem_write(new,bytes(160));engine.mem_write(entity,b'\xcc'*0x1000)
        engine.mem_write(new+offset,struct.pack('<I',value))
        call(0x212A480,(info,msg,code.base+descriptor,old+offset),(new+offset,))
        count=struct.unpack('<I',engine.mem_read(msg+0x1C,4))[0];packet=bytes(engine.mem_read(buffer,count))
        engine.mem_write(msg+0x24,bytes(8));engine.mem_write(msg+0x2C,struct.pack('<i',-1))
        call(0x2105F20,(msg,old+offset,entity+0x3F8+offset,code.base+descriptor))
        expected=bytearray(b'\xcc'*0x1000);struct.pack_into('<I',expected,0x3F8+offset,value)
        assert engine.mem_read(entity,0x1000)==expected
    # Preserve the actual zero branch instead of treating a stock capacity as the clone sentinel.
    for source in (None,0,63,64,126,127,255,256,actors-1):
        value=0 if source is None else source+1
        round_trip(0x33B1498,92,value)
        for client in range(2):
            engine.mem_write(entity+0x400,struct.pack('<I',0x10));engine.reg_write(x64.UC_X86_REG_RDI,entity);engine.reg_write(x64.UC_X86_REG_R15,0)
            engine.reg_write(x64.UC_X86_REG_RSP,stack+0x1F000)
            engine.emu_start(code.base+0x497EAE,code.base+(0x497ECD if source is None else 0x497EC0),count=100)
            assert engine.reg_read(x64.UC_X86_REG_RIP)==code.base+(0x497ECD if source is None else 0x497EC0)
            if source is not None:
                engine.reg_write(x64.UC_X86_REG_R8,entity)
                engine.emu_start(code.base+0x488528,code.base+0x48852F,count=10)
                assert engine.reg_read(x64.UC_X86_REG_RSI)==value
                target=actors-1 if source!=actors-1 else 0
                engine.mem_write(cg,b'\xa5'*(4*NATIVE_CLIENT_STRIDE))
                start=banks.base+client*NATIVE_CLIENT_STRIDE;source_address=start+source*0xB00;target_address=start+target*0xB00
                source_record=bytes((index*7+source)&255 for index in range(0xB00));engine.mem_write(source_address,source_record)
                before=bytearray(engine.mem_read(cg,4*NATIVE_CLIENT_STRIDE));expected=bytearray(before)
                members=((0x30,4),(0x34,2),(0x36,1),(0x38,2),(0x3A,1),(0x3C,2),(0x3E,1),(0x40,2),(0x42,1),(0x44,2),(0x46,1),(0x48,2),(0x4A,1))
                for offset,size in members:expected[target_address-cg+offset:target_address-cg+offset+size]=source_record[offset:offset+size]
                engine.mem_write(entity+0x450,struct.pack('<I',target))
                frame=stack+0x1F000;engine.mem_write(frame+0x50,struct.pack('<Q',cg+client*NATIVE_CLIENT_STRIDE))
                for name,register in (('RDI',cg+client*NATIVE_CLIENT_STRIDE),('RCX',entity),('RSI',value),('RBP',frame),('RSP',frame)):
                    engine.reg_write(getattr(x64,'UC_X86_REG_'+name),register)
                engine.emu_start(code.base+0x48B644,code.base+0x48B6D7,count=1000)
                assert engine.reg_read(x64.UC_X86_REG_RDI)==target_address and engine.reg_read(x64.UC_X86_REG_RSI)==source_address
                assert engine.mem_read(cg,4*NATIVE_CLIENT_STRIDE)==expected
            cases.append({'case':'one-based-clone','source':source,'encoded':value,'localClient':client,'zeroBranchAndCompleteBanks':True})
    # Compare actual stock/expanded cleanup tails, including their original restored-register epilogue.
    for expanded in (False,True):
        engine.mem_write(code.base+sentinel.guard.rva,sentinel.replacement if expanded else code.read(sentinel.guard.rva,8))
        engine.ctl_remove_cache(code.base+sentinel.guard.rva,code.base+sentinel.guard.rva+8)
        engine.mem_write(actor,b'\xa5'*0x1000);engine.mem_write(entity,b'\x5a'*0x1000)
        frame=stack+0x1F000
        for offset,name in ((0x20,'R14'),(0x30,'RDI'),(0x38,'RBX'),(0x40,'RBP'),(0x48,'RSI')):engine.mem_write(frame+offset,struct.pack('<Q',saved[name]))
        engine.mem_write(frame+0x28,struct.pack('<Q',stop));engine.reg_write(x64.UC_X86_REG_RSP,frame)
        for name,value in saved.items():engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
        engine.reg_write(x64.UC_X86_REG_R14,entity);engine.reg_write(x64.UC_X86_REG_RSI,actor);engine.reg_write(x64.UC_X86_REG_RBP,0)
        engine.emu_start(code.base+0x24AE775,stop,count=100)
        invalid=struct.unpack('<I',engine.mem_read(entity+88,4))[0]
        assert (invalid in range(actors)) is (not expanded),(expanded,invalid,actors)
        expected_entity=bytearray(b'\x5a'*0x1000);struct.pack_into('<I',expected_entity,88,actors if expanded else 64)
        expected_actor=bytearray(b'\xa5'*0x1000);expected_actor[:4]=bytes(4)
        assert engine.mem_read(entity,0x1000)==expected_entity and engine.mem_read(actor,0x1000)==expected_actor
        assert engine.reg_read(x64.UC_X86_REG_RSP)==frame+0x30
        assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in saved.items())
        round_trip(0x33B1480,88,invalid)
        cases.append({'case':'native-invalid-value' if expanded else 'stock-invalid-collision','invalidActor':invalid,'epilogueAndCodec':True})
    class ChangedCode(CapturedCode):
        def read(self,rva: int,size: int) -> bytes:
            raw=bytearray(super().read(rva,size))
            if rva<=self.mutation<rva+size:raw[self.mutation-rva]^=1
            return bytes(raw)
    mutations=(0x24AE5E0,0x24AE707,0x24AE77F,0x31CF418,0x31CF42C,0x488500,0x48B65C,0x496470,0x497EB7,0x310E55C,0x310E37C)
    for mutation in mutations:
        changed=object.__new__(ChangedCode);changed.__dict__.update(code.__dict__);changed.mutation=mutation
        try:prepare_actor_wire(changed,shape)
        except ValueError:pass
        else:raise AssertionError('An altered entity actor owner escaped preparation refusal.')
    output.parent.mkdir(parents=True,exist_ok=True);binary=output.with_suffix('.entity.bin');binary.write_bytes(packet)
    paths=(Path(__file__),PATCHES/'actor_wire.py',PATCHES/'client_actors.py',PATCHES/'client_actor_inventory.json',PATCHES/'captured_code.py',PATCHES/'shape.py')
    result={'passed':True,'actors':actors,'cases':cases,'guardRefusals':len(mutations),
            'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
            'artifact':{'path':str(binary),'sha256':hashlib.sha256(packet).hexdigest()},'gameWrites':0,'activationAllowed':False,
            'scope':'Native entity field codecs, cleanup epilogue, clone zero branch/address calculation and selected field copy. Complete destructor/clone callers, alternate field selector, remaining flags, saves and matching peers remain. Codec flag endpoint is authored.'}
    output.write_text(json.dumps(result,indent=2)+'\n');return {'passed':True,'actors':actors,'cases':len(cases),'guardRefusals':len(mutations),'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=500)
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.dependencies,args.output,args.actors)))
