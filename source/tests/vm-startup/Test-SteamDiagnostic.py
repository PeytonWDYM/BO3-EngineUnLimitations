"""Owned config and inert native argv/environment recorder only."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'source'))
from patcher.steam_launch import SteamPlay, launch_field
from patcher.errors import PatchError
from patcher.paths import private_path

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--target',type=Path,required=True)
    parser.add_argument('--pwsh',type=Path,required=True)
    args=parser.parse_args()
    root=private_path(args.output,installations=(ROOT,))
    root.mkdir(parents=True,exist_ok=False)
    # Both entrypoints must reject an output alias into the source tree before writes.
    junction=root/'owned output junction'
    linked=subprocess.run(['cmd','/c','mklink','/J',str(junction),str(ROOT)],capture_output=True,text=True)
    assert linked.returncode==0,linked.stderr
    forbidden=junction/('must-not-create-'+root.name)
    direct=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--output',str(forbidden),
                           '--target',str(args.target),'--pwsh',str(args.pwsh)],capture_output=True,text=True,timeout=20)
    build_guard=subprocess.run([str(args.pwsh),'-NoLogo','-NoProfile','-File',str(Path(__file__).with_name('Build-SteamDiagnostic.ps1')),
                                '-OutputDirectory',str(forbidden),'-Python',sys.executable],capture_output=True,text=True,timeout=20)
    assert direct.returncode!=0 and 'redirects through a link' in direct.stderr
    assert build_guard.returncode!=0 and 'Keep owned outputs outside the repository' in build_guard.stderr
    assert not forbidden.exists()
    (root/'output-guard-result.json').write_text(json.dumps({'passed':True,'directExit':direct.returncode,
        'buildExit':build_guard.returncode,'repositoryOutputCreated':False},indent=2)+'\n')
    spec=importlib.util.spec_from_file_location('steam_diagnostic',ROOT/'source/launch/enhanced/SteamDiagnostic.py')
    setup=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=setup
    spec.loader.exec_module(setup)
    steam=root/'Steam fixture'
    config=steam/'userdata/42/config/localconfig.vdf'
    config.parent.mkdir(parents=True)
    original=b'"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { "311210" { "LastPlayed" "keep" } } } } } }\r\n'
    config.write_bytes(original)
    game=root/'game with spaces'/ 'BlackOps3.exe'
    game.parent.mkdir()
    game.write_bytes(b'Inert owned game: never execute')
    (game.parent/'settings.ini').write_bytes(b'owned settings')
    build=root/'owned control build'
    build.mkdir()
    control=build/'BO3-Startup-Control.exe'
    control.write_bytes(args.target.read_bytes())
    helper=build/'Bo3EnhancedHelper.dll'; helper.write_bytes(b'inert owned helper')
    license=build/'Detours-LICENSE.md'; license.write_bytes(b'owned fixture license')
    profile={'schemaVersion':1,'mode':'--no-debugger','capacity':'stock','deadlineSeconds':120,
             'gameSha256':sha(game),'files':{p.name:sha(p) for p in (control,helper,license)}}
    manager=SteamPlay(steam,active_user=42,state=root/'receipt',process_running=lambda name:False)
    diag=setup.DiagnosticSetup(manager,profile=profile,tools_root=root/'private tools')
    result=diag.enable(build,game,root/'private logs',args.pwsh)
    assert result['status']=='enabled'
    assert result['deadlineSeconds']==120
    shim=Path(result['shim'])
    arguments=['space value','é漢字','','quoted "value"','trailing \\','-NoProfile','--flag=value','--observe-seconds','5']
    environment=dict(os.environ,SteamAppId='owned app',SteamGameId='owned game',SteamOverlayGameId='owned overlay')
    for _ in range(2):
        child=subprocess.run([str(args.pwsh),'-NoLogo','-NoProfile','-File',str(shim),str(game),*arguments],env=environment,capture_output=True,text=True,timeout=20)
        assert child.returncode==0,child.stderr
    logs=sorted((root/'private logs').glob('*.jsonl'))
    assert len(logs)==2
    for log in logs:
        recorded=json.loads(log.read_text(encoding='utf-8'))
        assert recorded['arguments']==['--no-debugger','--observe-seconds','120',str(game),str(log),*arguments],recorded
        assert recorded['environment']=={name:environment[name] for name in ('SteamAppId','SteamGameId','SteamOverlayGameId')}
    before=launch_field(original).with_value('sentinel')
    assert before==launch_field(config.read_bytes()).with_value('sentinel')
    assert diag.remove()['status']=='restored'
    assert config.read_bytes()==original
    cases=['output-junction-refusal-before-write','explicit120-prefix-argv-environment-unique-output','absent-field-roundtrip']
    def refused(call):
        before_config=config.read_bytes()
        try: call()
        except PatchError: pass
        else: raise AssertionError('Expected diagnostic refusal')
        assert config.read_bytes()==before_config
    for duration in (0,30,119,121,120.5,True,'120'):
        rejected=dict(profile,deadlineSeconds=duration)
        refused(lambda p=rejected:setup.DiagnosticSetup(manager,profile=p,tools_root=root/'private tools'))
    cases.append('non120-profile-refusal')
    for input_file in (game,control,helper,license):
        saved=input_file.read_bytes()
        input_file.write_bytes(saved+b'corrupt')
        refused(lambda:diag.enable(build,game,root/'private logs',args.pwsh))
        input_file.write_bytes(saved)
        cases.append('hash-refusal-'+input_file.name)
    cached_helper=shim.parent/'Bo3EnhancedHelper.dll'
    saved=cached_helper.read_bytes()
    cached_helper.write_bytes(b'changed private cache')
    refused(lambda:diag.enable(build,game,root/'private logs',args.pwsh))
    cached_helper.write_bytes(saved)
    cases.append('cache-conflict')
    for protected in (steam,game.parent,ROOT):
        refused(lambda p=protected:diag.enable(build,game,p/'diagnostic-output',args.pwsh))
    cases.append('protected-log-roots')
    # Plain arguments, including an explicitly empty field, restore exact bytes.
    for options in ('','-windowed "plain value"'):
        source=launch_field(original).with_value(options)
        config.write_bytes(source)
        diag.enable(build,game,root/'private logs',args.pwsh)
        installed=launch_field(config.read_bytes()).value
        assert installed.endswith(' '+options) if options else installed.endswith('%command%')
        assert diag.remove()['status']=='restored'
        assert config.read_bytes()==source
    config.write_bytes(original)
    cases.append('empty-and-plain-options-roundtrip')
    for running in ('steam.exe','BlackOps3.exe','BO3-Enhanced-Zombies.exe','BO3-Startup-Control.exe'):
        guarded=setup.DiagnosticSetup(SteamPlay(steam,active_user=42,state=root/'receipt',process_running=lambda name,r=running:name==r),profile=profile,tools_root=root/'private tools')
        try: guarded.enable(build,game,root/'private logs',args.pwsh)
        except PatchError: pass
        else: raise AssertionError('Running process admitted: '+running)
        assert config.read_bytes()==original
        cases.append('running-refusal-'+running)
    diag.enable(build,game,root/'private logs',args.pwsh)
    refused(lambda:diag.enable(build,game,root/'private logs',args.pwsh))
    cases.append('existing-receipt-refusal')
    config.write_bytes(launch_field(config.read_bytes()).with_value('foreign %command%'))
    try: diag.remove()
    except PatchError: pass
    else: raise AssertionError('Foreign launch options admitted')
    config.write_bytes(original)
    cases.append('external-field-conflict')
    report={'passed':True,'scope':'Owned config and inert native recorder only','nativeTargetSha256':sha(args.target),
            'cases':cases,
            'shimSha256':sha(shim),'logs':[{'name':p.name,'sha256':sha(p)} for p in logs],
            'sourceSha256':{p.name:sha(p) for p in (ROOT/'source/launch/enhanced/SteamDiagnostic.py',ROOT/'source/launch/enhanced/SteamDiagnosticShim.ps1',Path(__file__))},
            'gameExecuted':False,'normalSteamConfigEdited':False,'stockCapacityDiagnostic':True}
    report['deadlineSeconds']=120
    (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
