#include "../../patches/vm_migration/Admission.h"
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <array>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace bo3::migration;
extern "C" std::uint32_t TestMigrationVersion(std::uint32_t);
namespace {
std::uint32_t Accepted() { return 1; }
std::uint32_t Rejected() { return 0; }
std::uint32_t loaded, dropped;
std::uint32_t flushed;
std::uint32_t receivedHeaders, receivedData, receivedAcks, sentHeaders, sentAcks;
Header current;
WrittenState written{nullptr, 0, 25000000};
std::vector<std::byte> ack;
std::vector<std::uint32_t> calls;
void Check(bool value) { if (!value) throw std::runtime_error("migration fixture assertion"); }
void CheckUnwind(void (*entry)(), std::uint32_t offset, bool dataFrame, bool flushFrame = false) {
    const auto pc = reinterpret_cast<DWORD64>(entry) + offset;
    DWORD64 imageBase = 0;
    auto* function = RtlLookupFunctionEntry(pc, &imageBase, nullptr); Check(function != nullptr);
    alignas(16) std::array<DWORD64, 16> stack{};
    constexpr DWORD64 sentinel = 0x123456789abcdef0;
    CONTEXT context{}; context.Rip = pc; context.Rsp = reinterpret_cast<DWORD64>(stack.data());
    if (dataFrame) { stack[0] = 14; stack[1] = 15; stack[2] = 16; stack[3] = sentinel; }
    else if (flushFrame) { stack[4] = 17; stack[5] = sentinel; }
    else stack[1] = sentinel;
    const auto before = context.Rsp;
    void* handler = nullptr; DWORD64 frame = 0;
    RtlVirtualUnwind(UNW_FLAG_NHANDLER, imageBase, pc, function, &context, &handler, &frame, nullptr);
    Check(context.Rip == sentinel && context.Rsp == before + (dataFrame ? 32 : flushFrame ? 48 : 16));
    if (dataFrame) Check(context.R14 == 14 && context.Rbp == 15 && context.Rbx == 16);
    if (flushFrame) Check(context.Rdi == 17);
}
void Load(WrittenState** object, std::uint32_t* time) {
    Check(object != nullptr && *object == &written && time != nullptr && *time == 789); ++loaded;
}
void Drop(const char*, int, int code, const char* format, ...) {
    Check(code == 2 && std::strcmp(format, "Migration state has an incompatible format or size") == 0); ++dropped;
}
void Flush(void*) { ++flushed; }
const Header* GetHeader() { return &current; }
const WrittenState* GetWritten() { return &written; }
void SendAck(std::int32_t client, const char* command, const void* bytes, std::uint32_t count) {
    Check(client == 1 && std::strcmp(command, "mhack") == 0);
    ack.clear();
    if (count != 0) {
        const auto* first = static_cast<const std::byte*>(bytes); ack.assign(first, first + count);
    } else Check(bytes == nullptr);
    ++sentAcks; calls.push_back(2);
}
void ReceiveHeader(std::int32_t client, const void* from, const Message* message) {
    Check(client == 1 && from == &written);
    Check(Peek(*message, &current, sizeof(current))); ++receivedHeaders; calls.push_back(1);
    SendHeaderAck(client, "mhack", nullptr, 0);
}
void ReceiveData(std::int32_t client, const void* from, const Message*) {
    Check(client == 1 && from == &written); ++receivedData; calls.push_back(4);
}
void ReceiveAck(std::int32_t peer, const Message*) { Check(peer == 7); ++receivedAcks; calls.push_back(3); }
void SendHeader(std::int32_t peer) { Check(peer == 7); ++sentHeaders; calls.push_back(0); }
Message View(const void* bytes, std::uint32_t count) {
    return {0, 0, static_cast<const std::byte*>(bytes), nullptr, static_cast<std::int32_t>(count), static_cast<std::int32_t>(count), 0, 0};
}
}
int main() {
    try {
        Check(Bo3MigrationBindings.wireVersion == 0 && Bo3MigrationBindings.bufferBytes == 0);
        const auto version = FormatVersion(500001, 18);
        Bo3MigrationBindings = {version, 32 * 1024 * 1024, ReceiveHeader, ReceiveData, ReceiveAck, SendHeader, SendAck, GetHeader, GetWritten};
        Bo3MigrationVersionBranches = {reinterpret_cast<std::uintptr_t>(Accepted), reinterpret_cast<std::uintptr_t>(Rejected)};
        Bo3MigrationLoadBindings = {Load, Drop};
        Bo3MigrationFlushBindings = {Flush, 0};
        Check(TestMigrationVersion(3) == 1 && TestMigrationVersion(version) == 1);
        Check(TestMigrationVersion(4) == 0 && TestMigrationVersion(FormatVersion(1000001, 18)) == 0);
        std::cout << "dual-version-loader-branch passed\n";
        CheckUnwind(MigrationDataReentry, 4, true);
        CheckUnwind(MigrationDataReentry, 11, true);
        CheckUnwind(MigrationHeaderAckReentry, 4, false);
        CheckUnwind(MigrationHeaderAckReentry, 23, false);
        CheckUnwind(MigrationHeaderAckReentry, 37, false);
        CheckUnwind(MigrationFlushReentry, 5, false, true);
        CheckUnwind(MigrationFlushReentry, 12, false, true);
        std::cout << "static-reentry-Windows-unwind passed\n";
        const Header good{25000000, version, 123, HeaderMagic, 456, 789};
        for (const auto badVersion : {4u, FormatVersion(1000001, 18), FormatVersion(500001, 10), version ^ 0x02000000}) {
            auto bad = good; bad.version = badVersion; const auto message = View(&bad, 24);
            ReceiveMigrationHeader(1, &written, &message);
            Check(receivedHeaders == 0 && sentAcks == 0 && current.version == 0);
        }
        for (const auto badSize : {0u, 33554433u, 0xffffffffu}) {
            auto bad = good; bad.size = badSize; const auto message = View(&bad, 24);
            ReceiveMigrationHeader(1, &written, &message); Check(receivedHeaders == 0 && sentAcks == 0);
        }
        auto wrongMagic = good; wrongMagic.magic = 0; auto message = View(&wrongMagic, 24);
        ReceiveMigrationHeader(1, &written, &message); Check(receivedHeaders == 0);
        message = View(&good, 23); ReceiveMigrationHeader(1, &written, &message); Check(receivedHeaders == 0);
        message = View(&good, 24); message.overflowed = 1; ReceiveMigrationHeader(1, &written, &message); Check(receivedHeaders == 0);
        std::cout << "incompatible-header-refused-before-buffer-or-ack passed\n";
        auto empty = View(nullptr, 0); ReceiveMigrationHeaderAck(7, &empty); Check(receivedAcks == 0);
        auto mismatch = version + 1; auto badAck = View(&mismatch, 4); ReceiveMigrationHeaderAck(7, &badAck); Check(receivedAcks == 0);
        ReceiveMigrationData(1, &written, &empty); Check(receivedData == 0);
        Check(!CanLoadMigrationState());
        std::cout << "stock-ack-and-pre-header-data-refused passed\n";
        const auto* goodBytes = reinterpret_cast<const std::byte*>(&good);
        message = {0, 0, goodBytes, goodBytes + 9, 24, 9, 15, 0};
        const auto before = message;
        ReceiveMigrationHeader(1, &written, &message);
        Check(receivedHeaders == 1 && sentAcks == 1 && current.version == version && ack.size() == 4);
        Check(std::memcmp(&message, &before, sizeof(message)) == 0);
        std::uint32_t echo; std::memcpy(&echo, ack.data(), 4); Check(echo == version);
        auto matchingAck = View(ack.data(), 4); ReceiveMigrationHeaderAck(7, &matchingAck);
        ReceiveMigrationData(1, &written, &empty);
        Check(receivedAcks == 1 && receivedData == 1 && calls == std::vector<std::uint32_t>({1, 2, 3, 4}));
        Check(CanLoadMigrationState());
        std::cout << "split-header-format-echo-then-native-data-order passed\n";
        auto legacy = good; legacy.version = 3; legacy.size = 0x280000;
        message = View(&legacy, sizeof(legacy));
        ReceiveMigrationHeader(1, &written, &message);
        Check(receivedHeaders == 2 && sentAcks == 2 && ack.empty() && current.version == 3);
        ReceiveMigrationData(1, &written, &empty); Check(receivedData == 2);
        Check(CanLoadMigrationState());
        for (const auto badSize : {0u, 33554433u}) {
            auto bad = legacy; bad.size = badSize; message = View(&bad, sizeof(bad));
            ReceiveMigrationHeader(1, &written, &message); Check(receivedHeaders == 2 && sentAcks == 2);
            current = bad; Check(!CanLoadMigrationState());
        }
        current = good; current.version = 4; Check(!CanLoadMigrationState());
        WrittenState* object = &written; std::uint32_t time = 789;
        LoadMigrationState(&object, &time); Check(loaded == 0 && dropped == 1);
        current = legacy; LoadMigrationState(&object, &time); Check(loaded == 1 && dropped == 1);
        current = good; LoadMigrationState(&object, &time); Check(loaded == 2 && dropped == 1);
        std::cout << "legacy-import-original-empty-ack-and-preload-budget passed\n";
        written.writtenBytes = 0; SendMigrationHeader(7); Check(sentHeaders == 0);
        written.writtenBytes = 33554433; SendMigrationHeader(7); Check(sentHeaders == 0);
        written.writtenBytes = 25000000; SendMigrationHeader(7); Check(sentHeaders == 1);
        Check(MaxProtocolBytes == 39321600 && sizeof(Header) == 24 && sizeof(Bindings) == 64);
        std::cout << "sender-budget-and-original-callback-arguments passed\n";
        written.capacity = 100; written.compressed = 1; written.bufferedBytes = 10;
        for (std::uint32_t remaining = 0; remaining < 4; ++remaining) {
            written.writtenBytes = 100 - remaining; written.overflow = 0; written.bufferedBytes = 10;
            FlushMigrationState(&written);
            Check(flushed == 0 && written.overflow == 1 && written.bufferedBytes == 0);
        }
        written.writtenBytes = 96; written.overflow = 0; written.bufferedBytes = 10;
        FlushMigrationState(&written); Check(flushed == 1);
        WrittenState other{}; FlushMigrationState(&other); Check(flushed == 2);
        written.compressed = 0; FlushMigrationState(&written); Check(flushed == 3);
        std::cout << "migration-only-compressed-prefix-room-guard passed\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
