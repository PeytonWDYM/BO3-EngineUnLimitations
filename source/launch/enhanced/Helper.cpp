#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <detours.h>
#include "Boot.h"

namespace bo3::enhanced {
extern "C" { __declspec(dllexport) constinit BootRecord Bo3EnhancedBoot{}; }
}

// Detours requires ordinal one for the pre-import helper.
extern "C" void VmStartupOrdinal() {}

// Hook preparation stays in the paused parent. This entry only restores imports and publishes POD state.
BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID) {
    if (reason != DLL_PROCESS_ATTACH) return TRUE;
    if (!DetourRestoreAfterWith()) return FALSE;
    bo3::enhanced::Bo3EnhancedBoot = {bo3::enhanced::BootAbi, sizeof(bo3::enhanced::BootRecord),
        reinterpret_cast<std::uintptr_t>(module), 1, 0};
    return TRUE;
}
