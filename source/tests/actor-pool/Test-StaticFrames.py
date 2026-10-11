"""Export a guarded reset template for the owned static PE frame experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

SOURCE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SOURCE/'patches/actor_pool'))
from captured_code import CapturedCode
from shape import ActorShape
from temporal_layout import TemporalLayout
from temporal_reset import prepare_history_reset
from static_frames import emit_called_frame


def export(module: Path,executable: Path,output: Path,actors: int) -> None:
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab output folder.')
    code=CapturedCode(module,executable)
    layout=TemporalLayout(ActorShape(actors))
    prepared=prepare_history_reset(code,layout,code.base+0x24000000,code.base+0x20000000)
    assembly=emit_called_frame('Bo3HistoryResetTemplate',prepared.rewrite.stub,prepared.metadata)
    assert len(prepared.rewrite.stub)==47 and prepared.metadata==bytes.fromhex('0104010004420000')
    altered=bytearray(prepared.rewrite.stub)
    altered[19:21]=b'\x50\x58'
    refusals=0
    for name,body,metadata in (('bad\n.code',prepared.rewrite.stub,prepared.metadata),
                               ('BadFrame',prepared.rewrite.stub,b'\x00'*8),
                               ('BadBody',b'\xc3',prepared.metadata),
                               ('AlteredBody',bytes(altered),prepared.metadata)):
        try:emit_called_frame(name,body,metadata)
        except ValueError:refusals+=1
        else:raise AssertionError('An unsupported static frame template was admitted.')
    assert refusals==4
    output.mkdir(parents=True)
    (output/'ResetTemplate.asm').write_text(assembly,encoding='ascii')
    raw=b'BO3SFM01'+struct.pack('<III',len(prepared.rewrite.stub),len(prepared.metadata),layout.history_bytes)
    raw+=prepared.rewrite.stub+prepared.metadata
    (output/'template.bin').write_bytes(raw)
    paths=[Path(__file__),SOURCE/'patches/actor_pool/static_frames.py',SOURCE/'patches/actor_pool/temporal_reset.py',
           output/'ResetTemplate.asm',output/'template.bin']
    result={'passed':True,'actors':actors,'historyBytes':layout.history_bytes,'templateRefusals':refusals,'gameWrites':0,'deploymentAllowed':False,
            'executableSha256':code.executable_sha256,'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}
    (output/'input-receipt.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=500)
    args=parser.parse_args();export(args.module,args.executable,args.output,args.actors)
