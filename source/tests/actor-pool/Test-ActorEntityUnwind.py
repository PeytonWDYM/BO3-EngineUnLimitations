"""Export the actor allocation call continuation for owned Windows frame comparison."""
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
from entity_allocator import prepare_entity_allocator,ENTITY_ALLOCATOR_OWNER,ENTITY_ALLOCATOR_UNWIND
from native_unwind import read_frame,active_operations,reference_image,stack_contract,encode
from unwind import native_frames


def run(module: Path, executable: Path, output: Path) -> dict:
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab output folder.')
    code=CapturedCode(module,executable)
    edit=prepare_entity_allocator(code,code.base+0x201A0000)
    owner=next(row for row in native_frames(code) if row[0]<=edit.guard.rva<row[1])
    assert owner==ENTITY_ALLOCATOR_OWNER
    frame=read_frame(code,owner)
    assert frame.flags==0 and not frame.parent
    operations=active_operations(frame,edit.guard.rva)
    metadata=encode(operations)
    assert metadata==ENTITY_ALLOCATOR_UNWIND
    reference,function,control=reference_image(code,frame,edit.guard.rva)
    stack,return_offset=stack_contract(operations)
    assert stack==((32,8,3),) and return_offset==40
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    decoder.detail=True
    instructions=list(decoder.disasm(edit.stub,edit.stub_address))
    assert sum(instruction.size for instruction in instructions)==len(edit.stub)
    rebased=bytearray(edit.stub)
    return_pcs=[]
    for instruction in instructions:
        # The stub does not change RSP or nonvolatile registers. Every boundary
        # therefore carries the complete original frame, including the call return.
        writes={instruction.reg_name(register) for register in instruction.regs_access()[1]}
        assert not writes&{'rbx','rbp','rsi','rdi','r12','r13','r14','r15'}
        assert 'rsp' not in writes or instruction.group(capstone.CS_GRP_CALL)
        if not (instruction.group(capstone.CS_GRP_JUMP) or instruction.group(capstone.CS_GRP_CALL)):
            continue
        target=instruction.operands[0]
        assert target.type==capstone.x86.X86_OP_IMM and instruction.imm_size==4
        offset=instruction.address-edit.stub_address
        if instruction.group(capstone.CS_GRP_CALL):
            assert target.imm==code.base+0x1B75050
            destination=0x19000 # Owned address; the fixture never executes G_Spawn.
            return_pcs.append(offset+instruction.size)
        elif edit.stub_address<=target.imm<edit.stub_address+len(edit.stub):
            destination=0x10000+target.imm-edit.stub_address
        else:
            assert target.imm in (code.base+0x1B75230,code.base+0x1B75246)
            destination=target.imm-code.base-owner[0]
        struct.pack_into('<i',rebased,offset+instruction.imm_offset,
                         destination-(0x10000+offset+instruction.size))
    assert len(return_pcs)==1 and return_pcs[0] in {i.address-edit.stub_address for i in instructions}
    data=bytearray(b'BO3NFUW2'+struct.pack('<I',1))
    data+=struct.pack('<11I',edit.guard.rva,len(reference),*function,control,len(stack),return_offset,
                      len(edit.stub),len(instructions),owner[1]-owner[0])
    data+=reference+rebased
    source=bytearray(edit.replacement)
    assert source[:2]==b'\x40\xe9'
    struct.pack_into('<i',source,2,0x10000-(control+6))
    data+=struct.pack('<I',len(source))+source
    for offset,width,register in stack:
        data+=struct.pack('<III',offset,width,register)
    for instruction in instructions:
        begin=instruction.address-edit.stub_address
        data+=struct.pack('<6I',begin,begin+instruction.size,0,len(metadata),0,len(metadata))
        data+=metadata+metadata
    paths=(Path(__file__),PATCHES/'entity_allocator.py',PATCHES/'captured_code.py',
           PATCHES/'native_unwind.py',PATCHES/'unwind.py',PATCHES/'x64_table.py')
    receipt={'continuations':1,'instructionBoundaryProbes':len(instructions),
             'callReturnOffsets':return_pcs,'nativeReturnOffset':return_offset,
             'owner':[hex(value) for value in owner],'metadata':metadata.hex(),
             'fixtureSha256':hashlib.sha256(data).hexdigest(),'gameWrites':0,
             'sourceFiles':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
             'scope':'Owned original-frame Windows comparison input. No G_Spawn execution or game registration.'}
    output.mkdir(parents=True)
    (output/'native-unwind.bin').write_bytes(data)
    (output/'input-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return {'output':str(output),'continuations':1,'instructionBoundaryProbes':len(instructions)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.module,args.executable,args.output)))
