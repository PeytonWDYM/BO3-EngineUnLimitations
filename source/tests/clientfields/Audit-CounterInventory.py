"""Reproduce the exact clientfield counter instructions and complete owner guards."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SOURCE/'patches/actor_pool'))
from captured_code import CapturedCode

OWNERS = ((0x133560,0x133574),(0x133CA0,0x133E94),(0x1342E0,0x1343C0))
SITES = ((0x133560,'pool'),(0x133569,'bytes'),(0x133CB0,'pool'),(0x133CB7,'end'),
         (0x133D09,'capacity'),(0x133D1E,'capacity'),(0x133E04,'capacity'),
         (0x133E20,'lastField'),(0x133E27,'lastState'),(0x133E2E,'lastCount'),(0x133E38,'lastField'))


def inventory(code: CapturedCode) -> dict:
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    md=Cs(CS_ARCH_X86,CS_MODE_64);md.detail=True
    rows=[]
    targets={'pool':0x41C9C30,'end':0x41D5C30,'lastField':0x41D5C18,'lastState':0x41D5C20,'lastCount':0x41D5C28}
    for rva,kind in SITES:
        instruction=next(md.disasm(code.read(rva,15),code.base+rva,count=1))
        raw=bytes(instruction.bytes)
        offset,size=(instruction.disp_offset,instruction.disp_size) if kind in targets else (instruction.imm_offset,instruction.imm_size)
        stock=int.from_bytes(raw[offset:offset+size],'little',signed=kind in targets)
        assert size==4 and any(begin<=rva and rva+len(raw)<=end for begin,end in OWNERS)
        assert instruction.address+len(raw)+stock==code.base+targets[kind] if kind in targets else stock=={'bytes':49152,'capacity':2048}[kind]
        rows.append({'rva':rva,'bytes':raw.hex(),'operandOffset':offset,'operandSize':size,'kind':kind,
                     'instruction':instruction.mnemonic+' '+instruction.op_str})
    return {'executableSha256':code.executable_sha256,'captureSha256':hashlib.sha256(code.manifest.read_bytes()).hexdigest(),
            'imageSize':code.meta['imageSize'],'poolRva':0x41C9C30,'stockCapacity':2048,'recordBytes':24,
            'instructions':rows,'guards':[vars(code.guard(begin,end-begin)) for begin,end in OWNERS]}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--spans',type=Path)
    args=parser.parse_args()
    if args.output.exists() or args.spans and args.spans.exists():raise FileExistsError('Use new inventory and spans paths.')
    code=CapturedCode(args.module,args.executable)
    args.output.write_text(json.dumps(inventory(code),indent=2)+'\n',encoding='utf-8')
    if args.spans:
        raw=bytearray(struct.pack('<I',len(OWNERS)))
        for begin,end in OWNERS:raw+=struct.pack('<II',begin,end-begin)+code.read(begin,end-begin)
        args.spans.write_bytes(raw)
    print(hashlib.sha256(args.output.read_bytes().replace(b'\r\n',b'\n')).hexdigest())
