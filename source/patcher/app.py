"""Windows GUI and CLI for reversible exact-file patches."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from patcher.engine import Engine, PatchError
from patcher.plans import load
from patcher.windows import game_running, steam_installs


def resources() -> Path:
    return Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def state_directory(roots: dict[str, Path]) -> Path:
    identity = "\n".join(f"{key}:{str(value.resolve()).casefold()}" for key, value in sorted(roots.items()))
    return Path(os.environ["LOCALAPPDATA"]) / "BO3 Engine UnLimitations" / hashlib.sha256(identity.encode()).hexdigest()[:20]


def make_engine(workshop: str, game: str, state: str | None, features, resource_path: Path | None = None) -> Engine:
    roots = {}
    if workshop:
        roots["workshop"] = Path(workshop)
    if game:
        roots["game"] = Path(game)
    if not roots:
        raise PatchError("Select a full-AAE Workshop folder or a game folder.")
    return Engine(roots, Path(state) if state else state_directory(roots), features, resource_path or resources(), game_running)


def gui(version: str, features, resource_path: Path) -> None:
    import tkinter as tk
    from tkinter import filedialog, ttk
    import queue
    import threading
    window = tk.Tk()
    window.title("BO3 Engine UnLimitations")
    window.geometry("840x660")
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=f"BO3 Engine UnLimitations · {version}", font=("Segoe UI", 16)).pack(anchor="w")
    ttk.Label(frame, text="Close Black Ops III. Keep Steam downloads stopped during a file change.").pack(anchor="w", pady=(8, 2))
    ttk.Label(frame, text="These fixes still need gameplay and friend compatibility validation.").pack(anchor="w")
    installs = steam_installs()
    current = installs[0] if installs else {}
    paths = {}
    controls = []
    for key, title in (("workshop", "Full AAE folder (Workshop item 2631943123)"), ("game", "Black Ops III game folder"), ("originals", "Exact original files (optional import folder)")):
        ttk.Label(frame, text=title).pack(anchor="w", pady=(12, 2))
        row = ttk.Frame(frame)
        row.pack(fill="x")
        value = tk.StringVar(value=str(current[key]) if key in current and current[key].is_dir() else "")
        entry = ttk.Entry(row, textvariable=value)
        entry.pack(side="left", fill="x", expand=True)
        button = ttk.Button(row, text="Browse", command=lambda v=value: v.set(filedialog.askdirectory() or v.get()))
        button.pack(side="left", padx=(8, 0))
        controls.extend((entry, button))
        paths[key] = value
    selections = {}
    ttk.Label(frame, text="Patch files").pack(anchor="w", pady=(12, 2))
    for feature in features:
        value = tk.BooleanVar(value=True)
        checkbox = ttk.Checkbutton(frame, text=feature.label, variable=value)
        checkbox.pack(anchor="w")
        controls.append(checkbox)
        selections[feature.id] = value
    output = tk.Text(frame, height=12, wrap="word", font=("Consolas", 10), state="disabled")
    actions = ttk.Frame(frame)
    actions.pack(fill="x", pady=12)
    output.pack(fill="both", expand=True)
    messages = queue.Queue()
    def show(message):
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("end", message)
        output.configure(state="disabled")
    def complete():
        try:
            message = messages.get_nowait()
        except queue.Empty:
            window.after(100, complete)
            return
        for control in controls:
            control.configure(state="normal")
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        show(message)
    def perform(action):
        values = {key: value.get() for key, value in paths.items()}
        selected = [key for key, value in selections.items() if value.get()]
        for control in controls:
            control.configure(state="disabled")
        window.protocol("WM_DELETE_WINDOW", lambda: None)
        show(f"{action.capitalize()} in progress. Wait for the result.")
        def worker():
            try:
                engine = make_engine(values["workshop"], values["game"], None, features, resource_path)
                if action == "status":
                    rows = engine.status()
                    result = "\n\n".join(f"{row['label']}: {row['status']}\nOriginal backup verified: {row['originalVerified']}\n{row['path']}" for row in rows)
                else:
                    result = json.dumps(engine.run(action, selected, Path(values["originals"]) if values["originals"] else None), indent=2)
                messages.put(result + f"\n\nBackup folder: {engine.state}")
            except Exception as exc:
                messages.put(str(exc))
        threading.Thread(target=worker, daemon=True).start()
        window.after(100, complete)
    for action in ("status", "apply", "remove", "recover"):
        button = ttk.Button(actions, text=action.capitalize(), command=lambda a=action: perform(a))
        button.pack(side="left", padx=(0, 8))
        controls.append(button)
    show("Select the install folders. Status reads the files without changing them.")
    window.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("status", "apply", "remove", "recover"))
    parser.add_argument("--workshop", default="", help="Full-AAE item 2631943123 folder")
    parser.add_argument("--game", default="", help="Black Ops III game folder")
    parser.add_argument("--state", help="Backup folder outside game and Workshop")
    parser.add_argument("--originals", type=Path, help="Folder containing exact original files at manifest relative paths")
    parser.add_argument("--select", nargs="+", help="Patch file IDs. Default: every supported patch file")
    parser.add_argument("--resources", type=Path, help="Public build resources folder when running from source")
    args = parser.parse_args()
    try:
        resource_path = args.resources or resources()
        version, features = load(resource_path)
        if args.action is None:
            gui(version, features, resource_path)
        else:
            if not args.workshop and not args.game:
                installs = steam_installs()
                if len(installs) != 1:
                    raise PatchError("Select install folders explicitly with --workshop and --game.")
                args.workshop = str(installs[0]["workshop"]) if installs[0]["workshop"].is_dir() else ""
                args.game = str(installs[0]["game"]) if installs[0]["game"].is_dir() else ""
            engine = make_engine(args.workshop, args.game, args.state, features, resource_path)
            result = engine.status() if args.action == "status" else engine.run(args.action, args.select, args.originals)
            print(json.dumps({"version": version, "backupFolder": str(engine.state), "result": result}, indent=2))
        return 0
    except Exception as exc:
        if args.action is None:
            from tkinter import messagebox
            messagebox.showerror("BO3 Engine UnLimitations", str(exc))
        else:
            print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
