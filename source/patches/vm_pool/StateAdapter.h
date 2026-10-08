#pragma once
#include <cstddef>
#include <cstdint>

namespace bo3::vm {
inline constexpr std::uint32_t StockTotal = 130000;
inline constexpr std::uint32_t FormatMagic = 0x33564d50;
inline constexpr std::uint32_t FormatVersion = 1;

struct Slot {
    std::uint64_t value;
    std::uint32_t type, reserved12, flags, reserved20;
    std::uint32_t next, association, refs, reserved36;
    std::uint64_t key;
    std::uint32_t siblingNext, siblingPrevious, parent, collision;
};
static_assert(sizeof(Slot) == 64);
static_assert(offsetof(Slot, key) == 0x28 && offsetof(Slot, next) == 0x18);

enum class StateError {
    None, UnsupportedCapacity, UnsupportedVersion, CapacityMismatch,
    InvalidFreeHead, InvalidFreeChain, NestedImport, ClientRootMismatch, UnsupportedMode
};
struct ImportContext {
    bool active;
    std::uint32_t sourceTotal, targetTotal;
    std::uint32_t sourceClientRoots;
};
using WholeFunction = void (*)(std::uint32_t, void*);
using SlotFunction = void (*)(std::uint32_t, void*, std::uint32_t);
using TailFunction = void (*)(std::uint32_t, void*, std::uint32_t);
struct NativePool {
    Slot* slots;
    std::uint32_t* buckets;
    std::uint32_t total;
    void (*read)(void*, std::uint32_t, void*);
    void (*write32)(void*, std::uint32_t);
    SlotFunction readSlot, writeSlot;
    TailFunction readTail, writeTail;
    WholeFunction readClient, writeClient;
    std::uint32_t clientRoots, stockClientRoots;
};

// The native insertion hook calls this after decoding a key and before inserting it.
std::uint64_t TranslateImportedKey(const ImportContext&, const Slot&, std::uint64_t key);
StateError ReadState(const NativePool&, ImportContext&, std::uint32_t instance, void* file);
StateError WriteState(const NativePool&, std::uint32_t instance, void* file);
}
