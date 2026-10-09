#pragma once
#include "ProfileTypes.h"
#include "ProfileIdentity.h"
#include "../vm_startup/DebugGate.h"
namespace bo3::code_integrity {
// Comparison-only edits leave raw checksums in chained image cells. Input
// ownership and chained-write correction require separate reviewed admission.
inline constexpr bool kProductionInputAttributionVerified=false;
std::span<const unsigned char> Original(Family);
std::span<const unsigned char> Replacement(Family);
// Read-only preparation. The caller must have verified and locked the exact
// executable file, and hold the owned job frozen through the combined transaction.
// Supply the complete engine plan. This rejects every overlap before any write.
std::vector<vm_startup::AddressEdit> PrepareStopped(HANDLE process,std::uintptr_t imageBase,
    const std::array<unsigned char,32>& verifiedExecutableDigest,
    std::span<const vm_startup::AddressEdit> existingEdits);
}
