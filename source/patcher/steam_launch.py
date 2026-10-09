"""Reversibly configure only the selected Steam account's BO3 launch field."""
from collections.abc import Callable
import hashlib
import json
import os
from pathlib import Path

from patcher.coordination import StateLock
from patcher.payload import prepare, PAYLOAD_NAMES, supported_build
from patcher.errors import PatchError
from patcher.paths import private_path, reject_redirects
from patcher.storage import replace_bytes
from patcher.vdf_span import Block, Token, launch_field, parse, quote, tokens
from patcher.windows import game_running


def select_config(steam: Path, active_user: int | None, auto_login_name: str | None = None) -> Path:
    if active_user is not None:
        if type(active_user) is not int or not 0 < active_user < 2**32:
            raise PatchError("Steam active account identity is invalid.")
        account = active_user
    else:
        login = steam / 'config/loginusers.vdf'
        reject_redirects(login, private_files=True)
        users = parse(login.read_text(encoding='utf-8-sig')).get('users')
        if not isinstance(users, Block):
            raise PatchError("Steam login account list is missing.")
        recent = []
        for key, user in users.entries:
            if not isinstance(user, Block):
                raise PatchError("Steam login account list is invalid.")
            marker = user.get('AccountName' if auto_login_name else 'MostRecent')
            if isinstance(marker, Token) and marker.value == (auto_login_name or '1'):
                if not key.value.isdecimal():
                    raise PatchError("Steam recent account identity is invalid.")
                recent.append(int(key.value) - 76561197960265728)
        if len(recent) != 1 or not 0 < recent[0] < 2**32:
            raise PatchError("Select an unambiguous current or most-recent Steam account.")
        account = recent[0]
    config = steam / f'userdata/{account}/config/localconfig.vdf'
    reject_redirects(config, private_files=True)
    if not config.is_file():
        raise PatchError("The selected Steam account has no local configuration file.")
    return config


def _same(snapshot: dict, field) -> bool:
    return snapshot['present'] == (field.entry is not None) and snapshot['value'] == field.value


def _snapshot_valid(snapshot: dict) -> bool:
    if not isinstance(snapshot, dict) or type(snapshot.get('present')) is not bool:
        return False
    if not snapshot['present']:
        return snapshot.get('value') is None and snapshot.get('raw') is None
    if not isinstance(snapshot.get('value'), str) or not isinstance(snapshot.get('raw'), str):
        return False
    decoded = tokens(snapshot['raw'])
    return len(decoded) == 1 and decoded[0].quoted and decoded[0].start == 0 and decoded[0].end == len(snapshot['raw']) and decoded[0].value == snapshot['value']


def _inserted_valid(receipt: dict) -> bool:
    inserted = receipt['inserted']
    if receipt['original']['present']:
        return inserted == ''
    decoded = tokens(inserted)
    if len(decoded) != 2:
        return False
    key, value = decoded
    return (key.quoted and key.value == 'LaunchOptions' and value.quoted
            and value.value == receipt['installed']
            and not inserted[:key.start].strip(' \t')
            and not inserted[key.end:value.start].strip(' \t')
            and inserted[value.end:] in (' ', '\n', '\r\n'))


