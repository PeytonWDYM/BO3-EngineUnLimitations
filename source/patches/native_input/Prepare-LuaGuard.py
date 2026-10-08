"""Prepare a private PE candidate for a verified native Lua callback."""

import argparse
import json
from pathlib import Path

from guard_image import build_image


def prepare(source: Path, profile_path: Path, output: Path) -> dict:
    profile = json.loads(profile_path.read_text())
    output = output.resolve()
    repo = Path(__file__).resolve().parents[3]
    if output == repo or repo in output.parents or output.exists():
        raise ValueError("Use a new private output directory.")
    candidate_bytes, report = build_image(source.read_bytes(), profile)
    output.mkdir(parents=True)
    candidate = output / "T7Overcharged.ff"
    candidate.write_bytes(candidate_bytes)
    report["candidate"] = str(candidate)
    (output / "candidate.json").write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.profile, args.output), indent=2))


if __name__ == "__main__":
    main()
