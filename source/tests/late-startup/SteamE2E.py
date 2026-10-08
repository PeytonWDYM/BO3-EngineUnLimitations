"""Owned VDF/four-file cache and inert direct argv/environment recorder."""
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
from patcher.coordination import StateLock
from patcher.errors import PatchError
from patcher.paths import private_path
from patcher.steam_launch import SteamPlay
from patcher.vdf_span import launch_field

def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--target',type=Path,required=True)
    args=parser.parse_args();root=private_path(args.output,installations=(ROOT,));root.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('SteamLateSetup',ROOT/'source/launch/late_startup/SteamSetup.py')
    setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)
    public=setup.recipe()
    assert public['serverUsableSlots']==500000 and public['gateDeadlineMs']==30000
    assert public['successfulGameLifetime']=='until-exit' and set(public['files'])==set(setup.FILES)
    public_recipe_sha=setup.RECIPE_SHA256
    steam=root/'Steam fixture';config=steam/'userdata/42/config/localconfig.vdf';config.parent.mkdir(parents=True)
    original=b'"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { "311210" { "Unrelated" "keep" } } } } } }\r\n'
    config.write_bytes(original)
    game=root/'owned game'/ 'BlackOps3.exe';game.parent.mkdir();game.write_bytes(b'inert game: never execute')
    build=root/'owned build';build.mkdir()
    payload={'BO3-Late-Zombies.exe':args.target.read_bytes(),'Bo3EnhancedHelper.dll':b'inert VM helper','Bo3StartupGate.dll':b'inert gate','Detours-LICENSE.md':b'owned license'}
    for name,data in payload.items():(build/name).write_bytes(data)
    shared={name:sha((ROOT/'source/patcher'/name).read_bytes()) for name in ('steam_launch.py','coordination.py','vdf_span.py','paths.py','storage.py','windows.py','engine.py','errors.py','enhanced_launch.py','__init__.py')}
    recipe={'schemaVersion':1,'status':'experimental','gateDeadlineMs':30000,'successfulGameLifetime':'until-exit','serverUsableSlots':500000,
            'sharedSources':shared,'gameSha256':sha(game.read_bytes()),'files':{name:sha(data) for name,data in payload.items()}}
    recipe_path=root/'SteamProfile.json';raw=(json.dumps(recipe,indent=2)+'\n').encode();recipe_path.write_bytes(raw)
    setup.RECIPE_PATH=recipe_path;setup.RECIPE_SHA256=sha(raw)
    manager=SteamPlay(steam,active_user=42,state=root/'receipt',process_running=lambda name:False)
    transport=setup.LateSteam(manager,tools_root=root/'private tools')
    def refused(call):
        before=config.read_bytes()
        try:call()
        except PatchError:pass
        else:raise AssertionError('Expected refusal')
        assert config.read_bytes()==before
    recipe_path.write_bytes(raw+b' ');refused(lambda:setup.LateSteam(manager,tools_root=root/'private tools'));recipe_path.write_bytes(raw)
    for name,data in payload.items():
        (build/name).write_bytes(data+b'changed');refused(lambda:transport.enable(build,game));(build/name).write_bytes(data)
    saved=game.read_bytes();game.write_bytes(saved+b'changed');refused(lambda:transport.enable(build,game));game.write_bytes(saved)
    result=transport.enable(build,game);launcher=Path(result['launcher']);assert result['status']=='enabled'
    assert launch_field(config.read_bytes()).value=='"'+str(launcher)+'" %command%'
    assert {p.name for p in launcher.parent.iterdir()}==set(payload)
    arguments=['space value','é漢字','','embedded "quote"','trailing \\','--server-slots','7']
    log=root/'owned-argv.json';environment=dict(os.environ,OWNED_STEAM_OUTPUT=str(log),SteamAppId='owned app',SteamGameId='owned game',SteamOverlayGameId='owned overlay')
    child=subprocess.run([str(launcher),str(game),*arguments],env=environment,capture_output=True,text=True,timeout=20);assert child.returncode==0,child.stderr
    actual=json.loads(log.read_text(encoding='utf-8'));assert actual['arguments']==[str(game),*arguments]
    assert actual['environment']=={name:environment[name] for name in ('SteamAppId','SteamGameId','SteamOverlayGameId')}
    refused(lambda:transport.enable(build,game))
    assert transport.remove()['status']=='restored' and config.read_bytes()==original
    cached=launcher.parent/'Bo3StartupGate.dll';cached.write_bytes(b'changed cache');refused(lambda:transport.enable(build,game));cached.write_bytes(payload[cached.name])
    for running in ('steam.exe','BlackOps3.exe','BO3-Enhanced-Zombies.exe','BO3-Late-Zombies.exe','BO3-Startup-Control.exe'):
        blocked=setup.LateSteam(SteamPlay(steam,active_user=42,state=root/'receipt',process_running=lambda name,r=running:name==r),tools_root=root/'private tools')
        refused(lambda:blocked.enable(build,game));refused(blocked.remove)
    alias=root/'Steam alias';linked=subprocess.run(['cmd','/c','mklink','/J',str(alias),str(steam)],capture_output=True,text=True);assert linked.returncode==0,linked.stderr
    other=setup.LateSteam(SteamPlay(alias,active_user=42,state=root/'receipt',process_running=lambda name:False),tools_root=root/'private tools')
    assert other.manager.config==manager.config
    with StateLock(manager.state):refused(lambda:other.enable(build,game))
    redirect=root/'redirected tools';linked=subprocess.run(['cmd','/c','mklink','/J',str(redirect),str(game.parent)],capture_output=True,text=True);assert linked.returncode==0,linked.stderr
    refused(lambda:setup.LateSteam(manager,tools_root=redirect).enable(build,game));assert {p.name for p in game.parent.iterdir()}=={'BlackOps3.exe'}
    source=launch_field(original).with_value('-windowed "plain value"');config.write_bytes(source)
    transport.enable(build,game);assert launch_field(config.read_bytes()).value.endswith(' -windowed "plain value"')
    config.write_bytes(config.read_bytes().replace(b'"keep"',b'"later"'))
    transport.remove();assert config.read_bytes()==source.replace(b'"keep"',b'"later"')
    report={'passed':True,'groups':['public-recipe-admission','fixed-recipe-refusal','four-file-and-game-hashes','direct-argv-environment','absent-original-restoration','earlier-wrapper-refusal',
        'cache-refusal','five-running-processes-setup-remove','Steam-alias-lock','redirect-before-write','plain-args-and-later-unrelated-preservation'],
        'gameExecuted':False,'normalSteamConfigEdited':False,'ownedLauncherSha256':sha(args.target.read_bytes()),'argvSha256':sha(log.read_bytes()),
        'sourceSha256':sha((ROOT/'source/launch/late_startup/SteamSetup.py').read_bytes()),'testSha256':sha(Path(__file__).read_bytes()),'sharedSources':shared,
        'publicRecipeSha256':public_recipe_sha}
    (root/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
