"""Measure script-variable slots from repeated equal external reads."""

from collections import Counter
import struct

from profile import Instance


def metadata(process, instances: list[Instance]):
    base = process.module.baseaddress
    return [{"pool": process.number(base + instance.pool_rva, "Q"),
             "deferred": process.number(base + instance.deferred_rva, "I"),
             "error": process.number(base + instance.error_rva, "Q"),
             "depth": process.number(base + instance.depth_rva, "I")}
            for instance in instances]


def first_error(process, pointer: int, maximum: int):
    if not pointer:
        return {"pointer": None, "status": "none", "text": None}, b""
    data = b""
    while len(data) < maximum:
        address = pointer + len(data)
        size = min(maximum - len(data), 4096 - address % 4096)
        try:
            chunk = process.read(address, size)
        except OSError:
            return {"pointer": hex(pointer), "status": "unreadable", "text": None}, None
        end = chunk.find(b"\0")
        if end >= 0:
            data += chunk[:end]
            return {"pointer": hex(pointer), "status": "readable", "text": data.decode("utf-8", errors="replace")}, data
        data += chunk
    return {"pointer": hex(pointer), "status": "truncated", "text": data.decode("utf-8", errors="replace")}, data


def read_pools(process, instances, state):
    pools = []
    for instance, item in zip(instances, state):
        size = instance.capacity * 64
        if item["pool"] > (1 << 64) - size:
            raise ValueError("The VM pool address exceeds the address space.")
        pools.append(process.read(item["pool"], size) if item["pool"] else None)
    return pools


def inspect(instance: Instance, state: dict, pool: bytes | None, error: dict):
    report = {"index": instance.index, "capacity": instance.capacity, "usableCapacity": instance.capacity - 1,
              "poolPointer": hex(state["pool"]) if state["pool"] else None,
              "deferredHead": state["deferred"], "firstError": error,
              "currentFunctionDepth": state["depth"]}
    if pool is None:
        if state["deferred"]:
            raise ValueError("An uninitialized pool has a deferred head.")
        return report | {"status": "uninitialized", "free": None, "allocated": None, "numericTypes": None,
                         "reuseList": None, "deferredCount": None}
    types = [struct.unpack_from("<I", pool, index * 64 + 8)[0] for index in range(instance.capacity)]
    links = [struct.unpack_from("<I", pool, index * 64 + 24)[0] for index in range(instance.capacity)]

    def chain(head, required_type, name):
        seen = set()
        index = head
        while index:
            if not 0 < index < instance.capacity:
                raise ValueError(f"The {name} chain contains an out-of-range slot.")
            if index in seen:
                raise ValueError(f"The {name} chain contains a cycle.")
            if types[index] != required_type:
                raise ValueError(f"The {name} chain has a numeric type disagreement.")
            seen.add(index)
            index = links[index]
        return seen

    free = chain(links[0], 27, "reuse")
    if free != {index for index in range(1, instance.capacity) if types[index] == 27}:
        raise ValueError("The reuse chain disagrees with the free-type slot count.")
    deferred = chain(state["deferred"], 23, "deferred")
    if free & deferred:
        raise ValueError("The reuse and deferred chains overlap.")
    return report | {"status": "initialized", "free": len(free), "allocated": instance.capacity - 1 - len(free),
                     "numericTypes": {str(number): count for number, count in sorted(Counter(types[1:]).items())},
                     "reuseList": {"valid": True, "head": links[0], "count": len(free)},
                     "deferredCount": len(deferred)}


def sample(process, profile, instances, attempts, *, enhanced_session=None):
    error = ""
    for attempt in range(1, attempts + 1):
        try:
            if enhanced_session is not None:
                enhanced_session.authorize(profile, process)
            before = metadata(process, instances)
            first = read_pools(process, instances, before)
            first_errors = [first_error(process, item["error"], profile["errorMessageMaximumBytes"]) for item in before]
            middle = metadata(process, instances)
            if enhanced_session is not None:
                enhanced_session.authorize(profile, process)
            second = read_pools(process, instances, middle)
            second_errors = [first_error(process, item["error"], profile["errorMessageMaximumBytes"]) for item in middle]
            after = metadata(process, instances)
            if before != middle or before != after or first != second or first_errors != second_errors:
                raise ValueError("The VM state changed between repeated reads.")
            if not process.alive():
                raise ProcessLookupError("The process exited during capture.")
            return [inspect(instance, item, pool, text[0]) for instance, item, pool, text
                    in zip(instances, before, first, first_errors)], None, attempt
        except (ValueError, OSError) as problem:
            error = str(problem)
            if not process.alive():
                break
    return None, error, attempt
