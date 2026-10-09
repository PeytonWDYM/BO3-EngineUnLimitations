#pragma once
#include "ProfileTypes.h"
#include "Identity.h"
#include "../vm_startup/DebugGate.h"
#include <memory>

namespace bo3::early_integrity {
// The caller retains the frozen, sole-child job through preparation and publication.
// Release after PausedPatch rollback while the job is frozen. A failed rollback
// requires child termination under that freeze; never thaw or release the gate.
class RelayArena {
    HANDLE process_;
    std::uintptr_t address_;
    bool committed_ = false;
public:
    RelayArena(HANDLE process, std::uintptr_t address) noexcept;
    ~RelayArena();
    RelayArena(const RelayArena&) = delete;
    RelayArena& operator=(const RelayArena&) = delete;
    std::uintptr_t address() const noexcept {return address_;}
    size_t size() const noexcept {return kArenaSize;}
    // Committed memory stays in the child until process exit, even after owner release.
    void Commit() noexcept {committed_ = true;}
};
struct PreparedPlan {
    std::vector<vm_startup::AddressEdit> edits;
    std::shared_ptr<RelayArena> arena;
};
// Reads every image guard before allocation. The caller verifies and locks the file.
PreparedPlan PrepareStopped(HANDLE process, std::uintptr_t imageBase,
    const std::array<unsigned char,32>& verifiedExecutableDigest,
    std::span<const vm_startup::AddressEdit> existingEdits);
// Fixed MOV/LEA/JMP encoding. No stack pointer changes, callbacks, or runtime decoder.
std::array<unsigned char,kRelayStride> EncodeRelay(const Site& site,
    std::uintptr_t imageBase, std::uintptr_t relayAddress);
}
