"""Fixed owned cooperative callback E2E. Never starts BlackOps3.exe."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
b=a.output;repo=Path(__file__).resolve().parents[3]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
files={str(p):sha(p) for p in b.rglob('*') if p.suffix in ('.exe','.dll')}
environment=dict(os.environ);cases=[]
accepted=('success','repeated')
ignored=('nonmatch','noncrt','wrongthread','changedcaller','unwind')
boot=('missing','duplicate','abi','size','pid','tid','created','nonce','deadline','alias','dupalias','type','missingquery','missinganchor')
for scenario in accepted+ignored+('timeout','prerelease','parentloss')+boot:
    receipt=b/(scenario+'.json');proof=Path(str(receipt)+'-child.json')
    completed=subprocess.run([str(b/'owned/GateHarness.exe'),scenario,str(receipt)],capture_output=True,text=True,timeout=12,creationflags=subprocess.CREATE_NO_WINDOW)
    assert completed.returncode==0,(scenario,completed.stdout,completed.stderr)
    native=json.loads(receipt.read_text())
    if scenario in accepted+ignored:
        assert native['exitCode']==0,(scenario,native)
        child=json.loads(proof.read_text());assert child['passed'] and child['tlsLoaderProof'] and child['dllLoaderProof'] and child['apiPreserved'] and child['environmentPreserved'] and not child['debugger'],child
        assert child['anchorAvailable']==1 and child['mainAnchor']==1 and child['tlsAnchor']==0 and child['dllAnchor']==0,child
        assert native['readySeen']==(scenario in accepted)
        if scenario in accepted:
            assert native['phaseAtReady']==2 and native['generation']==1 and native['observationCount']==1
            assert native['callbackThreadId']==native['primaryThreadId'] and native['loaderCallout']==0
            assert child['phase']==4 and child['generation']==1 and child['vmReads']==13
        else:assert child['phase']==1 and child['generation']==0 and child['vmReads']==0
        if scenario=='unwind':assert child['unwindCode']==0xc0000005
        native['childProof']=child
    elif scenario in boot:
        assert native['exitCode']==0xc0000142 and not native['readySeen'] and not proof.exists(),(scenario,native)
    elif scenario=='prerelease':
        assert native['exitCode']==0xe0427602 and not native['readySeen'] and not proof.exists(),native
    else:
        assert native['exitCode']==0xe0427604 and native['readySeen'] and not proof.exists(),(scenario,native)
        if scenario=='timeout':assert 900<=native['elapsedMs']<5000,native
    cases.append({'name':scenario,'passed':True,'native':native})
assert dict(os.environ)==environment and files=={p:sha(Path(p)) for p in files}
sources=list((repo/'source/launch/startup_gate').glob('*'))+list((repo/'source/tests/startup-gate').glob('*'))
(b/'result.json').write_text(json.dumps({'scope':'Owned gate handshake only. No BO3 launch, debugger or native VM edits.',
    'caseCount':len(cases),'cases':cases,'parentEnvironmentPreserved':True,'binaries':files,'sources':{str(p):sha(p) for p in sources if p.is_file()}},indent=2))
print(f'{len(cases)} owned native gate cases passed.')
