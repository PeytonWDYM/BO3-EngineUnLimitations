"""Focused fixed stock-control admission and canonical Steam transaction proof."""
import argparse
import hashlib
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
from launch.job_control import SteamSetup as control


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--target',type=Path,required=True)
    args=parser.parse_args()
    root=private_path(args.output,installations=(ROOT,))
    root.mkdir(parents=True,exist_ok=False)
    public=control.recipe()
    assert public['status']=='experimental' and public['startupMethod']=='late-crt-job-freeze-control'
    assert public['serverTotal']==130000 and public['serverUsableSlots']==129999
    assert public['clientTotal']==65000 and public['clientRoots']==8 and public['migrationPolicy']=='stock'
    assert public['committed'] is False and public['editsWritten']==0 and public['relay']==0 and public['relayAllocations']==0
    assert public['expandedPoolEnrollment'] is False and public['liveAllocationValidated'] is False
    assert public['requiredRuntimeMetadataMask']==3 and public['requiresSolePrimary'] is True
    assert public['gateDeadlineMs']==30000 and public['successfulGameLifetime']=='until-exit'
    assert public['scope']=='Exact-host bounded stock diagnostic. Game loading, AAE and friends remain unvalidated.'
    assert 'diagnosticDeadlineMs' not in public and set(public['files'])==set(control.FILES)
    assert control.fixed_recipe().tools_name=='job-control' and control.fixed_recipe().receipt_key=='jobControlRecipeSha256'
    assert b'\r' not in control.RECIPE_PATH.read_bytes() and b'\r' not in Path(control.__file__).read_bytes()
    public_sha=control.RECIPE_SHA256
    config=root/'Steam fixture/userdata/42/config/localconfig.vdf'
    config.parent.mkdir(parents=True)
    steam=config.parents[3]
    original=b'"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { "311210" { "Other" "keep" } } } } } }\r\n'
    config.write_bytes(original)
    game=root/'owned game/BlackOps3.exe'
    game.parent.mkdir()
    game.write_bytes(b'inert game: never execute')
    build=root/'owned build'
    build.mkdir()
    payload=dict(zip(control.FILES,(args.target.read_bytes(),b'inert helper',b'inert gate',b'owned license')))
    for name,data in payload.items():(build/name).write_bytes(data)
    fixture={**public,'gameSha256':sha(game.read_bytes()),'files':{name:sha(data) for name,data in payload.items()}}
    profile=root/'OwnedControlProfile.json'
    raw=(json.dumps(fixture,indent=2)+'\n').encode()
    profile.write_bytes(raw)
    control.RECIPE_PATH=profile
    control.RECIPE_SHA256=sha(raw)
    manager=SteamPlay(steam,active_user=42,state=root/'receipt',process_running=lambda name:False)
    transport=control.ControlSteam(manager,tools_root=root/'private tools')

    def refused(call):
        before=config.read_bytes()
        try:call()
        except PatchError:pass
        else:raise AssertionError('Expected refusal')
        assert config.read_bytes()==before

    profile.write_bytes(raw+b' ')
    refused(lambda:control.ControlSteam(manager,tools_root=root/'private tools'))
    profile.write_bytes(raw)
    for name,data in payload.items():
        (build/name).write_bytes(data+b'changed')
        refused(lambda:transport.enable(build,game))
        (build/name).write_bytes(data)
    game.write_bytes(b'changed game')
    refused(lambda:transport.enable(build,game))
    game.write_bytes(b'inert game: never execute')
    cli=subprocess.run([sys.executable,'-B',str(ROOT/'source/launch/job_control/SteamSetup.py'),'setup','--profile','other.json','--server-slots','7','--diagnostic-deadline','120'],capture_output=True,text=True)
    assert cli.returncode==2 and 'unrecognized arguments' in cli.stderr
    result=transport.enable(build,game)
    launcher=Path(result['launcher'])
    assert launch_field(config.read_bytes()).value=='"'+str(launcher)+'" %command%'
    assert 'stock capacity' in result['notice'] and 'zero native edits' in result['notice'] and 'no expanded-pool enrollment' in result['notice']
    assert '500,000' not in result['notice'] and '120' not in result['notice']
    assert {p.name for p in launcher.parent.iterdir()}==set(control.FILES)
    receipt=json.loads((manager.state/'receipt.json').read_text())
    assert receipt['original']=={'present':False,'value':None,'raw':None}
    assert receipt['jobControlRecipeSha256']==control.RECIPE_SHA256
    log=root/'owned-argv.json'
    arguments=['space value','é漢字','','embedded "quote"','trailing \\']
    environment=dict(os.environ,OWNED_STEAM_OUTPUT=str(log),SteamAppId='owned app',SteamGameId='owned game',SteamOverlayGameId='owned overlay')
    child=subprocess.run([str(launcher),str(game),*arguments],env=environment,capture_output=True,text=True,timeout=20)
    assert child.returncode==0,child.stderr
    actual=json.loads(log.read_text(encoding='utf-8'))
    assert actual['arguments']==[str(game),*arguments]
    assert actual['environment']=={name:environment[name] for name in ('SteamAppId','SteamGameId','SteamOverlayGameId')}
    refused(lambda:transport.enable(build,game))
    installed=config.read_bytes()
    config.write_bytes(launch_field(installed).with_value('-external-change'))
    refused(transport.remove)
    assert json.loads((manager.state/'receipt.json').read_text())['phase']=='enabled'
    config.write_bytes(installed)
    transport.remove()
    assert config.read_bytes()==original
    for value in ('','-windowed "plain argument"'):
        baseline=launch_field(original).with_value(value)
        config.write_bytes(baseline)
        transport.enable(build,game)
        if value:assert launch_field(config.read_bytes()).value.endswith(' '+value)
        config.write_bytes(config.read_bytes().replace(b'"keep"',b'"later"'))
        transport.remove()
        assert config.read_bytes()==baseline.replace(b'"keep"',b'"later"')
    config.write_bytes(original)
    cached=launcher.parent/'Bo3StartupGate.dll'
    cached.write_bytes(b'changed cache')
    refused(lambda:transport.enable(build,game))
    cached.write_bytes(payload[cached.name])
    config.write_bytes(launch_field(original).with_value('"other wrapper" %command%'))
    refused(lambda:transport.enable(build,game))
    config.write_bytes(original)
    assert {'BO3-Job-Zombies.exe','BO3-Job-Control.exe'}<=set(control.CONTROLLERS)
    for running in ('steam.exe','BlackOps3.exe',*control.CONTROLLERS):
        blocked=control.ControlSteam(SteamPlay(steam,active_user=42,state=root/'receipt',process_running=lambda name,r=running:name==r),tools_root=root/'private tools')
        refused(lambda:blocked.enable(build,game))
        refused(blocked.remove)
    checks=0
    def closes_late(name):
        nonlocal checks
        if name=='steam.exe':checks+=1
        return name=='steam.exe' and checks>1
    late=control.ControlSteam(SteamPlay(steam,active_user=42,state=root/'receipt',process_running=closes_late),tools_root=root/'private tools')
    refused(lambda:late.enable(build,game))
    assert json.loads((manager.state/'receipt.json').read_text())['phase']=='pending'
    transport.remove()
    assert config.read_bytes()==original
    report={'passed':True,'groups':['fixed-stock-recipe-and-payload-refusals','native-argv-context-and-stock-notice',
        'canonical-field-restoration-and-cache-ownership','both-job-parents-and-final-process-refusal'],
        'gameExecuted':False,'normalSteamConfigEdited':False,'controllers':control.CONTROLLERS,'ownedLauncherSha256':sha(args.target.read_bytes()),
        'argvSha256':sha(log.read_bytes()),'sourceSha256':sha(Path(control.__file__).read_bytes()),'testSha256':sha(Path(__file__).read_bytes()),
        'publicRecipeSha256':public_sha,'sharedSetupSha256':public['sharedSetupSha256'],'sharedSources':public['sharedSources']}
    (root/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
