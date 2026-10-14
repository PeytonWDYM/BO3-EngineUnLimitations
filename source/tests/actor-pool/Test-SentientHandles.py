"""Replay the captured type-11 getter and native sentient-handle setter in owned memory."""
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
from storage_plan import StorageLayout,prepare_storage
from table_layout import TableLayout,NativeSentientAddress,ExternalTableAddress


def run(module: Path,executable: Path,dependencies: Path,output: Path,stock: bool) -> dict:
    sys.path.insert(0,str(dependencies))
    import capstone
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE,UcError
    import unicorn.x86_const as x64
    output=output.resolve();artifact=output.with_suffix('.pool.bin')
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists() or artifact.exists():
        raise ValueError('Use a new private BO3 lab result file.')
    code=CapturedCode(module,executable);shape=ActorShape(500)
    arena=(code.base+code.meta['imageSize']+65535)&~65535
    pool=arena+0x400000;pool_bytes=shape.sentient_bytes
    storage=StorageLayout(*(arena+offset for offset in (0x1F10000,0x2400000,0x2600000,0x2610000,0x2700000)))
    layout=TableLayout(NativeSentientAddress(pool),ExternalTableAddress(arena+0xB00000),shape)
    existing=prepare_storage(code,layout,storage,arena)
    if not stock:
        from folded_sentients import prepare_folded_sentient_storage,OWNER_GUARDS
        edit=prepare_folded_sentient_storage(code,pool)
    old_pool=code.base+0xA037CD0;old_page=old_pool&~4095
    old_bytes=((old_pool-old_page+pool_bytes+4095)&~4095)
    engine=Uc(UC_ARCH_X86,UC_MODE_64);pages=set()
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    fixtures=((0x1B14AC0,420),(0x159A2B0,208))
    for rva,size in fixtures:
        pages.update(range(rva&~4095,(rva+size+4095)&~4095,4096))
        for instruction in decoder.disasm(code.read(rva,size),code.base+rva):
            for operand in instruction.operands:
                if operand.type==capstone.x86.X86_OP_MEM and operand.mem.base==capstone.x86.X86_REG_RIP:
                    pages.add((instruction.address+instruction.size+operand.mem.disp-code.base)&~4095)
    endpoints=(0x12E9760,0x1593580,0x1595180)
    pages.update(rva&~4095 for rva in endpoints)
    for page in sorted(pages):
        if old_page<=code.base+page<old_page+old_bytes:continue
        engine.mem_map(code.base+page,4096);engine.mem_write(code.base+page,code.read(page,4096))
    for item in existing:
        if item.guard.rva in (0x159A2CE,0x159A2DF):engine.mem_write(code.base+item.guard.rva,item.replacement)
    if not stock:engine.mem_write(code.base+edit.guard.rva,edit.replacement)
    engine.mem_map(old_page,old_bytes);engine.mem_write(old_page,b'\xCC'*old_bytes)
    # Every old entity pointer is null. A stale read must reproduce the real crash.
    for index in range(shape.sentients):engine.mem_write(old_pool+index*0x3088,bytes(8))
    old_before=bytes(engine.mem_read(old_page,old_bytes))
    entities,stack,stop=0x10000000,0x20000000,0x30000000
    bank_page=pool-4096;bank_size=((pool_bytes+4095)&~4095)+8192
    for address,size in ((bank_page,bank_size),(entities,0x30000),(stack,0x20000),(stop,4096),
                         (storage.sentient_heads,4096)):
        engine.mem_map(address,size)
    engine.mem_write(bank_page,b'\xA5'*bank_size)
    engine.mem_write(entities,b'\x5A'*0x30000)
    for index in range(shape.sentients):
        entity=entities+index*0x100
        engine.mem_write(pool+index*0x3088,struct.pack('<Q',entity))
        engine.mem_write(entity,struct.pack('<I',0x4000+index))
    entity_before=bytes(engine.mem_read(entities,0x30000))
    field=pool+3*0x3088+0x122C;engine.mem_write(field,bytes(4))
    expected=bytearray(engine.mem_read(bank_page,bank_size))
    publishes=[];lists=[]
    def endpoint(current,address,size,unused):
        assert current.reg_read(x64.UC_X86_REG_RSP)&15==8
        if address==code.base+0x12E9760:
            assert current.reg_read(x64.UC_X86_REG_RCX)==0 and current.reg_read(x64.UC_X86_REG_R8)==0
            publishes.append(current.reg_read(x64.UC_X86_REG_RDX));result=0
        elif address==code.base+0x1593580:
            head=current.reg_read(x64.UC_X86_REG_RCX)
            index=(head-storage.sentient_heads)//2
            assert head==storage.sentient_heads+index*2 and 0<=index<shape.sentients
            assert current.reg_read(x64.UC_X86_REG_RDX)==field
            result=0x5000+index;lists.append(('assign',index))
        else:
            head=current.reg_read(x64.UC_X86_REG_RCX);index=(head-storage.sentient_heads)//2
            assert head==storage.sentient_heads+index*2 and 0<=index<shape.sentients
            assert current.reg_read(x64.UC_X86_REG_RDX)==0x5000+index
            result=0;lists.append(('release',index))
        current.reg_write(x64.UC_X86_REG_RAX,result)
        rsp=current.reg_read(x64.UC_X86_REG_RSP)
        current.reg_write(x64.UC_X86_REG_RIP,struct.unpack('<Q',current.mem_read(rsp,8))[0])
        current.reg_write(x64.UC_X86_REG_RSP,rsp+8)
    for rva in endpoints:engine.hook_add(UC_HOOK_CODE,endpoint,begin=code.base+rva,end=code.base+rva)
    saved={name:0x77770000+index for index,name in enumerate(('RBX','RBP','RSI','RDI','R12','R13','R14','R15'))}
    def call(rva: int,args: tuple[int,...]) -> None:
        rsp=stack+0x1F008;engine.mem_write(rsp,struct.pack('<Q',stop)+bytes(0x80))
        engine.reg_write(x64.UC_X86_REG_RSP,rsp)
        for name,value in saved.items():engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
        for name,value in zip(('RCX','RDX','R8','R9'),args):engine.reg_write(getattr(x64,'UC_X86_REG_'+name),value)
        engine.emu_start(code.base+rva,stop,count=10000)
        assert engine.reg_read(x64.UC_X86_REG_RSP)==rsp+8
        assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+name))==value for name,value in saved.items())
    cases=[]
    for handle in (0,1,104,105,540,0):
        target=pool+(handle-1)*0x3088 if handle else 0
        call(0x159A2B0,(field,target))
        encoded=struct.unpack('<HH',engine.mem_read(field,4))
        assert encoded==(handle,0x5000+handle-1 if handle else 0)
        struct.pack_into('<HH',expected,field-bank_page,*encoded)
        before=len(publishes)
        try:call(0x1B14AC0,(pool+3*0x3088,11,0x122C,0))
        except UcError:
            assert stock and handle==1
            result={'passed':False,'phase':'RED','handle':handle,'faultRva':hex(engine.reg_read(x64.UC_X86_REG_RIP)-code.base),
                    'rax':engine.reg_read(x64.UC_X86_REG_RAX),'oldPoolPoisoned':True,'scope':'Captured native getter reads the stale pool.'}
            output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n')
            raise AssertionError('The native getter still resolves valid handle1 through the poisoned stock pool.')
        assert publishes[before:]==([0x4000+handle-1] if handle else [])
        assert engine.mem_read(bank_page,bank_size)==expected
        assert engine.mem_read(old_page,old_bytes)==old_before and engine.mem_read(entities,0x30000)==entity_before
        cases.append({'handle':handle,'entityNumber':publishes[-1] if handle else None,'nativeZeroBranch':not handle})
    refusals=[]
    if not stock:
        class ChangedCode(CapturedCode):
            def read(self,rva: int,size: int) -> bytes:
                raw=bytearray(super().read(rva,size))
                if rva<=self.mutation<rva+size:raw[self.mutation-rva]^=1
                return bytes(raw)
        for guard in OWNER_GUARDS:
            changed=object.__new__(ChangedCode);changed.__dict__.update(code.__dict__);changed.mutation=guard.rva
            try:prepare_folded_sentient_storage(changed,pool)
            except ValueError:refusals.append(hex(guard.rva))
            else:raise AssertionError('A changed native handle contract escaped refusal.')
        for address in (0,pool+1,code.base,code.base+code.meta['imageSize']-16,0x800000000000-16,
                        code.base+(1<<31)+0x3090,code.base-(1<<31)+0x3080):
            try:prepare_folded_sentient_storage(code,address)
            except ValueError:refusals.append(hex(address))
            else:raise AssertionError('An invalid complete native sentient pool escaped refusal.')
    output.parent.mkdir(parents=True,exist_ok=True);artifact.write_bytes(engine.mem_read(pool,pool_bytes))
    fixture_receipts=[]
    for rva,size in (*fixtures,(0x3160F08,8),(0x314872C,20),(0x33FFB20,32)):
        path=output.with_name(output.stem+f'.{rva:x}.bin');raw=code.read(rva,size);path.write_bytes(raw)
        fixture_receipts.append({'rva':hex(rva),'bytes':size,'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()})
    paths=(Path(__file__),PATCHES/'folded_sentients.py',PATCHES/'storage_plan.py',PATCHES/'captured_code.py')
    result={'passed':True,'phase':'GREEN','cases':cases,'refusals':refusals,'lists':lists,'fixtures':fixture_receipts,
            'artifact':{'path':str(artifact),'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()},
            'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
            'gameWrites':0,'activationAllowed':False,
            'scope':'Captured full type11 getter and native handle setter. Script-value publication and list allocation/release endpoints are authored. Native entity pointers, one-based IDs, zero branches, pool poisoning, other fields, canaries, stack and nonvolatile registers are verified.'}
    output.write_text(json.dumps(result,indent=2)+'\n')
    return {'passed':True,'cases':len(cases),'refusals':len(refusals),'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--stock',action='store_true')
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.dependencies,args.output,args.stock)))
