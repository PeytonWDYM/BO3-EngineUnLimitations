#include "MigrationPlan.h"
#include <cstring>
#include <stdexcept>

namespace bo3::migration {
namespace {
using vm_startup::AddressEdit;
using vm_startup::ImageRange;
void Require(bool condition, const char* error) { if (!condition) throw std::runtime_error(error); }
std::uintptr_t Address(ImageRange image, std::uint32_t rva, std::size_t bytes) {
    Require(image.base <= UINTPTR_MAX - image.size && rva < image.size && bytes <= image.size - rva,
        "Migration offset exceeds its admitted image.");
    return image.base + rva;
}
template<class T> std::vector<unsigned char> Bytes(const T& value) {
    std::vector<unsigned char> result(sizeof(value)); std::memcpy(result.data(), &value, sizeof(value)); return result;
}
std::vector<unsigned char> Branch(std::uintptr_t from, std::uintptr_t to, std::size_t bytes, unsigned char opcode) {
    Require(from <= UINTPTR_MAX - 5 && bytes >= 5, "Migration branch address overflows.");
    const auto next = from + 5;
    const auto distance = to >= next ? to - next : next - to;
    Require(distance <= (to >= next ? 0x7fffffffull : 0x80000000ull), "Migration relay exceeds signed relative reach.");
    const auto relative = to >= next ? static_cast<std::int32_t>(distance)
        : static_cast<std::int32_t>(-static_cast<std::int64_t>(distance));
    std::vector<unsigned char> result(bytes, 0x90); result[0] = opcode;
    std::memcpy(result.data() + 1, &relative, 4); return result;
}
void ValidateEdits(const std::vector<AddressEdit>& edits) {
    for (std::size_t i = 0; i < edits.size(); ++i) {
        const auto& current = edits[i];
        Require(current.address <= UINTPTR_MAX - current.original.size(), "Migration edit address overflows.");
        Require(current.address / 4096 == (current.address + current.original.size() - 1) / 4096,
            "Migration edit crosses a native page.");
        for (std::size_t prior = 0; prior < i; ++prior)
            Require(current.address + current.original.size() <= edits[prior].address ||
                edits[prior].address + edits[prior].original.size() <= current.address, "Migration edits overlap.");
    }
}
}
std::vector<AddressEdit> BuildMigrationPlan(const MigrationPlanInput& input) {
    Require(input.image.size == 494186496 && input.total == 500001 && input.clientRoots == 18 &&
        input.bufferBytes == 32 * 1024 * 1024, "Migration admission requires the checked 500k/18-root/32-MiB policy.");
    Require((input.relay & 15) == 0 && input.relay <= UINTPTR_MAX - 128, "Invalid migration relay storage.");
    const auto helper = [&](std::uint32_t offset) { return Address(input.helper, offset, 1); };
    const auto game = [&](std::uint32_t offset) { return Address(input.image, offset, 1); };
    const auto& offsets = input.exports;
    const auto original = [&](Hook hook) { return helper(offsets.originals[static_cast<std::size_t>(hook)]); };
    const auto version = FormatVersion(input.total, input.clientRoots);
    const Bindings bindings{version, input.bufferBytes,
        reinterpret_cast<ClientHandler>(original(Hook::Header)), reinterpret_cast<ClientHandler>(original(Hook::Data)),
        reinterpret_cast<HeaderAckHandler>(original(Hook::HeaderAck)), reinterpret_cast<HeaderSender>(original(Hook::SendHeader)),
        reinterpret_cast<ClientSender>(game(0x1362330)), reinterpret_cast<const Header* (*)()>(game(0x20fc7d0)),
        reinterpret_cast<const WrittenState* (*)()>(game(0x20fc7c0))};
    const VersionBranches versionBranches{game(0x12e24a), game(0x12e22b)};
    const LoadBindings load{reinterpret_cast<Loader>(original(Hook::Load)), reinterpret_cast<ErrorEntry>(game(0x20ec0b0))};
    const Reentries reentries{game(0x13619e5), game(0x13617f5), game(0x21f9aa8), game(0x17756fa8),
        game(0x21fa755), game(0x12e1c5), game(0x21f9ac9)};
    const FlushBindings flush{reinterpret_cast<FlushFunction>(original(Hook::Flush)), game(0x2277a66)};
    std::vector<AddressEdit> edits;
    const auto publish = [&](std::uint32_t rva, const auto& record) {
        edits.push_back({Address(input.helper, rva, sizeof(record)), std::vector<unsigned char>(sizeof(record), 0), Bytes(record)});
    };
    publish(offsets.bindings, bindings); publish(offsets.versionBranches, versionBranches);
    publish(offsets.loadBindings, load); publish(offsets.reentries, reentries); publish(offsets.flushBindings, flush);
    std::array<std::uintptr_t, 8> targets{};
    for (std::size_t i = 0; i < HookCount; ++i) targets[i] = helper(offsets.handlers[i]);
    targets[6] = helper(offsets.sendAck); targets[7] = helper(offsets.versionGate);
    std::vector<unsigned char> relay(128, 0);
    for (std::size_t i = 0; i < targets.size(); ++i) {
        relay[i * 16] = 0xff; relay[i * 16 + 1] = 0x25;
        std::memcpy(relay.data() + i * 16 + 6, &targets[i], 8);
    }
    edits.push_back({input.relay, std::vector<unsigned char>(128, 0), std::move(relay)});
    const std::array<std::uint32_t, 6> entries{0x13619e0,0x13617f0,0x21f9aa0,0x21fa750,0x12e1c0,0x2277a60};
    const std::array<std::vector<unsigned char>, 6> prefixes{{
        {0x48,0x89,0x74,0x24,0x10}, {0x40,0x53,0x55,0x41,0x56}, {0x3b,0x0d,0x02,0xd5,0x55,0x15,0x75,0x21},
        {0x48,0x89,0x5c,0x24,0x10}, {0x48,0x89,0x5c,0x24,0x08}, {0x40,0x57,0x48,0x83,0xec,0x20}}};
    for (std::size_t i = 0; i < entries.size(); ++i) {
        const auto address = Address(input.image, entries[i], prefixes[i].size());
        edits.push_back({address, prefixes[i], Branch(address, input.relay + i * 16, prefixes[i].size(), 0xe9)});
    }
    const auto ack = Address(input.image, 0x1361a50, 5);
    edits.push_back({ack, {0xe8,0xdb,0x08,0,0}, Branch(ack, input.relay + 6 * 16, 5, 0xe8)});
    const auto gate = Address(input.image, 0x12e226, 5);
    edits.push_back({gate, {0x83,0xf8,0x03,0x74,0x1f}, Branch(gate, input.relay + 7 * 16, 5, 0xe9)});
    std::vector<unsigned char> buffer{0xbf,0,0,0,2};
    edits.push_back({Address(input.image,0xb253f,5), {0xbf,0,0,0x28,0}, std::move(buffer)});
    std::vector<unsigned char> sender{0xc7,0x44,0x24,0x5c};
    const auto versionBytes = Bytes(version); sender.insert(sender.end(), versionBytes.begin(), versionBytes.end());
    edits.push_back({Address(input.image,0x21fa7ae,8), {0xc7,0x44,0x24,0x5c,3,0,0,0}, std::move(sender)});
    ValidateEdits(edits);
    return edits;
}
}
