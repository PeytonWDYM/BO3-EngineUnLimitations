"""Owned-file transactions for removal-only stock features. No game access."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from patcher.engine import Engine, PatchError, digest
from patcher.plans import load

RESOURCES = Path(__file__).resolve().parents[2]
RETIRED = {"zero-spawn-delay", "storm-bow"}
ENABLED = {"aae-core", "aae-native"}
OUTPUT: Path


def fixture_features():
    _, features = load(RESOURCES)
    return [replace(feature, original_sha256=digest(stock(feature.id)),
                    patched_sha256=digest(candidate(feature.id)), admitted_sha256=(),
                    transform=lambda data, resources, identity=feature.id: candidate(identity))
            for feature in features]


def stock(identity):
    return (identity + " owned original").encode()


def candidate(identity):
    return (identity + " owned candidate").encode()


def engine_at(base):
    return Engine({scope: base / scope for scope in ("workshop", "game")},
                  base / "state", fixture_features(), RESOURCES, lambda: False,
                  coordination_root=base / "coordination")


def snapshot(base):
    return {path.relative_to(base).as_posix(): digest(path.read_bytes()) if path.is_file() else "directory"
            for path in sorted(base.rglob("*"))}


def legacy_writer(base):
    engine = engine_at(base)
    # Replay an older writer that admitted all four files before retirement.
    engine.features = [replace(feature, apply_availability="enabled") for feature in engine.features]
    final_target = engine.target(engine.features[-1])
    real_replace = os.replace

    def exit_after_final(source, target):
        real_replace(source, target)
        if Path(target) == final_target:
            os._exit(42)

    with patch("patcher.engine.os.replace", side_effect=exit_after_final):
        engine.run("apply")


class RetiredStockTransactions(unittest.TestCase):
    def setUp(self):
        self.base = OUTPUT / self._testMethodName
        self.base.mkdir()
        self.features = fixture_features()
        for feature in self.features:
            target = self.base / feature.scope / feature.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(stock(feature.id))
        (self.base / "game" / "settings.ini").write_bytes(b"owned settings")
        (self.base / "workshop" / "save.bin").write_bytes(b"owned save")
        self.engine = engine_at(self.base)
        self.before = snapshot(self.base)
        self.observations = {}

    def tearDown(self):
        report = {"before": self.before, "after": snapshot(self.base), **self.observations}
        (self.base / "evidence.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def assert_files(self, patched):
        for feature in self.features:
            expected = candidate(feature.id) if feature.id in patched else stock(feature.id)
            self.assertEqual(self.engine.target(feature).read_bytes(), expected)
        self.assertEqual((self.base / "game" / "settings.ini").read_bytes(), b"owned settings")
        self.assertEqual((self.base / "workshop" / "save.bin").read_bytes(), b"owned save")

    def test_default_apply_and_status(self):
        version, public_features = load(RESOURCES)
        self.assertEqual(version, "0.1.0-test.4")
        self.assertEqual({f.id for f in public_features}, ENABLED | RETIRED)
        self.assertEqual({f.id for f in public_features if f.apply_availability == "enabled"}, ENABLED)
        self.observations["result"] = self.engine.run("apply")
        self.assertEqual(set(self.observations["result"]["files"]), ENABLED)
        self.assert_files(ENABLED)
        rows = self.engine.status()
        self.observations["status"] = rows
        for row in rows:
            self.assertEqual(row["applyAvailability"], "removal-only" if row["id"] in RETIRED else "enabled")
            self.assertEqual(row["originalVerified"], row["id"] in ENABLED)
        backups = self.engine.state / "originals"
        self.assertEqual({p.stem for p in backups.iterdir()}, ENABLED)
        for feature in self.features:
            if feature.id in ENABLED:
                self.assertEqual(self.engine.original_path(feature).read_bytes(), stock(feature.id))

    def test_explicit_retired_apply_changes_nothing(self):
        selections = [[identity] for identity in sorted(RETIRED)] + [list(ENABLED | RETIRED)]
        for selected in selections:
            with self.subTest(selected=selected):
                with self.assertRaisesRegex(PatchError, "removal-only"):
                    self.engine.run("apply", selected=selected)
                self.assertEqual(snapshot(self.base), self.before)
        self.assert_files(set())
        self.observations["refusedSelections"] = selections

    def test_default_remove_restores_four_legacy_candidates(self):
        for feature in self.features:
            self.engine.target(feature).write_bytes(candidate(feature.id))
            backup = self.engine.original_path(feature)
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(stock(feature.id))
        self.observations["legacyInstalled"] = snapshot(self.base)
        self.observations["result"] = self.engine.run("remove")
        self.assertEqual(set(self.observations["result"]["files"]), ENABLED | RETIRED)
        self.assert_files(set())
        for feature in self.features:
            self.assertEqual(self.engine.original_path(feature).read_bytes(), stock(feature.id))

    def test_recover_four_file_legacy_apply_journal(self):
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--legacy-writer", str(self.base)],
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(child.returncode, 42, child.stderr)
        journal_path = self.engine.state / "journal.json"
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        self.assertEqual({entry["id"] for entry in journal["entries"]}, ENABLED | RETIRED)
        self.assertEqual(set(journal["admitted"]), ENABLED | RETIRED)
        self.assert_files(ENABLED | RETIRED)
        self.observations["legacyJournal"] = journal
        paused = snapshot(self.base)
        with self.assertRaisesRegex(PatchError, "removal-only"):
            self.engine.run("apply", selected=["aae-core", "storm-bow"])
        self.assertEqual(snapshot(self.base), paused)
        self.observations["result"] = self.engine.run("recover")
        self.assert_files(set())
        self.assertFalse(journal_path.exists())
        self.assertEqual(list((self.base / "coordination" / "active").glob("txn-*.json")), [])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--legacy-writer", type=Path)
    args = parser.parse_args()
    if args.legacy_writer:
        legacy_writer(args.legacy_writer)
        return 1
    if args.output is None:
        parser.error("--output is required to retain transaction evidence")
    global OUTPUT
    OUTPUT = args.output.resolve()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RetiredStockTransactions))
    report = {"status": "passed" if result.wasSuccessful() else "failed", "groups": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors),
              "gameAccess": False, "sourceHashes": {str(path): digest(path.read_bytes()) for path in
                  (Path(__file__).resolve(), RESOURCES / "patcher" / "engine.py", RESOURCES / "patcher" / "plans.py",
                   RESOURCES / "patcher" / "app.py", RESOURCES / "patchplans" / "release.json")}}
    (OUTPUT / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
