"""Run Steam wrapper path failures against private Linux filesystem fixtures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[3]
output = args.output.resolve()
if output.exists() or output.is_relative_to(repo):
    raise SystemExit('Use a new output directory outside the repository.')
output.mkdir(parents=True)
root = output / 'private root 世界'
common = root / 'steamapps/common'
game = common / 'Call of Duty Black Ops III 世界'
(game / 'players').mkdir(parents=True)
(game / 'BlackOps3.exe').write_bytes(b'MZ owned fixture')
helper = root / 'steamapps/workshop/content/311210/2631943123/T7Overcharged.ff'
helper.parent.mkdir(parents=True)
helper.write_text('owned Workshop fixture')
launcher = root / 'launcher'
installed = game / 'BO3-500K'
for directory in (launcher, installed):
    directory.mkdir()
    for name in ('BO3-500K-Zombies.exe', 'Bo3EnhancedHelper.dll', 'Bo3StartupGate.dll'):
        (directory / name).write_bytes(b'owned launcher fixture')
shutil.copyfile(repo / 'scripts/proton/Launch-Installed.sh', installed / 'Launch-Steam.sh')
codec = installed / 'Use-IntroCodec.sh'
codec.write_text('#!/usr/bin/env bash\nset -euo pipefail\nexport TEST_CODEC="$1"\nshift\nexec "$@"\n')
codec.chmod(0o755)
(installed / 'intro-codec.path').write_text(str(output / 'decoder 世界'))
alias = output / 'Steam library alias'
alias.symlink_to(root, target_is_directory=True)
external = output / 'other installation'
(external / 'players').mkdir(parents=True)
(external / 'BlackOps3.exe').write_bytes(b'MZ different owned fixture')
redirect = common / 'redirect'
redirect.symlink_to(external, target_is_directory=True)
runtime = output / 'capture-command.py'
runtime.write_text('''import json, os, sys
from pathlib import Path
Path(os.environ['WRAPPER_RESULT']).write_text(json.dumps({
    'cwd': str(Path.cwd()), 'arguments': sys.argv[1:],
    'prefix': os.environ.get('STEAM_COMPAT_DATA_PATH'),
    'install': os.environ['STEAM_COMPAT_INSTALL_PATH'],
    'codec': os.environ.get('TEST_CODEC'),
    'helper': Path('../../workshop/content/311210/2631943123/T7Overcharged.ff').read_text(),
}))
''')
literal = ['+set', 'literal $(touch should-not-exist)', '+set', 'fs_game', '2631943123']
cases = []


def run(name, script, command, *, selected_game=None, mode='patch', accepted=True, private=False, refusal=None):
    result_file = output / f'{name}.json'
    env = dict(os.environ, WRAPPER_RESULT=str(result_file), BO3_500K_MODE=mode,
               BO3_500K_SKIP_INTRO='0', STEAM_COMPAT_DATA_PATH=str(output / 'installed prefix'))
    env.pop('BO3_500K_GAME_PATH', None)
    if selected_game is not None:
        env['BO3_500K_GAME_PATH'] = str(selected_game)
    invocation = ['bash', str(script)]
    if private:
        invocation.append(str(root))
    invocation.extend([sys.executable, str(runtime), *command, *literal])
    result = subprocess.run(invocation, env=env, capture_output=True, text=True, timeout=30)
    passed = result.returncode == (0 if accepted else 2) and result_file.exists() == accepted
    if refusal is not None:
        passed = passed and refusal in result.stderr
    if passed and accepted:
        actual = json.loads(result_file.read_text())
        expected = [str(game / 'BlackOps3.exe')] if mode == 'stock' and private else [
            str(launcher if private else installed) + '/BO3-500K-Zombies.exe',
            'Z:' + str(game / 'BlackOps3.exe').replace('/', '\\')]
        if not private and mode in ('skip', 'custom'):
            expected.append('--skip-intro' if mode == 'skip' else '--custom-intro')
        passed = (actual['arguments'] == expected + literal
                  and actual['cwd'] == actual['install'] == str(game)
                  and actual['helper'] == 'owned Workshop fixture'
                  and actual['prefix'] == str(root / 'compatdata' if private else output / 'installed prefix')
                  and actual['codec'] == (str(output / 'decoder 世界') if not private and mode == 'custom' else None)
                  and not (game / 'should-not-exist').exists())
    cases.append({'name': name, 'passed': passed, 'exitCode': result.returncode, 'stderr': result.stderr})


private_script = repo / 'scripts/proton/Launch-Private.sh'
for mode in ('stock', 'patch'):
    run(f'private-custom-{mode}', private_script, ['/original/BlackOps3.exe'],
        selected_game=game, mode=mode, private=True)
for name, path in (('outside-layout', external), ('redirect-outside-private-root', redirect)):
    run('private-' + name, private_script, ['/original/BlackOps3.exe'],
        selected_game=path, accepted=False, private=True,
        refusal='The private game must be a direct folder in steamapps/common.')
installed_script = installed / 'Launch-Steam.sh'
alias_executable = alias / game.relative_to(root) / 'BlackOps3.exe'
for mode in ('stock', 'skip', 'custom'):
    (installed / 'intro-mode').write_text(mode)
    run('installed-alias-' + mode, installed_script, [str(alias_executable)], mode=mode)
(installed / 'intro-mode').write_text('stock')
for name, command in (
    ('different-executable', [str(external / 'BlackOps3.exe')]),
    ('duplicate-executable', [str(game / 'BlackOps3.exe'), str(alias_executable)]),
    ('missing-executable', []),
):
    run('installed-' + name, installed_script, command, accepted=False,
        refusal='Expected exactly one installed BlackOps3.exe in the Steam command.')
result = {'passed': all(case['passed'] for case in cases), 'cases': cases,
          'wrappers': {name: hashlib.sha256((repo / 'scripts/proton' / name).read_bytes()).hexdigest()
                       for name in ('Launch-Private.sh', 'Launch-Installed.sh')},
          'scope': 'Private Linux filesystem and command fixtures. No game launch, patch writes, or Steam changes.'}
(output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(f"{sum(case['passed'] for case in cases)}/{len(cases)} wrapper path cases passed. Results: {output / 'result.json'}")
raise SystemExit(0 if result['passed'] else 1)
