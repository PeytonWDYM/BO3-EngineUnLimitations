#include "Internal.h"
#include "../../tests/activation/Providers.h"
#include <memory>

namespace activation_test { thread_local bool FailNextAllocation = false; }
namespace {
class Roots final : public activation::Provider {
public:
    HRESULT CreateCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output) override;
    HRESULT CreateDirectSound(LPCGUID device, LPDIRECTSOUND8* output, LPUNKNOWN outer) override;
    [[noreturn]] void Abort(HRESULT code, const char*) override { StopSdk(code, Stage::UnsupportedStop); }
};
struct Owner {
    std::shared_ptr<activation_test::State> memoryState;
    std::unique_ptr<activation_test::MemoryProvider> memory;
    std::unique_ptr<activation::Boundary> boundary;
    HMODULE reference = nullptr;
};
Owner* owner;
void DescribeSdk() {
    const std::uint64_t addresses[] = {SdkTrace()->sdkCom, SdkTrace()->sdkSound, SdkTrace()->sdkThread};
    for (size_t index = 0; index < 3; ++index)
        RequireSdk(DescribeAddress(addresses[index], SdkTrace()->sdkModules[index]));
}
HRESULT Roots::CreateCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output) {
    InterlockedIncrement(&SdkTrace()->providerCalls);
    SdkRecord(Stage::ProviderEnter, Api::Com, 0, 0, &clsid, &iid);
    if (SdkTrace()->mode == Mode::Memory) return owner->memory->CreateCom(clsid, outer, context, iid, output);
    InterlockedIncrement(&SdkTrace()->physicalAudioCalls);
    return OriginalCom(clsid, outer, context, iid, output);
}
HRESULT Roots::CreateDirectSound(LPCGUID device, LPDIRECTSOUND8* output, LPUNKNOWN outer) {
    InterlockedIncrement(&SdkTrace()->providerCalls);
    SdkRecord(Stage::ProviderEnter, Api::Sound, 0, 0, nullptr, &IID_IDirectSound8);
    if (SdkTrace()->mode == Mode::Memory) return owner->memory->CreateDirectSound(device, output, outer);
    InterlockedIncrement(&SdkTrace()->physicalAudioCalls);
    return OriginalSound(device, output, outer);
}
}
BOOL InitializeSdk(Phase phase) {
    try {
        auto* trace = SdkTrace();
        RequireSdk(owner == nullptr && trace->hooksReady == 1 && trace->phase == static_cast<LONG>(phase));
        if (trace->scenario == Scenario::Denied) StopSdk(E_ACCESSDENIED, Stage::Error);
        DescribeSdk();
        auto value = std::make_unique<Owner>();
        if (trace->mode == Mode::Memory) {
            value->memoryState = std::make_shared<activation_test::State>();
            value->memoryState->events.reserve(512);
            value->memoryState->sessionRegisterResult = S_FALSE;
            value->memoryState->buffer8 = trace->scenario != Scenario::NoBuffer8;
            if (trace->scenario == Scenario::ClearFailed) value->memoryState->clearError = DSERR_BUFFERLOST;
            if (trace->scenario == Scenario::Reentrant) value->memoryState->reenterRoot = [] {
                void* output = nullptr;
                CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), &output);
                StopSdk(E_UNEXPECTED, Stage::Error);
            };
            value->memory = std::make_unique<activation_test::MemoryProvider>(value->memoryState);
        }
        if (trace->scenario != Scenario::Baseline)
            value->boundary = std::make_unique<activation::Boundary>(std::make_shared<Roots>());
        RequireSdk(GetModuleHandleExW(0, L"SdkInterceptHelper.dll", &value->reference) != FALSE);
        owner = value.release();
        InterlockedIncrement(&trace->constructors);
        InterlockedExchange(&trace->runtimeReady, 1);
        SdkRecord(Stage::RuntimeReady, Api::None, 0, 1, nullptr, nullptr);
        return TRUE;
    } catch (...) { StopSdk(E_UNEXPECTED, Stage::Error); }
}
extern "C" BOOL WINAPI SdkInitializeEntry() { return InitializeSdk(Phase::Entry); }
HRESULT ProviderCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output) {
    Roots raw;
    return owner->boundary ? owner->boundary->CreateCom(clsid, outer, context, iid, output)
        : raw.CreateCom(clsid, outer, context, iid, output);
}
HRESULT ProviderSound(LPCGUID device, LPDIRECTSOUND8* output, LPUNKNOWN outer) {
    Roots raw;
    return owner->boundary ? owner->boundary->CreateDirectSound(device, output, outer) : raw.CreateDirectSound(device, output, outer);
}
extern "C" void WINAPI SdkObserve(IUnknown* object, Api api, DWORD generation) {
    LONG raw = 0;
    if (SdkTrace()->mode == Mode::Memory) {
        raw = activation_test::IsRaw(object);
        if (raw) InterlockedIncrement(&SdkTrace()->rawPublications);
    }
    SdkRecord(api == Api::Com ? Stage::RenderPublish : Stage::BufferPublish, api, generation, raw, nullptr, nullptr);
}
extern "C" void WINAPI SdkFireCallbacks() {
    try {
        RequireSdk(SdkTrace()->mode == Mode::Memory && owner != nullptr);
        owner->memoryState->callbackExpectedThread = GetCurrentThreadId();
        owner->memoryState->NotifyEndpoint();
        owner->memoryState->NotifySession(owner->memoryState->generations.front());
    } catch (...) { StopSdk(E_UNEXPECTED, Stage::Error); }
}
extern "C" void WINAPI SdkSnapshot() {
    if (!owner || !owner->memoryState) return;
    const auto& state = *owner->memoryState;
    auto* trace = SdkTrace();
    trace->generations = static_cast<LONG>(state.generations.size());
    trace->renderPackets = trace->silentRenderPackets = trace->soundObservations = trace->silentSoundObservations = 0;
    for (const auto& generation : state.generations) {
        if (generation->sound) for (const bool silent : generation->sound->outputs) {
            ++trace->soundObservations; if (silent) ++trace->silentSoundObservations;
        } else for (const auto& packet : generation->render->packets) {
            ++trace->renderPackets; if (packet.silent) ++trace->silentRenderPackets;
        }
    }
}
extern "C" BOOL WINAPI SdkStopRuntime() {
    try {
        RequireSdk(owner != nullptr);
        if (owner->boundary && !owner->boundary->CanUnload()) {
            SdkRecord(Stage::RemovalDenied, Api::None, 0, 1, nullptr, nullptr); return FALSE;
        }
        SdkSnapshot();
        InterlockedExchange(&SdkTrace()->runtimeReady, 0);
        SdkRecord(Stage::RuntimeClosed, Api::None, 0, 1, nullptr, nullptr);
        if (SdkTrace()->mode == Mode::PhysicalSilent) {
            SdkRecord(Stage::Retained, Api::None, 0, 1, nullptr, nullptr); return TRUE;
        }
        const auto reference = owner->reference;
        delete owner; owner = nullptr;
        RequireSdk(ChangeHooks(false));
        InterlockedExchange(&SdkTrace()->hooksReady, 0);
        SdkRecord(Stage::HooksRemoved, Api::None, 0, 1, nullptr, nullptr);
        RequireSdk(FreeLibrary(reference) != FALSE);
        return TRUE;
    } catch (...) { StopSdk(E_UNEXPECTED, Stage::Error); }
}
