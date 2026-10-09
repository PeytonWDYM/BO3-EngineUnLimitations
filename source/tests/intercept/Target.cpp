#include "Contract.h"
#include <mmdeviceapi.h>
extern "C" __declspec(dllimport) void SdkConsumerTouch();
extern "C" __declspec(dllimport) void WINAPI SdkConsumerRun();
extern "C" __declspec(dllimport) void WINAPI SdkConsumerRelease();
extern "C" __declspec(dllimport) DWORD JoinWorker();

void NTAPI SdkTls(PVOID, DWORD reason, PVOID) {
    if (reason != DLL_PROCESS_ATTACH) return;
    auto* trace = SdkTrace(); trace->phase = static_cast<LONG>(Phase::Tls);
    SdkRecord(Stage::Tls, Api::None, 0, 0, nullptr, nullptr);
    if (trace->scenario == Scenario::TlsCom || trace->scenario == Scenario::TlsSound) {
        ConsumerCheck(trace->hooksReady == 1);
        if (trace->scenario == Scenario::TlsCom) {
            void* value = nullptr;
            CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), &value);
        } else {
            IDirectSound8* value = nullptr;
            DirectSoundCreate8(nullptr, &value, nullptr);
        }
        ConsumerStop(E_UNEXPECTED);
    }
}
#pragma const_seg(".CRT$XLB")
extern "C" const PIMAGE_TLS_CALLBACK sdkTlsCallback = SdkTls;
#pragma const_seg()
#pragma comment(linker, "/INCLUDE:_tls_used")
#pragma comment(linker, "/INCLUDE:sdkTlsCallback")
int main() {
    SdkConsumerTouch();
    auto* trace = SdkTrace();
    if (WorkerScenario(trace->scenario)) {
        const DWORD result = JoinWorker();
        if (trace->scenario == Scenario::WrongEntry) return result == 0x510e && !trace->runtimeReady ? 0 : 10;
        if (trace->scenario == Scenario::WrongContext) return result == 0x520d && !trace->runtimeReady ? 0 : 11;
        ConsumerCheck(result == 0 && trace->runtimeReady == 1);
    }
    trace->phase = static_cast<LONG>(Phase::Entry);
    SdkRecord(Stage::Entry, Api::None, 0, 0, nullptr, nullptr);
    if (!WorkerScenario(trace->scenario)) {
        ConsumerCheck(trace->hooksReady == 1);
        ConsumerGood(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED));
        ConsumerCheck(SdkInitializeEntry() != FALSE);
        SdkConsumerRun();
    }
    if (!WorkerScenario(trace->scenario)) SdkConsumerRelease();
    trace->phase = static_cast<LONG>(Phase::Shutdown);
    ConsumerCheck(SdkStopRuntime() != FALSE);
    if (!WorkerScenario(trace->scenario)) CoUninitialize();
    return trace->errors ? 12 : 0;
}
