#include "ProbeContract.h"
extern "C" __declspec(dllimport) void ConsumerTouch();
using Remove = BOOL (WINAPI*)();
using Acquire = BOOL (WINAPI*)();
using Release = void (WINAPI*)();

void NTAPI TargetTls(PVOID, DWORD reason, PVOID) {
    if (reason == DLL_PROCESS_ATTACH) ProbeOutput(Stage::Tls);
}
#pragma const_seg(".CRT$XLB")
extern "C" const PIMAGE_TLS_CALLBACK targetTlsCallback = TargetTls;
#pragma const_seg()
#pragma comment(linker, "/INCLUDE:_tls_used")
#pragma comment(linker, "/INCLUDE:targetTlsCallback")

int main() {
    ConsumerTouch();
    ProbeOutput(Stage::Entry);
    auto* state = ProbeState();
    if (state->scenario == Scenario::LiveReference || state->scenario == Scenario::Remove) {
        HMODULE helper = nullptr;
        if (!GetModuleHandleExW(0, L"PreentryHelper64.dll", &helper)) return 21;
        const auto remove = reinterpret_cast<Remove>(GetProcAddress(helper, "RemoveFixtureInstrumentation"));
        const auto acquire = reinterpret_cast<Acquire>(GetProcAddress(helper, "AcquireFixtureReference"));
        const auto release = reinterpret_cast<Release>(GetProcAddress(helper, "ReleaseFixtureReference"));
        if (!remove || !acquire || !release) return 22;
        if (state->scenario == Scenario::LiveReference) {
            if (!acquire() || !FreeLibrary(helper)) return 23;
            const HMODULE retained = GetModuleHandleW(L"PreentryHelper64.dll");
            ProbeRecord(Stage::UnloadAttempt, retained != nullptr ? 1 : 0);
            if (!retained || remove()) return 27;
            ProbeOutput(Stage::Entry);
            // Recover caller ownership before releasing the last live-reference pin.
            HMODULE caller = nullptr;
            if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS, reinterpret_cast<LPCWSTR>(remove), &caller)
                    || caller != helper) return 28;
            release();
        }
        if (!remove() || !FreeLibrary(helper)) return 24;
        const bool retained = GetModuleHandleW(L"PreentryHelper64.dll") != nullptr;
        ProbeRecord(Stage::HelperRetained, retained ? 1 : 0);
        if (!retained) return 25;
        // Output resumes only after successful removal and zero live references.
        const LONG normal = OwnedFactory();
        ProbeRecord(Stage::AfterRemove, normal);
        if (normal != 1) return 26;
    }
    return state->unsafeCalls || state->internalErrors ? 10 : 0;
}
