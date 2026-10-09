"""Owned Steam trees and inert binaries; preserve repeatable field-edit evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from patcher import steam_launch
from patcher import enhanced_launch
from patcher.errors import PatchError

EVIDENCE = None
BASE = ('\ufeff// owned fixture\r\n"UserLocalConfigStore"\r\n{\r\n'
        ' "Software" { "Valve" { "Steam" { "apps" {\r\n'
        '  "311210"\r\n  {\r\n   "LastPlayed" "123"\r\n'
        '   "cloud" { "LaunchOptions" "nested stays" "unicode" "é" }\r\n'
        '   PLACEHOLDER\r\n  }\r\n'
        '  "999" { "LaunchOptions" "other app stays" }\r\n'
        ' } } } }\r\n}\r\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


class SteamEndToEnd(unittest.TestCase):
    def setUp(self):
        if EVIDENCE:
            self.root = EVIDENCE / self._testMethodName
            self.root.mkdir()
        else:
            temp = tempfile.TemporaryDirectory(prefix="bo3-owned-steam-")
            self.addCleanup(temp.cleanup)
            self.root = Path(temp.name)
        self.steam = self.root / "Steam"
        self.config = self.steam / "userdata/42/config/localconfig.vdf"
        self.config.parent.mkdir(parents=True)
        (self.steam / "config").mkdir()
        (self.steam / "config/loginusers.vdf").write_text('"users" { "76561197960265770" { "MostRecent" "1" } }')
        self.game = self.root / "game"
        self.game.mkdir()
        (self.game / "BlackOps3.exe").write_bytes(b"owned game")
        (self.game / "settings.ini").write_bytes(b"owned settings")
        self.resources = self.root / "resources"
        bundle = self.resources / "enhanced"
        bundle.mkdir(parents=True)
        hashes = {}
        for name in enhanced_launch.PAYLOAD_NAMES:
            data = ("owned " + name).encode()
            (bundle / name).write_bytes(data)
            hashes[name] = sha(data)
        (bundle / "manifest.json").write_text(json.dumps({"schemaVersion": 1, "version": "0.1.0-test.3", "status": "experimental", "gameSha256": sha(b"owned game"), "files": hashes}))
        self.tools = self.root / "tools"
        self.state = self.root / "state"
        self.original = BASE.replace('PLACEHOLDER', '"LaunchOptions" "-console +set name \\\"quoted\\\""').encode()
        self.config.write_bytes(self.original)
        self.addCleanup(self.record)

    def record(self):
        if EVIDENCE:
            (self.root / "before.vdf").write_bytes(self.original)
            (self.root / "after.vdf").write_bytes(self.config.read_bytes())
            (self.root / "evidence.json").write_text(json.dumps({"beforeSha256": sha(self.original), "afterSha256": sha(self.config.read_bytes()), "settingsSha256": sha((self.game / "settings.ini").read_bytes()), "gameSha256": sha((self.game / "BlackOps3.exe").read_bytes()), "nativeExecuted": False}, indent=2))

    def manager(self, **kwargs):
        return steam_launch.SteamPlay(self.steam, state=self.state,
                                    process_running=kwargs.pop("process_running", lambda name: False), **kwargs)

    def enable(self, manager=None):
        return (manager or self.manager()).enable(self.resources, self.game, tools_root=self.tools)

    def options(self):
        return steam_launch.launch_field(self.config.read_bytes()).value

    def test_enable_restore_preserves_unrelated_and_plain_args(self):
        result = self.enable()
        self.assertEqual(result["status"], "enabled")
        expected = '"' + result["launcher"] + '" %command% -console +set name "quoted"'
        self.assertEqual(self.options(), expected)
        before_field = steam_launch.launch_field(self.original)
        after = self.config.read_bytes()
        after_field = steam_launch.launch_field(after)
        self.assertEqual(before_field.with_value("sentinel"), after_field.with_value("sentinel"))
        self.assertEqual(self.enable()["status"], "already-enabled")
        self.assertEqual(self.manager().remove()["status"], "restored")
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertEqual(self.manager().remove()["status"], "already-restored")
        self.assertEqual((self.game / "settings.ini").read_bytes(), b"owned settings")

    def test_absent_and_empty_restore_exactly(self):
        for value in ('', '"LaunchOptions" ""'):
            self.original = BASE.replace('PLACEHOLDER', value).encode()
            self.config.write_bytes(self.original)
            self.enable()
            self.manager().remove()
            self.assertEqual(self.config.read_bytes(), self.original)

    def test_restore_preserves_later_unrelated_changes(self):
        self.enable()
        current = self.config.read_bytes().replace(b'"LastPlayed" "123"', b'"LastPlayed" "456"')
        self.config.write_bytes(current)
        self.manager().remove()
        self.assertEqual(self.config.read_bytes(), self.original.replace(b'"LastPlayed" "123"', b'"LastPlayed" "456"'))

    def test_account_selection_and_ambiguity(self):
        (self.steam / "config/loginusers.vdf").write_text('"users" { "76561197960265770" { "MostRecent" "1" } "76561197960265771" { "MostRecent" "1" } }')
        with self.assertRaisesRegex(PatchError, "account"):
            self.manager()
        self.assertEqual(self.manager(active_user=42).config, self.config)
        with self.assertRaises(PatchError):
            self.manager(active_user=43)
        self.assertFalse(self.state.exists())

    def test_auto_login_exact_match_without_most_recent(self):
        (self.steam / "config/loginusers.vdf").write_text('"users" { "76561197960265770" { "AccountName" "owned-login" } "76561197960265771" { "AccountName" "other-login" } }')
        self.enable(self.manager(auto_login_name="owned-login"))
        self.assertEqual(self.manager(auto_login_name="owned-login").config, self.config)
        self.manager(auto_login_name="owned-login").remove()
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_auto_login_missing_or_ambiguous_refused(self):
        for users in ('"76561197960265770" { "AccountName" "other-login" }',
                      '"76561197960265770" { "AccountName" "owned-login" } "76561197960265771" { "AccountName" "owned-login" }'):
            (self.steam / "config/loginusers.vdf").write_text('"users" { ' + users + ' }')
            with self.assertRaises(PatchError):
                self.manager(auto_login_name="owned-login")
            self.assertFalse(self.state.exists())

    def test_processes_closed_and_last_gate(self):
        for running in ("steam.exe", "BlackOps3.exe", "BO3-Enhanced-Zombies.exe"):
            with self.assertRaises(PatchError):
                self.enable(self.manager(process_running=lambda name: name == running))
            self.assertEqual(self.config.read_bytes(), self.original)
        count = 0
        def changed(name):
            nonlocal count
            if name == "steam.exe":
                count += 1
                return count > 1
            return False
        with self.assertRaises(PatchError):
            self.enable(self.manager(process_running=changed))
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_wrapper_and_malformed_scoped_fields(self):
        for value in ('"LaunchOptions" "other %command%"', '"LaunchOptions" "x" "LaunchOptions" "y"', '"LaunchOptions" { "nested" "x" }'):
            self.config.write_bytes(BASE.replace('PLACEHOLDER', value).encode())
            before = self.config.read_bytes()
            with self.assertRaises(PatchError):
                self.enable()
            self.assertEqual(self.config.read_bytes(), before)
        self.config.write_bytes(self.original[:-6])
        with self.assertRaises(PatchError):
            self.enable()

    def test_user_changed_options_refuses_restore(self):
        self.enable()
        field = steam_launch.launch_field(self.config.read_bytes())
        changed = field.with_value(field.value + " user change")
        self.config.write_bytes(changed)
        with self.assertRaises(PatchError):
            self.manager().remove()
        self.assertEqual(self.config.read_bytes(), changed)

    def test_config_hardlink_and_state_junction(self):
        os.link(self.config, self.root / "config-link")
        with self.assertRaises(PatchError):
            self.enable()
        (self.root / "config-link").unlink()
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(self.state), str(self.game)], capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.addCleanup(lambda: os.rmdir(self.state))
        with self.assertRaises(PatchError):
            self.enable()
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_changed_config_at_last_gate_preserved(self):
        count = 0
        changed = self.original.replace(b'"LastPlayed" "123"', b'"LastPlayed" "789"')
        def processes(name):
            nonlocal count
            if name == "steam.exe":
                count += 1
                if count == 2:
                    self.config.write_bytes(changed)
            return False
        with self.assertRaises(PatchError):
            self.enable(self.manager(process_running=processes))
        self.assertEqual(self.config.read_bytes(), changed)
        self.enable()
        self.manager().remove()
        self.assertEqual(self.config.read_bytes(), changed)

    def crash(self, action, moment):
        child = subprocess.run([sys.executable, str(Path(__file__).with_name("steam_crash_fixture.py")), str(self.root), action, moment], capture_output=True, text=True)
        self.assertEqual(child.returncode, 42, child.stderr)

    def test_death_before_enable_write(self):
        self.crash("enable", "before")
        self.assertEqual(self.config.read_bytes(), self.original)
        self.enable()
        self.manager().remove()
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_death_after_enable_write(self):
        self.crash("enable", "after")
        self.config.write_bytes(self.config.read_bytes().replace(b'"LastPlayed" "123"', b'"LastPlayed" "456"'))
        self.assertEqual(self.enable()["status"], "already-enabled")
        self.manager().remove()
        self.assertEqual(self.config.read_bytes(), self.original.replace(b'"LastPlayed" "123"', b'"LastPlayed" "456"'))

    def test_death_before_remove_write(self):
        self.enable()
        self.crash("remove", "before")
        self.assertEqual(self.manager().remove()["status"], "restored")
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_death_after_remove_write(self):
        self.enable()
        self.crash("remove", "after")
        self.assertEqual(self.manager().remove()["status"], "already-restored")
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_pending_external_launch_change_retains_receipt(self):
        self.crash("enable", "after")
        self.config.write_bytes(steam_launch.launch_field(self.config.read_bytes()).with_value("external change"))
        receipt = self.state / "receipt.json"
        before = receipt.read_bytes()
        with self.assertRaises(PatchError):
            self.manager().remove()
        self.assertEqual(receipt.read_bytes(), before)
        self.assertEqual(self.options(), "external change")

    def test_corrupt_inserted_span_cannot_remove_sibling(self):
        self.original = BASE.replace('PLACEHOLDER', '').encode()
        self.config.write_bytes(self.original)
        self.enable()
        field = steam_launch.launch_field(self.config.read_bytes())
        line = field.text.rfind('\n', 0, field.entry[0].start) + 1
        sibling = '   "Unrelated" "must remain"\r\n'
        self.config.write_bytes((field.text[:line] + sibling + field.text[line:]).encode())
        path = self.state / 'receipt.json'
        receipt = json.loads(path.read_text())
        receipt['inserted'] = sibling + receipt['inserted']
        path.write_text(json.dumps(receipt))
        before, receipt_before = self.config.read_bytes(), path.read_bytes()
        with self.assertRaises(PatchError):
            self.manager().remove()
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(path.read_bytes(), receipt_before)

    def test_present_original_requires_empty_inserted_receipt(self):
        self.enable()
        path = self.state / 'receipt.json'
        receipt = json.loads(path.read_text())
        receipt['inserted'] = ' "LaunchOptions" "corrupt" '
        path.write_text(json.dumps(receipt))
        before = self.config.read_bytes()
        with self.assertRaises(PatchError):
            self.manager().remove()
        self.assertEqual(self.config.read_bytes(), before)

    def test_prepare_only_never_starts_process(self):
        with patch.object(enhanced_launch.subprocess, "Popen", side_effect=AssertionError("must not spawn")):
            folder = enhanced_launch.prepare(self.resources, self.game, tools_root=self.tools)
        self.assertEqual({p.name for p in folder.iterdir()}, set(enhanced_launch.PAYLOAD_NAMES))
        self.assertEqual(self.config.read_bytes(), self.original)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    EVIDENCE = args.evidence
    if EVIDENCE:
        EVIDENCE.mkdir(parents=True, exist_ok=False)
    unittest.main(argv=[sys.argv[0]], verbosity=2)
