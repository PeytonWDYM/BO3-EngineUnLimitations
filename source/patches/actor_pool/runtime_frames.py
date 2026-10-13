"""Describe every native runtime fragment and continuation in the fixed actor arena."""
from dataclasses import dataclass,replace
import struct
from captured_code import CodeGuard
from runtime_recipe import RuntimeRecipe,GuardedCode
from unwind import native_frames
from native_unwind import read_frame,active_operations
from native_handlers import prepare_native_handler
from continuation_unwind import prepare_continuation_phases
from leaf_unwind import prepare_leaf_phases
from temporal_layout import TemporalLayout
from shape import ActorShape
from temporal_unwind import prepare_temporal_unwind

BRIDGE_OFFSET=0x1F1000

@dataclass(frozen=True)
class RuntimeFunction:
    begin: int
    end: int
    metadata: bytes
    parent: int | None = None

@dataclass(frozen=True)
class HandlerPhase:
    begin: int
    end: int
    control_rva: int
    runtime: tuple[int,int,int]
    handler_rva: int
    data_rva: int
    prolog: int
    temporary_bytes: int

@dataclass(frozen=True)
class RuntimeFrames:
    functions: tuple[RuntimeFunction,...]
    handlers: tuple[HandlerPhase,...]
    guards: tuple[CodeGuard,...]

def prepare_runtime_frames(source,recipe: RuntimeRecipe) -> RuntimeFrames:
    code=GuardedCode(source);native=native_frames(code);handlers=[]
    functions=[RuntimeFunction(row.begin,row.end,row.metadata) for row in recipe.phase_functions]
    if any(row.metadata[0]>>3 for row in recipe.phase_functions):
        raise ValueError('An explicit partial-prolog phase has a language handler.')
    independent=dict(recipe.independent_frames)
    for edit in recipe.edits:
        if not edit.stub:continue
        explicit=sorted((row for row in recipe.phase_functions if edit.stub_address<=row.begin<edit.stub_address+len(edit.stub)),key=lambda row:row.begin)
        if explicit:
            if explicit[0].begin!=edit.stub_address or explicit[-1].end!=edit.stub_address+len(edit.stub) or any(a.end!=b.begin for a,b in zip(explicit,explicit[1:])):
                raise ValueError('The explicit partial-prolog phases do not cover the complete body.')
            continue
        if edit.stub_address in independent:
            functions.append(RuntimeFunction(edit.stub_address,edit.stub_address+len(edit.stub),independent[edit.stub_address]));continue
        if edit.instruction_map:
            if edit.name in ('temporal_producer','temporal_rewind'):
                moved=prepare_temporal_unwind(code,TemporalLayout(ActorShape(500)),edit)
                for frame in moved:
                    original=read_frame(code,frame.source_runtime)
                    if original.has_handler:prepare_native_handler(code,original)
                    functions.append(RuntimeFunction(frame.runtime[0],frame.runtime[1],frame.metadata,
                        frame.parent_runtime[0] if frame.parent_runtime else None))
            else:
                mapping=dict(edit.instruction_map)
                start,end=min(mapping),max(mapping)
                selected=[row for row in native if start<=code.base+row[0]<end]
                if not selected:
                    for phase in prepare_leaf_phases(edit):
                        functions.append(RuntimeFunction(edit.stub_address+phase.begin,edit.stub_address+phase.end,phase.unwind_info))
                    continue
                for runtime in selected:
                    frame=read_frame(code,runtime);header=code.read(runtime[2],4)
                    size=4+((header[2]+1)&~1)*2+(12 if frame.flags&4 else 8 if frame.flags&3 else 0)
                    raw=code.guarded(code.guard(runtime[2],size))
                    if frame.has_handler:prepare_native_handler(code,frame)
                    if frame.flags not in (0,3,4):raise ValueError('A relocated function has an unknown language handler.')
                    begin=code.base+runtime[0]
                    def mapped(address: int) -> int:
                        if address not in mapping:raise ValueError('A relocated unwind boundary is not mapped.')
                        return mapping[address]
                    operations=tuple(replace(op,offset=mapped(begin+op.offset)-mapped(begin)) for op in frame.operations)
                    codes=b''.join(bytes((op.offset,op.opcode|op.info<<4))+op.payload for op in operations)
                    prolog=mapped(begin+frame.prolog)-mapped(begin)
                    metadata=bytes((raw[0],prolog,len(codes)//2,raw[3]))+codes
                    metadata+=b'\0'*(-len(metadata)%4)
                    if frame.flags&4:metadata+=raw[-12:]
                    elif frame.flags&3:metadata+=raw[-8:]
                    parent=mapped(code.base+frame.parent.runtime[0]) if frame.parent else None
                    functions.append(RuntimeFunction(mapped(begin),mapped(code.base+runtime[1]),metadata,parent))
            continue
        owner=next((row for row in native if row[0]<=edit.guard.rva<row[1]),None)
        if owner is None:
            for phase in prepare_leaf_phases(edit):
                functions.append(RuntimeFunction(edit.stub_address+phase.begin,edit.stub_address+phase.end,phase.unwind_info))
            continue
        frame=read_frame(code,owner)
        handler=prepare_native_handler(code,frame) if frame.has_handler else None
        for phase in prepare_continuation_phases(edit,active_operations(frame,edit.guard.rva)):
            begin,end=edit.stub_address+phase.begin,edit.stub_address+phase.end
            metadata=phase.unwind_info
            if handler:
                row=HandlerPhase(begin,end,edit.guard.rva,owner,handler.handler_address-code.base,
                    handler.handler_data_address-code.base,handler.prolog_bytes,phase.stack_bytes)
                index=len(handlers);handlers.append(row)
                metadata=bytes((metadata[0]|24,))+metadata[1:]+struct.pack('<II',recipe.arena+BRIDGE_OFFSET-code.base,index)
            functions.append(RuntimeFunction(begin,end,metadata))
    functions.sort(key=lambda row:row.begin)
    for previous,current in zip(functions,functions[1:]):
        if previous.end>current.begin:raise ValueError('The actor runtime records overlap.')
    by_begin={row.begin:index for index,row in enumerate(functions)}
    functions=[replace(row,parent=by_begin[row.parent]) if row.parent is not None else row for row in functions]
    return RuntimeFrames(tuple(functions),tuple(handlers),tuple(code.guards.values()))
