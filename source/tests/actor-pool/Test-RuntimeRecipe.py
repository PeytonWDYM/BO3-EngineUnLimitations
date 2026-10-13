"""Compare the complete fixed runtime recipe with native preparation at different address bases."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
PATCHES=Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from captured_code import CapturedCode
from runtime_recipe import prepare_recipe
from runtime_frames import prepare_runtime_frames
from runtime_templates import make_template,render_template
from shape import ActorShape
from temporal_layout import TemporalLayout
from temporal_caller import caller_frame
from caller_unwind import CALLER_UNWIND
from native_unwind import read_frame

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
            'temporal_producer','temporal_rewind','temporal_history_recorder','temporal_history_selector',
            'pose_backup_frame_unwind','server_actor_snapshot_count'}
        # The shared caller owns two separate expanded buffers and one native cleanup descriptor.
        pose_growth=(500-64)*24
        caller=caller_frame(TemporalLayout(ActorShape(500)))
        allocation=next(e for e in recipe.edits if e.guard.rva==0x1580014)
        assert struct.unpack('<I',allocation.replacement[1:])[0]==caller.allocation+pose_growth
        unwind=next(e for e in recipe.edits if e.guard.rva==CALLER_UNWIND.rva)
        original=current.guarded(CALLER_UNWIND)
        assert unwind.replacement[0]==original[0] and unwind.replacement[0]>>3==3
        assert unwind.replacement[-8:-4]==original[-8:-4]
        old_cookie=struct.unpack_from('<I',original,76)[0]
        new_cookie=struct.unpack_from('<I',unwind.replacement,76)[0]
        assert new_cookie&7==old_cookie&7
        assert new_cookie&~7==caller.cookie+0x100+pose_growth
        original_frame=read_frame(current,(0x1580000,0x158063F,CALLER_UNWIND.rva))
        slot=0
        for operation in original_frame.operations:
            position=4+slot*2
            if operation.opcode==1:
                assert struct.unpack_from('<H',unwind.replacement,position+2)[0]*8==caller.allocation+pose_growth
            elif operation.opcode in (4,8):
                scale=16 if operation.opcode==8 else 8
                assert struct.unpack_from('<H',unwind.replacement,position+2)[0]==operation.value+(caller.growth+pose_growth)//scale
            slot+=2 if operation.opcode in (1,4,8) else 1
        assert not any(e.name in ('sentient_load_record_count',) for e in recipe.edits)
        for guard in recipe.guards:code.guarded(guard)
        frames=prepare_runtime_frames(current,recipe)
        assert len(frames.functions)>1900 and frames.handlers
        records=sorted((f.begin,f.end) for f in frames.functions)
        assert all(a<b for a,b in records) and all(a<=b for (_,a),(b,_) in zip(records,records[1:]))
        explicit={(row.begin,row.end,row.metadata) for row in recipe.phase_functions}
        assert explicit and all(metadata[0]>>3==0 for _,_,metadata in explicit)
        assert explicit<={(row.begin,row.end,row.metadata) for row in frames.functions}
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
