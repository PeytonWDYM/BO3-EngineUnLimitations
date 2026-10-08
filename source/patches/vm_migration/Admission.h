#pragma once
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace bo3::migration {
inline constexpr std::uint32_t HeaderMagic = 0x4864;
inline constexpr std::uint32_t MaxProtocolBytes = 32768 * 1200;
constexpr std::uint32_t FormatVersion(std::uint32_t total, std::uint32_t roots) {
    return 0xc6000000 | (roots << 20) | total;
}
struct Header { std::uint32_t size, version, crc, magic, crcSeed, time; };
struct Message {
    std::int32_t overflowed, readOnly;
    const std::byte* data;
    const std::byte* splitData;
    std::int32_t maxBytes, primaryBytes, splitBytes, cursor;
};
struct WrittenState {
    const std::byte* data;
    std::uint32_t capacity, writtenBytes;
    std::uint64_t field10;
    std::uint32_t bufferedBytes;
    std::byte reserved[16];
    std::uint8_t errorOnOverflow, overflow, compressed, padding;
};
static_assert(sizeof(Header) == 24 && sizeof(Message) == 40);
static_assert(offsetof(Message, primaryBytes) == 0x1c && offsetof(Message, cursor) == 0x24);
static_assert(offsetof(WrittenState, writtenBytes) == 0xc);
static_assert(sizeof(WrittenState) == 48 && offsetof(WrittenState, bufferedBytes) == 0x18 && offsetof(WrittenState, overflow) == 0x2d);
using ClientHandler = void (*)(std::int32_t, const void*, const Message*);
using HeaderAckHandler = void (*)(std::int32_t, const Message*);
using HeaderSender = void (*)(std::int32_t);
using ClientSender = void (*)(std::int32_t, const char*, const void*, std::uint32_t);
struct Bindings {
    std::uint32_t wireVersion, bufferBytes;
    ClientHandler originalHeader, originalData;
    HeaderAckHandler originalHeaderAck;
    HeaderSender originalSendHeader;
    ClientSender originalAckSend;
    const Header* (*nativeHeader)();
    const WrittenState* (*nativeWriteState)();
};
static_assert(sizeof(Bindings) == 64 && offsetof(Bindings, originalHeader) == 8);
static_assert(std::is_standard_layout_v<Bindings> && std::is_trivially_copyable_v<Bindings>);
extern "C" __declspec(dllexport) Bindings Bo3MigrationBindings;
struct VersionBranches { std::uintptr_t accepted, rejected; };
static_assert(sizeof(VersionBranches) == 16 && std::is_trivially_copyable_v<VersionBranches>);
extern "C" __declspec(dllexport) VersionBranches Bo3MigrationVersionBranches;
// Replace the captured five-byte cmp/je only after the pre-load guard is installed.
// EAX holds the header version. Both continuations resume the original loader.
extern "C" __declspec(dllexport) void MigrationVersionGate();
using Loader = void (*)(WrittenState**, std::uint32_t*);
using ErrorEntry = void (*)(const char*, int, int, const char*, ...);
struct LoadBindings { Loader original; ErrorEntry error; };
static_assert(sizeof(LoadBindings) == 16 && std::is_trivially_copyable_v<LoadBindings>);
extern "C" __declspec(dllexport) LoadBindings Bo3MigrationLoadBindings;
extern "C" __declspec(dllexport) void LoadMigrationState(WrittenState**, std::uint32_t*);
struct Reentries {
    std::uintptr_t header, data, headerAckAccepted, selectedPeer, sendHeader, load, headerAckRejected;
};
static_assert(sizeof(Reentries) == 56 && std::is_trivially_copyable_v<Reentries>);
extern "C" __declspec(dllexport) Reentries Bo3MigrationReentries;
extern "C" __declspec(dllexport) void MigrationHeaderReentry();
extern "C" __declspec(dllexport) void MigrationDataReentry();
extern "C" __declspec(dllexport) void MigrationHeaderAckReentry();
extern "C" __declspec(dllexport) void MigrationSendHeaderReentry();
extern "C" __declspec(dllexport) void MigrationLoadReentry();
using FlushFunction = void (*)(void*);
struct FlushBindings { FlushFunction original; std::uintptr_t continuation; };
static_assert(sizeof(FlushBindings) == 16 && std::is_trivially_copyable_v<FlushBindings>);
extern "C" __declspec(dllexport) FlushBindings Bo3MigrationFlushBindings;
extern "C" __declspec(dllexport) void FlushMigrationState(void*);
extern "C" __declspec(dllexport) void MigrationFlushReentry();

// Peek follows the captured native message layout without advancing its cursor.
bool Peek(const Message&, void* destination, std::uint32_t bytes);
extern "C" __declspec(dllexport) void ReceiveMigrationHeader(std::int32_t, const void*, const Message*);
extern "C" __declspec(dllexport) void ReceiveMigrationData(std::int32_t, const void*, const Message*);
extern "C" __declspec(dllexport) void ReceiveMigrationHeaderAck(std::int32_t, const Message*);
extern "C" __declspec(dllexport) void SendMigrationHeader(std::int32_t);
// The full-load entry hook must call this before native MemFile initialization.
extern "C" __declspec(dllexport) bool CanLoadMigrationState();
// Install only at the captured mhead acknowledgement call site, not the general send entry.
extern "C" __declspec(dllexport) void SendHeaderAck(std::int32_t, const char*, const void*, std::uint32_t);
}
