"""Measure an entity pool from a dump with a verified, private build profile."""

import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import struct

from dump_memory import DumpMemory, verify_identity


def inspect_pool(memory: DumpMemory, module, profile: dict) -> dict:
    layout = profile["layout"]
    stride, capacity = layout["stride"], layout["capacity"]
    limit, reserved = layout["normalLimit"], layout["reservedCount"]
    fake_start = layout["fakeStart"]
    if not (0 < stride <= 65536 and 0 <= reserved < limit <= fake_start <= capacity <= 65536):
        raise ValueError("Invalid pool bounds in the profile.")
    globals_ = profile["globals"]
    values = {}
    for name, format_code in (("pool", "Q"), ("highWater", "I"), ("time", "i"), ("head", "Q"), ("tail", "Q")):
        rva = globals_[name]
        if not 0 <= rva <= module.size - struct.calcsize("<" + format_code):
            raise ValueError("A profile global is outside the selected module.")
        values[name] = memory.number(module.baseaddress + rva, format_code)
    report = {"status": "uninitialized", "moduleBase": hex(module.baseaddress), "metadata": values}
    if values["pool"] == 0:
        if values["highWater"] != 0 or values["head"] != 0 or values["tail"] != 0:
            raise ValueError("A null pool has initialized metadata.")
        return report
    if not reserved <= values["highWater"] <= limit or values["pool"] % 8 != 0:
        raise ValueError("Invalid pool pointer or high-water mark.")
    # Keep legacy profile keys. This flag also marks some spent missiles.
    fields = {"inUse": (layout["inUseOffset"], "B"), "cleanupFlag": (layout["temporaryOffset"], layout["temporaryFormat"]),
              "type": (layout["typeOffset"], "H"), "freeTime": (layout["freeTimeOffset"], "i"),
              "next": (layout["freeNextOffset"], "Q")}
    if layout["temporaryFormat"] not in ("B", "I"):
        raise ValueError("The cleanup flag format must be B or I.")
    for offset, format_code in fields.values():
        if not 0 <= offset <= stride - struct.calcsize("<" + format_code):
            raise ValueError("A profile entity field is outside its slot.")
    pool = memory.read(values["pool"], stride * capacity)
    entities = [{name: struct.unpack_from("<" + format_code, pool, index * stride + offset)[0]
                 for name, (offset, format_code) in fields.items()} for index in range(capacity)]
    if any(item["inUse"] not in (0, 1) for item in entities):
        raise ValueError("An entity has an invalid in-use flag.")
    high_water = values["highWater"]
    if any(item["inUse"] for item in entities[high_water:limit]):
        raise ValueError("An active normal slot is outside the high-water mark.")
    free_indices = []
    pointer = values["head"]
    visited = set()
    while pointer:
        if pointer in visited:
            raise ValueError("The reuse list has a cycle.")
        visited.add(pointer)
        delta = pointer - values["pool"]
        if delta < 0 or delta % stride or not reserved <= delta // stride < high_water:
            raise ValueError("The reuse list points outside its allocatable range.")
        index = delta // stride
        if entities[index]["inUse"]:
            raise ValueError("The reuse list contains an active slot.")
        free_indices.append(index)
        pointer = entities[index]["next"]
    tail = values["pool"] + free_indices[-1] * stride if free_indices else 0
    if values["tail"] != tail:
        raise ValueError("The reuse-list tail differs from its final entry.")
    active = [item for item in entities[:high_water] if item["inUse"]]
    cleanup_flagged = [item for item in active if item["cleanupFlag"] == 1]
    # The cleanup path compares this field with the clock. Its origin varies by type.
    cleanup_clock_ages = [(values["time"] - item["freeTime"] + 2**31) % 2**32 - 2**31
                          for item in cleanup_flagged]
    head_age = None
    if free_indices:
        head_age = (values["time"] - entities[free_indices[0]]["freeTime"] + 2**31) % 2**32 - 2**31
    report.update({
        "status": "initialized", "normalLimit": limit, "highWater": high_water,
        "normalActive": len(active),
        "reservedActive": sum(item["inUse"] for item in entities[:reserved]),
        "allocatableActive": sum(item["inUse"] for item in entities[reserved:high_water]),
        "fakeActive": sum(item["inUse"] for item in entities[fake_start:]),
        "sentinelActive": sum(item["inUse"] for item in entities[limit:fake_start]),
        "cleanupFlaggedActive": len(cleanup_flagged),
        "cleanupFlaggedPastDelay": sum(age > layout["temporaryCleanupDelayMs"] for age in cleanup_clock_ages),
        "cleanupFlaggedOldestClockAgeMs": max(cleanup_clock_ages) if cleanup_clock_ages else None,
        "cleanupFlaggedNumericTypes": dict(Counter(item["type"] for item in cleanup_flagged)),
        "numericTypes": dict(Counter(item["type"] for item in active)),
        "freeListCount": len(free_indices), "freeIndices": free_indices,
        "unallocatedNormal": limit - high_water, "headAgeMs": head_age,
        "headReusable": head_age is not None and (high_water == limit or head_age >= layout["reuseDelayMs"]),
        "failureCondition": high_water == limit and not free_indices,
    })
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if output == repo or repo in output.parents:
        raise ValueError("Write game-derived reports outside the repository.")
    if output.exists():
        raise FileExistsError("Choose a new report path.")
    profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
    identity = json.loads(args.identity.read_text(encoding="utf-8-sig"))
    with closing(DumpMemory(args.dump)) as memory:
        module = verify_identity(memory, profile, identity)
        report = inspect_pool(memory, module, profile)
    report.update({"dump": str(args.dump.resolve()), "profile": str(args.profile.resolve()), "sha256": profile["sha256"]})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(output)}))


if __name__ == "__main__":
    main()
