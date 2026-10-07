"""Publish the last accepted sample for an external diagnostics window."""

import json
from pathlib import Path


class LatestState:
    def __init__(self, path: Path):
        self.path = path
        self.state: dict = {"lastSample": None, "lastSampleUtc": None}
        # Exclusive creation prevents another monitor's output from being replaced.
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"event": "starting", **self.state}, stream)

    def publish(self, row: dict) -> None:
        self.state.update({key: value for key, value in row.items() if key != "instances"})
        if row["event"] == "sample":
            self.state["lastSample"] = row["instances"]
            self.state["lastSampleUtc"] = row["utc"]
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(self.state, stream, ensure_ascii=True)
        temporary.replace(self.path)
