#pragma once
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace bo3::enhanced {
// The installer keeps the stock client. Developer builds must select the experimental profile explicitly.
#ifdef BO3_EXPERIMENTAL_CLIENT_250K
inline constexpr std::uint32_t kClientTotal = 250001;
inline constexpr std::size_t kNativeEdits = 61;
inline constexpr std::string_view kCandidate = "experimental-client250K";
#else
inline constexpr std::uint32_t kClientTotal = 65000;
inline constexpr std::size_t kNativeEdits = 42;
inline constexpr std::string_view kCandidate = "0.1.0-test.3";
#endif
}
