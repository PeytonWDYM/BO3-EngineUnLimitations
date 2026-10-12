#pragma once
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace bo3::enhanced {
// Every launcher build uses the same guarded VM and clientfield storage recipe.
inline constexpr std::uint32_t kClientTotal = 250001;
inline constexpr std::uint32_t kPendingCallbacksPerLocalClient = 8192;
inline constexpr std::uint32_t kClientfieldCounters = 8192;
inline constexpr std::uint32_t kActors=500,kSentients=540,kActorRuntimeFunctions=2465;
inline constexpr std::size_t kNativeEdits = 372;
inline constexpr std::string_view kCandidate = "0.5.0-test.7";
}
