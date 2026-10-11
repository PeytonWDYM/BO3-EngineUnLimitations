"""Export the two guarded snapshot continuations for the owned Windows frame comparison."""
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
from client_snapshots import ClientSnapshots,prepare_client_snapshots
from native_unwind import read_frame,active_operations,reference_image,stack_contract
from continuation_unwind import prepare_continuation_phases
from unwind import native_frames
import capstone


def run(module: Path,executable: Path,output: Path,actors: int) -> dict:
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new output directory inside the private BO3 lab.')
    code=CapturedCode(module,executable)
    layout=ClientSnapshots(code.base+0x2E000000,ActorShape(actors))
    edits=tuple(edit for edit in prepare_client_snapshots(code,layout,code.base+0x201C0000) if edit.stub)
    assert len(edits)==2
    frames=native_frames(code)
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    decoder.detail=True
    data=bytearray(b'BO3NFUW1'+struct.pack('<I',len(edits)))
    rows=[]
    for edit in edits:
        owner=next(frame for frame in frames if frame[0]<=edit.guard.rva<frame[1])
        frame=read_frame(code,owner)
        assert not frame.has_handler
        operations=active_operations(frame,edit.guard.rva)
        reference,function,control=reference_image(code,frame,edit.guard.rva)
        stack,return_offset=stack_contract(operations)
        phases=prepare_continuation_phases(edit,operations)
        lineage=[]
        current=frame
        while current is not None:
            lineage.append(current.runtime);current=current.parent
        origin=min(item[0] for item in lineage)
        procedure_end=max(item[1] for item in lineage)-origin
        rebased=bytearray(edit.stub)
        for instruction in decoder.disasm(edit.stub,edit.stub_address):
            if instruction.group(capstone.CS_GRP_JUMP):
                target=instruction.operands[0]
                if target.type!=capstone.x86.X86_OP_IMM or instruction.imm_size!=4:
                    raise ValueError('The snapshot continuation has an unsupported branch.')
                offset=instruction.address-edit.stub_address
                destination=target.imm-code.base-origin
                struct.pack_into('<i',rebased,offset+instruction.imm_offset,destination-(0x10000+offset+instruction.size))
        data+=struct.pack('<11I',edit.guard.rva,len(reference),*function,control,len(stack),return_offset,
                          len(edit.stub),len(phases),procedure_end)
        data+=reference+rebased
        for offset,width,register in stack:data+=struct.pack('<III',offset,width,register)
        for phase in phases:
            assert phase.stack_bytes==0 and not phase.saved_registers and not phase.unscaled_xmm_phase
            data+=struct.pack('<6I',phase.begin,phase.end,phase.stack_bytes,len(phase.unwind_info),
                              len(phase.saved_registers),len(phase.native_unwind_info))
            data+=phase.unwind_info+phase.native_unwind_info
        rows.append({'siteRva':hex(edit.guard.rva),'nativeFrame':[hex(value) for value in owner],
                     'instructionBoundaryProbes':len(phases),'nativeReturnOffset':return_offset,
                     'stubSha256':hashlib.sha256(edit.stub).hexdigest(),
                     'ownedRebasedStubSha256':hashlib.sha256(rebased).hexdigest()})
    output.mkdir(parents=True)
    (output/'native-unwind.bin').write_bytes(data)
    receipt={'scope':'Owned Windows comparison of two client snapshot continuations. No game registration.',
             'actors':actors,'continuations':rows,'fixtureSha256':hashlib.sha256(data).hexdigest(),'gameWrites':0,
             'sourceFiles':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in
                            (Path(__file__),PATCHES/'client_snapshots.py',PATCHES/'native_unwind.py',
                             PATCHES/'continuation_unwind.py',PATCHES/'shape.py',PATCHES/'captured_code.py',
                             PATCHES/'x64_table.py',PATCHES/'unwind.py')},
             'moduleManifestSha256':hashlib.sha256(module.read_bytes()).hexdigest()}
    (output/'input-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return {'output':str(output),'continuations':len(edits),'actors':actors,'fixtureSha256':receipt['fixtureSha256']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=500)
    args=parser.parse_args()
    print(json.dumps(run(args.module,args.executable,args.output,args.actors)))
