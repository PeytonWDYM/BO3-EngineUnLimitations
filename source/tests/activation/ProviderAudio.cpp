#include "ProviderCommon.h"
#include <cstring>

namespace activation_test {
#define OWNED_SESSION_METHODS \
    HRESULT STDMETHODCALLTYPE GetState(AudioSessionState* value) override { *value = AudioSessionStateActive; return S_OK; } \
    HRESULT STDMETHODCALLTYPE GetDisplayName(LPWSTR* value) override { *value = nullptr; return E_NOTIMPL; } \
    HRESULT STDMETHODCALLTYPE SetDisplayName(LPCWSTR, LPCGUID) override { return S_OK; } \
    HRESULT STDMETHODCALLTYPE GetIconPath(LPWSTR* value) override { *value = nullptr; return E_NOTIMPL; } \
    HRESULT STDMETHODCALLTYPE SetIconPath(LPCWSTR, LPCGUID) override { return S_OK; } \
    HRESULT STDMETHODCALLTYPE GetGroupingParam(GUID* value) override { *value = GUID_NULL; return S_OK; } \
    HRESULT STDMETHODCALLTYPE SetGroupingParam(LPCGUID, LPCGUID) override { return S_OK; } \
    HRESULT STDMETHODCALLTYPE RegisterAudioSessionNotification(IAudioSessionEvents* value) override { return notifications_.Register(value); } \
    HRESULT STDMETHODCALLTYPE UnregisterAudioSessionNotification(IAudioSessionEvents* value) override { return notifications_.Unregister(value); }

class Session final : public Object<IAudioSessionControl> {
public:
    Session(std::shared_ptr<State> state, std::shared_ptr<Generation> generation)
        : Object(__uuidof(IAudioSessionControl)), notifications_(std::move(state), std::move(generation)) {}
    OWNED_SESSION_METHODS
private:
    SessionMethods notifications_;
};
class Client final : public IAudioClient, public IAudioRenderClient, public IAudioSessionControl {
public:
    Client(std::shared_ptr<State> state, std::shared_ptr<Generation> generation)
        : state_(std::move(state)), generation_(std::move(generation)), render_(fixture::MakeRender(generation_->render)),
          session_(Make<IAudioSessionControl, Session>(state_, generation_)), notifications_(state_, generation_) {}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        if (!output) return E_POINTER;
        *output = nullptr;
        if (iid == IID_IUnknown || iid == __uuidof(IAudioClient) || iid == fixture::EscapeId) *output = static_cast<IAudioClient*>(this);
        else if (state_->sharedIdentity && iid == __uuidof(IAudioRenderClient)) *output = static_cast<IAudioRenderClient*>(this);
        else if (state_->sharedIdentity && iid == __uuidof(IAudioSessionControl)) *output = static_cast<IAudioSessionControl*>(this);
        else return E_NOINTERFACE;
        AddRef();
        return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++references_; }
    ULONG STDMETHODCALLTYPE Release() override { const ULONG value = --references_; if (!value) delete this; return value; }
    HRESULT STDMETHODCALLTYPE Initialize(AUDCLNT_SHAREMODE mode, DWORD flags, REFERENCE_TIME duration, REFERENCE_TIME period, const WAVEFORMATEX* format, LPCGUID session) override {
        state_->Event("provider.client.initialize", generation_->id);
        if (FAILED(state_->initializeError)) return state_->initializeError;
        if (mode != AUDCLNT_SHAREMODE_SHARED || flags != (AUDCLNT_STREAMFLAGS_EVENTCALLBACK | AUDCLNT_STREAMFLAGS_NOPERSIST) || duration != 250000 || period != 0 || session || format->nChannels != 2) return E_INVALIDARG;
        generation_->initialized = true;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetBufferSize(UINT32* value) override { *value = 8; return S_OK; }
    HRESULT STDMETHODCALLTYPE GetStreamLatency(REFERENCE_TIME* value) override { *value = 250000; return S_OK; }
    HRESULT STDMETHODCALLTYPE GetCurrentPadding(UINT32* value) override { *value = 0; return S_OK; }
    HRESULT STDMETHODCALLTYPE IsFormatSupported(AUDCLNT_SHAREMODE, const WAVEFORMATEX*, WAVEFORMATEX** closest) override { if (closest) *closest = nullptr; return S_OK; }
    HRESULT STDMETHODCALLTYPE GetMixFormat(WAVEFORMATEX** value) override {
        *value = static_cast<WAVEFORMATEX*>(CoTaskMemAlloc(sizeof(WAVEFORMATEX)));
        if (!*value) return E_OUTOFMEMORY;
        **value = {WAVE_FORMAT_IEEE_FLOAT, 2, 48000, 384000, 8, 32, 0};
        state_->Event("provider.client.mix-format", generation_->id);
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetDevicePeriod(REFERENCE_TIME* normal, REFERENCE_TIME* minimum) override { if (normal) *normal = 250000; if (minimum) *minimum = 100000; return S_OK; }
    HRESULT STDMETHODCALLTYPE Start() override {
        if (!generation_->initialized || !generation_->event) return AUDCLNT_E_NOT_INITIALIZED;
        generation_->started = true;
        state_->Event("provider.client.start", generation_->id);
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE Stop() override { generation_->started = false; state_->Event("provider.client.stop", generation_->id); return S_OK; }
    HRESULT STDMETHODCALLTYPE Reset() override { state_->Event("provider.client.reset", generation_->id); return S_OK; }
    HRESULT STDMETHODCALLTYPE SetEventHandle(HANDLE event) override { generation_->event = event; state_->Event("provider.client.event", generation_->id); return S_OK; }
    HRESULT STDMETHODCALLTYPE GetService(REFIID iid, void** output) override {
        *output = nullptr;
        state_->Event(iid == __uuidof(IAudioRenderClient) ? "provider.service.render" : "provider.service.session", generation_->id);
        if (FAILED(state_->serviceError)) return state_->serviceError;
        if (!generation_->initialized) return AUDCLNT_E_NOT_INITIALIZED;
        if (state_->sharedIdentity) return QueryInterface(iid, output);
        if (iid == __uuidof(IAudioRenderClient)) return render_->QueryInterface(iid, output);
        if (iid == __uuidof(IAudioSessionControl)) return session_->QueryInterface(iid, output);
        return E_NOINTERFACE;
    }
    HRESULT STDMETHODCALLTYPE GetBuffer(UINT32 frames, BYTE** data) override { if (!generation_->initialized) return AUDCLNT_E_NOT_INITIALIZED; return render_->GetBuffer(frames, data); }
    HRESULT STDMETHODCALLTYPE ReleaseBuffer(UINT32 frames, DWORD flags) override { return render_->ReleaseBuffer(frames, flags); }
    OWNED_SESSION_METHODS
private:
    ~Client() { state_->Event("provider.client.destroy", generation_->id); }
    std::atomic<ULONG> references_{1};
    std::shared_ptr<State> state_;
    std::shared_ptr<Generation> generation_;
    ComPtr<IAudioRenderClient> render_;
    ComPtr<IAudioSessionControl> session_;
    SessionMethods notifications_;
};
#undef OWNED_SESSION_METHODS
ComPtr<IAudioClient> MakeClient(const std::shared_ptr<State>& state, const std::shared_ptr<Generation>& generation) { return Make<IAudioClient, Client>(state, generation); }
}
