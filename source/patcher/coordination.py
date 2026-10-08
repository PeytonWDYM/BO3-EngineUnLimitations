"""Per-target admission and durable ownership shared by every backup folder."""
from contextlib import AbstractContextManager, ExitStack
import hashlib
import json
import os
from pathlib import Path
import re

from patcher.errors import PatchError
from patcher.paths import private_path, reject_redirects
from patcher.storage import replace_bytes


def canonical(target: Path) -> str:
    return target.resolve(strict=True).as_posix().casefold()


class StateLock(AbstractContextManager):
    def __init__(self, directory: Path):
        reject_redirects(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = private_path(directory, "lock")
        self.file = path.open("a+b")
        if self.file.seek(0, 2) == 0:
            self.file.write(b"\0")
            self.file.flush()
        self.file.seek(0)

    def __enter__(self):
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise PatchError("Another patcher uses an overlapping installation target.") from exc
        return self

    def __exit__(self, *_):
        self.file.close()


class Coordinator:
    def __init__(self, root: Path, installations):
        self.root = private_path(root, installations=installations)
        self.installations = installations

    def path(self, relative: str) -> Path:
        return private_path(self.root, relative, self.installations)

    def locks(self, targets: list[Path]) -> ExitStack:
        stack = ExitStack()
        try:
            for target in sorted({canonical(path) for path in targets}):
                identity = hashlib.sha256(target.encode()).hexdigest()
                stack.enter_context(StateLock(self.path("locks/" + identity)))
        except Exception:
            stack.close()
            raise
        return stack

    def receipt_path(self, transaction: str) -> Path:
        if not re.fullmatch(r"txn-[0-9a-f]{32}", transaction):
            raise PatchError("The transaction identity is invalid.")
        return self.path("active/" + transaction + ".json")

    def read(self, path: Path) -> dict:
        private_path(self.root, str(path.relative_to(self.root)), self.installations)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != 1 or data.get("phase") not in {"pending", "committed", "rolled-back"} or not isinstance(data.get("targets"), list):
            raise PatchError("A shared transaction receipt has an invalid format.")
        if self.receipt_path(data["transaction"]) != path:
            raise PatchError("A shared transaction receipt has an invalid identity.")
        return data

    def available(self, targets: list[Path], owner: tuple[str, str] | None = None) -> None:
        requested = {canonical(target) for target in targets}
        active = self.path("active")
        if not active.exists():
            return
        for path in active.glob("txn-*.json"):
            try:
                receipt = self.read(path)
            except FileNotFoundError:
                continue  # A disjoint completed transaction can remove its receipt during this scan.
            if receipt["phase"] == "pending" and requested.intersection(receipt["targets"]):
                if owner != (receipt["transaction"], receipt["state"]):
                    raise PatchError(f"An interrupted transaction owns this target. Run recovery with --state {receipt['state']}")

    def claim(self, transaction: str, state: Path, targets: list[Path]) -> dict:
        self.available(targets)
        receipt = {"schema": 1, "transaction": transaction, "state": str(state), "phase": "pending", "targets": sorted(canonical(target) for target in targets)}
        path = self.receipt_path(transaction)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise PatchError("This transaction already has a shared receipt.")
        replace_bytes(path, (json.dumps(receipt, indent=2) + "\n").encode())
        return receipt

    def finish(self, receipt: dict, phase: str) -> None:
        updated = {**receipt, "phase": phase}
        replace_bytes(self.receipt_path(receipt["transaction"]), (json.dumps(updated, indent=2) + "\n").encode())

    def remove(self, transaction: str) -> None:
        self.receipt_path(transaction).unlink(missing_ok=True)

    def cleanup_completed(self, state: Path) -> None:
        active = self.path("active")
        if not active.exists():
            return
        for path in active.glob("txn-*.json"):
            try:
                receipt = self.read(path)
            except FileNotFoundError:
                continue
            if receipt["state"] == str(state) and receipt["phase"] != "pending":
                self.remove(receipt["transaction"])
