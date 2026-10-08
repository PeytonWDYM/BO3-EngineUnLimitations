"""Configure one reviewed stock-capacity startup observation probe through Steam."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

SOURCE=Path(__file__).resolve().parent
sys.path.insert(0,str(SOURCE.parents[2]/'source'))
from patcher.errors import PatchError
from patcher.paths import reject_redirects
from patcher.steam_launch import SteamPlay
from patcher.windows import steam_context

SHARED_SETUP_SHA256='4798521805157217225d93f88b45796e89eaf87e9663c2b4b594a915c94cb252'
RECIPE_PATH=SOURCE/'SteamProbeProfile.json'
# This exact recipe binds the native final build and independent review.
RECIPE_SHA256='634b38a455288d64ea1d021ba786a14b488faa250e4ba0f66d7dbcc566bc114f'


def digest(path: Path) -> str:
    reject_redirects(path,private_files=True)
    return hashlib.sha256(path.read_bytes()).hexdigest()


if digest(SOURCE/'SteamDiagnostic.py')!=SHARED_SETUP_SHA256:
    raise PatchError('The reviewed shared Steam setup source changed.')
sys.path.insert(0,str(SOURCE))
from SteamDiagnostic import DiagnosticSetup


def recipe() -> dict:
    if digest(RECIPE_PATH)!=RECIPE_SHA256:
        raise PatchError('Unsupported Steam startup-probe recipe.')
    admitted=json.loads(RECIPE_PATH.read_text(encoding='utf-8'))
    for name in ('SteamDiagnostic.py','SteamDiagnosticShim.ps1'):
        if digest(SOURCE/name)!=admitted['sharedSources'][name]:
            raise PatchError('The reviewed shared Steam setup source changed.')
    return admitted['profile']


class SteamProbe(DiagnosticSetup):
    # The public transport admits one fixed recipe. Only tools_root is an owned-fixture provider.
    def __init__(self,manager: SteamPlay,*,tools_root: Path | None=None):
        profile=recipe()
        tools=tools_root or Path(os.environ['LOCALAPPDATA'])/'BO3 Engine UnLimitations/steam-startup-probe'
        super().__init__(manager,profile=profile,tools_root=tools)


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('setup','remove'))
    parser.add_argument('--steam',type=Path)
    parser.add_argument('--steam-user',type=int)
    parser.add_argument('--probe-build',type=Path)
    parser.add_argument('--game',type=Path,help='Exact BlackOps3.exe path')
    parser.add_argument('--logs',type=Path)
    parser.add_argument('--powershell',type=Path)
    args=parser.parse_args()
    context=steam_context() if args.steam is None or args.steam_user is None else None
    manager=SteamPlay(args.steam or context.directory,
                     active_user=args.steam_user if args.steam_user is not None else context.active_user,
                     auto_login_name=context.auto_login_name if context else None)
    probe=SteamProbe(manager)
    if args.action=='remove':
        result=probe.remove()
    else:
        if not all((args.probe_build,args.game,args.logs)):
            parser.error('setup requires --probe-build, --game and --logs')
        host=args.powershell or shutil.which('pwsh')
        if not host:
            raise PatchError('PowerShell 7 is required.')
        result=probe.enable(args.probe_build,args.game,args.logs,Path(host))
    print(json.dumps(result,indent=2))
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (PatchError,OSError,ValueError) as error:
        print(str(error),file=sys.stderr)
        raise SystemExit(1)
