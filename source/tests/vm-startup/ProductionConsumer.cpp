#include "Contract.h"
#include "../../launch/enhanced/Boot.h"
#include "../../patches/vm_pool/NativeStateBridge.h"
#include "../../patches/vm_startup/StateErrors.h"
#include <array>
#include <cstdlib>

extern "C" __declspec(dllexport) void OwnedConsumerAnchor() {}

// Only the owned consumer uses a mapping. The production helper has no fixture inputs.
BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID) {
    if (reason != DLL_PROCESS_ATTACH) return TRUE;
    wchar_t text[64]{};
    if (!GetEnvironmentVariableW(L"OWNED_VM_STARTUP_MAPPING", text, 64)) return FALSE;
    const auto mapping = reinterpret_cast<HANDLE>(_wcstoui64(text, nullptr, 10));
    auto* shared = static_cast<Shared*>(MapViewOfFile(mapping, FILE_MAP_WRITE, 0, 0, sizeof(Shared)));
    if (!shared) return FALSE;
    const auto helper = GetModuleHandleW(L"VmStartupHelper.dll");
    const auto* boot = reinterpret_cast<const bo3::enhanced::BootRecord*>(GetProcAddress(helper, "Bo3EnhancedBoot"));
    if (!boot) { UnmapViewOfFile(shared); return FALSE; }
    shared->helperBase = boot->module;
    shared->helperLoaded = boot->ready;
    shared->helperAtImport = boot->ready;
    shared->configZeroAtLoad = 1;
    const std::array records{
        std::pair{"Bo3VmStateBindings", sizeof(bo3::vm::NativeStateBindings)},
        std::pair{"Bo3VmErrorBindings", sizeof(bo3::vm::ErrorBindings)}};
    for (const auto& [name, size] : records) {
        const auto* data = reinterpret_cast<const unsigned char*>(GetProcAddress(helper, name));
        if (!data) { UnmapViewOfFile(shared); return FALSE; }
        for (std::size_t index = 0; index < size; ++index)
            if (data[index]) shared->configZeroAtLoad = 0;
    }
    // Deliberate owned corruption checks parent admission before any hook writes.
    auto* mutableBoot = const_cast<bo3::enhanced::BootRecord*>(boot);
    if (shared->scenario == Scenario::HelperDirty) mutableBoot->abi = 99;
    if (shared->scenario == Scenario::HelperNoReady) mutableBoot->ready = 0;
    UnmapViewOfFile(shared);
    return TRUE;
}
