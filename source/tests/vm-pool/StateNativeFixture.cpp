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
std::vector<Slot> clientPool;
std::array<std::uint32_t, 65536> buckets;
std::array<std::uint32_t, 65536> clientBuckets;
std::array<std::byte, 192> tables;
std::array<std::byte, 192> clientTables;
std::vector<std::byte> clients;
std::vector<std::byte> data;
std::size_t cursor;
std::uint32_t associations = 777, insertCount = 0;
std::uint32_t clientAssociations;
bool probeServerInsert;
bool interruptImport;
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
void Insert(std::uint32_t instance, std::uint32_t id, std::uint64_t key, std::uint32_t) {
    Check((instance == 1 ? clientPool : pool)[id].key == key); ++insertCount;
}
void ReadSlot(std::uint32_t instance, void* file, std::uint32_t id) {
    if (interruptImport) RaiseException(0xe0000001, 0, 0, nullptr);
    auto& slot = (instance == 1 ? clientPool : pool)[id];
    Read(file, 64, &slot);
    if (probeServerInsert && instance == 1 && id == 1) {
        const auto key = pool[1].key;
        InsertNativeStateKey(0, 1, key, 1);
        Check(pool[1].key == key);
    }
    if (slot.type != 27 && slot.reserved12 == 0) InsertNativeStateKey(instance, id, slot.key, slot.parent);
}
void WriteSlot(std::uint32_t instance, void*, std::uint32_t id) {
    auto* bytes = reinterpret_cast<std::byte*>(&(instance == 1 ? clientPool : pool)[id]);
    data.insert(data.end(), bytes, bytes + 64);
}
void ReadAssociations(std::uint32_t instance, void* file) { Read(file, 4, instance == 1 ? &clientAssociations : &associations); }
void WriteAssociations(std::uint32_t instance, void* file) { Write(file, instance == 1 ? clientAssociations : associations); }
void ClientCodec(std::uint32_t instance, void*) { Check(instance == 1); }
// The native engine error path can leave the adapter without C++ scope cleanup.
bool InterruptNativeImport(std::uint32_t instance) {
    __try { ReadNativeState(instance, nullptr); }
    __except (GetExceptionCode() == 0xe0000001 ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) {
        return true;
    }
    return false;
}
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
void SeedRoots(std::uint32_t count, std::uint32_t baseId = 0, std::uint32_t instance = 0) {
    auto& instanceTables = instance == 1 ? clientTables : tables;
    for (std::uint32_t index = 0; index < 9; ++index) Field<std::uint32_t>(0x512471c + instance * 0x78 + index * 4) = baseId + index + 11;
    for (std::uint32_t index = 0; index < 6; ++index) {
        *reinterpret_cast<std::uint32_t*>(instanceTables.data() + index * 32) = baseId + index + 41;
        *reinterpret_cast<std::uint32_t*>(instanceTables.data() + index * 32 + 4) = baseId + index + 71;
    }
    for (std::uint32_t index = 0; index < count; ++index) ClientRoot(index) = baseId + index + 91;
    Field<std::uint32_t>(0x5124718 + instance * 0x78) = baseId + 123;
    (instance == 1 ? clientAssociations : associations) = baseId + 777;
}
void VerifyRoots(std::uint32_t count, std::uint32_t baseId = 0, std::uint32_t instance = 0) {
    auto& instanceTables = instance == 1 ? clientTables : tables;
    for (std::uint32_t index = 0; index < 9; ++index) Check(Field<std::uint32_t>(0x512471c + instance * 0x78 + index * 4) == baseId + index + 11);
    for (std::uint32_t index = 0; index < 6; ++index) {
        Check(*reinterpret_cast<std::uint32_t*>(instanceTables.data() + index * 32) == baseId + index + 41);
        Check(*reinterpret_cast<std::uint32_t*>(instanceTables.data() + index * 32 + 4) == baseId + index + 71);
    }
    for (std::uint32_t index = 0; index < count; ++index) Check(ClientRoot(index) == baseId + index + 91);
    Check(Field<std::uint32_t>(0x5124718 + instance * 0x78) == baseId + 123 &&
          (instance == 1 ? clientAssociations : associations) == baseId + 777);
}

