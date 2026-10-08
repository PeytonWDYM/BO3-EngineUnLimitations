#pragma once
#include "../../patches/vm_startup/DebugGate.h"
#include "../../patches/vm_startup/NativePlan.h"
#include <array>
#include <span>

namespace bo3::enhanced {
struct CountInstruction {
    std::uint32_t rva;
    std::array<unsigned char, 6> bytes;
    std::uint32_t size, immediateOffset;
};
struct CodeGuard {
    std::uint32_t rva, size;
    std::array<unsigned char, 32> digest;
};
struct GameManifest {
    std::uint32_t imageSize, timestamp, allocationEntry, poolPointer, hashPointer;
    std::array<unsigned char, 5> allocationPrefix;
    std::array<vm_startup::NativeEntry, 4> entries;
    std::span<const CountInstruction> counts;
    std::span<const CodeGuard> guards;
};
vm_startup::Profile MakeGameProfile(const GameManifest&, std::uint32_t total);
// The caller owns a stopped, file-identity-verified child. This function performs only reads.
void VerifyGameCode(HANDLE process, std::uintptr_t imageBase, const GameManifest&);
void VerifyMigrationUnallocated(HANDLE process, std::uintptr_t imageBase);
}
