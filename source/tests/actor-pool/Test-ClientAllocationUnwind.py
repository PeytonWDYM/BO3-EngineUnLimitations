"""Export the guarded client allocation continuation for real Windows frame comparison."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import capstone

PATCHES=Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from captured_code import CapturedCode
from client_allocator import prepare_client_allocation
from native_unwind import read_frame,active_operations,reference_image,stack_contract
from continuation_unwind import prepare_continuation_phases
from unwind import native_frames


def run(module: Path,executable: Path,output: Path) -> dict:
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab output folder.')
    code=CapturedCode(module,executable)
    edit=prepare_client_allocation(code,code.base+0x201E0000)
    owner=next(frame for frame in native_frames(code) if frame[0]<=edit.guard.rva<frame[1])
    frame=read_frame(code,owner);assert not frame.has_handler
    operations=active_operations(frame,edit.guard.rva)
    reference,function,control=reference_image(code,frame,edit.guard.rva)
    stack,return_offset=stack_contract(operations)
    phases=prepare_continuation_phases(edit,operations)
    assert len(phases)==7 and return_offset==88
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    rebased=bytearray(edit.stub)
    for instruction in decoder.disasm(edit.stub,edit.stub_address):
        if not instruction.group(capstone.CS_GRP_JUMP):continue
        target=instruction.operands[0]
        assert target.type==capstone.x86.X86_OP_IMM and instruction.imm_size==4
        offset=instruction.address-edit.stub_address
        if edit.stub_address<=target.imm<edit.stub_address+len(edit.stub):
            destination=0x10000+target.imm-edit.stub_address
        else:
            assert target.imm==code.base+0x840929
            destination=target.imm-code.base-owner[0]
        struct.pack_into('<i',rebased,offset+instruction.imm_offset,destination-(0x10000+offset+instruction.size))
    data=bytearray(b'BO3NFUW1'+struct.pack('<I',1))
    data+=struct.pack('<11I',edit.guard.rva,len(reference),*function,control,len(stack),return_offset,
                      len(edit.stub),len(phases),owner[1]-owner[0])
    data+=reference+rebased
    for offset,width,register in stack:data+=struct.pack('<III',offset,width,register)
    for phase in phases:
        assert phase.stack_bytes==0 and not phase.saved_registers and not phase.unscaled_xmm_phase
        data+=struct.pack('<6I',phase.begin,phase.end,phase.stack_bytes,len(phase.unwind_info),0,len(phase.native_unwind_info))
        data+=phase.unwind_info+phase.native_unwind_info
    paths=(Path(__file__),PATCHES/'client_allocator.py',PATCHES/'client_actors.py',PATCHES/'captured_code.py',PATCHES/'x64_table.py',
           PATCHES/'native_unwind.py',PATCHES/'continuation_unwind.py',PATCHES/'unwind.py')
    receipt={'continuations':1,'instructionBoundaryProbes':len(phases),'nativeReturnOffset':return_offset,
             'fixtureSha256':hashlib.sha256(data).hexdigest(),'gameWrites':0,'deploymentAllowed':False,
             'sourceFiles':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
             'scope':'Owned Windows comparison of the allocation stub and its complete native frame. No game registration.'}
    output.mkdir(parents=True)
    (output/'native-unwind.bin').write_bytes(data)
    (output/'input-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return {'output':str(output),'continuations':1,'instructionBoundaryProbes':len(phases)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.output)))
