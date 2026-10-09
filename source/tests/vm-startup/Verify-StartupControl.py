"""Owned native control E2E only; never starts BlackOps3.exe."""
import argparse,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
parser=argparse.ArgumentParser()
for name in ('bin','production','output'): parser.add_argument('--'+name,type=Path,required=True)
args=parser.parse_args()
repo=Path(__file__).resolve().parents[3]
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for folder in (args.bin,args.production) for p in folder.iterdir() if p.suffix in ('.exe','.dll')}
environment=dict(os.environ)
control=args.bin/'BO3-Startup-Control.exe'; target=args.bin/'VmStartupControlTarget.exe'
argument='quoted "value" with trailing \\'
cases=[]
def start(binary,native,timeline,scenario,proof,no_debugger=False,seconds=None,game_tail=False):
    options=(["--no-debugger"] if no_debugger else [])+(["--observe-seconds",str(seconds)] if seconds is not None else [])
    command=[str(binary)]+options+[str(native),str(timeline),scenario,str(proof),argument]
    if game_tail: command += ["--observe-seconds","unrestricted-game-value"]
    return subprocess.Popen(command,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
def refusal(name,binary,native):
    timeline=args.output/(name+'.jsonl'); proof=args.output/(name+'-proof.json')
    child=start(binary,native,timeline,'entry',proof)
    stdout,stderr=child.communicate(timeout=10)
    assert child.returncode==2 and not timeline.exists() and not proof.exists(),(stdout,stderr)
    cases.append({'name':name,'passed':True,'stderr':stderr.strip()})
specs=[(s,s,None,False) for s in ('entry','exception','tls-breakpoint','breakpoint','timeout','detach-exit','event-stream','passive-entry','passive-exception','passive-exit','passive-timeout')]
specs += [('explicit-30','passive-entry',30,False),('game-options-literal','passive-entry',None,True),('long-debug-timeout','timeout',120,False),('long-passive-timeout','passive-timeout',120,False)]
for name,scenario,seconds,game_tail in specs:
    passive=scenario.startswith('passive-')
    deadline_ms=(seconds or 30)*1000
    timeout=scenario in ('timeout','event-stream','passive-timeout')
    timeline=args.output/(name+'.jsonl'); proof=args.output/(name+'-proof.json')
    child=start(control,target,timeline,scenario,proof,passive,seconds,game_tail)
    if name=='timeout':
        for _ in range(100):
            if proof.exists():break
            assert child.poll() is None
            time.sleep(.05)
        assert proof.exists()
        refusal('concurrent-lease',control,target)
    if seconds==120:
        # Native wall time proves the prior deadline did not terminate this child.
        time.sleep(31)
        assert child.poll() is None
    stdout,stderr=child.communicate(timeout=(seconds or 30)+10)
    assert child.returncode==0,(stdout,stderr)
    rows=[json.loads(line) for line in timeline.read_text().splitlines()]
    native=json.loads(proof.read_text())
    assert native['queryStatus']==0 and native['debugger']==(not passive) and native['bootReady'] and native['steamIds'] and native['argumentPreserved'] and native['gameOptionsPreserved']
    assert all(native[n]==0 for n in ('dr0','dr1','dr2','dr3')) and native['dr7']&0xffff00ff==0
    assert native['handled']==(1 if scenario in ('exception','tls-breakpoint','breakpoint','passive-exception') else 0)
    observations=[r for r in rows if r['event']=='observation']
    assert any(r['bootReady']==1 and r['bootAbi']==1 and r['bootBytes']==24 and r['bootReserved']==0
               and r['bootModule']==r['helperBase'] and r['poolReadable'] and r['poolPointer']==0 and r['hashReadable'] and r['hashPointer']==0 for r in observations)
    threads=[r for r in rows if r['event']=='thread']
    assert bool(threads)==(not passive)
    assert all(all(r[n]==0 for n in ('dr0','dr1','dr2','dr3')) and r['dr7']&0xffff00ff==0 for r in threads)
    assert rows[-1]['event']=='outcome' and rows[-1]['childExited'] and rows[-1]['editsWritten']==0 and not rows[-1]['activated']
    assert rows[0]['debugger']==(not passive) and rows[0]['deadlineMs']==deadline_ms
    assert f'after {seconds or 30} seconds' in stdout
    assert rows[-1]['timedOut']==timeout and rows[-1]['exitCode']==(97 if timeout else 23 if scenario in ('detach-exit','passive-exit') else 0)
    assert rows[-1]['debugExitSeen']==(not passive and scenario!='detach-exit')
    if passive or scenario=='detach-exit':
        assert any(r['event']=='process-exit' and r['exitCode']==rows[-1]['exitCode'] for r in rows)
    if passive:
        assert not any(r['event'] in ('debug','thread') for r in rows)
    if scenario=='detach-exit':
        assert rows[-1]['elapsedMs']<5000
    if scenario=='event-stream':
        assert sum(r['event']=='debug' and r['code']==8 for r in rows)>100
    if scenario=='exception':
        assert any(r['event']=='debug' and r.get('exceptionCode')==0xe0427630 and r['continuation']==0x80010001 for r in rows)
    if scenario in ('tls-breakpoint','breakpoint'):
        assert any(r['event']=='debug' and r.get('exceptionCode')==0x80000003 and r['continuation']==0x80010001 for r in rows)
    if timeout:
        assert any(r['event']=='timeout' and r['deadlineMs']==deadline_ms and deadline_ms<=r['elapsedMs']<deadline_ms+1000 for r in rows)
    cases.append({'name':name,'passed':True,'observationSeconds':seconds or 30,'native':native,'timeline':str(timeline),'outcome':rows[-1]})
# Invalid leading options must fail before creating either the target or its timeline.
invalid_options=[('duration-unsupported',['--observe-seconds','60']),
    ('duration-malformed',['--observe-seconds','120ms']),
    ('duration-missing',['--observe-seconds']),
    ('duration-duplicate',['--observe-seconds','30','--observe-seconds','120']),
    ('debugger-duplicate',['--no-debugger','--no-debugger']),
    ('unknown-option',['--unknown'])]
for name,options in invalid_options:
    timeline=args.output/(name+'.jsonl'); proof=args.output/(name+'-proof.json')
    command=[str(control)]+options
    if name!='duration-missing': command += [str(target),str(timeline),'entry',str(proof),argument]
    child=subprocess.run(command,capture_output=True,text=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
    assert child.returncode==2 and not timeline.exists() and not proof.exists(),child
    cases.append({'name':name,'passed':True,'stderr':child.stderr.strip()})
refusal('production-refuses-owned-target',args.production/'BO3-Startup-Control.exe',target)
tampered=args.output/'tampered';tampered.mkdir()
for p in args.bin.iterdir():
    if p.suffix in ('.exe','.dll'):shutil.copy2(p,tampered/p.name)
helper=tampered/'Bo3EnhancedHelper.dll'; data=bytearray(helper.read_bytes());data[-1]^=1;helper.write_bytes(data)
refusal('wrong-helper-hash',tampered/'BO3-Startup-Control.exe',tampered/target.name)
# Output admission must resolve a directory junction before creating timeline or child.
junction=args.output/'repo-junction'
link_text=str(junction).replace("'","''"); target_text=str(repo).replace("'","''")
subprocess.run(['pwsh','-NoProfile','-Command',f"New-Item -ItemType Junction -Path '{link_text}' -Target '{target_text}' | Out-Null"],check=True,capture_output=True)
try:
    rejection=junction/'control-must-not-create.jsonl'
    child=start(control,target,rejection,'entry',args.output/'junction-proof.json')
    stdout,stderr=child.communicate(timeout=10)
    assert child.returncode==2 and not rejection.exists() and not (args.output/'junction-proof.json').exists(),(stdout,stderr)
    cases.append({'name':'junction-output','passed':True,'stderr':stderr.strip()})
finally:
    os.rmdir(junction)
assert environment==dict(os.environ)
assert before=={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in before}
sources=[repo/'source/launch/enhanced'/n for n in ('StartupControl.h','StartupControl.cpp','StartupObservation.h','StartupObservation.cpp','StartupPassive.cpp','StartupDiagnostic.cpp','Build-StartupDiagnostic.ps1','SteamContext.cpp','SteamContext.h','LaunchLease.h','Boot.h','PhysicalPath.ps1')]
sources += [repo/'source/launch/preentry'/n for n in ('Identity.cpp','Identity.h')]
sources += [repo/'source/tests/vm-startup'/n for n in ('StartupControlFailures.txt','StartupControlTarget.cpp','Control-Profile.py','Compile-StartupControl.ps1','Test-StartupControl.ps1','Verify-StartupControl.py')]
report={'scope':'Owned native control only. No BO3 launch, DR writes, VM activation, production launcher modification or normal file changes.',
        'caseCount':len(cases),'cases':cases,'binaries':before,'sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'parentEnvironmentPreserved':True}
(args.output/'result.json').write_text(json.dumps(report,indent=2))
