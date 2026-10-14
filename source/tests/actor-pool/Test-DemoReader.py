"""Replay full native demo reset/playback/rebroadcast against real writer packet artifacts."""
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
from demo_writer import DemoWriter
from demo_reader import prepare_demo_reader
from actor_wire import prepare_actor_wire


def run(module: Path,executable: Path,dependencies: Path,writer: Path,output: Path) -> dict:
    sys.path.insert(0,str(dependencies))
    import capstone
    from unicorn import Uc,UcError,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
    import unicorn.x86_const as x64
    output=output.resolve();lab=(Path.home()/'.codex/labs/bo3-engine').resolve()
    if lab not in output.parents or output.exists() or lab not in writer.resolve().parents:
        raise ValueError('Use a new private BO3 lab result and a private writer receipt.')
    report=json.loads(writer.read_text());artifact=Path(report['artifact']['path']);raw=artifact.read_bytes()
    assert lab in artifact.resolve().parents
    assert report['passed'] and hashlib.sha256(raw).hexdigest()==report['artifact']['sha256']
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in report['sources'].items())
    assert raw[:8]==b'BO3DMAP1';actors,frames=struct.unpack_from('<II',raw,8);position=16;packets=[]
    for frame in range(frames):
        size,count=struct.unpack_from('<II',raw,position);position+=8
        packet=raw[position:position+size];position+=size
        records=[raw[position+index*80:position+(index+1)*80] for index in range(count)];position+=count*80
        packets.append((packet,records))
    assert position==len(raw) and frames==6 and actors==report['actors']
    code=CapturedCode(module,executable);shape=ActorShape(actors);storage=DemoWriter(code.base+0x32000000,shape)
    edits=prepare_demo_reader(code,storage);wire=prepare_actor_wire(code,shape)
    assert len(edits)==4 and all(not edit.stub and edit.guard.size==len(edit.replacement) for edit in edits)
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    pages=set(range(0x20F0000,0x2130000,4096))
    pages.update(edit.guard.rva&~4095 for edit in (*wire,*edits))
    pages.update(range(0x19578000,0x196CA000,4096));pages.update((0x35EE000,0x33A3000,0x2FC6000,0x33B1000,0x24AE000))
    for start,size in ((0x25A4D40,1730),(0x25A9AB0,155)):
        pages.update(range(start&~4095,(start+size+4095)&~4095,4096))
        for instruction in decoder.disasm(code.read(start,size),code.base+start):
            for operand in instruction.operands:
                if operand.type==capstone.x86.X86_OP_MEM and operand.mem.base==capstone.x86.X86_REG_RIP:
                    pages.add((instruction.address+instruction.size+operand.mem.disp-code.base)&~4095)
    endpoints=(0x71BD0,0x2595F90,0x2BC53B0,0x2BC3AA0,0x2587760,0x227B480,0x227B490)
    pages.update(address&~4095 for address in endpoints)
    native={page:code.read(page,4096) for page in sorted(pages)}
    data,stack,stop,connection,ring,context=0x10000000,0x20000000,0x30000000,0x60000000,0x70000000,0x80000000
    msg,buffer=data,data+0x1000;cookie=0x123456780CACEBAD
    saved={name:0x66660000+index for index,name in enumerate(('RBX','RBP','RSI','RDI','R12','R13','R14','R15'))}
    fields=(0,4,8,12,16,20,24,28,32,36,40,44,52,72,76)
    final_storage=b''
    class PlaybackLost(AssertionError):pass

    def execute(mode: int,legacy: str='') -> dict:
        nonlocal final_storage
        engine=Uc(UC_ARCH_X86,UC_MODE_64)
        for page,body in native.items():engine.mem_map(code.base+page,4096);engine.mem_write(code.base+page,body)
        for address,size in ((data,0x100000),(stack,0x20000),(stop,4096),(connection,0x10000),(ring-4096,0xA2000),
                             (context,0xAA0000),(storage.base-4096,((storage.bytes+16+4095)&~4095)+4096)):
            engine.mem_map(address,size)
        for edit in (*wire,*edits):
            if edit.name==legacy:continue
            engine.mem_write(code.base+edit.guard.rva,edit.replacement)
        engine.mem_write(storage.base-16,b'\xa5'*(storage.bytes+32));engine.mem_write(ring-16,b'\xcc'*(0xA0000+32))
        engine.mem_write(code.base+0x19578760,b'\xcc'*0x1502B0)
        engine.mem_write(code.base+0x1976CA80,struct.pack('<Q',context));engine.mem_write(code.base+0x1976CA88,bytes([int(mode==2)]))
        engine.mem_write(context,bytes(4));engine.mem_write(context+0xA97524,struct.pack('<I',mode))
        engine.mem_write(context+0xA74D70,b'\xcc'*0xB570);engine.mem_write(code.base+0x35EEA10,struct.pack('<Q',cookie))
        engine.mem_write(connection+0x50,struct.pack('<QI',ring,8192));clears=[]
        def endpoint(current,address,size,unused):
            rcx=current.reg_read(x64.UC_X86_REG_RCX);result=0
            if address==code.base+0x71BD0:assert rcx==0;result=connection
            elif address==code.base+0x2595F90:result=mode
            elif address in (code.base+0x227B480,code.base+0x227B490):result=rcx&0xFFFFFFFF
            elif address==code.base+0x2BC3AA0:assert rcx==cookie
            elif address==code.base+0x2BC53B0:
                length=current.reg_read(x64.UC_X86_REG_R8);value=current.reg_read(x64.UC_X86_REG_RDX)&255
                clears.append((rcx,length,value));current.mem_write(rcx,bytes([value])*length);result=rcx
            if address!=code.base+0x2BC3AA0:
                for name in ('RCX','RDX','R8','R9','R10','R11'):current.reg_write(getattr(x64,'UC_X86_REG_'+name),0xBAD00000)
                current.reg_write(x64.UC_X86_REG_RAX,result)
            rsp=current.reg_read(x64.UC_X86_REG_RSP);pc=struct.unpack('<Q',current.mem_read(rsp,8))[0]
            current.reg_write(x64.UC_X86_REG_RSP,rsp+8);current.reg_write(x64.UC_X86_REG_RIP,pc)
        for address in endpoints:engine.hook_add(UC_HOOK_CODE,endpoint,begin=code.base+address,end=code.base+address)
        def call(rva: int,args: tuple[int,...]) -> int:
            rsp=stack+0x1F008;engine.mem_write(rsp,struct.pack('<Q',stop)+bytes(0xF0));engine.reg_write(x64.UC_X86_REG_RSP,rsp)
            for name,value in saved.items():engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
            for name,value in zip(('RCX','RDX','R8','R9'),args):engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
            try:engine.emu_start(code.base+rva,stop,count=2000000)
            except UcError as error:
                raise PlaybackLost(f'Native demo replay fault at {engine.reg_read(x64.UC_X86_REG_RIP)-code.base:#x}, mode {mode}, control {legacy}.') from error
            assert engine.reg_read(x64.UC_X86_REG_RSP)==rsp+8
            assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in saved.items())
            return engine.reg_read(x64.UC_X86_REG_RAX)&0xFFFFFFFF
        call(0x25A9AB0,())
        expected_clears=[(code.base+0x19578760,0x1502A0,0),(code.base+0x19644C00,0x7C000,255),
                         (code.base+0x196C3C08,0x39F0,255),(storage.base,storage.bytes,255)]
        if mode==2:expected_clears.append((context+0xA74D70,0xB570,0))
        assert clears==expected_clears and engine.mem_read(storage.base,storage.bytes)==b'\xff'*storage.bytes
        expected_scratch=bytearray(0x1502A0)
        for address,length,value in expected_clears[1:3]:expected_scratch[address-code.base-0x19578760:address-code.base-0x19578760+length]=bytes([value])*length
        assert engine.mem_read(code.base+0x19578760,0x1502A0)==expected_scratch
        assert engine.mem_read(code.base+0x196C8A00,12)==bytes(12)
        expected_storage=bytearray(b'\xff'*storage.bytes);default=code.read(0x19160098,80);previous=set();cases=[]
        for frame,(packet,records) in enumerate(packets):
            engine.mem_write(msg,bytes(64));engine.mem_write(buffer,packet)
            engine.mem_write(msg+8,struct.pack('<Q',buffer));engine.mem_write(msg+0x18,struct.pack('<I',0x20000));engine.mem_write(msg+0x1C,struct.pack('<I',len(packet)));engine.mem_write(msg+0x2C,struct.pack('<i',-1))
            echo=context+0x984CC8;engine.mem_write(echo,bytes(64));engine.mem_write(echo+8,struct.pack('<Q',context+0x985000))
            engine.mem_write(echo+0x18,struct.pack('<I',0x20000));engine.mem_write(echo+0x2C,struct.pack('<i',-1))
            cursor=struct.unpack('<I',engine.mem_read(connection+0xB788,4))[0]
            assert call(0x25A4D40,(msg,1000,0xFFFFFFFF if frame==0 else 0))==len(records)
            active={struct.unpack_from('<I',record)[0] for record in records}
            for actor in previous-active:expected_storage[actor*80:(actor+1)*80]=default
            for index,record in enumerate(records):
                # The native decoder writes selected fields. Unserialized ring members retain their backing pattern.
                decoded=bytearray(b'\xcc'*80)
                for offset in fields:decoded[offset:offset+4]=record[offset:offset+4]
                actor=struct.unpack_from('<I',record)[0];expected_storage[actor*80:(actor+1)*80]=decoded
                actual=engine.mem_read(ring+((cursor+index)%8192)*80,80)
                if actual!=decoded:
                    differences=[(offset,actual[offset:offset+4].hex(),decoded[offset:offset+4].hex()) for offset in range(0,80,4) if actual[offset:offset+4]!=decoded[offset:offset+4]]
                    raise PlaybackLost(f'Native demo ring differs at mode {mode}, frame {frame}, actor {actor}: {differences}.')
            if engine.mem_read(storage.base,storage.bytes)!=expected_storage:raise PlaybackLost('The native indexed demo records differ from the real writer records.')
            if engine.mem_read(code.base+0x196C75FC,0x1400)!=bytes(0x1400):raise PlaybackLost('The native reader still writes the old inline actor records.')
            assert engine.mem_read(storage.base-16,16)==b'\xa5'*16 and engine.mem_read(storage.base+storage.bytes,16)==b'\xa5'*16
            assert engine.mem_read(ring-16,16)==b'\xcc'*16 and engine.mem_read(ring+0xA0000,16)==b'\xcc'*16
            assert engine.mem_read(code.base+0x196C89FC,4)==struct.pack('<I',len(records))
            assert engine.mem_read(connection+0xB788,4)==struct.pack('<I',cursor+len(records))
            if mode==2:
                size=struct.unpack('<I',engine.mem_read(echo+0x1C,4))[0]
                assert engine.mem_read(context+0x985000,size)==packet
            cases.append({'frame':frame,'activeActors':len(records),'rebroadcastChecked':mode==2});previous=active
        final_storage=bytes(engine.mem_read(storage.base,storage.bytes))
        return {'mode':mode,'frames':cases,'fullResetRequests':len(expected_clears)}
    cases=[execute(mode) for mode in (0,2)];controls=[]
    for legacy in ('demo_reader_actor_bits','demo_reader_prior_records'):
        try:execute(0,legacy)
        except (PlaybackLost,UcError) as error:controls.append({'unchangedInstruction':legacy,'failure':str(error)})
        else:raise AssertionError('A stock demo reader dependency preserved expanded playback.')
    class ChangedCode(CapturedCode):
        def read(self,rva: int,size: int) -> bytes:
            body=bytearray(super().read(rva,size))
            if rva<=self.mutation<rva+size:body[self.mutation-rva]^=1
            return bytes(body)
    mutations=(0x25A4D40,0x25A4E50,0x25A5055,0x31DB6C0,0x31DB6E0,0x25A9AB0,0x25A9AF2,0x25A9AF9,0x31DABD4)
    for mutation in mutations:
        changed=object.__new__(ChangedCode);changed.__dict__.update(code.__dict__);changed.mutation=mutation
        try:prepare_demo_reader(changed,storage)
        except ValueError:pass
        else:raise AssertionError('An altered demo reader/reset owner escaped refusal.')
    invalid_storage=(code.base,0,storage.base+1,code.base+0x90000000,0x800000000000-4096)
    for address in invalid_storage:
        try:prepare_demo_reader(code,DemoWriter(address,shape))
        except ValueError:pass
        else:raise AssertionError('An invalid complete demo storage interval escaped refusal.')
    output.parent.mkdir(parents=True,exist_ok=True);binary=output.with_suffix('.prior-records.bin');binary.write_bytes(final_storage)
    paths=(Path(__file__),PATCHES/'demo_reader.py',PATCHES/'demo_writer.py',PATCHES/'actor_wire.py',PATCHES/'native_unwind.py',PATCHES/'native_handlers.py',PATCHES/'native_handlers.json',PATCHES/'x64_table.py',PATCHES/'shape.py',PATCHES/'captured_code.py')
    result={'passed':True,'actors':actors,'cases':cases,'stockControlsRefused':controls,'guardRefusals':len(mutations),
            'addressRefusals':len(invalid_storage),
            'writerReceiptSha256':hashlib.sha256(writer.read_bytes()).hexdigest(),'writerArtifactSha256':hashlib.sha256(raw).hexdigest(),
            'sourceFiles':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
            'artifact':{'path':str(binary),'sha256':hashlib.sha256(final_storage).hexdigest()},'activationAllowed':False,'gameWrites':0,
            'scope':'Complete captured native demo reader/reset and rebroadcast. Connection/context, storage, clear/cookie, demo mode, little-endian long dispatch, and field-flag APIs are authored. Game handlers, full callers, save behavior, and peers remain.'}
    output.write_text(json.dumps(result,indent=2)+'\n');return {'passed':True,'actors':actors,'frames':12,'guardRefusals':len(mutations),'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','writer','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.dependencies,args.writer,args.output)))
