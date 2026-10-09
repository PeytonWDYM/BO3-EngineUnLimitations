#include "Harness.h"
#include <cstring>
#include <cstdlib>
#include <new>

namespace activation_test { thread_local bool FailNextAllocation = false; }
void* operator new(size_t bytes) {
    if (activation_test::FailNextAllocation) { activation_test::FailNextAllocation = false; throw std::bad_alloc(); }
    if (void* memory = malloc(bytes)) return memory;
    throw std::bad_alloc();
}
void operator delete(void* memory) noexcept { free(memory); }
void operator delete(void* memory, size_t) noexcept { free(memory); }

namespace activation_test {
#ifndef ACTIVATION_BASELINE
class Bridge final : public activation::Provider {
public:
    explicit Bridge(std::shared_ptr<MemoryProvider> provider) : provider_(std::move(provider)) {}
    HRESULT CreateCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output) override { return provider_->CreateCom(clsid, outer, context, iid, output); }
    HRESULT CreateDirectSound(LPCGUID device, LPDIRECTSOUND8* output, LPUNKNOWN outer) override { return provider_->CreateDirectSound(device, output, outer); }
    [[noreturn]] void Abort(HRESULT code, const char* stage) override { provider_->Abort(code, stage); }
private:
    std::shared_ptr<MemoryProvider> provider_;
};
#endif
Harness::Harness(std::shared_ptr<State> state) : provider_(std::make_shared<MemoryProvider>(std::move(state))) {
#ifndef ACTIVATION_BASELINE
    boundary_ = std::make_unique<activation::Boundary>(std::make_shared<Bridge>(provider_));
#endif
}
HRESULT Harness::CreateCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output) {
#ifdef ACTIVATION_BASELINE
    return provider_->CreateCom(clsid, outer, context, iid, output);
#else
    return boundary_->CreateCom(clsid, outer, context, iid, output);
#endif
}
HRESULT Harness::CreateDirectSound(LPCGUID device, LPDIRECTSOUND8* output, LPUNKNOWN outer) {
#ifdef ACTIVATION_BASELINE
    return provider_->CreateDirectSound(device, output, outer);
#else
    return boundary_->CreateDirectSound(device, output, outer);
#endif
}
bool Harness::CanUnload() const {
#ifdef ACTIVATION_BASELINE
    return true;
#else
    return boundary_->CanUnload();
#endif
}
void Initialize(IAudioClient* client) {
    WAVEFORMATEX* format = nullptr;
    Ok(client->GetMixFormat(&format));
    const HRESULT result = client->Initialize(AUDCLNT_SHAREMODE_SHARED, AUDCLNT_STREAMFLAGS_EVENTCALLBACK | AUDCLNT_STREAMFLAGS_NOPERSIST, 250000, 0, format, nullptr);
    CoTaskMemFree(format);
    Ok(result);
    Ok(client->SetEventHandle(reinterpret_cast<HANDLE>(1)));
}
Chain CreateChain(Harness& harness, State& state, bool initialize) {
    Chain chain;
    Ok(harness.CreateCom(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), reinterpret_cast<void**>(chain.enumerator.GetAddressOf())));
    Ok(chain.enumerator->GetDefaultAudioEndpoint(eRender, eConsole, &chain.device));
    Ok(chain.device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, reinterpret_cast<void**>(chain.client.GetAddressOf())));
    chain.generation = state.generations.back()->id;
    if (initialize) {
        Initialize(chain.client.Get());
        Ok(chain.client->GetService(__uuidof(IAudioRenderClient), reinterpret_cast<void**>(chain.render.GetAddressOf())));
        Publish(state, chain.render.Get(), "render", chain.generation);
        Ok(chain.client->GetService(__uuidof(IAudioSessionControl), reinterpret_cast<void**>(chain.session.GetAddressOf())));
    }
    return chain;
}
void Render(IAudioRenderClient* render, State& state, unsigned generation) {
    BYTE* samples = nullptr;
    Ok(render->GetBuffer(8, &samples));
    memset(samples, 0x3f, 8 * 2 * 4);
    Ok(render->ReleaseBuffer(8, 0));
    state.Event("consumer.render.release", generation);
}
void Record(fixture::Scenario& test, const State& state) {
    std::string trace = "[";
    for (size_t index = 0; index < state.events.size(); ++index) {
        if (index) trace += ',';
        trace += fixture::Quote(state.events[index]);
    }
    trace += ']';
    test.evidence.emplace_back("events", trace);
    test.Number("generations", static_cast<unsigned>(state.generations.size()));
    test.Number("rawLeafPublications", state.rawPublications);
    test.Number("controlledAborts", state.aborts);
}
DSBUFFERDESC Description(WAVEFORMATEX& format) {
    format = {WAVE_FORMAT_PCM, 2, 48000, 192000, 4, 16, 0};
    DSBUFFERDESC description{};
    description.dwSize = sizeof(description);
    description.dwFlags = 0x80e8;
    description.dwBufferBytes = 128;
    description.lpwfxFormat = &format;
    return description;
}
HRESULT NativeBufferCreate(IDirectSound8* device, const DSBUFFERDESC& description, IDirectSoundBuffer** output, State& state) {
    const HRESULT result = device->CreateSoundBuffer(&description, output, nullptr);
    if (FAILED(result)) {
        // Model the native null-Release branch without dereferencing null.
        state.unsafeBranchReached = !*output;
        state.Event("consumer.native-failure-branch");
        if (*output) { (*output)->Release(); *output = nullptr; }
    }
    return result;
}
}
