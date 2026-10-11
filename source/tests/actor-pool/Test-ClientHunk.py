"""Replay the complete measured client caller with native counting and fixed-backing hunk providers."""
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
    import capstone
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
    import unicorn.x86_const as x64
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab result file.')
    code=CapturedCode(module,executable)
    helper=code.base+0x201E0000
    class ChangedCode(CapturedCode):
        def read(self,rva: int,size: int) -> bytes:
            raw=bytearray(super().read(rva,size))
            if rva<=self.mutation<rva+size:raw[self.mutation-rva]^=1
            return bytes(raw)
    mutations=(0x135D378,0x135D468,0x135D3BC,0x85B9F5,0x2276D50,0x2276F86,0x22771E0,
               0x22773A7,0x2277460,0x2277480,0x2277500,0x3115C14,0x312F7A0,0x31BFB54,
               *range(0x33C28F0,0x33C28F0+200,8))
    for mutation in mutations:
        changed=object.__new__(ChangedCode);changed.__dict__.update(code.__dict__);changed.mutation=mutation
        try:prepare_client_allocation(changed,helper)
        except ValueError:pass
        else:raise AssertionError(f'An altered two-pass hunk dependency escaped refusal: {mutation:#x}.')
    edit=prepare_client_allocation(code,helper)
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True;decoder.skipdata=True
    pages=set()
    for first,last in ((0x8408F0,0x843BD0),(0x85B990,0x85D308),(0x135D330,0x135D4D2),
                       (0x2276D50,0x22770B3),(0x2277190,0x2277213),(0x22773A0,0x2277512)):
        pages.update(range(first&~4095,(last+4095)&~4095,4096))
        for instruction in decoder.disasm(code.read(first,last-first),code.base+first):
            if instruction.id==0:continue
            for operand in instruction.operands:
                if operand.type==capstone.x86.X86_OP_MEM and operand.mem.base==capstone.x86.X86_REG_RIP:
                    rva=instruction.address+instruction.size+operand.mem.disp-code.base
                    if 0<=rva<code.meta['imageSize']:pages.add(rva&~4095)
    pages.update((0x495A000,0x17E82000,0x49B2000,0x4C98000,0x4C9F000))
    endpoints=(0x14ED6C0,0x135DC20,0x23F8200,0x14D4720,0x13484E0,0xB24C0,
               0x20C4E80,0x20C5EE0,0x20C4F10,0x2250600,0x2250750,0x2BC53B0,0x20EC0B0)
    pages.update(address&~4095 for address in endpoints)
    native_pages={page:code.read(page,4096) for page in sorted(pages)}
    cases=[];last_backing=b''

    class Exhausted(RuntimeError):pass

    def execute(clients: int,selector: int,patched: bool,stale: bool=False) -> dict:
        nonlocal last_backing
        engine=Uc(UC_ARCH_X86,UC_MODE_64)
        for page,raw in native_pages.items():engine.mem_map(code.base+page,4096);engine.mem_write(code.base+page,raw)
        engine.mem_map(helper,4096);engine.mem_write(helper,edit.stub)
        if patched:engine.mem_write(code.base+edit.guard.rva,edit.replacement)
        caller=code.base+0x10000100
        engine.mem_map(caller&~4095,4096)
        engine.mem_write(caller,b'\xe8'+struct.pack('<i',code.base+0x135D330-(caller+5)))
        stack,teb,heap=0x20000000,0x40000000,0x50000000
        engine.mem_map(stack,0x20000);engine.mem_map(teb,0x20000)
        engine.mem_write(teb+0x30,struct.pack('<Q',teb));engine.mem_write(teb+0x60,struct.pack('<Q',teb+0x10000+selector*4096))
        engine.reg_write(x64.UC_X86_REG_GS_BASE,teb)
        requests=[];reservations=[];commits=[];roots=[];resets=[]

        def callback(current,address,size,unused):
            assert current.reg_read(x64.UC_X86_REG_RSP)&15==8
            result=0
            rcx=current.reg_read(x64.UC_X86_REG_RCX);rdx=current.reg_read(x64.UC_X86_REG_RDX);r8=current.reg_read(x64.UC_X86_REG_R8)
            if address==code.base+0x20C5EE0:
                assert not reservations and rdx==16
                reservations.append(rcx)
                current.mem_map(heap-4096,((rcx+16+4095)&~4095)+4096)
                current.mem_write(heap-16,b'\xcc'*(rcx+32));result=heap
            elif address==code.base+0x2BC53B0:
                assert rcx==heap and r8==0x50 or rcx==heap+0x48 and r8==reservations[0]-0x48
                assert rdx==0
                current.mem_write(rcx,bytes(r8));result=rcx;resets.append((rcx,r8))
            elif address==code.base+0x2250600:commits.append((rcx,rdx))
            elif address==code.base+0x2250750:raise AssertionError('A measured fixed-backing hunk attempted native growth.')
            elif address==code.base+0x20EC0B0:
                assert current.mem_read(heap-16,16)==b'\xcc'*16
                assert current.mem_read(heap+reservations[0],16)==b'\xcc'*16
                raise Exhausted('The native fixed-backing reserve refused exhaustion.')
            for name in ('RCX','RDX','R8','R9','R10','R11'):current.reg_write(getattr(x64,'UC_X86_REG_'+name),0xBAD00000)
            current.reg_write(x64.UC_X86_REG_RAX,result)
            rsp=current.reg_read(x64.UC_X86_REG_RSP);pc=struct.unpack('<Q',current.mem_read(rsp,8))[0]
            current.reg_write(x64.UC_X86_REG_RSP,rsp+8);current.reg_write(x64.UC_X86_REG_RIP,pc)
        for endpoint in endpoints:engine.hook_add(UC_HOOK_CODE,callback,begin=code.base+endpoint,end=code.base+endpoint)

        def observe(current,address,size,unused):
            if address==code.base+0x22773A0:
                hunk=current.reg_read(x64.UC_X86_REG_RCX)
                kind=struct.unpack('<I',current.mem_read(hunk,4))[0]
                requests.append((kind,current.reg_read(x64.UC_X86_REG_RDX),current.reg_read(x64.UC_X86_REG_R8)))
            elif address==code.base+0x84092E:roots.append(current.reg_read(x64.UC_X86_REG_RAX))
            elif stale:
                counter=current.reg_read(x64.UC_X86_REG_RSP)+0x58
                measured=struct.unpack('<I',current.mem_read(counter,4))[0]
                assert measured>BANK_OFFSET
                current.mem_write(counter,struct.pack('<I',measured-BANK_OFFSET))
        for target in (0x22773A0,0x84092E,0x135D3A8):engine.hook_add(UC_HOOK_CODE,observe,begin=code.base+target,end=code.base+target)
        saved={name:0x66660000+index for index,name in enumerate(('RBX','RBP','RSI','RDI','R12','R13','R14','R15'))}
        for name,value in saved.items():engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
        engine.reg_write(x64.UC_X86_REG_RSP,stack+0x1F000)
        engine.reg_write(x64.UC_X86_REG_RCX,clients);engine.reg_write(x64.UC_X86_REG_RDX,0);engine.reg_write(x64.UC_X86_REG_R8,0)
        engine.emu_start(caller,caller+5,count=1000000)
        assert engine.reg_read(x64.UC_X86_REG_RSP)==stack+0x1F000
        assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in saved.items())
        expected=[((clients+2 if patched else clients)*0x342720,16),
                  (clients*0x1E940,8),(clients*0x3A0,8),(0x200,8)]+[(0x7000,8),(0x11880,8),(0xDB7F0,16)]*clients+[(0x3F0000,8)]*clients
        assert requests==[(kind,size,alignment) for kind in (4,0) for size,alignment in expected]
        assert roots==[0,heap+0x50] and roots[1]&15==0
        measured=sum(size for size,alignment in expected)
        assert reservations==[measured+0x400] and not commits and len(resets)==2
        end,used=struct.unpack('<2Q',engine.mem_read(heap+0x30,16))
        assert end==heap+reservations[0] and used==roots[1]+measured and used<=end
        assert engine.mem_read(heap-16,16)==b'\xcc'*16 and engine.mem_read(end,16)==b'\xcc'*16
        last_backing=bytes(engine.mem_read(heap,reservations[0]))
        assert last_backing[0x48:]==bytes(reservations[0]-0x48)
        return {'localClients':clients,'pebBranch':selector,'patched':patched,'reservationBytes':reservations[0],
                'nativeAllocationCalls':len(requests),'completeBackingCanaries':True,'nativeGrowthCalls':0}

    for clients in (1,2):
        for selector in range(16):
            stock=execute(clients,selector,False);expanded=execute(clients,selector,True)
            assert expanded['reservationBytes']-stock['reservationBytes']==BANK_OFFSET
            cases.extend((stock,expanded))
    stale_refusals=0
    for clients in (1,2):
        try:execute(clients,0,True,True)
        except Exhausted:stale_refusals+=1
        else:raise AssertionError('A stale measured reserve escaped native exhaustion.')
    output.parent.mkdir(parents=True,exist_ok=True)
    binary=output.with_suffix('.hunk.bin');binary.write_bytes(last_backing)
    paths=(Path(__file__),PATCHES/'client_allocator.py',PATCHES/'client_actors.py',PATCHES/'captured_code.py',PATCHES/'x64_table.py')
    result={'passed':True,'cases':cases,'providerGuardRefusals':len(mutations),'staleReserveRefusals':stale_refusals,
            'additionalReserveBytes':BANK_OFFSET,'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
            'artifact':{'path':str(binary),'sha256':hashlib.sha256(last_backing).hexdigest()},'gameWrites':0,'activationAllowed':False,
            'scope':'Captured two-pass client caller, allocator/setup tail, and native measuring/fixed-backing providers. Outer components, OS backing/clear APIs and auxiliary initialization are authored. No game or OS allocator admission.'}
    output.write_text(json.dumps(result,indent=2)+'\n')
    return {key:result[key] for key in ('passed','providerGuardRefusals','staleReserveRefusals','additionalReserveBytes')}|{'cases':len(cases),'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.dependencies,args.output)))
