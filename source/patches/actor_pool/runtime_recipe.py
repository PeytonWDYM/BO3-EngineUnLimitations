"""Compose the fixed 500-actor recipe before runtime allocation and publication."""
from dataclasses import dataclass
from captured_code import CapturedCode,CodeGuard,Rewrite
from shape import ActorShape
from table_layout import TableLayout,NativeSentientAddress,ExternalTableAddress
from table_plan import prepare
from storage_plan import StorageLayout
from actor_wire import prepare_actor_wire
from client_snapshots import ClientSnapshots,prepare_client_snapshots
from client_snapshot_reset import prepare_client_snapshot_resets
from client_actors import ClientActors,prepare_client_actors,ACTOR_BANK_OFFSET
from context_aliases import prepare_context_aliases
from client_allocator import prepare_client_allocation
from client_actor_ring import prepare_client_actor_ring
from entity_allocator import prepare_entity_allocator,ENTITY_ALLOCATOR_UNWIND
from demo_writer import DemoWriter,prepare_demo_writer
from demo_reader import prepare_demo_reader
from temporal_layout import TemporalLayout
from temporal_history import prepare_history
from temporal_producer import prepare_producer
from temporal_rewind import prepare_rewind
from temporal_restore import prepare_restore
from temporal_caller import prepare_caller
from caller_unwind import prepare_caller_unwind
from temporal_save import prepare_history_write
from temporal_reset import prepare_history_reset
from load_counts import LoadCounts,prepare_load_counts
from unwind import native_frames
from native_unwind import read_frame

ARENA_BYTES=0x3000000
CODE_BYTES=0x200000
METADATA_OFFSET=0x200000
METADATA_BYTES=0x200000

@dataclass(frozen=True)
class RuntimeRecipe:
    arena: int
    arena_bytes: int
    actors: int
    sentients: int
    edits: tuple[Rewrite,...]
    guards: tuple[CodeGuard,...]
    storage: tuple[tuple[int,int],...]
    independent_frames: tuple[tuple[int,bytes],...]
    count_address: int
    actor_address: int
    history_address: int

class GuardedCode:
    """Record every preparation guard. The underlying capture retains its exact identity checks."""
    def __init__(self,code: CapturedCode):
        self.code=code;self.base=code.base;self.meta=code.meta;self.executable_sha256=code.executable_sha256
        self.guards: dict[tuple[int,int],CodeGuard]={}
    def read(self,rva: int,size: int) -> bytes:return self.code.read(rva,size)
    def guarded(self,guard: CodeGuard) -> bytes:
        raw=self.code.guarded(guard);self.guards[guard.rva,guard.size]=guard;return raw
    def guard(self,rva: int,size: int) -> CodeGuard:
        guard=self.code.guard(rva,size);self.guards[rva,size]=guard;return guard

