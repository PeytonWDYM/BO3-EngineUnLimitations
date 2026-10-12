"""Replay complete native actor/sentient codec loops with coordinated legacy and expanded read counts."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
PATCHES=Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from captured_code import CapturedCode
from load_counts import LoadCounts,LoadShape,prepare_load_counts


def run(module: Path,executable: Path,dependencies: Path,output: Path) -> dict:
    sys.path.insert(0,str(dependencies))
    import capstone
    from unicorn import Uc,UcError,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE
    import unicorn.x86_const as x64
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab output file.')
    code=CapturedCode(module,executable);slots=LoadCounts(code.base+0x33000000)
    edits=prepare_load_counts(code,slots)
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    families=(('actor',0xC9E50,0xCA00D,0xB60E0,0xB6346,0x2110,0,0xA1B0798),
              ('sentient',0xD1F00,0xD20D2,0xC44C0,0xC461D,0x3088,0xA0,0xA1B0790))
    cases=[];artifacts=bytearray()
    class PastEnd(AssertionError):pass
    for kind in (LoadShape.Legacy64,LoadShape.Expanded500):
        counts=slots.values(kind)
        for name,writer,writer_end,reader,reader_end,stride,flag,pointer in families:
            count=(64 if name=='actor' else 104) if kind is LoadShape.Legacy64 else (500 if name=='actor' else 540)
            stock=64 if name=='actor' else 104
            for active in (False,True):
                engine=Uc(UC_ARCH_X86,UC_MODE_64);pages=set()
                instructions=[]
                for first,last in ((writer,writer_end),(reader,reader_end)):
                    pages.update(range(first&~4095,(last+4095)&~4095,4096))
                    instructions+=list(decoder.disasm(code.read(first,last-first),code.base+first))
                for ins in instructions:
                    for op in ins.operands:
                        if op.type==capstone.x86.X86_OP_MEM and op.mem.base==capstone.x86.X86_REG_RIP:
                            pages.add((ins.address+ins.size+op.mem.disp-code.base)&~4095)
                endpoints=(0x2277B80,0x22778B0,0xC0410,0xCF8C0,0x2BC53B0,0x2BC4EB0,0x2505BF0,0x25003C0,0x2BC5B3C)
                pages.update(rva&~4095 for rva in endpoints);pages.add(pointer&~4095)
                for page in sorted(pages):engine.mem_map(code.base+page,4096);engine.mem_write(code.base+page,code.read(page,4096))
                data,stack,stop,pool=0x40000000,0x41000000,0x42000000,0x43000000
                engine.mem_map(data,0x50000);engine.mem_map(stack,0x20000);engine.mem_map(stop,4096)
                total=count*stride;backing=(500 if name=='actor' else 540)*stride
                engine.mem_map(pool-4096,((backing+16+4095)&~4095)+4096)
                engine.mem_write(pool-16,b'\xa5'*16);engine.mem_write(pool+backing,b'\x5a'*16)
                records=bytearray(total)
                if active:
                    for index in range(count):
                        records[index*stride:(index+1)*stride]=bytes([index%stock])*stride
                        records[index*stride+flag]=1
                        if name=='actor':struct.pack_into('<I',records,index*stride+0x24C,0)
                engine.mem_write(pool,bytes(records));engine.mem_write(code.base+pointer,struct.pack('<Q',pool))
                engine.mem_map(slots.base,4096);engine.mem_write(slots.base,counts)
                # Clear native descriptor lists and recursion state. Descriptor callbacks remain explicit authored endpoints.
                for rva in ((0xB6102,0xB6144,0xB620E) if name=='actor' else (0xC44E4,0xC451B)):
                    ins=next(i for i in instructions if i.address==code.base+rva)
                    mem=next(op.mem for op in ins.operands if op.type==capstone.x86.X86_OP_MEM)
                    target=ins.address+ins.size+mem.disp
                    engine.mem_write(target,b'\x00'*4)
                    if rva in (0xB6102,0xC44E4):engine.mem_write(target-20,b'\0'*4)
                stream=bytearray();cursor=0
                saved={name:0x66660000+i for i,name in enumerate(('RBX','RBP','RSI','RDI','R12','R13','R14','R15'))}
                def endpoint(current,address,size,unused):
                    nonlocal cursor
                    rcx=current.reg_read(x64.UC_X86_REG_RCX);rdx=current.reg_read(x64.UC_X86_REG_RDX);r8=current.reg_read(x64.UC_X86_REG_R8)
                    if address==code.base+0x2277B80:
                        pending=struct.unpack('<I',current.mem_read(data+0x18,4))[0]
                        stream.extend(current.mem_read(data+0x38,pending));current.mem_write(data+0x18,b'\0'*4)
                        stream.extend(current.mem_read(r8,rdx))
                    elif address==code.base+0x22778B0:
                        if cursor+rdx>len(stream):raise PastEnd('The native reader consumed past the admitted input shape.')
                        current.mem_write(r8,bytes(stream[cursor:cursor+rdx]));cursor+=rdx
                    elif address==code.base+0x2BC53B0:current.mem_write(rcx,bytes([rdx&255])*r8)
                    elif address==code.base+0x2BC4EB0:current.mem_write(rcx,bytes(current.mem_read(rdx,r8)))
                    elif address in (code.base+0xC0410,code.base+0xCF8C0):raise AssertionError('Unexpected native attachment callback.')
                    rsp=current.reg_read(x64.UC_X86_REG_RSP);pc=struct.unpack('<Q',current.mem_read(rsp,8))[0]
                    current.reg_write(x64.UC_X86_REG_RAX,0);current.reg_write(x64.UC_X86_REG_RSP,rsp+8);current.reg_write(x64.UC_X86_REG_RIP,pc)
                for rva in endpoints:engine.hook_add(UC_HOOK_CODE,endpoint,begin=code.base+rva,end=code.base+rva)
                def call(address):
                    rsp=stack+0x1F008;engine.mem_write(rsp,struct.pack('<Q',stop)+bytes(0xF0));engine.reg_write(x64.UC_X86_REG_RSP,rsp)
                    for reg,value in saved.items():engine.reg_write(getattr(x64,'UC_X86_REG_'+reg),value)
                    engine.reg_write(x64.UC_X86_REG_RCX,data)
                    try:engine.emu_start(code.base+address,stop,count=3000000)
                    except UcError as error:
                        raise AssertionError(f'{kind.name}/{name}/active={active}: native RVA {engine.reg_read(x64.UC_X86_REG_RIP)-code.base:#x}: {error}') from error
                    assert engine.reg_read(x64.UC_X86_REG_RSP)==rsp+8
                    assert all(engine.reg_read(getattr(x64,'UC_X86_REG_'+reg))==value for reg,value in saved.items())
                # The writer uses the selected shape. Preserve its complete native code and framing.
                bound=0xC9FE1 if name=='actor' else 0xD20A6
                engine.mem_write(code.base+bound,code.read(bound,3)+struct.pack('<I',total))
                call(writer);pending=struct.unpack('<I',engine.mem_read(data+0x18,4))[0];stream.extend(engine.mem_read(data+0x38,pending))
                expected=b''.join((bytes(records[i*stride:i*stride+4]) if name=='actor' else bytes(records[i*stride+flag:i*stride+flag+1]))+
                                  (bytes(records[i*stride:i*stride+(0x2100 if name=='actor' else stride)]) if active else b'') for i in range(count))
                assert stream==expected,(name,kind,len(stream),len(expected))
                artifacts+=struct.pack('<III',kind.value,int(name=='sentient'),len(stream))+stream
                marker=b'FOLLOWING-SECTION';stream+=marker
                engine.mem_write(pool,b'\0'*backing)
                # The unchanged native reader supplies a complete-record oracle, including its default-field writes.
                call(reader)
                baseline=bytes(engine.mem_read(pool,stock*stride))
                engine.mem_write(pool,b'\0'*backing);cursor=0
                for edit in edits:
                    if reader<=edit.guard.rva<reader_end:engine.mem_write(code.base+edit.guard.rva,edit.replacement)
                engine.ctl_remove_cache(code.base+reader,code.base+reader_end)
                call(reader)
                assert cursor==len(expected) and stream[cursor:]==marker
                assert engine.mem_read(pool-16,16)==b'\xa5'*16 and engine.mem_read(pool+backing,16)==b'\x5a'*16
                assert engine.mem_read(pool+total,backing-total)==b'\0'*(backing-total) if backing>total else True
                loaded=bytes(engine.mem_read(pool,total))
                for i in range(count):assert loaded[i*stride:(i+1)*stride]==baseline[(i%stock)*stride:(i%stock+1)*stride]
                if kind is LoadShape.Legacy64:
                    cursor=0;engine.mem_write(slots.base,slots.values(LoadShape.Expanded500))
                    try:call(reader)
                    except PastEnd:pass
                    else:raise AssertionError('Expanded counts accepted legacy input.')
                cases.append({'kind':kind.name,'family':name,'active':active,'records':count,'nativeBytes':len(expected),'nativeConsumed':len(expected)})
    # Execute both original secondary loops. Their serializer endpoint copies an opaque native-stride record.
    secondary=[]
    for kind in (LoadShape.Legacy64,LoadShape.Expanded500):
        count=kind.value
        for site,end,record_reg,file_reg in ((0xFA1A7,0xFA1D9,'RBX','RDI'),(0x12E10A,0x12E139,'RDI','RBX')):
            engine=Uc(UC_ARCH_X86,UC_MODE_64);page=code.base+(site&~4095)
            engine.mem_map(page,4096);engine.mem_write(page,code.read(site&~4095,4096))
            target=code.base+0xC4620;engine.mem_map(target&~4095,4096)
            stack,pool,file=0x44000000,0x45000000,0x46000000
            engine.mem_map(stack,0x10000);engine.mem_map(pool-4096,0x160000);engine.mem_map(file,4096)
            engine.mem_map(slots.base,4096);engine.mem_write(slots.base,slots.values(kind))
            selected=next(e for e in edits if e.guard.rva==site);engine.mem_write(code.base+site,selected.replacement)
            engine.mem_write(pool-16,b'\xa5'*16);engine.mem_write(pool+500*0xB00,b'\x5a'*16)
            engine.reg_write(x64.UC_X86_REG_RSP,stack+0xF000)
            engine.reg_write(getattr(x64,'UC_X86_REG_'+record_reg),pool);engine.reg_write(getattr(x64,'UC_X86_REG_'+file_reg),file)
            observed=[]
            def opaque(current,address,size,unused):
                index=len(observed);assert current.reg_read(x64.UC_X86_REG_RDX)==pool+index*0xB00
                assert current.reg_read(x64.UC_X86_REG_R8)==0xB00 and current.reg_read(x64.UC_X86_REG_R9)==file
                current.mem_write(pool+index*0xB00,bytes([index%251])*0xB00);observed.append(index)
                rsp=current.reg_read(x64.UC_X86_REG_RSP);pc=struct.unpack('<Q',current.mem_read(rsp,8))[0]
                current.reg_write(x64.UC_X86_REG_RSP,rsp+8);current.reg_write(x64.UC_X86_REG_RIP,pc)
            engine.hook_add(UC_HOOK_CODE,opaque,begin=target,end=target)
            engine.emu_start(code.base+site,code.base+end,count=10000)
            assert len(observed)==count and engine.reg_read(x64.UC_X86_REG_RSI)==0
            assert engine.reg_read(x64.UC_X86_REG_RSP)==stack+0xF000
            assert engine.mem_read(pool-16,16)==b'\xa5'*16 and engine.mem_read(pool+500*0xB00,16)==b'\x5a'*16
            for i in range(count):assert engine.mem_read(pool+i*0xB00,0xB00)==bytes([i%251])*0xB00
            secondary.append({'kind':kind.name,'site':hex(site),'records':count})
    class ChangedCode(CapturedCode):
        def read(self,rva: int,size: int) -> bytes:
            raw=bytearray(super().read(rva,size))
            if rva<=self.mutation<rva+size:raw[self.mutation-rva]^=1
            return bytes(raw)
    mutations=(0xB60E0,0xB631C,0x3101F88,0xC44C0,0xC45F1,0x3101FC0,0xFA0E0,0xFA1A7,0xFA1AC,0x3102880,0x12E01A,0x12E10A,0x12E10F,0x3102CE8)
    for mutation in mutations:
        changed=object.__new__(ChangedCode);changed.__dict__.update(code.__dict__);changed.mutation=mutation
        try:prepare_load_counts(changed,slots)
        except ValueError:pass
        else:raise AssertionError('A changed complete codec owner/count window escaped refusal.')
    addresses=(0,slots.base+1,code.base,code.base+0x90000000,0x800000000000-16)
    for address in addresses:
        try:prepare_load_counts(code,LoadCounts(address))
        except ValueError:pass
        else:raise AssertionError('An invalid complete count interval escaped refusal.')
    output.parent.mkdir(parents=True,exist_ok=True);binary=output.with_suffix('.codec.bin');binary.write_bytes(artifacts)
    paths=(Path(__file__),PATCHES/'load_counts.py',PATCHES/'captured_code.py',PATCHES/'x64_table.py')
    result={'passed':True,'cases':cases,'secondary':secondary,'guardRefusals':len(mutations),'addressRefusals':len(addresses),'sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
            'artifact':{'path':str(binary),'sha256':hashlib.sha256(artifacts).hexdigest()},'activationAllowed':False,'gameWrites':0,
            'scope':'Complete native actor/sentient save/read loops. Stream, descriptor termination, native clear/default endpoints and input count slots are authored. Root admission, unused-slot initialization, variable attachments and real game behavior remain separate.'}
    output.write_text(json.dumps(result,indent=2)+'\n');return {'passed':True,'cases':len(cases),'output':str(output)}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();print(json.dumps(run(a.module,a.executable,a.dependencies,a.output)))
