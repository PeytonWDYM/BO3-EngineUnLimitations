#include "Consumer.h"

namespace {
DWORD Context(LPVOID parameter) { return static_cast<DWORD>(reinterpret_cast<std::uintptr_t>(parameter)); }
}
extern "C" DWORD WINAPI SdkOwnedWorker(LPVOID parameter) {
    auto* trace = SdkTrace();
    trace->phase = static_cast<LONG>(Phase::Worker);
    trace->workerTid = static_cast<LONG>(GetCurrentThreadId());
    InterlockedIncrement(&trace->nativeSetups);
    const DWORD slot = TlsAlloc();
    ConsumerCheck(slot != TLS_OUT_OF_INDEXES && TlsSetValue(slot, parameter) != FALSE && TlsGetValue(slot) == parameter);
    trace->nativeContext = static_cast<LONG>(Context(parameter));
    SdkRecord(Stage::Setup, Api::Thread, 0, trace->nativeContext, nullptr, nullptr);
    if (trace->scenario == Scenario::WrongContext) {
        ConsumerCheck(TlsFree(slot) != FALSE);
        return 0x5200 | Context(parameter);
    }
    ConsumerGood(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED));
    SdkRecord(Stage::Dispatch, Api::Thread, 0, trace->nativeContext, nullptr, nullptr);
    // The red memory helper leaves the runtime cold. Check only committed interception before this SDK call.
    if (!trace->runtimeReady) {
        ConsumerCheck(trace->hooksReady == 1);
        void* value = nullptr;
        CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), &value);
        ConsumerStop(E_UNEXPECTED);
    }
    try {
        RunConsumers();
        if (trace->mode == Mode::Memory && trace->scenario != Scenario::Baseline) {
            ConsumerCheck(SdkStopRuntime() == FALSE);
            RetainedConsumers();
        }
        ReleaseConsumers();
    } catch (...) { ConsumerStop(E_UNEXPECTED); }
    ConsumerCheck(TlsGetValue(slot) == parameter && TlsFree(slot) != FALSE);
    CoUninitialize();
    return 0;
}
extern "C" DWORD WINAPI SdkOtherWorker(LPVOID parameter) {
    SdkTrace()->workerTid = static_cast<LONG>(GetCurrentThreadId());
    return 0x5100 | Context(parameter);
}
void CreateWorker() {
    auto* trace = SdkTrace();
    trace->creatorTid = static_cast<LONG>(GetCurrentThreadId());
    const auto entry = trace->scenario == Scenario::WrongEntry ? SdkOtherWorker : SdkOwnedWorker;
    const DWORD context = trace->scenario == Scenario::WrongContext ? 13 : 14;
    trace->originalEntry = reinterpret_cast<std::uintptr_t>(entry);
    trace->parameter = context; trace->flags = CREATE_SUSPENDED; trace->stackSize = 0; trace->attributesPresent = 0;
    DWORD id = 0;
    SdkRecord(Stage::ThreadCreate, Api::Thread, 0, CREATE_SUSPENDED, nullptr, nullptr);
    const HANDLE thread = CreateThread(nullptr, 0, entry, reinterpret_cast<LPVOID>(static_cast<std::uintptr_t>(context)), CREATE_SUSPENDED, &id);
    ConsumerCheck(thread != nullptr && id != 0 && GetThreadId(thread) == id);
    trace->returnedHandle = reinterpret_cast<std::uintptr_t>(thread); trace->returnedTid = static_cast<LONG>(id);
    SdkRecord(Stage::ThreadReturned, Api::Thread, 0, static_cast<LONG>(id), nullptr, nullptr);
    DWORD pending = 0;
    ConsumerCheck(GetExitCodeThread(thread, &pending) != FALSE && pending == STILL_ACTIVE && trace->workerTid == 0);
    SdkRecord(Stage::Suspended, Api::Thread, 0, 1, nullptr, nullptr);
    trace->priorityResult = SetThreadPriority(thread, THREAD_PRIORITY_TIME_CRITICAL);
    ConsumerCheck(trace->priorityResult != 0 && GetThreadPriority(thread) == THREAD_PRIORITY_TIME_CRITICAL);
    SdkRecord(Stage::Priority, Api::Thread, 0, THREAD_PRIORITY_TIME_CRITICAL, nullptr, nullptr);
    trace->resumeResult = static_cast<LONG>(ResumeThread(thread));
    ConsumerCheck(trace->resumeResult == 1);
    SdkRecord(Stage::Resume, Api::Thread, 0, trace->resumeResult, nullptr, nullptr);
}
DWORD JoinWorker() {
    auto* trace = SdkTrace();
    const HANDLE thread = reinterpret_cast<HANDLE>(static_cast<std::uintptr_t>(trace->returnedHandle));
    ConsumerCheck(WaitForSingleObject(thread, 15000) == WAIT_OBJECT_0);
    DWORD result = 0;
    ConsumerCheck(GetExitCodeThread(thread, &result) != FALSE && GetThreadId(thread) == static_cast<DWORD>(trace->returnedTid));
    ConsumerCheck(CloseHandle(thread) != FALSE);
    SdkRecord(Stage::Joined, Api::Thread, 0, static_cast<LONG>(result), nullptr, nullptr);
    return result;
}
extern "C" __declspec(dllexport) void SdkConsumerTouch() {}
extern "C" __declspec(dllexport) void WINAPI SdkConsumerRun() {
    try { RunConsumers(); } catch (...) { ConsumerStop(E_UNEXPECTED); }
}
extern "C" __declspec(dllexport) void WINAPI SdkConsumerRelease() {
    try { ReleaseConsumers(); } catch (...) { ConsumerStop(E_UNEXPECTED); }
}
BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID) {
    if (reason != DLL_PROCESS_ATTACH) return TRUE;
    auto* trace = SdkTrace();
    trace->phase = static_cast<LONG>(Phase::Imported);
    SdkRecord(Stage::Imported, Api::None, 0, 0, nullptr, nullptr);
    if (WorkerScenario(trace->scenario)) CreateWorker();
    if (trace->scenario == Scenario::ImportCom || trace->scenario == Scenario::ImportSound) {
        ConsumerCheck(trace->hooksReady == 1);
        if (trace->scenario == Scenario::ImportCom) {
            void* value = nullptr;
            CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), &value);
        } else {
            IDirectSound8* value = nullptr;
            DirectSoundCreate8(nullptr, &value, nullptr);
        }
        ConsumerStop(E_UNEXPECTED);
    }
    return TRUE;
}
