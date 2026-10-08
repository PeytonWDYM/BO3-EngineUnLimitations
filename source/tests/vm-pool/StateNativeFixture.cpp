#include "../../patches/vm_pool/NativeStateBridge.h"
#include <Windows.h>
#include <array>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
using namespace bo3::vm;
std::byte* image;
std::vector<Slot> pool;
std::array<std::uint32_t, 65536> buckets;
std::array<std::byte, 192> tables;
std::vector<std::byte> clients;
std::vector<std::byte> data;
std::size_t cursor;
std::uint32_t associations = 777, insertCount = 0;
std::uint32_t mode;
std::uint32_t Mode() { return mode; }
void Check(bool valid) { if (!valid) throw std::runtime_error("native bridge fixture assertion"); }
template<class T> T& Field(std::size_t offset) { return *reinterpret_cast<T*>(image + offset); }
void Read(void*, std::uint32_t size, void* target) {
    if (cursor + size > data.size()) throw std::runtime_error("owned stream truncated");
    std::memcpy(target, data.data() + cursor, size); cursor += size;
}
void Write(void*, std::uint32_t value) {
    auto* bytes = reinterpret_cast<std::byte*>(&value);
    data.insert(data.end(), bytes, bytes + 4);
}
void Insert(std::uint32_t, std::uint32_t id, std::uint64_t key, std::uint32_t) {
    Check(pool[id].key == key); ++insertCount;
}
void ReadSlot(std::uint32_t instance, void* file, std::uint32_t id) {
    Read(file, 64, &pool[id]);
    if (pool[id].type != 27 && pool[id].reserved12 == 0) InsertNativeStateKey(instance, id, pool[id].key, pool[id].parent);
}
void WriteSlot(std::uint32_t, void*, std::uint32_t id) {
    auto* bytes = reinterpret_cast<std::byte*>(&pool[id]);
    data.insert(data.end(), bytes, bytes + 64);
}
void ReadAssociations(std::uint32_t, void* file) { Read(file, 4, &associations); }
void WriteAssociations(std::uint32_t, void* file) { Write(file, associations); }
void ClientCodec(std::uint32_t instance, void*) { Check(instance == 1); }
void Commit(std::size_t offset) {
    Check(VirtualAlloc(image + (offset & ~std::size_t{4095}), 4096, MEM_COMMIT, PAGE_READWRITE) != nullptr);
}
template<class Function> void Thunk(std::size_t offset, Function function) {
    Commit(offset);
    std::array<std::byte, 12> code{std::byte{0x48}, std::byte{0xb8}};
    auto target = reinterpret_cast<std::uintptr_t>(function);
    std::memcpy(code.data() + 2, &target, 8); code[10] = std::byte{0xff}; code[11] = std::byte{0xe0};
    std::memcpy(image + offset, code.data(), code.size());
    DWORD old;
    Check(VirtualProtect(image + (offset & ~std::size_t{4095}), 4096, PAGE_EXECUTE_READ, &old) != FALSE);
    Check(FlushInstructionCache(GetCurrentProcess(), image + offset, code.size()) != FALSE);
}
std::uint32_t& ClientRoot(std::uint32_t index) {
    return *reinterpret_cast<std::uint32_t*>(clients.data() + static_cast<std::size_t>(index) * 0x171f0 + 0x16b08);
}
void SeedRoots(std::uint32_t count, std::uint32_t baseId = 0) {
    for (std::uint32_t index = 0; index < 9; ++index) Field<std::uint32_t>(0x512471c + index * 4) = baseId + index + 11;
    for (std::uint32_t index = 0; index < 6; ++index) {
        *reinterpret_cast<std::uint32_t*>(tables.data() + index * 32) = baseId + index + 41;
        *reinterpret_cast<std::uint32_t*>(tables.data() + index * 32 + 4) = baseId + index + 71;
    }
    for (std::uint32_t index = 0; index < count; ++index) ClientRoot(index) = baseId + index + 91;
    Field<std::uint32_t>(0x5124718) = baseId + 123;
    associations = baseId + 777;
}
void VerifyRoots(std::uint32_t count, std::uint32_t baseId = 0) {
    for (std::uint32_t index = 0; index < 9; ++index) Check(Field<std::uint32_t>(0x512471c + index * 4) == baseId + index + 11);
    for (std::uint32_t index = 0; index < 6; ++index) {
        Check(*reinterpret_cast<std::uint32_t*>(tables.data() + index * 32) == baseId + index + 41);
        Check(*reinterpret_cast<std::uint32_t*>(tables.data() + index * 32 + 4) == baseId + index + 71);
    }
    for (std::uint32_t index = 0; index < count; ++index) Check(ClientRoot(index) == baseId + index + 91);
    Check(Field<std::uint32_t>(0x5124718) == baseId + 123 && associations == baseId + 777);
}
}

