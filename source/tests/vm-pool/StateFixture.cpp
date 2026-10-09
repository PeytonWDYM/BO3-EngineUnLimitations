#include "../../patches/vm_pool/StateAdapter.h"
#include <algorithm>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace bo3::vm;
void RunNativeBridgeCases();
namespace {
std::vector<std::byte> stream;
std::size_t cursor;
std::vector<Slot> slots;
std::vector<std::uint32_t> buckets;
std::vector<std::uint64_t> inserted;
std::uint32_t readCalls, writeCalls, tails;
ImportContext* active;

void Need(bool condition) { if (!condition) throw std::runtime_error("fixture assertion"); }
void Read(void*, std::uint32_t size, void* target) {
    if (cursor + size > stream.size()) throw std::runtime_error("truncated fixture stream");
    std::memcpy(target, stream.data() + cursor, size);
    cursor += size;
}
void Write32(void*, std::uint32_t value) {
    const auto bytes = reinterpret_cast<const std::byte*>(&value);
    stream.insert(stream.end(), bytes, bytes + 4);
}
void ReadSlot(std::uint32_t instance, void* file, std::uint32_t id) {
    Need(instance == 0);
    Read(file, sizeof(Slot), &slots[id]);
    ++readCalls;
    const auto key = TranslateImportedKey(*active, slots[id], slots[id].key);
    slots[id].key = key;
    inserted.push_back(key);
}
void WriteSlot(std::uint32_t instance, void*, std::uint32_t id) {
    Need(instance == 0);
    const auto bytes = reinterpret_cast<const std::byte*>(&slots[id]);
    stream.insert(stream.end(), bytes, bytes + sizeof(Slot));
    ++writeCalls;
}
void Tail(std::uint32_t, void*, std::uint32_t count) { Need(count == 4 || count == 10); ++tails; }
void Client(std::uint32_t instance, void*) { Need(instance == 1); ++tails; }
void Cases() {
    slots.assign(500001, {});
    buckets.assign(65536, 77);
    active = nullptr;
    NativePool native{slots.data(), buckets.data(), 500001, Read, Write32, ReadSlot, WriteSlot, Tail, Tail, Client, Client, 10, 4};
    ImportContext context{};
    active = &context;
    for (std::uint32_t id = 1; id < 130000; ++id) {
        slots[id].type = 27;
        slots[id].next = id + 1 < 130000 ? id + 1 : 0;
    }
    slots[1].type = 21;
    slots[1].flags = 1;
    slots[1].key = 130000 + 131072;
    slots[2].type = 7;
    slots[2].flags = 4;
    slots[2].key = 129999;
    stream.clear(); Write32(nullptr, 3);
    for (std::uint32_t id = 1; id < 130000; ++id) WriteSlot(0, nullptr, id);
    slots.assign(500001, {}); native.slots = slots.data();
    cursor = readCalls = tails = 0; inserted.clear();
    Need(ReadState(native, context, 0, nullptr) == StateError::None);
    Need(readCalls == 129999 && tails == 1 && cursor == stream.size());
    Need(slots[1].key == 500001 + 131072 && inserted[0] == slots[1].key);
    Need(slots[2].key == 129999 && slots[129999].next == 130000);
    Need(slots.back().next == 0 && slots.back().type == 27 && slots[0].next == 3);
    Need(!context.active && std::all_of(buckets.begin(), buckets.end(), [](auto n) { return n == 0; }));
    std::uint32_t count = 0;
    for (auto id = slots[0].next; id != 0; id = slots[id].next) { Need(id < slots.size()); ++count; }
    Need(count == 499998);
    std::cout << "legacy-129999-records-extra-freechain-translated-before-insert passed\n";

    for (const auto category : {2u, 3u, 4u, 5u}) {
        Slot value{}; value.flags = category; value.key = 261072;
        context = {true, 130000, 500001, 4};
        Need(TranslateImportedKey(context, value, value.key) == 261072);
    }
    std::cout << "typed-key-categories-preserved passed\n";
    context = {};
    stream.clear(); writeCalls = tails = 0;
    Need(WriteState(native, 0, nullptr) == StateError::None);
    Need(writeCalls == 500000 && tails == 1);
    auto expected = slots;
    slots.assign(500001, {}); native.slots = slots.data();
    cursor = readCalls = tails = 0;
    Need(ReadState(native, context, 0, nullptr) == StateError::None);
    Need(readCalls == 500000 && cursor == stream.size());
    Need(std::memcmp(slots.data(), expected.data(), slots.size() * sizeof(Slot)) == 0);
    std::cout << "expanded-500k-fixed-owned-record-roundtrip passed\n";
    // Header admission must happen before any pool or hash-table mutation.
    for (const auto error : {StateError::UnsupportedVersion, StateError::CapacityMismatch, StateError::InvalidFreeHead, StateError::ClientRootMismatch}) {
        stream.clear(); Write32(nullptr, FormatMagic);
        Write32(nullptr, error == StateError::UnsupportedVersion ? 9 : FormatVersion);
        Write32(nullptr, error == StateError::CapacityMismatch ? 1000001 : 500001);
        Write32(nullptr, error == StateError::ClientRootMismatch ? 11 : 10);
        Write32(nullptr, error == StateError::InvalidFreeHead ? 500001 : 0);
        slots[0].next = 123; buckets[0] = 456; cursor = readCalls = 0;
        Need(ReadState(native, context, 0, nullptr) == error);
        Need(slots[0].next == 123 && buckets[0] == 456 && readCalls == 0);
    }
    std::cout << "header-refusal-before-runtime-mutation passed\n";
    // Exercise the declared invalid-chain cases through the complete legacy import.
    for (const auto failure : {0, 1, 2, 3}) {
        slots.assign(500001, {});
        for (std::uint32_t id = 1; id < StockTotal; ++id) {
            slots[id].type = 27;
            slots[id].next = id + 1 < StockTotal ? id + 1 : 0;
        }
        if (failure == 0) slots[StockTotal - 1].next = 1;
        if (failure == 1) slots[5].next = StockTotal;
        if (failure == 2) slots[3].type = 21;
        if (failure == 3) slots[3].next = 5;
        stream.clear(); Write32(nullptr, 1);
        for (std::uint32_t id = 1; id < StockTotal; ++id) WriteSlot(0, nullptr, id);
        slots.assign(500001, {}); native.slots = slots.data();
        for (std::uint32_t id = StockTotal; id < native.total; ++id) slots[id].type = 17;
        cursor = readCalls = tails = 0;
        Need(ReadState(native, context, 0, nullptr) == StateError::InvalidFreeChain);
        Need(readCalls == StockTotal - 1 && cursor == stream.size() && tails == 0 && !context.active);
        Need(std::all_of(slots.begin() + StockTotal, slots.end(), [](const auto& value) {
            return value.type == 17 && value.next == 0;
        }));
    }
    std::cout << "legacy-cycle-range-occupied-disconnected-refusal-before-extension passed\n";
    native.total = 130000; native.slots = expected.data(); native.clientRoots = 4;
    stream.clear(); writeCalls = tails = 0;
    Need(WriteState(native, 0, nullptr) == StateError::None);
    Need(writeCalls == 129999);
    std::uint32_t first; std::memcpy(&first, stream.data(), 4); Need(first != FormatMagic);
    native.clientRoots = 10; stream.clear(); writeCalls = 0;
    Need(WriteState(native, 0, nullptr) == StateError::ClientRootMismatch && stream.empty() && writeCalls == 0);
    std::cout << "stock-runtime-stock-format passed\n";
    Need(ReadState(native, context, 1, nullptr) == StateError::None);
    Need(WriteState(native, 1, nullptr) == StateError::None);
    std::cout << "client-original-whole-functions passed\n";
}
}
int main() {
    try { Cases(); RunNativeBridgeCases(); return 0; }
    catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
