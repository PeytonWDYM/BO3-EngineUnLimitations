"""Install one fixed experimental late-startup recipe in Steam's BO3 launch field."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

SOURCE=Path(__file__).resolve().parent
REPOSITORY=SOURCE.parents[2]
sys.path.insert(0,str(REPOSITORY/'source'))
from patcher.coordination import StateLock
from patcher.errors import PatchError
from patcher.paths import private_path,reject_redirects
from patcher.steam_launch import SteamPlay
from patcher.storage import durable_write
from patcher.vdf_span import launch_field,quote
from patcher.windows import steam_context

FILES=('BO3-Late-Zombies.exe','Bo3EnhancedHelper.dll','Bo3StartupGate.dll','Detours-LICENSE.md')
RECIPE_PATH=SOURCE/'SteamProfile.json'
RECIPE_SHA256='876eb122846464cef0d0067333e83e58dfd1115e943d58d33411884b33cbf657'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def recipe() -> dict:
    reject_redirects(RECIPE_PATH,private_files=True)
    raw=RECIPE_PATH.read_bytes()
    if digest(raw)!=RECIPE_SHA256:
        raise PatchError('Unsupported late-startup Steam recipe.')
    admitted=json.loads(raw)
    for name,expected in admitted['sharedSources'].items():
        path=REPOSITORY/'source/patcher'/name
        reject_redirects(path,private_files=True)
        if digest(path.read_bytes())!=expected:
            raise PatchError('A reviewed shared Steam transaction source changed.')
    return admitted


class LateSteam:
    # The CLI admits the fixed recipe. tools_root supports owned fixtures only.
    def __init__(self,manager: SteamPlay,*,tools_root: Path | None=None):
        self.plan=recipe()
        self.manager=manager
        self.tools_root=tools_root or Path(os.environ['LOCALAPPDATA'])/'BO3 Engine UnLimitations/late-zombies'
        provider=manager.process_running
        manager.process_running=lambda name:provider(name) or provider(FILES[0]) or provider('BO3-Startup-Control.exe')

    def _prepare(self,build: Path,game: Path) -> Path:
        protected=(self.manager.steam,game.parent,REPOSITORY)
        tools=private_path(self.tools_root,installations=protected)
        payload={}
        for name in FILES:
            source=build/name
            reject_redirects(source,private_files=True)
            data=source.read_bytes()
            if digest(data)!=self.plan['files'][name]:
                raise PatchError('A late-startup payload differs from the reviewed recipe.')
            payload[name]=data
        identity=digest(json.dumps(self.plan['files'],sort_keys=True).encode())
        folder=private_path(tools,identity,protected)
        with StateLock(tools):
            if folder.exists():
                if {p.name for p in folder.iterdir()}!=set(FILES):
                    raise PatchError('The private late-startup cache has unexpected files.')
                for name,data in payload.items():
                    if private_path(folder,name,protected).read_bytes()!=data:
                        raise PatchError('The private late-startup cache changed. Setup was refused.')
            else:
                stage=private_path(tools,'stage-'+uuid.uuid4().hex,protected)
                stage.mkdir()
                for name,data in payload.items():
                    durable_write(private_path(stage,name,protected),data)
                private_path(tools,folder.name,protected)
                stage.rename(folder)
        return folder

    def enable(self,build: Path,game: Path) -> dict:
        manager=self.manager
        manager._closed()
        reject_redirects(game,private_files=True)
        game=game.resolve(strict=True)
        if digest(game.read_bytes())!=self.plan['gameSha256']:
            raise PatchError('Unsupported BlackOps3.exe for the fixed late-startup recipe.')
        private_path(manager.state,installations=(manager.steam,game.parent,REPOSITORY))
        manager._private_paths()
        with StateLock(manager.state):
            receipt=manager._recover(manager._receipt())
            if receipt and receipt['phase']=='enabled':
                raise PatchError('Restore the existing Steam Play route before late-startup setup.')
            before=manager._read()
            field=launch_field(before)
            if field.value and '%command%' in field.value.casefold():
                raise PatchError('Existing launch options already contain a wrapper. Restore it first.')
            folder=self._prepare(build,game)
            launcher=folder/FILES[0]
            installed='"'+str(launcher)+'" %command%'+(' '+field.value if field.value else '')
            receipt={'schemaVersion':1,'config':str(manager.config),'phase':'restored','original':field.snapshot(),
                     'installed':installed,'inserted':field.insertion(quote(installed))[1] if field.entry is None else '',
                     'lateStartupRecipeSha256':RECIPE_SHA256}
            manager._edit(before,field.with_value(installed),receipt,'enable')
        return {'status':'enabled','launcher':str(launcher),'receiptFolder':str(manager.state),
                'notice':'EXPERIMENTAL: 500,000 server script slots. Actual game loading, mods and friends remain unvalidated.'}

    def remove(self) -> dict:
        return self.manager.remove()


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('setup','remove'))
    parser.add_argument('--steam',type=Path)
    parser.add_argument('--steam-user',type=int)
    parser.add_argument('--native-build',type=Path)
    parser.add_argument('--game',type=Path,help='Exact BlackOps3.exe path')
    args=parser.parse_args()
    context=steam_context() if args.steam is None or args.steam_user is None else None
    manager=SteamPlay(args.steam or context.directory,
                     active_user=args.steam_user if args.steam_user is not None else context.active_user,
                     auto_login_name=context.auto_login_name if context else None)
    transport=LateSteam(manager)
    if args.action=='remove':
        result=transport.remove()
    else:
        if not args.native_build or not args.game:
            parser.error('setup requires --native-build and --game')
        result=transport.enable(args.native_build,args.game)
    print(json.dumps(result,indent=2))
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (PatchError,OSError,ValueError) as error:
        print(str(error),file=sys.stderr)
        raise SystemExit(1)
