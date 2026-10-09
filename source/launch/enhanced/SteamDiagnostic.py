"""Temporary 120-second stock-capacity Control08 route through Steam Play."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

SOURCE = Path(__file__).resolve().parent
REPOSITORY = SOURCE.parents[2]
sys.path.insert(0, str(REPOSITORY / 'source'))
from patcher.coordination import StateLock
from patcher.errors import PatchError
from patcher.paths import private_path, reject_redirects
from patcher.steam_launch import SteamPlay
from patcher.storage import durable_write
from patcher.vdf_span import launch_field, quote
from patcher.windows import steam_context

FILES = ('BO3-Startup-Control.exe', 'Bo3EnhancedHelper.dll', 'Detours-LICENSE.md')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DiagnosticSetup:
    # Profile/tools overrides belong to owned fixtures; the CLI pins Control08.
    def __init__(self, manager: SteamPlay, *, profile: dict | None = None, tools_root: Path | None = None):
        self.manager = manager
        self.profile = profile if profile is not None else json.loads((SOURCE / 'SteamDiagnosticProfile.json').read_text())
        self.tools_root = tools_root or Path(os.environ['LOCALAPPDATA']) / 'BO3 Engine UnLimitations/steam-diagnostic-control08'
        provider = manager.process_running
        manager.process_running = lambda name: provider(name) or provider('BO3-Startup-Control.exe')
        p = self.profile
        if (p.get('schemaVersion') != 1 or p.get('mode') != '--no-debugger' or p.get('capacity') != 'stock'
                or type(p.get('deadlineSeconds')) is not int or p['deadlineSeconds'] != 120
                or set(p.get('files', {})) != set(FILES)
                or any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value)
                       for value in (p.get('gameSha256'), *p['files'].values()))):
            raise PatchError('Invalid stock-capacity diagnostic profile.')

    def _prepare(self, build: Path, game: Path, logs: Path) -> Path:
        protected = (self.manager.steam, game.parent, REPOSITORY)
        logs = private_path(logs, installations=protected)
        tools = private_path(self.tools_root, installations=protected)
        payload = {}
        for name, expected in self.profile['files'].items():
            source = build / name
            reject_redirects(source, private_files=True)
            data = source.read_bytes()
            if digest(data) != expected:
                raise PatchError('The Control08 diagnostic payload does not match its reviewed hash.')
            payload[name] = data
        runtime = dict(self.profile, game=str(game), logs=str(logs))
        payload['runtime.json'] = (json.dumps(runtime, indent=2) + '\n').encode()
        payload['SteamDiagnosticShim.ps1'] = (SOURCE / 'SteamDiagnosticShim.ps1').read_bytes()
        identity = digest(b''.join(name.encode() + digest(data).encode() for name, data in sorted(payload.items())))
        folder = private_path(tools, identity, protected)
        with StateLock(tools):
            if folder.exists():
                if {p.name for p in folder.iterdir()} != set(payload):
                    raise PatchError('The private diagnostic cache has unexpected files.')
                for name, data in payload.items():
                    path = private_path(folder, name, protected)
                    if path.read_bytes() != data:
                        raise PatchError('The private diagnostic cache changed. Setup was refused.')
            else:
                staging = private_path(tools, 'stage-' + uuid.uuid4().hex, protected)
                staging.mkdir()
                for name, data in payload.items():
                    durable_write(private_path(staging, name, protected), data)
                staging.rename(folder)
        logs.mkdir(parents=True, exist_ok=True)
        return folder

    def enable(self, build: Path, game: Path, logs: Path, powershell: Path) -> dict:
        manager = self.manager
        manager._closed()
        reject_redirects(game, private_files=True)
        game = game.resolve(strict=True)
        if digest(game.read_bytes()) != self.profile['gameSha256']:
            raise PatchError('Unsupported game executable for the stock diagnostic.')
        reject_redirects(powershell, private_files=True)
        powershell = powershell.resolve(strict=True)
        if powershell.name.casefold() != 'pwsh.exe':
            raise PatchError('Select the PowerShell 7 pwsh.exe host.')
        version = subprocess.run([str(powershell), '-NoLogo', '-NoProfile', '-Command',
                                  '$PSVersionTable.PSVersion.Major'], capture_output=True, text=True, timeout=15)
        if version.returncode != 0 or not version.stdout.strip().isdecimal() or int(version.stdout.strip()) < 7:
            raise PatchError('PowerShell 7 is required before configuring Steam Play.')
        private_path(manager.state, installations=(manager.steam, game.parent, REPOSITORY))
        manager._private_paths()
        with StateLock(manager.state):
            receipt = manager._recover(manager._receipt())
            if receipt and receipt['phase'] == 'enabled':
                raise PatchError('Restore the existing Steam Play route before enabling this diagnostic.')
            before = manager._read()
            field = launch_field(before)
            if field.value and '%command%' in field.value.casefold():
                raise PatchError('Existing Steam launch options already contain a wrapper. Restore it first.')
            folder = self._prepare(build, game, logs)
            shim = folder / 'SteamDiagnosticShim.ps1'
            installed = f'"{powershell}" -NoLogo -NoProfile -File "{shim}" %command%'
            if field.value:
                installed += ' ' + field.value
            receipt = {'schemaVersion': 1, 'config': str(manager.config), 'phase': 'restored',
                       'original': field.snapshot(), 'installed': installed,
                       'inserted': field.insertion(quote(installed))[1] if field.entry is None else '',
                       'diagnostic': {'capacity': 'stock', 'deadlineSeconds': 120,
                                      'controlSha256': self.profile['files'][FILES[0]]}}
            manager._edit(before, field.with_value(installed), receipt, 'enable')
        return {'status': 'enabled', 'shim': str(shim), 'receiptFolder': str(manager.state),
                'capacity': 'stock', 'deadlineSeconds': 120}

    def remove(self) -> dict:
        # The reviewed remover owns pending recovery and exact original-field restoration.
        return self.manager.remove()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'remove'))
    parser.add_argument('--steam', type=Path)
    parser.add_argument('--steam-user', type=int)
    parser.add_argument('--control-build', type=Path)
    parser.add_argument('--game', type=Path, help='Exact BlackOps3.exe path')
    parser.add_argument('--logs', type=Path)
    parser.add_argument('--powershell', type=Path)
    args = parser.parse_args()
    context = steam_context() if args.steam is None or args.steam_user is None else None
    manager = SteamPlay(args.steam or context.directory,
                        active_user=args.steam_user if args.steam_user is not None else context.active_user,
                        auto_login_name=context.auto_login_name if context else None)
    diagnostic = DiagnosticSetup(manager)
    if args.action == 'remove':
        result = diagnostic.remove()
    else:
        if not all((args.control_build, args.game, args.logs)):
            parser.error('setup requires --control-build, --game and --logs')
        host = args.powershell or shutil.which('pwsh')
        if not host:
            raise PatchError('PowerShell 7 is required.')
        result = diagnostic.enable(args.control_build, args.game, args.logs, Path(host))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (PatchError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
