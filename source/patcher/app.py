"""Install and remove the 500K launch route. No action starts the game."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patcher.errors import PatchError
from patcher.steam_launch import SteamPlay
from patcher.windows import steam_context, steam_installs

VERSION = '0.2.0-test.1'
NOTICE = ('500,000 server script slots for Zombies. This is a test release. '
          'Multiplayer and host migration need validation. Proton is not supported yet.')


def resources() -> Path:
    return Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]


def manager(steam: Path | None, account: int | None, state: Path | None) -> SteamPlay:
    context = steam_context() if steam is None else None
    return SteamPlay(steam or context.directory, active_user=account if account is not None else context.active_user if context else None,
                     auto_login_name=context.auto_login_name if context else None, state=state)


def action(name: str, steam: SteamPlay, game: Path | None) -> dict:
    if name == 'remove':
        return steam.remove()
    if game is None:
        raise PatchError('Select the Black Ops III game folder.')
    if name == 'install':
        return steam.enable(resources(), game)
    return steam.status(game, resources())


def gui() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    root = tk.Tk()
    root.title('BO3 500K')
    root.geometry('620x320')
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='BO3 500K Zombies', font=('Segoe UI', 18)).pack(anchor='w')
    ttk.Label(frame, text=NOTICE, wraplength=570).pack(anchor='w', pady=(8, 12))
    installs = steam_installs()
    folder = tk.StringVar(value=str(installs[0]) if installs else '')
    row = ttk.Frame(frame)
    row.pack(fill='x')
    ttk.Entry(row, textvariable=folder, width=66).pack(side='left', fill='x', expand=True)
    ttk.Button(row, text='Browse', command=lambda: folder.set(filedialog.askdirectory() or folder.get())).pack(side='left', padx=(8, 0))
    status = tk.StringVar(value='Close Steam and the game before Install or Remove.')
    ttk.Label(frame, textvariable=status, wraplength=570).pack(anchor='w', pady=12)

    def clicked(name: str) -> None:
        try:
            status.set('Checking files...')
            root.update_idletasks()
            result = action(name, manager(None, None, None), Path(folder.get()) if folder.get() else None)
            text = result.get('message') or {
                'enabled': 'Installed. Open Steam and select Play. Keep the launcher window open.',
                'already-enabled': 'Already installed. Open Steam and select Play.',
                'restored': 'Removed. Steam Play now uses the previous launch options.',
                'already-restored': 'The 500K launch route is not installed.',
                'externally-changed': 'Steam launch options changed outside the installer.',
                'pending': 'An interrupted setup exists. Close Steam and select Remove.',
            }[result['status']]
            status.set(text)
        except (PatchError, OSError, ValueError, KeyError) as error:
            status.set(str(error))
            messagebox.showerror('BO3 500K', str(error))

    buttons = ttk.Frame(frame)
    buttons.pack(anchor='w')
    for name in ('install', 'remove', 'status'):
        ttk.Button(buttons, text=name.title(), command=lambda value=name: clicked(value)).pack(side='left', padx=(0, 8))
    root.mainloop()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('action', nargs='?', choices=('install', 'remove', 'status'))
    parser.add_argument('--game', type=Path, help='Black Ops III game folder')
    parser.add_argument('--steam', type=Path, help='Steam installation folder')
    parser.add_argument('--steam-user', type=int, help='Steam account ID')
    parser.add_argument('--state', type=Path, help='Private setup receipt folder')
    args = parser.parse_args()
    if os.name != 'nt':
        raise PatchError('Proton support needs a verified process-freeze backend. This release requires Windows x64.')
    if hasattr(ctypes.WinDLL('ntdll'), 'wine_get_version'):
        raise PatchError('This release does not support Proton or Wine. The required job-freeze backend is unavailable.')
    if args.action is None:
        return gui()
    print(json.dumps(action(args.action, manager(args.steam, args.steam_user, args.state), args.game), indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (PatchError, OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
