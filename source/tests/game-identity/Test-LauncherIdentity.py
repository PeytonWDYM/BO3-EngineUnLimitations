"""Check the launcher's read-only PE admission using private executable copies.

--verify-build never starts a game process. It is safe on Windows and Wine, including
Wine versions with the process-suspend fallback. Runtime code guards are checked
separately by private startup tests; PE admission alone does not prove compatibility.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--launcher', type=Path, required=True, help='Folder with BO3-500K-Zombies.exe and both helpers')
parser.add_argument('--game', type=Path, required=True, help='BlackOps3.exe of the profiled build')
parser.add_argument('--other-build', type=Path, required=True, help='BlackOps3.exe of a different build')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
if os.name != 'nt' and not os.environ.get('WINEPREFIX'):
    raise SystemExit('Set WINEPREFIX to a private test prefix.')
args.output.mkdir(parents=True, exist_ok=False)
wine = os.environ.get('WINE', 'wine')
launcher = args.launcher / 'BO3-500K-Zombies.exe'
receipts = Path(os.environ['LOCALAPPDATA']) / 'BO3 Engine UnLimitations/sessions' if os.name == 'nt' else Path(os.environ['WINEPREFIX']) / 'drive_c/users'


def copy_game(name: str, data: bytes | None = None, source: Path | None = None) -> Path:
    folder = args.output / name / 'game'
    folder.mkdir(parents=True)
    target = folder / 'BlackOps3.exe'
    if data is None:
        shutil.copyfile(source or args.game, target)
    else:
        target.write_bytes(data)
    return target


def run(name: str, game: Path) -> dict:
    before = set(receipts.rglob('*.json'))
    command = [str(launcher), '--verify-build', str(game)]
    if os.name != 'nt':
        command.insert(0, wine)
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    (args.output / name / 'stdout.txt').write_text(result.stdout)
    (args.output / name / 'stderr.txt').write_text(result.stderr)
    created = sorted(set(receipts.rglob('*.json')) - before)
    receipt = json.loads(created[-1].read_text()) if created else None
    if receipt:
        shutil.copyfile(created[-1], args.output / name / 'receipt.json')
    return {'exitCode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr, 'receipt': receipt}


cases = []
genuine = copy_game('profiled-build-copy')
resigned_bytes = bytearray(args.game.read_bytes())
resigned_bytes[-1] ^= 0xff  # The last bytes belong to the Authenticode signature, not the code.
admitted = [('profiled-build-copy', genuine), ('same-build-other-signature', copy_game('same-build-other-signature', bytes(resigned_bytes)))]
for name, game in admitted:
    outcome = run(name, game)
    assert 'Unsupported game version' not in outcome['stderr'], outcome['stderr']
    assert outcome['exitCode'] == 0 and sha256(game) in outcome.get('stdout', ''), outcome
    assert outcome['receipt'] is None, f'{name}: read-only verification created a launch receipt.'
    cases.append({'name': name, 'passed': True, 'gameSha256': sha256(game), 'gameLaunched': False})

refused = [('other-build', copy_game('other-build', source=args.other_build)),
           ('not-a-pe', copy_game('not-a-pe', b'Not a Windows executable')),
           ('truncated-headers', copy_game('truncated-headers', args.game.read_bytes()[:0x100]))]
for name, game in refused:
    outcome = run(name, game)
    assert outcome['exitCode'] == 2, outcome
    assert 'Unsupported game version' in outcome['stderr'], outcome['stderr']
    assert outcome['receipt'] is None, f'{name}: a game process was created.'
    cases.append({'name': name, 'passed': True, 'gameSha256': sha256(game), 'exitCode': outcome['exitCode']})

(args.output / 'result.json').write_text(json.dumps({'passed': True, 'launcherSha256': sha256(launcher), 'cases': cases,
    'scope': 'Read-only launcher PE admission with private executable copies. No game process or patch writes.'}, indent=2) + '\n')
print(f'{len(cases)} launcher identity cases passed.')
