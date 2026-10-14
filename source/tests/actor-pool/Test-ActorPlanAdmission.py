"""Exercise exact identity and storage refusals with private owned fixtures."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

PATCHES = Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from captured_code import CapturedCode, CodeGuard
from shape import ActorShape
from table_layout import TableLayout, NativeSentientAddress, ExternalTableAddress
from storage_plan import StorageLayout
from table_plan import prepare
from x64_table import rel32


def run(module: Path, executable: Path, output: Path, actors: int = 300) -> dict:
    output = output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new output directory inside the private BO3 lab.')
    output.mkdir(parents=True)
    cases = []
    bad_executable = output/'unknown.exe'
    bad_executable.write_bytes(b'Unknown executable fixture. No game code.')
    bad_manifest = output/'unknown-module.json'
    bad_manifest.write_text('{}\n')
    for name,manifest,binary,message in [('unknown_executable',module,bad_executable,'admitted SHA-256'),
                                         ('unknown_capture',bad_manifest,executable,'pinned private capture')]:
        target = output/name
        process = subprocess.run([sys.executable,'-B',str(PATCHES/'Prepare-ActorPlan.py'),
                                  '--module',str(manifest),'--executable',str(binary),'--output',str(target)],
                                 capture_output=True,text=True)
        assert process.returncode != 0 and message in process.stderr and not target.exists()
        cases.append({'case':name,'refusedBeforeExport':True})

    source = CapturedCode(module,executable)
    staged = output/'changed-range'
    staged.mkdir()
    (staged/'module.json').write_bytes(module.read_bytes())
    first = source.meta['ranges'][0]
    raw = bytearray((module.parent/first['file']).read_bytes())
    raw[-1] ^= 1
    (staged/first['file']).write_bytes(raw)
    changed = CapturedCode(staged/'module.json',executable)

    def refuse(name: str, action, expected: type[Exception] = ValueError) -> None:
        try:
            action()
        except expected:
            cases.append({'case':name,'refused':True})
        else:
            raise AssertionError(f'The preparation admitted {name}.')

    refuse('changed_captured_range',lambda:changed.read(0,2))
    refuse('changed_native_guard',lambda:source.guarded(CodeGuard(0x2505BB0,50,'0'*64)))
    refuse('unsupported_shape',lambda:ActorShape(200))
    refuse('rel32_out_of_range',lambda:rel32(0,1 << 31))
    layout = TableLayout(NativeSentientAddress(source.base+0x21000000),ExternalTableAddress(source.base+0x22000000),ActorShape(actors))
    storage = StorageLayout(*(source.base+offset for offset in (0x24000000,0x26000000,0x28000000,0x2A000000,0x2C000000)))
    if actors == 500:
        refuse('old_matrix_spacing_overlap',lambda:StorageLayout(source.base+0x23000000,storage.secondary_actors,storage.sentient_heads,storage.indexed_words,storage.dobj).regions(layout))
    refuse('storage_overlap',lambda:StorageLayout(storage.actors,storage.actors,storage.sentient_heads,storage.indexed_words,storage.dobj).regions(layout))
    refuse('storage_unaligned',lambda:StorageLayout(storage.actors+1,storage.secondary_actors,storage.sentient_heads,storage.indexed_words,storage.dobj).regions(layout))
    refuse('storage_wrap',lambda:StorageLayout((1 << 64)-16,storage.secondary_actors,storage.sentient_heads,storage.indexed_words,storage.dobj).regions(layout))
    refuse('matrix_owner_out_of_range',lambda:layout.owner_index(NativeSentientAddress(layout.native_pool+layout.shape.sentient_bytes)))
    refuse('matrix_target_out_of_range',lambda:layout.entry(layout.native_pool,NativeSentientAddress(layout.native_pool+layout.shape.sentient_bytes)))
    refuse('matrix_entry_overrun',lambda:layout.mapped_member(layout.native_pool,layout.native_pool+0x12A0+71,2))
    plan = prepare(source,layout,source.base+0x20000000,storage)
    refuse('incomplete_plan_activation',plan.require_activation,RuntimeError)
    regions = storage.regions(layout)
    expected = {300:(16165640,8323200,231200),500:(33932440,20995200,583200)}[actors]
    assert len(regions)==7 and sum(size for _,size in regions)==expected[0]
    assert (layout.table_bytes,plan.word_table.table_bytes)==expected[1:]
    report = {'status':'actor_preparation_admission_refusals_passed','cases':cases,
              'executableSha256':source.executable_sha256,'moduleManifestSha256':hashlib.sha256(module.read_bytes()).hexdigest(),
              'sourceFiles':{str(path.relative_to(PATCHES.parents[2])):hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in [*PATCHES.glob('*.py'),*PATCHES.glob('*.json'),Path(__file__)]},
              'actors':actors,'sentients':layout.capacity,'storageBytes':expected[0],
              'deploymentAllowed':False,'gameLaunched':False}
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return {'status':report['status'],'cases':len(cases),'output':str(output/'result.json')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True)
    parser.add_argument('--executable',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=300)
    args=parser.parse_args()
    print(json.dumps(run(args.module,args.executable,args.output,args.actors),indent=2))
