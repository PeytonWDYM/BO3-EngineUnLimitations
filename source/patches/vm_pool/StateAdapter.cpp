#include "StateAdapter.h"
#include <algorithm>

namespace bo3::vm {
namespace {
bool Supported(std::uint32_t total) {
    return total == StockTotal || total == 500001 || total == 1000001;
}
std::uint32_t Read32(const NativePool& native, void* file) {
    std::uint32_t value;
    native.read(file, sizeof(value), &value);
    return value;
}
StateError ExtendFreeChain(const NativePool& native, std::uint32_t sourceTotal) {
    std::uint32_t last = 0, reached = 0;
    for (auto id = native.slots[0].next; id != 0; id = native.slots[id].next) {
        if (id >= sourceTotal || native.slots[id].type != 27 || ++reached >= sourceTotal)
            return StateError::InvalidFreeChain;
        last = id;
    }
    std::uint32_t declared = 0;
    for (std::uint32_t id = 1; id < sourceTotal; ++id)
        declared += native.slots[id].type == 27;
    if (declared != reached) return StateError::InvalidFreeChain;
    if (sourceTotal == native.total) return StateError::None;
    for (auto id = sourceTotal; id < native.total; ++id) {
        native.slots[id] = {};
        native.slots[id].type = 27;
        native.slots[id].next = id + 1 < native.total ? id + 1 : 0;
    }
    native.slots[last].next = sourceTotal;
    return StateError::None;
}
struct ImportScope {
    ImportContext& context;
    ~ImportScope() { context.active = false; }
};
}

std::uint64_t TranslateImportedKey(const ImportContext& context, const Slot& slot, std::uint64_t key) {
    if (!context.active || context.sourceTotal == context.targetTotal || (slot.flags & 7) != 1)
        return key;
    const auto first = static_cast<std::uint64_t>(context.sourceTotal) + 0x20000;
    if (key == first || key == first + 1)
        return key - context.sourceTotal + context.targetTotal;
    return key;
}

StateError ReadState(const NativePool& native, ImportContext& context, std::uint32_t instance, void* file) {
    if (instance == 1) { native.readClient(instance, file); return StateError::None; }
    if (!Supported(native.total)) return StateError::UnsupportedCapacity;
    if (context.active) return StateError::NestedImport;
    auto head = Read32(native, file);
    auto savedTotal = StockTotal;
    auto savedClientRoots = native.stockClientRoots;
    if (head == FormatMagic) {
        const auto version = Read32(native, file);
        savedTotal = Read32(native, file);
        savedClientRoots = Read32(native, file);
        head = Read32(native, file);
        if (version != FormatVersion) return StateError::UnsupportedVersion;
        if (savedTotal != native.total) return StateError::CapacityMismatch;
        if (savedClientRoots != native.clientRoots) return StateError::ClientRootMismatch;
    }
    if (head >= savedTotal) return StateError::InvalidFreeHead;
    std::fill_n(native.buckets, 65536, 0);
    native.slots[0].next = head;
    context = {true, savedTotal, native.total, savedClientRoots};
    ImportScope scope{context};
    for (std::uint32_t id = 1; id < savedTotal; ++id)
        native.readSlot(instance, file, id);
    const auto chain = ExtendFreeChain(native, savedTotal);
    if (chain != StateError::None) return chain;
    native.readTail(instance, file, savedClientRoots);
    return StateError::None;
}

StateError WriteState(const NativePool& native, std::uint32_t instance, void* file) {
    if (instance == 1) { native.writeClient(instance, file); return StateError::None; }
    if (!Supported(native.total)) return StateError::UnsupportedCapacity;
    if (native.total == StockTotal && native.clientRoots != native.stockClientRoots)
        return StateError::ClientRootMismatch;
    if (native.slots[0].next >= native.total) return StateError::InvalidFreeHead;
    if (native.total != StockTotal) {
        native.write32(file, FormatMagic);
        native.write32(file, FormatVersion);
        native.write32(file, native.total);
        native.write32(file, native.clientRoots);
    }
    native.write32(file, native.slots[0].next);
    for (std::uint32_t id = 1; id < native.total; ++id)
        native.writeSlot(instance, file, id);
    native.writeTail(instance, file, native.clientRoots);
    return StateError::None;
}
}
