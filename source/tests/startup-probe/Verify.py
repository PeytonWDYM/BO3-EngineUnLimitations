"""Owned native Windows API E2E. Never starts BlackOps3.exe."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
import pefile
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
b=a.output;repo=Path(__file__).resolve().parents[3];cases=[]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
files={str(p):sha(p) for folder in ('production','owned','boot-failure') for p in (b/folder).iterdir() if p.suffix in ('.exe','.dll')}
environment=dict(os.environ)
argument='quoted "value" with trailing \\'
def run(folder,name,scenario='once'):
    native=b/folder/'VmStartupControlTarget.exe';timeline=b/(name+'.jsonl');proof=b/(name+'-proof.json')
    result=subprocess.run([str(b/folder/'BO3-Startup-Control.exe'),'--no-debugger',str(native),str(timeline),scenario,str(proof),argument],capture_output=True,text=True,timeout=40,creationflags=subprocess.CREATE_NO_WINDOW)
    rows=[json.loads(x) for x in timeline.read_text().splitlines()] if timeline.exists() else []
    return result,rows,proof
for scenario in ('once','repeated','nonmatch','other-wrapper-caller','changed-caller','unreadable','unwind','race'):
    result,rows,path=run('owned',scenario,scenario)
    assert result.returncode==0 and rows[-1]['exitCode']==0,(scenario,result.stdout,result.stderr,rows[-1] if rows else None)
    native=json.loads(path.read_text());assert native['passed'] and native['ready'] and native['apiPreserved'] and native['environmentPreserved'] and not native['debugger'],native
    assert native['sequence']==native['count']*2
    assert native['vmReads']==native['count']*13
    if scenario in ('once','repeated','other-wrapper-caller','unreadable'):
        assert native['count']==(5 if scenario=='repeated' else 1)
        assert native['wrapperCallerReadable'] and native['wrapperCallerMatches']==(scenario!='other-wrapper-caller')
        assert native['readableMask']==8191 if scenario!='unreadable' else native['readableMask']!=8191
    if scenario in ('nonmatch','changed-caller','unwind'):assert native['count']==0 and native['vmReads']==0
    if scenario=='changed-caller':assert native['rejected']==1
    if scenario=='unwind':assert native['unwindCode']==0xc0000005
    if scenario=='race':assert native['attempts']==4000 and native['count']+native['dropped']==4000 and native['dropped']>0
    cases.append({'name':scenario,'passed':True,'native':native,'timeline':str(b/(scenario+'.jsonl'))})
result,rows,proof=run('boot-failure','boot-failure')
assert result.returncode==0 and not proof.exists() and rows[-1]['exitCode']==0xc0000142,(result,rows)
cases.append({'name':'boot-failure','passed':True,'outcome':rows[-1]})
# Production locks refuse the owned binary before timeline or child creation.
timeline=b/'production-refusal.jsonl';proof=b/'production-refusal-proof.json'
result=subprocess.run([str(b/'production/BO3-Startup-Control.exe'),'--no-debugger',str(b/'owned/VmStartupControlTarget.exe'),str(timeline),'once',str(proof),argument],capture_output=True,text=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
assert result.returncode==2 and not timeline.exists() and not proof.exists()
cases.append({'name':'production-identity','passed':True})
tampered=b/'tampered';tampered.mkdir()
for p in (b/'owned').iterdir():
    if p.suffix in ('.exe','.dll'):shutil.copy2(p,tampered/p.name)
h=tampered/'Bo3EnhancedHelper.dll';data=bytearray(h.read_bytes());data[-1]^=1;h.write_bytes(data)
result=subprocess.run([str(tampered/'BO3-Startup-Control.exe'),'--no-debugger',str(tampered/'VmStartupControlTarget.exe'),str(b/'tampered.jsonl'),'once',str(b/'tampered-proof.json'),argument],capture_output=True,text=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
assert result.returncode==2 and not (b/'tampered.jsonl').exists() and not (b/'tampered-proof.json').exists()
cases.append({'name':'helper-identity','passed':True})
assert environment==dict(os.environ)
assert files=={p:sha(Path(p)) for p in files}
helper=pefile.PE(str(b/'production/Bo3EnhancedHelper.dll'))
exports=[x.name.decode() for x in helper.DIRECTORY_ENTRY_EXPORT.symbols if x.name]
assert set(exports)=={'Bo3EnhancedBoot','Bo3StartupProbeObservation','Bo3StartupProbeCounters'}
sources=list((repo/'source/launch/startup_probe').iterdir())+list((repo/'source/tests/startup-probe').iterdir())
report={'scope':'Owned API probe only. No BO3 launch or VM publication. Native world reads remain provisional.',
    'caseCount':len(cases),'cases':cases,'parentEnvironmentPreserved':True,'binaries':files,
    'sources':{str(p):sha(p) for p in sources if p.is_file()},'exports':exports}
(b/'result.json').write_text(json.dumps(report,indent=2))
