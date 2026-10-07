"""Find null-terminated ASCII strings in a completely captured module section."""

import argparse
import json
from pathlib import Path
import re


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--section", default=".rdata")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if output == repo or repo in output.parents:
        raise ValueError("Write captured strings outside the repository.")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    section = next(section for section in manifest["sections"] if section["name"] == args.section)
    if not section["complete"]:
        raise ValueError("The dump does not contain the complete selected section.")
    cursor = int(section["address"], 16)
    stop = cursor + section["size"]
    parts = []
    for item in manifest["ranges"]:
        start = int(item["address"], 16)
        end = start + item["size"]
        if start <= cursor < end:
            length = min(stop, end) - cursor
            with (args.manifest.parent / item["file"]).open("rb") as source:
                source.seek(cursor - start)
                part = source.read(length)
            if len(part) != length:
                raise EOFError("A captured range file is truncated.")
            parts.append(part)
            cursor += length
        if cursor == stop:
            break
    if cursor != stop:
        raise ValueError("The selected section has a missing memory range.")
    pattern = re.compile(args.pattern, re.IGNORECASE)
    matches = []
    for match in re.finditer(rb"[\x09\x0a\x0d\x15\x20-\x7e]{6,}\x00", b"".join(parts)):
        text = match.group()[:-1].decode("ascii")
        if pattern.search(text):
            matches.append({"address": hex(int(section["address"], 16) + match.start()), "text": text})
    output.write_text(json.dumps(matches, indent=2), encoding="utf-8")
    print(f"Exported {len(matches)} matching strings: {output}")


if __name__ == "__main__":
    main()
