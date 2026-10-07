#include "RuntimeOwner.h"
#include <detours.h>

ComFactory OriginalCom = OwnedCoCreateInstance;
SoundFactory OriginalSound = OwnedDirectSoundCreate8;
extern "C" void DetoursOwnedOrdinal() {}

namespace {
void Admit(Api api, const GUID* iid) {
    auto* state = StartupState();
    StartupEvent(Stage::RootEnter, api, 0, 0, iid);
    // Fixture phases are an explicit contract. They do not detect the Windows loader lock.
    if (!state->runtimeReady || (state->phase != static_cast<LONG>(Phase::Entry)
        && state->phase != static_cast<LONG>(Phase::Worker))) StopOwned(E_UNEXPECTED, Stage::EarlyStop);
}
HRESULT WINAPI InterceptCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output) noexcept {
    Admit(Api::Com, &iid);
    try {
        const HRESULT result = OwnedBoundary().CreateCom(clsid, outer, context, iid, output);
        if (FAILED(result) && clsid == __uuidof(MMDeviceEnumerator)) StopOwned(result, Stage::ControlledStop);
        StartupEvent(Stage::RootReturn, Api::Com, 0, result, &iid);
        return result;
    } catch (...) { StopOwned(E_UNEXPECTED, Stage::ControlledStop); }
}
HRESULT WINAPI InterceptSound(LPCGUID device, LPDIRECTSOUND8* output, LPUNKNOWN outer) noexcept {
    Admit(Api::Sound, &IID_IDirectSound8);
    try {
        const HRESULT result = OwnedBoundary().CreateDirectSound(device, output, outer);
        if (FAILED(result)) StopOwned(result, Stage::ControlledStop);
        StartupEvent(Stage::RootReturn, Api::Sound, 0, result, &IID_IDirectSound8);
        return result;
    } catch (...) { StopOwned(E_UNEXPECTED, Stage::ControlledStop); }
}
bool ChangeHooks(bool attach) {
    if (DetourTransactionBegin() != NO_ERROR) return false;
    LONG result = DetourUpdateThread(GetCurrentThread());
    if (result == NO_ERROR) result = attach
        ? DetourAttach(reinterpret_cast<PVOID*>(&OriginalCom), InterceptCom)
        : DetourDetach(reinterpret_cast<PVOID*>(&OriginalCom), InterceptCom);
    if (result == NO_ERROR) result = attach
        ? DetourAttach(reinterpret_cast<PVOID*>(&OriginalSound), InterceptSound)
        : DetourDetach(reinterpret_cast<PVOID*>(&OriginalSound), InterceptSound);
    if (result != NO_ERROR) { DetourTransactionAbort(); return false; }
    return DetourTransactionCommit() == NO_ERROR;
}
}
bool RemoveOwnedHooks() {
    if (StartupState()->hooksReady && !ChangeHooks(false)) return false;
    InterlockedExchange(&StartupState()->hooksReady, 0);
    StartupEvent(Stage::HooksRemoved, Api::None, 0, 1, nullptr);
    return true;
}

// Only POD state, the owned trace, and Detours transactions run under loader lock.
BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        if (!DetourRestoreAfterWith()) return FALSE;
        auto* state = StartupState();
        state->phase = static_cast<LONG>(Phase::Helper);
        StartupEvent(Stage::Restore, Api::None, 0, 1, nullptr);
        if (state->scenario == Scenario::Denied) return FALSE;
        if (state->scenario != Scenario::Baseline) {
            if (!ChangeHooks(true)) return FALSE;
            InterlockedExchange(&state->hooksReady, 1);
            StartupEvent(Stage::HookReady, Api::None, 0, 1, nullptr);
        }
    } else if (reason == DLL_PROCESS_DETACH)
        StartupEvent(Stage::HelperDetach, Api::None, 0, 0, nullptr);
    return TRUE;
}
