"""Exercise complete Steam transactions with owned files and save repeatable evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patcher.errors import PatchError
from patcher.steam_launch import SteamPlay
from patcher.payload import PAYLOAD_NAMES, supported_build
from patcher.vdf_span import launch_field


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    resources = output / 'bundle'
    resources.mkdir()
    builds = []
    for index in (1, 2):
        folder = resources / 'native' / f'owned-{index}'
        folder.mkdir(parents=True)
        hashes = {}
        for name in PAYLOAD_NAMES:
            data = f'Owned non-executable payload {index}: {name}'.encode()
            (folder / name).write_bytes(data)
            hashes[name] = digest(data)
        builds.append({'id': f'owned-{index}', 'gameSha256': digest(f'Owned game {index}'.encode()),
                       'runtime': 'windows', 'files': hashes})
    (resources / 'release.json').write_text(json.dumps({'schemaVersion': 1, 'version': 'owned', 'builds': builds}))
    cases = []

    def fixture(name: str, original: str = '') -> tuple[SteamPlay, Path, Path, bytes]:
        root = output / name
        steam = root / 'steam'
        config = steam / 'userdata/42/config/localconfig.vdf'
        config.parent.mkdir(parents=True)
        field = f'"LaunchOptions" "{original}"' if original else ''
        raw = ('// retained comment\r\n"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { '
               '"apps" { "311210" { ' + field + ' "Other" "keep" } "7" { "LaunchOptions" "other game" } } '
               '} } } "Unrelated" "retain" }\r\n').encode()
        config.write_bytes(raw)
        game = root / 'game'
        game.mkdir()
        (game / 'BlackOps3.exe').write_bytes(b'Owned game 1')
        manager = SteamPlay(steam, active_user=42, state=root / 'state', process_running=lambda _: False)
        return manager, game, root / 'tools', raw

    def record(name: str, manager: SteamPlay, original: bytes) -> None:
        cases.append({'name': name, 'passed': True, 'beforeSha256': digest(original),
                      'afterSha256': digest(manager.config.read_bytes()), 'config': str(manager.config)})

    for name, arguments in [('absent-field', ''), ('existing-arguments', '+set test 1')]:
        manager, game, tools, original = fixture(name, arguments)
        manager.enable(resources, game, tools_root=tools)
        assert manager.status(game, resources)['status'] == 'enabled'
        assert '+set test 1' in manager.config.read_text() if arguments else '%command%' in manager.config.read_text()
        manager.remove()
        assert manager.config.read_bytes() == original
        assert (game / 'BlackOps3.exe').read_bytes() == b'Owned game 1'
        record(name, manager, original)

    for name in ('unknown-version', 'damaged-payload', 'active-process', 'existing-wrapper', 'overlapping-state'):
        manager, game, tools, original = fixture(name, '%command%' if name == 'existing-wrapper' else '')
        bundle = resources
        if name == 'unknown-version':
            (game / 'BlackOps3.exe').write_bytes(b'Unknown updated executable')
        if name == 'active-process':
            manager.process_running = lambda _: True
        if name == 'overlapping-state':
            manager.state = game / 'unsafe-state'
        if name == 'damaged-payload':
            import shutil
            bundle = output / 'damaged-bundle'
            shutil.copytree(resources, bundle)
            (bundle / 'native/owned-1/Bo3EnhancedHelper.dll').write_bytes(b'Damaged')
        try:
            manager.enable(bundle, game, tools_root=tools)
        except PatchError:
            pass
        else:
            raise AssertionError(f'Admission did not refuse {name}')
        assert manager.config.read_bytes() == original
        assert not tools.exists()
        record(name, manager, original)

    manager, game, tools, original = fixture('updated-supported-version')
    (game / 'BlackOps3.exe').write_bytes(b'Owned game 2')
    assert supported_build(resources, game)['id'] == 'owned-2'
    manager.enable(resources, game, tools_root=tools)
    assert 'owned-2' in manager.config.read_text()
    manager.remove()
    assert manager.config.read_bytes() == original
    record('updated-supported-version', manager, original)

    manager, game, tools, original = fixture('changed-launch-field')
    manager.enable(resources, game, tools_root=tools)
    changed = manager.config.read_bytes().replace(b'%command%', b'%command% +changed')
    manager.config.write_bytes(changed)
    try:
        manager.remove()
    except PatchError:
        pass
    else:
        raise AssertionError('Removal replaced an external edit')
    assert manager.config.read_bytes() == changed
    record('changed-launch-field', manager, original)

    manager, game, tools, original = fixture('interrupted-enable')
    manager.enable(resources, game, tools_root=tools)
    receipt = manager._receipt()
    after = launch_field(manager.config.read_bytes()).snapshot()
    receipt['phase'] = 'pending'
    receipt['pending'] = {'action': 'enable', 'previous': 'restored', 'before': receipt['original'], 'after': after}
    manager._save(receipt)
    manager.remove()
    assert manager.config.read_bytes() == original
    record('interrupted-enable', manager, original)

    manager, game, tools, original = fixture('updated-game-status')
    manager.enable(resources, game, tools_root=tools)
    (game / 'BlackOps3.exe').write_bytes(b'Unknown updated executable')
    assert manager.status(game, resources)['gameSupported'] is False
    manager.remove()
    assert manager.config.read_bytes() == original
    record('updated-game-status', manager, original)

    (output / 'result.json').write_text(json.dumps({'passed': True, 'cases': cases,
        'scope': 'Owned Steam configuration and payload files. No Steam or game launch.'}, indent=2) + '\n')
    print(f'{len(cases)} installer E2E cases passed. Evidence: {output / "result.json"}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