void RunExpandedClientBridgeCases(NativeStateBindings binding) {
    const auto savedBinding = Bo3VmStateBindings;
    const auto savedClients = clients;
    clientPool.assign(250001, {}); clients.assign(18 * 0x171f0, {});
    Field<Slot*>(0x5124680) = clientPool.data();
    Field<std::uint32_t*>(0x5124600) = clientBuckets.data();
    Field<std::byte*>(0x3267230) = clientTables.data();
    Field<std::byte*>(0xa1b0730) = clients.data();
    clientPool[0].next = 3;
    for (std::uint32_t id = 3; id < 65000; ++id) {
        clientPool[id].type = 27; clientPool[id].next = id + 1 < 65000 ? id + 1 : 0;
    }
    for (std::uint32_t id = 1; id <= 2; ++id) {
        clientPool[id].type = 7; clientPool[id].flags = 1;
        clientPool[id].key = 65000 + 0x20000 + id - 1;
    }
    clientPool[2].reserved12 = 1;
    for (std::uint32_t index = 0; index < 18; ++index) ClientRoot(index) = 170000 + index;
    const auto sharedClientsBefore = clients;
    SeedRoots(0, 40000, 1);
    data.clear(); Write(nullptr, 3);
    for (std::uint32_t id = 1; id < 65000; ++id) WriteSlot(1, nullptr, id);
    for (std::uint32_t index = 0; index < 9; ++index)
        Write(nullptr, Field<std::uint32_t>(0x5124794 + index * 4));
    for (std::uint32_t index = 0; index < 6; ++index) {
        Write(nullptr, *reinterpret_cast<std::uint32_t*>(clientTables.data() + index * 32));
        Write(nullptr, *reinterpret_cast<std::uint32_t*>(clientTables.data() + index * 32 + 4));
    }
    WriteAssociations(1, nullptr);
    Write(nullptr, Field<std::uint32_t>(0x5124790));
    const auto legacyEnd = data.size(); Write(nullptr, 0xdeadbeef);
    pool[1].key = 65000 + 0x20000;
    const auto serverBefore = pool;
    const auto bucketsBefore = buckets;
    const auto tablesBefore = tables;
    std::array<std::uint32_t, 10> serverRoots;
    for (std::uint32_t index = 0; index < 10; ++index)
        serverRoots[index] = Field<std::uint32_t>(0x5124718 + index * 4);
    binding.clientTotal = 250001; binding.clientRoots = 18; binding.stockClientRoots = 8;
    Bo3VmStateBindings = binding;
    clientPool.assign(250001, {}); Field<Slot*>(0x5124680) = clientPool.data();
    clientBuckets.fill(77); cursor = 0; probeServerInsert = true;
    Check(ReadNativeState(1, nullptr) == StateError::None && cursor == legacyEnd);
    std::uint32_t following; Read(nullptr, 4, &following); Check(following == 0xdeadbeef && cursor == data.size());
    probeServerInsert = false;
    Check(clientPool[1].key == 381073 && clientPool[2].key == 381074);
    VerifyRoots(0, 40000, 1);
    Check(clients == sharedClientsBefore);
    for (std::uint32_t id = 3; id < 250001; ++id)
        Check(clientPool[id].type == 27 && clientPool[id].next == (id + 1 < 250001 ? id + 1 : 0));
    Check(buckets == bucketsBefore && tables == tablesBefore);
    Check(std::memcmp(pool.data(), serverBefore.data(), pool.size() * sizeof(Slot)) == 0);
    for (std::uint32_t index = 0; index < 10; ++index)
        Check(Field<std::uint32_t>(0x5124718 + index * 4) == serverRoots[index]);
    SeedRoots(0, 150000, 1);
    clientPool[249999].next = 0;
    clientPool[250000] = {}; clientPool[250000].type = 7;
    clientPool[250000].key = 0x100000000ull + 250000;
    data.clear(); Check(WriteNativeState(1, nullptr) == StateError::None);
    std::uint32_t magic; std::memcpy(&magic, data.data(), 4); Check(magic == ClientFormatMagic);
    const auto expectedPool = clientPool;
    clientPool.assign(250001, {}); Field<Slot*>(0x5124680) = clientPool.data();
    clientBuckets.fill(77); cursor = 0;
    Check(ReadNativeState(1, nullptr) == StateError::None && cursor == data.size());
    Check(std::memcmp(clientPool.data(), expectedPool.data(), clientPool.size() * sizeof(Slot)) == 0);
    VerifyRoots(0, 150000, 1); Check(clients == sharedClientsBefore);
    for (auto rejectedMode : {1u, 2u, 3u, 15u, 0xffffffffu}) {
        mode = rejectedMode;
        const auto savedData = data; const auto savedCursor = cursor;
        Check(ReadNativeState(1, nullptr) == StateError::UnsupportedMode);
        Check(WriteNativeState(1, nullptr) == StateError::UnsupportedMode);
        Check(data == savedData && cursor == savedCursor);
        Check(std::memcmp(clientPool.data(), expectedPool.data(), clientPool.size() * sizeof(Slot)) == 0);
    }
    mode = 0;
    ClearNativeImportContext();
    data.clear(); Write(nullptr, 1); interruptImport = true;
    for (auto instance : {0u, 1u}) {
        cursor = 0;
        Check(InterruptNativeImport(instance));
    }
    interruptImport = false;
    const auto errorCursor = cursor;
    Check(ReadNativeState(0, nullptr) == StateError::NestedImport);
    Check(ReadNativeState(1, nullptr) == StateError::NestedImport && cursor == errorCursor);
    for (auto instance : {0u, 1u}) {
        auto& slot = (instance == 1 ? clientPool : pool)[1];
        const auto sourceKey = (instance == 1 ? StockClientTotal : StockTotal) + 0x20000;
        slot.flags = 1; slot.key = sourceKey;
        InsertNativeStateKey(instance, 1, sourceKey, 1);
        Check(slot.key != sourceKey);
    }
    ClearNativeImportContext();
    for (auto instance : {0u, 1u}) {
        auto& slot = (instance == 1 ? clientPool : pool)[1];
        const auto sourceKey = (instance == 1 ? StockClientTotal : StockTotal) + 0x20000;
        slot.key = sourceKey; InsertNativeStateKey(instance, 1, sourceKey, 1);
        Check(slot.key == sourceKey);
    }
    std::cout << "native-both-import-contexts-cleared-after-owned-seh-engine-error passed\n";
    const auto ordinaryKey = 65000 + 0x20000;
    clientPool[1].key = ordinaryKey; InsertNativeStateKey(1, 1, ordinaryKey, 1);
    Check(clientPool[1].key == ordinaryKey);
    binding.clientTotal = 0; Bo3VmStateBindings = binding;
    const auto savedData = data; const auto savedCursor = cursor;
    Check(ReadNativeState(1, nullptr) == StateError::UnsupportedCapacity);
    Check(WriteNativeState(1, nullptr) == StateError::UnsupportedCapacity);
    Check(data == savedData && cursor == savedCursor);
    Bo3VmStateBindings = savedBinding; clients = savedClients;
    Field<std::byte*>(0xa1b0730) = clients.data();
    std::cout << "native-client-bridge-stock-import-250k-state-complete-owned-tail-instance-isolation-and-zero-binding-refusal passed\n";
}
}

void RunNativeBridgeCases() {
    Check(Bo3VmStateBindings.imageBase == 0 && Bo3VmStateBindings.total == 0 &&
          Bo3VmStateBindings.clientRoots == 0 && Bo3VmStateBindings.stockClientRoots == 0 &&
          Bo3VmStateBindings.originalClientReader == nullptr && Bo3VmStateBindings.originalClientWriter == nullptr &&
          Bo3VmStateBindings.originalInsert == nullptr && Bo3VmStateBindings.clientTotal == 0);
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
    NativeStateBindings binding{reinterpret_cast<std::uintptr_t>(image), 130000, 4, 4, NativeModePolicy::Any, ClientCodec, ClientCodec, Insert, 65000};
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
    RunExpandedClientBridgeCases(binding);
}
