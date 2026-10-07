#define STARTUP_SHIM_BUILD
#include "Contract.h"
static Shared* state;
static ComFactory comFactory;
static SoundFactory soundFactory;
extern "C" Shared* StartupState() { return state; }
extern "C" void SetMemoryFactories(ComFactory com, SoundFactory sound) { comFactory = com; soundFactory = sound; }
extern "C" __declspec(noinline) HANDLE WINAPI OwnedCreateThread(LPSECURITY_ATTRIBUTES attributes, SIZE_T stack,
    LPTHREAD_START_ROUTINE entry, LPVOID parameter, DWORD flags, LPDWORD id) {
    state->attributesPresent = attributes != nullptr;
    state->stackSize = stack;
    state->creationFlags = flags;
    state->nativeEntry = reinterpret_cast<std::uintptr_t>(entry);
    state->nativeParameter = reinterpret_cast<std::uintptr_t>(parameter);
    StartupEvent(Stage::ThreadCreate, Api::None, 0, static_cast<LONG>(flags), nullptr);
    return CreateThread(attributes, stack, entry, parameter, flags, id);
}
extern "C" void StartupEvent(Stage stage, Api api, DWORD generation, LONG value, const GUID* iid) {
    const LONG index = InterlockedIncrement(&state->count) - 1;
    if (index >= 0 && index < kEventCapacity) {
        state->events[index] = {stage, static_cast<Phase>(state->phase), api, GetCurrentThreadId(), generation,
                               value, state->hooksReady, state->runtimeReady, iid ? *iid : GUID{}};
    } else InterlockedIncrement(&state->errors);
}
extern "C" __declspec(noinline) HRESULT WINAPI OwnedCoCreateInstance(REFCLSID clsid, LPUNKNOWN outer,
    DWORD context, REFIID iid, void** output) {
    StartupEvent(Stage::RawFactory, Api::Com, 0, 0, &iid);
    if (!comFactory) {
        if (output) *output = nullptr;
        InterlockedIncrement(&state->uncovered);
        StartupEvent(Stage::Uncovered, Api::Com, 0, E_UNEXPECTED, &iid);
        return E_UNEXPECTED;
    }
    return comFactory(clsid, outer, context, iid, output);
}
extern "C" __declspec(noinline) HRESULT WINAPI OwnedDirectSoundCreate8(LPCGUID device,
    LPDIRECTSOUND8* output, LPUNKNOWN outer) {
    StartupEvent(Stage::RawFactory, Api::Sound, 0, 0, nullptr);
    if (!soundFactory) {
        if (output) *output = nullptr;
        InterlockedIncrement(&state->uncovered);
        StartupEvent(Stage::Uncovered, Api::Sound, 0, E_UNEXPECTED, nullptr);
        return E_UNEXPECTED;
    }
    return soundFactory(device, output, outer);
}
BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        wchar_t text[32]{};
        const DWORD length = GetEnvironmentVariableW(L"BO3_OWNED_STARTUP_TRACE", text, 32);
        if (length == 0 || length >= 32) return FALSE;
        std::uintptr_t handle = 0;
        for (DWORD i = 0; i < length; ++i) {
            if (text[i] < L'0' || text[i] > L'9') return FALSE;
            handle = handle * 10 + static_cast<unsigned>(text[i] - L'0');
        }
        state = static_cast<Shared*>(MapViewOfFile(reinterpret_cast<HANDLE>(handle), FILE_MAP_WRITE, 0, 0, sizeof(Shared)));
        if (!state || state->magic != kStartupMagic) return FALSE;
        state->phase = static_cast<LONG>(Phase::Dependency);
        if (state->scenario == Scenario::Dependency) {
            void* output = nullptr;
            const GUID clsid{};
            OwnedCoCreateInstance(clsid, nullptr, CLSCTX_ALL, IID_IUnknown, &output);
        }
    } else if (reason == DLL_PROCESS_DETACH && state) UnmapViewOfFile(state);
    return TRUE;
}
