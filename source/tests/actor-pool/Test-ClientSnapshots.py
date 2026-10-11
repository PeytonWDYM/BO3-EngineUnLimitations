"""Replay captured snapshot selection, export, and actor lookup in owned memory."""
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
from client_snapshots import ClientSnapshots,prepare_client_snapshots


def run(module: Path,executable: Path,dependencies: Path,output: Path,actors: int) -> dict:
    sys.path.insert(0,str(dependencies))
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_64
    import unicorn.x86_const as x64
    output=output.resolve()
    artifact=output.with_name(output.name+'.snapshot.bin')
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists() or artifact.exists():
        raise ValueError('Use a new result file in the private BO3 lab.')
    code=CapturedCode(module,executable)
    layout=ClientSnapshots(code.base+0x2E000000,ActorShape(actors))
    stub_base=code.base+0x201C0000
    edits=prepare_client_snapshots(code,layout,stub_base)
    cg,connection,row,ring,stack=0x10000000,0x18000000,0x18001000,0x1A000000,0x20000000
    cases=[]
    capacity=actors+13
    record=lambda index:struct.pack('<20I',index,(index+11)%1024,*((index*0x10001)^word for word in range(2,20)))
    ring_bytes=b''.join(record(index) for index in range(capacity))

    def machine(patched: bool=True,count_only: bool=False):
        engine=Uc(UC_ARCH_X86,UC_MODE_64)
        for rva in (0xFC5000,0x1321000,0xFDC000):
            engine.mem_map(code.base+rva,4096)
            engine.mem_write(code.base+rva,code.read(rva,4096))
        engine.mem_map(stub_base,4096)
        if patched:
            for edit in edits:
                if count_only and edit.name!='client_snapshot_actor_clamp':continue
                engine.mem_write(code.base+edit.guard.rva,edit.replacement)
                if edit.stub:engine.mem_write(edit.stub_address,edit.stub)
        for address,size in ((cg,0x700000),(connection,0x10000),(ring,0x20000),(stack,0x10000),
                             (layout.base,(layout.total_bytes+4095)&~4095)):
            engine.mem_map(address,size)
        engine.mem_write(cg,b'\x5a'*0x700000)
        engine.mem_write(layout.base,b'\xa5'*layout.total_bytes)
        engine.mem_write(ring,ring_bytes)
        engine.mem_write(connection+0x50,struct.pack('<Qi',ring,capacity))
        engine.mem_write(stack+0xFF60,struct.pack('<Q',0x123456789ABCDEF0))
        return engine

    def selected(engine,client: int,current: int,retry: bool=False) -> int:
        first=layout.base+client*layout.client_bytes
        engine.mem_write(cg+client*0x342720+0x28,struct.pack('<Q',current))
        engine.mem_write(connection+0x28,struct.pack('<I',100))
        seeds={'R14':cg+client*0x342720,'R15':client,'RBX':connection,'RSP':stack+0xFF00}
        for name,value in seeds.items():engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
        if retry:engine.reg_write(x64.UC_X86_REG_RSI,first)
        engine.emu_start(code.base+(0xFC57E0 if retry else 0xFC57D5),code.base+0xFC5803,count=1000)
        expected=first+(layout.snapshot_bytes if current==first else 0)
        assert engine.reg_read(x64.UC_X86_REG_RDI)==expected
        assert engine.reg_read(x64.UC_X86_REG_RSI)==first
        assert engine.reg_read(x64.UC_X86_REG_R8)==expected
        assert engine.reg_read(x64.UC_X86_REG_RCX)==client and engine.reg_read(x64.UC_X86_REG_RDX)==101
        assert engine.mem_read(connection+0x28,4)==struct.pack('<I',101)
        assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in seeds.items())
        return expected

    for client in range(2):
        first=layout.base+client*layout.client_bytes
        for current in (0,first,first+layout.snapshot_bytes):
            for retry in (False,True):
                engine=machine();selected(engine,client,current,retry)
                cases.append({'case':'native-slot-selection','localClient':client,'current':hex(current),'retryEntry':retry})

    def copy(engine,target: int,count: int):
        engine.mem_write(row+0xB598,struct.pack('<i',count))
        engine.mem_write(row+0xB5B4,struct.pack('<I',capacity-5))
        for name,value in {'RSI':row,'RDI':target,'R14':connection,'R13':0,'RSP':stack+0xFF00}.items():
            engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
        engine.emu_start(code.base+0x13218CB,code.base+0x13219B8,count=100000)
        assert engine.reg_read(x64.UC_X86_REG_RSP)==stack+0xFF00
        assert engine.reg_read(x64.UC_X86_REG_R12)==0x123456789ABCDEF0

    counts=tuple(dict.fromkeys((-1,0,1,63,64,65,299,300,actors,actors+1)))
    final_snapshot=b''
    for client,slot,count in (*((0,0,count) for count in counts),(0,1,actors),(1,0,actors),(1,1,actors)):
        engine=machine();first=layout.base+client*layout.client_bytes
        current=first if slot else 0
        target=selected(engine,client,current)
        cg_before=bytes(engine.mem_read(cg,0x700000))
        copy(engine,target,count)
        clipped=min(count,actors)
        expected=bytearray(b'\xa5'*layout.total_bytes)
        struct.pack_into('<i',expected,target-layout.base+0xB588,clipped)
        for index in range(max(0,clipped)):
            start=target-layout.base+layout.actor_offset+index*80
            expected[start:start+80]=record((capacity-5+index)%capacity)
        assert engine.mem_read(layout.base,layout.total_bytes)==expected
        assert engine.mem_read(cg,0x700000)==cg_before
        for index in range(max(0,clipped)):
            engine.reg_write(x64.UC_X86_REG_R14,target);engine.reg_write(x64.UC_X86_REG_R15,index)
            engine.emu_start(code.base+0xFDCAD7,code.base+0xFDCAED,count=100)
            assert engine.reg_read(x64.UC_X86_REG_RSI)==target+layout.actor_offset+index*80
            assert engine.reg_read(x64.UC_X86_REG_R8)==((capacity-5+index)%capacity+11)%1024
        cases.append({'case':'native-ring-export','localClient':client,'slot':slot,'inputActors':count,
                      'exportedActors':clipped,'allBytesAndCanaries':True})
        if client==1 and slot==1:final_snapshot=bytes(engine.mem_read(target,layout.snapshot_bytes))

    engine=machine(False);copy(engine,layout.base,actors)
    assert engine.mem_read(layout.base+0xB588,4)==struct.pack('<I',64)
    cases.append({'case':'stock-truncation-detected','exportedActors':64})
    engine=machine(True,True);copy(engine,layout.base,actors)
    assert engine.mem_read(layout.base+0x8D410,16)!=b'\xa5'*16
    cases.append({'case':'count-only-metadata-corruption-detected'})

    class ChangedCode(CapturedCode):
        def read(self,rva: int,size: int) -> bytes:
            raw=bytearray(super().read(rva,size))
            if rva<=self.mutation<rva+size:raw[self.mutation-rva]^=1
            return bytes(raw)

    mutations=(0x1321250,0x13218D6,0x13218F1,0xFDCA50,0xFDCADF,0xFC57D5,0xFC57E0,0xFC57F2,0xFC57FD,
               0x3120D6C,0x3120D7C)
    for mutation in mutations:
        altered=object.__new__(ChangedCode);altered.__dict__.update(code.__dict__);altered.mutation=mutation
        try:prepare_client_snapshots(altered,layout,stub_base)
        except ValueError:pass
        else:raise AssertionError('An altered snapshot owner escaped refusal.')
    address_refusals=0
    for base,stub in ((code.base,stub_base),(layout.base,code.base),(stub_base,stub_base),
                      (layout.base,layout.base+layout.total_bytes-4096),(layout.base,code.base+0x100000000),
                      (layout.base+1,stub_base)):
        try:prepare_client_snapshots(code,ClientSnapshots(base,layout.shape),stub)
        except ValueError:address_refusals+=1
        else:raise AssertionError('An invalid snapshot storage binding escaped refusal.')
    result={'passed':True,'actors':actors,'snapshotBytes':layout.snapshot_bytes,'storageBytes':layout.total_bytes,
            'rewrites':len(edits),'stubs':sum(bool(edit.stub) for edit in edits),'cases':cases,
            'guardRefusals':len(mutations),'addressRefusals':address_refusals,'gameWrites':0,'activationAllowed':False,
            'snapshotArtifact':str(artifact),'snapshotSha256':hashlib.sha256(final_snapshot).hexdigest(),
            'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in
                       (Path(__file__),PATCHES/'client_snapshots.py',PATCHES/'shape.py',PATCHES/'captured_code.py',PATCHES/'x64_table.py')},
            'scope':'Captured selection, export, and address blocks in owned Unicorn memory. Full native caller, reset/copy paths, connection allocation, actor client storage, and peers remain required.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    artifact.write_bytes(final_snapshot)
    output.write_text(json.dumps(result,indent=2)+'\n')
    return {'passed':True,'actors':actors,'cases':len(cases),'guardRefusals':len(mutations),'addressRefusals':address_refusals,'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=500)
    args=parser.parse_args()
    print(json.dumps(run(args.module,args.executable,args.dependencies,args.output,args.actors)))
