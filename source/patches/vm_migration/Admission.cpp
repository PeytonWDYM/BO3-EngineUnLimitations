#include "Admission.h"
#include <algorithm>
#include <cstring>
#pragma comment(linker, "/EXPORT:MigrationVersionGate")
#pragma comment(linker, "/EXPORT:MigrationHeaderReentry")
#pragma comment(linker, "/EXPORT:MigrationDataReentry")
#pragma comment(linker, "/EXPORT:MigrationHeaderAckReentry")
#pragma comment(linker, "/EXPORT:MigrationSendHeaderReentry")
#pragma comment(linker, "/EXPORT:MigrationLoadReentry")
#pragma comment(linker, "/EXPORT:MigrationFlushReentry")

namespace bo3::migration {
extern "C" {
__declspec(dllexport) constinit Bindings Bo3MigrationBindings{};
__declspec(dllexport) constinit VersionBranches Bo3MigrationVersionBranches{};
__declspec(dllexport) constinit LoadBindings Bo3MigrationLoadBindings{};
__declspec(dllexport) constinit Reentries Bo3MigrationReentries{};
__declspec(dllexport) constinit FlushBindings Bo3MigrationFlushBindings{};
}
namespace {
bool FormatValid(std::uint32_t version) {
    const auto total = version & 0xfffff;
    const auto roots = (version >> 20) & 31;
    return (version & 0xfe000000) == 0xc6000000 &&
           (total == 500001 || total == 1000001) && roots > 0 && roots <= 18;
}
bool HeaderAllowed(const Header& header) {
    const auto& config = Bo3MigrationBindings;
    return FormatValid(config.wireVersion) && (header.version == 3 || header.version == config.wireVersion) &&
           header.magic == HeaderMagic && header.size > 0 && header.size <= config.bufferBytes &&
           config.bufferBytes <= MaxProtocolBytes;
}
}

bool Peek(const Message& message, void* destination, std::uint32_t bytes) {
    if (message.overflowed || message.cursor < 0 || message.primaryBytes < 0 || message.splitBytes < 0)
        return false;
    const auto total = static_cast<std::int64_t>(message.primaryBytes) + message.splitBytes;
    if (static_cast<std::int64_t>(message.cursor) + bytes > total) return false;
    const auto first = message.cursor < message.primaryBytes
        ? std::min(bytes, static_cast<std::uint32_t>(message.primaryBytes - message.cursor)) : 0;
    if (first != 0) std::memcpy(destination, message.data + message.cursor, first);
    if (first != bytes) {
        const auto splitOffset = message.cursor > message.primaryBytes ? message.cursor - message.primaryBytes : 0;
        std::memcpy(static_cast<std::byte*>(destination) + first, message.splitData + splitOffset, bytes - first);
    }
    return true;
}

void ReceiveMigrationHeader(std::int32_t client, const void* from, const Message* message) {
    Header header;
    if (!Peek(*message, &header, sizeof(header)) || !HeaderAllowed(header)) return;
    Bo3MigrationBindings.originalHeader(client, from, message);
}
void ReceiveMigrationData(std::int32_t client, const void* from, const Message* message) {
    if (!HeaderAllowed(*Bo3MigrationBindings.nativeHeader())) return;
    Bo3MigrationBindings.originalData(client, from, message);
}
void ReceiveMigrationHeaderAck(std::int32_t peer, const Message* message) {
    std::uint32_t echo;
    if (!Peek(*message, &echo, sizeof(echo)) || echo != Bo3MigrationBindings.wireVersion || !FormatValid(echo)) return;
    // The native handler retains its selected-peer and migration-phase checks.
    Bo3MigrationBindings.originalHeaderAck(peer, message);
}
void SendMigrationHeader(std::int32_t peer) {
    const auto& config = Bo3MigrationBindings;
    const auto length = config.nativeWriteState()->writtenBytes;
    if (!FormatValid(config.wireVersion) || length == 0 || length > config.bufferBytes || config.bufferBytes > MaxProtocolBytes) return;
    config.originalSendHeader(peer);
}
bool CanLoadMigrationState() {
    return HeaderAllowed(*Bo3MigrationBindings.nativeHeader());
}
void LoadMigrationState(WrittenState** object, std::uint32_t* time) {
    if (!CanLoadMigrationState()) {
        Bo3MigrationLoadBindings.error("vm_migration", 0, 2, "Migration state has an incompatible format or size");
        return;
    }
    Bo3MigrationLoadBindings.original(object, time);
}
void SendHeaderAck(std::int32_t client, const char* command, const void* payload, std::uint32_t count) {
    if (Bo3MigrationBindings.nativeHeader()->version == 3) {
        Bo3MigrationBindings.originalAckSend(client, command, payload, count);
        return;
    }
    const auto version = Bo3MigrationBindings.wireVersion;
    Bo3MigrationBindings.originalAckSend(client, command, &version, sizeof(version));
}
void FlushMigrationState(void* file) {
    if (file == Bo3MigrationBindings.nativeWriteState()) {
        auto& state = *static_cast<WrittenState*>(file);
        if (state.compressed && !state.overflow && state.bufferedBytes != 0 &&
            (state.capacity < 4 || state.writtenBytes > state.capacity - 4)) {
            state.overflow = 1;
            state.bufferedBytes = 0;
            return;
        }
    }
    Bo3MigrationFlushBindings.original(file);
}
}
