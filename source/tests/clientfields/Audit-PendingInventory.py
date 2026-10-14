"""Reproduce the callback instruction inventory from the exact private native capture."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import struct

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SOURCE/'patches/actor_pool'))
from captured_code import CapturedCode

# Complete decoded owners, including the static pool binding and whole-engine clear.
OWNERS = ((0x132EF0,0x132FE2),(0x132FF0,0x1330D6),(0x133790,0x133A29),
          (0x1343C0,0x13542F),(0x136B70,0x136CE9),(0x136EE0,0x137190),(0x8ED490,0x8F3398))
SITES = ((0x8F26E3,'pool'),(0x8F2DB0,'pool'),(0x8F2DB9,'bytes'),
         (0x13444B,'bytes'),(0x137160,'bytes'),(0x132F59,'counts'),(0x132F60,'capacity'),
         (0x132F77,'shift'),(0x132F7F,'counts'),(0x13304D,'counts'),(0x133054,'capacity'),
         (0x133071,'shift'),(0x133079,'counts'),(0x1337F6,'counts'),(0x133811,'shift'),
         (0x136BD4,'counts'),(0x136C02,'shift'))


def inventory(module: Path,executable: Path) -> dict:
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    code=CapturedCode(module,executable)
    decoder=Cs(CS_ARCH_X86,CS_MODE_64)
    decoder.detail=True
    rows=[]
    for rva,kind in SITES:
        instruction=next(decoder.disasm(code.read(rva,15),code.base+rva,count=1))
        if kind in ('pool','counts'):
            offset,size=instruction.disp_offset,instruction.disp_size
        else:
            offset,size=instruction.imm_offset,instruction.imm_size
        raw=bytes(instruction.bytes)
        stock=int.from_bytes(raw[offset:offset+size],'little',signed=kind=='pool')
        expected={'bytes':0x20008,'counts':0x20000,'capacity':2048,'shift':11}.get(kind)
        if kind=='pool':
            assert instruction.address+instruction.size+stock==code.base+0x49925A0
        else:
            assert stock==expected
        assert any(start<=rva and rva+len(raw)<=end for start,end in OWNERS)
        rows.append({'rva':rva,'bytes':raw.hex(),'operandOffset':offset,'operandSize':size,
                     'kind':kind,'instruction':instruction.mnemonic+' '+instruction.op_str})
    guards=[vars(code.guard(start,end-start)) for start,end in OWNERS]
    return {'executableSha256':code.executable_sha256,'captureSha256':hashlib.sha256(module.read_bytes()).hexdigest(),
            'imageSize':code.meta['imageSize'],'poolRva':0x49925A0,'pointerRva':0x4992590,
            'stockCapacity':2048,'recordBytes':32,'localClients':2,'instructions':rows,'guards':guards}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--spans',type=Path)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Use a new inventory output file.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(inventory(args.module,args.executable),indent=2)+'\n',encoding='utf-8')
    if args.spans:
        if args.spans.exists():raise FileExistsError('Use a new guard spans output file.')
        code=CapturedCode(args.module,args.executable)
        raw=bytearray(struct.pack('<I',len(OWNERS)))
        for start,end in OWNERS:
            raw+=struct.pack('<II',start,end-start)+code.read(start,end-start)
        args.spans.write_bytes(raw)
    print(args.output)
