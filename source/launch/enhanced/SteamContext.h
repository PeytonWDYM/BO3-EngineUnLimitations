#pragma once
#include <vector>

namespace enhanced {
// Pass data() to CreateProcessW with CREATE_UNICODE_ENVIRONMENT.
// Copies the calling process environment; only the child's two Steam IDs change.
std::vector<wchar_t> SteamChildEnvironment();
}
