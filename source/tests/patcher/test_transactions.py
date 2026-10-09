"""Owned-file E2E tests. No game or mod assets are needed."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import shutil
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from patcher.engine import Engine, Feature, PatchError


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixtures(root):
    root.mkdir(exist_ok=True)
    for name, content in {"first.ff": b"first original", "second.ff": b"second original", "save.bin": b"save", "settings.ini": b"settings"}.items():
        (root / name).write_bytes(content)


def features():
    return [Feature(name, name, "workshop", name + ".ff", digest((name + " original").encode()), digest((name + " patched").encode()), lambda data, resources, n=name: (n + " patched").encode()) for name in ("first", "second")]


class Transactions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "install"
        fixtures(self.root)
        self.engine = Engine({"workshop": self.root}, self.base / "state", features(), self.base, lambda: False, coordination_root=self.base / "coordination")

    def tearDown(self):
        self.temp.cleanup()

    def original(self):
        for name in ("first", "second"):
            self.assertEqual((self.root / (name + ".ff")).read_bytes(), (name + " original").encode())

    def test_apply_remove_preserves_unrelated(self):
        self.engine.run("apply")
        self.assertEqual([x["status"] for x in self.engine.status()], ["patched", "patched"])
        self.assertEqual((self.root / "save.bin").read_bytes(), b"save")
        self.assertEqual((self.root / "settings.ini").read_bytes(), b"settings")
        self.engine.run("remove")
        self.original()

    def test_unsupported_pair_and_bad_transform(self):
        (self.root / "second.ff").write_bytes(b"unsupported")
        with self.assertRaises(PatchError):
            self.engine.run("apply")
        self.assertEqual((self.root / "first.ff").read_bytes(), b"first original")
        (self.root / "second.ff").write_bytes(b"second original")
        self.engine.features[1] = Feature("second", "second", "workshop", "second.ff", digest(b"second original"), digest(b"second patched"), lambda data, resources: b"bad")
        with self.assertRaises(PatchError):
            self.engine.run("apply")
        self.original()

    def test_running_process(self):
        self.engine.running = lambda: True
        for action in ("apply", "remove", "recover"):
            with self.assertRaises(PatchError):
                self.engine.run(action)
        self.original()

    def test_corrupt_backup(self):
        self.engine.run("apply")
        (self.base / "state" / "originals" / "first.bin").write_bytes(b"bad")
        with self.assertRaises(PatchError):
            self.engine.run("remove")
        self.assertEqual((self.root / "first.ff").read_bytes(), b"first patched")
        self.assertEqual((self.root / "second.ff").read_bytes(), b"second patched")

    def test_adopt_never_saves_patched_as_original(self):
        for name in ("first", "second"):
            (self.root / (name + ".ff")).write_bytes((name + " patched").encode())
        with self.assertRaises(PatchError):
            self.engine.run("apply")
        self.assertFalse((self.base / "state" / "originals" / "first.bin").exists())
        originals = self.base / "originals"
        fixtures(originals)
        self.engine.run("apply", originals=originals)
        self.engine.run("remove")
        self.original()

    def test_second_replace_failure_rolls_back(self):
        real_replace = os.replace
        def fail_second(source, target):
            if Path(target) == self.root / "second.ff" and Path(source).read_bytes() == b"second patched":
                raise OSError("owned failure")
            return real_replace(source, target)
        with patch("patcher.engine.os.replace", side_effect=fail_second):
            with self.assertRaises(PatchError):
                self.engine.run("apply")
        self.original()

    def test_change_before_replace(self):
        real_replace = os.replace
        def change_second(source, target):
            result = real_replace(source, target)
            if Path(target) == self.root / "first.ff" and Path(target).read_bytes() == b"first patched":
                (self.root / "second.ff").write_bytes(b"external")
            return result
        with patch("patcher.engine.os.replace", side_effect=change_second):
            with self.assertRaises(PatchError):
                self.engine.run("apply")
        self.assertEqual((self.root / "first.ff").read_bytes(), b"first original")
        self.assertEqual((self.root / "second.ff").read_bytes(), b"external")

    def crash(self):
        child = Path(__file__).with_name("crash_fixture.py")
        result = subprocess.run([sys.executable, str(child), str(self.base), "first", str(self.base / "coordination")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 42, result.stderr)

    def test_process_death_recovery(self):
        self.crash()
        self.assertTrue((self.base / "state" / "journal.json").exists())
        self.engine.run("recover")
        self.original()
        self.engine.run("apply")
        self.engine.run("remove")
        self.original()

    def test_process_death_before_original_publication(self):
        child = Path(__file__).with_name("crash_fixture.py")
        result = subprocess.run([sys.executable, str(child), str(self.base), "original", str(self.base / "coordination")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertFalse((self.base / "state" / "originals" / "first.bin").exists())
        self.original()
        self.engine.run("apply")
        self.engine.run("remove")
        self.original()

    def test_recovery_external_change(self):
        self.crash()
        (self.root / "first.ff").write_bytes(b"external")
        with self.assertRaises(PatchError):
            self.engine.run("recover")
        self.assertEqual((self.root / "first.ff").read_bytes(), b"external")
        self.assertTrue((self.base / "state" / "journal.json").exists())

    def test_recovery_final_change(self):
        self.crash()
        real_replace = os.replace
        def change_after_restore(source, target):
            real_replace(source, target)
            if Path(target) == self.root / "first.ff":
                (self.root / "second.ff").write_bytes(b"external")
        with patch("patcher.engine.os.replace", side_effect=change_after_restore):
            with self.assertRaises(PatchError):
                self.engine.run("recover")
        self.assertEqual((self.root / "first.ff").read_bytes(), b"first original")
        self.assertEqual((self.root / "second.ff").read_bytes(), b"external")
        self.assertTrue((self.base / "state" / "journal.json").exists())

    def test_recovery_corrupt_snapshot(self):
        self.crash()
        journal = json.loads((self.base / "state" / "journal.json").read_text())
        (self.base / "state" / journal["transaction"] / "second.before").write_bytes(b"bad")
        with self.assertRaises(PatchError):
            self.engine.run("recover")
        self.assertEqual((self.root / "first.ff").read_bytes(), b"first patched")

    def test_target_escape(self):
        first = self.engine.features[0]
        self.engine.features[0] = Feature(first.id, first.label, first.scope, "../first.ff", first.original_sha256, first.patched_sha256, first.transform)
        with self.assertRaises(PatchError):
            self.engine.run("apply")
        self.original()

    def test_independent_selection(self):
        self.engine.run("apply", selected=["first"])
        self.engine.run("apply", selected=["second"])
        self.engine.run("remove")
        self.original()

    def test_lock(self):
        from patcher.engine import StateLock
        with StateLock(self.base / "state"):
            with self.assertRaises(PatchError):
                self.engine.run("apply")

    def other_engine(self):
        extra = self.base / "game"
        extra.mkdir(exist_ok=True)
        return Engine({"workshop": self.root, "game": extra}, self.base / "state-B", features(), self.base, lambda: False, coordination_root=self.base / "coordination")

    def child_crash(self, mode):
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("crash_fixture.py")), str(self.base), mode, str(self.base / "coordination")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 42, result.stderr)

    def test_cross_state_live_overlap_and_subset(self):
        paused = threading.Event()
        resume = threading.Event()
        errors = []
        def transform(data, resources):
            paused.set()
            self.assertTrue(resume.wait(10))
            return b"second patched"
        old = self.engine.features[1]
        self.engine.features[1] = Feature(old.id, old.label, old.scope, old.relative_path, old.original_sha256, old.patched_sha256, transform)
        def writer():
            try:
                self.engine.run("apply")
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=writer)
        thread.start()
        self.assertTrue(paused.wait(10))
        try:
            with self.assertRaises(PatchError):
                self.other_engine().run("apply", selected=["second"])
            self.original()
        finally:
            resume.set()
            thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.engine.run("remove")
        self.original()

    def test_cross_state_process_death_and_subset(self):
        self.crash()
        originals = self.base / "imports"
        fixtures(originals)
        for selected in (["first"], ["second"], None):
            with self.assertRaises(PatchError):
                self.other_engine().run("apply", selected=selected, originals=originals)
        self.assertEqual((self.root / "first.ff").read_bytes(), b"first patched")
        self.assertEqual((self.root / "second.ff").read_bytes(), b"second original")
        self.engine.run("recover")
        self.original()

    def test_death_before_receipt_does_not_undo_completed_writer(self):
        self.child_crash("receipt")
        self.original()
        other = self.other_engine()
        other.run("apply")
        self.engine.run("recover")
        self.assertEqual((self.root / "first.ff").read_bytes(), b"first patched")
        self.assertEqual((self.root / "second.ff").read_bytes(), b"second patched")
        other.run("remove")
        self.original()

    def test_death_after_final_replace_remains_pending(self):
        self.child_crash("final")
        originals = self.base / "imports"
        fixtures(originals)
        with self.assertRaises(PatchError):
            self.other_engine().run("apply", originals=originals)
        self.engine.run("recover")
        self.original()

    def test_death_after_commit_does_not_undo_later_writer(self):
        self.child_crash("commit")
        originals = self.base / "imports"
        fixtures(originals)
        other = self.other_engine()
        other.run("apply", originals=originals)
        other.run("remove")
        other.run("apply")
        self.engine.run("recover")
        self.assertEqual((self.root / "first.ff").read_bytes(), b"first patched")
        self.assertEqual((self.root / "second.ff").read_bytes(), b"second patched")

    def junction(self, path, target):
        if os.name == "nt":
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(path), str(target)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            path.symlink_to(target, target_is_directory=True)

    def test_originals_junction_refuses_every_write(self):
        state = self.base / "state"
        state.mkdir()
        extra = self.root / "unselected"
        extra.mkdir()
        self.junction(state / "originals", extra)
        with self.assertRaises(PatchError):
            self.engine.run("apply")
        self.original()
        self.assertEqual(list(extra.iterdir()), [])
        self.assertFalse((state / "lock").exists())

    def test_redirected_transaction_recovery(self):
        self.crash()
        journal = json.loads((self.base / "state" / "journal.json").read_text())
        transaction = self.base / "state" / journal["transaction"]
        redirected = self.root / "redirected"
        shutil.move(str(transaction), redirected)
        self.junction(transaction, redirected)
        with self.assertRaises(PatchError):
            self.engine.run("recover")
        self.assertEqual((self.root / "first.ff").read_bytes(), b"first patched")
        self.assertEqual((self.root / "second.ff").read_bytes(), b"second original")

    def test_missing_receipt_after_admitted_write(self):
        self.crash()
        path = self.base / "state" / "journal.json"
        journal = json.loads(path.read_text())
        self.assertEqual(journal["admitted"], ["first"])
        self.engine.coordinator.receipt_path(journal["transaction"]).unlink()
        with self.assertRaises(PatchError):
            self.engine.run("recover")
        self.assertTrue(path.exists())
        self.assertEqual((self.root / "first.ff").read_bytes(), b"first patched")
        self.assertEqual((self.root / "second.ff").read_bytes(), b"second original")

    def test_hardlinked_private_lock(self):
        state = self.base / "state"
        state.mkdir()
        settings = self.root / "empty-settings.ini"
        settings.write_bytes(b"")
        os.link(settings, state / "lock")
        with self.assertRaises(PatchError):
            self.engine.run("apply")
        self.assertEqual(settings.read_bytes(), b"")
        self.original()

    def test_committed_cleanup_failure(self):
        with patch.object(self.engine.coordinator, "remove", side_effect=OSError("owned cleanup failure")):
            with self.assertRaisesRegex(PatchError, "committed"):
                self.engine.run("apply")
        self.assertEqual((self.root / "first.ff").read_bytes(), b"first patched")
        self.assertEqual((self.root / "second.ff").read_bytes(), b"second patched")
        self.engine.run("recover")
        self.assertEqual(list((self.base / "coordination" / "active").glob("txn-*.json")), [])
        self.assertEqual((self.root / "first.ff").read_bytes(), b"first patched")
        self.assertEqual((self.root / "second.ff").read_bytes(), b"second patched")
        self.engine.run("remove")
        self.original()


if __name__ == "__main__":
    unittest.main()
