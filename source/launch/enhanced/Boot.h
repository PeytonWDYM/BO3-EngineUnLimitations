#pragma once
#include <cstdint>
#include <type_traits>

namespace bo3::enhanced {
inline constexpr std::uint32_t BootAbi = 1;
struct BootRecord {
    std::uint32_t abi, bytes;
    std::uintptr_t module;
    std::uint32_t ready, reserved;
};
static_assert(sizeof(BootRecord) == 24);
static_assert(std::is_standard_layout_v<BootRecord> && std::is_trivially_copyable_v<BootRecord>);
extern "C" __declspec(dllexport) BootRecord Bo3EnhancedBoot;
}
