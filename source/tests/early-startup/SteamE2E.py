"""Focused owned admission and Steam transaction checks for the fixed early checksum launcher."""
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
from launch.late_startup import SteamSetup as shared
from launch.early_startup import SteamSetup as job


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--target',type=Path,required=True)
    args=parser.parse_args()
    root=private_path(args.output,installations=(ROOT,))
    root.mkdir(parents=True,exist_ok=False)
    public=job.recipe()
    assert public['status']=='experimental' and public['startupMethod']=='late-crt-job-freeze-early-checksum'
    assert public['scope']=='Experimental early checksum startup. Game startup, AAE loading and friends require manual validation.'
    assert public['requiredRuntimeMetadataMask']==3
    assert public['serverUsableSlots']==500000 and public['clientRoots']==18 and public['migrationBufferBytes']==33554432
    assert public['serverTotal']==500001 and public['clientTotal']==65000 and public['requiresSolePrimary'] is True
    assert public['gateDeadlineMs']==30000 and public['successfulGameLifetime']=='until-exit'
    assert 'diagnosticDeadlineMs' not in public and set(public['files'])==set(job.FILES)
    assert job.fixed_recipe().tools_name=='500k-zombies' and job.fixed_recipe().receipt_key=='earlyChecksumRecipeSha256'
    assert b'\r' not in job.RECIPE_PATH.read_bytes() and b'\r' not in Path(job.__file__).read_bytes()
    public_sha=job.RECIPE_SHA256
    steam=root/'Steam fixture'
    config=steam/'userdata/42/config/localconfig.vdf'
    config.parent.mkdir(parents=True)
    original=b'"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { "311210" { "Other" "keep" } } } } } }\r\n'
    config.write_bytes(original)
    game=root/'owned game/BlackOps3.exe'
    game.parent.mkdir()
    game.write_bytes(b'inert game: never execute')
    build=root/'owned build'
    build.mkdir()
    payload=dict(zip(job.FILES,(args.target.read_bytes(),b'inert helper',b'inert gate',b'owned license')))
    for name,data in payload.items():(build/name).write_bytes(data)
    fixture={**public,'gameSha256':sha(game.read_bytes()),'files':{name:sha(data) for name,data in payload.items()}}
    profile=root/'OwnedJobProfile.json'
    raw=(json.dumps(fixture,indent=2)+'\n').encode()
    profile.write_bytes(raw)
    job.RECIPE_PATH=profile
    job.RECIPE_SHA256=sha(raw)
    manager=SteamPlay(steam,active_user=42,state=root/'receipt',process_running=lambda name:False)
    transport=job.EarlySteam(manager,tools_root=root/'private tools')

    def refused(call):
        before=config.read_bytes()
        try:call()
        except PatchError:pass
        else:raise AssertionError('Expected refusal')
        assert config.read_bytes()==before

    profile.write_bytes(raw+b' ')
    refused(lambda:job.EarlySteam(manager,tools_root=root/'private tools'))
    bad_raw=(json.dumps({**fixture,'sharedSetupSha256':'0'*64})+'\n').encode()
    profile.write_bytes(bad_raw)
    job.RECIPE_SHA256=sha(bad_raw)
    refused(lambda:job.EarlySteam(manager,tools_root=root/'private tools'))
    profile.write_bytes(raw)
    job.RECIPE_SHA256=sha(raw)
    for name,data in payload.items():
        (build/name).write_bytes(data+b'changed')
        refused(lambda:transport.enable(build,game))
        (build/name).write_bytes(data)
    game.write_bytes(b'changed game')
    refused(lambda:transport.enable(build,game))
    game.write_bytes(b'inert game: never execute')
    cli=subprocess.run([sys.executable,'-B',str(ROOT/'source/launch/early_startup/SteamSetup.py'),'setup','--profile','other.json','--server-slots','7','--diagnostic-deadline','120'],capture_output=True,text=True)
    assert cli.returncode==2 and 'unrecognized arguments' in cli.stderr

    result=transport.enable(build,game)
    launcher=Path(result['launcher'])
    assert launch_field(config.read_bytes()).value=='"'+str(launcher)+'" %command%'
    assert 'EXPERIMENTAL: 500,000 intended server script slots.' in result['notice']
    assert 'Game startup, AAE loading and friends require manual validation.' in result['notice']
    assert '120' not in result['notice'] and {p.name for p in launcher.parent.iterdir()}==set(job.FILES)
    receipt=json.loads((manager.state/'receipt.json').read_text())
    assert receipt['original']=={'present':False,'value':None,'raw':None}
    assert receipt['earlyChecksumRecipeSha256']==job.RECIPE_SHA256
    assert not any(name in receipt for name in ('lateStartupRecipeSha256','lateControlRecipeSha256','latePassiveControlRecipeSha256'))
    log=root/'owned-argv.json'
    arguments=['space value','é漢字','','embedded "quote"','trailing \\','--server-slots','7']
    environment=dict(os.environ,OWNED_STEAM_OUTPUT=str(log),SteamAppId='owned app',SteamGameId='owned game',SteamOverlayGameId='owned overlay')
    child=subprocess.run([str(launcher),str(game),*arguments],env=environment,capture_output=True,text=True,timeout=20)
    assert child.returncode==0,child.stderr
    actual=json.loads(log.read_text(encoding='utf-8'))
    assert actual['arguments']==[str(game),*arguments]
    assert actual['environment']=={name:environment[name] for name in ('SteamAppId','SteamGameId','SteamOverlayGameId')}

    refused(lambda:transport.enable(build,game))
    owned=config.read_bytes()
    config.write_bytes(launch_field(owned).with_value('-external-change'))
    refused(transport.remove)
    assert json.loads((manager.state/'receipt.json').read_text())['phase']=='enabled'
    config.write_bytes(owned)
    transport.remove()
    assert config.read_bytes()==original
    # The old route uses the same canonical receipt and must restore before job setup.
    old_files={**fixture['files'],'BO3-Late-Passive-Control.exe':fixture['files'][job.FILES[0]]}
    del old_files[job.FILES[0]]
    old_profile=root/'OwnedPreviousProfile.json'
    old_raw=(json.dumps({**fixture,'files':old_files})+'\n').encode()
    old_profile.write_bytes(old_raw)
    old_fixed=shared.FixedSteamRecipe(old_profile,sha(old_raw),('BO3-Late-Passive-Control.exe',*job.FILES[1:]),'old-route','latePassiveControlRecipeSha256','owned previous route')
    (build/'BO3-Late-Passive-Control.exe').write_bytes(payload[job.FILES[0]])
    previous=shared.LateSteam(manager,tools_root=root/'old tools',fixed=old_fixed)
    previous.enable(build,game)
    refused(lambda:transport.enable(build,game))
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
    cached.unlink()
    refused(lambda:transport.enable(build,game))
    cached.write_bytes(payload[cached.name])
    config.write_bytes(launch_field(original).with_value('"other wrapper" %command%'))
    refused(lambda:transport.enable(build,game))
    config.write_bytes(original)
    for running in ('steam.exe','BlackOps3.exe',*job.CONTROLLERS):
        blocked=job.EarlySteam(SteamPlay(steam,active_user=42,state=root/'receipt',process_running=lambda name,r=running:name==r),tools_root=root/'private tools')
        refused(lambda:blocked.enable(build,game))
        refused(blocked.remove)
    checks=0
    def closes_late(name):
        nonlocal checks
        if name=='steam.exe':checks+=1
        return name=='steam.exe' and checks>1
    late=job.EarlySteam(SteamPlay(steam,active_user=42,state=root/'receipt',process_running=closes_late),tools_root=root/'private tools')
    refused(lambda:late.enable(build,game))
    assert json.loads((manager.state/'receipt.json').read_text())['phase']=='pending'
    transport.remove()
    assert config.read_bytes()==original
    report={'passed':True,'groups':['fixed-early-checksum-recipe-and-payload-admission','direct-native-argv-environment-and-lifetime-notice',
        'canonical-receipt-and-original-restoration','cache-and-wrapper-ownership-refusals','controller-admission-before-child-and-final-recheck'],
        'gameExecuted':False,'normalSteamConfigEdited':False,'controllers':job.CONTROLLERS,'ownedLauncherSha256':sha(args.target.read_bytes()),
        'argvSha256':sha(log.read_bytes()),'sourceSha256':sha(Path(job.__file__).read_bytes()),'testSha256':sha(Path(__file__).read_bytes()),
        'publicRecipeSha256':public_sha,'sharedSetupSha256':public['sharedSetupSha256'],'sharedSources':public['sharedSources']}
    (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
