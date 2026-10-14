"""Replay cold descriptor admission and the complete captured CRT field initializer."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES=Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from captured_code import CapturedCode,CodeGuard

INITIALIZER=CodeGuard(0x2EE25F0,28801,'3b4cedc2d079abb49634d308f44477b3be79302630fa5ce9d87fd6469955b9d1')
UNWIND=CodeGuard(0x31D3DD4,24,'0cea504bb5b4f565bb7279d925cb4c75eed12d14edda826611e6977660bb9524')
NAME=CodeGuard(0x2FED858,14,'6ba1fd380c6dc0e002a29d0f94ddd8bb87c972b42dc28348bc114dc149b0b2fe')
FINAL=bytes.fromhex('b7dadec62c120000080000000b00000000000000000000000000000000000000')


def run(module: Path,executable: Path,dependencies: Path,output: Path) -> dict:
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new result file in the private BO3 lab.')
    code=CapturedCode(module,executable)
    cold=code.read(0x33FFB20,32)
    if cold!=bytes(32):
        report={'passed':False,'phase':'RED','reason':'Canonical capture still supplies the initialized descriptor at the frozen startup phase.',
                'observedSha256':hashlib.sha256(cold).hexdigest(),'expectedSha256':hashlib.sha256(bytes(32)).hexdigest(),
                'testSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'gameWrites':0}
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
        raise AssertionError('The frozen startup descriptor must be exactly 32 zero bytes.')
    for guard in (INITIALIZER,UNWIND,NAME):code.guarded(guard)
    assert struct.unpack('<Q',code.read(0x2F11F20,8))[0]==code.base+INITIALIZER.rva
    from startup_guards import field_preimages
    # The preimage adapter consumes the pinned raw capture, before its canonical startup bytes replace the initialized field.
    source=code._read_captured
    assert source(0x33FFB20,32)==FINAL
    preimages=field_preimages(source)
    assert (0x33FFB20,bytes(32)) in preimages
    for rva,size in ((0x33FFB1F,1),(0x33FFB40,1),(0x33FFB1C,4),(0x33FFB40,8)):
        assert code.read(rva,size)==source(rva,size)
    assert code.read(0x33FFB1C,40)==source(0x33FFB1C,4)+bytes(32)+source(0x33FFB40,4)
    assert code.read(0x33FFB23,7)==bytes(7)
    refusals=[]
    for mutation in (0x33FFB20,0x33FFB3F):
        def changed(rva: int,size: int) -> bytes:
            raw=bytearray(source(rva,size))
            if rva<=mutation<rva+size:raw[mutation-rva]^=1
            return bytes(raw)
        try:field_preimages(changed)
        except ValueError:refusals.append(hex(mutation))
        else:raise AssertionError('A changed field initializer contract escaped cold-phase refusal.')
    from folded_sentients import prepare_folded_sentient_storage
    class ChangedCode(CapturedCode):
        def read(self,rva: int,size: int) -> bytes:
            raw=bytearray(super().read(rva,size))
            if rva<=self.mutation<rva+size:raw[self.mutation-rva]^=1
            return bytes(raw)
    pool=((code.base+code.meta['imageSize']+65535)&~65535)+0x400000
    for mutation in (0x2EE25F0,0x2EE7240,0x31D3DD4,0x2FED858,0x2F11F20):
        changed=object.__new__(ChangedCode);changed.__dict__.update(code.__dict__);changed.mutation=mutation
        try:prepare_folded_sentient_storage(changed,pool)
        except ValueError:refusals.append(hex(mutation))
        else:raise AssertionError('A changed registered initializer escaped native source admission.')
    sys.path.insert(0,str(dependencies))
    import capstone
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_64
    import unicorn.x86_const as x64
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    body=code.guarded(INITIALIZER);instructions=list(decoder.disasm(body,code.base+INITIALIZER.rva))
    assert sum(i.size for i in instructions)==len(body) and not any(i.mnemonic=='call' for i in instructions)
    pages=set(range(0x2EE2000,0x2EEA000,4096))
    for instruction in instructions:
        for operand in instruction.operands:
            if operand.type==capstone.x86.X86_OP_MEM and operand.mem.base==capstone.x86.X86_REG_RIP:
                pages.add((instruction.address+instruction.size+operand.mem.disp-code.base)&~4095)
    engine=Uc(UC_ARCH_X86,UC_MODE_64)
    for page in sorted(pages):
        engine.mem_map(code.base+page,4096);engine.mem_write(code.base+page,code.read(page,4096))
    assert engine.mem_read(code.base+0x33FFB20,32)==bytes(32)
    stack,stop=0x20000000,0x30000000
    engine.mem_map(stack,0x20000);engine.mem_map(stop,4096)
    rsp=stack+0x1F008;engine.mem_write(rsp,struct.pack('<Q',stop));engine.reg_write(x64.UC_X86_REG_RSP,rsp)
    saved={name:0x55550000+index for index,name in enumerate(('RBX','RBP','RSI','RDI','R12','R13','R14','R15'))}
    for name,value in saved.items():engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
    engine.emu_start(code.base+INITIALIZER.rva,stop,count=100000)
    actual=bytes(engine.mem_read(code.base+0x33FFB20,32))
    assert actual==FINAL and engine.reg_read(x64.UC_X86_REG_RSP)==rsp+8
    assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in saved.items())
    name=code.guarded(NAME);value=0x4B9ACE2F
    for byte in name:value=((value^byte)*0x1000193)&0xFFFFFFFF
    assert struct.unpack('<IIIIQQ',actual)==(value,0x122C,8,11,0,0)
    # Runtime admission checks the exact image-relative callback target, before pointer normalization.
    callbacks=[]
    for game in (code.base,0x7FF700310000,0x7FF77B080000):
        pointer=struct.pack('<Q',game+INITIALIZER.rva)
        assert struct.unpack('<Q',pointer)[0]-game==INITIALIZER.rva
        callbacks.append({'imageBase':hex(game),'callback':hex(game+INITIALIZER.rva),'normalizedRva':hex(INITIALIZER.rva)})
    output.parent.mkdir(parents=True,exist_ok=True);fixtures=[]
    for guard in (INITIALIZER,UNWIND,NAME,code.guard(0x2F11F20,8)):
        path=output.with_name(output.stem+f'.{guard.rva:x}.bin');raw=code.read(guard.rva,guard.size);path.write_bytes(raw)
        fixtures.append({'rva':hex(guard.rva),'bytes':guard.size,'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()})
    for label,raw in (('cold',cold),('initialized',actual)):
        path=output.with_name(output.stem+f'.{label}.bin');path.write_bytes(raw)
        fixtures.append({'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()})
    result={'passed':True,'phase':'GREEN','guardRefusals':refusals,'callbacks':callbacks,'fixtures':fixtures,
            'field':{'name':name.rstrip(b'\0').decode(),'hash':hex(value),'offset':'0x122C','wordAt8':8,'type':11,'setter':0,'getter':0},
            'initializerBytes':len(body),'authoredEndpoints':0,'gameWrites':0,'activationAllowed':False,
            'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in
                       (Path(__file__),PATCHES/'captured_code.py',PATCHES/'startup_guards.py')},
            'scope':'Canonical cold descriptor boundaries, exact initializer contracts, callback target normalization, and complete captured native initializer replay. The replay constructs the pinned field from zeros and preserves stack/nonvolatile registers. Live startup phase still requires the frozen launcher admission.'}
    output.write_text(json.dumps(result,indent=2)+'\n')
    return {'passed':True,'initializerBytes':len(body),'guardRefusals':len(refusals),'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.dependencies,args.output)))
