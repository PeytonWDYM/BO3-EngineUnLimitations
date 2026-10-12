"""Check the real actor500 payload through an owned installer transaction. Never start BO3."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from patcher.errors import PatchError
from patcher.payload import PAYLOAD_NAMES, file_hash
from patcher.steam_launch import SteamPlay


def run(build: Path, executable: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    release = Path(__file__).resolve().parents[2] / 'release.json'
    manifest = json.loads(release.read_text(encoding='utf-8'))
    profile = manifest['builds'][0]
    receipt = json.loads((build / 'build-receipt.json').read_text(encoding='utf-8-sig'))
    assert receipt['clientTotal'] == 250001
    assert manifest['version'] == '0.5.0-test.5'
    capacities = {'serverUsableSlots': 500000, 'pendingCallbacksPerLocalClient': 8192,
                  'clientfieldCounters': 8192, 'actorCapacity': 500, 'sentientCapacity': 540,
                  'actorRuntimeFunctions': 2465, 'nativeEdits': 360}
    for name, expected in capacities.items():
        assert receipt[name] == expected and manifest[name] == expected, name
    assert receipt['gameSha256'] == profile['gameSha256']
    assert manifest['clientUsableSlots'] == 250000
    assert file_hash(executable) == profile['gameSha256']
    resources = output / 'resources'
    native = resources / 'native' / profile['id']
    native.mkdir(parents=True)
    shutil.copyfile(release, resources / 'release.json')
    for name in PAYLOAD_NAMES:
        assert file_hash(build / name) == profile['files'][name]
        shutil.copyfile(build / name, native / name)
    cases = []

    def fixture(name: str, *, known: bool = True) -> tuple[SteamPlay, Path, Path, bytes]:
        root = output / name
        config = root / 'steam/userdata/42/config/localconfig.vdf'
        config.parent.mkdir(parents=True)
        original = (b'"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { '
                    b'"311210" { "LaunchOptions" "+set owned 1" "Other" "keep" } } } } } }\r\n')
        config.write_bytes(original)
        game = root / 'game'
        game.mkdir()
        if known:
            shutil.copyfile(executable, game / 'BlackOps3.exe')
        else:
            (game / 'BlackOps3.exe').write_bytes(b'Owned unknown executable. Never run as a game.')
        manager = SteamPlay(root / 'steam', active_user=42, state=root / 'state', process_running=lambda _: False)
        return manager, game, root / 'tools', original

    manager, game, tools, original = fixture('install-repeat-remove')
    manager.enable(resources, game, tools_root=tools)
    assert manager.status(game, resources)['status'] == 'enabled'
    assert b'+set owned 1' in manager.config.read_bytes()
    staged = next(path for path in tools.iterdir() if path.is_dir())
    for name in PAYLOAD_NAMES:
        assert file_hash(staged / name) == profile['files'][name]
    manager.enable(resources, game, tools_root=tools)
    manager.remove()
    assert manager.config.read_bytes() == original
    assert file_hash(game / 'BlackOps3.exe') == profile['gameSha256']
    cases.append({'name': 'install-repeat-remove', 'passed': True})

    for name in ('unknown-game', *PAYLOAD_NAMES):
        manager, game, tools, original = fixture('refuse-' + name, known=name != 'unknown-game')
        bundle = resources
        if name != 'unknown-game':
            bundle = output / ('damaged-' + name)
            shutil.copytree(resources, bundle)
            (bundle / 'native' / profile['id'] / name).write_bytes(b'Damaged owned payload')
        try:
            manager.enable(bundle, game, tools_root=tools)
        except PatchError:
            pass
        else:
            raise AssertionError('Installer admitted ' + name)
        assert manager.config.read_bytes() == original and not tools.exists()
        cases.append({'name': 'refuse-' + name, 'passed': True})

    unknown = output / 'unknown.bin'
    unknown.write_bytes(b'Owned unknown executable fixture')
    refused = subprocess.run([str(build / PAYLOAD_NAMES[0]), str(unknown)], capture_output=True, text=True, timeout=20)
    assert refused.returncode == 2 and 'SHA256' in refused.stderr, refused.stderr
    cases.append({'name': 'launcher-refuses-unknown-before-child', 'passed': True, 'stderr': refused.stderr})
    files = [release, Path(__file__), build / 'build-receipt.json', *[build / name for name in PAYLOAD_NAMES]]
    (output / 'result.json').write_text(json.dumps({
        'passed': True, 'clientUsableSlots': 250000, **capacities,
        'scope': 'Real actor500 payload identity and owned Steam configuration. No game or GUI launch. Game behavior remains unverified.',
        'cases': cases, 'files': [{'path': str(path), 'sha256': file_hash(path)} for path in files],
    }, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.build.resolve(strict=True), args.executable.resolve(strict=True), args.output.resolve())
