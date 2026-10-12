"""Export guarded demo frames and complete native GS helpers for real owned Windows exception dispatch."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES=Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from captured_code import CapturedCode,CodeGuard
from demo_writer import DemoWriter,prepare_demo_writer,WRITER,METADATA
from native_handlers import prepare_native_handler
from native_unwind import read_frame
from shape import ActorShape

HELPER_METADATA=(
    CodeGuard(0x3242F18,8,'2d8867f028f39ef522d70e56d169d2fbb9046163869f9360ec470bdd2040cd24'),
    CodeGuard(0x3242F10,8,'eb874a2d5756386f3a7d463290a08f132ac00fa4e4080cfb811bafc05b2569b2'),
    CodeGuard(0x3242F20,4,'67abdd721024f0ff4e0b3f4c2fc13bc5bad42d0b7851d456d88d203d15aaa450'),
)


def run(module: Path,executable: Path,output: Path) -> dict:
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab output directory.')
    code=CapturedCode(module,executable);profile=json.loads((PATCHES/'native_handlers.json').read_text())
    helpers=[CodeGuard(int(profile[name]['rva'],0),profile[name]['size'],profile[name]['sha256']) for name in ('handler','common','cookie')]
    bodies=[code.guarded(guard) for guard in helpers];metadata=[code.guarded(guard) for guard in HELPER_METADATA]
    prepare_native_handler(code,read_frame(code,(WRITER.rva,WRITER.rva+WRITER.size,METADATA.rva)))
    original=code.guarded(WRITER);old_metadata=code.guarded(METADATA)
    data=bytearray(b'BO3DGSW1'+struct.pack('<I',3));cases=[]
    for actors in (64,300,500):
        body=bytearray(original);root_metadata=bytearray(old_metadata)
        if actors!=64:
            edits=prepare_demo_writer(code,DemoWriter(code.base+0x32000000,ActorShape(actors)),code.base+0x201F0000)
            for edit in edits:
                if WRITER.rva<=edit.guard.rva<WRITER.rva+WRITER.size:
                    offset=edit.guard.rva-WRITER.rva;body[offset:offset+edit.guard.size]=edit.replacement
                elif edit.guard.rva==METADATA.rva:root_metadata=bytearray(edit.replacement)
        struct.pack_into('<i',body,0x22,0x3000-0x26)
        struct.pack_into('<i',body,0x294,0x109C-0x298)
        # Replace only the body with owned normal-return and exception paths. Native frame setup/teardown stay complete.
        authored=bytearray(b'\xb8\x34\x12\x00\x00')
        if actors!=64:authored+=bytes.fromhex('48c784246001000000000000')
        authored+=b'\x85\xc9\x0f\x84'+struct.pack('<i',0x288-(0x31+len(authored)+8))
        authored+=b'\xe8'+struct.pack('<i',0x2020-(0x31+len(authored)+5))
        authored+=b'\xe9'+struct.pack('<i',0x288-(0x31+len(authored)+5))
        assert len(authored)<0x288-0x31
        body[0x31:0x288]=authored+b'\x90'*(0x288-0x31-len(authored))
        struct.pack_into('<I',root_metadata,32,0x1000)
        cookie=bytearray(bodies[2]);struct.pack_into('<i',cookie,3,0x3000-(0x109C+7))
        struct.pack_into('<i',cookie,27,0x2000-(0x109C+31))
        image=bytearray(0x4000)
        for address,raw in ((0,body),(0x1000,bodies[0]),(0x1020,bodies[1]),(0x109C,cookie),(0x1400,root_metadata),
                            (0x1428,metadata[0]),(0x1430,metadata[1]),(0x1438,metadata[2])):
            image[address:address+len(raw)]=raw
        struct.pack_into('<Q',image,0x3000,0x00002A780CACEBAD)
        data+=struct.pack('<II',actors,len(image))+image
        cases.append({'actors':actors,'writerBytes':len(body),'cookieOffset':struct.unpack_from('<I',root_metadata,36)[0],
                      'nativeGsHelpers':3,'authoredBody':True,'relocatedCookieFailureBindings':True})
    output.mkdir(parents=True);(output/'demo-gs-windows.bin').write_bytes(data)
    paths=(Path(__file__),PATCHES/'demo_writer.py',PATCHES/'native_handlers.py',PATCHES/'native_handlers.json',PATCHES/'native_unwind.py',PATCHES/'x64_table.py',PATCHES/'shape.py',PATCHES/'captured_code.py')
    result={'passedExport':True,'cases':cases,'fixtureSha256':hashlib.sha256(data).hexdigest(),
            'sourceFiles':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},'activationAllowed':False,'gameWrites':0,
            'scope':'Guarded native frame setup/teardown and complete GS helpers with owned cookie/failure/exception bindings and authored body. Real game code and game registration remain separate.'}
    (output/'input-receipt.json').write_text(json.dumps(result,indent=2)+'\n');return {'passedExport':True,'cases':3,'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.output)))
