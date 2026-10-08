"""Load public transformation metadata. Payload bytes come from the user's files."""
import importlib
import json
from pathlib import Path

from patcher.engine import Feature, PatchError


def load(resources: Path) -> tuple[str, list[Feature]]:
    manifest = resources / "patchplans" / "release.json"
    if not manifest.is_file():
        raise PatchError("This build has no completed release manifest.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1 or data.get("status") != "ready":
        raise PatchError("The release manifest is incomplete. Build from a completed release checkpoint.")
    entries = data["features"]
    if not entries:
        raise PatchError("The release manifest contains no supported patch files.")
    features = []
    for entry in entries:
        module, name = entry["transform"].split(":")
        if not module.startswith("patchplans.") or not name.isidentifier():
            raise PatchError("The release manifest has an invalid transform name.")
        transform = getattr(importlib.import_module(module), name)
        features.append(Feature(entry["id"], entry["label"], entry["scope"], entry["relativePath"], entry["originalSha256"].lower(), entry["patchedSha256"].lower(), transform, tuple(value.lower() for value in entry.get("admittedSha256", []))))
    return data["version"], features
