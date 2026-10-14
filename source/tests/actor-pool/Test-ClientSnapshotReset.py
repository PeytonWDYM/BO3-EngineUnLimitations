"""Replay both captured client-clear paths and complete external snapshot resets."""
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
from client_snapshots import ClientSnapshots
from client_snapshot_reset import prepare_client_snapshot_resets


def run(module: Path,executable: Path,dependencies: Path,output: Path,actors: int) -> dict:
    sys.path.insert(0,str(dependencies))
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
    import unicorn.x86_const as x64
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new result file in the private BO3 lab.')
    code=CapturedCode(module,executable)
    layout=ClientSnapshots(code.base+0x2E000000,ActorShape(actors))
    helpers=code.base+0x201D0000
    frames=prepare_client_snapshot_resets(code,layout,helpers)
    cg,control,stack,stop=0x10000000,0x18000000,0x20000000,0x30000000
    native_bytes=0x342720
    heap_bytes=4*native_bytes+32
    cases=[]
    for shutdown in (False,True):
        for client in range(2):
            engine=Uc(UC_ARCH_X86,UC_MODE_64)
            for rva in (0x8F0000,0x92E000,0x2BC5000):
                engine.mem_map(code.base+rva,4096)
                engine.mem_write(code.base+rva,code.read(rva,4096))
            engine.mem_map(helpers,4096)
            for frame in frames:
                edit=frame.rewrite
                engine.mem_write(code.base+edit.guard.rva,edit.replacement)
                engine.mem_write(edit.stub_address,edit.stub)
            for address,size in ((cg,(heap_bytes+4095)&~4095),(control,4096),(stack,0x10000),(stop,4096),
                                 (layout.base,(layout.total_bytes+4095)&~4095)):
                engine.mem_map(address,size)
            clears=[]

            def clear(current,address,size,unused):
                target=current.reg_read(x64.UC_X86_REG_RCX)
                count=current.reg_read(x64.UC_X86_REG_R8)
                assert current.reg_read(x64.UC_X86_REG_RDX)==0
                assert current.reg_read(x64.UC_X86_REG_RSP)&15==8
                current.mem_write(target,bytes(count));clears.append((target,count))
                for name in ('RCX','RDX','R8','R9','R10','R11'):
                    current.reg_write(getattr(x64,'UC_X86_REG_'+name),0xBAD00000)
                current.reg_write(x64.UC_X86_REG_RAX,target)
                rsp=current.reg_read(x64.UC_X86_REG_RSP)
                pc=struct.unpack('<Q',current.mem_read(rsp,8))[0]
                current.reg_write(x64.UC_X86_REG_RSP,rsp+8)
                current.reg_write(x64.UC_X86_REG_RIP,pc)

            engine.hook_add(UC_HOOK_CODE,clear,begin=code.base+0x2BC53B0,end=code.base+0x2BC53B0)
            for iteration in range(2):
                clears.clear()
                engine.mem_write(cg,b'\x5a'*heap_bytes)
                engine.mem_write(layout.base,b'\xa5'*layout.total_bytes)
                current_cg=cg+16+client*native_bytes
                engine.reg_write(x64.UC_X86_REG_RSI,current_cg)
                engine.reg_write(x64.UC_X86_REG_R14,client)
                engine.reg_write(x64.UC_X86_REG_R9,0xBAD00001)
                body_rsp=stack+0xFE00
                engine.reg_write(x64.UC_X86_REG_RSP,body_rsp)
                if shutdown:
                    saved={name:0x55550000+index for index,name in enumerate(('R15','R14','R13','R12','RDI','RSI','RBX','RBP'))}
                    for index,(name,value) in enumerate(saved.items()):
                        engine.mem_write(body_rsp+0x28+index*8,struct.pack('<Q',value))
                    engine.mem_write(body_rsp+0x68,struct.pack('<Q',stop))
                    engine.mem_write(body_rsp+0x70,struct.pack('<I',client))
                    engine.reg_write(x64.UC_X86_REG_RBP,body_rsp+0x28)
                    engine.reg_write(x64.UC_X86_REG_RBX,control)
                    engine.reg_write(x64.UC_X86_REG_RDI,0x12345678)
                    engine.reg_write(x64.UC_X86_REG_RAX,0x2F8)
                    engine.emu_start(code.base+0x92EBE9,stop,count=1000)
                    assert engine.reg_read(x64.UC_X86_REG_RSP)==body_rsp+0x70
                    assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in saved.items())
                else:
                    saved={name:engine.reg_read(getattr(x64,'UC_X86_REG_'+name)) for name in ('RBX','RBP','RSI','RDI','R12','R13','R14','R15')}
                    engine.emu_start(code.base+0x8F0AA9,code.base+0x8F0AB9,count=1000)
                    assert engine.reg_read(x64.UC_X86_REG_RSP)==body_rsp
                    assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in saved.items())
                assert engine.reg_read(x64.UC_X86_REG_RAX)==current_cg
                target=layout.base+client*layout.client_bytes
                actor_bank=current_cg+2*native_bytes
                assert clears==[(current_cg,native_bytes),(target,layout.client_bytes),(actor_bank,native_bytes)]
                expected_cg=bytearray(b'\x5a'*heap_bytes)
                expected_cg[current_cg-cg:current_cg-cg+native_bytes]=bytes(native_bytes)
                expected_cg[actor_bank-cg:actor_bank-cg+native_bytes]=bytes(native_bytes)
                expected_snapshots=bytearray(b'\xa5'*layout.total_bytes)
                expected_snapshots[client*layout.client_bytes:(client+1)*layout.client_bytes]=bytes(layout.client_bytes)
                assert engine.mem_read(cg,heap_bytes)==expected_cg
                assert engine.mem_read(layout.base,layout.total_bytes)==expected_snapshots
                cases.append({'case':'shutdown-tail' if shutdown else 'startup-call','localClient':client,
                              'iteration':iteration,'completeClears':3,'otherClientIntact':True})

    class ChangedCode(CapturedCode):
        def read(self,rva: int,size: int) -> bytes:
            raw=bytearray(super().read(rva,size))
            if rva<=self.mutation<rva+size:raw[self.mutation-rva]^=1
            return bytes(raw)
    mutations=(0x8ED490,0x8ED4CF,0x8F0AB4,0x926D90,0x92EC08,0x31164A8,0x31164D0)
    for mutation in mutations:
        altered=object.__new__(ChangedCode);altered.__dict__.update(code.__dict__);altered.mutation=mutation
        try:prepare_client_snapshot_resets(altered,layout,helpers)
        except ValueError:pass
        else:raise AssertionError('An altered client clear owner escaped refusal.')
    refusals=0
    for base,entry in ((code.base,helpers),(layout.base,code.base),(helpers,helpers),
                       (layout.base,layout.base+layout.total_bytes-512),(layout.base,code.base+0x100000000),
                       (layout.base,helpers+1)):
        try:prepare_client_snapshot_resets(code,ClientSnapshots(base,layout.shape),entry)
        except ValueError:refusals+=1
        else:raise AssertionError('An invalid client clear binding escaped refusal.')
    result={'passed':True,'actors':actors,'cases':cases,'guardRefusals':len(mutations),'addressRefusals':refusals,
            'helperFrames':[{'bytes':len(frame.rewrite.stub),'unwind':frame.unwind.hex()} for frame in frames],
            'snapshotBytesClearedPerLocalClient':layout.client_bytes,'gameWrites':0,'activationAllowed':False,
            'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in
                       (Path(__file__),PATCHES/'client_snapshot_reset.py',PATCHES/'client_snapshots.py',
                        PATCHES/'shape.py',PATCHES/'captured_code.py',PATCHES/'x64_table.py',PATCHES/'client_actors.py')},
            'scope':'Owned replay of captured startup clear and shutdown epilogue. Native memset endpoint is authored. Complete native callers and game lifetime remain required.'}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n')
    return {'passed':True,'actors':actors,'cases':len(cases),'guardRefusals':len(mutations),'addressRefusals':refusals,'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=500)
    args=parser.parse_args()
    print(json.dumps(run(args.module,args.executable,args.dependencies,args.output,args.actors)))
