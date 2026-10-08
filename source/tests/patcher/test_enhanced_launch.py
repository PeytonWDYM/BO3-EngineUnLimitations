"""Owned extraction and process handoff; never execute native launcher or BO3."""
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
from patcher import enhanced_launch as launch
from patcher.errors import PatchError


def digest(data):
    return hashlib.sha256(data).hexdigest()


class EnhancedEndToEnd(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bo3-owned-enhanced-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.resources = self.root / "resources"
        self.bundle = self.resources / "enhanced"
        self.bundle.mkdir(parents=True)
        self.game = self.root / "game"
        self.game.mkdir()
        (self.game / "BlackOps3.exe").write_bytes(b"owned-game")
        (self.game / "settings.ini").write_bytes(b"owned-settings")
        self.tools = self.root / "tools"
        self.payload = {name: ("owned-" + name).encode() for name in launch.PAYLOAD_NAMES}
        self.manifest = {"schemaVersion": 1, "version": "0.1.0-test.3", "status": "experimental",
                         "gameSha256": digest(b"owned-game"),
                         "files": {name: digest(data) for name, data in self.payload.items()}}
        for name, data in self.payload.items():
            (self.bundle / name).write_bytes(data)
        self.write_manifest()
        self.calls = []
        self.children = []
        self.environment = dict(os.environ)
        self.baseline = {p.name: digest(p.read_bytes()) for p in self.game.iterdir()}

    def write_manifest(self):
        (self.bundle / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def processes(self, name="BlackOps3.exe"):
        self.calls.append(name)
        return name == "steam.exe"

    def spawn(self, args, *, cwd, creationflags):
        # A real owned child checks the handoff. Native payload bytes stay inert.
        report = self.root / "stand-in.json"
        script = "import json,pathlib,sys; p=pathlib.Path.cwd(); json.dump({'cwd':str(p),'argv':sys.argv[1:],'files':sorted(x.name for x in p.iterdir())},open(sys.argv[3],'w'))"
        child = subprocess.Popen([sys.executable, "-c", script, *args, str(report)], cwd=cwd)
        self.children.append(child)
        child.wait(timeout=15)
        self.assertEqual(child.returncode, 0)
        self.assertEqual(creationflags, subprocess.CREATE_NEW_CONSOLE)
        self.handoff = json.loads(report.read_text())
        return child

    def play(self, **kwargs):
        return launch.play(self.resources, self.game, tools_root=self.tools,
                           process_running=kwargs.pop("process_running", self.processes),
                           spawn=kwargs.pop("spawn", self.spawn), **kwargs)

    def assert_preserved(self):
        self.assertEqual(self.baseline, {p.name: digest(p.read_bytes()) for p in self.game.iterdir()})
        self.assertEqual(self.environment, dict(os.environ))

    def test_owned_process_handoff_and_repeat(self):
        first = self.play()
        second = self.play()
        self.assertEqual(first["toolsFolder"], second["toolsFolder"])
        folder = Path(first["toolsFolder"])
        self.assertEqual(self.handoff["argv"], [str(folder / launch.PAYLOAD_NAMES[0]), str(self.game / "BlackOps3.exe"), str(self.root / "stand-in.json")])
        self.assertEqual(set(self.handoff["files"]), set(launch.PAYLOAD_NAMES))
        self.assertEqual(self.calls, ["BlackOps3.exe", "BO3-Enhanced-Zombies.exe", "steam.exe"] * 4)
        for name, data in self.payload.items():
            self.assertEqual((folder / name).read_bytes(), data)
        self.assert_preserved()

    def test_optional_missing(self):
        (self.bundle / "manifest.json").unlink()
        self.assertFalse(launch.available(self.resources))
        with self.assertRaisesRegex(PatchError, "not bundled"):
            self.play()
        self.assertFalse(self.tools.exists())

    def test_no_steam_retains_identity_refusal_precedence(self):
        (self.game / "BlackOps3.exe").write_bytes(b"unsupported")
        with self.subTest(reason="unsupported"):
            with self.assertRaisesRegex(PatchError, "unsupported"):
                self.play(process_running=lambda name: False)
        (self.game / "BlackOps3.exe").write_bytes(b"owned-game")
        (self.bundle / "manifest.json").unlink()
        with self.subTest(reason="not bundled"):
            with self.assertRaisesRegex(PatchError, "not bundled"):
                self.play(process_running=lambda name: False)
        self.assertFalse(self.tools.exists())

    def test_corrupt_bundled_files(self):
        for name, data in self.payload.items():
            with self.subTest(name=name):
                (self.bundle / name).write_bytes(b"corrupt")
                with self.assertRaises(PatchError):
                    self.play()
                self.assertFalse(self.tools.exists())
                (self.bundle / name).write_bytes(data)
        self.assert_preserved()

    def test_game_and_process_admission(self):
        for checker in (lambda name="BlackOps3.exe": True, lambda name="BlackOps3.exe": False):
            with self.assertRaises(PatchError):
                self.play(process_running=checker)
            self.assertFalse(self.tools.exists())
        (self.game / "BlackOps3.exe").write_bytes(b"unsupported")
        with self.assertRaisesRegex(PatchError, "unsupported"):
            self.play()
        self.assertFalse(self.tools.exists())

    def test_pending_launcher_blocks_duplicate_handoff(self):
        children = []
        def delayed_spawn(args, **kwargs):
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            children.append(child)
            self.addCleanup(child.wait, timeout=15)
            self.addCleanup(child.terminate)
            return child
        def processes(name="BlackOps3.exe"):
            return name == "steam.exe" or (name == "BO3-Enhanced-Zombies.exe" and any(child.poll() is None for child in children))
        self.play(process_running=processes, spawn=delayed_spawn)
        with self.assertRaisesRegex(PatchError, "launcher"):
            self.play(process_running=processes, spawn=delayed_spawn)
        self.assertEqual(len(children), 1)
        self.assert_preserved()

    def test_launcher_appearing_during_extraction_refuses_spawn(self):
        checks = 0
        def processes(name="BlackOps3.exe"):
            nonlocal checks
            if name == "BO3-Enhanced-Zombies.exe":
                checks += 1
                return checks == 2
            return name == "steam.exe"
        with self.assertRaisesRegex(PatchError, "launcher"):
            self.play(process_running=processes)
        self.assertEqual(len(self.children), 0)
        self.assert_preserved()

    def test_manifest_refusal(self):
        mutations = [("version", "../escape"), ("gameSha256", "x"), ("files", {"../escape": "0" * 64})]
        for key, value in mutations:
            original = self.manifest[key]
            self.manifest[key] = value
            self.write_manifest()
            with self.assertRaises(PatchError):
                self.play()
            self.assertFalse(self.tools.exists())
            self.manifest[key] = original
        self.write_manifest()

    def test_existing_tamper_extra_and_hardlink(self):
        folder = Path(self.play()["toolsFolder"])
        launcher = folder / launch.PAYLOAD_NAMES[0]
        launcher.write_bytes(b"tampered")
        with self.assertRaises(PatchError):
            self.play()
        self.assertEqual(launcher.read_bytes(), b"tampered")
        launcher.write_bytes(self.payload[launcher.name])
        extra = folder / "unselected.dll"
        extra.write_bytes(b"extra")
        with self.assertRaises(PatchError):
            self.play()
        extra.unlink()
        os.link(launcher, self.root / "other-link")
        with self.assertRaises(PatchError):
            self.play()
        self.assert_preserved()

    def test_interrupted_extraction(self):
        original = launch.durable_write
        count = 0
        def interrupted(path, data):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("owned extraction fault")
            original(path, data)
        with patch.object(launch, "durable_write", interrupted):
            with self.assertRaises(OSError):
                self.play()
        self.assertFalse(any(p.is_dir() and not p.name.startswith("stage-") for p in self.tools.iterdir()))
        self.play()
        self.assert_preserved()

    def test_tools_inside_install_refused(self):
        self.tools = self.game / "tools"
        with self.assertRaises(PatchError):
            self.play()
        self.assertFalse(self.tools.exists())
        self.assert_preserved()

    def test_tools_junction_refused(self):
        self.tools.parent.mkdir(exist_ok=True)
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(self.tools), str(self.game)], capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.addCleanup(lambda: os.rmdir(self.tools))
        with self.assertRaises(PatchError):
            self.play()
        self.assert_preserved()


if __name__ == "__main__":
    unittest.main(verbosity=2)
