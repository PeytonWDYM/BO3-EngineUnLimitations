"""Owned fixed bindings-control Steam transactions without native or game launches."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'source'))
from patcher.errors import PatchError
from patcher.paths import private_path
from patcher.steam_launch import SteamPlay
from patcher.vdf_span import launch_field
from launch.bindings_control import SteamSetup as bindings


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=private_path(args.output,installations=(ROOT,))
    root.mkdir(parents=True,exist_ok=False)
    public=bindings.recipe()
    assert public['status']=='experimental' and public['startupMethod']=='late-crt-job-freeze-bindings-control'
    assert public['serverTotal']==130000 and public['serverUsableSlots']==129999
    assert public['clientTotal']==65000 and public['clientRoots']==8 and public['migrationPolicy']=='stock'
    assert public['gameInstructionEdits']==0 and public['helperBindingEdits']==7
    assert public['relayAllocations']==1 and public['relayBlocks']==2
    assert public['hookActivation'] is False and public['expandedPoolEnrollment'] is False
    assert public['liveAllocationValidated'] is False and public['requiredRuntimeMetadataMask']==3
    assert public['gateDeadlineMs']==30000 and public['observationLimitMs']==120000
    assert public['requiresSolePrimary'] is True and public['debuggerAttachment'] is False
    assert public['scope']=='Exact-host bounded stock-capacity diagnostic. Game loading, AAE and friends remain unvalidated.'
    assert set(public['files'])==set(bindings.FILES)
    assert public['sharedSources']['engine.py']=='02fa311b716d5768d6b2b35eebc080f26c5ed9e46816055be55adb8e4bff733d'
    assert bindings.fixed_recipe().tools_name=='bindings-control'
    assert bindings.fixed_recipe().receipt_key=='bindingsControlRecipeSha256'
    assert b'\r' not in bindings.RECIPE_PATH.read_bytes() and b'\r' not in Path(bindings.__file__).read_bytes()
    public_sha=bindings.RECIPE_SHA256
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
    payload={name:('inert payload '+name).encode() for name in bindings.FILES}
    for name,data in payload.items():(build/name).write_bytes(data)
    fixture={**public,'gameSha256':sha(game.read_bytes()),'files':{name:sha(data) for name,data in payload.items()}}
    profile=root/'OwnedBindingsProfile.json'
    raw=(json.dumps(fixture,indent=2)+'\n').encode()
    profile.write_bytes(raw)
    bindings.RECIPE_PATH=profile
    bindings.RECIPE_SHA256=sha(raw)
    manager=SteamPlay(steam,active_user=42,state=root/'receipt',process_running=lambda name:False)
    transport=bindings.BindingsSteam(manager,tools_root=root/'private tools')

    def refused(call):
        before=config.read_bytes()
        try:call()
        except PatchError:pass
        else:raise AssertionError('Expected refusal')
        assert config.read_bytes()==before

    profile.write_bytes(raw+b' ')
    refused(lambda:bindings.BindingsSteam(manager,tools_root=root/'private tools'))
    profile.write_bytes(raw)
    changed=(json.dumps({**fixture,'sharedSetupSha256':'0'*64})+'\n').encode()
    profile.write_bytes(changed)
    bindings.RECIPE_SHA256=sha(changed)
    refused(lambda:bindings.BindingsSteam(manager,tools_root=root/'private tools'))
    profile.write_bytes(raw)
    bindings.RECIPE_SHA256=sha(raw)
    for name,data in payload.items():
        (build/name).write_bytes(data+b'changed')
        refused(lambda:transport.enable(build,game))
        (build/name).write_bytes(data)
    game.write_bytes(b'changed game')
    refused(lambda:transport.enable(build,game))
    game.write_bytes(b'inert game: never execute')
    result=transport.enable(build,game)
    launcher=Path(result['launcher'])
    assert launch_field(config.read_bytes()).value=='"'+str(launcher)+'" %command%'
    assert 'stock-capacity diagnostic' in result['notice'] and '129,999' in result['notice']
    assert 'seven helper bindings and two relay blocks' in result['notice'] and 'no expanded-pool enrollment' in result['notice']
    assert '500' not in result['notice'] and '120-second' in result['notice']
    assert {p.name for p in launcher.parent.iterdir()}==set(bindings.FILES)
    receipt=json.loads((manager.state/'receipt.json').read_text())
    assert receipt['original']=={'present':False,'value':None,'raw':None}
    assert receipt['bindingsControlRecipeSha256']==bindings.RECIPE_SHA256
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
        if value:assert launch_field(config.read_bytes()).value=='"'+str(launcher)+'" %command% '+value
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
    assert {'BO3-Bindings-Control.exe','BO3-Job-Zombies.exe','BO3-Job-Control.exe'}<=set(bindings.CONTROLLERS)
    for running in ('steam.exe','BlackOps3.exe',*bindings.CONTROLLERS):
        blocked=bindings.BindingsSteam(SteamPlay(steam,active_user=42,state=root/'receipt',process_running=lambda name,r=running:name==r),tools_root=root/'private tools')
        refused(lambda:blocked.enable(build,game))
        refused(blocked.remove)
    checks=0
    def appears_late(name):
        nonlocal checks
        if name=='steam.exe':checks+=1
        return name=='BO3-Bindings-Control.exe' and checks>1
    late=bindings.BindingsSteam(SteamPlay(steam,active_user=42,state=root/'receipt',process_running=appears_late),tools_root=root/'private tools')
    refused(lambda:late.enable(build,game))
    assert json.loads((manager.state/'receipt.json').read_text())['phase']=='pending'
    transport.remove()
    assert config.read_bytes()==original
    report={'passed':True,'groups':['fixed-stock-bindings-recipe-and-payload-refusals','canonical-command-and-diagnostic-notice',
        'canonical-config-restoration-and-cache-refusals','controller-parent-and-final-process-refusals'],
        'nativeExecuted':False,'gameExecuted':False,'normalSteamConfigEdited':False,'controllers':bindings.CONTROLLERS,
        'sourceSha256':sha(Path(bindings.__file__).read_bytes()),'testSha256':sha(Path(__file__).read_bytes()),
        'publicRecipeSha256':public_sha,'sharedSetupSha256':public['sharedSetupSha256'],'sharedSources':public['sharedSources']}
    (root/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
