"""Exercise the shipped CLI without using Steam or any game process."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--executable', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
# Under Wine the installer must refuse every action before it touches Steam.
wine = os.name == 'nt' and hasattr(ctypes.WinDLL('ntdll'), 'wine_get_version')
args.output.mkdir(parents=True, exist_ok=False)
config = args.output / 'steam/userdata/42/config/localconfig.vdf'
config.parent.mkdir(parents=True)
original = b'"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { "311210" {} } } } } }'
config.write_bytes(original)
game = args.output / 'game'
game.mkdir()
(game / 'BlackOps3.exe').write_bytes(b'Owned unknown game version')
cases = []
for name, code in [('status', 1), ('install', 1), ('remove', 1)] if wine else [('status', 0), ('install', 1), ('remove', 0)]:
    command = [str(args.executable), name, '--game', str(game), '--steam', str(args.output / 'steam'), '--steam-user', '42', '--state', str(args.output / 'state')]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (args.output / f'{name}.stdout.txt').write_text(result.stdout)
    (args.output / f'{name}.stderr.txt').write_text(result.stderr)
    assert result.returncode == code, result.stderr
    assert config.read_bytes() == original
    if wine:
        assert 'does not support Proton or Wine' in result.stderr, result.stderr
    elif name == 'install':
        assert 'Unsupported game version' in result.stderr
    cases.append({'name': name, 'passed': True, 'command': command, 'exitCode': result.returncode})
(args.output / 'result.json').write_text(json.dumps({'passed': True, 'cases': cases,
    'executableSha256': hashlib.sha256(args.executable.read_bytes()).hexdigest(),
    'wine': wine,
    'scope': 'Packaged CLI Wine refusal with an unchanged owned Steam config. No game execution.' if wine else
             'Packaged CLI, owned Steam config, unknown-version refusal and removal. No game execution.'}, indent=2) + '\n')
print('Three packaged executable cases passed' + (' under Wine.' if wine else '.'))
