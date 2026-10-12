"""Compare startup guard preparation with admitted private saved images. Never start BO3."""
import argparse
import bisect
import hashlib
import json
import struct
import sys
from pathlib import Path

PATCHES=Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from captured_code import CapturedCode,CodeGuard
from actor_wire import OWNER_GUARDS,prepare_actor_wire
from shape import ActorShape

STOCK_OWNERS=((0x19CA570,93492),(0x20EC0B0,1382))
ROOTS=(0x21268D0,0x20FD190,0x20FCE70,0x20FDFC0,0x212A480,0x2105F20)


def codec_closure(image):
    """Follow complete native rows, split branches, chained metadata, and leaf control flow."""
    import capstone
    pe=struct.unpack_from('<I',image,0x3C)[0]
    rva,size=struct.unpack_from('<II',image,pe+24+112+24)
    rows=sorted(struct.iter_unpack('<III',image[rva:rva+size]))
    row_set=set(rows)
    starts=[r[0] for r in rows]
    children={}
    for begin,end,unwind in rows:
        if image[unwind]>>3&4:
            offset=unwind+4+((image[unwind+2]+1)&~1)*2
            parent=struct.unpack_from('<III',image,offset)
            assert parent in row_set
            children.setdefault(parent[0],[]).append(begin)
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    pending=list(ROOTS);owners={};leaves={};metadata={};external=set()
    def target(instruction):
        if instruction.group(capstone.CS_GRP_JUMP) or instruction.group(capstone.CS_GRP_CALL):
            if len(instruction.operands)==1 and instruction.operands[0].type==capstone.CS_OP_IMM:
                return instruction.operands[0].imm
        return None
    while pending:
        entry=pending.pop();begin,end,unwind=rows[bisect.bisect_right(starts,entry)-1]
        if begin<=entry<end:
            if begin in owners:continue
            owners[begin]=(end,unwind)
            pending.extend(children.get(begin,()))
            instructions=list(decoder.disasm(image[begin:end],begin))
            flags=image[unwind]>>3
            extent=4+((image[unwind+2]+1)&~1)*2+(12 if flags&4 else 8 if flags&3 else 0)
            metadata[unwind]=extent
            if flags&4:pending.append(struct.unpack_from('<III',image,unwind+extent-12)[0])
        else:
            if entry in leaves:continue
            begin=entry;seen={};queue=[entry]
            leaf_limit=starts[bisect.bisect_right(starts,entry)]
            while queue:
                pc=queue.pop()
                if pc in seen:continue
                if not entry<=pc<leaf_limit:
                    if 0x20F0000<=pc<0x2140000:pending.append(pc)
                    else:external.add(pc)
                    continue
                instruction=next(decoder.disasm(image[pc:pc+15],pc))
                seen[pc]=instruction;branch=target(instruction)
                if branch is not None and instruction.group(capstone.CS_GRP_JUMP):
                    queue.append(branch)
                if instruction.group(capstone.CS_GRP_RET) or instruction.mnemonic=='jmp':continue
                queue.append(pc+instruction.size)
            end=max(i.address+i.size for i in seen.values())
            leaves[entry]=end;instructions=list(seen.values())
        for instruction in instructions:
            branch=target(instruction)
            if branch is None:continue
            if 0x20F0000<=branch<0x2140000:
                if not begin<=branch<end:pending.append(branch)
            else:external.add(branch)
    external={r for r in external if not 0x20F0000<=r<0x2140000}
    assert external=={0x1359250,0x227B480,0x227B490,0x227B4A0,0x2587760,0x25D48D0,
                     0x25D4A80,0x2BC3AA0,0x2BC4EB0,0x2BC53B0,0x2BC6D08},sorted(map(hex,external))
    return [(b,e-b) for b,(e,_) in owners.items()]+[(b,e-b) for b,e in leaves.items()],list(metadata.items())