def prepare_recipe(source: CapturedCode,arena: int) -> RuntimeRecipe:
    if arena&0xFFFF or arena<source.base+source.meta['imageSize'] or arena+ARENA_BYTES>source.base+0x7FFFFFFF:
        raise ValueError('The complete actor arena must be aligned, outside the game, and within relative reach.')
    code=GuardedCode(source);shape=ActorShape(500);temporal=TemporalLayout(shape)
    table=TableLayout(NativeSentientAddress(arena+0x400000),ExternalTableAddress(arena+0xB00000),shape)
    storage=StorageLayout(*(arena+offset for offset in (0x1F10000,0x2400000,0x2600000,0x2610000,0x2700000)))
    server=prepare(code,table,arena,storage)
    counts=LoadCounts(arena+0x2C40000)
    dynamic=prepare_load_counts(code,counts)
    replaced={edit.guard.rva for edit in dynamic}
    edits=[edit for edit in server.rewrites if edit.guard.rva not in replaced]
    edits.extend(dynamic)
    entity_allocation=prepare_entity_allocator(code,arena+0x1A0000)
    edits.append(entity_allocation)
    edits.extend(prepare_actor_wire(code,shape))
    snapshots=ClientSnapshots(arena+0x2800000,shape)
    edits.extend(prepare_client_snapshots(code,snapshots,arena+0x1C0000))
    resets=prepare_client_snapshot_resets(code,snapshots,arena+0x1D0000)
    edits.extend(frame.rewrite for frame in resets)
    # The operands use only the fixed bank displacement. The native allocator owns the actual root.
    model=arena+0x2E00000
    clients=ClientActors(model,model+ACTOR_BANK_OFFSET,shape)
    edits.extend(prepare_client_actors(code,clients))
    edits.extend(prepare_context_aliases(code,clients,storage.secondary_actors))
    edits.append(prepare_client_allocation(code,arena+0x1E0000))
    edits.extend(prepare_client_actor_ring(code,shape))
    demo=DemoWriter(arena+0x2B00000,shape)
    demo_edits=prepare_demo_writer(code,demo,arena+0x1F0000)+prepare_demo_reader(code,demo)
    edits.extend(demo_edits)
    history=arena+0x2C00000
    edits.extend(prepare_history(code,temporal,history,arena+0x160000,arena+0x170000))
    edits.append(prepare_producer(code,temporal,arena+0x140000))
    edits.append(prepare_rewind(code,temporal,arena+0x150000))
    edits.extend(prepare_restore(code,temporal,arena+0x180000))
    edits.extend(prepare_caller(code,temporal))
    edits.append(prepare_caller_unwind(code,temporal))
    edits.append(prepare_history_write(code,temporal,history))
    history_reset=prepare_history_reset(code,temporal,history,arena+0x190000)
    edits.append(history_reset.rewrite)
    frames=native_frames(code)
    def admit_frame(runtime: tuple[int,int,int]) -> None:
        frame=read_frame(code,runtime);rva=runtime[2];header=code.read(rva,4)
        extent=4+((header[2]+1)&~1)*2+(12 if frame.flags&4 else 8 if frame.flags&3 else 0)
        code.guard(rva,extent)
        if frame.parent:admit_frame(frame.parent.runtime)
    for edit in edits:
        owner=next((row for row in frames if row[0]<=edit.guard.rva<row[1]),None)
        if owner:
            code.guard(owner[0],owner[1]-owner[0]);admit_frame(owner)
    # The late CRT gate can follow static initialization. Verify and reproduce the complete native defaults separately.
    for rva,size,digest in ((0x19C00B0,146,'9b843882ef196d717e6a4076a4b39ca94f5dd0393ec92b1d54308bf8541477f9'),
            (0x19C0160,15,'98515196f94346f90d1e2b7b7e8c0fdf0215f2e0934edaa58422cd61fe9fc563')):
        code.guarded(CodeGuard(rva,size,digest))
    ordered=sorted(edits,key=lambda e:e.guard.rva)
    if any(a.guard.rva+a.guard.size>b.guard.rva for a,b in zip(ordered,ordered[1:])):
        raise ValueError('The combined actor recipe overlaps native edits.')
    blobs=sorted((e.stub_address,len(e.stub)) for e in edits if e.stub)
    if any(start<arena or start+size>arena+CODE_BYTES for start,size in blobs) or any(a+n>b for (a,n),(b,_) in zip(blobs,blobs[1:])):
        raise ValueError('A combined actor body exceeds or overlaps the complete code arena.')
    regions=tuple(storage.regions(table))+((snapshots.base,snapshots.total_bytes),(demo.base,demo.bytes),
        (history,temporal.history_bytes),(counts.base,24),(arena+0x2C50000,temporal.history_bytes))
    banks=sorted(regions)
    if any(a<arena+CODE_BYTES+METADATA_BYTES or a+n>arena+ARENA_BYTES for a,n in banks) or any(a+n>b for (a,n),(b,_) in zip(banks,banks[1:])):
        raise ValueError('A combined actor storage interval exceeds or overlaps the complete data arena.')
    independent=tuple((f.rewrite.stub_address,f.unwind) for f in resets)+(
        (history_reset.rewrite.stub_address,history_reset.metadata),
        (entity_allocation.stub_address,ENTITY_ALLOCATOR_UNWIND))
    leaf=next(e for e in demo_edits if e.stub)
    independent+=((leaf.stub_address,bytes.fromhex('01000000')),)
    return RuntimeRecipe(arena,ARENA_BYTES,500,540,tuple(edits),tuple(sorted(code.guards.values(),key=lambda g:(g.rva,g.size))),
                         regions,independent,counts.base,storage.actors,history)
