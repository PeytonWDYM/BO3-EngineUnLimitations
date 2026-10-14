"""Replay measured native connection allocations and actor packets through a complete retained ring."""
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
from client_allocator import prepare_client_allocation
from actor_wire import prepare_actor_wire
from client_actor_ring import prepare_client_actor_ring,RING_RECORDS


def run(module: Path,executable: Path,dependencies: Path,output: Path,actors: int) -> dict:
    sys.path.insert(0,str(dependencies))
    import capstone
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
    import unicorn.x86_const as x64
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab result file.')
    code=CapturedCode(module,executable);shape=ActorShape(actors)
    helper=code.base+0x201E0000
    allocation=prepare_client_allocation(code,helper)
    ring_edits=prepare_client_actor_ring(code,shape);wire=prepare_actor_wire(code,shape)
    assert len(ring_edits)==2 and all(not edit.stub and len(edit.replacement)==edit.guard.size for edit in ring_edits)
    assert RING_RECORDS>=16*actors and RING_RECORDS*80==655360
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True;decoder.skipdata=True
    pages=set(range(0x20F0000,0x2130000,4096))
    for first,last in ((0x8408F0,0x843BD0),(0x85B990,0x85D308),(0x135D330,0x135D4D2),
                       (0x13484E0,0x134B8FC),(0x14D4720,0x14D482A),(0x13655C0,0x136596E),
                       (0x2276D50,0x22770B3),(0x2277190,0x2277213),(0x22773A0,0x2277512)):
        pages.update(range(first&~4095,(last+4095)&~4095,4096))
        for instruction in decoder.disasm(code.read(first,last-first),code.base+first):
            if instruction.id==0:continue
            for operand in instruction.operands:
                if operand.type==capstone.x86.X86_OP_MEM and operand.mem.base==capstone.x86.X86_REG_RIP:
                    rva=instruction.address+instruction.size+operand.mem.disp-code.base
                    if 0<=rva<code.meta['imageSize']:pages.add(rva&~4095)
    pages.update((0x495A000,0x17E82000,0x49B2000,0x4C98000,0x4C9F000,0x35EE000,0x33A3000,0x2FC6000,0x33B1000,0x24AE000))
    # The native connection constructor clears a complete static auxiliary table at this typed RIP binding.
    pages.update(range(0x56A3000,0x56BC000,4096))
    endpoints=(0x14ED6C0,0x135DC20,0x23F8200,0xB24C0,0x20C4E80,0x20C5EE0,0x20C4F10,
               0x2250600,0x2250750,0x2BC53B0,0x2BC3AA0,0x2587760,0x20EC0B0)
    pages.update(address&~4095 for address in endpoints)
    native_pages={page:code.read(page,4096) for page in sorted(pages)}
    data,stack,stop,teb,heap=0x10000000,0x20000000,0x30000000,0x40000000,0x50000000
    msg,buffer,info,old,new=data,data+0x1000,data+0x21000,data+0x22000,data+0x23000
    cookie=0x123456780CACEBAD
    cases=[];final_ring=b''
    class HistoryLost(AssertionError):pass
    class BackingMismatch(AssertionError):pass

    def execute(clients: int,selector: int,expanded: bool,count_only: bool=False) -> dict:
        nonlocal final_ring
        engine=Uc(UC_ARCH_X86,UC_MODE_64)
        for page,raw in native_pages.items():engine.mem_map(code.base+page,4096);engine.mem_write(code.base+page,raw)
        for address,size in ((data,0x100000),(stack,0x20000),(stop,4096),(teb,0x20000),(helper,4096)):
            engine.mem_map(address,size)
        engine.mem_write(helper,allocation.stub)
        selected=ring_edits[1:] if count_only else ring_edits if expanded else ()
        for edit in (allocation,*wire,*selected):engine.mem_write(code.base+edit.guard.rva,edit.replacement)
        engine.mem_write(teb+0x30,struct.pack('<Q',teb));engine.mem_write(teb+0x60,struct.pack('<Q',teb+0x10000+selector*4096))
        engine.reg_write(x64.UC_X86_REG_GS_BASE,teb);engine.mem_write(code.base+0x35EEA10,struct.pack('<Q',cookie))
        caller=code.base+0x10000100
        engine.mem_map(caller&~4095,4096);engine.mem_write(caller,b'\xe8'+struct.pack('<i',code.base+0x135D330-(caller+5)))
        reservations=[];requests=[];roots=[];commits=[];allocated=[]

        def callback(current,address,size,unused):
            assert current.reg_read(x64.UC_X86_REG_RSP)&15==8
            rcx=current.reg_read(x64.UC_X86_REG_RCX);rdx=current.reg_read(x64.UC_X86_REG_RDX);r8=current.reg_read(x64.UC_X86_REG_R8)
            result=0
            if address==code.base+0x20C5EE0:
                assert not reservations and rdx==128
                reservations.append(rcx);current.mem_map(heap-4096,((rcx+16+4095)&~4095)+4096)
                current.mem_write(heap-16,b'\xcc'*(rcx+32));result=heap
            elif address==code.base+0x2BC53B0:current.mem_write(rcx,bytes([rdx&255])*r8);result=rcx
            elif address==code.base+0x2BC3AA0:assert rcx==cookie
            elif address in (code.base+0x2250600,code.base+0x2250750):commits.append(address)
            elif address==code.base+0x20EC0B0:raise AssertionError('The native ring exceeded its measured fixed backing.')
            # The native security-cookie leaf preserves the decoder's return value and general registers.
            if address!=code.base+0x2BC3AA0:
                for name in ('RCX','RDX','R8','R9','R10','R11'):current.reg_write(getattr(x64,'UC_X86_REG_'+name),0xBAD00000)
                current.reg_write(x64.UC_X86_REG_RAX,result)
            rsp=current.reg_read(x64.UC_X86_REG_RSP);pc=struct.unpack('<Q',current.mem_read(rsp,8))[0]
            current.reg_write(x64.UC_X86_REG_RSP,rsp+8);current.reg_write(x64.UC_X86_REG_RIP,pc)
        for endpoint in endpoints:engine.hook_add(UC_HOOK_CODE,callback,begin=code.base+endpoint,end=code.base+endpoint)

        def observe(current,address,size,unused):
            if address==code.base+0x22773A0:
                hunk=current.reg_read(x64.UC_X86_REG_RCX);kind=struct.unpack('<I',current.mem_read(hunk,4))[0]
                requests.append((kind,current.reg_read(x64.UC_X86_REG_RDX),current.reg_read(x64.UC_X86_REG_R8)))
            elif address==code.base+0x1348539:roots.append(current.reg_read(x64.UC_X86_REG_RAX))
            else:allocated.append((requests[-1][0],current.reg_read(x64.UC_X86_REG_RAX),requests[-1][1]))
        for target in (0x22773A0,0x1348539,0x22770A5):engine.hook_add(UC_HOOK_CODE,observe,begin=code.base+target,end=code.base+target)

        saved={name:0x66660000+index for index,name in enumerate(('RBX','RBP','RSI','RDI','R12','R13','R14','R15'))}
        for name,value in saved.items():engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
        engine.reg_write(x64.UC_X86_REG_RSP,stack+0x1F000)
        engine.reg_write(x64.UC_X86_REG_RCX,clients);engine.reg_write(x64.UC_X86_REG_RDX,18);engine.reg_write(x64.UC_X86_REG_R8,0)
        engine.emu_start(caller,caller+5,count=1000000)
        assert engine.reg_read(x64.UC_X86_REG_RSP)==stack+0x1F000
        assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in saved.items())
        assert len(roots)==2 and roots[0]==0 and heap<roots[1]<heap+reservations[0]
        half=len(requests)//2
        assert requests[:half]==[(4,size,alignment) for kind,size,alignment in requests[half:]]
        assert all(kind==0 for kind,size,alignment in requests[half:]) and not commits
        records=RING_RECORDS if expanded else 1024
        assert len(allocated)==half and all(kind==0 for kind,pointer,size in allocated)
        extents={pointer:size for kind,pointer,size in allocated if size}
        if not count_only:assert sum(size==records*80 for kind,size,alignment in requests)==2*clients
        connection_root=roots[1]
        snapshots=[];rings=[]
        for client in range(clients):
            connection=connection_root+client*0x197A30
            ring=struct.unpack('<Q',engine.mem_read(connection+0x50,8))[0]
            capacity=struct.unpack('<I',engine.mem_read(connection+0x58,4))[0]
            assert capacity==records and engine.mem_read(connection+0x5C,4)==struct.pack('<I',1024)
            if extents[ring]!=records*80:raise BackingMismatch('The actor ring capacity exceeds its complete native allocation.')
            assert heap<ring<ring+records*80<heap+reservations[0]
            snapshots.append(struct.unpack('<Q',engine.mem_read(connection+0x68,8))[0]);rings.append(ring)
            engine.mem_write(ring-16,b'\xa5'*16);engine.mem_write(ring+records*80,b'\x5a'*16)

        def call(rva: int,args: tuple[int,...],extra: tuple[int,...]=()) -> None:
            rsp=stack+0x1F008;engine.mem_write(rsp,struct.pack('<Q',stop)+bytes(0xF0));engine.reg_write(x64.UC_X86_REG_RSP,rsp)
            for name,value in saved.items():engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
            for name,value in zip(('RCX','RDX','R8','R9'),args):engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
            for index,value in enumerate(extra):engine.mem_write(rsp+0x28+index*8,struct.pack('<Q',value))
            engine.emu_start(code.base+rva,stop,count=1000000)
            assert engine.reg_read(x64.UC_X86_REG_RSP)==rsp+8
            assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in saved.items())

        def record(actor: int,frame: int) -> bytes:
            value=bytearray(80);struct.pack_into('<II',value,0,actor,(actor+frame+1)%1024)
            return bytes(value)
        fields=(0,4,8,12,16,20,24,28,32,36,40,44,52,72,76)
        parsed=0;frame_count=max(18,records//actors+2)
        for client in range(clients):
            connection=connection_root+client*0x197A30;previous=0
            other={i:bytes(engine.mem_read(rings[i],records*80)) for i in range(clients) if i!=client}
            for frame in range(frame_count):
                engine.mem_write(msg,bytes(64));engine.mem_write(buffer,bytes(0x20000))
                engine.mem_write(msg+8,struct.pack('<Q',buffer));engine.mem_write(msg+0x18,struct.pack('<I',0x20000));engine.mem_write(msg+0x2C,struct.pack('<i',-1))
                for actor in range(actors):
                    engine.mem_write(old,record(actor,frame-1) if frame else bytes(80));engine.mem_write(new,record(actor,frame))
                    call(0x21268D0,(info,msg,1000,old),(new,1))
                # Add a zero-filled byte for the authored outer-list terminator.
                count=struct.unpack('<I',engine.mem_read(msg+0x1C,4))[0]
                engine.mem_write(msg+0x1C,struct.pack('<I',count+1));engine.mem_write(msg+0x24,bytes(8));engine.mem_write(msg+0x2C,struct.pack('<i',-1))
                row=snapshots[client]+(frame&15)*0xB5C0
                call(0x13655C0,(connection,msg,1000,previous),(row,))
                assert engine.mem_read(row+0xB598,4)==struct.pack('<I',actors)
                assert engine.mem_read(row+0xB5B4,4)==struct.pack('<I',frame*actors)
                assert engine.mem_read(connection+0xB788,4)==struct.pack('<I',(frame+1)*actors)
                for actor in range(actors):
                    actual=bytes(engine.mem_read(rings[client]+((frame*actors+actor)%records)*80,80));expected=record(actor,frame)
                    assert all(actual[offset:offset+4]==expected[offset:offset+4] for offset in fields)
                oldest=max(0,frame-15)
                for actor in range(actors):
                    actual=bytes(engine.mem_read(rings[client]+((oldest*actors+actor)%records)*80,8))
                    if actual!=record(actor,oldest)[:8]:raise HistoryLost('The native ring lost retained snapshot history.')
                assert engine.mem_read(rings[client]-16,16)==b'\xa5'*16 and engine.mem_read(rings[client]+records*80,16)==b'\x5a'*16
                assert all(engine.mem_read(rings[i],records*80)==before for i,before in other.items())
                previous=row;parsed+=1
            # Sparse changes exercise removal, skipped old records, and the tail copy in the complete native parser.
            expected_rows=[record(actor,frame_count-1) for actor in range(actors) if actor!=64]
            for sparse in (True,False):
                engine.mem_write(msg,bytes(64));engine.mem_write(buffer,bytes(0x20000))
                engine.mem_write(msg+8,struct.pack('<Q',buffer));engine.mem_write(msg+0x18,struct.pack('<I',0x20000));engine.mem_write(msg+0x2C,struct.pack('<i',-1))
                if sparse:
                    for actor in sorted({64,299,actors-1}):
                        engine.mem_write(old,record(actor,frame_count-1));engine.mem_write(new,record(actor,frame_count+1))
                        call(0x21268D0,(info,msg,1000,old),(0 if actor==64 else new,1))
                        if actor!=64:expected_rows[actor-1]=record(actor,frame_count+1)
                count=struct.unpack('<I',engine.mem_read(msg+0x1C,4))[0]
                engine.mem_write(msg+0x1C,struct.pack('<I',count+1));engine.mem_write(msg+0x24,bytes(8));engine.mem_write(msg+0x2C,struct.pack('<i',-1))
                cursor=struct.unpack('<I',engine.mem_read(connection+0xB788,4))[0]
                row=snapshots[client]+((frame_count+(0 if sparse else 1))&15)*0xB5C0
                call(0x13655C0,(connection,msg,1000,previous),(row,))
                assert engine.mem_read(row+0xB598,4)==struct.pack('<I',actors-1),(sparse,struct.unpack('<I',engine.mem_read(row+0xB598,4))[0],actors-1)
                for index,expected in enumerate(expected_rows):
                    actual=bytes(engine.mem_read(rings[client]+((cursor+index)%records)*80,80))
                    assert all(actual[offset:offset+4]==expected[offset:offset+4] for offset in fields)
                assert engine.mem_read(rings[client]-16,16)==b'\xa5'*16 and engine.mem_read(rings[client]+records*80,16)==b'\x5a'*16
                assert all(engine.mem_read(rings[i],records*80)==before for i,before in other.items())
                previous=row;parsed+=1
        assert engine.mem_read(heap-16,16)==b'\xcc'*16 and engine.mem_read(heap+reservations[0],16)==b'\xcc'*16
        final_ring=bytes(engine.mem_read(rings[-1],records*80))
        return {'localClients':clients,'pebBranch':selector,'actors':actors,'frames':parsed,'records':records,
                'reservationBytes':reservations[0],'nativeAllocationCalls':len(requests),'retainedSnapshots':16,'ringWrapChecked':frame_count*actors>records}

    for clients in (1,2):
        for selector in (0,15):cases.append(execute(clients,selector,True))
    try:execute(1,0,False)
    except HistoryLost:stock_refused=True
    else:raise AssertionError('A stock ring preserved sixteen expanded actor snapshots.')
    count_refusals=0
    for clients in (1,2):
        try:execute(clients,0,True,True)
        except BackingMismatch:count_refusals+=1
        else:raise AssertionError('A count-only ring increase escaped native backing validation.')
    class ChangedCode(CapturedCode):
        def read(self,rva: int,size: int) -> bytes:
            raw=bytearray(super().read(rva,size))
            if rva<=self.mutation<rva+size:raw[self.mutation-rva]^=1
            return bytes(raw)
    mutations=(0x13484E0,0x1349EB6,0x134B7B8,0x134B77B,0x312EF28,0x312EF34,0x312EF58,0x312EF6C,0x312EF7C,0x312EF8C,0x312EFB0,0x13655C0,0x3130048)
    for mutation in mutations:
        changed=object.__new__(ChangedCode);changed.__dict__.update(code.__dict__);changed.mutation=mutation
        try:prepare_client_actor_ring(changed,shape)
        except ValueError:pass
        else:raise AssertionError('An altered actor ring dependency escaped refusal.')
    output.parent.mkdir(parents=True,exist_ok=True)
    binary=output.with_suffix('.ring.bin');binary.write_bytes(final_ring)
    paths=(Path(__file__),PATCHES/'client_actor_ring.py',PATCHES/'client_allocator.py',PATCHES/'client_actors.py',PATCHES/'actor_wire.py',PATCHES/'shape.py',PATCHES/'captured_code.py')
    result={'passed':True,'actors':actors,'cases':cases,'guardRefusals':len(mutations),'stockHistoryRefused':stock_refused,'countOnlyRefusals':count_refusals,
            'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
            'artifact':{'path':str(binary),'sha256':hashlib.sha256(final_ring).hexdigest()},'gameWrites':0,'activationAllowed':False,
            'scope':'Native measured allocation/cache/connection constructors and full packet ring parser. Outer components, OS backing/clear/cookie/field-flag APIs and packet-list terminator are authored. Demos, cursor overflow, saves, full callers and peers remain.'}
    output.write_text(json.dumps(result,indent=2)+'\n')
    return {'passed':True,'actors':actors,'cases':len(cases),'frames':sum(case['frames'] for case in cases),'guardRefusals':len(mutations),'stockHistoryRefused':True,'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=500)
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.dependencies,args.output,args.actors)))
