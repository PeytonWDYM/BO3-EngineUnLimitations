#pragma once
#include "ProviderCommon.h"
#ifndef ACTIVATION_BASELINE
#include "../../launch/activation/ActivationBoundary.h"
#endif

namespace activation_test {
class Harness {
public:
    explicit Harness(std::shared_ptr<State> state);
    HRESULT CreateCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output);
    HRESULT CreateDirectSound(LPCGUID device, LPDIRECTSOUND8* output, LPUNKNOWN outer);
    bool CanUnload() const;
private:
    std::shared_ptr<MemoryProvider> provider_;
#ifndef ACTIVATION_BASELINE
    std::unique_ptr<activation::Boundary> boundary_;
#endif
};
struct Chain { ComPtr<IMMDeviceEnumerator> enumerator; ComPtr<IMMDevice> device; ComPtr<IAudioClient> client; ComPtr<IAudioRenderClient> render; ComPtr<IAudioSessionControl> session; unsigned generation = 0; };
Chain CreateChain(Harness& harness, State& state, bool initialize = true);
void Initialize(IAudioClient* client);
void Render(IAudioRenderClient* render, State& state, unsigned generation);
void Record(fixture::Scenario& test, const State& state);
HRESULT NativeBufferCreate(IDirectSound8* device, const DSBUFFERDESC& description, IDirectSoundBuffer** output, State& state);
DSBUFFERDESC Description(WAVEFORMATEX& format);
void WasapiScenarios(fixture::Report& report);
void OtherScenarios(fixture::Report& report);
template<typename Action> void Run(fixture::Report& report, const char* name, Action action) {
    report.Run(name, [&](fixture::Scenario& test) {
        auto state = std::make_shared<State>();
        state->events.reserve(512);
        Harness harness(state);
        try { action(test, *state, harness); }
        catch (...) { FailNextAllocation = false; Record(test, *state); throw; }
        Record(test, *state);
        Require(state->rawPublications == 0, "A raw output leaf reached the consumer");
    });
}

class EndpointCallback final : public Object<IMMNotificationClient> {
public:
    explicit EndpointCallback(std::function<void()> action) : Object(__uuidof(IMMNotificationClient)), action_(std::move(action)) {}
    HRESULT STDMETHODCALLTYPE OnDeviceStateChanged(LPCWSTR, DWORD) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnDeviceAdded(LPCWSTR) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnDeviceRemoved(LPCWSTR) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnDefaultDeviceChanged(EDataFlow, ERole, LPCWSTR) override { action_(); return S_OK; }
    HRESULT STDMETHODCALLTYPE OnPropertyValueChanged(LPCWSTR, const PROPERTYKEY) override { return S_OK; }
private:
    std::function<void()> action_;
};
class SessionCallback final : public Object<IAudioSessionEvents> {
public:
    SessionCallback(std::function<void()> action, std::shared_ptr<bool> destroyed, ComPtr<IAudioClient> retained)
        : Object(__uuidof(IAudioSessionEvents)), action_(std::move(action)), destroyed_(destroyed), retained_(std::move(retained)) {}
    HRESULT STDMETHODCALLTYPE OnDisplayNameChanged(LPCWSTR, LPCGUID) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnIconPathChanged(LPCWSTR, LPCGUID) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnSimpleVolumeChanged(float, BOOL, LPCGUID) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnChannelVolumeChanged(DWORD, float[], DWORD, LPCGUID) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnGroupingParamChanged(LPCGUID, LPCGUID) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnStateChanged(AudioSessionState) override { action_(); return S_OK; }
    HRESULT STDMETHODCALLTYPE OnSessionDisconnected(AudioSessionDisconnectReason) override { return S_OK; }
private:
    ~SessionCallback() override { *destroyed_ = true; }
    std::function<void()> action_;
    std::shared_ptr<bool> destroyed_;
    ComPtr<IAudioClient> retained_;
};
}
