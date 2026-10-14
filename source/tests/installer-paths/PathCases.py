"""Exercise discovery and app actions against private Windows installer files."""
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from patcher import app
from patcher.errors import PatchError
from patcher.steam_launch import SteamPlay
from patcher.vdf_span import quote
from patcher.windows import SteamContext, steam_installs


def run_path_cases(output: Path, resources: Path, *, skip_gui_tests: bool = False) -> list[dict]:
    root = output.resolve(strict=True) / 'installer-paths'
    root.mkdir()
    cases = []

    def record(name: str, **evidence) -> None:
        cases.append({'name': name, 'passed': True, **evidence})

    def game_at(path: Path) -> Path:
        path.mkdir(parents=True)
        (path / 'BlackOps3.exe').write_bytes(b'Owned game 1')
        return path

    def library_file(steam: Path, text: str) -> None:
        folder = steam / 'steamapps'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'libraryfolders.vdf').write_text(text, encoding='utf-8')

    def discover(steam: Path) -> list[Path]:
        with patch('patcher.windows.steam_context', return_value=SteamContext(steam, 42, None)):
            return steam_installs()

    script = root / 'Create-Junction.ps1'
    script.write_text('param([string]$Link, [string]$Target)\n'
                      '$ErrorActionPreference = "Stop"\n'
                      'New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null\n', encoding='utf-8')

    def junction_at(link: Path, target: Path) -> None:
        subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-File', str(script),
                        '-Link', str(link), '-Target', str(target)], check=True, capture_output=True, text=True)

    steam = root / 'Steam owned'
    library = root / 'Library café 漢字'
    game = game_at(library / 'steamapps/common/Custom BO3 café 漢字')
    (library / 'steamapps/appmanifest_311210.acf').write_text(
        '"AppState" { "appid" "311210" "installdir" "Custom BO3 café 漢字" }', encoding='utf-8')
    library_file(steam, f'"libraryfolders" {{ "0" {{ "path" {quote(str(steam))} }} '
                        f'"1" {{ "path" {quote(str(library))} }} }}')
    assert discover(steam) == [game]
    record('secondary-library-custom-unicode', selected=str(game))

    legacy = root / 'Legacy library'
    legacy_game = game_at(legacy / 'steamapps/common/Call of Duty Black Ops III')
    library_file(steam, f'"LibraryFolders" {{ "1" {quote(str(legacy))} }}')
    assert discover(steam) == [legacy_game]
    record('legacy-library', selected=str(legacy_game))

    empty = root / 'Empty library'
    (empty / 'steamapps/common/Call of Duty Black Ops III').mkdir(parents=True)
    library_file(steam, f'"libraryfolders" {{ // "path" {quote(str(legacy))}\n'
                        f'"1" {{ "path" {quote(str(empty))} }} }}')
    assert discover(steam) == []
    record('comments-and-empty-directory')

    (library / 'steamapps/appmanifest_311210.acf').write_text(
        '"AppState" { "appid" "311210" "installdir" "../outside" }', encoding='utf-8')
    library_file(steam, f'"libraryfolders" {{ "1" {{ "path" {quote(str(library))} }} }}')
    before = (steam / 'steamapps/libraryfolders.vdf').read_bytes()
    try:
        discover(steam)
    except PatchError:
        pass
    else:
        raise AssertionError('Discovery admitted an installdir outside steamapps/common')
    assert (steam / 'steamapps/libraryfolders.vdf').read_bytes() == before
    record('manifest-traversal-refused')

    for index, rooted in enumerate(('/', '\\')):
        (library / 'steamapps/appmanifest_311210.acf').write_text(
            f'"AppState" {{ "appid" "311210" "installdir" {quote(rooted)} }}', encoding='utf-8')
        try:
            discover(steam)
        except PatchError:
            pass
        else:
            raise AssertionError('Discovery admitted a rooted installdir')
        record(f'manifest-root-{index}-refused')

    junction = root / 'Library junction'
    junction_at(junction, legacy)
    library_file(steam, f'"libraryfolders" {{ "0" {{ "path" {quote(str(legacy))} }} '
                        f'"1" {{ "path" {quote(str(junction))} }} }}')
    assert len(discover(steam)) == 1
    assert discover(steam)[0].resolve() == legacy_game.resolve()
    record('junction-library-deduplicated', selected=str(discover(steam)[0]))

    def fixture(name: str) -> tuple[SteamPlay, Path, Path, bytes]:
        folder = root / name
        config = folder / 'Steam café 漢字/userdata/42/config/localconfig.vdf'
        config.parent.mkdir(parents=True)
        original = ('"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { '
                    '"apps" { "311210" { "LaunchOptions" "+set owned 1" } } } } } }').encode()
        config.write_bytes(original)
        game = game_at(folder / 'Custom game café 漢字')
        manager = SteamPlay(config.parents[3], active_user=42, state=folder / 'State café 漢字',
                            process_running=lambda _: False)
        return manager, game, folder / 'Tools café 漢字', original

    manager, game, tools, original = fixture('cli-auto-game')
    with patch('patcher.app.steam_installs', return_value=[game]), \
            patch('patcher.app.resources', return_value=resources), \
            patch.dict('os.environ', {'LOCALAPPDATA': str(tools)}):
        assert app.action('install', manager, None)['status'] == 'enabled'
        assert app.action('remove', manager, None)['status'] == 'restored'
    assert manager.config.read_bytes() == original
    record('cli-auto-game', config=str(manager.config))

    manager, game, tools, original = fixture('cli-ambiguous-game')
    with patch('patcher.app.steam_installs', return_value=[game, legacy_game]), \
            patch('patcher.app.resources', return_value=resources), \
            patch.dict('os.environ', {'LOCALAPPDATA': str(tools)}):
        try:
            app.action('install', manager, None)
        except PatchError:
            pass
        else:
            raise AssertionError('Install selected one of multiple games without --game')
    assert not manager.state.exists()
    assert not tools.exists()
    assert manager.config.read_bytes() == original
    record('cli-ambiguous-game-refused', config=str(manager.config))

    manager, game, tools, original = fixture('explicit-unicode-game')
    manager.enable(resources, game, tools_root=tools)
    assert manager.status(game, resources)['status'] == 'enabled'
    assert str(tools) in manager.config.read_text(encoding='utf-8').replace('\\\\', '\\')
    manager.remove()
    assert manager.config.read_bytes() == original
    assert (game / 'BlackOps3.exe').read_bytes() == b'Owned game 1'
    record('explicit-unicode-paths', config=str(manager.config), game=str(game))

    manager, game, tools, original = fixture('game-folder-junction')
    alias = game.parent / 'Game junction'
    junction_at(alias, game)
    manager.enable(resources, alias, tools_root=tools)
    manager.remove()
    assert manager.config.read_bytes() == original
    for name, private in [('payload-inside-game', game / 'unsafe-tools'),
                          ('payload-through-junction', alias.parent / 'Tools junction')]:
        if name == 'payload-through-junction':
            junction_at(private, tools)
        try:
            manager.enable(resources, alias, tools_root=private)
        except PatchError:
            pass
        else:
            raise AssertionError(f'Install admitted {name}')
        assert manager.config.read_bytes() == original
        assert not (game / 'unsafe-tools').exists()
        record(name + '-refused', config=str(manager.config))
    (game / 'BlackOps3.exe').write_bytes(b'Unknown game through junction')
    try:
        manager.enable(resources, alias, tools_root=tools)
    except PatchError:
        pass
    else:
        raise AssertionError('Install admitted an unknown executable through a junction')
    assert manager.config.read_bytes() == original
    record('game-folder-junction-identity', game=str(alias), config=str(manager.config))

    if not skip_gui_tests:
        manager, game, tools, original = fixture('gui-explicit-options')
        run_gui_case(manager, game, tools, original, resources)
        record('gui-explicit-options-install-remove', config=str(manager.config), game=str(game))

    (root / 'result.json').write_text(json.dumps({'passed': True, 'cases': cases,
        'guiCases': 'not run: explicitly skipped' if skip_gui_tests else 'executed',
        'scope': 'Private Windows Steam files and app actions. No Steam or game launch.'}, indent=2), encoding='utf-8')
    return cases


