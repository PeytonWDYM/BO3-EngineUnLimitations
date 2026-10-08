#include "Contract.h"
#include "../../patches/vm_pool/NativeStateBridge.h"
#include "../../patches/vm_startup/OriginalEntries.h"
#include <detours.h>

namespace { Shared* shared; }
extern "C" void VmStartupOrdinal() {}
extern "C" __declspec(dllexport) DWORD FixtureBindingReader() {
    bo3::vm::ClearNativeImportContext();
    const auto& bindings = bo3::vm::Bo3VmStateBindings;
    bindings.originalClientReader(1, shared);
    InterlockedIncrement(&shared->hookReads);
    return bindings.total;
}
extern "C" __declspec(dllexport) DWORD FixtureBindingWriter() {
    const auto& bindings = bo3::vm::Bo3VmStateBindings;
    bindings.originalClientWriter(1, shared);
    bindings.originalInsert(1, 7, 0x1122334455667788ull, 9);
    InterlockedIncrement(&shared->hookWrites);
    return bindings.total;
}
// Windows has already loaded the static helper and its platform dependencies.
// This entry only maps the owned trace, restores imports, and publishes POD state.
BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID) {
    if (reason != DLL_PROCESS_ATTACH) return TRUE;
    wchar_t text[64]{};
    const auto length = GetEnvironmentVariableW(L"OWNED_VM_STARTUP_MAPPING", text, 64);
    if (!length || length >= 64) return FALSE;
    std::uintptr_t handle = 0;
    for (DWORD index = 0; index < length; ++index) {
        if (text[index] < L'0' || text[index] > L'9') return FALSE;
        handle = handle * 10 + static_cast<unsigned>(text[index] - L'0');
    }
    shared = static_cast<Shared*>(MapViewOfFile(reinterpret_cast<HANDLE>(handle), FILE_MAP_WRITE, 0, 0, sizeof(Shared)));
    if (!shared || !DetourRestoreAfterWith()) return FALSE;
    shared->helperBase = reinterpret_cast<std::uintptr_t>(module);
    shared->configZeroAtLoad = 1;
    const auto* bytes = reinterpret_cast<const unsigned char*>(&bo3::vm::Bo3VmStateBindings);
    for (size_t index = 0; index < sizeof(bo3::vm::NativeStateBindings); ++index)
        if (bytes[index] != 0) shared->configZeroAtLoad = 0;
    const auto* errorBytes=reinterpret_cast<const unsigned char*>(&bo3::vm::Bo3VmErrorBindings);
    for(size_t index=0;index<sizeof(bo3::vm::ErrorBindings);++index)
        if(errorBytes[index]!=0) shared->configZeroAtLoad=0;
    if (shared->scenario == Scenario::HelperDirty) bo3::vm::Bo3VmStateBindings.total = 130000;
    if (shared->scenario != Scenario::HelperNoReady) shared->helperLoaded = 1;
    return TRUE;
}
