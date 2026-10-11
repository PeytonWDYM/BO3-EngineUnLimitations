#pragma once
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace bo3::enhanced {
// Every launcher build uses the same guarded server500K/client250K recipe.
inline constexpr std::uint32_t kClientTotal = 250001;
inline constexpr std::size_t kNativeEdits = 61;
inline constexpr std::string_view kCandidate = "0.3.0-test.1";
}
