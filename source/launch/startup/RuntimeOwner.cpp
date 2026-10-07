#include "RuntimeOwner.h"
#include <memory>

namespace activation_test { thread_local bool FailNextAllocation = false; }
namespace {
class Roots final : public activation::Provider {
public:
    HRESULT CreateCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output) override {
        return OriginalCom(clsid, outer, context, iid, output);
    }
    HRESULT CreateDirectSound(LPCGUID device, LPDIRECTSOUND8* output, LPUNKNOWN outer) override {
        return OriginalSound(device, output, outer);
    }
    [[noreturn]] void Abort(HRESULT code, const char*) override { StopOwned(code, Stage::ControlledStop); }
};
struct Owner {
    std::shared_ptr<activation_test::State> state;
    std::unique_ptr<activation_test::MemoryProvider> memory;
    std::unique_ptr<activation::Boundary> boundary;
    HMODULE reference = nullptr;
};
Owner* owner;
HRESULT WINAPI MemoryCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output) {
    try {
        InterlockedIncrement(&StartupState()->providerCalls);
        return owner->memory->CreateCom(clsid, outer, context, iid, output);
    } catch (...) { StopOwned(E_UNEXPECTED, Stage::Error); }
}
HRESULT WINAPI MemorySound(LPCGUID device, LPDIRECTSOUND8* output, LPUNKNOWN outer) {
    try {
        InterlockedIncrement(&StartupState()->providerCalls);
        return owner->memory->CreateDirectSound(device, output, outer);
    } catch (...) { StopOwned(E_UNEXPECTED, Stage::Error); }
}
}
activation_test::State& MemoryState() { return *owner->state; }
activation::Boundary& OwnedBoundary() { return *owner->boundary; }

// The owned entrypoint calls this after DLL initialization and TLS have finished.
extern "C" BOOL WINAPI InitializeOwnedRuntime() {
    try {
        auto* trace = StartupState();
        CheckOwned(owner == nullptr && trace->phase == static_cast<LONG>(Phase::Entry));
        CheckOwned(trace->scenario == Scenario::Baseline || trace->hooksReady == 1);
        auto value = std::make_unique<Owner>();
        value->state = std::make_shared<activation_test::State>();
        value->state->events.reserve(512);
        value->state->sharedIdentity = trace->scenario == Scenario::SharedEntry;
        value->state->buffer8 = trace->scenario != Scenario::NoBuffer8;
        if (trace->scenario == Scenario::ClearFailed) value->state->clearError = DSERR_BUFFERLOST;
        value->memory = std::make_unique<activation_test::MemoryProvider>(value->state);
        if (trace->scenario != Scenario::Baseline)
            value->boundary = std::make_unique<activation::Boundary>(std::make_shared<Roots>());
        CheckOwned(GetModuleHandleExW(0, L"StartupHelper64.dll", &value->reference) != FALSE);
        owner = value.release();
        InterlockedIncrement(&trace->constructors);
        SetMemoryFactories(MemoryCom, MemorySound);
        InterlockedExchange(&trace->runtimeReady, 1);
        StartupEvent(Stage::RuntimeReady, Api::None, 0, 1, nullptr);
        const auto shim = GetModuleHandleW(L"StartupFactories.dll");
        const auto named = GetProcAddress(shim, "OwnedDirectSoundCreate8Named");
        const auto ordinal = GetProcAddress(shim, MAKEINTRESOURCEA(11));
        CheckOwned(named != nullptr && named == ordinal);
        StartupEvent(Stage::OrdinalMatch, Api::Sound, 0, 1, nullptr);
        return TRUE;
    } catch (...) { StopOwned(E_UNEXPECTED, Stage::Error); }
}
extern "C" DWORD WINAPI RunOwnedConsumers() {
    try { return ConsumeFamilies(); }
    catch (...) { StopOwned(E_UNEXPECTED, Stage::Error); }
}
extern "C" DWORD WINAPI RunRetainedConsumers() {
    try { return ConsumeRetained(); }
    catch (...) { StopOwned(E_UNEXPECTED, Stage::Error); }
}
extern "C" void WINAPI ReleaseOwnedConsumers() {
    try { ReleaseFamilies(); }
    catch (...) { StopOwned(E_UNEXPECTED, Stage::Error); }
}
bool DestroyOwnedRuntime() {
    CheckOwned(owner != nullptr);
    if (owner->boundary && !owner->boundary->CanUnload()) {
        StartupEvent(Stage::RemovalDenied, Api::None, 0, 1, nullptr);
        return false;
    }
    SnapshotMemory();
    InterlockedExchange(&StartupState()->runtimeReady, 0);
    SetMemoryFactories(nullptr, nullptr);
    const auto reference = owner->reference;
    delete owner;
    owner = nullptr;
    StartupEvent(Stage::RuntimeDestroyed, Api::None, 0, 1, nullptr);
    CheckOwned(RemoveOwnedHooks());
    CheckOwned(FreeLibrary(reference) != FALSE);
    return true;
}
extern "C" BOOL WINAPI StopOwnedRuntime() {
    try { return DestroyOwnedRuntime() ? TRUE : FALSE; }
    catch (...) { StopOwned(E_UNEXPECTED, Stage::Error); }
}
