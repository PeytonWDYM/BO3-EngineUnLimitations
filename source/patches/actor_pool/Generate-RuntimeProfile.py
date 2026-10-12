"""Generate the fixed native runtime profile without private inputs during normal builds."""
import argparse,dataclasses,hashlib,json,struct,sys
from pathlib import Path

FOLDER=Path(__file__).resolve().parent
INVENTORY=FOLDER/'runtime_inventory.json'

def digest(path):
    # Git stores these tracked Python and JSON sources with LF line endings.
    return hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()

def regenerate(module,executable,seed):
    from captured_code import CapturedCode
    from runtime_recipe import prepare_recipe
    from runtime_frames import prepare_runtime_frames
    from runtime_templates import make_template
    from unwind import native_frames
    from native_unwind import read_frame
    import pefile
    code=CapturedCode(module,executable)
    recipe=prepare_recipe(code,code.base+0x20000000)
    frames=prepare_runtime_frames(code,recipe)
    guards={(g.rva,g.size):g for g in (*recipe.guards,*frames.guards)}
    # Reader entry and native .pdata admission includes every native owner used by a phase.
    native=native_frames(code)
    pe=pefile.PE(str(executable))
    pdata=pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    extra=[(pdata.VirtualAddress,pdata.Size),(0xFF77B,5)]
    for entry in (0xB60E0,0xC44C0,0xFA0E0,0x19C3270,0x22778B0,0x20EC0B0):
        owner=next(row for row in native if row[0]<=entry<row[1])
        extra.append((owner[0],owner[1]-owner[0]))
        if entry in (0xB60E0,0xC44C0,0xFA0E0):extra.append((entry,5))
        if entry==0x19C3270:extra.append((entry,7))
        frame=read_frame(code,owner)
        while frame:
            header=code.read(frame.runtime[2],4)
            size=4+((header[2]+1)&~1)*2+(12 if frame.flags&4 else 8 if frame.flags&3 else 0)
            extra.append((frame.runtime[2],size));frame=frame.parent
    for rva,size in extra:guards[rva,size]=code.guard(rva,size)
    relocations={item.rva for block in getattr(pe,'DIRECTORY_ENTRY_BASERELOC',[]) for item in block.entries if item.type==10}
    # Named native data tables also contain absolute image pointers in the captured layout.
    normalizations={}
    for guard in guards.values():
        raw=code.guarded(guard)
        candidates=relocations.intersection(range(guard.rva,guard.rva+guard.size-7))
        if guard.rva>=0x2F00000:
            candidates.update(range((guard.rva+7)&~7,guard.rva+guard.size-7,8))
        for field in candidates:
            value=struct.unpack_from('<Q',raw,field-guard.rva)[0]
            if code.base<=value<code.base+code.meta['imageSize']:
                normalizations[field]=value-code.base
    templates=[]
    for edit in recipe.edits:
        templates.append(dataclasses.asdict(make_template(code,recipe,'game',edit.guard.rva,edit.replacement,
            image_relative_operands=edit.image_relative_operands,context_relative_operands=edit.context_relative_operands)))
        if edit.stub:templates.append(dataclasses.asdict(make_template(code,recipe,'arena',edit.stub_address-recipe.arena,edit.stub,edit.instruction_map)))
    def json_bytes(value):
        if isinstance(value,bytes):return value.hex()
        raise TypeError(type(value).__name__)
    phase_rows=[]
    for phase in frames.handlers:
        row=dataclasses.asdict(phase)
        index=native.index(phase.runtime)
        row['native_row_rva']=pdata.VirtualAddress+index*12
        if struct.unpack('<III',code.read(row['native_row_rva'],12))!=phase.runtime:raise ValueError('The native phase owner row differs.')
        phase_rows.append(row)
    sources={path.name:digest(path) for path in sorted(FOLDER.glob('*')) if path.suffix in ('.py','.json') and path!=INVENTORY}
    inventory={'schema':1,'image_size':code.meta['imageSize'],'captured_base':code.base,'executable_sha256':code.executable_sha256,
        'source_sha256':sources,'guards':[dataclasses.asdict(g) for g in sorted(guards.values(),key=lambda g:(g.rva,g.size))],
        'normalizations':[{'rva':rva,'target':target} for rva,target in sorted(normalizations.items())],
        'templates':templates,'functions':[{'begin':f.begin-recipe.arena,'end':f.end-recipe.arena,'metadata':f.metadata.hex(),'parent':f.parent} for f in frames.functions],
        'phases':phase_rows,'storage':[(address-recipe.arena,size) for address,size in recipe.storage],
        'unallocated_pointers':[0xA1B0798,0xA1B0790],'source_edit_count':len(recipe.edits),
        'source_publication_count':sum((edit.guard.rva%0x1000+len(edit.replacement)+0xFFF)//0x1000 for edit in recipe.edits),
        'body_count':sum(bool(e.stub) for e in recipe.edits)}
    INVENTORY.write_text(json.dumps(inventory,default=json_bytes,separators=(',',':'))+'\n')
    if seed:
        seed=seed.resolve()
        lab=(Path.home()/'.codex/labs/bo3-engine').resolve()
        if lab not in seed.parents or seed.exists():raise ValueError('Use a new private seed in the BO3 lab.')
        seed.parent.mkdir(parents=True,exist_ok=True)
        with seed.open('wb') as stream:
            stream.write(struct.pack('<I',len(guards)))
            for guard in guards.values():stream.write(struct.pack('<II',guard.rva,guard.size)+code.read(guard.rva,guard.size))
            stream.write(struct.pack('<I',len(normalizations)))
            for rva,target in sorted(normalizations.items()):stream.write(struct.pack('<II',rva,target))

def generate(output):
    inventory=json.loads(INVENTORY.read_text())
    if inventory['schema']!=1 or inventory['image_size']!=494186496:raise ValueError('The runtime inventory identity is invalid.')
    for name,expected in inventory['source_sha256'].items():
        if digest(FOLDER/name)!=expected:raise ValueError('The runtime inventory source differs: '+name)
    data=bytearray()
    def blob(raw):
        offset=len(data);data.extend(raw);return offset,len(raw)
    guards=[]
    for g in inventory['guards']:guards.append((g['rva'],g['size'],blob(bytes.fromhex(g['sha256']))[0]))
    pieces=[];fixups=[];templates=[]
    for template in inventory['templates']:
        first_piece=len(pieces);first_fixup=len(fixups)
        for p in template['pieces']:
            offset,_=blob(bytes.fromhex(p['data']))
            pieces.append((p['offset'],p['size'],p['source'] if p['source'] is not None else 0xFFFFFFFF,offset))
        for r in template['relocations']:
            fixups.append((r['offset'],r['width'],int(r['target']['space']=='arena'),r['target']['offset'],
                r['next_offset'] if r['next_offset'] is not None else 0xFFFFFFFF,int(r['image_relative']),r.get('image_anchor',0)))
        templates.append((int(template['origin']['space']=='arena'),template['origin']['offset'],template['size'],first_piece,len(template['pieces']),first_fixup,len(template['relocations'])))
    functions=[]
    for f in inventory['functions']:
        offset,size=blob(bytes.fromhex(f['metadata']))
        functions.append((f['begin'],f['end'],offset,size,f['parent'] if f['parent'] is not None else 0xFFFFFFFF))
    phases=[(p['control_rva'],p['native_row_rva'],p['handler_rva'],p['data_rva'],p['prolog'],p['temporary_bytes']) for p in inventory['phases']]
    text=['// Generated from runtime_inventory.json. Do not edit.','#pragma once','#include <cstdint>','namespace bo3::actors::profile {',
        'struct Guard {std::uint32_t rva,size,digest;};','struct Normalization {std::uint32_t rva,target;};',
        'struct Piece {std::uint32_t offset,size,source,data;};','struct Fixup {std::uint32_t offset,width,arena,target,next,imageRelative,imageAnchor;};',
        'struct Template {std::uint32_t arena,offset,size,pieceFirst,pieceCount,fixupFirst,fixupCount;};',
        'struct Function {std::uint32_t begin,end,data,size,parent;};','struct Phase {std::uint32_t control,owner,handler,data,prolog,stack;};',
        'struct Storage {std::uint32_t offset,size;};',f'inline constexpr std::uintptr_t CapturedBase={inventory["captured_base"]}ull;',
        f'inline constexpr std::uint32_t ImageSize={inventory["image_size"]};',
        f'inline constexpr std::uint32_t SourceEditCount={inventory["source_edit_count"]};',
        f'inline constexpr std::uint32_t SourcePublicationCount={inventory["source_publication_count"]};',
        'inline constexpr std::uint32_t HelperPublicationCount=4;',
        f'inline constexpr std::uint32_t EditCount={inventory["source_publication_count"]+5+4};',
        'inline constexpr std::uint32_t ExtraFunctionCount=6;']
    def array(type_,name,rows):
        text.append(f'inline constexpr {type_} {name}[]={{')
        text.extend('{'+','.join(str(v)+'u' for v in row)+'},' for row in rows)
        text.append('};')
    array('Guard','Guards',guards)
    array('Normalization','Normalizations',[(n['rva'],n['target']) for n in inventory['normalizations']])
    array('Piece','Pieces',pieces);array('Fixup','Fixups',fixups);array('Template','Templates',templates)
    array('Function','Functions',functions);array('Phase','Phases',phases);array('Storage','StorageSpans',inventory['storage'])
    text.append('inline constexpr unsigned char Data[]={')
    text.extend(','.join(str(b) for b in data[i:i+32])+',' for i in range(0,len(data),32));text.extend(['};','}'])
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text('\n'.join(text)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--module',type=Path);parser.add_argument('--executable',type=Path);parser.add_argument('--seed',type=Path)
    args=parser.parse_args()
    if bool(args.module)!=bool(args.executable) or args.seed and not args.module:parser.error('Private regeneration needs module and executable paths.')
    if args.module:regenerate(args.module,args.executable,args.seed)
    generate(args.output)
