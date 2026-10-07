#define PREENTRY_PROVIDER_BUILD
#include "ProbeContract.h"
static SharedTrace* trace;

extern "C" SharedTrace* ProbeState() { return trace; }
extern "C" void ProbeRecord(Stage stage, LONG output) {
    const LONG index = InterlockedIncrement(&trace->count) - 1;
    if (index >= 0 && index < static_cast<LONG>(kMaximumEvents))
        trace->events[index] = {static_cast<DWORD>(stage), trace->ready, output, trace->references};
    else InterlockedIncrement(&trace->internalErrors);
}
extern "C" __declspec(noinline) LONG OwnedFactory() {
    volatile LONG value = 1;
    return value;
}
extern "C" void ProbeOutput(Stage stage) {
    const LONG output = OwnedFactory();
    if (output != 0 || trace->ready == 0) InterlockedIncrement(&trace->unsafeCalls);
    ProbeRecord(stage, output);
}

BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        wchar_t text[32]{};
        const DWORD length = GetEnvironmentVariableW(L"BO3_OWNED_PREENTRY_TRACE", text, 32);
        if (length == 0 || length >= 32) return FALSE;
        std::uintptr_t value = 0;
        for (DWORD i = 0; i < length; ++i) {
            if (text[i] < L'0' || text[i] > L'9') return FALSE;
            value = value * 10 + static_cast<unsigned>(text[i] - L'0');
        }
        trace = static_cast<SharedTrace*>(MapViewOfFile(reinterpret_cast<HANDLE>(value), FILE_MAP_WRITE, 0, 0, sizeof(SharedTrace)));
        if (!trace || trace->magic != kTraceMagic) return FALSE;
        if (trace->scenario == Scenario::EarlyDependency) ProbeOutput(Stage::ProviderInit);
    } else if (reason == DLL_PROCESS_DETACH && trace) UnmapViewOfFile(trace);
    return TRUE;
}
