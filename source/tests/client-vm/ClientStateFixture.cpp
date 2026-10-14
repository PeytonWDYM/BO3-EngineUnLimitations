#include "../../patches/vm_pool/StateAdapter.h"
#include <algorithm>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
using namespace bo3::vm;
constexpr std::uint32_t ClientStock = 65000, ClientMagic = 0x43564d50;
std::vector<Slot> slots;
std::vector<std::uint32_t> buckets;
std::vector<std::byte> stream;
std::size_t cursor;
std::uint32_t reads, tails, stockCalls;
ImportContext* active;
void Need(bool condition) { if (!condition) throw std::runtime_error("client state fixture failed"); }
void Read(void*, std::uint32_t size, void* target) {
    Need(cursor + size <= stream.size());
    std::memcpy(target, stream.data() + cursor, size); cursor += size;
}
void Write32(void*, std::uint32_t value) {
    const auto* bytes = reinterpret_cast<const std::byte*>(&value);
    stream.insert(stream.end(), bytes, bytes + sizeof(value));
}
void ReadSlot(std::uint32_t instance, void* file, std::uint32_t id) {
    Need(instance == 1); Read(file, sizeof(Slot), &slots[id]); ++reads;
    slots[id].key = TranslateImportedKey(*active, slots[id], slots[id].key);
}
void WriteSlot(std::uint32_t instance, void*, std::uint32_t id) {
    Need(instance == 1);
    const auto* bytes = reinterpret_cast<const std::byte*>(&slots[id]);
    stream.insert(stream.end(), bytes, bytes + sizeof(Slot));
}
void Tail(std::uint32_t instance, void*, std::uint32_t roots) {
    Need(instance == 1 && roots == 0); ++tails;
}
void Stock(std::uint32_t instance, void*) { Need(instance == 1); ++stockCalls; }
NativePool Pool(std::uint32_t total) {
    NativePool pool{slots.data(), buckets.data(), total, Read, Write32, ReadSlot, WriteSlot,
                    Tail, Tail, Stock, Stock, 0, 0};
    pool.stockTotal = ClientStock; pool.formatMagic = ClientMagic;
    return pool;
}
void Header(std::uint32_t magic, std::uint32_t version, std::uint32_t total, std::uint32_t roots) {
    stream.clear(); cursor = reads = tails = 0;
    for (auto word : {magic, version, total, roots, 0u}) Write32(nullptr, word);
}
void Refuse(const NativePool& native, ImportContext& context, StateError error) {
    std::fill(buckets.begin(), buckets.end(), 77);
    const auto original = slots[1].key;
    Need(ReadState(native, context, 1, nullptr) == error);
    Need(reads == 0 && tails == 0 && slots[1].key == original);
    Need(std::all_of(buckets.begin(), buckets.end(), [](auto value) { return value == 77; }));
}
void Run(std::uint32_t total) {
    slots.assign(total, {}); buckets.assign(65536, 77);
    auto native = Pool(total);
    ImportContext client{}, server{true, 130000, 500001, 8}; active = &client;
    slots[0].next = 3;
    for (std::uint32_t id = 3; id < ClientStock; ++id) {
        slots[id].type = 27; slots[id].next = id + 1 < ClientStock ? id + 1 : 0;
    }
    for (std::uint32_t id = 1; id <= 2; ++id) {
        slots[id].type = 7; slots[id].flags = 1; slots[id].key = ClientStock + 0x20000 + id - 1;
    }
    stream.clear(); Write32(nullptr, 3);
    for (std::uint32_t id = 1; id < ClientStock; ++id) WriteSlot(1, nullptr, id);
    slots.assign(total, {}); native.slots = slots.data(); cursor = reads = tails = 0;
    Need(ReadState(native, client, 1, nullptr) == StateError::None);
    Need(reads == ClientStock - 1 && tails == 1 && !client.active && server.active);
    Need(cursor == stream.size());
    Need(slots[1].key == total + 0x20000 && slots[2].key == total + 0x20001);
    for (std::uint32_t id = 3; id < total; ++id)
        Need(slots[id].type == 27 && slots[id].next == (id + 1 < total ? id + 1 : 0));
    slots[1].key = 0x100000000ull + total; slots[1].flags = 4;
    stream.clear(); tails = 0;
    Need(WriteState(native, 1, nullptr) == StateError::None && tails == 1);
    Need(stream.size() == 20 + static_cast<std::size_t>(total - 1) * sizeof(Slot));
    std::uint32_t magic; std::memcpy(&magic, stream.data(), 4); Need(magic == ClientMagic);
    const auto expectedKey = slots[1].key;
    slots.assign(total, {}); native.slots = slots.data(); cursor = reads = tails = 0;
    Need(ReadState(native, client, 1, nullptr) == StateError::None);
    Need(reads == total - 1 && tails == 1 && cursor == stream.size() && slots[1].key == expectedKey);
    Header(ClientMagic, 2, total, 0); Refuse(native, client, StateError::UnsupportedVersion);
    Header(ClientMagic, 1, total == 250001 ? 500001 : 250001, 0); Refuse(native, client, StateError::CapacityMismatch);
    Header(ClientMagic, 1, total, 8); Refuse(native, client, StateError::ClientRootMismatch);
    Header(FormatMagic, 1, total, 0); Refuse(native, client, StateError::InvalidFreeHead);
    Header(0x51564d50, 1, total, 0); Refuse(native, client, StateError::InvalidFreeHead);
    Header(ClientMagic, 1, total, 0); client.active = true; Refuse(native, client, StateError::NestedImport); client.active = false;
    auto stock = native; stock.total = ClientStock;
    const auto before = stockCalls;
    Need(ReadState(stock, client, 1, nullptr) == StateError::None);
    Need(WriteState(stock, 1, nullptr) == StateError::None && stockCalls == before + 2);
    stock.total = 0;
    Need(ReadState(stock, client, 1, nullptr) == StateError::UnsupportedCapacity);
    Need(WriteState(stock, 1, nullptr) == StateError::UnsupportedCapacity && stockCalls == before + 2);
    Need(ReadState(native, client, 0, nullptr) == StateError::UnsupportedCapacity);
    Need(WriteState(native, 0, nullptr) == StateError::UnsupportedCapacity);
    stock = native; stock.stockTotal = StockTotal; stock.formatMagic = FormatMagic; stock.total = 500001;
    Need(ReadState(stock, client, 1, nullptr) == StateError::UnsupportedCapacity);
    Need(WriteState(stock, 1, nullptr) == StateError::UnsupportedCapacity && stockCalls == before + 2);
    std::cout << "client codec total=" << total << " stock-import, expanded-roundtrip, namespace, refusal, stock-delegate passed\n";
}
}
int main() { Run(250001); Run(500001); }
