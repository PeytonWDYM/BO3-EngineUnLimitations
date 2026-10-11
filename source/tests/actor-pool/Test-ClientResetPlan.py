"""Check the complete guarded export, including both disabled client reset frames."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

PATCHES=Path(__file__).resolve().parents[2]/'patches/actor_pool'


def run(module: Path,executable: Path,output: Path,actors: int) -> dict:
    output=output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new private BO3 lab output folder.')
    process=subprocess.run([sys.executable,'-B',str(PATCHES/'Prepare-ActorPlan.py'),
                            '--module',str(module),'--executable',str(executable),
                            '--output',str(output),'--actors',str(actors)],capture_output=True,text=True)
    assert process.returncode==0,process.stderr
    plan=json.loads((output/'plan.json').read_text())
    snapshots=plan['clientSnapshotPreparation']
    reset=snapshots['resetPreparation']
    assert plan['deploymentAllowed'] is snapshots['deploymentAllowed'] is reset['deploymentAllowed'] is False
    assert len(reset['rewrites'])==len(reset['staticPEFrames'])==2
    assert [edit['rva'] for edit in reset['rewrites']]==['0x8f0ab4','0x92ec08']
    assert [frame['codeBytes'] for frame in reset['staticPEFrames']]==[70,72]
    assert [frame['unwindInfo'] for frame in reset['staticPEFrames']]==['0107010007620000','0109010009620000']
    assembly=output/reset['staticTemplateFile']
    assert hashlib.sha256(assembly.read_bytes()).hexdigest()==reset['staticTemplateSha256']
    edits=plan['rewrites']+plan['wirePreparation']['rewrites']+snapshots['rewrites']+reset['rewrites']
    native=sorted((int(edit['rva'],0),int(edit['rva'],0)+edit['size']) for edit in edits)
    assert len(native)==164 and all(left[1]<=right[0] for left,right in zip(native,native[1:]))
    storage=[(int(region['address'],0),int(region['address'],0)+region['bytes']) for region in plan['storageRegions']]
    storage.append((int(snapshots['storageAddress'],0),int(snapshots['storageAddress'],0)+snapshots['storageBytes']))
    code=[]
    for edit in edits:
        if 'stubFile' not in edit:continue
        body=(output/edit['stubFile']).read_bytes()
        assert hashlib.sha256(body).hexdigest()==edit['stubSha256']
        address=int(edit['stubAddress'],0);code.append((address,address+len(body)))
    intervals=sorted(storage+code)
    assert all(left[1]<=right[0] for left,right in zip(intervals,intervals[1:]))
    assert all(frame['gameBindingVerified'] is False for frame in reset['staticPEFrames'])
    result={'passed':True,'actors':actors,'nativeEdits':len(native),'storageRegions':len(storage),
            'emittedBodies':len(code),'staticResetFrames':2,'deploymentAllowed':False,
            'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'planSha256':hashlib.sha256((output/'plan.json').read_bytes()).hexdigest(),
            'staticTemplateSha256':reset['staticTemplateSha256'],'gameWrites':0}
    (output/'export-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=500)
    args=parser.parse_args();print(json.dumps(run(args.module,args.executable,args.output,args.actors)))
