"""Replay the native allocation, pointer publication/decoder, and matching release paths."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES=Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from captured_code import CapturedCode
from client_allocator import prepare_client_allocation,BANK_OFFSET


def run(module: Path,executable: Path,dependencies: Path,output: Path) -> dict:
    sys.path.insert(0,str(dependencies))
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
    import unicorn.x86_const as x64
    import capstone
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab result file.')
    code=CapturedCode(module,executable)
    helper=code.base+0x201E0000
    edit=prepare_client_allocation(code,helper)
    assert edit.guard.rva==0x840922 and edit.guard.size==7 and len(edit.replacement)==7
    assert BANK_OFFSET==2*0x342720
    cases=[]
    for clients in (1,2):
        for selector in range(16):
            engine=Uc(UC_ARCH_X86,UC_MODE_64)
            decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True;decoder.skipdata=True
            pages=set(range(0x840000,0x844000,4096))|set(range(0x853000,0x857000,4096))|set(range(0x8ED000,0x8F4000,4096))
            for first,last in ((0x8408F0,0x843B54),(0x853D90,0x856F23)):
                for instruction in decoder.disasm(code.read(first,last-first),code.base+first):
                    if instruction.id==0:continue
                    for operand in instruction.operands:
                        if operand.type==capstone.x86.X86_OP_MEM and operand.mem.base==capstone.x86.X86_REG_RIP:
                            rva=instruction.address+instruction.size+operand.mem.disp-code.base
                            if 0<=rva<code.meta['imageSize']:pages.add(rva&~4095)
            pages.update((0x495A000,0x17E82000,0x49B2000,0x4C98000,0x2277000,0x23F8000,0x873000,0x85B000))
            for page in sorted(pages):
                engine.mem_map(code.base+page,4096);engine.mem_write(code.base+page,code.read(page,4096))
            engine.mem_map(helper,4096);engine.mem_write(helper,edit.stub)
            engine.mem_write(code.base+edit.guard.rva,edit.replacement)
            caller=code.base+0x10000100
            engine.mem_map(caller&~4095,4096)
            for offset,target in ((0,0x8408F0),(16,0x853D90),(32,0x8ED490)):
                engine.mem_write(caller+offset,b'\xe8'+struct.pack('<i',code.base+target-(caller+offset+5)))
            stack,teb,hunk=0x20000000,0x40000000,0x44000000
            peb=teb+0x10000+selector*4096
            for address,size in ((stack,0x20000),(teb,0x20000),(hunk,4096)):
                engine.mem_map(address,size)
            engine.mem_write(teb+0x30,struct.pack('<Q',teb));engine.mem_write(teb+0x60,struct.pack('<Q',peb))
            engine.reg_write(x64.UC_X86_REG_GS_BASE,teb)
            allocations=[];released=[];tail_calls=[]

            def callback(current,address,size,unused):
                assert current.reg_read(x64.UC_X86_REG_RSP)&15==8
                result=0
                if address==code.base+0x22773A0:
                    assert current.reg_read(x64.UC_X86_REG_RCX)==hunk
                    extent=current.reg_read(x64.UC_X86_REG_RDX)
                    alignment=current.reg_read(x64.UC_X86_REG_R8)
                    pointer=0x50000010+len(allocations)*0x2000000
                    allocations.append((pointer,extent,alignment));result=pointer
                elif address==code.base+0x22774E0:
                    assert current.reg_read(x64.UC_X86_REG_RCX)==hunk
                    pointer=current.reg_read(x64.UC_X86_REG_RDX)
                    assert pointer in {allocation[0] for allocation in allocations} and pointer not in released
                    released.append(pointer)
                elif address==code.base+0x85B990:
                    tail_calls.append((current.reg_read(x64.UC_X86_REG_RCX),current.reg_read(x64.UC_X86_REG_RDX),current.reg_read(x64.UC_X86_REG_R8)))
                for name in ('RCX','RDX','R8','R9','R10','R11'):
                    current.reg_write(getattr(x64,'UC_X86_REG_'+name),0xBAD00000)
                current.reg_write(x64.UC_X86_REG_RAX,result)
                rsp=current.reg_read(x64.UC_X86_REG_RSP);pc=struct.unpack('<Q',current.mem_read(rsp,8))[0]
                current.reg_write(x64.UC_X86_REG_RSP,rsp+8);current.reg_write(x64.UC_X86_REG_RIP,pc)

            for rva in (0x22773A0,0x22774E0,0x23F8200,0x873A30,0x85B990):
                engine.hook_add(UC_HOOK_CODE,callback,begin=code.base+rva,end=code.base+rva)
            engine.reg_write(x64.UC_X86_REG_RCX,hunk);engine.reg_write(x64.UC_X86_REG_RDX,clients)
            engine.reg_write(x64.UC_X86_REG_RSP,stack+0x1F000)
            saved={name:0x66660000+index for index,name in enumerate(('RBX','RBP','RSI','RDI','R12','R13','R14','R15'))}
            for name,value in saved.items():engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
            engine.emu_start(caller,caller+5,count=100000)
            assert engine.reg_read(x64.UC_X86_REG_RSP)==stack+0x1F000
            assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in saved.items())
            assert len(allocations)==4+3*clients
            assert allocations[0][1:]==((clients+2)*0x342720,16)
            assert [allocation[1:] for allocation in allocations[1:]]==[(clients*0x1E940,8),(clients*0x3A0,8),(0x200,8)]+[(0x7000,8),(0x11880,8),(0xDB7F0,16)]*clients
            assert tail_calls==[(hunk,clients,0)]
            # Run the actual decoder block with the same PEB branch and direct-call return classification.
            body=stack+0x1E000
            engine.reg_write(x64.UC_X86_REG_RSP,body);engine.reg_write(x64.UC_X86_REG_RBP,body+0x100)
            engine.reg_write(x64.UC_X86_REG_RCX,0)
            engine.mem_write(body+0x388,struct.pack('<Q',caller+37))
            engine.emu_start(code.base+0x8ED4C8,code.base+0x8EEEA1,count=100000)
            assert engine.reg_read(x64.UC_X86_REG_RAX)==allocations[0][0]
            engine.reg_write(x64.UC_X86_REG_RCX,hunk);engine.reg_write(x64.UC_X86_REG_RDX,clients)
            engine.reg_write(x64.UC_X86_REG_RSP,stack+0x1F000)
            for name,value in saved.items():engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
            engine.emu_start(caller+16,caller+21,count=100000)
            assert len(released)==len(allocations)
            assert engine.reg_read(x64.UC_X86_REG_RSP)==stack+0x1F000
            assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in saved.items())
            assert engine.mem_read(code.base+0x4C98C80,8)==bytes(8)
            cases.append({'localClients':clients,'pebBranch':selector,'firstAllocationBytes':allocations[0][1],
                          'allocations':len(allocations),'releases':len(released),'nativePointerRoundTrip':True})
    # The isolated allocation argument retains the original product for unsupported counts.
    products=[]
    for count in (-1,0,1,2,3):
        current=Uc(UC_ARCH_X86,UC_MODE_64);current.mem_map(helper,4096);current.mem_write(helper,edit.stub)
        current.mem_map(code.base+0x840000,4096)
        current.reg_write(x64.UC_X86_REG_RDX,count&((1<<64)-1));current.reg_write(x64.UC_X86_REG_RSP,0x12345678)
        current.emu_start(helper,code.base+0x840929,count=100)
        expected=((count+2 if count in (1,2) else count)*0x342720)&((1<<64)-1)
        assert current.reg_read(x64.UC_X86_REG_RDX)==expected and current.reg_read(x64.UC_X86_REG_RSP)==0x12345678
        products.append({'count':count,'bytes':expected})
    class ChangedCode(CapturedCode):
        def read(self,rva: int,size: int) -> bytes:
            raw=bytearray(super().read(rva,size))
            if rva<=self.mutation<rva+size:raw[self.mutation-rva]^=1
            return bytes(raw)
    mutations=(0x8408F0,0x840922,0x8421BC,0x853D90,0x856ED4,
               0x3115684,0x311569C,0x31156B0,0x31156C0,0x8ED490,0x31164A8)
    for mutation in mutations:
        changed=object.__new__(ChangedCode);changed.__dict__.update(code.__dict__);changed.mutation=mutation
        try:prepare_client_allocation(changed,helper)
        except ValueError:pass
        else:raise AssertionError('A changed allocator, publication/release, or decoder owner escaped refusal.')
    refusals=0
    for address in (0,code.base,helper+1,code.base+0x100000000,0x800000000000-16):
        try:prepare_client_allocation(code,address)
        except ValueError:refusals+=1
        else:raise AssertionError('An invalid allocation code binding escaped refusal.')
    paths=(Path(__file__),PATCHES/'client_allocator.py',PATCHES/'client_actors.py',PATCHES/'captured_code.py',PATCHES/'x64_table.py')
    result={'passed':True,'cases':cases,'allocationProducts':products,'guardRefusals':len(mutations),'addressRefusals':refusals,
            'gameWrites':0,'activationAllowed':False,
            'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
            'scope':'Owned native allocation/encoding/decoding/release callers. Hunk providers, setup tail and auxiliary initialization endpoints are authored. Native provider and game lifetime remain required.'}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n')
    return {'passed':True,'cases':len(cases),'allocationProducts':len(products),'guardRefusals':len(mutations),'addressRefusals':refusals,'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.dependencies,args.output)))
