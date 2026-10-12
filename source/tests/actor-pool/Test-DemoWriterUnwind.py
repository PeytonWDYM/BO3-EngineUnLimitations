"""Export native demo writer contexts for the existing owned Windows caller-frame fixture."""
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
from demo_writer import DemoWriter,prepare_demo_writer,WRITER,METADATA


def run(module: Path,executable: Path,dependencies: Path,output: Path,actors: int) -> dict:
    sys.path.insert(0,str(dependencies))
    import capstone
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
    import unicorn.x86_const as x64
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab output directory.')
    code=CapturedCode(module,executable);layout=DemoWriter(code.base+0x32000000,ActorShape(actors))
    edits=prepare_demo_writer(code,layout,code.base+0x201F0000)
    original=code.guarded(WRITER);old_metadata=code.guarded(METADATA)
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    stack,stop=0x50000000,0x51000000;entry_rsp=stack+0x1F008;return_pc=0x1234567812345678
    names=('RAX','RCX','RDX','RBX','RSP','RBP','RSI','RDI','R8','R9','R10','R11','R12','R13','R14','R15')
    registers=[getattr(x64,'UC_X86_REG_'+name) for name in names]
    vectors=[getattr(x64,'UC_X86_REG_XMM'+str(index)) for index in range(16)]
    expected=[0x100000000+index for index in range(16)]
    xmm=[(index<<120)|0x112233445566778899 for index in range(16)]
    data=bytearray(b'BO3CFUW2'+struct.pack('<I',2));cases=[]
    for expanded in (False,True):
        body=bytearray(original);metadata=old_metadata
        if expanded:
            for edit in edits:
                if WRITER.rva<=edit.guard.rva<WRITER.rva+WRITER.size:
                    offset=edit.guard.rva-WRITER.rva;body[offset:offset+edit.guard.size]=edit.replacement
                elif edit.guard.rva==METADATA.rva:metadata=edit.replacement
        instructions=list(decoder.disasm(body,code.base+WRITER.rva));assert sum(i.size for i in instructions)==len(body)
        engine=Uc(UC_ARCH_X86,UC_MODE_64)
        for page in (code.base+0x25CE000,code.base+0x35EE000,code.base+(0x2BC3AA0&~4095)):engine.mem_map(page,4096)
        engine.mem_map(stack,0x20000);engine.mem_map(stop,4096)
        engine.mem_write(code.base+WRITER.rva,bytes(body));engine.mem_write(stack,b'\xcc'*0x20000)
        engine.mem_write(entry_rsp,struct.pack('<Q',return_pc));cookie=0x123456780CACEBAD
        engine.mem_write(code.base+0x35EEA10,struct.pack('<Q',cookie))
        for register,value in zip(registers,expected):engine.reg_write(register,value)
        for register,value in zip(vectors,xmm):engine.reg_write(register,value)
        engine.reg_write(x64.UC_X86_REG_RSP,entry_rsp);contexts={}
        def snapshot(current,address,size,unused):
            if code.base+WRITER.rva<=address<code.base+WRITER.rva+len(body):
                contexts[address]=([current.reg_read(register) for register in registers],[current.reg_read(register) for register in vectors])
            elif address==code.base+0x2BC3AA0:
                assert current.reg_read(x64.UC_X86_REG_RCX)==cookie
                rsp=current.reg_read(x64.UC_X86_REG_RSP);pc=struct.unpack('<Q',current.mem_read(rsp,8))[0]
                current.reg_write(x64.UC_X86_REG_RSP,rsp+8);current.reg_write(x64.UC_X86_REG_RIP,pc)
        engine.hook_add(UC_HOOK_CODE,snapshot)
        engine.emu_start(code.base+WRITER.rva,code.base+0x25CEA01,count=100)
        body_state=([engine.reg_read(register) for register in registers],[engine.reg_read(register) for register in vectors])
        engine.emu_start(code.base+0x25CEC58,return_pc,count=100)
        assert engine.reg_read(x64.UC_X86_REG_RSP)==entry_rsp+8
        for instruction in instructions:contexts.setdefault(instruction.address,body_state)
        helper=next(edit.stub for edit in edits if edit.stub) if expanded else b''
        helper_controls=[instruction.address for instruction in decoder.disasm(helper,0)]
        data+=struct.pack('<7I',len(body),len(metadata),len(old_metadata),len(contexts),int(expanded),len(helper),len(helper_controls))
        data+=body+metadata+old_metadata+bytes(engine.mem_read(stack,0x20000))
        for instruction in instructions:
            gprs,simd=contexts[instruction.address]
            data+=struct.pack('<I16Q',instruction.address-code.base-WRITER.rva,*gprs)
            data+=b''.join(value.to_bytes(16,'little') for value in simd)
        data+=helper+b''.join(struct.pack('<I',control) for control in helper_controls)
        cases.append({'expanded':expanded,'contexts':len(contexts),'helperContexts':len(helper_controls),
                      'executedPrologEpilog':True,'bodyContextsUseCanonicalFrame':True})
    output.mkdir(parents=True);(output/'caller-unwind.bin').write_bytes(data)
    paths=(Path(__file__),PATCHES/'demo_writer.py',PATCHES/'native_unwind.py',PATCHES/'native_handlers.py',PATCHES/'native_handlers.json',PATCHES/'x64_table.py',PATCHES/'shape.py',PATCHES/'captured_code.py')
    receipt={'passedExport':True,'cases':cases,'actors':actors,'fixtureSha256':hashlib.sha256(data).hexdigest(),
             'sourceFiles':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},'gameWrites':0,'activationAllowed':False,
             'scope':'Captured native demo prolog/epilogue with original-width edits. Canonical body and leaf-call frames, omitted handlers, and authored cookie endpoint. Native game handler and game registration remain separate.'}
    (output/'input-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return {'passedExport':True,'contexts':sum(case['contexts'] for case in cases),'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=500)
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.dependencies,args.output,args.actors)))
