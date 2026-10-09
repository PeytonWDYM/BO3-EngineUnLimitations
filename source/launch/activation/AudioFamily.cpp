#include "Runtime.h"

namespace activation {
class AudioFamily final : public Node, public IAudioClient, public IAudioRenderClient, public IAudioSessionControl {
public:
    AudioFamily(std::shared_ptr<Runtime> runtime, IUnknown* identity, ComPtr<IAudioClient> client,
        ComPtr<IAudioRenderClient> render, ComPtr<IAudioSessionControl> session)
        : Node(std::move(runtime), identity), client_(std::move(client)), render_(std::move(render)), session_(std::move(session)) {}
    HRESULT QueryKnown(REFIID iid, void** output) override { return QueryInterface(iid, output); }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        if (!output) return E_POINTER;
        *output = nullptr;
        if (iid == IID_IUnknown) *output = static_cast<IAudioClient*>(this);
        else if (iid == __uuidof(IAudioClient) && client_) *output = static_cast<IAudioClient*>(this);
        else if (iid == __uuidof(IAudioRenderClient) && render_) *output = static_cast<IAudioRenderClient*>(this);
        else if (iid == __uuidof(IAudioSessionControl) && session_) *output = static_cast<IAudioSessionControl*>(this);
        else return E_NOINTERFACE;
        AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return Node::AddRef(); }
    ULONG STDMETHODCALLTYPE Release() override { return Node::Release(); }
    HRESULT STDMETHODCALLTYPE Initialize(AUDCLNT_SHAREMODE a, DWORD b, REFERENCE_TIME c, REFERENCE_TIME d, const WAVEFORMATEX* e, LPCGUID f) override { return client_->Initialize(a, b, c, d, e, f); }
    HRESULT STDMETHODCALLTYPE GetBufferSize(UINT32* value) override { return client_->GetBufferSize(value); }
    HRESULT STDMETHODCALLTYPE GetStreamLatency(REFERENCE_TIME* value) override { return client_->GetStreamLatency(value); }
    HRESULT STDMETHODCALLTYPE GetCurrentPadding(UINT32* value) override { return client_->GetCurrentPadding(value); }
    HRESULT STDMETHODCALLTYPE IsFormatSupported(AUDCLNT_SHAREMODE a, const WAVEFORMATEX* b, WAVEFORMATEX** c) override { return client_->IsFormatSupported(a, b, c); }
    HRESULT STDMETHODCALLTYPE GetMixFormat(WAVEFORMATEX** value) override { return client_->GetMixFormat(value); }
    HRESULT STDMETHODCALLTYPE GetDevicePeriod(REFERENCE_TIME* a, REFERENCE_TIME* b) override { return client_->GetDevicePeriod(a, b); }
    HRESULT STDMETHODCALLTYPE Start() override { return client_->Start(); }
    HRESULT STDMETHODCALLTYPE Stop() override { return client_->Stop(); }
    HRESULT STDMETHODCALLTYPE Reset() override { return client_->Reset(); }
    HRESULT STDMETHODCALLTYPE SetEventHandle(HANDLE value) override { return client_->SetEventHandle(value); }
    HRESULT STDMETHODCALLTYPE GetService(REFIID iid, void** output) override {
        if (!output) return E_POINTER;
        *output = nullptr;
        if (iid != __uuidof(IAudioRenderClient) && iid != __uuidof(IAudioSessionControl)) return E_NOINTERFACE;
        void* value = nullptr;
        const HRESULT result = client_->GetService(iid, &value);
        if (FAILED(result)) return result;
        ComPtr<IUnknown> raw;
        raw.Attach(static_cast<IUnknown*>(value));
        const HRESULT wrapped = runtime_->Wrap(raw.Get(), Kind::Audio, iid, output);
        return FAILED(wrapped) ? wrapped : result;
    }
    HRESULT STDMETHODCALLTYPE GetBuffer(UINT32 frames, BYTE** output) override { return render_->GetBuffer(frames, output); }
    HRESULT STDMETHODCALLTYPE ReleaseBuffer(UINT32 frames, DWORD flags) override { return render_->ReleaseBuffer(frames, flags); }
    HRESULT STDMETHODCALLTYPE GetState(AudioSessionState* value) override { return session_->GetState(value); }
    HRESULT STDMETHODCALLTYPE GetDisplayName(LPWSTR* value) override { return session_->GetDisplayName(value); }
    HRESULT STDMETHODCALLTYPE SetDisplayName(LPCWSTR a, LPCGUID b) override { return session_->SetDisplayName(a, b); }
    HRESULT STDMETHODCALLTYPE GetIconPath(LPWSTR* value) override { return session_->GetIconPath(value); }
    HRESULT STDMETHODCALLTYPE SetIconPath(LPCWSTR a, LPCGUID b) override { return session_->SetIconPath(a, b); }
    HRESULT STDMETHODCALLTYPE GetGroupingParam(GUID* value) override { return session_->GetGroupingParam(value); }
    HRESULT STDMETHODCALLTYPE SetGroupingParam(LPCGUID a, LPCGUID b) override { return session_->SetGroupingParam(a, b); }
    HRESULT STDMETHODCALLTYPE RegisterAudioSessionNotification(IAudioSessionEvents* callback) override { return session_->RegisterAudioSessionNotification(callback); }
    HRESULT STDMETHODCALLTYPE UnregisterAudioSessionNotification(IAudioSessionEvents* callback) override { return session_->UnregisterAudioSessionNotification(callback); }
private:
    ComPtr<IAudioClient> client_;
    ComPtr<IAudioRenderClient> render_;
    ComPtr<IAudioSessionControl> session_;
};
std::unique_ptr<Node> MakeAudioNode(const std::shared_ptr<Runtime>& runtime, IUnknown* identity, HRESULT& result) {
    ComPtr<IAudioClient> client;
    ComPtr<IAudioRenderClient> rawRender, render;
    ComPtr<IAudioSessionControl> session;
    // Probe the complete known family before publishing a static IID set.
    result = identity->QueryInterface(__uuidof(IAudioClient), reinterpret_cast<void**>(client.GetAddressOf()));
    if (FAILED(result) && result != E_NOINTERFACE) return nullptr;
    result = identity->QueryInterface(__uuidof(IAudioRenderClient), reinterpret_cast<void**>(rawRender.GetAddressOf()));
    if (FAILED(result) && result != E_NOINTERFACE) return nullptr;
    result = identity->QueryInterface(__uuidof(IAudioSessionControl), reinterpret_cast<void**>(session.GetAddressOf()));
    if (FAILED(result) && result != E_NOINTERFACE) return nullptr;
    if (rawRender) {
        result = quiet::WrapRenderClient(rawRender.Get(), &render);
        if (FAILED(result)) return nullptr;
    }
    result = S_OK;
    return std::make_unique<AudioFamily>(runtime, identity, std::move(client), std::move(render), std::move(session));
}
}
