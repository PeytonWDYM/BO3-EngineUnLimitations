"""Owned stock-control Steam transactions with an inert direct argv recorder."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'source'))
sys.path.insert(0,str(ROOT/'source/launch/late_startup'))
from patcher.coordination import StateLock
from patcher.errors import PatchError
from patcher.paths import private_path
from patcher.steam_launch import SteamPlay
from patcher.vdf_span import launch_field
import SteamSetup as setup
import SteamControl as control


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--target',type=Path,required=True)
    args=parser.parse_args()
    root=private_path(args.output,installations=(ROOT,))
    root.mkdir(parents=True,exist_ok=False)
    public=control.recipe()
    assert public['startupMethod']=='late-crt-control' and public['status']=='diagnostic'
    assert public['serverUsableSlots']==129999 and public['expandedPoolEnrollment'] is False
    assert public['vmMigrationEdits']==0 and public['debugRegisterWrites']==0
    assert public['gateDeadlineMs']==30000 and public['diagnosticDeadlineMs']==120000
    assert public['successfulGameLifetime']=='owned-120-second-observation'
    assert set(public['files'])==set(control.FILES)
    production=setup.recipe()
    assert production['serverUsableSlots']==500000 and production['successfulGameLifetime']=='until-exit'
    public_sha=control.RECIPE_SHA256
    steam=root/'Steam fixture'
    config=steam/'userdata/42/config/localconfig.vdf'
    config.parent.mkdir(parents=True)
    original=b'"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { "311210" { "Unrelated" "keep" } } } } } }\r\n'
    config.write_bytes(original)
    game=root/'owned game/BlackOps3.exe'
    game.parent.mkdir()
    game.write_bytes(b'inert game: never execute')
    build=root/'owned build'
    build.mkdir()
    payload=dict(zip(control.FILES,(args.target.read_bytes(),b'inert VM helper',b'inert gate',b'owned license')))
    for name,data in payload.items():(build/name).write_bytes(data)
    fixture={**public,'gameSha256':sha(game.read_bytes()),'files':{name:sha(data) for name,data in payload.items()}}
    recipe_path=root/'SteamControlProfile.json'
    raw=(json.dumps(fixture,indent=2)+'\n').encode()
    recipe_path.write_bytes(raw)
    control.RECIPE_PATH=recipe_path
    control.RECIPE_SHA256=sha(raw)
    manager=SteamPlay(steam,active_user=42,state=root/'receipt',process_running=lambda name:False)
    transport=control.StockLateSteam(manager,tools_root=root/'private tools')

    def refused(call):
        before=config.read_bytes()
        try:call()
        except PatchError:pass
        else:raise AssertionError('Expected refusal')
        assert config.read_bytes()==before

    recipe_path.write_bytes(raw+b' ')
    refused(lambda:control.StockLateSteam(manager,tools_root=root/'private tools'))
    recipe_path.write_bytes(raw)
    bad_shared={**fixture,'sharedSources':{**fixture['sharedSources'],'steam_launch.py':'0'*64}}
    bad_raw=(json.dumps(bad_shared)+'\n').encode()
    recipe_path.write_bytes(bad_raw)
    control.RECIPE_SHA256=sha(bad_raw)
    refused(lambda:control.StockLateSteam(manager,tools_root=root/'private tools'))
    bad_setup=(json.dumps({**fixture,'sharedSetupSha256':'0'*64})+'\n').encode()
    recipe_path.write_bytes(bad_setup)
    control.RECIPE_SHA256=sha(bad_setup)
    refused(lambda:control.StockLateSteam(manager,tools_root=root/'private tools'))
    recipe_path.write_bytes(raw)
    control.RECIPE_SHA256=sha(raw)
    for name,data in payload.items():
        (build/name).write_bytes(data+b'changed')
        refused(lambda:transport.enable(build,game))
        (build/name).write_bytes(data)
    game.write_bytes(b'changed game')
    refused(lambda:transport.enable(build,game))
    game.write_bytes(b'inert game: never execute')
    result=transport.enable(build,game)
    launcher=Path(result['launcher'])
    assert result['status']=='enabled' and 'stock' in result['notice'].lower()
    assert '500,000' not in result['notice'] and '129,999' in result['notice']
    assert launch_field(config.read_bytes()).value=='"'+str(launcher)+'" %command%'
    assert {p.name for p in launcher.parent.iterdir()}==set(payload)
    receipt=json.loads((manager.state/'receipt.json').read_text())
    assert receipt['lateControlRecipeSha256']==control.RECIPE_SHA256
    assert 'lateStartupRecipeSha256' not in receipt
    arguments=['space value','é漢字','','embedded "quote"','trailing \\','--server-slots','7']
    log=root/'owned-argv.json'
    environment=dict(os.environ,OWNED_STEAM_OUTPUT=str(log),SteamAppId='owned app',SteamGameId='owned game',SteamOverlayGameId='owned overlay')
    child=subprocess.run([str(launcher),str(game),*arguments],env=environment,capture_output=True,text=True,timeout=20)
    assert child.returncode==0,child.stderr
    actual=json.loads(log.read_text(encoding='utf-8'))
    assert actual['arguments']==[str(game),*arguments]
    assert actual['environment']=={name:environment[name] for name in ('SteamAppId','SteamGameId','SteamOverlayGameId')}
    refused(lambda:transport.enable(build,game))
    # Both routes use the same receipt and cannot replace each other.
    owned_production={**fixture,'files':{**fixture['files'],'BO3-Late-Zombies.exe':fixture['files']['BO3-Late-Control.exe']}}
    del owned_production['files']['BO3-Late-Control.exe']
    production_path=root/'OwnedProductionProfile.json'
    production_raw=(json.dumps(owned_production)+'\n').encode()
    production_path.write_bytes(production_raw)
    owned_fixed=setup.FixedSteamRecipe(production_path,sha(production_raw),setup.FILES,'late-zombies','lateStartupRecipeSha256',setup.production_recipe().notice)
    production_transport=setup.LateSteam(manager,tools_root=root/'production tools',fixed=owned_fixed)
    refused(lambda:production_transport.enable(build,game))
    assert transport.remove()['status']=='restored' and config.read_bytes()==original
    assert transport.remove()['status']=='already-restored'
    (build/'BO3-Late-Zombies.exe').write_bytes(payload['BO3-Late-Control.exe'])
    production_transport.enable(build,game)
    assert 'lateStartupRecipeSha256' in json.loads((manager.state/'receipt.json').read_text())
    refused(lambda:transport.enable(build,game))
    assert transport.remove()['status']=='restored' and config.read_bytes()==original
    for value in ('','-windowed "plain value"'):
        source=launch_field(original).with_value(value)
        config.write_bytes(source)
        transport.enable(build,game)
        assert launch_field(config.read_bytes()).value.endswith(' '+value) if value else True
        config.write_bytes(config.read_bytes().replace(b'"keep"',b'"later"'))
        transport.remove()
        assert config.read_bytes()==source.replace(b'"keep"',b'"later"')
    config.write_bytes(original)
    transport.enable(build,game)
    owned=config.read_bytes()
    config.write_bytes(launch_field(owned).with_value('-changed externally'))
    refused(transport.remove)
    assert json.loads((manager.state/'receipt.json').read_text())['phase']=='enabled'
    config.write_bytes(owned)
    transport.remove()
    for name,data in payload.items():
        cached=launcher.parent/name
        cached.write_bytes(b'changed cache')
        refused(lambda:transport.enable(build,game))
        cached.write_bytes(data)
    extra=launcher.parent/'extra'
    extra.write_bytes(b'unexpected cache file')
    refused(lambda:transport.enable(build,game))
    extra.unlink()
    missing=launcher.parent/'Bo3StartupGate.dll'
    missing.unlink()
    refused(lambda:transport.enable(build,game))
    missing.write_bytes(payload[missing.name])
    processes=('steam.exe','BlackOps3.exe','BO3-Enhanced-Zombies.exe','BO3-Late-Zombies.exe','BO3-Startup-Control.exe','BO3-Late-Control.exe')
    for running in processes:
        blocked=control.StockLateSteam(SteamPlay(steam,active_user=42,state=root/'receipt',process_running=lambda name,r=running:name==r),tools_root=root/'private tools')
        refused(lambda:blocked.enable(build,game))
        refused(blocked.remove)
    with StateLock(manager.state):refused(lambda:transport.enable(build,game))
    with StateLock(root/'private tools'):refused(lambda:transport.enable(build,game))
    alias=root/'Steam alias'
    linked=subprocess.run(['cmd','/c','mklink','/J',str(alias),str(steam)],capture_output=True,text=True)
    assert linked.returncode==0,linked.stderr
    other=control.StockLateSteam(SteamPlay(alias,active_user=42,state=root/'receipt',process_running=lambda name:False),tools_root=root/'private tools')
    assert other.manager.config==manager.config
    with StateLock(manager.state):refused(lambda:other.enable(build,game))
    redirect=root/'redirected tools'
    linked=subprocess.run(['cmd','/c','mklink','/J',str(redirect),str(game.parent)],capture_output=True,text=True)
    assert linked.returncode==0,linked.stderr
    refused(lambda:control.StockLateSteam(manager,tools_root=redirect).enable(build,game))
    state_redirect=root/'redirected state'
    linked=subprocess.run(['cmd','/c','mklink','/J',str(state_redirect),str(game.parent)],capture_output=True,text=True)
    assert linked.returncode==0,linked.stderr
    refused(lambda:SteamPlay(steam,active_user=42,state=state_redirect,process_running=lambda name:False))
    cache_tools=root/'redirected cache tools'
    cache_tools.mkdir()
    linked=subprocess.run(['cmd','/c','mklink','/J',str(cache_tools/launcher.parent.name),str(game.parent)],capture_output=True,text=True)
    assert linked.returncode==0,linked.stderr
    refused(lambda:control.StockLateSteam(manager,tools_root=cache_tools).enable(build,game))
    assert {p.name for p in game.parent.iterdir()}=={'BlackOps3.exe'}
    # Stop after the pending receipt exists, then recover through the normal remove path.
    checks=0
    def closes_late(name):
        nonlocal checks
        if name=='steam.exe':checks+=1
        return name=='steam.exe' and checks>1
    late=control.StockLateSteam(SteamPlay(steam,active_user=42,state=root/'receipt',process_running=closes_late),tools_root=root/'private tools')
    refused(lambda:late.enable(build,game))
    assert json.loads((manager.state/'receipt.json').read_text())['phase']=='pending'
    transport.remove()
    assert config.read_bytes()==original
    cli=subprocess.run([sys.executable,'-B',str(ROOT/'source/launch/late_startup/SteamControl.py'),'setup','--server-slots','500000'],capture_output=True,text=True)
    assert cli.returncode==2 and 'unrecognized arguments' in cli.stderr
    report={'passed':True,'groups':['fixed-public-stock-schema','production-default-recipe','recipe-and-shared-source-refusal','four-payload-and-game-hashes',
        'direct-argv-and-inherited-Steam-IDs','canonical-shared-receipt','absent-empty-raw-restoration','later-unrelated-byte-preservation','external-field-ownership',
        'changed-missing-extra-cache-refusal','six-running-processes-setup-remove','canonical-state-and-cache-locks','Steam-alias-lock','redirect-before-write',
        'final-process-recheck-and-pending-recovery','no-runtime-capacity-override'],
        'gameExecuted':False,'normalSteamConfigEdited':False,'ownedLauncherSha256':sha(args.target.read_bytes()),'argvSha256':sha(log.read_bytes()),
        'controlSourceSha256':sha((ROOT/'source/launch/late_startup/SteamControl.py').read_bytes()),
        'sharedSetupSha256':sha((ROOT/'source/launch/late_startup/SteamSetup.py').read_bytes()),'testSha256':sha(Path(__file__).read_bytes()),
        'publicRecipeSha256':public_sha,'sharedSources':public['sharedSources']}
    (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
