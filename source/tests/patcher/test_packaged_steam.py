"""Frozen Steam commands against an owned tree and inert resource payloads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from patcher.vdf_span import launch_field


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    root = args.output.resolve()
    config = root / 'Steam/userdata/42/config/localconfig.vdf'
    config.parent.mkdir(parents=True)
    original = b'"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { "311210" { "cloud" { "owned" "keep" } } "999" { "LaunchOptions" "other" } } } } } }\r\n'
    config.write_bytes(original)
    resources = root / 'resources'
    (resources / 'patchplans').mkdir(parents=True)
    (resources / 'patchplans/release.json').write_bytes(args.manifest.read_bytes())
    enhanced = resources / 'enhanced'
    enhanced.mkdir()
    files = {}
    for name in ('BO3-Enhanced-Zombies.exe', 'Bo3EnhancedHelper.dll', 'Detours-LICENSE.md'):
        data = ('Inert owned frozen fixture: ' + name).encode()
        (enhanced / name).write_bytes(data)
        files[name] = sha(data)
    game = root / 'game'
    game.mkdir()
    (game / 'BlackOps3.exe').write_bytes(b'Inert owned game fixture; never execute')
    (game / 'settings.ini').write_bytes(b'Owned unchanged settings')
    (enhanced / 'manifest.json').write_text(json.dumps({'schemaVersion': 1, 'version': '0.1.0-test.3', 'status': 'experimental', 'gameSha256': sha((game / 'BlackOps3.exe').read_bytes()), 'files': files}))
    environment = dict(os.environ, LOCALAPPDATA=str(root / 'private'))
    before_files = {p.name: sha(p.read_bytes()) for p in game.iterdir()}
    flags = ['--steam', str(root / 'Steam'), '--steam-user', '42', '--game', str(game), '--resources', str(resources), '--state', str(game / 'must-not-be-used')]
    commands = []
    enabled = False
    for action in ('steam-enable', 'steam-remove'):
        result = subprocess.run([str(args.executable.resolve()), action, *flags], capture_output=True, text=True, env=environment, timeout=120)
        (root / (action + '-stdout.txt')).write_text(result.stdout, encoding='utf-8')
        (root / (action + '-stderr.txt')).write_text(result.stderr, encoding='utf-8')
        assert result.returncode in (0, 1), result.stderr
        if result.returncode == 1:
            assert 'Close Steam' in result.stderr, result.stderr
            status = 'process-closure-refused'
        else:
            status = json.loads(result.stdout)['result']['status']
            if action == 'steam-enable':
                assert status == 'enabled'
                enabled = True
                assert '%command%' in launch_field(config.read_bytes()).value
            else:
                assert status in ('restored', 'already-restored')
                enabled = False
        commands.append({'action': action, 'exitCode': result.returncode, 'status': status})
        assert launch_field(original).with_value('sentinel') == launch_field(config.read_bytes()).with_value('sentinel')
        assert before_files == {p.name: sha(p.read_bytes()) for p in game.iterdir()}
        assert not (game / 'must-not-be-used').exists()
    if not enabled:
        assert config.read_bytes() == original
    report = {'status': 'passed', 'scope': 'Frozen CLI, owned Steam tree and inert native/game files',
              'artifactSha256': sha(args.executable.read_bytes()), 'commands': commands,
              'originalConfigSha256': sha(original), 'finalConfigSha256': sha(config.read_bytes()),
              'ownedGameHashes': before_files, 'nativeExecuted': False, 'gameplayValidated': False}
    (root / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
