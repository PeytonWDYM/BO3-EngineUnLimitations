#include "Contract.h"
#include <cstdlib>

extern "C" __declspec(dllexport) void OwnedConsumerAnchor() {}
// This dependency records loader order without importing the helper or the target.
BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID) {
    if (reason != DLL_PROCESS_ATTACH) return TRUE;
    wchar_t text[64]{};
    if (!GetEnvironmentVariableW(L"OWNED_VM_STARTUP_MAPPING", text, 64)) return FALSE;
    const auto mapping = reinterpret_cast<HANDLE>(_wcstoui64(text, nullptr, 10));
    auto* shared = static_cast<Shared*>(MapViewOfFile(mapping, FILE_MAP_WRITE, 0, 0, sizeof(Shared)));
    if (!shared) return FALSE;
    shared->helperAtImport = shared->helperLoaded;
    UnmapViewOfFile(shared);
    return TRUE;
}
