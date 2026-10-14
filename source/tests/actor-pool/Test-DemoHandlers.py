"""Execute native demo prologs and the complete GS handler/cookie validation path in owned memory."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES=Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from captured_code import CapturedCode,CodeGuard
from native_unwind import read_frame
from native_handlers import prepare_native_handler
from demo_writer import DemoWriter,prepare_demo_writer,WRITER,METADATA
from shape import ActorShape

COOKIE=CodeGuard(0x2BC3AA0,31,'e2ffa4ae47cfda2452c6fe15fb18bc6a00332f427e5ead7fb5320cd7bc368cd7')


def run(module: Path,executable: Path,dependencies: Path,output: Path) -> dict:
    sys.path.insert(0,str(dependencies))
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
    import unicorn.x86_const as x64
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab result file.')
    code=CapturedCode(module,executable);inventory=json.loads((PATCHES/'native_handlers.json').read_text())
    helpers=[CodeGuard(int(inventory[name]['rva'],0),inventory[name]['size'],inventory[name]['sha256']) for name in ('handler','common')]
    helpers.append(COOKIE)
    bodies=[(guard,code.guarded(guard)) for guard in helpers]
    cases=[];artifact=bytearray()
    class CookieFailure(AssertionError):pass
    for actors in (64,300,500):
        for reader in ((False,True) if actors==64 else (False,)):
            owner=(0x25A4D40,0x25A5402,0x31DB6C0) if reader else (WRITER.rva,WRITER.rva+WRITER.size,METADATA.rva)
            frame=read_frame(code,owner);recipe=prepare_native_handler(code,frame)
            metadata_size=36 if reader else 40;metadata=code.read(owner[2],metadata_size)
            edits=() if actors==64 else prepare_demo_writer(code,DemoWriter(code.base+0x32000000,ActorShape(actors)),code.base+0x201F0000)
            if actors!=64:metadata=next(edit.replacement for edit in edits if edit.guard.rva==owner[2])
            cookie_offset=0x98 if reader else 0x160+(actors-64)*4
            for control in ('valid','stale-offset','untranslated-frame','offset-only','high-cookie'):
                if actors==64 and control=='stale-offset':continue
                machine=Uc(UC_ARCH_X86,UC_MODE_64)
                stack,call_stack,data,stop=0x50000000,0x51000000,0x49000000,0x52000000
                pages={code.base+0x2BC3000,code.base+0x2BC8000,code.base+0x35EE000,code.base+(owner[2]&~4095)}
                pages.update(range((code.base+owner[0])&~4095,(code.base+owner[1]+4095)&~4095,4096))
                for page in sorted(pages):machine.mem_map(page,4096)
                for address,size in ((stack,0x20000),(call_stack,0x20000),(data,4096),(stop,4096)):machine.mem_map(address,size)
                machine.mem_write(code.base+owner[0],code.read(owner[0],owner[1]-owner[0]))
                machine.mem_write(code.base+owner[2],metadata)
                for edit in edits:
                    if owner[0]<=edit.guard.rva<owner[1]:machine.mem_write(code.base+edit.guard.rva,edit.replacement)
                for guard,body in bodies:machine.mem_write(code.base+guard.rva,body)
                cookie=0x00002A780CACEBAD if control!='high-cookie' else 0x12342A780CACEBAD
                machine.mem_write(code.base+0x35EEA10,struct.pack('<Q',cookie));machine.mem_write(stack,b'\xcc'*0x20000)
                machine.reg_write(x64.UC_X86_REG_RSP,stack+0x1F008);machine.mem_write(stack+0x1F008,struct.pack('<Q',stop))
                end=code.base+(0x25A4D69 if reader else 0x25CEA01)
                machine.emu_start(code.base+owner[0],end,count=100)
                native_frame=machine.reg_read(x64.UC_X86_REG_RSP)
                assert machine.mem_read(native_frame+cookie_offset,8)==struct.pack('<Q',cookie^native_frame)
                handler_data=code.base+owner[2]+metadata_size-4
                actual_frame=native_frame
                if control in ('stale-offset','offset-only'):
                    handler_data=data+0x200;offset=0x160 if control=='stale-offset' else cookie_offset+8
                    machine.mem_write(handler_data,struct.pack('<I',offset))
                if control in ('untranslated-frame','offset-only'):actual_frame-=8
                machine.mem_write(data+8,struct.pack('<Q',code.base));machine.mem_write(data+0x10,struct.pack('<Q',data+0x100))
                machine.mem_write(data+0x38,struct.pack('<Q',handler_data));machine.mem_write(data+0x100,struct.pack('<III',*owner))
                expected={name:0x66660000+index for index,name in enumerate(('RBX','RBP','RSI','RDI','R12','R13','R14','R15'))}
                for name,value in expected.items():machine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
                initial_rsp=call_stack+0x1F008;machine.reg_write(x64.UC_X86_REG_RSP,initial_rsp);machine.mem_write(initial_rsp,struct.pack('<Q',stop))
                for name,value in zip(('RCX','RDX','R8','R9'),(0,actual_frame,0,data)):machine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
                checked=[]
                def observe(current,address,size,unused):
                    if address==code.base+COOKIE.rva:checked.append(current.reg_read(x64.UC_X86_REG_RCX))
                    else:raise CookieFailure('The native cookie leaf reached its failure branch.')
                machine.hook_add(UC_HOOK_CODE,observe,begin=code.base+COOKIE.rva,end=code.base+COOKIE.rva)
                machine.hook_add(UC_HOOK_CODE,observe,begin=code.base+0x2BC87F0,end=code.base+0x2BC87F0)
                refused=False
                try:machine.emu_start(recipe.handler_address,stop,count=1000)
                except CookieFailure:refused=True
                assert refused==(control!='valid') and len(checked)==1
                if not refused:
                    assert checked==[cookie] and machine.reg_read(x64.UC_X86_REG_RAX)==1
                    assert machine.reg_read(x64.UC_X86_REG_RSP)==initial_rsp+8
                    assert all(machine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in expected.items())
                cases.append({'actors':actors,'reader':reader,'control':control,'cookieOffset':cookie_offset,
                              'nativeFailureReached':refused,'nativeCookieInput':hex(checked[0])})
                artifact+=struct.pack('<IIII',actors,int(reader),cookie_offset,len(metadata))+metadata
    class ChangedCode(CapturedCode):
        def read(self,rva: int,size: int) -> bytes:
            body=bytearray(super().read(rva,size))
            if rva<=self.mutation<rva+size:body[self.mutation-rva]^=1
            return bytes(body)
    mutations=(0x2BC3A04,0x2BC3A24,0x2BC3AA0,0x2BC3AB2,0x31DBB24,0x31DB6E0)
    writer_frame=read_frame(code,(WRITER.rva,WRITER.rva+WRITER.size,METADATA.rva))
    reader_frame=read_frame(code,(0x25A4D40,0x25A5402,0x31DB6C0))
    for mutation in mutations:
        changed=object.__new__(ChangedCode);changed.__dict__.update(code.__dict__);changed.mutation=mutation
        try:prepare_native_handler(changed,reader_frame if mutation==0x31DB6E0 else writer_frame)
        except ValueError:pass
        else:raise AssertionError('A changed complete demo GS binding escaped refusal.')
    output.parent.mkdir(parents=True,exist_ok=True);binary=output.with_suffix('.frames.bin');binary.write_bytes(artifact)
    paths=(Path(__file__),PATCHES/'native_handlers.py',PATCHES/'native_handlers.json',PATCHES/'native_unwind.py',PATCHES/'demo_writer.py',PATCHES/'demo_reader.py',PATCHES/'captured_code.py',PATCHES/'x64_table.py',PATCHES/'shape.py')
    result={'passed':True,'cases':cases,'guardRefusals':len(mutations),
            'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
            'artifact':{'path':str(binary),'sha256':hashlib.sha256(artifact).hexdigest()},'gameWrites':0,'activationAllowed':False,
            'scope':'Real native demo prologs, complete GS handler/common/security-cookie leaf, and selected metadata. Dispatcher and failure endpoint are authored. No Windows exception dispatch or game registration.'}
    output.write_text(json.dumps(result,indent=2)+'\n');return {'passed':True,'cases':len(cases),'guardRefusals':len(mutations),'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.dependencies,args.output)))
