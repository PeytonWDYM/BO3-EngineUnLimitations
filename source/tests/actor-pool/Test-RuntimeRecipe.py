"""Compare the complete fixed runtime recipe with native preparation at different address bases."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
PATCHES=Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from captured_code import CapturedCode
from runtime_recipe import prepare_recipe
from runtime_frames import prepare_runtime_frames
from runtime_templates import make_template,render_template

class RebasedCode:
    # Model loader-relocated image pointers. Guard checks still use the exact pinned input.
    def __init__(self,code: CapturedCode,shift: int):
        self.code=code;self.base=code.base+shift;self.shift=shift;self.meta=code.meta;self.executable_sha256=code.executable_sha256
    def read(self,rva: int,size: int) -> bytes:
        raw=bytearray(self.code.read(rva,size))
        if self.shift:
            for offset in range(len(raw)-7):
                value=struct.unpack_from('<Q',raw,offset)[0]
                if self.code.base<=value<self.code.base+self.meta['imageSize']:
                    struct.pack_into('<Q',raw,offset,value+self.shift)
        return bytes(raw)
    def guard(self,rva: int,size: int):return self.code.guard(rva,size)
    def guarded(self,guard):self.code.guarded(guard);return self.read(guard.rva,guard.size)

def run(module: Path,executable: Path,output: Path) -> dict:
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab result file.')
    code=CapturedCode(module,executable)
    cases=[];canonical={}
    for shift,arena_delta in ((0,0x20000000),(0x100000000,0x24000000),(-0x100000000,0x28000000)):
        current=RebasedCode(code,shift)
        recipe=prepare_recipe(current,current.base+arena_delta)
        assert recipe.actors==500 and recipe.sentients==540
        assert len(recipe.edits)>221 and len(recipe.storage)>=12
        assert len(recipe.guards)>100
        source=sorted((e.guard.rva,e.guard.size) for e in recipe.edits)
        assert all(a+n<=b for (a,n),(b,_) in zip(source,source[1:]))
        banks=sorted(recipe.storage)
        assert all(a>=recipe.arena and a+n<=recipe.arena+recipe.arena_bytes for a,n in banks)
        assert all(a+n<=b for (a,n),(b,_) in zip(banks,banks[1:]))
        assert {e.name for e in recipe.edits}>={'actor_load_extent','sentient_load_extent','secondary_load_count',
            'tagged_secondary_load_count','temporal_history_save_write','temporal_history_level_reset',
            'temporal_producer','temporal_rewind','temporal_history_recorder','temporal_history_selector','temporal_caller_unwind'}
        assert not any(e.name in ('sentient_load_record_count',) for e in recipe.edits)
        for guard in recipe.guards:code.guarded(guard)
        frames=prepare_runtime_frames(current,recipe)
        assert len(frames.functions)>1900 and frames.handlers
        records=sorted((f.begin,f.end) for f in frames.functions)
        assert all(a<b for a,b in records) and all(a<=b for (_,a),(b,_) in zip(records,records[1:]))
        for edit in recipe.edits:
            if edit.stub:
                selected=[(a,b) for a,b in records if edit.stub_address<=a<edit.stub_address+len(edit.stub)]
                assert selected[0][0]==edit.stub_address and selected[-1][1]==edit.stub_address+len(edit.stub)
                assert all(a==b for (_,a),(b,_) in zip(selected,selected[1:])),edit.name
            key=(edit.guard.rva,'replacement')
            if not shift:canonical[key]=make_template(current,recipe,'game',edit.guard.rva,edit.replacement,
                image_relative_operands=edit.image_relative_operands,context_relative_operands=edit.context_relative_operands)
            replacement=canonical[key]
            assert render_template(replacement,current,current.base,recipe.arena)==edit.replacement,edit.name
            if edit.stub:
                key=(edit.guard.rva,'body')
                if not shift:canonical[key]=make_template(current,recipe,'arena',edit.stub_address-recipe.arena,edit.stub,edit.instruction_map)
                body=canonical[key]
                assert render_template(body,current,current.base,recipe.arena)==edit.stub,edit.name
                if edit.instruction_map:
                    assert sum(p.size for p in body.pieces if p.source is not None)>len(edit.stub)//2,edit.name
        cases.append({'gameBase':hex(current.base),'arenaBase':hex(recipe.arena),'edits':len(recipe.edits),
            'bodies':sum(bool(e.stub) for e in recipe.edits),'storageBytes':sum(n for _,n in recipe.storage),'guards':len(recipe.guards),
            'runtimeFunctions':len(frames.functions),'handlerPhases':len(frames.handlers)})
    output.parent.mkdir(parents=True,exist_ok=True)
    paths=[Path(__file__),*PATCHES.glob('*.py')]
    result={'passed':True,'cases':cases,'gameWrites':0,'activationAllowed':False,
        'scope':'Combined recipe and complete native guards at three address bases. Runtime copying, registration and game binding require separate checks.',
        'sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    output.write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','output'):parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();print(json.dumps(run(a.module,a.executable,a.output)['cases']))
