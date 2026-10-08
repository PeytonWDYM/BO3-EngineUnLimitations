#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <array>
#include <cstring>

int main() {
    std::array<wchar_t, 32> app{}, game{};
    if (!GetEnvironmentVariableW(L"SteamAppId", app.data(), static_cast<DWORD>(app.size()))
        || !GetEnvironmentVariableW(L"SteamGameId", game.data(), static_cast<DWORD>(game.size()))
        || std::wcscmp(app.data(), L"311210") || std::wcscmp(game.data(), L"311210")) return 1;
    const auto helper = GetModuleHandleW(L"Bo3EnhancedHelper.dll");
    if (!helper) return 2;
    for (const auto& [name, size] : std::array<std::pair<const char*, std::size_t>, 7>{{
        {"Bo3VmStateBindings",48},{"Bo3VmErrorBindings",32},{"Bo3MigrationBindings",64},
        {"Bo3MigrationVersionBranches",16},{"Bo3MigrationLoadBindings",16},{"Bo3MigrationReentries",56},
        {"Bo3MigrationFlushBindings",16}}}) {
        const auto* bytes = reinterpret_cast<const unsigned char*>(GetProcAddress(helper, name));
        if (!bytes) return 3;
        for (std::size_t i = 0; i < size; ++i) if (bytes[i]) return 4;
    }
    DebugBreak();
    return 0;
}
