"""Replay actor-region operands and complete creation/release loops in owned allocations."""
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
from client_actors import ClientActors,prepare_client_actors


def run(module: Path,executable: Path,dependencies: Path,output: Path,actors: int) -> dict:
    sys.path.insert(0,str(dependencies))
    import capstone
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
    import unicorn.x86_const as x64
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab result file.')
    code=CapturedCode(module,executable)
    native,external,control,stack=0x10000000,0x18000000,0x20000000,0x30000000
    layout=ClientActors(native+16,external,ActorShape(actors))
    edits=prepare_client_actors(code,layout)
    assert len(edits)==42 and all(len(edit.replacement)==edit.guard.size and not edit.stub for edit in edits)
    engine=Uc(UC_ARCH_X86,UC_MODE_64)
    for page in sorted({edit.guard.rva&~4095 for edit in edits}|{0x22C7000,0x22C8000}):
        engine.mem_map(code.base+page,4096);engine.mem_write(code.base+page,code.read(page,4096))
    for edit in edits:engine.mem_write(code.base+edit.guard.rva,edit.replacement)
    native_bytes=2*layout.client_stride+32
    for address,size in ((native,(native_bytes+4095)&~4095),
                         (external,(layout.total_bytes+4095)&~4095),(control,0x300000),(stack,0x10000)):
        engine.mem_map(address,size)
    engine.mem_write(native,b'\x5a'*native_bytes)
    engine.mem_write(external,b'\xa5'*layout.total_bytes)
    expected=bytearray(b'\xa5'*layout.total_bytes)
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    registers=('rax','rbx','rcx','rdx','rsi','rdi','rbp','r8','r9','r10','r11','r12','r13','r14','r15')
    def register(name: str) -> int:return getattr(x64,'UC_X86_REG_'+name.upper())
    cases=[]
    for edit in edits[:40]:
        instruction=next(decoder.disasm(code.read(edit.guard.rva,edit.guard.size),code.base+edit.guard.rva))
        operand=next((operand for operand in instruction.operands if operand.type==capstone.x86.X86_OP_MEM),None)
        original_offset=operand.mem.disp if operand is not None else instruction.operands[1].imm
        member=original_offset-0x2F84E0
        for client in range(2):
            for actor in sorted({0,63,64,299,actors-1}):
                for index,name in enumerate(registers):engine.reg_write(register(name),0x11220000+index)
                engine.reg_write(x64.UC_X86_REG_RSP,stack+0xFE00)
                cg=layout.native_base+client*layout.client_stride
                target=external+client*layout.client_stride+actor*0xB00+member
                if operand is not None:
                    base=instruction.reg_name(operand.mem.base);index=instruction.reg_name(operand.mem.index)
                    engine.reg_write(register(base),cg+(0 if index else actor*0xB00))
                    if index:engine.reg_write(register(index),actor*0xB00//operand.mem.scale)
                else:engine.reg_write(register(instruction.reg_name(instruction.operands[0].reg)),cg+actor*0xB00)
                value=0 if instruction.mnemonic=='cmp' and actor%2==0 else 0x33330000+actor
                if operand is not None and instruction.mnemonic!='lea':
                    encoded=value.to_bytes(8,'little')[:operand.size]
                    engine.mem_write(target,encoded);expected[target-external:target-external+len(encoded)]=encoded
                before={name:engine.reg_read(register(name)) for name in registers}
                engine.emu_start(code.base+edit.guard.rva,code.base+edit.guard.rva+edit.guard.size,count=1)
                destination=instruction.operands[0]
                if instruction.mnemonic in ('lea','add'):
                    assert engine.reg_read(register(instruction.reg_name(destination.reg)))==target
                elif instruction.mnemonic=='cmp':
                    mask=(1<<(operand.size*8))-1
                    assert bool(engine.reg_read(x64.UC_X86_REG_EFLAGS)&64)==(value&mask==0)
                elif destination.type==capstone.x86.X86_OP_REG:
                    assert engine.reg_read(register(instruction.reg_name(destination.reg)))==value
                else:
                    source=instruction.reg_name(instruction.operands[1].reg)
                    encoded=engine.reg_read(register(source)).to_bytes(8,'little')[:operand.size]
                    expected[target-external:target-external+len(encoded)]=encoded
                    assert engine.mem_read(target,len(encoded))==encoded
                changed=None
                if destination.type==capstone.x86.X86_OP_REG and instruction.mnemonic!='cmp':
                    changed=instruction.reg_name(destination.reg)
                    if changed.startswith('e'):changed='r'+changed[1:]
                    if changed.endswith('d'):changed=changed[:-1]
                assert all(engine.reg_read(register(name))==value for name,value in before.items() if name!=changed)
                assert engine.reg_read(x64.UC_X86_REG_RSP)==stack+0xFE00
                cases.append({'rva':hex(edit.guard.rva),'localClient':client,'actor':actor})
        assert engine.mem_read(native,native_bytes)==b'\x5a'*native_bytes
        assert engine.mem_read(external,layout.total_bytes)==expected

    resources=[];released=[];current_client=0
    def endpoint(current,address,size,unused):
        assert current.reg_read(x64.UC_X86_REG_RSP)&15==8
        if address==code.base+0x22C7FE0:
            assert current.reg_read(x64.UC_X86_REG_RCX)==control+0x100 and current.reg_read(x64.UC_X86_REG_EDX)==current_client
            result=0x55550000+len(resources)*16;resources.append(result)
        else:
            resource=current.reg_read(x64.UC_X86_REG_RCX)
            assert resource==resources[len(released)] and current.reg_read(x64.UC_X86_REG_EDX)==0xFFFFFFFF
            released.append(resource);result=0
        for name in ('rcx','rdx','r8','r9','r10','r11'):current.reg_write(register(name),0xBAD00000)
        current.reg_write(x64.UC_X86_REG_RAX,result)
        rsp=current.reg_read(x64.UC_X86_REG_RSP);pc=struct.unpack('<Q',current.mem_read(rsp,8))[0]
        current.reg_write(x64.UC_X86_REG_RSP,rsp+8);current.reg_write(x64.UC_X86_REG_RIP,pc)
    for rva in (0x22C7FE0,0x22C8B50):engine.hook_add(UC_HOOK_CODE,endpoint,begin=code.base+rva,end=code.base+rva)
    engine.mem_write(control+0x2E2BB0,struct.pack('<Q',control+0x100))
    cycles=[]
    for client in range(2):
        current_client=client
        for iteration in range(2):
            resources.clear();released.clear()
            engine.reg_write(x64.UC_X86_REG_RSP,stack+0xFE00)
            engine.reg_write(x64.UC_X86_REG_R14,layout.native_base+client*layout.client_stride)
            engine.reg_write(x64.UC_X86_REG_R12,client);engine.reg_write(x64.UC_X86_REG_RBX,control)
            engine.emu_start(code.base+0x904669,code.base+0x90469E,count=actors*16+100)
            assert len(resources)==actors
            for actor,resource in enumerate(resources):
                position=client*layout.client_stride+actor*0xB00+0xA88
                expected[position:position+8]=struct.pack('<Q',resource)
            assert engine.mem_read(external,layout.total_bytes)==expected
            engine.reg_write(x64.UC_X86_REG_R15,0)
            engine.emu_start(code.base+0x8CB30F,code.base+0x8CB33F,count=actors*20+100)
            assert released==resources and engine.reg_read(x64.UC_X86_REG_RSP)==stack+0xFE00
            for actor in range(actors):
                position=client*layout.client_stride+actor*0xB00+0xA88;expected[position:position+8]=bytes(8)
            assert engine.mem_read(external,layout.total_bytes)==expected
            assert engine.mem_read(native,native_bytes)==b'\x5a'*native_bytes
            cycles.append({'localClient':client,'iteration':iteration,'created':actors,'released':actors})
    class ChangedCode(CapturedCode):
        def read(self,rva: int,size: int) -> bytes:
            raw=bytearray(super().read(rva,size))
            if rva<=self.mutation<rva+size:raw[self.mutation-rva]^=1
            return bytes(raw)
    guards=json.loads((PATCHES/'client_actor_inventory.json').read_text())['guards']
    for guard in guards:
        altered=object.__new__(ChangedCode);altered.__dict__.update(code.__dict__);altered.mutation=guard['rva']
        try:prepare_client_actors(altered,layout)
        except ValueError:pass
        else:raise AssertionError('An altered client actor owner escaped refusal.')
    address_refusals=0
    for first,last in ((layout.native_base,layout.native_base),(layout.native_base,code.base),
                        (layout.native_base+1,external),(layout.native_base,external+1),
                        (layout.native_base,0x800000000000-4096),(layout.native_base,layout.native_base+0x100000000)):
        try:prepare_client_actors(code,ClientActors(first,last,layout.shape))
        except ValueError:address_refusals+=1
        else:raise AssertionError('An invalid complete actor allocation escaped refusal.')
    output.parent.mkdir(parents=True,exist_ok=True)
    binary=output.with_suffix('.bank.bin');binary.write_bytes(expected)
    paths=(Path(__file__),PATCHES/'client_actors.py',PATCHES/'client_actor_inventory.json',
           PATCHES/'shape.py',PATCHES/'captured_code.py')
    result={'passed':True,'actors':actors,'operandCases':len(cases),'operands':40,'resourceCycles':cycles,
            'guardRefusals':len(guards),'addressRefusals':address_refusals,'externalBytes':layout.total_bytes,
            'rewrites':42,'emittedStubs':0,'activationAllowed':False,'gameWrites':0,
            'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
            'artifact':{'path':str(binary),'sha256':hashlib.sha256(expected).hexdigest()},
            'scope':'Owned native operand and resource-loop replay. Allocation/release endpoints and native client root are authored. Complete allocation/root discovery, resets, flag consumers and native callers remain.'}
    output.write_text(json.dumps(result,indent=2)+'\n')
    return {key:result[key] for key in ('passed','actors','operandCases','guardRefusals','addressRefusals','rewrites','emittedStubs')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=500)
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.dependencies,args.output,args.actors)))