class SteamPlay:
    # State overrides are owned-fixture providers; GUI/CLI use the canonical private receipt folder.
    def __init__(self, steam: Path, *, active_user: int | None = None, auto_login_name: str | None = None, state: Path | None = None,
                 process_running: Callable[[str], bool] = game_running):
        self.steam = steam.resolve(strict=True)
        self.config = select_config(self.steam, active_user, auto_login_name)
        identity = hashlib.sha256(self.config.as_posix().casefold().encode()).hexdigest()[:20]
        self.state = private_path(state or Path(os.environ['LOCALAPPDATA']) / 'BO3 Engine UnLimitations/steam-play' / identity, installations=(self.steam,))
        self.process_running = process_running
        self._private_paths()

    def _private_paths(self) -> None:
        for name in ('.', 'lock', 'receipt.json'):
            private_path(self.state, name, (self.steam,))

    def _closed(self) -> None:
        if any(self.process_running(name) for name in ('steam.exe', 'BlackOps3.exe', PAYLOAD_NAMES[0])):
            raise PatchError("Close Steam, Black Ops III, and the 500K launcher before changing Steam Play.")

    def _read(self) -> bytes:
        reject_redirects(self.config, private_files=True)
        return self.config.read_bytes()

    def _save(self, receipt: dict) -> None:
        self._private_paths()
        replace_bytes(self.state / 'receipt.json', (json.dumps(receipt, indent=2) + '\n').encode())

    def _receipt(self) -> dict | None:
        path = self.state / 'receipt.json'
        if not path.exists():
            return None
        self._private_paths()
        receipt = json.loads(path.read_text(encoding='utf-8'))
        if (receipt.get('schemaVersion') != 1 or receipt.get('config') != str(self.config)
                or receipt.get('phase') not in ('enabled', 'restored', 'pending')
                or not _snapshot_valid(receipt.get('original'))
                or not isinstance(receipt.get('installed'), str)
                or not isinstance(receipt.get('inserted'), str)
                or not _inserted_valid(receipt)):
            raise PatchError("The private Steam Play receipt is invalid.")
        if receipt['phase'] == 'pending':
            pending = receipt.get('pending')
            if (not isinstance(pending, dict) or pending.get('action') not in ('enable', 'remove')
                    or pending.get('previous') not in ('enabled', 'restored')
                    or not _snapshot_valid(pending.get('before')) or not _snapshot_valid(pending.get('after'))):
                raise PatchError("The pending Steam Play receipt is invalid.")
        return receipt

    def _recover(self, receipt: dict | None) -> dict | None:
        if receipt is None or receipt['phase'] != 'pending':
            return receipt
        field = launch_field(self._read())
        pending = receipt['pending']
        if _same(pending['after'], field):
            receipt['phase'] = 'enabled' if pending['action'] == 'enable' else 'restored'
        elif _same(pending['before'], field):
            receipt['phase'] = pending['previous']
        else:
            raise PatchError("Steam launch options changed during an interrupted transaction. The receipt was retained.")
        del receipt['pending']
        self._save(receipt)
        return receipt

    def _edit(self, before: bytes, after: bytes, receipt: dict, action: str) -> None:
        previous = receipt['phase']
        receipt['phase'] = 'pending'
        receipt['pending'] = {'action': action, 'previous': previous,
                              'before': launch_field(before).snapshot(), 'after': launch_field(after).snapshot()}
        self._save(receipt)
        self._closed()
        if self._read() != before:
            raise PatchError("Steam configuration changed before replacement. Close Steam and retry.")
        replace_bytes(self.config, after)
        if self._read() != after:
            raise PatchError("Steam configuration changed after replacement. The pending receipt was retained.")
        receipt['phase'] = 'enabled' if action == 'enable' else 'restored'
        del receipt['pending']
        self._save(receipt)

    def enable(self, resources: Path, game: Path, *, tools_root: Path | None = None) -> dict:
        supported_build(resources, game)
        self._closed()
        private_path(self.state, installations=(self.steam, game.resolve(strict=True)))
        self._private_paths()
        with StateLock(self.state):
            receipt = self._recover(self._receipt())
            before = self._read()
            field = launch_field(before)
            if receipt and receipt['phase'] == 'enabled' and field.value != receipt['installed']:
                raise PatchError("Steam launch options changed after setup. Restore was refused.")
            if not receipt or receipt['phase'] != 'enabled':
                if field.value and '%command%' in field.value.casefold():
                    raise PatchError("Existing Steam launch options already contain a %command% wrapper.")
            folder = prepare(resources, game, tools_root=tools_root)
            launcher = str(folder / PAYLOAD_NAMES[0])
            original = receipt['original'] if receipt and receipt['phase'] == 'enabled' else field.snapshot()
            installed = '"' + launcher + '" %command%' + (' ' + original['value'] if original['value'] else '')
            if receipt and receipt['phase'] == 'enabled':
                if receipt['installed'] != installed:
                    raise PatchError("Restore Steam Play before enabling another launcher version.")
                return {'status': 'already-enabled', 'launcher': launcher, 'receiptFolder': str(self.state)}
            after = field.with_value(installed)
            inserted = field.insertion(quote(installed))[1] if field.entry is None else ''
            receipt = {'schemaVersion': 1, 'config': str(self.config), 'phase': 'restored',
                       'original': original, 'installed': installed, 'inserted': inserted}
            self._edit(before, after, receipt, 'enable')
            return {'status': 'enabled', 'launcher': launcher, 'receiptFolder': str(self.state)}

    def status(self, game: Path, resources: Path) -> dict:
        receipt = self._receipt()
        field = launch_field(self._read())
        try:
            build = supported_build(resources, game)
        except PatchError as error:
            support = {'gameSupported': False, 'message': str(error)}
        else:
            support = {'gameSupported': True, 'build': build['id']}
        phase = receipt['phase'] if receipt else 'restored'
        status = 'enabled' if phase == 'enabled' and field.value == receipt['installed'] else phase
        if phase == 'enabled' and field.value != receipt['installed']:
            status = 'externally-changed'
        return {'status': status, 'receiptFolder': str(self.state), **support}

    def remove(self) -> dict:
        self._private_paths()
        receipt = self._receipt()
        if receipt is None or receipt['phase'] == 'restored':
            return {'status': 'already-restored', 'receiptFolder': str(self.state)}
        self._closed()
        self._private_paths()
        with StateLock(self.state):
            receipt = self._recover(self._receipt())
            if receipt is None or receipt['phase'] == 'restored':
                return {'status': 'already-restored', 'receiptFolder': str(self.state)}
            before = self._read()
            field = launch_field(before)
            if field.value != receipt['installed']:
                raise PatchError("Steam launch options changed after setup. Restore was refused.")
            original = receipt['original']
            after = field.with_raw(original['raw']) if original['present'] else field.without(receipt['inserted'])
            self._edit(before, after, receipt, 'remove')
            return {'status': 'restored', 'receiptFolder': str(self.state)}
