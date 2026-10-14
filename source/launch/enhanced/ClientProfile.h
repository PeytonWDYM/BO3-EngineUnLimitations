#pragma once
#include "GameProfile.h"

namespace bo3::enhanced {
struct ClientManifest {
    std::span<const CountInstruction> counts;
    std::span<const CodeGuard> guards;
};
// The caller holds the stopped exact-build child. All checks finish before edit publication.
vm_startup::Profile AdmitClientProfile(HANDLE, std::uintptr_t, const ClientManifest&, std::uint32_t total);
}
