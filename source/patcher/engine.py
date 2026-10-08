"""Durable transactions over user-supplied files. Never copy patched bytes as stock."""

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Callable
import uuid

from patcher.coordination import Coordinator, StateLock, canonical
from patcher.errors import PatchError
from patcher.paths import check_state, private_path
from patcher.storage import durable_write, replace_bytes


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Feature:
    id: str
    label: str
    scope: str
    relative_path: str
    original_sha256: str
    patched_sha256: str
    transform: Callable[[bytes, Path], bytes]
    admitted_sha256: tuple[str, ...] = field(default_factory=tuple)

    @property
    def supported(self) -> set[str]:
        return {self.original_sha256, self.patched_sha256, *self.admitted_sha256}


class Engine:
    def __init__(self, roots: dict[str, Path], state: Path, features: list[Feature], resources: Path, running: Callable[[], bool], *, coordination_root: Path | None = None):
        self.roots = {key: value.resolve(strict=True) for key, value in roots.items()}
        self.state = Path(os.path.abspath(state))
        check_state(self.state, self.roots.values())
        self.features = list(features)
        self.resources = resources
        self.running = running
        ids = [feature.id for feature in features]
        if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[a-z][a-z0-9_-]*", item) for item in ids):
            raise PatchError("The patch manifest has invalid file identities.")
        for feature in features:
            if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in feature.supported):
                raise PatchError("The patch manifest has invalid file hashes.")
        # The production registry is fixed across --state, selected roots, and feature subsets.
        registry = coordination_root or Path(os.environ["LOCALAPPDATA"]) / "BO3 Engine UnLimitations" / "target-coordination"
        self.coordinator = Coordinator(registry, tuple(self.roots.values()))

    def target(self, feature: Feature) -> Path:
        if feature.scope not in self.roots:
            raise PatchError(f"Select the {feature.scope} folder for {feature.label}.")
        relative = Path(feature.relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise PatchError("The patch manifest contains an unsafe target path.")
        root = self.roots[feature.scope]
        path = (root / relative).resolve(strict=True)
        if root not in path.parents or not path.is_file():
            raise PatchError("A patch target is outside its selected folder.")
        return path

    def closed(self) -> None:
        if self.running():
            raise PatchError("Close Black Ops III before apply, removal, or recovery.")

    def original_path(self, feature: Feature) -> Path:
        return private_path(self.state, "originals/" + feature.id + ".bin", self.roots.values())

    def original(self, feature: Feature, current: bytes, originals: Path | None) -> bytes:
        backup = self.original_path(feature)
        if backup.exists():
            data = backup.read_bytes()
        elif digest(current) == feature.original_sha256:
            data = current
        elif originals is not None:
            supplied = (originals / feature.relative_path).resolve(strict=True)
            if originals.resolve() not in supplied.parents:
                raise PatchError("An imported original is outside its selected folder.")
            data = supplied.read_bytes()
        else:
            raise PatchError(f"{feature.label} already contains a patch. Select exact originals before apply or removal.")
        if digest(data) != feature.original_sha256:
            raise PatchError(f"The original backup for {feature.label} has an unsupported hash.")
        return data

    def status(self) -> list[dict[str, str | bool]]:
        rows = []
        for feature in self.features:
            target = self.target(feature)
            current = digest(target.read_bytes())
            state = "stock" if current == feature.original_sha256 else "patched" if current == feature.patched_sha256 else "previous patch" if current in feature.admitted_sha256 else "unsupported"
            original = self.original_path(feature)
            rows.append({"id": feature.id, "label": feature.label, "path": str(target), "sha256": current, "status": state, "originalVerified": original.exists() and digest(original.read_bytes()) == feature.original_sha256})
        return rows

    def save_journal(self, journal: dict) -> None:
        data = (json.dumps(journal, indent=2) + "\n").encode()
        replace_bytes(private_path(self.state, "journal.json", self.roots.values()), data)

    def recovery_entries(self, journal: dict) -> list[tuple[Path, bytes, str, str]]:
        if journal.get("schema") != 2 or not re.fullmatch(r"txn-[0-9a-f]{32}", journal.get("transaction", "")):
            raise PatchError("The recovery journal has an unsupported format.")
        by_id = {feature.id: feature for feature in self.features}
        entries = []
        seen = set()
        transaction = private_path(self.state, journal["transaction"], self.roots.values())
        for entry in journal["entries"]:
            identity = entry["id"]
            if identity in seen or identity not in by_id:
                raise PatchError("The recovery journal has an invalid file identity.")
            seen.add(identity)
            feature = by_id[identity]
            target = self.target(feature)
            if str(target) != entry["target"] or entry["beforeSha256"] not in feature.supported or entry["afterSha256"] not in feature.supported:
                raise PatchError("The recovery journal differs from this installation or patch version.")
            before = private_path(transaction, identity + ".before", self.roots.values()).read_bytes()
            after = private_path(transaction, identity + ".after", self.roots.values()).read_bytes()
            if digest(before) != entry["beforeSha256"] or digest(after) != entry["afterSha256"]:
                raise PatchError("A recovery snapshot has an invalid hash.")
            entries.append((target, before, entry["beforeSha256"], entry["afterSha256"]))
        return entries

    def recover(self, allow_external: bool = False) -> None:
        check_state(self.state, self.roots.values())
        journal_path = private_path(self.state, "journal.json", self.roots.values())
        if not journal_path.exists():
            return
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        entries = self.recovery_entries(journal)
        admitted = journal["admitted"]
        if not isinstance(admitted, list) or len(admitted) != len(set(admitted)) or not set(admitted) <= {entry["id"] for entry in journal["entries"]}:
            raise PatchError("The journal has an invalid write-admission list.")
        targets = [entry[0] for entry in entries]
        receipt_path = self.coordinator.receipt_path(journal["transaction"])
        if not receipt_path.exists():
            if admitted:
                raise PatchError("The shared receipt is missing after write admission. Preserve the journal and backups for inspection.")
            # An empty admission list proves this journal did not admit a target replacement.
            journal_path.unlink()
            return
        receipt = self.coordinator.read(receipt_path)
        if receipt["state"] != str(self.state) or receipt["targets"] != sorted(canonical(target) for target in targets):
            raise PatchError("The shared transaction receipt differs from the recovery journal.")
        self.coordinator.available(targets, (journal["transaction"], str(self.state)))
        if receipt["phase"] != "pending":
            journal_path.unlink()
            self.coordinator.remove(journal["transaction"])
            return
        admitted_paths = {Path(entry["target"]) for entry in journal["entries"] if entry["id"] in admitted}
        external = []
        for target, _, before, after in entries:
            current = digest(target.read_bytes())
            if current not in {before, after} or (before != after and target not in admitted_paths and current != before):
                external.append(target)
        if external and not allow_external:
            raise PatchError("Recovery found an externally changed target. Preserve the backups and restore that file before recovery.")
        for target, data, before, after in reversed(entries):
            self.closed()
            current = digest(target.read_bytes())
            if current == after and current != before and target in admitted_paths:
                replace_bytes(target, data)
            elif current != before and target not in external:
                raise PatchError("A target changed during recovery. The journal remains available.")
        if external:
            raise PatchError("Owned changes were restored. An externally changed target still blocks recovery.")
        self.closed()
        if any(digest(target.read_bytes()) != before for target, _, before, _ in entries):
            raise PatchError("A target changed before recovery completed. The journal remains available.")
        self.coordinator.finish(receipt, "rolled-back")
        journal_path.unlink()
        self.coordinator.remove(journal["transaction"])

    def run(self, action: str, selected: list[str] | None = None, originals: Path | None = None) -> dict:
        if action not in {"apply", "remove", "recover"}:
            raise PatchError("Choose apply, remove, or recover.")
        self.closed()
        check_state(self.state, self.roots.values())
        with StateLock(self.state):
            self.closed()
            if action == "recover":
                path = private_path(self.state, "journal.json", self.roots.values())
                if not path.exists():
                    targets = [self.target(feature) for feature in self.features if feature.scope in self.roots]
                    with self.coordinator.locks(targets):
                        self.coordinator.available(targets)
                        self.coordinator.cleanup_completed(self.state)
                    return {"action": action, "status": "complete"}
                journal = json.loads(path.read_text(encoding="utf-8"))
                targets = [entry[0] for entry in self.recovery_entries(journal)]
                with self.coordinator.locks(targets):
                    self.recover()
                    return {"action": action, "status": "complete"}
            if (self.state / "journal.json").exists():
                raise PatchError("An interrupted transaction needs recovery before another change.")
            requested = set(selected) if selected is not None else {feature.id for feature in self.features}
            if not requested or not requested <= {feature.id for feature in self.features}:
                raise PatchError("Select at least one supported patch file.")
            targets = [self.target(feature) for feature in self.features if feature.id in requested]
            if len(targets) != len({canonical(target) for target in targets}):
                raise PatchError("The manifest selects the same target more than once.")
            with self.coordinator.locks(targets):
                self.coordinator.available(targets)
                return self.apply_or_remove(action, requested, originals)

    def apply_or_remove(self, action: str, requested: set[str], originals: Path | None) -> dict:
        prepared = []
        for feature in self.features:
            if feature.id not in requested:
                continue
            target = self.target(feature)
            current = target.read_bytes()
            current_hash = digest(current)
            if current_hash not in feature.supported:
                raise PatchError(f"{feature.label} has an unsupported hash. No target files changed.")
            stock = self.original(feature, current, originals)
            desired = feature.transform(stock, self.resources) if action == "apply" and current_hash != feature.patched_sha256 else current if action == "apply" else stock
            desired_hash = feature.patched_sha256 if action == "apply" else feature.original_sha256
            if digest(desired) != desired_hash:
                raise PatchError(f"The prepared result for {feature.label} has an unexpected hash.")
            prepared.append((feature, target, current, desired, stock))
        # Admission and transformation finish for every selected file before backups or target writes.
        check_state(self.state, self.roots.values())
        private_path(self.state, "originals", self.roots.values()).mkdir(exist_ok=True)
        for feature, _, _, _, stock in prepared:
            backup = self.original_path(feature)
            if not backup.exists():
                replace_bytes(backup, stock)
        changed = [row for row in prepared if row[2] != row[3]]
        if not changed:
            return {"action": action, "status": "already complete", "files": sorted(requested)}
        transaction = private_path(self.state, "txn-" + uuid.uuid4().hex, self.roots.values())
        transaction.mkdir()
        entries = []
        for feature, target, current, desired, _ in prepared:
            durable_write(private_path(transaction, feature.id + ".before", self.roots.values()), current)
            durable_write(private_path(transaction, feature.id + ".after", self.roots.values()), desired)
            entries.append({"id": feature.id, "target": str(target), "beforeSha256": digest(current), "afterSha256": digest(desired)})
        journal = {"schema": 2, "action": action, "transaction": transaction.name, "entries": entries, "admitted": []}
        self.save_journal(journal)
        receipt = self.coordinator.claim(transaction.name, self.state, [row[1] for row in prepared])
        committed = False
        try:
            for feature, target, current, desired, _ in changed:
                self.closed()
                if target.read_bytes() != current:
                    raise PatchError(f"{feature.label} changed after preparation.")
                journal["admitted"].append(feature.id)
                self.save_journal(journal)
                replace_bytes(target, desired)
                if digest(target.read_bytes()) != digest(desired):
                    raise PatchError(f"{feature.label} failed its installed hash check.")
            self.closed()
            for _, target, _, desired, _ in prepared:
                if target.read_bytes() != desired:
                    raise PatchError("A target changed before the transaction completed.")
            self.coordinator.finish(receipt, "committed")
            committed = True
            private_path(self.state, "journal.json", self.roots.values()).unlink()
            self.coordinator.remove(transaction.name)
        except Exception as exc:
            if committed:
                raise PatchError(f"Patch files are committed. Metadata cleanup stopped: {exc}. Run Recover with this backup folder.") from exc
            try:
                self.recover(allow_external=True)
            except Exception as recovery_error:
                raise PatchError(f"The transaction stopped: {exc}. Recovery needs attention: {recovery_error}") from exc
            raise PatchError(f"The transaction stopped and restored its files: {exc}") from exc
        return {"action": action, "status": "complete", "files": [row[0].id for row in changed]}
