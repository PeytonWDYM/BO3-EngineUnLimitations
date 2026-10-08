"""Read pool and arena metadata at 1 Hz from one exactly bound Windows process."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time

from windows_process import ACCESS_MASK, VerifiedProcess

REPO = Path(__file__).resolve().parents[2]
RECORD_SIZE = 0xF68
MAX_MARKS = 80
MAX_NAME_BYTES = 128


def integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Invalid {name}.")
    return value


def source_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(profile, pid):
    if profile["schemaVersion"] != 1 or profile["status"] not in ("fixture-only", "private-read-only"):
        raise ValueError("The lifecycle profile is disabled or unsupported.")
    if integer(profile["expectedProcessId"], "bound PID", 1, 0xFFFFFFFF) != pid:
        raise ValueError("The PID differs from the bound profile.")
    integer(profile["expectedProcessStartTicks"], "process creation ticks", 1, 0x7FFFFFFFFFFFFFFF)
    size = integer(profile["imageSize"], "image size", RECORD_SIZE, 0xFFFFFFFF)
    for name, width in (("poolPointerRva", 8), ("serverTimeRva", 4), ("entityPoolPointerRva", 8),
                        ("arenaRecordRva", RECORD_SIZE)):
        integer(profile[name], name, 0, size - width)
    integer(profile["poolAllocationBytes"], "pool allocation bytes", 64, 64 * 1024 * 1024)
    for name, path in (("readerSourceSha256", Path(__file__)),
                       ("processApiSourceSha256", Path(__file__).with_name("windows_process.py"))):
        if profile[name] != source_hash(path):
            raise ValueError("The reader source differs from the bound profile.")
    evidence = profile["codeEvidence"]
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 64:
        raise ValueError("Require one through 64 native code evidence ranges.")
    total = 0
    for item in evidence:
        start = integer(item["startRva"], "code start", 0, size - 1)
        end = integer(item["endRva"], "code end", start + 1, size)
        if not isinstance(item["sha256"], str) or not re.fullmatch("[0-9a-f]{64}", item["sha256"]):
            raise ValueError("Invalid native code hash.")
        total += end - start
    if total > 256 * 1024:
        raise ValueError("Native code evidence exceeds the read budget.")


def verify_code(process, profile):
    for item in profile["codeEvidence"]:
        data = process.read(process.module.baseaddress + item["startRva"], item["endRva"] - item["startRva"])
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("The live native code differs from the reviewed profile.")


def mark_name(process, pointer):
    integer(pointer, "mark name pointer", 0x10000, 0x7FFFFFFFFFFF - MAX_NAME_BYTES)
    text = bytearray()
    # Read through the terminator only. A valid name can end at a page boundary.
    for index in range(MAX_NAME_BYTES):
        value = process.read(pointer + index, 1)[0]
        if value == 0:
            return text.decode("ascii")
        if not 32 <= value <= 126:
            raise ValueError("A mark name contains unsupported bytes.")
        text.append(value)
    raise ValueError("A mark name exceeds the bounded read.")


def read_metadata(process, profile):
    base = process.module.baseaddress
    pool = process.number(base + profile["poolPointerRva"], "Q")
    server_time = process.number(base + profile["serverTimeRva"], "i")
    entities = process.number(base + profile["entityPoolPointerRva"], "Q")
    record = base + profile["arenaRecordRva"]
    header = process.read(record, 0x40)
    cursors = list(struct.unpack_from("<5Q", header, 0x10))
    count = struct.unpack_from("<I", header, 0x38)[0]
    integer(count, "arena mark count", 0, MAX_MARKS)
    descriptor = process.number(record + 0xF40, "Q")
    result = {"serverPoolPointer": hex(pool), "serverTime": server_time,
              "entityPoolPointer": hex(entities), "arenaDescriptorPointer": hex(descriptor),
              "serverPoolOffset": None, "arena": None}
    if descriptor == 0:
        if pool or count or any(cursors):
            raise ValueError("An absent arena has initialized metadata.")
        return result
    integer(descriptor, "arena descriptor pointer", 0x10000, 0x7FFFFFFFFFFF - 32)
    kind, _, start, size = struct.unpack("<4Q", process.read(descriptor, 32))
    if kind != 2:
        raise ValueError("The arena kind differs from the reviewed layout.")
    integer(start, "arena base", 0x10000, 0x7FFFFFFFFFFF)
    integer(size, "arena size", 1, min(1 << 40, 0x800000000000 - start))
    integer(cursors[0], "arena main cursor", 0, size)
    if pool:
        offset = pool - start
        if not 0 <= offset <= cursors[0] - profile["poolAllocationBytes"]:
            raise ValueError("The server pool lies outside the allocated arena range.")
        result["serverPoolOffset"] = offset
    raw = process.read(record + 0x40, count * 48) if count else b""
    marks = []
    previous = 0
    for offset in range(0, len(raw), 48):
        pointer, *offsets = struct.unpack_from("<6Q", raw, offset)
        if not previous <= offsets[0] <= cursors[0]:
            raise ValueError("Arena main marks descend or exceed the cursor.")
        previous = offsets[0]
        marks.append({"namePointer": hex(pointer), "name": mark_name(process, pointer), "offsets": offsets})
    result["arena"] = {"base": hex(start), "size": size, "cursor": cursors[0],
                       "sourceCursors": cursors, "remainingBytes": size - cursors[0], "marks": marks}
    return result


def sample(process, profile):
    error = "Metadata changed between repeated reads."
    for attempt in range(1, 3):
        try:
            first = read_metadata(process, profile)
            second = read_metadata(process, profile)
            if first == second:
                return second, None, attempt
            error = "Metadata changed between repeated reads."
        except (OSError, ValueError, UnicodeError) as problem:
            error = str(problem)
    return None, error, 2


def changes(previous, current):
    if previous is None:
        return []
    result = []
    for field, label in (("serverPoolPointer", "serverPoolPointerChanged"),
                         ("entityPoolPointer", "entityPoolPointerChanged"),
                         ("arenaDescriptorPointer", "arenaDescriptorPointerChanged")):
        if previous[field] != current[field]:
            result.append(label)
    if current["serverTime"] < previous["serverTime"]:
        result.append("serverTimeDecreased")
    before, after = previous["arena"], current["arena"]
    if before != after:
        if before is None or after is None:
            result.append("arenaInitializationChanged")
        else:
            if before["marks"] != after["marks"]:
                result.append("arenaMarksChanged")
            if before["cursor"] != after["cursor"]:
                result.append("arenaCursorChanged")
            if before["base"] != after["base"] or before["size"] != after["size"]:
                result.append("arenaStorageChanged")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=0, help="Seconds. Zero runs until interruption or process exit.")
    args = parser.parse_args()
    try:
        integer(args.pid, "PID", 1, 0xFFFFFFFF)
        if not 0 <= args.duration <= 86400:
            raise ValueError("Use duration 0 through 86400 seconds.")
        output = args.output.resolve()
        if output == REPO or REPO in output.parents:
            raise ValueError("Write lifecycle capture output outside the repository.")
        if output.exists():
            raise ValueError("Choose a new output file.")
        profile_bytes = args.profile.read_bytes()
        profile = json.loads(profile_bytes.decode("utf-8-sig"))
        validate(profile, args.pid)
        with VerifiedProcess(args.pid, profile, profile["expectedProcessStartTicks"]) as process:
            verify_code(process, profile)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as stream:
                def emit(event, **values):
                    row = {"event": event, "utc": datetime.now(timezone.utc).isoformat(), **values}
                    stream.write(json.dumps(row) + "\n")
                    stream.flush()
                emit("attached", pid=process.pid, processStartTicks=process.started_ticks,
                     processStartUtc=process.started_utc, path=str(process.path), sha256=process.sha256,
                     moduleBase=hex(process.module.baseaddress), imageSize=process.module.size,
                     timestamp=process.module.timestamp, profileSha256=hashlib.sha256(profile_bytes).hexdigest(),
                     readerSourceSha256=profile["readerSourceSha256"], processApiSourceSha256=profile["processApiSourceSha256"],
                     accessMask=hex(ACCESS_MASK), rateHz=1, scope=profile["status"],
                     consistency="Repeated equal metadata reads are not an atomic snapshot. Changes are provisional observations, not world epochs.")
                started = time.monotonic()
                previous = None
                accepted = rejected = 0
                try:
                    while not args.duration or time.monotonic() - started < args.duration:
                        if not process.alive():
                            emit("process-exited")
                            break
                        try:
                            verify_code(process, profile)
                        except (OSError, ValueError) as problem:
                            emit("process-exited" if not process.alive() else "code-guard-refused", error=str(problem))
                            break
                        metadata, error, attempts = sample(process, profile)
                        if metadata is None:
                            if not process.alive():
                                emit("process-exited")
                                break
                            rejected += 1
                            emit("rejected", error=error, attemptsUsed=attempts)
                        else:
                            accepted += 1
                            emit("sample", metadata=metadata, changes=changes(previous, metadata), attemptsUsed=attempts)
                            previous = metadata
                        remaining = args.duration - (time.monotonic() - started) if args.duration else 1
                        if remaining > 0:
                            time.sleep(min(1, remaining))
                except KeyboardInterrupt:
                    emit("interrupted")
                emit("stopped", accepted=accepted, rejected=rejected)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Pool lifecycle: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
