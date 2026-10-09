"""Exercise private Steam command forwarding and Workshop paths without starting BO3."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[3]
output = args.output.resolve()
if output.is_relative_to(repo) or output.exists():
    raise SystemExit('Use a new output directory outside the repository.')
output.mkdir(parents=True)
root = output / 'private root'
game = root / 'steamapps/common/BlackOps3'
game.mkdir(parents=True)
(game / 'players').mkdir()
(game / 'BlackOps3.exe').write_bytes(b'MZ private fixture')
helper = root / 'steamapps/workshop/content/311210/2631943123/T7Overcharged.ff'
helper.parent.mkdir(parents=True)
helper.write_bytes(b'MZ private workshop fixture')
launcher = root / 'launcher'
launcher.mkdir()
for name in ('BO3-500K-Zombies.exe', 'Bo3EnhancedHelper.dll', 'Bo3StartupGate.dll'):
    (launcher / name).write_bytes(b'owned fixture')
runtime = output / 'steam-runtime.py'
runtime.write_text('''import json, os, sys
from pathlib import Path
Path(os.environ['WRAPPER_RESULT']).write_text(json.dumps({
    'cwd': str(Path.cwd()), 'arguments': sys.argv[1:],
    'prefix': os.environ['STEAM_COMPAT_DATA_PATH'],
    'install': os.environ['STEAM_COMPAT_INSTALL_PATH'],
    'helper': Path('../../workshop/content/311210/2631943123/T7Overcharged.ff').read_bytes().decode(),
}))
''')
script = repo / 'scripts/proton/Launch-Private.sh'
cases = []
arguments = ['+set', 'literal value $(touch should-not-exist)', '+set', 'fs_game', '2631943123']
for mode in ('stock', 'patch'):
    result_file = output / f'{mode}.json'
    env = dict(os.environ, BO3_500K_MODE=mode, WRAPPER_RESULT=str(result_file), PRIVATE_TEST_SECRET='do-not-log-environment')
    command = ['bash', str(script), str(root), sys.executable, str(runtime), '/original/BlackOps3.exe', *arguments]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    actual = json.loads(result_file.read_text())
    assert actual['cwd'] == actual['install'] == str(game)
    assert actual['prefix'] == str(root / 'compatdata')
    assert actual['helper'] == 'MZ private workshop fixture'
    expected = [str(game / 'BlackOps3.exe')] if mode == 'stock' else [str(launcher / 'BO3-500K-Zombies.exe'), 'Z:' + str(game / 'BlackOps3.exe').replace('/', '\\')]
    assert actual['arguments'] == expected + arguments
    assert not (game / 'should-not-exist').exists()
    cases.append({'name': f'{mode}-private-cwd-prefix-workshop-and-arguments', 'passed': True})
for name, mode, executable_args in (
    ('invalid-mode', 'unknown', ['/original/BlackOps3.exe']),
    ('missing-executable-argument', 'patch', []),
    ('ambiguous-executable-arguments', 'patch', ['/first/BlackOps3.exe', '/second/BlackOps3.exe']),
):
    result_file = output / f'{name}.json'
    result = subprocess.run(['bash', str(script), str(root), sys.executable, str(runtime), *executable_args],
                            env=dict(os.environ, BO3_500K_MODE=mode, WRAPPER_RESULT=str(result_file)), capture_output=True, timeout=30)
    assert result.returncode == 2 and not result_file.exists(), name
    cases.append({'name': name, 'passed': True})
for log in (root / 'logs').glob('*.log'):
    assert 'do-not-log-environment' not in log.read_text()
(output / 'result.json').write_text(json.dumps({'passed': True, 'cases': cases,
    'wrapperSha256': hashlib.sha256(script.read_bytes()).hexdigest(),
    'scope': 'Owned command and Workshop file fixtures. No game launch or native patch writes.'}, indent=2) + '\n')
print(f'{len(cases)} private Steam wrapper cases passed.')
