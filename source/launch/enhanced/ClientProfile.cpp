#include "ClientProfile.h"
#include "GameManifest.h"
#include "../preentry/Identity.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include <algorithm>
#include <cstring>

namespace bo3::enhanced {
vm_startup::Profile AdmitClientProfile(HANDLE process, std::uintptr_t image,
    const ClientManifest& client, std::uint32_t total) {
    Require(total == 250001 && client.counts.size() == 19 && client.guards.size() == 40,
        "The exact experimental client250K inventory is required.");
    auto guarded = ExactGameManifest;
    guarded.guards = client.guards;
    VerifyGameCode(process, image, guarded);
    for (const auto rva : {0x5124680u, 0x5124600u}) {
        const auto bytes = vm_startup::ReadStopped(process, image + rva, 8);
        Require(std::all_of(bytes.begin(), bytes.end(), [](unsigned char value) {return value == 0;}),
            "Client backing already exists. Early activation is required.");
    }
    vm_startup::Profile result{ExactGameManifest.imageSize, 0x12df230, 0x5124680, 0x5124600, {}, {}};
    for (const auto& count : client.counts) {
        Require(count.size >= 5 && count.size <= count.bytes.size() && count.rva <= result.imageSize - count.size
            && count.immediateOffset <= count.size - 4, "Invalid experimental client instruction.");
        std::uint32_t stock{};
        std::memcpy(&stock, count.bytes.data() + count.immediateOffset, sizeof(stock));
        Require(stock == 65000, "The original client count differs from stock.");
        result.checks.push_back({count.rva, {count.bytes.begin(), count.bytes.begin() + count.size}});
        Require(vm_startup::ReadStopped(process, image + count.rva, count.size) == result.checks.back().bytes,
            "A complete client count instruction differs.");
        std::vector<unsigned char> replacement(sizeof(total));
        std::memcpy(replacement.data(), &total, sizeof(total));
        const auto original = count.bytes.begin() + count.immediateOffset;
        result.edits.push_back({count.rva + count.immediateOffset, {original, original + 4}, std::move(replacement)});
    }
    return result;
}
}