def run_gui_case(manager: SteamPlay, game: Path, tools: Path, original: bytes, resources: Path) -> None:
    import tkinter as tk
    from tkinter import ttk

    window = tk.Tk()
    window.withdraw()

    def controls(widget):
        for child in widget.winfo_children():
            yield child
            yield from controls(child)

    def gui_actions() -> None:
        widgets = list(controls(window))
        entry = next(child for child in widgets if isinstance(child, ttk.Entry))
        assert Path(entry.get()) == game
        buttons = {child.cget('text'): child for child in widgets if isinstance(child, ttk.Button)}
        buttons['Install'].invoke()
        assert manager.status(game, resources)['status'] == 'enabled'
        buttons['Remove'].invoke()
        assert manager.config.read_bytes() == original
        assert (game / 'BlackOps3.exe').read_bytes() == b'Owned game 1'

    def owned_manager(steam, *, active_user, auto_login_name, state):
        return SteamPlay(steam, active_user=active_user, auto_login_name=auto_login_name,
                         state=state, process_running=lambda _: False)

    def gui_error(title, message) -> None:
        raise AssertionError(f'{title}: {message}')

    try:
        with patch.object(sys, 'argv', ['BO3-500K-Setup', '--game', str(game), '--steam', str(manager.steam),
                                       '--steam-user', '42', '--state', str(manager.state)]), \
                patch('tkinter.Tk', return_value=window), \
                patch.object(window, 'mainloop', side_effect=gui_actions), \
                patch('tkinter.messagebox.showerror', side_effect=gui_error), \
                patch('patcher.app.SteamPlay', side_effect=owned_manager), \
                patch('patcher.app.resources', return_value=resources), \
                patch.dict('os.environ', {'LOCALAPPDATA': str(tools)}):
            assert app.main() == 0
    finally:
        window.destroy()
