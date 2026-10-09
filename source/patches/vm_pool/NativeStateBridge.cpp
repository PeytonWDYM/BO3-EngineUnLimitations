#include "NativeStateBridge.h"
#include <cstddef>
#include <cstdint>

namespace bo3::vm {
extern "C" {
__declspec(dllexport) constinit NativeStateBindings Bo3VmStateBindings{};
}
namespace {
constinit NativeStateBindings& bindings = Bo3VmStateBindings;
__declspec(thread) constinit ImportContext importing{false, 0, 0, 0};

template<class T> T& Global(std::uintptr_t rva) {
    return *reinterpret_cast<T*>(bindings.imageBase + rva);
}
template<class T> T Function(std::uintptr_t rva) {
    return reinterpret_cast<T>(bindings.imageBase + rva);
}
using ReadFunction = void (*)(void*, std::uint32_t, void*);
using WriteFunction = void (*)(void*, std::uint32_t);
void ReadSlot(std::uint32_t instance, void* file, std::uint32_t id) {
    Function<SlotFunction>(0x12d5590)(instance, file, id);
    auto& slot = Global<Slot*>(0x5124580)[id];
    // Records without a saved hash entry must still retain the translated namespace.
    slot.key = TranslateImportedKey(importing, slot, slot.key);
}
std::uint32_t Read32(void* file) {
    std::uint32_t value;
    Function<ReadFunction>(0x22778b0)(file, 4, &value);
    return value;
}
void Write32(void* file, std::uint32_t value) {
    Function<WriteFunction>(0xd2870)(file, value);
}
std::uint32_t& ClientRoot(std::uint32_t index) {
    auto* clients = Global<std::byte*>(0xa1b0730);
    return *reinterpret_cast<std::uint32_t*>(clients + static_cast<std::size_t>(index) * 0x171f0 + 0x16b08);
}

// These fields follow the pool in both captured whole-state routines.
void ReadTail(std::uint32_t instance, void* file, std::uint32_t savedClients) {
    for (std::uint32_t index = 0; index < 9; ++index)
        Global<std::uint32_t>(0x512471c + instance * 0x78 + index * 4) = Read32(file);
    auto* tables = Global<std::byte*>(0x3267228 + instance * 8);
    for (std::uint32_t index = 0; index < 6; ++index) {
        *reinterpret_cast<std::uint32_t*>(tables + index * 0x20) = Read32(file);
        *reinterpret_cast<std::uint32_t*>(tables + index * 0x20 + 4) = Read32(file);
    }
    Function<WholeFunction>(0x1611c0)(instance, file);
    for (std::uint32_t index = 0; index < savedClients; ++index)
        ClientRoot(index) = Read32(file);
    for (auto index = savedClients; index < bindings.clientRoots; ++index)
        ClientRoot(index) = 0;
    Global<std::uint32_t>(0x5124718 + instance * 0x78) = Read32(file);
}
void WriteTail(std::uint32_t instance, void* file, std::uint32_t clients) {
    for (std::uint32_t index = 0; index < 9; ++index)
        Write32(file, Global<std::uint32_t>(0x512471c + instance * 0x78 + index * 4));
    auto* tables = Global<std::byte*>(0x3267228 + instance * 8);
    for (std::uint32_t index = 0; index < 6; ++index) {
        Write32(file, *reinterpret_cast<std::uint32_t*>(tables + index * 0x20));
        Write32(file, *reinterpret_cast<std::uint32_t*>(tables + index * 0x20 + 4));
    }
    Function<WholeFunction>(0x161310)(instance, file);
    for (std::uint32_t index = 0; index < clients; ++index)
        Write32(file, ClientRoot(index));
    Write32(file, Global<std::uint32_t>(0x5124718 + instance * 0x78));
}
NativePool Pool() {
    return {Global<Slot*>(0x5124580), Global<std::uint32_t*>(0x5124500), bindings.total,
            Function<ReadFunction>(0x22778b0), Function<WriteFunction>(0xd2870),
            ReadSlot, Function<SlotFunction>(0x12d64c0),
            ReadTail, WriteTail, bindings.originalClientReader, bindings.originalClientWriter,
            bindings.clientRoots, bindings.stockClientRoots};
}
bool ModeAllowed(std::uint32_t instance) {
    return instance == 1 || bindings.modePolicy == NativeModePolicy::Any
        || Function<std::uint32_t (*)()>(0x20eac70)() == 0;
}
}

void BindNativeState(const NativeStateBindings& verified) { bindings = verified; }
StateError ReadNativeState(std::uint32_t instance, void* file) {
    if (!ModeAllowed(instance)) return StateError::UnsupportedMode;
    return ReadState(Pool(), importing, instance, file);
}
StateError WriteNativeState(std::uint32_t instance, void* file) {
    if (!ModeAllowed(instance)) return StateError::UnsupportedMode;
    return WriteState(Pool(), instance, file);
}
void InsertNativeStateKey(std::uint32_t instance, std::uint32_t id, std::uint64_t key, std::uint32_t parent) {
    if (instance == 0 && importing.active) {
        auto& slot = Global<Slot*>(0x5124580)[id];
        key = TranslateImportedKey(importing, slot, key);
        slot.key = key;
    }
    bindings.originalInsert(instance, id, key, parent);
}
void ClearNativeImportContext() { importing = {}; }
}
