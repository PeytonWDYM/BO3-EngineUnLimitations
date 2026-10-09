"""Test the fixed transport with an owned recipe and inert argv recorder."""
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
from patcher.errors import PatchError
from patcher.paths import private_path
from patcher.steam_launch import SteamPlay
from patcher.vdf_span import launch_field

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--target',type=Path,required=True)
    parser.add_argument('--pwsh',type=Path,required=True)
    args=parser.parse_args()
    output=private_path(args.output,installations=(ROOT,))
    output.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('SteamProbe',ROOT/'source/launch/enhanced/SteamProbe.py')
    probe=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    admitted=probe.recipe()
    assert admitted['capacity']=='stock' and admitted['deadlineSeconds']==120
    assert admitted['gameSha256']=='0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0'
    public_recipe_sha=probe.RECIPE_SHA256
    steam=output/'Steam fixture'
    config=steam/'userdata/42/config/localconfig.vdf'
    config.parent.mkdir(parents=True)
    original=b'"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { "311210" { "Unrelated" "keep" } } } } } }\n'
    config.write_bytes(original)
    game=output/'owned game'/ 'BlackOps3.exe'
    game.parent.mkdir()
    game.write_bytes(b'Inert game: never execute')
    build=output/'owned native build'
    build.mkdir()
    payload={'BO3-Startup-Control.exe':args.target.read_bytes(),'Bo3EnhancedHelper.dll':b'owned inert probe helper','Detours-LICENSE.md':b'owned license'}
    for name,data in payload.items(): (build/name).write_bytes(data)
    shared={name:sha((ROOT/'source/launch/enhanced'/name).read_bytes()) for name in ('SteamDiagnostic.py','SteamDiagnosticShim.ps1')}
    recipe={'schemaVersion':1,'purpose':'startup-info-observation','nativeBuildReceiptSha256':'1'*64,'nativeReviewReceiptSha256':'2'*64,
            'sharedSources':shared,'profile':{'schemaVersion':1,'mode':'--no-debugger','capacity':'stock','deadlineSeconds':120,
            'gameSha256':sha(game.read_bytes()),'files':{name:sha(data) for name,data in payload.items()}}}
    # Only this isolated module's fixed recipe is replaced with owned identities.
    recipe_path=output/'SteamProbeProfile.json'
    recipe_bytes=(json.dumps(recipe,indent=2)+'\n').encode()
    recipe_path.write_bytes(recipe_bytes)
    probe.RECIPE_PATH=recipe_path
    probe.RECIPE_SHA256=sha(recipe_bytes)
    manager=SteamPlay(steam,active_user=42,state=output/'receipt',process_running=lambda name:False)
    transport=probe.SteamProbe(manager,tools_root=output/'private tools')
    def refused(call):
        before=config.read_bytes()
        try: call()
        except PatchError: pass
        else: raise AssertionError('Expected refusal')
        assert config.read_bytes()==before
    recipe_path.write_bytes(recipe_bytes+b' ')
    refused(lambda:probe.SteamProbe(manager,tools_root=output/'private tools'))
    recipe_path.write_bytes(recipe_bytes)
    changed=dict(recipe,sharedSources=dict(shared,**{'SteamDiagnosticShim.ps1':'3'*64}))
    altered=(json.dumps(changed,indent=2)+'\n').encode()
    recipe_path.write_bytes(altered); probe.RECIPE_SHA256=sha(altered)
    refused(lambda:probe.SteamProbe(manager,tools_root=output/'private tools'))
    recipe_path.write_bytes(recipe_bytes); probe.RECIPE_SHA256=sha(recipe_bytes)
    for name in payload:
        path=build/name
        path.write_bytes(payload[name]+b'changed')
        refused(lambda:transport.enable(build,game,output/'private logs',args.pwsh))
        path.write_bytes(payload[name])
    result=transport.enable(build,game,output/'private logs',args.pwsh)
    arguments=['space value','é漢字','','embedded "quote"','trailing \\','--observe-seconds','30']
    environment=dict(os.environ,SteamAppId='owned app',SteamGameId='owned game',SteamOverlayGameId='owned overlay')
    child=subprocess.run([str(args.pwsh),'-NoLogo','-NoProfile','-File',result['shim'],str(game),*arguments],env=environment,capture_output=True,text=True,timeout=20)
    assert child.returncode==0,child.stderr
    log,=list((output/'private logs').glob('*.jsonl'))
    actual=json.loads(log.read_text(encoding='utf-8'))
    expected=['--no-debugger','--observe-seconds','120',str(game),str(log),*arguments]
    assert actual['arguments']==expected,(actual['arguments'],expected)
    assert actual['environment']=={name:environment[name] for name in ('SteamAppId','SteamGameId','SteamOverlayGameId')}
    assert launch_field(config.read_bytes()).with_value('same')==launch_field(original).with_value('same')
    refused(lambda:transport.enable(build,game,output/'private logs',args.pwsh))
    assert transport.remove()['status']=='restored'
    assert config.read_bytes()==original
    for running in ('steam.exe','BlackOps3.exe','BO3-Enhanced-Zombies.exe','BO3-Startup-Control.exe'):
        blocked=probe.SteamProbe(SteamPlay(steam,active_user=42,state=output/'receipt',process_running=lambda name,r=running:name==r),tools_root=output/'private tools')
        refused(lambda:blocked.enable(build,game,output/'private logs',args.pwsh))
        refused(blocked.remove)
    junction=output/'redirected private tools'
    linked=subprocess.run(['cmd','/c','mklink','/J',str(junction),str(game.parent)],capture_output=True,text=True)
    assert linked.returncode==0,linked.stderr
    redirected=probe.SteamProbe(manager,tools_root=junction)
    refused(lambda:redirected.enable(build,game,output/'private logs',args.pwsh))
    assert set(path.name for path in game.parent.iterdir())=={'BlackOps3.exe'}
    report={'passed':True,'groups':['public-recipe-admission','fixed-recipe-admission','shared-source-admission','three-payload-hashes','literal-argv-and-environment',
        'canonical-field-restoration','earlier-wrapper-refusal','four-running-processes-setup-and-remove','redirect-before-write'],
        'gameExecuted':False,'normalSteamConfigEdited':False,'logSha256':sha(log.read_bytes()),
        'sourceSha256':sha((ROOT/'source/launch/enhanced/SteamProbe.py').read_bytes()),'testSha256':sha(Path(__file__).read_bytes()),
        'sharedSources':shared,'publicRecipeSha256':public_recipe_sha,'ownedTargetSha256':sha(args.target.read_bytes())}
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
