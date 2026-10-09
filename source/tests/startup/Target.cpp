#include "Contract.h"
#include <mmdeviceapi.h>
extern "C" __declspec(dllimport) void ImportedConsumerTouch();
using Initialize = BOOL (WINAPI*)();
using Run = DWORD (WINAPI*)();
using Stop = BOOL (WINAPI*)();
using Release = void (WINAPI*)();

void NTAPI TargetTls(PVOID, DWORD reason, PVOID) {
    if (reason != DLL_PROCESS_ATTACH) return;
    auto* state = StartupState();
    state->phase = static_cast<LONG>(Phase::Tls);
    StartupEvent(Stage::TlsProbe, Api::None, 0, 0, nullptr);
    if (state->scenario == Scenario::TlsCom) {
        void* output = nullptr;
        OwnedCoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), &output);
        StartupEvent(Stage::ConsumerAfter, Api::Com, 0, 0, nullptr);
    } else if (state->scenario == Scenario::TlsSound) {
        IDirectSound8* output = nullptr;
        OwnedDirectSoundCreate8(nullptr, &output, nullptr);
        StartupEvent(Stage::ConsumerAfter, Api::Sound, 0, 0, nullptr);
    }
}
#pragma const_seg(".CRT$XLB")
extern "C" const PIMAGE_TLS_CALLBACK startupTlsCallback = TargetTls;
#pragma const_seg()
#pragma comment(linker, "/INCLUDE:_tls_used")
#pragma comment(linker, "/INCLUDE:startupTlsCallback")

int main() {
    ImportedConsumerTouch();
    auto* state = StartupState();
    // This join precedes the fixture's entry-readiness milestone. It does not identify the Windows EXE entry boundary.
    if (StartupWorkerScenario(state->scenario)) {
        const DWORD result = JoinStartupWorker();
        if (state->scenario == Scenario::StartupWrongEntry) return result == (0x5100 | 14) && !state->runtimeReady ? 0 : 31;
        if (state->scenario == Scenario::StartupWrongContext) return result == (0x5200 | 13) && !state->runtimeReady ? 0 : 32;
        if (result || !state->runtimeReady) return 33;
    }
    state->phase = static_cast<LONG>(Phase::Entry);
    StartupEvent(Stage::EntryProbe, Api::None, 0, 0, nullptr);
    if (state->uncovered) return 10;
    HMODULE helper = nullptr;
    if (!GetModuleHandleExW(0, L"StartupHelper64.dll", &helper)) return 20;
    const auto initialize = reinterpret_cast<Initialize>(GetProcAddress(helper, "InitializeOwnedRuntime"));
    auto run = reinterpret_cast<Run>(GetProcAddress(helper, "RunOwnedConsumers"));
    const auto again = reinterpret_cast<Run>(GetProcAddress(helper, "RunRetainedConsumers"));
    const auto release = reinterpret_cast<Release>(GetProcAddress(helper, "ReleaseOwnedConsumers"));
    const auto stop = reinterpret_cast<Stop>(GetProcAddress(helper, "StopOwnedRuntime"));
    if (!initialize || !run || !again || !release || !stop) return 21;
    if (!StartupWorkerScenario(state->scenario) && !initialize()) return 21;
    DWORD result = 0;
    if (state->scenario == Scenario::Worker) {
        // Worker startup and this join occur outside DLL initialization.
        HANDLE worker = CreateThread(nullptr, 0, [](LPVOID value) -> DWORD {
            StartupState()->phase = static_cast<LONG>(Phase::Worker);
            StartupState()->workerThread = static_cast<LONG>(GetCurrentThreadId());
            StartupEvent(Stage::WorkerProbe, Api::None, 0, 0, nullptr);
            const auto action = *static_cast<Run*>(value);
            const DWORD code = action();
            return code;
        }, &run, 0, nullptr);
        if (!worker) return 22;
        const DWORD wait = WaitForSingleObject(worker, 10000);
        const BOOL exitRead = GetExitCodeThread(worker, &result);
        CloseHandle(worker);
        if (wait != WAIT_OBJECT_0 || !exitRead) return 23;
        state->phase = static_cast<LONG>(Phase::Entry);
    } else if (!StartupWorkerScenario(state->scenario)) result = run();
    if (result) return static_cast<int>(result);
    if (state->scenario == Scenario::Live) {
        if (!FreeLibrary(helper)) return 24;
        const BOOL retained = GetModuleHandleW(L"StartupHelper64.dll") != nullptr;
        StartupEvent(Stage::HelperRetained, Api::None, 0, retained, nullptr);
        if (!retained || stop() || again() != 0) return 25;
        if (!GetModuleHandleExW(0, L"StartupHelper64.dll", &helper)) return 26;
    }
    release();
    state->phase = static_cast<LONG>(Phase::Shutdown);
    if (!stop()) return 27;
    if (!FreeLibrary(helper)) return 28;
    StartupEvent(Stage::HelperRetained, Api::None, 0, GetModuleHandleW(L"StartupHelper64.dll") != nullptr, nullptr);
    return state->errors ? 29 : 0;
}
