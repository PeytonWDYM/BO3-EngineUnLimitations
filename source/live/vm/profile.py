"""Validate bounded VM layouts without public executable addresses."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Instance:
    index: int
    capacity: int
    pool_rva: int
    deferred_rva: int
    error_rva: int
    depth_rva: int


def integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Invalid {name}.")
    return value


def validate(profile: dict, *, enhanced_session=None) -> list[Instance]:
    if profile["status"] not in ("fixture-only", "game-validated"):
        raise ValueError("The VM profile is disabled. Separate game validation is required.")
    # These fields use full native DWORD comparisons, without packed type masks.
    layout = {"slotStride": 64, "reservedZeroIndex": 0, "typeOffset": 8, "typeFormat": "I",
              "freeNumericType": 27, "linkOffset": 24, "linkFormat": "I",
              "deferredEntityHeadFormat": "I", "deferredEntityNumericType": 23,
              "firstErrorMessagePointerFormat": "Q", "currentFunctionDepthFormat": "I"}
    for name, expected in layout.items():
        if type(profile[name]) is not type(expected) or profile[name] != expected:
            raise ValueError(f"Unsupported VM layout field: {name}.")
    if profile["reuseHead"] != {"slotIndex": 0, "offset": 24, "format": "I"}:
        raise ValueError("Unsupported reuse head layout.")
    integer(profile["errorMessageMaximumBytes"], "error message bound", 1, 1024)
    image_size = integer(profile["imageSize"], "image size", 88, 0xFFFFFFFF)
    fields = (("poolPointerRva", "instancePointerStride", 8),
              ("deferredEntityHeadRva", "variablePublicInstanceStride", 4),
              ("firstErrorMessagePointerRva", "variablePublicInstanceStride", 8),
              ("currentFunctionDepthRva", "currentFunctionDepthInstanceStride", 4))
    if not 1 <= len(profile["instances"]) <= 2:
        raise ValueError("Use one or two VM instances.")
    result = []
    for item in profile["instances"]:
        index = integer(item["index"], "instance index", 0, 1)
        capacity = integer(item["capacity"], "pool capacity", 2, 130000)
        addresses = []
        for name, stride, size in fields:
            rva = integer(profile[name], name, 0, image_size - size)
            step = integer(profile[stride], stride, 0, image_size)
            addresses.append(integer(rva + index * step, name, 0, image_size - size))
        result.append(Instance(index, capacity, *addresses))
    if len({instance.index for instance in result}) != len(result):
        raise ValueError("VM instance indices must be unique.")
    if enhanced_session is not None:
        from enhanced_session import EnhancedSession
        if type(enhanced_session) is not EnhancedSession:
            raise ValueError("Expanded capacity requires runtime session enrollment.")
        enhanced_session.authorize(profile)
        if not any(instance.index == 0 and instance.capacity == 130000 for instance in result):
            raise ValueError("Enhanced enrollment requires the stock server layout.")
        if any(instance.index == 1 and instance.capacity != 65000 for instance in result):
            raise ValueError("Enhanced enrollment preserves the stock client capacity.")
        result = [Instance(instance.index, 500001 if instance.index == 0 else instance.capacity,
                           instance.pool_rva, instance.deferred_rva, instance.error_rva, instance.depth_rva)
                  for instance in result]
    return result
