#define STARTUP_SHIM_BUILD
#include "Contract.h"
#include <mmdeviceapi.h>
#include <intrin.h>

namespace {
using Run = DWORD (WINAPI*)();
using Stop = BOOL (WINAPI*)();
[[noreturn]] void Fail() { TerminateProcess(GetCurrentProcess(), 0xe0510002); __fastfail(7); }
void Check(bool condition) { if (!condition) Fail(); }
DWORD Context(LPVOID parameter) { return static_cast<DWORD>(reinterpret_cast<std::uintptr_t>(parameter)); }
}
extern "C" DWORD WINAPI OwnedGenericThread(LPVOID parameter) {
    auto* state = StartupState();
    state->phase = static_cast<LONG>(Phase::Worker);
    state->workerThread = static_cast<LONG>(GetCurrentThreadId());
    InterlockedIncrement(&state->nativeSetups);
    const DWORD slot = TlsAlloc();
    Check(slot != TLS_OUT_OF_INDEXES && TlsSetValue(slot, parameter) != FALSE);
    Check(TlsGetValue(slot) == parameter);
    state->nativeContext = static_cast<LONG>(Context(parameter));
    StartupEvent(Stage::NativeSetup, Api::None, 0, state->nativeContext, nullptr);
    if (state->scenario == Scenario::StartupWrongContext) {
        Check(TlsFree(slot) != FALSE);
        return 0x5200 | Context(parameter);
    }
    StartupEvent(Stage::NativeDispatch, Api::None, 0, state->nativeContext, nullptr);
    if (state->scenario == Scenario::StartupColdCom) {
        void* output = nullptr;
        OwnedCoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), &output);
        StartupEvent(Stage::ConsumerAfter, Api::Com, 0, 0, nullptr);
    } else if (state->scenario == Scenario::StartupColdSound) {
        IDirectSound8* output = nullptr;
        OwnedDirectSoundCreate8(nullptr, &output, nullptr);
        StartupEvent(Stage::ConsumerAfter, Api::Sound, 0, 0, nullptr);
    }
    if (!state->runtimeReady) {
        void* output = nullptr;
        OwnedCoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), &output);
        StartupEvent(Stage::ConsumerAfter, Api::Com, 0, 0, nullptr);
        Fail();
    }
    const auto helper = GetModuleHandleW(L"StartupHelper64.dll");
    const auto run = reinterpret_cast<Run>(GetProcAddress(helper, "RunOwnedConsumers"));
    const auto again = reinterpret_cast<Run>(GetProcAddress(helper, "RunRetainedConsumers"));
    const auto stop = reinterpret_cast<Stop>(GetProcAddress(helper, "StopOwnedRuntime"));
    Check(run && again && stop);
    const DWORD result = run();
    Check(result == 0 && stop() == FALSE && again() == 0);
    Check(TlsGetValue(slot) == parameter && TlsFree(slot) != FALSE);
    StartupEvent(Stage::NativeExit, Api::None, 0, static_cast<LONG>(result), nullptr);
    return result;
}
extern "C" DWORD WINAPI OwnedOtherThread(LPVOID parameter) {
    StartupState()->workerThread = static_cast<LONG>(GetCurrentThreadId());
    StartupEvent(Stage::NativeExit, Api::None, 0, static_cast<LONG>(Context(parameter)), nullptr);
    return 0x5100 | Context(parameter);
}
extern "C" void CreateStartupWorker() {
    auto* state = StartupState();
    state->creatorThread = static_cast<LONG>(GetCurrentThreadId());
    const auto entry = state->scenario == Scenario::StartupWrongEntry ? OwnedOtherThread : OwnedGenericThread;
    const DWORD context = state->scenario == Scenario::StartupWrongContext || state->scenario == Scenario::StartupColdCom
        || state->scenario == Scenario::StartupColdSound ? 13 : 14;
    LPVOID parameter = reinterpret_cast<LPVOID>(static_cast<std::uintptr_t>(context));
    state->originalEntry = reinterpret_cast<std::uintptr_t>(entry);
    state->originalParameter = reinterpret_cast<std::uintptr_t>(parameter);
    DWORD id = 0;
    const HANDLE thread = OwnedCreateThread(nullptr, 0, entry, parameter, CREATE_SUSPENDED, &id);
    Check(thread != nullptr && id != 0 && GetThreadId(thread) == id);
    state->returnedHandle = reinterpret_cast<std::uintptr_t>(thread);
    state->returnedThread = static_cast<LONG>(id);
    StartupEvent(Stage::ThreadReturned, Api::None, 0, static_cast<LONG>(id), nullptr);
    DWORD pending = 0;
    Check(GetExitCodeThread(thread, &pending) != FALSE && pending == STILL_ACTIVE && state->workerThread == 0 && state->nativeSetups == 0);
    StartupEvent(Stage::SuspendedChecked, Api::None, 0, 1, nullptr);
    const BOOL priority = SetThreadPriority(thread, THREAD_PRIORITY_TIME_CRITICAL);
    Check(priority != FALSE && GetThreadPriority(thread) == THREAD_PRIORITY_TIME_CRITICAL);
    state->priorityResult = priority;
    StartupEvent(Stage::ThreadPriority, Api::None, 0, THREAD_PRIORITY_TIME_CRITICAL, nullptr);
    state->resumeResult = static_cast<LONG>(ResumeThread(thread));
    Check(state->resumeResult == 1);
    StartupEvent(Stage::ThreadResume, Api::None, 0, state->resumeResult, nullptr);
}
extern "C" DWORD JoinStartupWorker() {
    auto* state = StartupState();
    const HANDLE thread = reinterpret_cast<HANDLE>(static_cast<std::uintptr_t>(state->returnedHandle));
    Check(WaitForSingleObject(thread, 15000) == WAIT_OBJECT_0);
    DWORD result = 0;
    Check(GetExitCodeThread(thread, &result) != FALSE && GetThreadId(thread) == static_cast<DWORD>(state->returnedThread));
    Check(CloseHandle(thread) != FALSE);
    StartupEvent(Stage::WorkerJoined, Api::None, 0, static_cast<LONG>(result), nullptr);
    return result;
}
