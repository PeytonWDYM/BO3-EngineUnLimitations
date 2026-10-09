#include "ProviderCommon.h"

namespace activation_test {
class Buffer final : public Object<IDirectSoundBuffer8> {
public:
    Buffer(std::shared_ptr<State> state, std::shared_ptr<Generation> generation)
        : Object(IID_IDirectSoundBuffer8), state_(std::move(state)), generation_(std::move(generation)), sink_(fixture::MakeSound(generation_->sound)) {}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        if (iid == IID_IDirectSoundBuffer8 && !state_->buffer8) { *output = nullptr; state_->Event("provider.buffer8.unsupported", generation_->id); return E_NOINTERFACE; }
        if (iid == IID_IDirectSoundBuffer) { *output = static_cast<IDirectSoundBuffer*>(this); AddRef(); return S_OK; }
        if (iid == IID_IDirectSoundBuffer8) state_->Event("provider.buffer8.query", generation_->id);
        return Object::QueryInterface(iid, output);
    }
    HRESULT STDMETHODCALLTYPE GetCaps(LPDSBCAPS value) override { return sink_->GetCaps(value); }
    HRESULT STDMETHODCALLTYPE GetCurrentPosition(LPDWORD a, LPDWORD b) override { return sink_->GetCurrentPosition(a, b); }
    HRESULT STDMETHODCALLTYPE GetFormat(LPWAVEFORMATEX a, DWORD b, LPDWORD c) override { return sink_->GetFormat(a, b, c); }
    HRESULT STDMETHODCALLTYPE GetVolume(LPLONG a) override { return sink_->GetVolume(a); }
    HRESULT STDMETHODCALLTYPE GetPan(LPLONG a) override { return sink_->GetPan(a); }
    HRESULT STDMETHODCALLTYPE GetFrequency(LPDWORD a) override { return sink_->GetFrequency(a); }
    HRESULT STDMETHODCALLTYPE GetStatus(LPDWORD a) override { return sink_->GetStatus(a); }
    HRESULT STDMETHODCALLTYPE Initialize(LPDIRECTSOUND a, LPCDSBUFFERDESC b) override { return sink_->Initialize(a, b); }
    HRESULT STDMETHODCALLTYPE Lock(DWORD a, DWORD b, LPVOID* c, LPDWORD d, LPVOID* e, LPDWORD f, DWORD g) override {
        state_->Event(g & DSBLOCK_ENTIREBUFFER ? "provider.buffer.clear-lock" : "provider.buffer.write-lock", generation_->id);
        return sink_->Lock(a, b, c, d, e, f, g);
    }
    HRESULT STDMETHODCALLTYPE Play(DWORD a, DWORD b, DWORD c) override { state_->Event("provider.buffer.play", generation_->id); return sink_->Play(a, b, c); }
    HRESULT STDMETHODCALLTYPE SetCurrentPosition(DWORD a) override { return sink_->SetCurrentPosition(a); }
    HRESULT STDMETHODCALLTYPE SetFormat(LPCWAVEFORMATEX a) override { return sink_->SetFormat(a); }
    HRESULT STDMETHODCALLTYPE SetVolume(LONG a) override { return sink_->SetVolume(a); }
    HRESULT STDMETHODCALLTYPE SetPan(LONG a) override { return sink_->SetPan(a); }
    HRESULT STDMETHODCALLTYPE SetFrequency(DWORD a) override { return sink_->SetFrequency(a); }
    HRESULT STDMETHODCALLTYPE Stop() override { state_->Event("provider.buffer.stop", generation_->id); return sink_->Stop(); }
    HRESULT STDMETHODCALLTYPE Unlock(LPVOID a, DWORD b, LPVOID c, DWORD d) override { state_->Event("provider.buffer.unlock", generation_->id); return sink_->Unlock(a, b, c, d); }
    HRESULT STDMETHODCALLTYPE Restore() override { state_->Event("provider.buffer.restore", generation_->id); return sink_->Restore(); }
    HRESULT STDMETHODCALLTYPE SetFX(DWORD a, LPDSEFFECTDESC b, LPDWORD c) override { return sink_->SetFX(a, b, c); }
    HRESULT STDMETHODCALLTYPE AcquireResources(DWORD a, DWORD b, LPDWORD c) override { return sink_->AcquireResources(a, b, c); }
    HRESULT STDMETHODCALLTYPE GetObjectInPath(REFGUID a, DWORD b, REFGUID c, LPVOID* d) override { return sink_->GetObjectInPath(a, b, c, d); }
private:
    std::shared_ptr<State> state_;
    std::shared_ptr<Generation> generation_;
    ComPtr<IDirectSoundBuffer8> sink_;
};
class DirectSound final : public Object<IDirectSound8> {
public:
    explicit DirectSound(std::shared_ptr<State> state) : Object(IID_IDirectSound8), state_(std::move(state)) {}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        if (iid == IID_IDirectSound) { *output = static_cast<IDirectSound*>(this); AddRef(); return S_OK; }
        return Object::QueryInterface(iid, output);
    }
    HRESULT STDMETHODCALLTYPE CreateSoundBuffer(LPCDSBUFFERDESC description, LPDIRECTSOUNDBUFFER* output, LPUNKNOWN outer) override {
        *output = nullptr;
        state_->Event("provider.buffer.create-base");
        if (FAILED(state_->bufferError)) return state_->bufferError;
        if (outer) return CLASS_E_NOAGGREGATION;
        auto generation = state_->NewGeneration();
        generation->sound = fixture::MakeSoundState(description->lpwfxFormat->wFormatTag, description->lpwfxFormat->wBitsPerSample, description->lpwfxFormat->nChannels);
        generation->sound->caps = description->dwFlags;
        generation->sound->lockError = state_->clearError;
        auto buffer = Make<IDirectSoundBuffer8, Buffer>(state_, generation);
        return buffer->QueryInterface(IID_IDirectSoundBuffer, reinterpret_cast<void**>(output));
    }
    HRESULT STDMETHODCALLTYPE GetCaps(LPDSCAPS value) override { value->dwFlags = 0; return S_OK; }
    HRESULT STDMETHODCALLTYPE DuplicateSoundBuffer(LPDIRECTSOUNDBUFFER source, LPDIRECTSOUNDBUFFER* output) override {
        state_->Event("provider.buffer.duplicate.raw");
        *output = source; source->AddRef(); return S_OK;
    }
    HRESULT STDMETHODCALLTYPE SetCooperativeLevel(HWND, DWORD level) override { state_->Event("provider.device.cooperative"); return level == DSSCL_PRIORITY ? S_OK : E_INVALIDARG; }
    HRESULT STDMETHODCALLTYPE Compact() override { return S_OK; }
    HRESULT STDMETHODCALLTYPE GetSpeakerConfig(LPDWORD value) override { *value = DSSPEAKER_STEREO; return S_OK; }
    HRESULT STDMETHODCALLTYPE SetSpeakerConfig(DWORD) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE Initialize(LPCGUID) override { return DSERR_ALREADYINITIALIZED; }
    HRESULT STDMETHODCALLTYPE VerifyCertification(LPDWORD value) override { *value = DS_CERTIFIED; return S_OK; }
private:
    std::shared_ptr<State> state_;
};
ComPtr<IDirectSound8> MakeDirectSound(const std::shared_ptr<State>& state) { return Make<IDirectSound8, DirectSound>(state); }
}
