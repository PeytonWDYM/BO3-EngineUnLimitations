#include "ProbeContract.h"
#include <detours.h>

static LONG (*originalFactory)() = OwnedFactory;
static bool installed;
static HMODULE livePin;
static LONG QuietFactory() { return 0; }
static BOOL Fail(LONG error) {
    InterlockedIncrement(&ProbeState()->internalErrors);
    ProbeRecord(Stage::Error, error);
    return FALSE;
}
// The owned fixture has one caller thread. This is not a running-process hook API.
static LONG ChangeHook(bool attach) {
    LONG error = DetourTransactionBegin();
    if (error != NO_ERROR) return error;
    error = DetourUpdateThread(GetCurrentThread());
    if (error == NO_ERROR) {
        if (attach) error = DetourAttach(reinterpret_cast<PVOID*>(&originalFactory), QuietFactory);
        else error = DetourDetach(reinterpret_cast<PVOID*>(&originalFactory), QuietFactory);
    }
    if (error != NO_ERROR) { DetourTransactionAbort(); return error; }
    return DetourTransactionCommit();
}
extern "C" void FixtureImportOrdinal() {}
extern "C" BOOL WINAPI AcquireFixtureReference() {
    auto* state = ProbeState();
    if (!installed || state->references != 0) return FALSE;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
                           reinterpret_cast<LPCWSTR>(FixtureImportOrdinal), &livePin)) return Fail(GetLastError());
    InterlockedExchange(&state->references, 1);
    ProbeRecord(Stage::LiveAcquire, 1);
    return TRUE;
}
extern "C" void WINAPI ReleaseFixtureReference() {
    auto* state = ProbeState();
    if (state->references != 1) { Fail(ERROR_INVALID_STATE); return; }
    InterlockedExchange(&state->references, 0);
    ProbeRecord(Stage::LiveRelease, 1);
    const HMODULE pin = livePin;
    livePin = nullptr;
    // The fixture restores caller ownership before releasing this pin.
    if (!FreeLibrary(pin)) Fail(GetLastError());
}
extern "C" BOOL WINAPI RemoveFixtureInstrumentation() {
    auto* state = ProbeState();
    if (state->references != 0) { ProbeRecord(Stage::RemoveDenied, 0); return FALSE; }
    if (!installed) return FALSE;
    const LONG error = ChangeHook(false);
    if (error != NO_ERROR) return Fail(error);
    installed = false;
    InterlockedExchange(&state->ready, 0);
    ProbeRecord(Stage::Removed, 1);
    return TRUE;
}
BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        const BOOL restored = DetourRestoreAfterWith();
        ProbeRecord(Stage::Restore, restored);
        if (!restored) return Fail(ERROR_INVALID_DATA);
        if (ProbeState()->scenario == Scenario::Denied) {
            ProbeRecord(Stage::Error, ERROR_ACCESS_DENIED);
            return FALSE;
        }
        const LONG error = ChangeHook(true);
        if (error != NO_ERROR) return Fail(error);
        installed = true;
        InterlockedExchange(&ProbeState()->ready, 1);
        ProbeRecord(Stage::HelperReady, 1);
    } else if (reason == DLL_PROCESS_DETACH) {
        if (installed) {
            const LONG error = ChangeHook(false);
            if (error != NO_ERROR) Fail(error);
            installed = false;
            InterlockedExchange(&ProbeState()->ready, 0);
        }
        ProbeRecord(Stage::HelperDetach, 1);
    }
    return TRUE;
}