def run(args):
    sys.path.insert(0,str(args.dependencies))
    from minidump.minidumpfile import MinidumpFile
    output=args.output.resolve()
    lab=(Path.home()/'.codex/labs/bo3-engine').resolve()
    if lab not in output.parents or output.exists():raise ValueError('Use a new private result path.')
    code=CapturedCode(args.module,args.executable)
    cases=[]
    def check(name,passed,**details):cases.append({'case':name,'passed':bool(passed),**details})
    image=args.stock_image.read_bytes()
    inventory=json.loads((PATCHES/'runtime_inventory.json').read_text())
    pointer_fields=inventory['normalizations']
    check('stock-image-identity',hashlib.sha256(image).hexdigest()=='fcc35afd9b9a13d656f1b15a3d0fd5536429aca3dd7457e4f0ed148771f4ce79')
    views=[('passive-startup',args.stock_base,lambda r,s:image[r:r+s])]
    streams=[]
    for path in args.stock_dump:
        dump=MinidumpFile.parse(str(path))
        identity=json.loads((path.parent/'process.json').read_text(encoding='utf-8-sig'))
        game=next(m for m in dump.modules.modules if Path(m.name).name.lower()=='blackops3.exe')
        check('saved-stock-identity-'+str(identity['pid']),identity['sha256'].lower()==code.executable_sha256 and
              game.size==494186496 and game.timestamp==1765634846 and dump.misc_info.ProcessId==identity['pid'])
        stream=path.open('rb');streams.append(stream)
        ranges=(dump.memory_segments_64 or dump.memory_segments).memory_segments
        def read(rva,size,base=game.baseaddress,ranges=ranges,stream=stream):
            position=base+rva;end=position+size;out=bytearray()
            while position<end:
                row=next(row for row in ranges if row.start_virtual_address<=position<row.end_virtual_address)
                take=min(end-position,row.end_virtual_address-position)
                stream.seek(row.start_file_address+position-row.start_virtual_address)
                out.extend(stream.read(take));position+=take
            return bytes(out)
        views.append((str(identity['pid']),game.baseaddress,read))
    try:
        for label,base,read in views:
            for rva,size in STOCK_OWNERS:
                expected=hashlib.sha256(code.read(rva,size)).hexdigest()
                actual=hashlib.sha256(read(rva,size)).hexdigest()
                check('complete-stock-owner-'+label+'-'+hex(rva),expected==actual,rva=rva,size=size,expected=expected,actual=actual)
            for guard in OWNER_GUARDS:
                before=code.read(guard.rva,guard.size)
                observed=bytearray(read(guard.rva,guard.size))
                for normalization in pointer_fields:
                    field,target=normalization['rva'],normalization['target']
                    if guard.rva<=field and field+8<=guard.rva+guard.size:
                        offset=field-guard.rva
                        check('descriptor-pointer-'+label+'-'+hex(field),struct.unpack_from('<Q',observed,offset)[0]==base+target)
                        struct.pack_into('<Q',observed,offset,code.base+target)
                check('complete-wire-guard-'+label+'-'+hex(guard.rva),hashlib.sha256(observed).hexdigest()==guard.sha256,
                      rva=guard.rva,size=guard.size)
        # These six endpoints define the existing native packet replay contract.
        check('packet-roots-have-complete-guards',all(any(g.rva<=r<g.rva+g.size for g in OWNER_GUARDS) for r in ROOTS))
        code_spans,metadata_spans=codec_closure(image)
        declared={(g.rva,g.size) for g in OWNER_GUARDS}
        check('complete-native-and-leaf-closure',all(span in declared for span in code_spans),codeOwners=len(code_spans))
        check('complete-unwind-closure',all(span in declared for span in metadata_spans),metadataOwners=len(metadata_spans))
        import capstone
        decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
        for begin,selectors,count,table in ((0x2127080,0x2127EDC,113,0x2127E04),(0x2126230,0x212677C,62,0x2126714)):
            indices=image[selectors:selectors+count]
            targets={struct.unpack_from('<I',image,table+4*i)[0] for i in indices}
            boundaries={i.address for i in decoder.disasm(image[begin:table],begin)}
            owner=next(g for g in OWNER_GUARDS if g.rva==begin)
            check('complete-indirect-switch-'+hex(begin),targets<=boundaries and
                  all(owner.rva<=pc<owner.rva+owner.size for pc in targets) and
                  owner.rva<=table<selectors+count<=owner.rva+owner.size,caseTargets=len(targets))
        prepare_actor_wire(code,ActorShape(500))
        check('packet-preparation',True)
        from startup_guards import STOCK_PREIMAGES,stock_preimages
        source_refusals=0
        for address,captured,_ in STOCK_PREIMAGES:
            for offset in range(len(captured)):
                for bit in range(8):
                    def altered_source(rva,size,address=address,offset=offset,bit=bit):
                        raw=bytearray(code._read_captured(rva,size))
                        if rva<=address+offset<rva+size:raw[address+offset-rva]^=1<<bit
                        return bytes(raw)
                    try:stock_preimages(altered_source)
                    except ValueError:source_refusals+=1
        check('exact-captured-hook-preimage-refusals',source_refusals==80,refused=source_refusals)
        from runtime_recipe import prepare_recipe
        from runtime_templates import make_template
        recipe=prepare_recipe(code,code.base+0x20000000)
        copied=0;uncovered=[]
        for edit in recipe.edits:
            bodies=[('game',edit.guard.rva,edit.replacement,())]
            if edit.stub:bodies.append(('arena',edit.stub_address-recipe.arena,edit.stub,edit.instruction_map))
            for space,offset,body,instruction_map in bodies:
                template=make_template(code,recipe,space,offset,body,instruction_map,
                    edit.image_relative_operands if space=='game' else ())
                for piece in template.pieces:
                    if piece.source is None:continue
                    copied+=piece.size
                    if not any(g.rva<=piece.source and piece.source+piece.size<=g.rva+g.size for g in recipe.guards):
                        uncovered.append((piece.source,piece.size))
        check('complete-template-copy-coverage',not uncovered,copiedBytes=copied,uncovered=uncovered)
        class ChangedCode(CapturedCode):
            def read(self,rva,size):
                raw=bytearray(super().read(rva,size))
                if rva<=self.mutation<rva+size:raw[self.mutation-rva]^=1
                return bytes(raw)
        changed=object.__new__(ChangedCode);changed.__dict__.update(code.__dict__)
        refused=0
        preparation_refusals=0
        for rva,size in code_spans+metadata_spans:
            guard=next(g for g in OWNER_GUARDS if (g.rva,g.size)==(rva,size))
            # Refuse every byte of complete functions, including their inactive branches.
            for offset in range(size):
                changed.mutation=rva+offset
                try:changed.guarded(guard)
                except ValueError:refused+=1
            for offset in (0,size-1):
                changed.mutation=rva+offset
                try:prepare_actor_wire(changed,ActorShape(500))
                except ValueError:preparation_refusals+=1
        required=sum(s for _,s in code_spans+metadata_spans)
        check('complete-code-and-metadata-byte-refusals',refused==required,refused=refused,required=required)
        check('complete-preparation-owner-boundary-refusals',preparation_refusals==2*(len(code_spans)+len(metadata_spans)),
              refused=preparation_refusals)
    finally:
        for stream in streams:stream.close()
    result={'passed':all(c['passed'] for c in cases),'cases':cases,'gameWrites':0,'gameStarted':False,
            'scope':'Private saved startup guard comparison. Game and peer behavior remain unverified.',
            'sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                       (Path(__file__),PATCHES/'captured_code.py',PATCHES/'actor_wire.py',
                        PATCHES/'startup_guards.py',PATCHES/'wire_guard_inventory.json')}}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'passed':result['passed'],'cases':len(cases),'failed':sum(not c['passed'] for c in cases),'receipt':str(output)}))
    return result['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','stock-image','dependencies','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--stock-base',type=lambda v:int(v,0),required=True)
    parser.add_argument('--stock-dump',type=Path,action='append',default=[])
    raise SystemExit(0 if run(parser.parse_args()) else 1)
