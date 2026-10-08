#pragma once
#include "Admission.h"
#include "../vm_startup/NativePlan.h"
#include <array>

namespace bo3::migration {
enum class Hook : std::size_t { Header, Data, HeaderAck, SendHeader, Load, Flush, Count };
inline constexpr std::size_t HookCount = static_cast<std::size_t>(Hook::Count);
struct HelperOffsets {
    std::uint32_t bindings, versionBranches, loadBindings, reentries, flushBindings;
    std::array<std::uint32_t, HookCount> handlers, originals; // Hook enum order.
    std::uint32_t sendAck, versionGate;
};
struct MigrationPlanInput {
    vm_startup::ImageRange image, helper;
    HelperOffsets exports;
    std::uintptr_t relay; // Eight slots begin after the core plan's four slots.
    std::uint32_t total = 500001, clientRoots = 18, bufferBytes = 32 * 1024 * 1024;
};
// Pure checked preparation; the paused caller combines this with its core plan.
std::vector<vm_startup::AddressEdit> BuildMigrationPlan(const MigrationPlanInput&);
}