void RunNativeBridgeCases() {
    Check(Bo3VmStateBindings.imageBase == 0 && Bo3VmStateBindings.total == 0 &&
          Bo3VmStateBindings.clientRoots == 0 && Bo3VmStateBindings.stockClientRoots == 0 &&
          Bo3VmStateBindings.originalClientReader == nullptr && Bo3VmStateBindings.originalClientWriter == nullptr &&
          Bo3VmStateBindings.originalInsert == nullptr);
    image = static_cast<std::byte*>(VirtualAlloc(nullptr, 0xa1b1000, MEM_RESERVE, PAGE_NOACCESS));
    Check(image != nullptr);
    struct ReleaseImage { ~ReleaseImage() { VirtualFree(image, 0, MEM_RELEASE); } } release;
    for (auto offset : {0x5124500u, 0x3267228u, 0xa1b0730u}) Commit(offset);
    Thunk(0x22778b0, Read); Thunk(0xd2870, Write);
    Thunk(0x12d5590, ReadSlot); Thunk(0x12d64c0, WriteSlot);
    Thunk(0x1611c0, ReadAssociations); Thunk(0x161310, WriteAssociations);
    Thunk(0x20eac70, Mode);
    pool.assign(500001, {}); clients.assign(10 * 0x171f0, {});
    Field<Slot*>(0x5124580) = pool.data();
    Field<std::uint32_t*>(0x5124500) = buckets.data();
    Field<std::byte*>(0x3267228) = tables.data(); Field<std::byte*>(0xa1b0730) = clients.data();
    for (std::uint32_t id = 3; id < 130000; ++id) {
        pool[id].type = 27; pool[id].next = id < 129999 ? id + 1 : 0;
    }
    pool[0].next = 3; pool[1].type = 21; pool[1].flags = 1; pool[1].key = 261072;
    pool[2].type = 21; pool[2].flags = 1; pool[2].key = 261073; pool[2].reserved12 = 1;
    SeedRoots(4);
    NativeStateBindings binding{reinterpret_cast<std::uintptr_t>(image), 130000, 4, 4, NativeModePolicy::Any, ClientCodec, ClientCodec, Insert};
    Bo3VmStateBindings = binding; data.clear();
    Check(WriteNativeState(0, nullptr) == StateError::None);
    const auto stockBytes = data.size();
    pool.assign(500001, {}); Field<Slot*>(0x5124580) = pool.data();
    clients.assign(10 * 0x171f0, std::byte{0xff}); Field<std::byte*>(0xa1b0730) = clients.data();
    binding.total = 500001; binding.clientRoots = 10; Bo3VmStateBindings = binding; cursor = insertCount = 0;
    Check(ReadNativeState(0, nullptr) == StateError::None);
    Check(cursor == stockBytes && insertCount == 1 && pool[1].key == 631073 && pool[2].key == 631074);
    VerifyRoots(4);
    for (std::uint32_t index = 4; index < 10; ++index) Check(ClientRoot(index) == 0);
    std::cout << "native-bridge-legacy-roots-associations-key-hook-and-ten-client-bounds passed\n";
    SeedRoots(10, 300000); data.clear();
    Check(WriteNativeState(0, nullptr) == StateError::None);
    cursor = 0; associations = 0;
    for (std::uint32_t index = 0; index < 10; ++index) ClientRoot(index) = 0;
    Check(ReadNativeState(0, nullptr) == StateError::None);
    Check(cursor == data.size()); VerifyRoots(10, 300000);
    Check(ReadNativeState(1, nullptr) == StateError::None && WriteNativeState(1, nullptr) == StateError::None);
    std::cout << "native-bridge-expanded-prefix-and-complete-native-tail-roundtrip passed\n";
    // An ordinary key insertion after import must retain its original key.
    pool[1].key = 261072; InsertNativeStateKey(0, 1, 261072, 1); Check(pool[1].key == 261072);
    ClearNativeImportContext();
    std::cout << "native-bridge-import-context-ended passed\n";
    binding.modePolicy = NativeModePolicy::ZombiesOnly; Bo3VmStateBindings = binding;
    const auto beforeSlots = pool;
    const auto beforeData = data;
    const auto beforeBuckets = buckets;
    const auto beforeClients = clients;
    const auto beforeCursor = cursor;
    for (auto rejectedMode : {1u, 2u, 3u, 15u, 0xffffffffu}) {
        mode = rejectedMode;
        Check(ReadNativeState(0, nullptr) == StateError::UnsupportedMode);
        Check(WriteNativeState(0, nullptr) == StateError::UnsupportedMode);
        Check(ReadNativeState(1, nullptr) == StateError::None && WriteNativeState(1, nullptr) == StateError::None);
        Check(cursor == beforeCursor && data == beforeData && buckets == beforeBuckets && clients == beforeClients);
        Check(std::memcmp(pool.data(), beforeSlots.data(), pool.size() * sizeof(Slot)) == 0);
    }
    mode = 0; data.clear();
    Check(WriteNativeState(0, nullptr) == StateError::None);
    std::cout << "native-bridge-zombies-only-policy-refusal-before-state-and-stream-mutation passed\n";
}
