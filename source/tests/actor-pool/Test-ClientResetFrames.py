"""Export the two client-clear frames for a real owned Windows DLL."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import struct
import sys

SOURCE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SOURCE/'patches/actor_pool'))
from captured_code import CapturedCode
from shape import ActorShape
from client_snapshots import ClientSnapshots
from client_snapshot_reset import prepare_client_snapshot_resets
from client_reset_frames import emit_client_reset_frames


def export(module: Path,executable: Path,output: Path,actors: int) -> None:
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab output folder.')
    code=CapturedCode(module,executable)
    layout=ClientSnapshots(code.base+0x2E000000,ActorShape(actors))
    frames=prepare_client_snapshot_resets(code,layout,code.base+0x201D0000)
    assembly=emit_client_reset_frames(frames)
    refusals=0
    bad_sets=[frames[:1],tuple(reversed(frames)),(frames[0],frames[0])]
    for index,frame in enumerate(frames):
        prefix=3 if index==0 else 5
        for offset in (0,prefix+4,prefix+9,prefix+24,prefix+41,prefix+44,prefix+57,prefix+62):
            body=bytearray(frame.rewrite.stub);body[offset]^=1
            changed=replace(frame,rewrite=replace(frame.rewrite,stub=bytes(body)))
            bad_sets.append(tuple(changed if i==index else original for i,original in enumerate(frames)))
        changed=replace(frame,unwind=b'\x00'*8)
        bad_sets.append(tuple(changed if i==index else original for i,original in enumerate(frames)))
    for changed in bad_sets:
        try:emit_client_reset_frames(changed)
        except ValueError:refusals+=1
        else:raise AssertionError('An unsupported client clear static template was admitted.')
    output.mkdir(parents=True)
    (output/'ClientResetTemplates.asm').write_text(assembly,encoding='ascii')
    raw=b'BO3CRF01'+struct.pack('<I',layout.client_bytes)
    for frame in frames:
        raw+=struct.pack('<II',len(frame.rewrite.stub),len(frame.unwind))+frame.rewrite.stub+frame.unwind
    (output/'templates.bin').write_bytes(raw)
    paths=(Path(__file__),SOURCE/'patches/actor_pool/client_reset_frames.py',
           SOURCE/'patches/actor_pool/client_snapshot_reset.py',SOURCE/'patches/actor_pool/client_snapshots.py',
           SOURCE/'patches/actor_pool/client_actors.py',
           SOURCE/'patches/actor_pool/shape.py',SOURCE/'patches/actor_pool/captured_code.py',
           SOURCE/'patches/actor_pool/x64_table.py',output/'ClientResetTemplates.asm',output/'templates.bin')
    result={'passed':True,'actors':actors,'snapshotBytesPerLocalClient':layout.client_bytes,
            'templateRefusals':refusals,'gameWrites':0,'activationAllowed':False,
            'executableSha256':code.executable_sha256,
            'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}
    (output/'input-receipt.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=500)
    args=parser.parse_args();export(args.module,args.executable,args.output,args.actors)
