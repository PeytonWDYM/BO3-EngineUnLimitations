"""Four owned groups for the fixed passive Steam recipe and shared transactions."""
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
from patcher.errors import PatchError
from patcher.paths import private_path
from patcher.steam_launch import SteamPlay
from patcher.vdf_span import launch_field
import SteamSetup as setup
import SteamPassiveControl as passive


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--target',type=Path,required=True)
    args=parser.parse_args()
    root=private_path(args.output,installations=(ROOT,))
    root.mkdir(parents=True,exist_ok=False)
    public=passive.recipe()
    assert public['status']=='diagnostic' and public['startupMethod']=='late-crt-passive-control'
    assert public['serverUsableSlots']==129999 and public['expandedPoolEnrollment'] is False
    assert public['debuggerAttachment'] is False and public['debugRegisterWrites']==0
    assert public['readsSequential'] is True and public['allThreadsStopped'] is False
    assert public['vmMigrationEdits']==0 and public['relayAllocations']==0
    assert public['gateDeadlineMs']==30000 and public['diagnosticDeadlineMs']==120000
    assert public['successfulGameLifetime']=='owned-120-second-observation'
    assert set(public['files'])==set(passive.FILES)
    public_sha=passive.RECIPE_SHA256
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
    payload=dict(zip(passive.FILES,(args.target.read_bytes(),b'inert helper',b'inert gate',b'owned license')))
    for name,data in payload.items():(build/name).write_bytes(data)
    fixture={**public,'gameSha256':sha(game.read_bytes()),'files':{name:sha(data) for name,data in payload.items()}}
    profile=root/'OwnedPassiveProfile.json'
    raw=(json.dumps(fixture,indent=2)+'\n').encode()
    profile.write_bytes(raw)
    passive.RECIPE_PATH=profile
    passive.RECIPE_SHA256=sha(raw)
    manager=SteamPlay(steam,active_user=42,state=root/'receipt',process_running=lambda name:False)
    transport=passive.PassiveLateSteam(manager,tools_root=root/'private tools')

    def refused(call):
        before=config.read_bytes()
        try:call()
        except PatchError:pass
        else:raise AssertionError('Expected refusal')
        assert config.read_bytes()==before

    profile.write_bytes(raw+b' ')
    refused(lambda:passive.PassiveLateSteam(manager,tools_root=root/'private tools'))
    profile.write_bytes(raw)
    for name,data in payload.items():
        (build/name).write_bytes(data+b'changed')
        refused(lambda:transport.enable(build,game))
        (build/name).write_bytes(data)
    game.write_bytes(b'changed game')
    refused(lambda:transport.enable(build,game))
    game.write_bytes(b'inert game: never execute')
    cli=subprocess.run([sys.executable,'-B',str(ROOT/'source/launch/late_startup/SteamPassiveControl.py'),'setup','--debugger','--server-slots','500000'],capture_output=True,text=True)
    assert cli.returncode==2 and 'unrecognized arguments' in cli.stderr

    result=transport.enable(build,game)
    launcher=Path(result['launcher'])
    assert launch_field(config.read_bytes()).value=='"'+str(launcher)+'" %command%'
    assert 'stock 129,999' in result['notice'] and 'No debugger attaches.' in result['notice']
    assert '500,000' not in result['notice'] and '120 seconds' in result['notice']
    receipt=json.loads((manager.state/'receipt.json').read_text())
    assert receipt['original']=={'present':False,'value':None,'raw':None}
    assert receipt['latePassiveControlRecipeSha256']==passive.RECIPE_SHA256
    assert 'lateControlRecipeSha256' not in receipt and 'lateStartupRecipeSha256' not in receipt
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
    # Simulate the currently installed stock route with the same canonical receipt.
    stock_payload={**fixture['files'],'BO3-Late-Control.exe':fixture['files'][passive.FILES[0]]}
    del stock_payload[passive.FILES[0]]
    stock_profile=root/'OwnedStockProfile.json'
    stock_raw=(json.dumps({**fixture,'files':stock_payload})+'\n').encode()
    stock_profile.write_bytes(stock_raw)
    fixed=setup.FixedSteamRecipe(stock_profile,sha(stock_raw),('BO3-Late-Control.exe',*passive.FILES[1:]),'late-startup-control','lateControlRecipeSha256','owned stock route')
    (build/'BO3-Late-Control.exe').write_bytes(payload[passive.FILES[0]])
    stock=setup.LateSteam(manager,tools_root=root/'stock tools',fixed=fixed)
    stock.enable(build,game)
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

    blocked=passive.PassiveLateSteam(SteamPlay(steam,active_user=42,state=root/'receipt',process_running=lambda name:name==passive.FILES[0]),tools_root=root/'private tools')
    refused(lambda:blocked.enable(build,game))
    refused(blocked.remove)
    report={'passed':True,'groups':['fixed-passive-schema-and-payload-refusals','native-argv-Steam-IDs-and-diagnostic-notice',
        'canonical-stock-route-receipt-and-original-restoration','passive-controller-setup-remove-refusal'],
        'gameExecuted':False,'normalSteamConfigEdited':False,'ownedLauncherSha256':sha(args.target.read_bytes()),
        'argvSha256':sha(log.read_bytes()),'sourceSha256':sha((ROOT/'source/launch/late_startup/SteamPassiveControl.py').read_bytes()),
        'testSha256':sha(Path(__file__).read_bytes()),'publicRecipeSha256':public_sha,
        'sharedSetupSha256':public['sharedSetupSha256'],'sharedSources':public['sharedSources']}
    (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
