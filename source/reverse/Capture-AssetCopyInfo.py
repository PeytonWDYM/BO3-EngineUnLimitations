"""One sequential, read-only asset-copy capture from an exact process instance."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "live"))
from windows_process import VerifiedProcess

PROFILE_SHA = "497ce875da1dea5bcb1f9c80cb3a828bf36db80a367d173cadd80b55f05a7ed6"
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III\BlackOps3.exe")
EVIDENCE = Path.home() / ".codex/labs/bo3-engine/evidence"


def utc():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--created-ticks", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw_profile = args.profile.read_bytes()
    if hashlib.sha256(raw_profile).hexdigest() != PROFILE_SHA:
        raise ValueError("The asset-copy profile differs from the fixed reviewed recipe.")
    profile = json.loads(raw_profile)
    output = args.output.resolve()
    if not output.is_relative_to(EVIDENCE.resolve()):
        raise ValueError("Use a new directory inside private lab evidence.")
    output.mkdir(parents=True)
    manifest = {"schema": 1, "status": "refused", "requestedPid": args.pid,
                "requestedCreatedTicks": args.created_ticks, "profileSha256": PROFILE_SHA,
                "utcStarted": utc(), "stage": "identity", "segments": [],
                "readsSequential": True, "atomic": False, "faultTimeState": False,
                "historicalDescriptor": {"previousCasePids": [61296, 64884],
                    "rva": 0x985d0c0, "currentFaultContextMatched": False}}
    summary = None
    try:
        identity = profile["identity"]
        process_profile = {"module": "BlackOps3.exe", "sha256": identity["executableSha256"],
                          "imageSize": identity["imageSize"], "timestamp": identity["timestamp"]}
        with VerifiedProcess(args.pid, process_profile, args.created_ticks) as process:
            if process.path != GAME.resolve() or not process.path.samefile(GAME):
                raise ValueError("The process is not the exact normal BO3 executable path.")
            manifest["identity"] = {"pid": process.pid, "createdTicks": process.started_ticks,
                "startedUtc": process.started_utc, "imagePath": str(process.path),
                "sha256": process.sha256, "imageBase": process.module.baseaddress,
                "imageSize": process.module.size, "timestamp": process.module.timestamp}

            def read(name, rva, size):
                manifest["stage"] = name
                started = utc()
                data = process.read(process.module.baseaddress + rva, size)
                with (output / (name + ".bin")).open("xb") as file:
                    file.write(data)
                manifest["segments"].append({"name": name, "rva": rva, "size": size,
                    "utcBeforeRead": started, "utcAfterRead": utc(),
                    "sha256": hashlib.sha256(data).hexdigest()})
                return data

            def guards(phase):
                for guard in profile["codeGuards"]:
                    data = read(phase + "-" + guard["name"], guard["rva"], guard["size"])
                    if data.hex() != guard["bytes"] or hashlib.sha256(data).hexdigest() != guard["sha256"]:
                        raise ValueError("A native code guard differs: " + guard["name"])

            guards("before")
            names = ["counter-before", "copy-info-array", "historical-previous-case-descriptor", "counter-after"]
            values = [read(name, row["rva"], row["size"]) for name, row in zip(names, profile["readSequence"])]
            guards("after")
            manifest["stage"] = "alive-after"
            if not process.alive():
                raise ProcessLookupError("The process exited during capture.")
            pointers = struct.unpack("<15360Q", values[1])
            summary = {"counterBefore": struct.unpack("<I", values[0])[0],
                "counterAfter": struct.unpack("<I", values[3])[0], "arrayNonNull": sum(x != 0 for x in pointers),
                "firstNullIndex": pointers.index(0) if 0 in pointers else None,
                "indices": {str(i): hex(pointers[i]) for i in [347, 348, 349]}}
            manifest.update(status="complete", stage="complete", aliveAfter=True, summary=summary)
    except Exception as error:
        manifest["error"] = str(error)
    manifest["utcEnded"] = utc()
    with (output / "manifest.json").open("x", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2)
    print(json.dumps(summary if summary is not None else {"status": "refused", "stage": manifest["stage"], "error": manifest["error"]}))
    return 0 if manifest["status"] == "complete" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
